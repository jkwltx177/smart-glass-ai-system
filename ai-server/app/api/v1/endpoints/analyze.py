from datetime import datetime
from time import perf_counter
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import Device, Incident, IncidentAsset
from app.schemas.api_models import (
    DiagnosticActionPlan,
    DiagnosticPredictive,
    DiagnosticReferenceDoc,
    DiagnosticResponse,
)
from app.services.auth.token_verifier import verify_bearer_token
from app.services.aiops import emit_aiops_event
from app.services.pipeline.workflow import app_pipeline


router = APIRouter()


def _strip_markdown_asterisks(text: str) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("**", "")
        .replace("__", "")
        .replace("* ", "")
        .replace(" *", " ")
    )


def _normalize_action_steps(steps: List[str], explanation: str) -> List[str]:
    placeholder = "상세 조치 내용은 아래 분석 결과를 확인하세요."
    cleaned: List[str] = []
    for step in steps:
        s = _strip_markdown_asterisks(step).strip()
        if not s:
            continue
        if s == placeholder:
            continue
        if explanation and s in explanation:
            continue
        if s not in cleaned:
            cleaned.append(s)
    return cleaned


def _persist_asset(
    db: Session,
    incident_id: int,
    asset_type: str,
    file_name: str,
    file_bytes: bytes,
    mime_type: Optional[str],
) -> None:
    asset = IncidentAsset(
        incident_id=incident_id,
        asset_type=asset_type,
        file_name=file_name,
        file_path=f"/tmp/{uuid.uuid4()}_{file_name}",
        mime_type=mime_type,
        file_size=len(file_bytes),
    )
    db.add(asset)


def _to_reference_docs(raw_docs: Any, top_k: int) -> List[DiagnosticReferenceDoc]:
    if not isinstance(raw_docs, list):
        return []
    docs: List[DiagnosticReferenceDoc] = []
    for item in raw_docs[:top_k]:
        if isinstance(item, dict):
            docs.append(
                DiagnosticReferenceDoc(
                    doc_id=str(item.get("doc_id", "unknown")),
                    content=str(item.get("content", "")),
                    score=item.get("score"),
                    metadata=item.get("metadata", {}) or {},
                )
            )
    return docs


@router.post("/diagnostic", response_model=DiagnosticResponse)
async def analyze_diagnostic(
    equipment_id: str = Form(...),
    site: str = Form("Unknown Site"),
    line: str = Form("Unknown Line"),
    device_type: str = Form("Unknown"),
    audio_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    rag_top_k: int = Form(3),
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    """
    로그인 토큰을 검증하고 STT/Vision/예측/RAG를 하나의 API로 실행한다.
    실패가 발생해도 fallback으로 전체 파이프라인이 끊기지 않도록 처리한다.
    """
    started_at = perf_counter()
    device = db.query(Device).filter(Device.device_id == equipment_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {equipment_id} not found")

    incident = Incident(
        device_id=equipment_id,
        site=site,
        line=line,
        device_type=device_type,
        title=f"Diagnostic for {equipment_id}",
        description=f"Triggered by user {token_payload.get('sub', 'unknown')}",
        status="PROCESSING",
        severity="INFO",
        started_at=datetime.utcnow(),
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    emit_aiops_event(
        event_type="diagnostic_requested",
        severity="INFO",
        service="analyze",
        stage="request",
        incident_id=int(incident.incident_id),
        device_id=equipment_id,
        status="accepted",
        message="Integrated diagnostic requested",
        payload={
            "site": site,
            "line": line,
            "device_type": device_type,
            "rag_top_k": rag_top_k,
        },
        db=db,
    )

    fallbacks: List[str] = []
    audio_bytes: Optional[bytes] = None
    image_bytes: Optional[bytes] = None
    assets: List[Dict[str, str]] = []

    if audio_file is not None:
        try:
            audio_bytes = await audio_file.read()
            _persist_asset(
                db=db,
                incident_id=int(incident.incident_id),
                asset_type="audio",
                file_name=audio_file.filename or "audio.webm",
                file_bytes=audio_bytes,
                mime_type=audio_file.content_type,
            )
            assets.append({"type": "audio", "filename": audio_file.filename or "audio.webm"})
        except Exception as e:
            fallbacks.append(f"audio_ingest_error:{str(e)}")

    if image_file is not None:
        try:
            image_bytes = await image_file.read()
            _persist_asset(
                db=db,
                incident_id=int(incident.incident_id),
                asset_type="image",
                file_name=image_file.filename or "image.jpg",
                file_bytes=image_bytes,
                mime_type=image_file.content_type,
            )
            assets.append({"type": "image", "filename": image_file.filename or "image.jpg"})
        except Exception as e:
            fallbacks.append(f"image_ingest_error:{str(e)}")

    db.commit()

    initial_state = {
        "incident_id": str(incident.incident_id),
        "equipment_id": equipment_id,
        "audio_content": audio_bytes,
        "image_content": image_bytes,
        "assets": assets,
        "rag_top_k": rag_top_k,
        "pipeline_fallbacks": fallbacks,
    }

    try:
        result = app_pipeline.invoke(initial_state)
        incident.status = "COMPLETED"
        incident.ended_at = datetime.utcnow()
    except Exception as e:
        incident.status = "FAILED"
        incident.ended_at = datetime.utcnow()
        db.commit()
        fallback_message = f"pipeline_runtime_error:{str(e)}"
        fallbacks.append(fallback_message)
        emit_aiops_event(
            event_type="pipeline_failed",
            severity="HIGH",
            service="analyze",
            stage="pipeline",
            incident_id=int(incident.incident_id),
            device_id=equipment_id,
            status="failed",
            message="Integrated pipeline failed",
            payload={"error": str(e), "fallback_count": len(fallbacks)},
            db=db,
        )
        result = {
            "transcription": "음성 분석 결과 없음",
            "vision_analysis": "이미지 분석 결과 없음",
            "failure_probability": 0.5,
            "predicted_rul": 180.0,
            "anomaly_score": 0.5,
            "prediction_model": "fallback-default",
            "final_action_plan": {
                "steps": ["기본 안전 점검을 수행하세요."],
                "risk_level": "MEDIUM",
                "escalation_required": False,
            },
            "explanation": "파이프라인 오류로 기본 응답을 반환합니다.",
            "rag_retrieved_docs": [],
            "pipeline_fallbacks": fallbacks,
        }

    fp = float(result.get("failure_probability", 0.5) or 0.5)
    rul = float(result.get("predicted_rul", 180.0) or 180.0)
    anomaly = float(result.get("anomaly_score", 0.5) or 0.5)
    confidence = max(0.0, min(1.0, 1.0 - fp))
    action_plan = result.get("final_action_plan", {}) or {}
    reference_docs = _to_reference_docs(result.get("rag_retrieved_docs", []), top_k=max(1, rag_top_k))
    pipeline_fallbacks = list(result.get("pipeline_fallbacks", []))
    clean_answer = _strip_markdown_asterisks(str(result.get("explanation", "")))
    clean_steps = _normalize_action_steps(
        list(action_plan.get("steps", ["기본 점검 수행"])),
        clean_answer,
    )

    # PDF 보고서 생성 시 최신 설명/조치가 반영되도록 description 갱신
    incident.description = (
        f"Triggered by user {token_payload.get('sub', 'unknown')}\n\n"
        "[분석 결과]\n"
        f"{clean_answer}\n\n"
        "[조치 절차]\n"
        + "\n".join(f"- {step}" for step in clean_steps)
    )
    incident.updated_at = datetime.utcnow()
    db.commit()
    latency_ms = round((perf_counter() - started_at) * 1000.0, 2)
    severity = "HIGH" if pipeline_fallbacks else "INFO"
    emit_aiops_event(
        event_type="pipeline_completed" if incident.status == "COMPLETED" else "pipeline_failed",
        severity=severity,
        service="analyze",
        stage="response",
        incident_id=int(incident.incident_id),
        device_id=equipment_id,
        model_name=str(result.get("prediction_model", "unknown")),
        status=str(incident.status).lower(),
        message="Integrated diagnostic finished",
        payload={
            "latency_ms": latency_ms,
            "fallback_count": len(pipeline_fallbacks),
            "failure_probability": fp,
            "predicted_rul_minutes": rul,
            "anomaly_score": anomaly,
            "risk_level": str(action_plan.get("risk_level", result.get("risk_level", "MEDIUM"))),
            "escalation_required": bool(action_plan.get("escalation_required", False)),
        },
        db=db,
    )
    if pipeline_fallbacks:
        emit_aiops_event(
            event_type="pipeline_fallback",
            severity="MEDIUM",
            service="analyze",
            stage="response",
            incident_id=int(incident.incident_id),
            device_id=equipment_id,
            status="degraded",
            message="Diagnostic completed with fallbacks",
            payload={"fallbacks": pipeline_fallbacks},
            db=db,
        )

    return DiagnosticResponse(
        status="success",
        incident_id=str(incident.incident_id),
        equipment_id=equipment_id,
        transcription=str(result.get("transcription", "음성 분석 결과 없음")),
        vision_analysis=str(result.get("vision_analysis", "이미지 분석 결과 없음")),
        predictive_ai=DiagnosticPredictive(
            predicted_rul_minutes=rul,
            failure_probability=fp,
            anomaly_score=anomaly,
            model=str(result.get("prediction_model", "unknown")),
        ),
        action_plan=DiagnosticActionPlan(
            steps=clean_steps,
            risk_level=str(action_plan.get("risk_level", result.get("risk_level", "MEDIUM"))),
            escalation_required=bool(action_plan.get("escalation_required", False)),
        ),
        answer=clean_answer,
        confidence=round(confidence, 4),
        reference_docs=reference_docs,
        pipeline_fallbacks=pipeline_fallbacks,
    )

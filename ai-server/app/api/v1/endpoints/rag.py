from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException
from typing import Optional
from sqlalchemy.orm import Session
from app.schemas.api_models import RAGQueryResponse, ActionPlan
from app.services.pipeline.workflow import app_pipeline
from app.core.database import get_db
from app.models.domain import Incident, IncidentAsset, Device
from datetime import datetime
import uuid

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


@router.post("/query", response_model=RAGQueryResponse)
async def run_rag_query_with_files(
    audio: UploadFile = File(...),
    image: Optional[UploadFile] = File(None),
    equipment_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Multipart 파일을 받아 DB에 사건을 생성하고 LangGraph 파이프라인 구동 후 결과 반환"""
    device = db.query(Device).filter(Device.device_id == equipment_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {equipment_id} not found")
    
    # 1. DB에 사건(Incident) 레코드 임시 생성
    new_incident = Incident(
        device_id=equipment_id,
        site=(device.location or "Unknown Site"),
        line=(device.line_or_site or "Unknown Line"),
        device_type=(device.vehicle_type or "Unknown"),
        title=f"Multi-Modal Query ({device.device_name or equipment_id})",
        description="음성/이미지 기반 RAG 쿼리",
        status="PROCESSING",
        severity="INFO",
        started_at=datetime.utcnow()
    )
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)
    
    incident_id = new_incident.incident_id

    # 2. 파일 데이터 읽기 및 자산(Asset) 레코드 저장
    audio_bytes = await audio.read()
    
    audio_asset = IncidentAsset(
        incident_id=incident_id,
        asset_type="audio",
        file_name=audio.filename,
        file_path=f"/tmp/{uuid.uuid4()}_{audio.filename}",
        file_size=len(audio_bytes)
    )
    db.add(audio_asset)
    
    image_bytes = None
    if image:
        image_bytes = await image.read()
        image_asset = IncidentAsset(
            incident_id=incident_id,
            asset_type="image",
            file_name=image.filename,
            file_path=f"/tmp/{uuid.uuid4()}_{image.filename}",
            file_size=len(image_bytes)
        )
        db.add(image_asset)

    db.commit()

    # 3. 초기 상태 설정
    initial_state = {
        "incident_id": str(incident_id),
        "equipment_id": equipment_id,
        "audio_content": audio_bytes,
        "image_content": image_bytes,
        "assets": [
            {"type": "audio", "filename": audio.filename if audio else "audio.webm"},
            {"type": "image", "filename": image.filename if image else "image.jpg"}
        ]
    }
    
    # 4. 파이프라인 구동
    try:
        result = app_pipeline.invoke(initial_state)
        final_plan_data = result.get("final_action_plan", {}) or {}
        steps = list(final_plan_data.get("steps", ["기본 점검 수행"]))
        clean_explanation = _strip_markdown_asterisks(result.get("explanation", "결과 분석 중입니다."))
        clean_steps = [_strip_markdown_asterisks(step) for step in steps]

        # PDF 보고서가 실제 분석 결과를 반영하도록 incident.description 갱신
        new_incident.description = (
            "[분석 결과]\n"
            f"{clean_explanation}\n\n"
            "[조치 절차]\n"
            + "\n".join(f"- {step}" for step in clean_steps)
        )
        
        # 분석 완료 상태 업데이트
        new_incident.status = "COMPLETED"
        new_incident.ended_at = datetime.utcnow()
        new_incident.updated_at = datetime.utcnow()
        db.commit()
        
    except Exception as e:
        new_incident.status = "FAILED"
        new_incident.description = f"파이프라인 실행 오류: {str(e)}"
        new_incident.ended_at = datetime.utcnow()
        db.commit()
        
        return RAGQueryResponse(
            action_plan=ActionPlan(steps=["에러 발생"], risk_level="ERROR", escalation_required=True),
            explanation=f"파이프라인 실행 중 오류: {str(e)}",
            evidence=[]
        )

    # 5. 결과 파싱
    final_plan_data = result.get("final_action_plan", {}) or {}
    clean_explanation = _strip_markdown_asterisks(result.get("explanation", "결과 분석 중입니다."))
    clean_steps = [_strip_markdown_asterisks(step) for step in final_plan_data.get("steps", ["기본 점검 수행"])]
    
    return RAGQueryResponse(
        action_plan=ActionPlan(
            steps=clean_steps,
            risk_level=final_plan_data.get("risk_level", "NORMAL"),
            escalation_required=final_plan_data.get("escalation_required", False)
        ),
        explanation=clean_explanation,
        evidence=result.get("evidence", []),
        incident_id=str(incident_id)
    )

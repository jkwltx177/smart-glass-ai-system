from fastapi import APIRouter, UploadFile, File, Depends, Form
from typing import Optional
from sqlalchemy.orm import Session
from app.schemas.api_models import RAGQueryResponse, ActionPlan
from app.services.pipeline.workflow import app_pipeline
from app.core.database import get_db
from app.models.domain import Incident, IncidentAsset
from datetime import datetime
import uuid

router = APIRouter()

@router.post("/query", response_model=RAGQueryResponse)
async def run_rag_query_with_files(
    audio: UploadFile = File(...),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """Multipart 파일을 받아 DB에 사건을 생성하고 LangGraph 파이프라인 구동 후 결과 반환"""
    
    # 1. DB에 사건(Incident) 레코드 임시 생성
    new_incident = Incident(
        device_id="EQ-UNKNOWN",
        site="Unknown Site",
        line="Unknown Line",
        device_type="Unknown",
        title="Multi-Modal Query",
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
        
        # 분석 완료 상태 업데이트
        new_incident.status = "COMPLETED"
        new_incident.updated_at = datetime.utcnow()
        db.commit()
        
    except Exception as e:
        new_incident.status = "FAILED"
        db.commit()
        
        return RAGQueryResponse(
            action_plan=ActionPlan(steps=["에러 발생"], risk_level="ERROR", escalation_required=True),
            explanation=f"파이프라인 실행 중 오류: {str(e)}",
            evidence=[]
        )

    # 5. 결과 파싱
    final_plan_data = result.get("final_action_plan", {})
    
    return RAGQueryResponse(
        action_plan=ActionPlan(
            steps=final_plan_data.get("steps", ["기본 점검 수행"]),
            risk_level=final_plan_data.get("risk_level", "NORMAL"),
            escalation_required=final_plan_data.get("escalation_required", False)
        ),
        explanation=result.get("explanation", "결과 분석 중입니다."),
        evidence=result.get("evidence", [])
    )

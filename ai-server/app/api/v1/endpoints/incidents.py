"""
Incident Management & Multi-Modal Analysis Endpoints

주요 기능:
1. 사건(Incident) 생성 및 관리 (DB 연동)
2. 음성 파일 업로드 및 STT 처리
3. 이미지 파일 업로드 및 Vision LLM 분석
4. 멀티모달 통합 분석 (음성 + 이미지)
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, status
import uuid
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.domain import Incident, IncidentAsset

from app.schemas.api_models import (
    IncidentCreate, 
    IncidentResponse,
    STTResponse,
    VisionAnalysisResponse,
    MultiModalAnalysisResponse,
)

# Import Services
from app.services.speech.stt_service import process_audio_upload
from app.services.vision.vision_service import process_image_upload, encode_image_to_base64

# ============================================
# 라우터 생성
# ============================================

router = APIRouter()

# ============================================
# 1. 사건 생성 및 관리
# ============================================

@router.post("/", response_model=IncidentResponse)
async def create_incident(data: IncidentCreate, db: Session = Depends(get_db)):
    """
    새로운 사건을 데이터베이스에 생성합니다.
    """
    # 1. SQLAlchemy Incident 객체 생성
    new_incident = Incident(
        device_id=data.equipment_id,
        site=data.site,
        line=data.line,
        device_type=data.device_type,
        title=f"Incident for {data.equipment_id}",
        description=data.description or "",
        status="OPEN",
        severity="MEDIUM",
        started_at=datetime.utcnow()
    )
    
    # 2. DB 저장
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)
    
    return IncidentResponse(
        incident_id=str(new_incident.incident_id),
        status=new_incident.status,
        created_at=new_incident.created_at
    )


@router.get("/{incident_id}")
async def get_incident_detail(incident_id: int, db: Session = Depends(get_db)):
    """
    사건의 상세 정보를 DB에서 조회합니다.
    """
    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    assets = db.query(IncidentAsset).filter(IncidentAsset.incident_id == incident_id).all()
    
    return {
        "incident_id": str(incident.incident_id),
        "site": incident.site,
        "line": incident.line,
        "device_type": incident.device_type,
        "equipment_id": incident.device_id,
        "description": incident.description,
        "created_at": incident.created_at,
        "status": incident.status,
        "assets": [{"asset_id": a.asset_id, "type": a.asset_type, "filename": a.file_name} for a in assets],
    }


@router.get("/")
async def list_incidents(site: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    """
    사건 목록을 조회합니다.
    """
    query = db.query(Incident).order_by(Incident.created_at.desc())
    if site:
        query = query.filter(Incident.site == site)
        
    incidents = query.limit(limit).all()
    
    results = []
    for inc in incidents:
        results.append({
            "incident_id": str(inc.incident_id),
            "site": inc.site,
            "device_id": inc.device_id,
            "device_type": inc.device_type,
            "status": inc.status,
            "created_at": inc.created_at
        })
    
    return results


# ============================================
# 2. 음성 파일 처리 (STT)
# ============================================

@router.post("/{incident_id}/audio", response_model=STTResponse)
async def upload_audio(
    incident_id: int,
    audio_file: UploadFile = File(...),
    analysis_context: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    사건에 음성 파일을 업로드하고 STT 처리합니다.
    """
    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    try:
        file_content = await audio_file.read()
        filename = audio_file.filename
        
        # 파일 저장 (예시용: /tmp 또는 지정된 볼륨 경로에 저장)
        file_path = f"/tmp/{uuid.uuid4()}_{filename}"
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        # DB에 Asset 등록
        asset = IncidentAsset(
            incident_id=incident_id,
            asset_type="audio",
            file_name=filename,
            file_path=file_path,
            mime_type=audio_file.content_type,
            file_size=len(file_content)
        )
        db.add(asset)
        db.commit()

        # STT 처리
        transcription = process_audio_upload(file_content, filename)
        
        return STTResponse(
            transcription=transcription,
            confidence=0.95,
            duration_ms=None,
            language="ko",
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio processing failed: {str(e)}"
        )


# ============================================
# 3. 이미지 파일 처리 (Vision)
# ============================================

@router.post("/{incident_id}/image", response_model=VisionAnalysisResponse)
async def upload_image(
    incident_id: int,
    image_file: UploadFile = File(...),
    analysis_type: str = Form("general"),
    db: Session = Depends(get_db)
):
    """
    사건에 이미지 파일을 업로드하고 Vision LLM으로 분석합니다.
    """
    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    try:
        file_content = await image_file.read()
        filename = image_file.filename
        
        file_path = f"/tmp/{uuid.uuid4()}_{filename}"
        with open(file_path, "wb") as f:
            f.write(file_content)
            
        asset = IncidentAsset(
            incident_id=incident_id,
            asset_type="image",
            file_name=filename,
            file_path=file_path,
            mime_type=image_file.content_type,
            file_size=len(file_content)
        )
        db.add(asset)
        db.commit()

        # Vision 분석
        result = process_image_upload(file_content, filename, analysis_type)
        
        return VisionAnalysisResponse(
            analysis=result["analysis"],
            analysis_type=analysis_type,
            filename=filename,
            media_type=result["media_type"],
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image analysis failed: {str(e)}"
        )


# ============================================
# 4. 멀티모달 통합 분석
# ============================================

@router.post("/{incident_id}/analyze", response_model=MultiModalAnalysisResponse)
async def multimodal_analysis(
    incident_id: int,
    audio_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    analysis_type: str = Form("general"),
    analysis_context: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    음성과 이미지를 동시에 처리하고 통합 분석합니다.
    """
    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    if not audio_file and not image_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of audio_file or image_file is required"
        )
    
    transcription = None
    vision_analysis = None
    assets_info = {}
    
    try:
        # 1. 음성 처리 및 DB 저장
        if audio_file:
            audio_content = await audio_file.read()
            file_path = f"/tmp/{uuid.uuid4()}_{audio_file.filename}"
            with open(file_path, "wb") as f:
                f.write(audio_content)
                
            db.add(IncidentAsset(
                incident_id=incident_id, asset_type="audio", file_name=audio_file.filename,
                file_path=file_path, file_size=len(audio_content)
            ))
            
            transcription = process_audio_upload(audio_content, audio_file.filename)
            assets_info["audio"] = audio_file.filename
        
        # 2. 이미지 처리 및 DB 저장
        if image_file:
            image_content = await image_file.read()
            file_path = f"/tmp/{uuid.uuid4()}_{image_file.filename}"
            with open(file_path, "wb") as f:
                f.write(image_content)
                
            db.add(IncidentAsset(
                incident_id=incident_id, asset_type="image", file_name=image_file.filename,
                file_path=file_path, file_size=len(image_content)
            ))
            
            image_result = process_image_upload(image_content, image_file.filename, analysis_type)
            vision_analysis = image_result["analysis"]
            assets_info["image"] = image_file.filename
            
        # 3. 통합 요약 생성
        integrated_summary = _generate_integrated_summary(
            transcription,
            vision_analysis,
            incident.device_type,
            incident.device_id,
            analysis_context,
        )
        
        incident.status = "ANALYZED"
        incident.updated_at = datetime.utcnow()
        db.commit()
        
        return MultiModalAnalysisResponse(
            incident_id=str(incident_id),
            transcription=transcription,
            vision_analysis=vision_analysis,
            integrated_summary=integrated_summary,
            assets=assets_info,
        )
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )

def _generate_integrated_summary(
    transcription: Optional[str],
    vision_analysis: Optional[str],
    device_type: str,
    equipment_id: str,
    context: Optional[str],
) -> str:
    summary_parts = []
    summary_parts.append(f"장비 분석 보고서 ({device_type} / {equipment_id})")
    summary_parts.append("=" * 50)
    
    if transcription:
        summary_parts.append("\n[현장 보고]")
        summary_parts.append(transcription)
    if vision_analysis:
        summary_parts.append("\n[이미지 분석]")
        summary_parts.append(vision_analysis)
    if context:
        summary_parts.append("\n[추가 정보]")
        summary_parts.append(context)
        
    summary_parts.append("\n" + "=" * 50)
    summary_parts.append("분석 완료")
    
    return "\n".join(summary_parts)

"""
Incident Management & Multi-Modal Analysis Endpoints

주요 기능:
1. 사건(Incident) 생성 및 관리
2. 음성 파일 업로드 및 STT 처리
3. 이미지 파일 업로드 및 Vision LLM 분석
4. 멀티모달 통합 분석 (음성 + 이미지)
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from fastapi.responses import JSONResponse
import uuid
import os
from datetime import datetime
from typing import Optional, Dict, Any

from app.schemas.api_models import (
    IncidentCreate, 
    IncidentResponse,
    STTResponse,
    VisionAnalysisResponse,
    MultiModalAnalysisRequest,
    MultiModalAnalysisResponse,
)

# Import Services
from app.services.speech.stt_service import process_audio_upload
from app.services.vision.vision_service import process_image_upload, encode_image_to_base64

# ============================================
# 라우터 생성
# ============================================

router = APIRouter()

# 메모리 저장소 (프로토타입용; 실제 프로덕션에서는 DB 사용)
incidents_db: Dict[str, Dict[str, Any]] = {}
assets_db: Dict[str, Dict[str, Any]] = {}


# ============================================
# 1. 사건 생성 및 관리
# ============================================

@router.post("/", response_model=IncidentResponse)
async def create_incident(data: IncidentCreate):
    """
    새로운 사건을 생성합니다.
    
    Request:
    ```json
    {
        "site": "Plant A",
        "line": "Line 1",
        "device_type": "Pump",
        "equipment_id": "EQ-2024-X1",
        "description": "비정상 진동 감지"
    }
    ```
    """
    incident_id = str(uuid.uuid4())
    
    incident = {
        "incident_id": incident_id,
        "site": data.site,
        "line": data.line,
        "device_type": data.device_type,
        "equipment_id": data.equipment_id,
        "description": data.description or "",
        "created_at": datetime.utcnow(),
        "status": "created",
        "assets": {},
    }
    
    incidents_db[incident_id] = incident
    
    return IncidentResponse(
        incident_id=incident_id,
        status="created"
    )


@router.get("/{incident_id}")
async def get_incident_detail(incident_id: str):
    """
    사건의 상세 정보를 조회합니다.
    """
    if incident_id not in incidents_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    incident = incidents_db[incident_id]
    return {
        "incident_id": incident_id,
        "site": incident["site"],
        "line": incident["line"],
        "device_type": incident["device_type"],
        "equipment_id": incident["equipment_id"],
        "description": incident["description"],
        "created_at": incident["created_at"],
        "status": incident["status"],
        "assets": incident["assets"],
    }


@router.get("/")
async def list_incidents(site: Optional[str] = None, limit: int = 50):
    """
    사건 목록을 조회합니다.
    
    Query Parameters:
    - site: 특정 사이트로 필터링 (선택사항)
    - limit: 반환할 최대 항목 수 (기본값: 50)
    """
    results = list(incidents_db.values())
    
    if site:
        results = [r for r in results if r["site"] == site]
    
    return results[:limit]


# ============================================
# 2. 음성 파일 처리 (STT)
# ============================================

@router.post("/{incident_id}/audio", response_model=STTResponse)
async def upload_audio(
    incident_id: str,
    audio_file: UploadFile = File(...),
    analysis_context: Optional[str] = Form(None),
):
    """
    사건에 음성 파일을 업로드하고 STT 처리합니다.
    
    Supported formats: .webm, .mp3, .wav, .m4a, .ogg
    
    Request:
    - audio_file: 음성 파일 (바이너리)
    - analysis_context: 분석 컨텍스트 (선택사항)
    
    Returns:
    - transcription: 변환된 텍스트
    - confidence: 신뢰도 (0-1)
    - duration_ms: 음성 길이 (ms)
    - language: 감지된 언어
    """
    if incident_id not in incidents_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    try:
        # 파일 데이터 읽기
        file_content = await audio_file.read()
        filename = audio_file.filename
        
        # STT 처리
        transcription = process_audio_upload(file_content, filename)
        
        # 사건에 음성 정보 저장
        asset_id = str(uuid.uuid4())
        incidents_db[incident_id]["assets"][asset_id] = {
            "type": "audio",
            "filename": filename,
            "transcription": transcription,
            "context": analysis_context,
            "timestamp": datetime.utcnow(),
        }
        
        return STTResponse(
            transcription=transcription,
            confidence=0.95,  # Whisper는 기본적으로 높은 신뢰도
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
    incident_id: str,
    image_file: UploadFile = File(...),
    analysis_type: str = Form("general"),
):
    """
    사건에 이미지 파일을 업로드하고 Vision LLM으로 분석합니다.
    
    Supported formats: .jpg, .jpeg, .png, .gif, .webp
    
    Request:
    - image_file: 이미지 파일 (바이너리)
    - analysis_type: 분석 유형 (general|damage|maintenance)
    
    Analysis Types:
    - general: 일반적 상태 분석
    - damage: 손상 및 결함 감지
    - maintenance: 유지보수 필요사항 판단
    
    Returns:
    - analysis: Vision LLM 분석 결과
    - analysis_type: 적용된 분석 유형
    - filename: 원본 파일 이름
    - media_type: MIME 타입
    """
    if incident_id not in incidents_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    if analysis_type not in ["general", "damage", "maintenance"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid analysis_type. Must be: general, damage, or maintenance"
        )
    
    try:
        # 파일 데이터 읽기
        file_content = await image_file.read()
        filename = image_file.filename
        
        # Vision 분석
        result = process_image_upload(file_content, filename, analysis_type)
        
        # 사건에 이미지 정보 저장
        asset_id = str(uuid.uuid4())
        incidents_db[incident_id]["assets"][asset_id] = {
            "type": "image",
            "filename": filename,
            "analysis": result["analysis"],
            "analysis_type": analysis_type,
            "timestamp": datetime.utcnow(),
        }
        
        return VisionAnalysisResponse(
            analysis=result["analysis"],
            analysis_type=analysis_type,
            filename=filename,
            media_type=result["media_type"],
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image format: {str(e)}"
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
    incident_id: str,
    audio_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    analysis_type: str = Form("general"),
    analysis_context: Optional[str] = Form(None),
):
    """
    음성과 이미지를 동시에 처리하고 통합 분석합니다.
    
    이 엔드포인트는:
    1. 음성 파일을 받아 STT로 문자화
    2. 이미지 파일을 받아 Vision LLM으로 분석
    3. 두 결과를 통합하여 최종 진단 생성
    
    Request (multipart/form-data):
    - audio_file: 음성 파일 (선택사항)
    - image_file: 이미지 파일 (선택사항)
    - analysis_type: "general" | "damage" | "maintenance"
    - analysis_context: 추가 컨텍스트 정보
    
    Returns:
    - incident_id: 사건 ID
    - transcription: STT 결과 (음성 있을 경우)
    - vision_analysis: Vision 분석 결과 (이미지 있을 경우)
    - integrated_summary: 통합 분석 결과
    """
    if incident_id not in incidents_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    if not audio_file and not image_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of audio_file or image_file is required"
        )
    
    transcription = None
    vision_analysis = None
    
    try:
        # 1. 음성 처리
        if audio_file:
            audio_content = await audio_file.read()
            transcription = process_audio_upload(audio_content, audio_file.filename)
        
        # 2. 이미지 처리
        if image_file:
            image_content = await image_file.read()
            image_result = process_image_upload(image_content, image_file.filename, analysis_type)
            vision_analysis = image_result["analysis"]
        
        # 3. 통합 분석
        integrated_summary = _generate_integrated_summary(
            transcription,
            vision_analysis,
            incidents_db[incident_id]["device_type"],
            incidents_db[incident_id]["equipment_id"],
            analysis_context,
        )
        
        # 사건에 분석 결과 저장
        incidents_db[incident_id]["status"] = "analyzed"
        
        assets = {}
        if audio_file:
            assets["audio"] = audio_file.filename
        if image_file:
            assets["image"] = image_file.filename
        
        return MultiModalAnalysisResponse(
            incident_id=incident_id,
            transcription=transcription,
            vision_analysis=vision_analysis,
            integrated_summary=integrated_summary,
            assets=assets,
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )


# ============================================
# 유틸리티 함수
# ============================================

def _generate_integrated_summary(
    transcription: Optional[str],
    vision_analysis: Optional[str],
    device_type: str,
    equipment_id: str,
    context: Optional[str],
) -> str:
    """
    음성과 이미지 분석 결과를 통합하여 최종 요약을 생성합니다.
    
    Args:
        transcription: STT 결과
        vision_analysis: Vision LLM 분석 결과
        device_type: 장비 유형
        equipment_id: 장비 ID
        context: 추가 컨텍스트
        
    Returns:
        통합 분석 요약
    """
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

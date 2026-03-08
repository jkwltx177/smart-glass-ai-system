from fastapi import APIRouter, UploadFile, File
from typing import Optional
from app.schemas.api_models import RAGQueryResponse, ActionPlan
from app.services.pipeline.workflow import app_pipeline

router = APIRouter()

@router.post("/query", response_model=RAGQueryResponse)
async def run_rag_query_with_files(
    audio: UploadFile = File(...),
    image: Optional[UploadFile] = File(None)
):
    """Multipart 파일을 받아 LangGraph 파이프라인 구동 후 결과 반환"""
    
    # 1. 파일 데이터 읽기
    audio_bytes = await audio.read()
    image_bytes = await image.read() if image else None

    # 2. 초기 상태 설정
    initial_state = {
        "incident_id": "test-incident-123",
        "audio_content": audio_bytes,
        "image_content": image_bytes,
        "assets": [
            {"type": "audio", "filename": audio.filename if audio else "audio.webm"},
            {"type": "image", "filename": image.filename if image else "image.jpg"}
        ]
    }
    
    # 3. 파이프라인 구동 (안전을 위해 try-except 권장되나 Mock 상태이므로 직접 호출)
    try:
        result = app_pipeline.invoke(initial_state)
    except Exception as e:
        # 파이프라인 중단 시 기본값 반환하여 프론트엔드 hang 방지
        return RAGQueryResponse(
            action_plan=ActionPlan(steps=["에러 발생"], risk_level="ERROR", escalation_required=True),
            explanation=f"파이프라인 실행 중 오류: {str(e)}",
            evidence=[]
        )

    # 4. 결과 파싱 (workflow.py의 reasoning_node와 키 일치 확인)
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

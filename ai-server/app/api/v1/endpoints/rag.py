from fastapi import APIRouter, UploadFile, File, Form, Optional
from app.schemas.api_models import RAGQueryResponse, ActionPlan
from app.services.pipeline.workflow import app_pipeline

router = APIRouter()

@router.post("/query", response_model=RAGQueryResponse)
async def run_rag_query_with_files(
    audio: UploadFile = File(...),          # App.vue의 'audio' 필드와 일치
    image: Optional[UploadFile] = File(None) # App.vue의 'image' 필드와 일치
):
    """프론트엔드 업로드 파일(음성, 이미지)을 받아 즉시 RAG 파이프라인 구동"""
    
    # 1. 파일 데이터 읽기
    audio_bytes = await audio.read()
    image_bytes = await image.read() if image else None

    # 2. 파이프라인 초기 상태 설정 (사용자 정의 흐름 시작)
    initial_state = {
        "incident_id": "incident-from-upload", # 실제 운영 시 UUID 생성 혹은 DB 연동
        "audio_content": audio_bytes,
        "image_content": image_bytes
    }
    
    # 3. LangGraph 파이프라인 구동 (분석 -> 텍스트화 -> RAG -> 답변)
    result = app_pipeline.invoke(initial_state)

    # 4. 결과 매핑 및 반환
    return RAGQueryResponse(
        action_plan=ActionPlan(
            steps=result.get("final_action_plan", {}).get("steps", []),
            risk_level=result.get("final_action_plan", {}).get("risk_level", "NORMAL"),
            escalation_required=result.get("final_action_plan", {}).get("escalation_required", False)
        ),
        explanation=result.get("explanation", ""),
        evidence=result.get("evidence", [])
    )

@router.get("/outputs/{incident_id}")
async def get_rag_outputs(incident_id: str):
    return {"incident_id": incident_id, "latest_output": "ECU 냉각 상태 점검 필요"}

# --- 이전 버전 (주석 보존: JSON 전용) ---
# from app.schemas.api_models import RAGQueryRequest
# @router.post("/query_json", response_model=RAGQueryResponse)
# async def run_rag_query(request: RAGQueryRequest):
#     if request.incident_id == "demo-maf-sensor":
#         return RAGQueryResponse(...)
#     return RAGQueryResponse(...)

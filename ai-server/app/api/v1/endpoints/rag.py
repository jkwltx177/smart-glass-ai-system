from fastapi import APIRouter
from app.schemas.api_models import RAGQueryRequest, RAGQueryResponse, ActionPlan

router = APIRouter()

@router.post("/query", response_model=RAGQueryResponse)
async def run_rag_query(request: RAGQueryRequest):
    # 데모 시나리오 기반 Mock 응답 분기
    if request.incident_id == "demo-maf-sensor":
        return RAGQueryResponse(
            action_plan=ActionPlan(
                steps=["1. 센서 커넥터 확인", "2. 센서 청소", "3. 흡기 라인 점검"],
                risk_level="MEDIUM",
                escalation_required=False
            ),
            explanation="DTC P0101 기반 공기 유량 센서 성능 저하가 의심됩니다. 오염이나 누설 여부를 먼저 확인하세요.",
            evidence=["Manual P0101 Section 4.2", "Case Study: dirty MAF sensor on Engine X"]
        )
    
    # 기본 응답
    return RAGQueryResponse(
        action_plan=ActionPlan(steps=["기본 점검 수행"], risk_level="LOW", escalation_required=False),
        explanation="분석된 정보에 근거한 일반적인 조치입니다.",
        evidence=[]
    )

@router.get("/outputs/{incident_id}")
async def get_rag_outputs(incident_id: str):
    return {"incident_id": incident_id, "latest_output": "ECU 냉각 상태 점검 필요"}

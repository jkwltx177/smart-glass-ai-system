from langgraph.graph import StateGraph, END
from .state import AgentState

def data_ingestion_node(state: AgentState):
    """사건 ID로부터 관련 자산 및 텔레메트리 데이터를 로드하는 단계"""
    # 실제로는 DB에서 incident_id로 조회
    return {
        "equipment_id": "EQ-MAF-001",
        "telemetry_data": {"airflow": "unstable", "fuel_trim": "+18%"}
    }

def speech_vision_analysis_node(state: AgentState):
    """음성 및 이미지 동시 분석 (Multi-modal)"""
    return {
        "transcription": "엔진 출력이 약함",
        "vision_analysis": "MAF 센서 주변 먼지 고착 확인"
    }

def predictive_ai_node(state: AgentState):
    """RUL 및 고장 확률 예측"""
    return {"failure_probability": 0.67, "predicted_rul": 180.0}

def rag_knowledge_node(state: AgentState):
    """KB에서 매뉴얼 및 과거 사례 검색"""
    return {"rag_context": ["Manual P0101: MAF 센서 청소 절차", "Case: Dirty MAF causes P0101"]}

def reasoning_node(state: AgentState):
    """최종 조치 방안 및 근거 생성 (LLM)"""
    return {
        "final_action_plan": {
            "steps": ["센서 커넥터 확인", "센서 청소", "흡기 라인 점검"],
            "risk_level": "MEDIUM",
            "escalation_required": False
        },
        "explanation": "DTC P0101 기반 공기 유량 센서 성능 저하가 의심됩니다.",
        "evidence": ["Manual P0101 Section 4.2"]
    }

def create_integrated_pipeline():
    workflow = StateGraph(AgentState)

    workflow.add_node("ingestion", data_ingestion_node)
    workflow.add_node("analysis", speech_vision_analysis_node)
    workflow.add_node("prediction", predictive_ai_node)
    workflow.add_node("rag", rag_knowledge_node)
    workflow.add_node("reasoning", reasoning_node)

    workflow.set_entry_point("ingestion")
    workflow.add_edge("ingestion", "analysis")
    workflow.add_edge("analysis", "prediction")
    workflow.add_edge("prediction", "rag")
    workflow.add_edge("rag", "reasoning")
    workflow.add_edge("reasoning", END)

    return workflow.compile()

app_pipeline = create_integrated_pipeline()

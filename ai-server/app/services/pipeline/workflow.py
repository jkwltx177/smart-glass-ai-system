from langgraph.graph import StateGraph, END
from .state import AgentState

# 실제 구현 시에는 각 서비스 모듈에서 함수를 가져옵니다.
# from app.services.speech import stt_service
# from app.services.vision import vision_service
# from app.services.prediction import prediction_service
# from app.services.rag import rag_service

def speech_to_text_node(state: AgentState):
    # Mock 로직 (실제 서비스 연결 전)
    return {"transcription": "펌프에서 이상한 소음이 발생하고 진동이 심함"}

def vision_analysis_node(state: AgentState):
    # Mock 로직
    return {"vision_results": "펌프 배관 연결부위 미세 누유 및 마찰 흔적 발견"}

def predictive_ai_node(state: AgentState):
    # Mock 로직 (기존 예측 모델 연결 예정)
    return {"failure_probability": 0.85, "predicted_rul": 12.5}

def rag_search_node(state: AgentState):
    # Mock 로직 (VectorDB 검색 연결 예정)
    return {"rag_context": ["매뉴얼 [PUMP-M-01]: 소음 발생 시 조인트 씰 점검", "유사사례: 24년 1월 누유로 인한 모터 과열 건"]}

def llm_reasoning_node(state: AgentState):
    # 모든 정보를 취합하여 최종 결과 구성
    return {
        "final_report": "설비 긴급 점검 및 부품 교체 권고",
        "risk_level": "HIGH",
        "steps": [
            "1. 즉시 펌프 가동 중지",
            "2. 연결부위 누유 차단 밸브 잠금",
            "3. 매뉴얼 [PUMP-M-01]에 따라 조인트 씰 교체"
        ],
        "escalation_required": True
    }

def create_pipeline():
    workflow = StateGraph(AgentState)

    workflow.add_node("stt", speech_to_text_node)
    workflow.add_node("vision", vision_analysis_node)
    workflow.add_node("prediction", predictive_ai_node)
    workflow.add_node("rag", rag_search_node)
    workflow.add_node("reasoning", llm_reasoning_node)

    workflow.set_entry_point("stt")
    workflow.add_edge("stt", "vision")
    workflow.add_edge("vision", "prediction")
    workflow.add_edge("prediction", "rag")
    workflow.add_edge("rag", "reasoning")
    workflow.add_edge("reasoning", END)

    return workflow.compile()

app_pipeline = create_pipeline()

from langgraph.graph import StateGraph, END
from .state import AgentState

def data_ingestion_node(state: AgentState):
    """Step 1: 데이터 로드 (Mock)"""
    return {
        "equipment_id": "EQ-MAF-001",
        "telemetry_data": {"airflow": "unstable", "fuel_trim": "+18%"}
    }

def speech_vision_analysis_node(state: AgentState):
    """Step 2-1: 분석 및 텍스트화 (Mock)"""
    return {
        "transcription": "엔진 출력 저하 경고 발생",
        "vision_analysis": "MAF 센서 주변 먼지 고착"
    }

def predictive_ai_node(state: AgentState):
    """Step 2-2: 예측 및 텍스트화 (Mock)"""
    prob, rul = 0.67, 180.0
    summary = f"고장 확률 {prob*100}%, RUL {rul}분 예상"
    return {
        "predicted_rul": rul,
        "prediction_summary_text": summary
    }

def rag_knowledge_node(state: AgentState):
    """Step 4: 유사 로그 검색 (Mock)"""
    return {
        "rag_context": ["유사사례: 센서 클리닝으로 해결됨"]
    }

def reasoning_node(state: AgentState):
    """Step 5: 최종 해결책 생성 (Mock)"""
    # 중요: rag.py에서 이 결과를 읽을 수 있도록 구조를 맞춤
    return {
        "final_action_plan": {
            "steps": ["1. 커넥터 점검", "2. 센서 클리닝", "3. 재시동"],
            "risk_level": "MEDIUM",
            "escalation_required": False
        },
        "explanation": "MAF 센서 오염으로 인한 성능 저하가 의심됩니다.",
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

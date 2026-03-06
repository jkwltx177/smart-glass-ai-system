from langgraph.graph import StateGraph, END
from .state import AgentState

def data_ingestion_node(state: AgentState):
    """사건 ID로부터 관련 자산 및 텔레메트리 데이터를 로드 (Step 1)"""
    return {
        "equipment_id": "EQ-MAF-001",
        "telemetry_data": {"airflow": "unstable", "fuel_trim": "+18%"}
    }

def speech_vision_analysis_node(state: AgentState):
    """음성 및 이미지 분석 -> 텍스트 설명 생성 (Step 2-1)"""
    return {
        "transcription": "DTC P0101 감지: 엔진 출력이 약하고 가속 시 울컥거림 발생",
        "vision_analysis": "MAF 센서 커넥터 주변 먼지 오염 및 배선 피복 손상 흔적 발견"
    }

def predictive_ai_node(state: AgentState):
    """LSTM 예측 수행 -> 예측 결과를 텍스트로 변환 (Step 2-2)"""
    prob = 0.67
    rul = 180.0
    summary_text = f"시계열 데이터 분석 결과, 고장 확률 {prob*100}%이며 잔여 수명은 약 {rul}분으로 예측됩니다."
    return {
        "predicted_rul": rul,
        "prediction_summary_text": summary_text
    }

def rag_knowledge_node(state: AgentState):
    """취합된 모든 텍스트 기반으로 VectorDB 유사도 검색 (Step 4)"""
    combined_query = f"""
    [에러/상황]: {state.get('transcription')}
    [이미지 분석]: {state.get('vision_analysis')}
    [예측 결과]: {state.get('prediction_summary_text')}
    """
    similar_logs = [
        "과거사례 A: P0101 발생 시 센서 클리닝으로 출력 저하 80% 개선됨",
        "매뉴얼 B: MAF 센서 전압 불안정 시 커넥터 접점 부활제 사용 권장"
    ]
    return {"rag_context": similar_logs}

def reasoning_node(state: AgentState):
    """유사 로그를 참고하여 최종 해결 답변 생성 (Step 5)"""
    return {
        "final_action_plan": {
            "steps": ["1. 센서 커넥터 세척", "2. 에어클리너 박스 누설 점검", "3. MAF 센서 초기화"],
            "risk_level": "MEDIUM",
            "escalation_required": False
        },
        "explanation": "취합된 데이터와 과거 사례를 분석한 결과, 센서 오염이 주요 원인으로 판단됩니다.",
        "evidence": state.get("rag_context", [])
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

# --- 이전 버전 (주석 보존) ---
# def data_ingestion_node_v1(state: AgentState):
#     """사건 ID로부터 관련 자산 및 텔레메트리 데이터를 로드하는 단계"""
#     return {
#         "equipment_id": "EQ-MAF-001",
#         "telemetry_data": {"airflow": "unstable", "fuel_trim": "+18%"}
#     }
# 
# def speech_vision_analysis_node_v1(state: AgentState):
#     """음성 및 이미지 동시 분석 (Multi-modal)"""
#     return {
#         "transcription": "엔진 출력이 약함",
#         "vision_analysis": "MAF 센서 주변 먼지 고착 확인"
#     }
# 
# def predictive_ai_node_v1(state: AgentState):
#     """RUL 및 고장 확률 예측"""
#     return {"failure_probability": 0.67, "predicted_rul": 180.0}
# 
# def rag_knowledge_node_v1(state: AgentState):
#     """KB에서 매뉴얼 및 과거 사례 검색"""
#     return {"rag_context": ["Manual P0101: MAF 센서 청소 절차", "Case: Dirty MAF causes P0101"]}
# 
# def reasoning_node_v1(state: AgentState):
#     """최종 조치 방안 및 근거 생성 (LLM)"""
#     return {
#         "final_action_plan": {
#             "steps": ["센서 커넥터 확인", "센서 청소", "흡기 라인 점검"],
#             "risk_level": "MEDIUM",
#             "escalation_required": False
#         },
#         "explanation": "DTC P0101 기반 공기 유량 센서 성능 저하가 의심됩니다.",
#         "evidence": ["Manual P0101 Section 4.2"]
#     }

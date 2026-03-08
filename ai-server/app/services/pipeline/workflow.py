from langgraph.graph import StateGraph, END
from .state import AgentState
from app.services.speech.stt_service import process_audio_upload
from app.services.vision.vision_service import process_image_upload

def data_ingestion_node(state: AgentState):
    """Step 1: 데이터 로드 (Mock)"""
    return {
        "equipment_id": "EQ-MAF-001",
        "telemetry_data": {"airflow": "unstable", "fuel_trim": "+18%"}
    }

def speech_vision_analysis_node(state: AgentState):
    """Step 2-1: 분석 및 텍스트화"""
    transcription = "음성 분석 결과 없음"
    vision_analysis = "이미지 분석 결과 없음"

    if state.get("audio_content"):
        filename = "audio.webm"
        assets = state.get("assets", [])
        for asset in assets:
            if asset.get("type") == "audio":
                filename = asset.get("filename", "audio.webm")
        try:
            transcription = process_audio_upload(state["audio_content"], filename)
        except Exception as e:
            transcription = f"STT 에러: {str(e)}"

    if state.get("image_content"):
        filename = "image.jpg"
        assets = state.get("assets", [])
        for asset in assets:
            if asset.get("type") == "image":
                filename = asset.get("filename", "image.jpg")
        try:
            # 기본적으로 general 분석을 수행합니다. 필요에 따라 변경 가능
            image_result = process_image_upload(state["image_content"], filename, "general")
            vision_analysis = image_result.get("analysis", "분석 결과 없음")
        except Exception as e:
            vision_analysis = f"비전 분석 에러: {str(e)}"

    return {
        "transcription": transcription,
        "vision_analysis": vision_analysis
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
    transcription = state.get("transcription", "")
    vision_analysis = state.get("vision_analysis", "")
    
    # 중요: rag.py에서 이 결과를 읽을 수 있도록 구조를 맞춤
    return {
        "final_action_plan": {
            "steps": ["1. 커넥터 점검", "2. 센서 클리닝", "3. 재시동"],
            "risk_level": "MEDIUM",
            "escalation_required": False
        },
        "explanation": f"[음성인식]: {transcription}\n[비전분석]: {vision_analysis}\n\n[진단결과]: MAF 센서 오염으로 인한 성능 저하가 의심됩니다.",
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

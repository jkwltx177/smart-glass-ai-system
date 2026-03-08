from langgraph.graph import StateGraph, END
from .state import AgentState
from app.services.speech.stt_service import process_audio_upload
from app.services.vision.vision_service import process_image_upload
from app.services.rag.rag_pipeline import RAGInput, init_sample_store, run_rag_pipeline
from app.core.database import SessionLocal
from app.models.domain import ErrorLog

# RAG 벡터 스토어 전역 초기화
faiss_store = init_sample_store()

def data_ingestion_node(state: AgentState):
    """Step 1: 데이터 로드 (DB에서 에러 로그 조회 및 센서 데이터 Mock)"""
    device_id = state.get("equipment_id", "DEV-MAF-01")
    
    # DB에서 에러 로그 조회
    recent_errors = []
    try:
        with SessionLocal() as db:
            logs = db.query(ErrorLog).filter(ErrorLog.device_id == device_id).order_by(ErrorLog.error_timestamp.desc()).limit(3).all()
            for log in logs:
                recent_errors.append({
                    "timestamp": str(log.error_timestamp),
                    "error_code": log.dtc_code,
                    "message": log.dtc_description
                })
    except Exception as e:
        print(f"Error fetching logs from DB: {e}")
        
    return {
        "equipment_id": device_id,
        "telemetry_data": {"airflow": "unstable", "fuel_trim": "+18%"},
        "recent_error_logs": recent_errors
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
    """Step 4: RAG 파이프라인 (검색 및 응답 생성 통합)"""
    transcription = state.get("transcription", "")
    vision_analysis = state.get("vision_analysis", "")
    
    # AI Payload 조립 (RAGInput 구조에 맞춤)
    ai_payload = {
        "device_id": state.get("equipment_id", "Unknown"),
        "predictive_ai": {
            "predicted_rul_minutes": state.get("predicted_rul", 180),
            "failure_probability": 0.67,
            "anomaly_score": 0.81,
        },
        "timeseries_summary": state.get("telemetry_data", {}),
        "recent_error_logs": state.get("recent_error_logs", [])
    }
    
    rag_input = RAGInput(
        user_query=transcription,
        image_description=vision_analysis,
        ai_payload=ai_payload
    )
    
    # RAG 파이프라인 실행
    rag_result = run_rag_pipeline(rag_input=rag_input, vector_store=faiss_store, top_k=3)
    
    # 문서 내용만 추출
    context_docs = [doc["content"] for doc in rag_result.retrieved_docs]
    
    return {
        "rag_context": context_docs,
        "explanation": rag_result.answer,
        "risk_level": "HIGH" if rag_result.escalation_needed else "MEDIUM",
        "escalation_required": rag_result.escalation_needed
    }

def reasoning_node(state: AgentState):
    """Step 5: 최종 해결책 포맷팅"""
    # RAG 노드에서 생성된 답변을 프론트엔드 포맷으로 래핑
    explanation = state.get("explanation", "분석 결과를 생성하지 못했습니다.")
    risk_level = state.get("risk_level", "NORMAL")
    escalation = state.get("escalation_required", False)
    rag_context = state.get("rag_context", [])
    
    # GPT 응답에서 조치 절차(Action) 부분을 대략적으로 추출하여 steps로 나눔
    # (실제로는 LLM 응답을 JSON으로 받아야 더 깔끔하지만, 현재는 텍스트 통짜 응답이므로 분리 생략 가능)
    
    return {
        "final_action_plan": {
            "steps": ["상세 조치 내용은 아래 분석 결과를 확인하세요."],
            "risk_level": risk_level,
            "escalation_required": escalation
        },
        "explanation": explanation,
        "evidence": rag_context
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

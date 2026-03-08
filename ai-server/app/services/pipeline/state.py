from typing import TypedDict, List, Optional, Any

class AgentState(TypedDict, total=False): # total=False 추가로 유연성 확보
    # 1. 입력 데이터
    incident_id: str
    equipment_id: Optional[str]
    audio_content: Optional[bytes]
    image_content: Optional[bytes]
    assets: Optional[List[dict]]
    telemetry_data: Optional[dict]
    recent_error_logs: Optional[List[dict]]
    
    # 2. 분석 결과
    transcription: Optional[str]
    vision_analysis: Optional[str]
    predicted_rul: Optional[float]
    prediction_summary_text: Optional[str]
    
    # 3. RAG 관련
    rag_context: Optional[List[str]]
    
    # 5. 최종 결과 (중요: 이 키들이 명확해야 함)
    final_action_plan: Optional[dict]
    explanation: Optional[str]
    evidence: Optional[List[str]]
    risk_level: Optional[str]
    escalation_required: Optional[bool]

# --- 이전 버전 (주석 보존) ---
# class AgentState(TypedDict):
#     incident_id: str
#     equipment_id: Optional[str]
#     audio_content: Optional[bytes]
#     image_content: Optional[bytes]
#     ... (생략)

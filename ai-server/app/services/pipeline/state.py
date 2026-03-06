from typing import TypedDict, List, Optional, Any

class AgentState(TypedDict):
    # 1. 입력 데이터 (Incident 중심 + 파일 바이너리)
    incident_id: str
    equipment_id: Optional[str]
    audio_content: Optional[bytes]      # 추가: 업로드된 음성 바이너리
    image_content: Optional[bytes]      # 추가: 업로드된 이미지 바이너리
    assets: Optional[List[dict]]
    telemetry_data: Optional[dict]
    
    # 2. 분석 결과 (이미지 -> 텍스트, 음성 -> 텍스트, LSTM -> 텍스트)
    transcription: Optional[str]
    vision_analysis: Optional[str]
    predicted_rul: Optional[float]
    prediction_summary_text: Optional[str]
    
    # 3. RAG 관련
    rag_context: Optional[List[str]]
    
    # 5. 최종 결과
    final_action_plan: Optional[dict]
    explanation: Optional[str]
    evidence: Optional[List[str]]
    risk_level: Optional[str]
    escalation_required: Optional[bool]

# --- 이전 버전 (주석 보존) ---
# class AgentState(TypedDict):
#     incident_id: str
#     equipment_id: Optional[str]
#     assets: List[dict]
#     telemetry_data: dict
#     transcription: Optional[str]
#     vision_analysis: Optional[str]
#     predicted_rul: Optional[float]
#     prediction_summary_text: Optional[str]
#     rag_context: Optional[List[str]]
#     final_action_plan: Optional[dict]
#     explanation: Optional[str]
#     evidence: Optional[List[str]]
#     risk_level: Optional[str]
#     escalation_required: Optional[bool]

from typing import TypedDict, List, Optional

class AgentState(TypedDict):
    # 입력 데이터
    equipment_id: str
    audio_content: Optional[bytes]
    image_content: Optional[bytes]
    
    # 처리 중간 결과
    transcription: Optional[str]
    vision_results: Optional[str]
    failure_probability: Optional[float]
    predicted_rul: Optional[float]
    rag_context: Optional[List[str]]
    
    # 최종 결과
    final_report: Optional[str]
    risk_level: Optional[str]
    steps: Optional[List[str]]
    escalation_required: Optional[bool]

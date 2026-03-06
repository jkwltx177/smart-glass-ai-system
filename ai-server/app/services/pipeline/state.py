from typing import TypedDict, List, Optional, Any

class AgentState(TypedDict):
    # 입력 데이터 (Incident 중심)
    incident_id: str
    equipment_id: Optional[str]
    
    # 수집된 자산 및 데이터
    assets: List[Dict[str, Any]]  # 이미지, 음성 파일 정보
    telemetry_data: Dict[str, Any] # 센서 수치류
    
    # 처리 중간 결과
    transcription: Optional[str]
    vision_analysis: Optional[str]
    failure_probability: Optional[float]
    predicted_rul: Optional[float]
    rag_context: Optional[List[str]]
    
    # 최종 결과 (A~F 명세 기반)
    final_action_plan: Optional[Dict[str, Any]]
    explanation: Optional[str]
    evidence: Optional[List[str]]
    risk_level: Optional[str]
    escalation_required: Optional[bool]

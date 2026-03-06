from typing import TypedDict, List, Optional, Any

class AgentState(TypedDict):
    # 1. 입력 데이터 (Incident 중심)
    incident_id: str
    equipment_id: Optional[str]
    assets: List[dict]  # 이미지, 음성 파일 정보
    telemetry_data: dict # 센서 수치류
    
    # 2. 분석 결과 (이미지 -> 텍스트, 음성 -> 텍스트, LSTM -> 텍스트)
    transcription: Optional[str]        # 음성/에러코드 설명 텍스트
    vision_analysis: Optional[str]      # 이미지 설명 텍스트
    predicted_rul: Optional[float]      # LSTM 수치 결과
    prediction_summary_text: Optional[str] # LSTM 결과를 설명하는 텍스트
    
    # 3. RAG 관련 (유사 로그 검색 결과)
    rag_context: Optional[List[str]]    # VectorDB에서 가져온 유사 로그들
    
    # 5. 최종 결과 (해결 답변 생성)
    final_action_plan: Optional[dict]   # 단계별 조치 방안
    explanation: Optional[str]          # 상세 설명
    evidence: Optional[List[str]]       # 근거 자료
    risk_level: Optional[str]
    escalation_required: Optional[bool]

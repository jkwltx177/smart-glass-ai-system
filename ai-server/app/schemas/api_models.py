from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- A. Incidents (Enhanced with Multi-Modal Support) ---
class IncidentCreate(BaseModel):
    site: str
    line: str
    device_type: str
    equipment_id: str
    description: Optional[str] = None
    timestamp: Optional[datetime] = None

class IncidentResponse(BaseModel):
    incident_id: str
    status: str = "created"
    created_at: datetime = Field(default_factory=datetime.utcnow)

# --- Audio/Speech Analysis ---
class STTResponse(BaseModel):
    transcription: str
    confidence: Optional[float] = None
    duration_ms: Optional[int] = None
    language: str = "ko"

class AudioUploadRequest(BaseModel):
    incident_id: str
    audio_metadata: Optional[Dict[str, Any]] = None

# --- Image/Vision Analysis ---
class VisionAnalysisResponse(BaseModel):
    analysis: str
    analysis_type: str  # "general", "damage", "maintenance"
    filename: str
    media_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ImageComparisonRequest(BaseModel):
    incident_id: str
    context: Optional[str] = None  # "과거 vs 현재", "정상 vs 비정상"

class ImageComparisonResponse(BaseModel):
    comparison_result: str
    files_compared: List[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# --- Multimodal Analysis (통합 분석) ---
class MultiModalAnalysisRequest(BaseModel):
    incident_id: str
    equipment_id: str
    site: Optional[str] = None
    audio_metadata: Optional[Dict[str, Any]] = None
    vision_analysis_type: str = "general"  # "general", "damage", "maintenance"

class MultiModalAnalysisResponse(BaseModel):
    incident_id: str
    transcription: Optional[str] = None
    vision_analysis: Optional[str] = None
    integrated_summary: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    assets: Dict[str, Any] = {}

# --- B. KB ---
class KBIngestResponse(BaseModel):
    source_id: str
    chunk_count: int

# --- C. RAG ---
class RAGQueryRequest(BaseModel):
    incident_id: Optional[str] = None
    query_spec: Optional[str] = None

class ActionPlan(BaseModel):
    steps: List[str]
    risk_level: str
    escalation_required: bool

class RAGQueryResponse(BaseModel):
    action_plan: ActionPlan
    explanation: str
    evidence: List[str]
    incident_id: Optional[str] = None

# --- D. Predictive ---
class PredictionRequest(BaseModel):
    incident_id: str

class PredictionResponse(BaseModel):
    failure_probability: float
    predicted_rul: float
    model_version: str

# --- E. AIOps ---
class MetricsResponse(BaseModel):
    timestamps: List[str]
    rmse_values: List[float]

# --- F. Reports ---
class ReportResponse(BaseModel):
    report_url: str
    summary: str

# --- G. History (분석 이력) ---
class HistoryLogItem(BaseModel):
    id: str
    timestamp: str
    type: str
    status: str
    latency: str

class HistoryListResponse(BaseModel):
    items: List[HistoryLogItem]
    total: int


# --- H. Equipment Telemetry ---
class TelemetryIngestRequest(BaseModel):
    incident_id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    engine_rpm: Optional[int] = None
    coolant_temp: Optional[float] = None
    intake_air_temp: Optional[float] = None
    throttle_pos: Optional[float] = None
    fuel_trim: Optional[float] = None
    maf: Optional[float] = None
    failure: bool = False

    @model_validator(mode="after")
    def validate_sensor_payload(self):
        sensor_values = [
            self.engine_rpm,
            self.coolant_temp,
            self.intake_air_temp,
            self.throttle_pos,
            self.fuel_trim,
            self.maf,
        ]
        if all(v is None for v in sensor_values):
            raise ValueError("At least one sensor value is required")
        return self


class TelemetryIngestResponse(BaseModel):
    status: str
    recorded: bool
    ts_id: int
    device_id: str
    incident_id: int
    timestamp: datetime


# --- I. Integrated Diagnostic ---
class DiagnosticActionPlan(BaseModel):
    steps: List[str]
    risk_level: str
    escalation_required: bool


class DiagnosticPredictive(BaseModel):
    predicted_rul_minutes: float
    failure_probability: float
    anomaly_score: float
    model: Optional[str] = None


class DiagnosticReferenceDoc(BaseModel):
    doc_id: str
    content: str
    score: Optional[float] = None
    metadata: Dict[str, Any] = {}


class DiagnosticResponse(BaseModel):
    status: str
    incident_id: str
    equipment_id: str
    transcription: str
    vision_analysis: str
    predictive_ai: DiagnosticPredictive
    action_plan: DiagnosticActionPlan
    answer: str
    confidence: float
    reference_docs: List[DiagnosticReferenceDoc]
    pipeline_fallbacks: List[str]
    generated_at: datetime = Field(default_factory=datetime.utcnow)

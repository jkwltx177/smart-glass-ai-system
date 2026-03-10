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
    predictive_ai: Optional[Dict[str, Any]] = None

# --- D. Predictive ---
class PredictionRequest(BaseModel):
    incident_id: str

class PredictionResponse(BaseModel):
    prediction_id: int
    model_name: str
    failure_probability: float
    predicted_rul: float
    model_version: str

# --- E. AIOps ---
class MetricsResponse(BaseModel):
    timestamps: List[str]
    rmse_values: List[float]


class AIOpsOverviewResponse(BaseModel):
    generated_at: str
    incident_count: int
    completed_incident_count: int
    failed_incident_count: int
    prediction_count: int
    avg_incident_latency_seconds: float
    events_last_24h: int
    critical_events_last_24h: int
    fallback_events_last_24h: int
    latest_prediction: Dict[str, Any]


class AIOpsMetricsResponse(BaseModel):
    model: str
    timestamps: List[str]
    failure_probability_values: List[float]
    anomaly_score_values: List[float]
    predicted_rul_minutes_values: List[float]
    summary: Dict[str, Any]


class AIOpsAlertItem(BaseModel):
    type: str
    severity: str
    title: str
    service: Optional[str] = None
    stage: Optional[str] = None
    incident_id: Optional[int] = None
    device_id: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    created_at: Optional[str] = None


class AIOpsAlertsResponse(BaseModel):
    items: List[AIOpsAlertItem]
    total: int
    severity_summary: Dict[str, int]
    generated_at: str


class AIOpsDriftResponse(BaseModel):
    drift_detected: bool
    retrain_recommended: bool = False
    events: List[Dict[str, Any]]
    generated_at: str


class RetrainRequest(BaseModel):
    period_months: int = Field(default=3, ge=1, le=24)
    model_target: str = Field(default="prediction", min_length=3, max_length=100)
    trigger_reason: str = Field(default="manual", min_length=3, max_length=255)


class RetrainResponse(BaseModel):
    job_id: str
    status: str
    model_target: str
    period_months: int
    trigger_reason: str
    requested_by: Optional[str] = None
    created_at: Optional[str] = None


class RetrainJobItem(BaseModel):
    job_id: str
    model_target: str
    period_months: int
    trigger_reason: str
    requested_by: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    payload: Dict[str, Any] = {}


class RetrainJobsResponse(BaseModel):
    items: List[RetrainJobItem]
    total: int
    status_summary: Dict[str, int]
    generated_at: str


class ModelRegistryItem(BaseModel):
    name: str
    version: str
    prediction_count: int
    last_used_at: Optional[str] = None
    status: str


class ModelRegistryResponse(BaseModel):
    items: List[ModelRegistryItem]


class AIOpsReportResponse(BaseModel):
    report_url: str
    summary: str
    generated_at: str


class AIOpsDeploymentResponse(BaseModel):
    status: str
    current: Optional[Dict[str, Any]] = None
    previous: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = []
    rolled_back_from: Optional[Dict[str, Any]] = None

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
    report_url: Optional[str] = None
    html_report_url: Optional[str] = None

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

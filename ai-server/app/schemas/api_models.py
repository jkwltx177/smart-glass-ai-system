from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- A. Incidents ---
class IncidentCreate(BaseModel):
    site: str
    line: str
    device_type: str
    equipment_id: str

class IncidentResponse(BaseModel):
    incident_id: str
    status: str = "created"

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

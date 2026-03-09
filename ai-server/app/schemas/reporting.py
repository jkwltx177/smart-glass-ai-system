from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ReportHeader(BaseModel):
    report_id: str
    incident_id: str
    generated_at: datetime
    device_id: str
    lot_id: Optional[str] = None
    process_step: Optional[str] = None
    station_id: Optional[str] = None
    product_type: Optional[str] = None
    severity: str
    status: str


class IncidentSummary(BaseModel):
    issue_title: str
    user_intent: str
    symptom_summary: str
    business_impact: str
    recommended_priority: str


class PredictiveAISummary(BaseModel):
    predicted_rul_minutes: Optional[float] = None
    failure_probability: Optional[float] = None
    anomaly_score: Optional[float] = None


class EvidenceSummary(BaseModel):
    voice_transcript: Optional[str] = None
    objects_detected: List[str] = Field(default_factory=list)
    observations: List[str] = Field(default_factory=list)
    error_log_pattern: str
    timeseries_summary: Dict[str, Optional[str]] = Field(default_factory=dict)
    predictive_ai: PredictiveAISummary


class ImmediateContainmentAction(BaseModel):
    stop_or_continue_recommendation: str
    isolation_action: str
    reinspection_action: str
    escalation_condition: str


class RootCauseCorrectiveAction(BaseModel):
    problem_description: str
    suspected_root_cause: str
    interim_containment_action: str
    corrective_action: str
    preventive_action: str
    owner: str
    due_date: str
    verification_method: str


class PDCAMapping(BaseModel):
    plan: str
    do: str
    check: str
    act: str


class StatisticalSummary(BaseModel):
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    trend: str


class RuleBasedFlags(BaseModel):
    out_of_control: bool
    repeated_error_burst: bool
    abnormal_drift: bool


class SQCSummary(BaseModel):
    monitored_features: List[str]
    statistical_summary: StatisticalSummary
    rule_based_flags: RuleBasedFlags
    interpretation: List[str]


class AECQReference(BaseModel):
    applicable_component_type: str
    possible_related_stress_categories: List[str]
    aec_reference_note: str
    review_required: bool


class ReferenceDocument(BaseModel):
    doc_id: str
    title: str
    section: str
    snippet: str


class ReportFooter(BaseModel):
    disclaimer: str
    version: str
    model_info: str
    data_sources: List[str]


class QualityIncidentReport(BaseModel):
    report_title: str = "Quality Incident & Corrective Action Report"
    header: ReportHeader
    incident_summary: IncidentSummary
    evidence_summary: EvidenceSummary
    immediate_containment_action: ImmediateContainmentAction
    root_cause_corrective_action: RootCauseCorrectiveAction
    iso9001_pdca_mapping: PDCAMapping
    sqc_spc_summary: SQCSummary
    aec_q_reference: AECQReference
    reference_documents: List[ReferenceDocument]
    footer: ReportFooter


class QualityReportResponse(BaseModel):
    report_url: str
    html_report_url: Optional[str] = None
    summary: str
    report: QualityIncidentReport


class QualityReportSampleResponse(BaseModel):
    report: QualityIncidentReport
    generated_at: datetime = Field(default_factory=datetime.utcnow)

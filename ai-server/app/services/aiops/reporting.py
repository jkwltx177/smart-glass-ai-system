from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.core.config import settings
from .analytics import compute_aiops_alerts, compute_aiops_drift, compute_aiops_overview, list_retrain_jobs


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fit_text(text: str, *, limit: int = 120) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 3)] + "..."


def _drift_line(event: Dict[str, Any]) -> str:
    category = str(event.get("category", "unknown"))
    metric = str(event.get("metric", "-"))
    if category == "data_drift":
        delta = _safe_float(event.get("delta_ratio")) * 100.0
        return f"data_drift | {metric} | shift={delta:.1f}%"
    if category == "performance_drift":
        rmse = _safe_float(event.get("recent_rmse")) * 100.0
        threshold = _safe_float(event.get("threshold")) * 100.0
        return f"performance_drift | {metric} | rmse={rmse:.2f}% threshold={threshold:.2f}%"
    if category == "model_drift":
        recent = _safe_float(event.get("recent_failure_probability")) * 100.0
        baseline = _safe_float(event.get("baseline_failure_probability")) * 100.0
        return f"model_drift | {metric} | failure_prob {recent:.1f}% vs {baseline:.1f}%"
    if category == "service_drift":
        recent = int(_safe_float(event.get("recent_24h_count")))
        baseline = _safe_float(event.get("baseline_daily_count"))
        return f"service_drift | {metric} | fallback {recent} vs {baseline:.2f}"
    return f"{category} | {metric}"


def _add_section_title(pdf: FPDF, title: str) -> None:
    pdf.set_font("", "B", 12)
    pdf.cell(0, 8, txt=title, ln=1)
    pdf.set_font("", "", 10)


def _try_register_korean_font(pdf: FPDF) -> None:
    base = Path(__file__).resolve().parents[1] / "reporting"
    regular = base / "NanumGothic.ttf"
    bold = base / "NanumGothicBold.ttf"
    if not regular.exists() or not bold.exists():
        pdf.set_font("Helvetica", size=10)
        return
    pdf.add_font("NanumGothic", "", str(regular), uni=True)
    pdf.add_font("NanumGothic", "B", str(bold), uni=True)
    pdf.set_font("NanumGothic", size=10)


def generate_aiops_pdf_report(db: Session) -> Tuple[str, str]:
    overview = compute_aiops_overview(db)
    drift = compute_aiops_drift(db)
    alerts = compute_aiops_alerts(db, limit=20)
    jobs = list_retrain_jobs(db, limit=15)

    os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)
    generated_at = datetime.utcnow()
    file_name = f"aiops_operational_report_{generated_at.strftime('%Y%m%d%H%M%S')}.pdf"
    out_path = os.path.join(settings.REPORT_OUTPUT_DIR, file_name)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    _try_register_korean_font(pdf)

    pdf.set_font("", "B", 15)
    pdf.cell(0, 10, txt="AIOps Operational Report", ln=1)
    pdf.set_font("", "", 10)
    pdf.cell(0, 6, txt=f"Generated at (UTC): {generated_at.isoformat()}", ln=1)
    pdf.ln(2)

    _add_section_title(pdf, "1) Overview")
    pdf.multi_cell(
        0,
        6,
        txt=(
            f"- incidents: {int(overview.get('incident_count', 0))}\n"
            f"- predictions: {int(overview.get('prediction_count', 0))}\n"
            f"- events_last_24h: {int(overview.get('events_last_24h', 0))}\n"
            f"- critical_events_last_24h: {int(overview.get('critical_events_last_24h', 0))}\n"
            f"- avg_incident_latency_seconds: {_safe_float(overview.get('avg_incident_latency_seconds')):.2f}"
        ),
    )

    _add_section_title(pdf, "2) Drift Status")
    pdf.multi_cell(
        0,
        6,
        txt=(
            f"- drift_detected: {bool(drift.get('drift_detected'))}\n"
            f"- retrain_recommended: {bool(drift.get('retrain_recommended'))}\n"
            f"- drift_events: {len(drift.get('events', []) or [])}"
        ),
    )
    for idx, event in enumerate((drift.get("events") or [])[:8], start=1):
        if not isinstance(event, dict):
            continue
        pdf.multi_cell(0, 6, txt=f"  {idx}. {_fit_text(_drift_line(event), limit=140)}")

    _add_section_title(pdf, "3) Retrain Jobs (Latest)")
    items = jobs.get("items") if isinstance(jobs, dict) else []
    if not isinstance(items, list):
        items = []
    if not items:
        pdf.multi_cell(0, 6, txt="- no retrain jobs")
    else:
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            gate_passed = payload.get("gate_passed")
            gate_value = payload.get("gate_value")
            gate_threshold = payload.get("gate_threshold")
            line = (
                f"- {item.get('job_id')} | status={item.get('status')} | "
                f"trigger={item.get('trigger_reason')} | gate={gate_passed} | "
                f"rmse={gate_value} | threshold={gate_threshold}"
            )
            pdf.multi_cell(0, 6, txt=_fit_text(line, limit=180))
            reason = str(payload.get("reason") or payload.get("error") or "").strip()
            if reason:
                pdf.multi_cell(0, 6, txt=f"    reason: {_fit_text(reason, limit=170)}")

    _add_section_title(pdf, "4) Alert Summary")
    severity = alerts.get("severity_summary") if isinstance(alerts, dict) else {}
    if not isinstance(severity, dict):
        severity = {}
    high = int(severity.get("HIGH", 0)) + int(severity.get("CRITICAL", 0))
    medium = int(severity.get("MEDIUM", 0))
    low = int(severity.get("LOW", 0)) + int(severity.get("INFO", 0))
    pdf.multi_cell(
        0,
        6,
        txt=f"- HIGH: {high}\n- MEDIUM: {medium}\n- LOW: {low}",
    )

    pdf.output(out_path)
    summary = (
        f"drift_detected={bool(drift.get('drift_detected'))}, "
        f"events={len(drift.get('events', []) or [])}, "
        f"jobs={len(items)}"
    )
    return out_path, summary

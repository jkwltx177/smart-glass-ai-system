from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.schemas.api_models import ReportResponse
from app.schemas.reporting import QualityReportResponse, QualityReportSampleResponse
from app.core.config import settings
from app.core.database import get_db
from app.models.domain import Incident, Prediction, IncidentReport
from app.services.aiops import compute_aiops_overview
from app.services.reporting.report_generator import (
    generate_fallback_report_bundle,
    generate_quality_report_bundle,
    sample_quality_report,
)
import os

router = APIRouter()


def _persist_incident_report(
    db: Session,
    incident_id: int,
    report_url: str,
    html_report_url: str | None,
    summary: str,
) -> None:
    try:
        db.add(
            IncidentReport(
                incident_id=incident_id,
                report_type="quality",
                report_url=report_url,
                html_report_url=html_report_url,
                summary=summary,
                generated_at=datetime.utcnow(),
            )
        )
        db.commit()
    except Exception:
        db.rollback()

@router.post("/quality", response_model=QualityReportResponse)
async def generate_quality_report(incident_id: int, db: Session = Depends(get_db)):
    try:
        report, pdf_path, html_path = generate_quality_report_bundle(incident_id, db)
        report_url = f"/static/reports/{os.path.basename(pdf_path)}"
        html_report_url = f"/static/reports/{os.path.basename(html_path)}"
        summary = f"Incident {incident_id} quality report generated"
        _persist_incident_report(
            db=db,
            incident_id=incident_id,
            report_url=report_url,
            html_report_url=html_report_url,
            summary=summary,
        )
        return QualityReportResponse(
            report_url=report_url,
            html_report_url=html_report_url,
            summary=summary,
            report=report,
        )
    except Exception as e:
        # Safety net: even when rich report generation fails, always return a usable response.
        try:
            fallback_report, fallback_pdf_path, fallback_html_path = generate_fallback_report_bundle(
                incident_id=incident_id,
                reason=str(e),
            )
            fallback_report_url = f"/static/reports/{os.path.basename(fallback_pdf_path)}"
            fallback_html_url = f"/static/reports/{os.path.basename(fallback_html_path)}"
            fallback_summary = f"Incident {incident_id} fallback quality report generated (engineer review required)"
            _persist_incident_report(
                db=db,
                incident_id=incident_id,
                report_url=fallback_report_url,
                html_report_url=fallback_html_url,
                summary=fallback_summary,
            )
            return QualityReportResponse(
                report_url=fallback_report_url,
                html_report_url=fallback_html_url,
                summary=fallback_summary,
                report=fallback_report,
            )
        except Exception as fallback_error:
            sample = sample_quality_report()
            emergency_report = sample.model_copy(
                update={
                    "header": sample.header.model_copy(
                        update={
                            "incident_id": str(incident_id),
                            "status": "EMERGENCY_FALLBACK",
                            "generated_at": datetime.utcnow(),
                        }
                    ),
                    "incident_summary": sample.incident_summary.model_copy(
                        update={
                            "issue_title": f"Emergency fallback report for incident_id={incident_id}",
                            "symptom_summary": f"quality report generation failed: {str(e)} / fallback failed: {str(fallback_error)}",
                        }
                    ),
                }
            )
            os.makedirs(settings.REPORT_OUTPUT_DIR, exist_ok=True)
            stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            emergency_html_name = f"quality_incident_report_emergency_{incident_id}_{stamp}.html"
            emergency_html_path = os.path.join(settings.REPORT_OUTPUT_DIR, emergency_html_name)
            with open(emergency_html_path, "w", encoding="utf-8") as f:
                f.write(
                    "<!doctype html><html><head><meta charset='utf-8'><title>Emergency Fallback Report</title></head>"
                    "<body style='font-family:Arial;padding:20px'>"
                    "<h1>Emergency Fallback Report</h1>"
                    f"<p>incident_id={incident_id}</p>"
                    f"<p>report generation failed: {str(e)}</p>"
                    f"<p>fallback generation failed: {str(fallback_error)}</p>"
                    "<p>Engineer review required.</p>"
                    "</body></html>"
                )
            emergency_report_url = f"/static/reports/{emergency_html_name}"
            emergency_summary = "Emergency fallback report returned (engineer review required)"
            _persist_incident_report(
                db=db,
                incident_id=incident_id,
                report_url=emergency_report_url,
                html_report_url=emergency_report_url,
                summary=emergency_summary,
            )
            return QualityReportResponse(
                report_url=emergency_report_url,
                html_report_url=emergency_report_url,
                summary=emergency_summary,
                report=emergency_report,
            )


@router.get("/quality/sample", response_model=QualityReportSampleResponse)
async def get_quality_report_sample():
    return QualityReportSampleResponse(
        report=sample_quality_report(),
        generated_at=datetime.utcnow(),
    )

@router.post("/aiops", response_model=ReportResponse)
async def generate_aiops_report(db: Session = Depends(get_db)):
    overview = compute_aiops_overview(db)
    latest_incident = db.query(Incident).order_by(Incident.created_at.desc()).first()

    latest_id = int(latest_incident.incident_id) if latest_incident else 0

    return ReportResponse(
        report_url=f"/api/v1/report/quality?incident_id={latest_id}" if latest_id else "/api/v1/report/quality",
        summary=(
            f"incidents={overview['incident_count']}, completed={overview['completed_incident_count']}, "
            f"failed={overview['failed_incident_count']}, predictions={overview['prediction_count']}, "
            f"events_last_24h={overview['events_last_24h']}, "
            f"critical_events_last_24h={overview['critical_events_last_24h']}"
        ),
    )

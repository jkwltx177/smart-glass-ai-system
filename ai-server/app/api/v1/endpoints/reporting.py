from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.schemas.api_models import ReportResponse
from app.core.database import get_db
from app.models.domain import Incident, Prediction
from app.services.reporting.report_generator import generate_pdf_report
import os

router = APIRouter()

@router.post("/quality", response_model=ReportResponse)
async def generate_quality_report(incident_id: int, db: Session = Depends(get_db)):
    try:
        pdf_path = generate_pdf_report(incident_id, db)
        
        # 실제 환경에서는 S3 URL이나 정적 파일 서빙 URL로 변환해야 함
        # 여기서는 로컬 저장 경로를 반환
        return ReportResponse(
            report_url=f"/static/reports/{os.path.basename(pdf_path)}",
            summary=f"Incident {incident_id} 건에 대한 정밀 분석 보고서 생성 완료"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

@router.post("/aiops", response_model=ReportResponse)
async def generate_aiops_report(db: Session = Depends(get_db)):
    total_incidents = db.query(Incident).count()
    completed_incidents = db.query(Incident).filter(Incident.status == "COMPLETED").count()
    failed_incidents = db.query(Incident).filter(Incident.status == "FAILED").count()
    total_predictions = db.query(Prediction).count()
    avg_failure_probability = db.query(func.avg(Prediction.failure_probability)).scalar()
    latest_incident = db.query(Incident).order_by(Incident.created_at.desc()).first()

    latest_id = int(latest_incident.incident_id) if latest_incident else 0
    avg_failure = float(avg_failure_probability or 0.0)

    return ReportResponse(
        report_url=f"/api/v1/report/quality?incident_id={latest_id}" if latest_id else "/api/v1/report/quality",
        summary=(
            f"incidents={total_incidents}, completed={completed_incidents}, "
            f"failed={failed_incidents}, predictions={total_predictions}, "
            f"avg_failure_probability={avg_failure:.4f}"
        ),
    )

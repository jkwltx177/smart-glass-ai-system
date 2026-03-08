from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.api_models import ReportResponse
from app.core.database import get_db
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
async def generate_aiops_report():
    return ReportResponse(
        report_url="/reports/aiops/october_summary.pdf",
        summary="10월 모델 운영 및 성능 변화 요약"
    )

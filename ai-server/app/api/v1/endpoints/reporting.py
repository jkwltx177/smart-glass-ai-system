from fastapi import APIRouter
from app.schemas.api_models import ReportResponse

router = APIRouter()

@router.post("/quality", response_model=ReportResponse)
async def generate_quality_report(incident_id: str):
    return ReportResponse(
        report_url=f"/reports/quality/{incident_id}.pdf",
        summary="ECU 과열 건에 대한 정밀 분석 보고서"
    )

@router.post("/aiops", response_model=ReportResponse)
async def generate_aiops_report():
    return ReportResponse(
        report_url="/reports/aiops/october_summary.pdf",
        summary="10월 모델 운영 및 성능 변화 요약"
    )

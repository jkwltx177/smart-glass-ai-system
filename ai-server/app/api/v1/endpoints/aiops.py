from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.api_models import (
    AIOpsAlertsResponse,
    AIOpsDriftResponse,
    AIOpsMetricsResponse,
    AIOpsOverviewResponse,
    ModelRegistryResponse,
    RetrainRequest,
    RetrainResponse,
)
from app.services.aiops import (
    compute_aiops_alerts,
    compute_aiops_drift,
    compute_aiops_metrics,
    compute_aiops_overview,
    list_model_registry,
    queue_retrain_job,
)
from app.services.auth.token_verifier import verify_bearer_token


router = APIRouter()


@router.get("/overview", response_model=AIOpsOverviewResponse)
async def get_overview(db: Session = Depends(get_db)):
    return compute_aiops_overview(db)


@router.post("/retrain", response_model=RetrainResponse)
async def start_retraining(
    payload: RetrainRequest,
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    requested_by = str(token_payload.get("sub", "") or "")
    return queue_retrain_job(
        db,
        period_months=payload.period_months,
        model_target=payload.model_target,
        trigger_reason=payload.trigger_reason,
        requested_by=requested_by,
        payload={"requested_from": "api.v1.aiops.retrain"},
    )


@router.get("/models", response_model=ModelRegistryResponse)
async def list_models(db: Session = Depends(get_db)):
    return list_model_registry(db)


@router.get("/metrics", response_model=AIOpsMetricsResponse)
async def get_metrics(
    model_name: str = Query(default=""),
    db: Session = Depends(get_db),
):
    return compute_aiops_metrics(db, model_name=model_name or None)


@router.get("/drift", response_model=AIOpsDriftResponse)
async def check_drift(db: Session = Depends(get_db)):
    return compute_aiops_drift(db)


@router.get("/alerts", response_model=AIOpsAlertsResponse)
async def get_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return compute_aiops_alerts(db, limit=limit)

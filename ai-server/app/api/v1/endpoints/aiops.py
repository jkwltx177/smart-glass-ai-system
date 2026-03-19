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
    RetrainJobsResponse,
    RetrainRequest,
    RetrainResponse,
)
from app.services.aiops import (
    compute_aiops_alerts,
    compute_aiops_drift,
    compute_aiops_metrics,
    compute_aiops_overview,
    list_retrain_jobs,
    list_model_registry,
    queue_retrain_job,
    run_drift_cycle_once,
    run_retrain_cycle_once,
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


@router.get("/retrain/jobs", response_model=RetrainJobsResponse)
async def get_retrain_jobs(
    status: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    _ = token_payload
    normalized_status = status.strip().lower() or None
    return list_retrain_jobs(db, status=normalized_status, limit=limit)


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


@router.post("/runtime/retrain-cycle")
async def trigger_retrain_cycle(
    limit: int = Query(default=3, ge=1, le=10),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    _ = token_payload
    processed = run_retrain_cycle_once(limit=limit)
    return {"status": "ok", "processed_jobs": processed}


@router.post("/runtime/drift-cycle")
async def trigger_drift_cycle(
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    _ = token_payload
    detected = run_drift_cycle_once()
    return {"status": "ok", "drift_detected": detected}

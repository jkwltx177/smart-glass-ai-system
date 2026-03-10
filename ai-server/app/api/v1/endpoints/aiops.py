from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
import os
from datetime import datetime

from app.models.domain import AIOpsEvent
from app.schemas.api_models import (
    AIOpsAlertsResponse,
    AIOpsDriftResponse,
    AIOpsMetricsResponse,
    AIOpsOverviewResponse,
    AIOpsReportResponse,
    AIOpsDeploymentResponse,
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
from app.services.aiops.deployment import get_deployment_state, promote_retrain_job, rollback_deployment
from app.services.aiops.reporting import generate_aiops_pdf_report
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
    result = queue_retrain_job(
        db,
        period_months=payload.period_months,
        model_target=payload.model_target,
        trigger_reason=payload.trigger_reason,
        requested_by=requested_by,
        payload={"requested_from": "api.v1.aiops.retrain"},
    )
    try:
        run_retrain_cycle_once(limit=1)
    except Exception:
        pass
    return result


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


@router.get("/events/recent")
async def get_recent_events(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    _ = token_payload
    rows = (
        db.query(AIOpsEvent)
        .order_by(AIOpsEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "event_id": int(row.event_id),
                "event_type": row.event_type,
                "severity": row.severity,
                "service": row.service,
                "stage": row.stage,
                "incident_id": row.incident_id,
                "device_id": row.device_id,
                "model_name": row.model_name,
                "status": row.status,
                "message": row.message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total": len(rows),
        "generated_at": datetime.utcnow().isoformat(),
    }


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


@router.post("/report", response_model=AIOpsReportResponse)
async def generate_aiops_report(
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    _ = token_payload
    out_path, summary = generate_aiops_pdf_report(db)
    return {
        "report_url": f"/static/reports/{os.path.basename(out_path)}",
        "summary": summary,
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get("/deployment", response_model=AIOpsDeploymentResponse)
async def get_model_deployment(
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    _ = token_payload
    state = get_deployment_state()
    return {
        "status": "ok",
        "current": state.get("current"),
        "previous": state.get("previous"),
        "history": state.get("history") or [],
    }


@router.post("/deployment/promote", response_model=AIOpsDeploymentResponse)
async def promote_model_candidate(
    job_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    try:
        raw = str(job_id).strip()
        numeric = int(raw.split("_")[-1]) if "_" in raw else int(raw)
        result = promote_retrain_job(
            db,
            job_id=numeric,
            requested_by=str(token_payload.get("sub", "") or "unknown"),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="job_id must be numeric or retrain_job_<id>")
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state = get_deployment_state()
    return {
        "status": str(result.get("status", "ok")),
        "current": state.get("current"),
        "previous": state.get("previous"),
        "history": state.get("history") or [],
    }


@router.post("/deployment/rollback", response_model=AIOpsDeploymentResponse)
async def rollback_model_deployment(
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    try:
        result = rollback_deployment(db, requested_by=str(token_payload.get("sub", "") or "unknown"))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state = get_deployment_state()
    return {
        "status": str(result.get("status", "ok")),
        "current": state.get("current"),
        "previous": state.get("previous"),
        "history": state.get("history") or [],
        "rolled_back_from": result.get("rolled_back_from"),
    }

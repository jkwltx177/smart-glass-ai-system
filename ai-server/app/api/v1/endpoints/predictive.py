from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import Incident, Prediction
from app.schemas.api_models import PredictionRequest, PredictionResponse
from app.services.aiops import emit_aiops_event, run_drift_cycle_once
from app.services.prediction import (
    build_timeseries_features_payload,
    predict_from_timeseries_summary,
)

router = APIRouter()

@router.post("/", response_model=PredictionResponse)
async def perform_prediction(request: PredictionRequest, db: Session = Depends(get_db)):
    try:
        incident_id = int(request.incident_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="incident_id must be an integer")

    incident = db.query(Incident).filter(Incident.incident_id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    if not incident.device_id:
        raise HTTPException(status_code=400, detail="Incident has no device_id")

    telemetry = build_timeseries_features_payload(
        db=db,
        device_id=str(incident.device_id),
        limit_rows=720,
        window_size=120,
        stride=30,
    )
    pred = predict_from_timeseries_summary(telemetry)
    model_name = ",".join(pred.model_versions)
    model_version = str(getattr(pred, "model_source", model_name))
    row = Prediction(
        incident_id=incident_id,
        model_name=model_name[:100],
        model_version=model_version[:50],
        failure_probability=round(float(pred.failure_probability), 4),
        predicted_rul_minutes=int(round(float(pred.predicted_rul_minutes))),
        anomaly_score=round(float(pred.anomaly_score), 4),
        prediction_summary="Prediction persisted from /predict endpoint",
        predicted_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    emit_aiops_event(
        event_type="prediction_completed",
        severity="INFO",
        service="prediction",
        stage="inference",
        incident_id=incident_id,
        device_id=str(incident.device_id),
        model_name=model_name,
        status="ok",
        message="Prediction persisted from /predict endpoint",
        payload={
            "prediction_id": int(row.prediction_id),
            "failure_probability": round(float(pred.failure_probability), 4),
            "predicted_rul_minutes": round(float(pred.predicted_rul_minutes), 2),
            "anomaly_score": round(float(pred.anomaly_score), 4),
            "model_version": model_version,
        },
        db=db,
    )
    try:
        run_drift_cycle_once()
    except Exception:
        pass

    return PredictionResponse(
        prediction_id=int(row.prediction_id),
        model_name=model_name,
        failure_probability=pred.failure_probability,
        predicted_rul=pred.predicted_rul_minutes,
        model_version=model_version,
    )

@router.post("/feedback")
async def submit_feedback(incident_id: str, y_true: float):
    raise HTTPException(
        status_code=501,
        detail=(
            "feedback endpoint is not implemented in demo mode. "
            "Use /predict for inference only."
        ),
    )

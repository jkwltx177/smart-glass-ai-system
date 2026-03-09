from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import Incident
from app.schemas.api_models import PredictionRequest, PredictionResponse
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

    return PredictionResponse(
        failure_probability=pred.failure_probability,
        predicted_rul=pred.predicted_rul_minutes,
        model_version=",".join(pred.model_versions),
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

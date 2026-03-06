from fastapi import APIRouter
from app.schemas.api_models import PredictionRequest, PredictionResponse

router = APIRouter()

@router.post("/", response_model=PredictionResponse)
async def perform_prediction(request: PredictionRequest):
    # 시나리오에 따른 예측값 리턴 (Mock)
    return PredictionResponse(
        failure_probability=0.72,
        predicted_rul=180.0,
        model_version="v2.4.1-stable"
    )

@router.post("/feedback")
async def submit_feedback(incident_id: str, y_true: float):
    return {"status": "success", "updated_metrics": {"rmse": 4.2}}

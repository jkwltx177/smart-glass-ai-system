from fastapi import APIRouter, UploadFile, File, Form
from app.schemas.api_models import IncidentCreate, IncidentResponse
import uuid

router = APIRouter()

@router.post("/", response_model=IncidentResponse)
async def create_incident(data: IncidentCreate):
    # 사건 ID 생성 및 초기화 로직
    return IncidentResponse(incident_id=str(uuid.uuid4()))

@router.post("/{incident_id}/assets")
async def upload_asset(incident_id: str, file: UploadFile = File(...), type: str = Form(...)):
    return {"asset_id": str(uuid.uuid4()), "path": f"/assets/{incident_id}/{file.filename}"}

@router.post("/{incident_id}/telemetry")
async def upload_telemetry(incident_id: str, payload: dict):
    return {"status": "recorded", "incident_id": incident_id}

@router.get("/{incident_id}")
async def get_incident_detail(incident_id: str):
    return {
        "incident_id": incident_id,
        "site": "Test Site",
        "assets": ["img_01.jpg", "audio_01.wav"],
        "telemetry_summary": {"ecu_temp_avg": 78.5}
    }

@router.get("/")
async def list_incidents(site: str = None):
    return [{"incident_id": "1", "site": site or "Default"}]

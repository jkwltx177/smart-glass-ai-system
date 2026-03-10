from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import Device, Incident, SensorTimeseries
from app.schemas.api_models import TelemetryIngestRequest, TelemetryIngestResponse
from app.services.aiops import emit_aiops_event
from app.services.auth.token_verifier import verify_bearer_token


router = APIRouter()


class DeviceCreateRequest(BaseModel):
    device_id: str = Field(..., min_length=3, max_length=30)
    device_name: str = Field(..., min_length=2, max_length=100)
    vehicle_type: str = Field(default="Unknown", max_length=50)
    line_or_site: str = Field(default="Unknown Line", max_length=100)
    location: str = Field(default="Unknown Location", max_length=100)
    status: str = Field(default="ACTIVE", max_length=20)


def _ordered_devices_for_user(db: Session, username: str) -> List[Device]:
    devices = db.query(Device).order_by(Device.device_id.asc()).all()
    if not username:
        return devices

    recent_rows = (
        db.query(Incident.device_id)
        .filter(Incident.description.like(f"Triggered by user {username}%"))
        .order_by(Incident.created_at.desc())
        .limit(100)
        .all()
    )

    recent_order: List[str] = []
    for row in recent_rows:
        device_id = str(row[0]) if row and row[0] else ""
        if device_id and device_id not in recent_order:
            recent_order.append(device_id)

    rank = {device_id: idx for idx, device_id in enumerate(recent_order)}
    return sorted(
        devices,
        key=lambda item: (
            0 if item.device_id in rank else 1,
            rank.get(item.device_id, 99999),
            str(item.device_id),
        ),
    )


@router.get("/devices")
async def list_devices(
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    username = str(token_payload.get("sub", "") or "")
    ordered_devices = _ordered_devices_for_user(db, username=username)
    items = [
        {
            "device_id": d.device_id,
            "device_name": d.device_name,
            "vehicle_type": d.vehicle_type,
            "line_or_site": d.line_or_site,
            "location": d.location,
            "status": d.status,
        }
        for d in ordered_devices
    ]
    return {"items": items}


@router.post("/devices")
async def create_device(
    payload: DeviceCreateRequest,
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    exists = db.query(Device).filter(Device.device_id == payload.device_id).first()
    if exists:
        return {
            "created": False,
            "device": {
                "device_id": exists.device_id,
                "device_name": exists.device_name,
                "vehicle_type": exists.vehicle_type,
                "line_or_site": exists.line_or_site,
                "location": exists.location,
                "status": exists.status,
            },
            "message": "Device already exists",
        }

    device = Device(
        device_id=payload.device_id.strip(),
        device_name=payload.device_name.strip(),
        vehicle_type=payload.vehicle_type.strip() or "Unknown",
        line_or_site=payload.line_or_site.strip() or "Unknown Line",
        location=payload.location.strip() or "Unknown Location",
        status=payload.status.strip() or "ACTIVE",
        created_at=datetime.utcnow(),
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    return {
        "created": True,
        "device": {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "vehicle_type": device.vehicle_type,
            "line_or_site": device.line_or_site,
            "location": device.location,
            "status": device.status,
        },
        "message": f"Device created by {token_payload.get('sub', 'unknown')}",
    }


def _resolve_incident_id(db: Session, device_id: str, payload_incident_id: int | None) -> int:
    if payload_incident_id is not None:
        incident = db.query(Incident).filter(Incident.incident_id == payload_incident_id).first()
        if not incident:
            raise HTTPException(status_code=404, detail=f"Incident {payload_incident_id} not found")
        if incident.device_id != device_id:
            raise HTTPException(
                status_code=400,
                detail=f"Incident {payload_incident_id} does not belong to device {device_id}",
            )
        return int(incident.incident_id)

    latest_incident = (
        db.query(Incident)
        .filter(Incident.device_id == device_id)
        .order_by(Incident.created_at.desc())
        .first()
    )
    if not latest_incident:
        raise HTTPException(
            status_code=400,
            detail=f"No incident found for device {device_id}. Provide incident_id explicitly.",
        )
    return int(latest_incident.incident_id)


@router.post("/{device_id}/telemetry", response_model=TelemetryIngestResponse)
async def ingest_telemetry(
    device_id: str,
    payload: TelemetryIngestRequest,
    db: Session = Depends(get_db),
):
    """
    설비 장비의 실시간 센서 로그를 sensor_timeseries 테이블에 적재합니다.
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found",
        )

    incident_id = _resolve_incident_id(db, device_id, payload.incident_id)

    row = SensorTimeseries(
        incident_id=incident_id,
        device_id=device_id,
        timestamp=payload.timestamp or datetime.utcnow(),
        engine_rpm=payload.engine_rpm,
        coolant_temp=payload.coolant_temp,
        intake_air_temp=payload.intake_air_temp,
        throttle_pos=payload.throttle_pos,
        fuel_trim=payload.fuel_trim,
        maf=payload.maf,
        failure=payload.failure,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    observed_fields = [
        name for name in [
            "engine_rpm",
            "coolant_temp",
            "intake_air_temp",
            "throttle_pos",
            "fuel_trim",
            "maf",
        ]
        if getattr(payload, name) is not None
    ]
    emit_aiops_event(
        event_type="telemetry_recorded",
        severity="INFO",
        service="equipment",
        stage="ingest",
        incident_id=incident_id,
        device_id=device_id,
        status="recorded",
        message="Telemetry row stored",
        payload={
            "ts_id": int(row.ts_id),
            "observed_fields": observed_fields,
            "failure_flag": bool(payload.failure),
        },
        db=db,
    )
    if len(observed_fields) <= 2:
        emit_aiops_event(
            event_type="telemetry_quality_low",
            severity="MEDIUM",
            service="equipment",
            stage="ingest",
            incident_id=incident_id,
            device_id=device_id,
            status="degraded",
            message="Sparse telemetry payload detected",
            payload={"observed_fields": observed_fields},
            db=db,
        )

    return TelemetryIngestResponse(
        status="ok",
        recorded=True,
        ts_id=int(row.ts_id),
        device_id=device_id,
        incident_id=incident_id,
        timestamp=row.timestamp,
    )


@router.get("/{device_id}/telemetry")
async def list_telemetry(
    device_id: str,
    limit: int = Query(default=180, ge=30, le=600),
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    _ = token_payload
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found",
        )

    rows = (
        db.query(SensorTimeseries)
        .filter(SensorTimeseries.device_id == device_id)
        .order_by(SensorTimeseries.timestamp.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))

    def _num(value):
        return float(value) if value is not None else None

    items = [
        {
            "ts_id": int(row.ts_id),
            "timestamp": row.timestamp.isoformat(),
            "engine_rpm": int(row.engine_rpm) if row.engine_rpm is not None else None,
            "coolant_temp": _num(row.coolant_temp),
            "intake_air_temp": _num(row.intake_air_temp),
            "throttle_pos": _num(row.throttle_pos),
            "maf": _num(row.maf),
            "fuel_trim": _num(row.fuel_trim),
            "failure": bool(row.failure),
        }
        for row in rows
    ]

    return {
        "device_id": device_id,
        "count": len(items),
        "items": items,
        "source": "db.sensor_timeseries",
    }


@router.get("/{device_id}/telemetry/query")
async def list_telemetry_query(
    device_id: str,
    limit: int = Query(default=180, ge=30, le=600),
    db: Session = Depends(get_db),
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    # 일부 환경에서 /telemetry 경로가 POST 전용으로 라우팅되는 문제를 피하기 위한 조회 전용 별칭
    return await list_telemetry(
        device_id=device_id,
        limit=limit,
        db=db,
        token_payload=token_payload,
    )

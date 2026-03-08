from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import Device, Incident, IncidentAsset
from app.services.auth.token_verifier import verify_bearer_token
from app.services.pipeline.workflow import app_pipeline


router = APIRouter()

_SESSION_LOCK = threading.Lock()
_MOBILE_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _strip_markdown_asterisks(text: str) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("**", "")
        .replace("__", "")
        .replace("* ", "")
        .replace(" *", " ")
    )


def _new_session_code() -> str:
    return secrets.token_hex(3).upper()


def _cleanup_sessions() -> None:
    now = _utcnow()
    expired_codes = []
    for code, data in _MOBILE_SESSIONS.items():
        if data.get("expires_at") and data["expires_at"] < now:
            expired_codes.append(code)
    for code in expired_codes:
        _MOBILE_SESSIONS.pop(code, None)


class SessionConnectRequest(BaseModel):
    code: str
    device_label: Optional[str] = None


@router.post("/session/start")
async def start_mobile_session(
    ttl_minutes: int = 30,
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    ttl_minutes = max(5, min(ttl_minutes, 180))
    with _SESSION_LOCK:
        _cleanup_sessions()
        code = _new_session_code()
        while code in _MOBILE_SESSIONS:
            code = _new_session_code()

        now = _utcnow()
        _MOBILE_SESSIONS[code] = {
            "owner": str(token_payload.get("sub", "unknown")),
            "created_at": now,
            "expires_at": now + timedelta(minutes=ttl_minutes),
            "connected": False,
            "device_label": None,
            "user_agent": None,
            "last_seen": None,
            "last_result": None,
            "last_result_at": None,
        }

    return {
        "code": code,
        "expires_at": _MOBILE_SESSIONS[code]["expires_at"].isoformat(),
        "mobile_path": f"/?mobile=1&code={code}",
    }


@router.get("/session/{code}")
async def get_mobile_session_status(
    code: str,
    token_payload: Dict[str, Any] = Depends(verify_bearer_token),
):
    with _SESSION_LOCK:
        _cleanup_sessions()
        session = _MOBILE_SESSIONS.get(code.upper())
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or expired")

        if session.get("owner") != str(token_payload.get("sub", "unknown")):
            raise HTTPException(status_code=403, detail="Not allowed for this session")

        result = session.get("last_result")
        return {
            "code": code.upper(),
            "connected": bool(session.get("connected")),
            "device_label": session.get("device_label"),
            "user_agent": session.get("user_agent"),
            "last_seen": session.get("last_seen").isoformat() if session.get("last_seen") else None,
            "expires_at": session.get("expires_at").isoformat() if session.get("expires_at") else None,
            "result": result,
            "result_at": session.get("last_result_at").isoformat() if session.get("last_result_at") else None,
        }


@router.post("/session/connect")
async def connect_mobile_session(
    payload: SessionConnectRequest,
    user_agent: Optional[str] = Header(default=None),
):
    code = payload.code.strip().upper()
    with _SESSION_LOCK:
        _cleanup_sessions()
        session = _MOBILE_SESSIONS.get(code)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or expired")

        session["connected"] = True
        session["device_label"] = payload.device_label or "Mobile Device"
        session["user_agent"] = user_agent or "unknown"
        session["last_seen"] = _utcnow()

    return {"connected": True, "code": code}


@router.post("/session/{code}/submit")
async def submit_mobile_payload(
    code: str,
    equipment_id: str = Form(...),
    audio: UploadFile = File(...),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    code = code.upper()
    with _SESSION_LOCK:
        _cleanup_sessions()
        session = _MOBILE_SESSIONS.get(code)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or expired")
        session["connected"] = True
        session["last_seen"] = _utcnow()

    device = db.query(Device).filter(Device.device_id == equipment_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {equipment_id} not found")

    incident = Incident(
        device_id=equipment_id,
        site=(device.location or "Unknown Site"),
        line=(device.line_or_site or "Unknown Line"),
        device_type=(device.vehicle_type or "Unknown"),
        title=f"Mobile Capture ({device.device_name or equipment_id})",
        description="모바일 전송 기반 RAG 요청",
        status="PROCESSING",
        severity="INFO",
        started_at=_utcnow(),
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    audio_bytes = await audio.read()
    db.add(
        IncidentAsset(
            incident_id=int(incident.incident_id),
            asset_type="audio",
            file_name=audio.filename or "audio.webm",
            file_path=f"/tmp/{code}_{audio.filename or 'audio.webm'}",
            mime_type=audio.content_type,
            file_size=len(audio_bytes),
        )
    )

    image_bytes = None
    if image is not None:
        image_bytes = await image.read()
        db.add(
            IncidentAsset(
                incident_id=int(incident.incident_id),
                asset_type="image",
                file_name=image.filename or "image.jpg",
                file_path=f"/tmp/{code}_{image.filename or 'image.jpg'}",
                mime_type=image.content_type,
                file_size=len(image_bytes),
            )
        )

    db.commit()

    initial_state = {
        "incident_id": str(incident.incident_id),
        "equipment_id": equipment_id,
        "audio_content": audio_bytes,
        "image_content": image_bytes,
        "assets": [
            {"type": "audio", "filename": audio.filename or "audio.webm"},
            {"type": "image", "filename": image.filename or "image.jpg"},
        ],
    }

    try:
        result = app_pipeline.invoke(initial_state)
        final_plan_data = result.get("final_action_plan", {}) or {}
        clean_explanation = _strip_markdown_asterisks(result.get("explanation", "결과 분석 중입니다."))
        clean_steps = [
            _strip_markdown_asterisks(step)
            for step in final_plan_data.get("steps", ["기본 점검 수행"])
        ]

        incident.description = (
            "[분석 결과]\n"
            f"{clean_explanation}\n\n"
            "[조치 절차]\n"
            + "\n".join(f"- {step}" for step in clean_steps)
        )
        incident.status = "COMPLETED"
        incident.ended_at = _utcnow()
        incident.updated_at = _utcnow()
        db.commit()

        summary = {
            "incident_id": str(incident.incident_id),
            "equipment_id": equipment_id,
            "explanation": clean_explanation,
            "steps": clean_steps,
        }
    except Exception as e:
        incident.status = "FAILED"
        incident.description = f"모바일 파이프라인 오류: {str(e)}"
        incident.ended_at = _utcnow()
        db.commit()
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

    with _SESSION_LOCK:
        session = _MOBILE_SESSIONS.get(code)
        if session:
            session["last_result"] = summary
            session["last_result_at"] = _utcnow()
            session["last_seen"] = _utcnow()

    return {
        "status": "ok",
        "code": code,
        "incident_id": str(incident.incident_id),
        "message": "Submitted and processed",
    }

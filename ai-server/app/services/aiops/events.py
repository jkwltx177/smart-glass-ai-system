import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.domain import AIOpsEvent


def _to_json(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return "{}"
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def emit_aiops_event(
    *,
    event_type: str,
    severity: str = "INFO",
    service: str,
    stage: Optional[str] = None,
    incident_id: Optional[int] = None,
    device_id: Optional[str] = None,
    model_name: Optional[str] = None,
    status: Optional[str] = None,
    message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> None:
    own_session = db is None
    session = db or SessionLocal()
    try:
        session.add(
            AIOpsEvent(
                event_type=event_type[:50],
                severity=(severity or "INFO")[:20],
                service=service[:50],
                stage=(stage or "")[:50] or None,
                incident_id=incident_id,
                device_id=(device_id or "")[:30] or None,
                model_name=(model_name or "")[:100] or None,
                status=(status or "")[:30] or None,
                message=(message or "")[:255] or None,
                payload_json=_to_json(payload),
            )
        )
        session.commit()
    except Exception:
        if own_session:
            session.rollback()
    finally:
        if own_session:
            session.close()

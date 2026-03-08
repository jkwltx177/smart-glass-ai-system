"""분석 이력(History) API"""

from datetime import datetime
from typing import Dict, List, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import Incident, IncidentAsset
from app.schemas.api_models import HistoryLogItem, HistoryListResponse

router = APIRouter()


def _format_ts(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _calc_latency(incident: Incident) -> str:
    start = incident.started_at or incident.created_at
    end = incident.ended_at or incident.updated_at or incident.created_at
    if not start or not end:
        return "-"
    sec = max(0.0, float((end - start).total_seconds()))
    return f"{sec:.1f}s"


def _resolve_type(asset_types: Set[str]) -> str:
    has_audio = "audio" in asset_types
    has_image = "image" in asset_types
    if has_audio and has_image:
        return "Multimodal"
    if has_audio:
        return "Audio Only"
    if has_image:
        return "Image Only"
    return "System"


@router.get("/", response_model=HistoryListResponse)
async def get_analysis_history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    incidents = (
        db.query(Incident)
        .order_by(Incident.created_at.desc())
        .limit(limit)
        .all()
    )

    incident_ids = [int(item.incident_id) for item in incidents]
    asset_map: Dict[int, Set[str]] = {iid: set() for iid in incident_ids}
    if incident_ids:
        assets = (
            db.query(IncidentAsset.incident_id, IncidentAsset.asset_type)
            .filter(IncidentAsset.incident_id.in_(incident_ids))
            .all()
        )
        for incident_id, asset_type in assets:
            if incident_id is None or not asset_type:
                continue
            asset_map.setdefault(int(incident_id), set()).add(str(asset_type))

    items: List[HistoryLogItem] = []
    for incident in incidents:
        iid = int(incident.incident_id)
        status = str(incident.status or "UNKNOWN")
        if status.upper() == "COMPLETED":
            status = "Success"
        elif status.upper() == "FAILED":
            status = "Failed"

        items.append(
            HistoryLogItem(
                id=f"INC-{iid}",
                timestamp=_format_ts(incident.created_at or incident.started_at),
                type=_resolve_type(asset_map.get(iid, set())),
                status=status,
                latency=_calc_latency(incident),
            )
        )

    return HistoryListResponse(
        items=items,
        total=len(items),
    )

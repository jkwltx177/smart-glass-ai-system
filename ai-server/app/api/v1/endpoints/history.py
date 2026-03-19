"""분석 이력(History) API"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import Incident, IncidentAsset, IncidentReport
from app.schemas.api_models import HistoryLogItem, HistoryListResponse

router = APIRouter()
_REPORTS_DIR = Path("storage/reports")


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


def _load_legacy_reports(db: Session, incident_ids: List[int]) -> Dict[int, Dict[str, Optional[str]]]:
    if not incident_ids:
        return {}
    try:
        placeholders = ",".join([str(int(iid)) for iid in incident_ids])
        rows = db.execute(
            text(
                "SELECT incident_id, report_url, created_at "
                f"FROM reports WHERE incident_id IN ({placeholders}) "
                "ORDER BY created_at DESC"
            )
        ).mappings().all()
    except Exception:
        return {}

    out: Dict[int, Dict[str, Optional[str]]] = {}
    for row in rows:
        try:
            iid = int(row.get("incident_id"))
        except Exception:
            continue
        if iid in out:
            continue
        raw_report_url = row.get("report_url")
        report_url: Optional[str] = None
        if raw_report_url:
            candidate = str(raw_report_url)
            # Legacy demo URL -> static URL normalize
            if candidate.startswith("/demo/reports/"):
                file_name = Path(candidate).name
                static_candidate = f"/static/reports/{file_name}"
                if (_REPORTS_DIR / file_name).exists():
                    candidate = static_candidate
            # Only expose links that are likely accessible.
            if candidate.startswith("/static/reports/") or candidate.startswith("http://") or candidate.startswith("https://"):
                report_url = candidate
        out[iid] = {
            "report_url": report_url,
            "html_report_url": None,
        }
    return out


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

    report_map: Dict[int, IncidentReport] = {}
    if incident_ids:
        reports = (
            db.query(IncidentReport)
            .filter(IncidentReport.incident_id.in_(incident_ids))
            .order_by(IncidentReport.generated_at.desc())
            .all()
        )
        for report in reports:
            report_incident_id = int(report.incident_id)
            if report_incident_id not in report_map:
                report_map[report_incident_id] = report

    legacy_report_map = _load_legacy_reports(db, incident_ids)

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
                report_url=(
                    report_map[iid].report_url
                    if iid in report_map
                    else legacy_report_map.get(iid, {}).get("report_url")
                ),
                html_report_url=(
                    report_map[iid].html_report_url
                    if iid in report_map
                    else legacy_report_map.get(iid, {}).get("html_report_url")
                ),
            )
        )

    return HistoryListResponse(
        items=items,
        total=len(items),
    )

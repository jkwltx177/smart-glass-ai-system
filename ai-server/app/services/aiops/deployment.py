from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.domain import RetrainJob
from app.services.prediction import reload_predictor
from .events import emit_aiops_event


MODEL_FILES = [
    "lgbm_failure.txt",
    "lgbm_rul.txt",
    "sklearn_failure.joblib",
    "sklearn_rul.joblib",
    "xgb_failure.json",
    "xgb_rul.json",
    "tcn_failure.pt",
    "tcn_rul.pt",
    "model_meta.json",
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _artifact_root() -> Path:
    base = Path(os.getenv("AIOPS_RETRAIN_ARTIFACT_DIR", "storage/retrain-artifacts"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _state_path() -> Path:
    return _artifact_root() / "deployment_state.json"


def _model_dir() -> Path:
    configured = Path(os.getenv("PREDICTION_MODEL_DIR", "models/weights"))
    if configured.is_absolute():
        out = configured
    else:
        out = Path(__file__).resolve().parents[3] / configured
    out.mkdir(parents=True, exist_ok=True)
    return out


def _read_state() -> Dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return {"current": None, "previous": None, "history": [], "updated_at": datetime.utcnow().isoformat()}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("invalid_state")
        data.setdefault("current", None)
        data.setdefault("previous", None)
        data.setdefault("history", [])
        data.setdefault("updated_at", datetime.utcnow().isoformat())
        return data
    except Exception:
        return {"current": None, "previous": None, "history": [], "updated_at": datetime.utcnow().isoformat()}


def _write_state(data: Dict[str, Any]) -> None:
    data["updated_at"] = datetime.utcnow().isoformat()
    _state_path().write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _backup_current_model() -> Dict[str, Any]:
    model_dir = _model_dir()
    backup_dir = _artifact_root() / "deploy-backups" / datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, str] = {}
    for name in MODEL_FILES:
        src = model_dir / name
        if not src.exists():
            continue
        dst = backup_dir / name
        _copy_file(src, dst)
        files[name] = str(dst)
    return {
        "backup_dir": str(backup_dir),
        "files": files,
        "created_at": datetime.utcnow().isoformat(),
    }


def _restore_backup(snapshot: Dict[str, Any]) -> None:
    files = snapshot.get("files") if isinstance(snapshot, dict) else {}
    if not isinstance(files, dict) or not files:
        raise RuntimeError("rollback_snapshot_missing")
    model_dir = _model_dir()
    restored = 0
    for name, source_path in files.items():
        src = Path(str(source_path))
        if not src.exists():
            continue
        _copy_file(src, model_dir / name)
        restored += 1
    if restored == 0:
        raise RuntimeError("rollback_source_not_found")
    reload_predictor(model_dir=str(model_dir))


def get_deployment_state() -> Dict[str, Any]:
    return _read_state()


def promote_retrain_job(db: Session, *, job_id: int, requested_by: str) -> Dict[str, Any]:
    job = db.query(RetrainJob).filter(RetrainJob.job_id == int(job_id)).first()
    if not job:
        raise RuntimeError("retrain_job_not_found")
    if str(job.status).lower() != "completed":
        raise RuntimeError("retrain_job_not_completed")

    payload: Dict[str, Any] = {}
    try:
        payload = json.loads(job.payload_json or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    gate_passed = payload.get("gate_passed")
    if gate_passed is False:
        raise RuntimeError("rmse_gate_not_passed")

    artifacts = payload.get("model_artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError("candidate_artifacts_missing")

    state = _read_state()
    backup = _backup_current_model()
    previous = state.get("current")

    model_dir = _model_dir()
    copied = 0
    for _, path_value in artifacts.items():
        src = Path(str(path_value))
        if not src.exists():
            continue
        dst = model_dir / src.name
        _copy_file(src, dst)
        copied += 1
    if copied == 0:
        raise RuntimeError("candidate_artifacts_not_found")

    model_version = str(payload.get("model_version") or f"candidate-job-{job.job_id}")
    current = {
        "job_id": f"retrain_job_{int(job.job_id)}",
        "model_target": job.model_target,
        "model_version": model_version,
        "trigger_reason": job.trigger_reason,
        "deployed_by": requested_by or "unknown",
        "deployed_at": datetime.utcnow().isoformat(),
        "gate_passed": gate_passed,
        "gate_value": _safe_float(payload.get("gate_value")),
        "gate_threshold": _safe_float(payload.get("gate_threshold")),
        "rollback_snapshot": backup,
    }
    state["previous"] = previous
    state["current"] = current
    history = state.get("history") if isinstance(state.get("history"), list) else []
    history.insert(0, current)
    state["history"] = history[:30]
    _write_state(state)

    payload["deployment_status"] = "deployed"
    payload["deployed_at"] = current["deployed_at"]
    payload["deployed_by"] = current["deployed_by"]
    job.payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    db.commit()
    reload_predictor(model_dir=str(model_dir))

    emit_aiops_event(
        event_type="model_deployed",
        severity="INFO",
        service="aiops",
        stage="deploy",
        model_name=job.model_target,
        status="deployed",
        message="Retrained model promoted to production",
        payload={
            "job_id": current["job_id"],
            "model_version": current["model_version"],
            "deployed_by": current["deployed_by"],
        },
        db=db,
    )
    return {"status": "ok", "current": current}


def rollback_deployment(db: Session, *, requested_by: str) -> Dict[str, Any]:
    state = _read_state()
    current = state.get("current")
    if not isinstance(current, dict):
        raise RuntimeError("no_current_deployment")
    snapshot = current.get("rollback_snapshot")
    if not isinstance(snapshot, dict):
        raise RuntimeError("rollback_snapshot_missing")

    _restore_backup(snapshot)
    previous = state.get("previous")
    rolled_back_to = previous if isinstance(previous, dict) else None

    state["current"] = rolled_back_to
    state["previous"] = None
    history = state.get("history") if isinstance(state.get("history"), list) else []
    history.insert(
        0,
        {
            "event": "rollback",
            "requested_by": requested_by or "unknown",
            "rolled_back_from": current.get("model_version"),
            "rolled_back_at": datetime.utcnow().isoformat(),
        },
    )
    state["history"] = history[:30]
    _write_state(state)

    emit_aiops_event(
        event_type="model_rolled_back",
        severity="HIGH",
        service="aiops",
        stage="deploy",
        model_name="prediction",
        status="rolled_back",
        message="Model rollback completed",
        payload={
            "requested_by": requested_by or "unknown",
            "rolled_back_from": current.get("model_version"),
            "rolled_back_to": (rolled_back_to or {}).get("model_version"),
        },
        db=db,
    )
    return {"status": "ok", "current": state.get("current"), "rolled_back_from": current}

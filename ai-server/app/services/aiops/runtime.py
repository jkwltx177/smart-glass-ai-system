import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.core.database import SessionLocal
from app.models.domain import Prediction, RetrainJob, SensorTimeseries
from app.services.prediction.preprocessing import SENSOR_FIELDS
from .analytics import compute_aiops_drift, compute_aiops_overview
from .events import emit_aiops_event


_RUNTIME_STOP = threading.Event()
_RUNTIME_THREADS: list[threading.Thread] = []
_LAST_DRIFT_SIGNATURE: str = ""
_LAST_DRIFT_EMITTED_AT: Optional[datetime] = None
_LAST_HEARTBEAT_AT: Optional[datetime] = None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_payload(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_artifact(payload: Dict[str, Any], model_target: str, job_id: int) -> str:
    base_dir = Path(os.getenv("AIOPS_RETRAIN_ARTIFACT_DIR", "storage/retrain-artifacts"))
    base_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{model_target}_job_{job_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
    out_path = base_dir / file_name
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    return str(out_path)


def _build_retrain_snapshot(job: RetrainJob) -> Dict[str, Any]:
    horizon = datetime.utcnow() - timedelta(days=max(1, int(job.period_months or 1)) * 30)
    with SessionLocal() as db:
        sensor_rows = (
            db.query(SensorTimeseries)
            .filter(SensorTimeseries.timestamp >= horizon)
            .order_by(SensorTimeseries.timestamp.desc())
            .limit(5000)
            .all()
        )
        prediction_rows = (
            db.query(Prediction)
            .filter(Prediction.predicted_at >= horizon)
            .order_by(Prediction.predicted_at.desc())
            .limit(1000)
            .all()
        )

        sensor_means: Dict[str, float] = {}
        for field in SENSOR_FIELDS:
            values = [_safe_float(getattr(row, field, None)) for row in sensor_rows if getattr(row, field, None) is not None]
            sensor_means[field] = round(sum(values) / len(values), 4) if values else 0.0

        failure_vals = [_safe_float(row.failure_probability) for row in prediction_rows]
        anomaly_vals = [_safe_float(row.anomaly_score) for row in prediction_rows]
        rul_vals = [_safe_float(row.predicted_rul_minutes) for row in prediction_rows]

    return {
        "job_id": int(job.job_id),
        "model_target": job.model_target,
        "period_months": int(job.period_months or 1),
        "window_start": horizon.isoformat(),
        "window_end": datetime.utcnow().isoformat(),
        "dataset": {
            "sensor_row_count": len(sensor_rows),
            "prediction_row_count": len(prediction_rows),
        },
        "feature_profile": {
            "sensor_means": sensor_means,
            "avg_failure_probability": round(sum(failure_vals) / len(failure_vals), 4) if failure_vals else 0.0,
            "avg_anomaly_score": round(sum(anomaly_vals) / len(anomaly_vals), 4) if anomaly_vals else 0.0,
            "avg_predicted_rul_minutes": round(sum(rul_vals) / len(rul_vals), 4) if rul_vals else 0.0,
        },
        "trainer": "aiops.runtime.snapshot-trainer",
    }


def _mark_job_running(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.query(RetrainJob).filter(RetrainJob.job_id == job_id).first()
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()
        emit_aiops_event(
            event_type="retrain_started",
            severity="INFO",
            service="aiops",
            stage="retrain",
            model_name=job.model_target,
            status=job.status,
            message="Retrain job started",
            payload={"job_id": int(job.job_id), "period_months": int(job.period_months or 1)},
            db=db,
        )


def _mark_job_done(job_id: int, *, status: str, payload_patch: Dict[str, Any], message: str, severity: str) -> None:
    with SessionLocal() as db:
        job = db.query(RetrainJob).filter(RetrainJob.job_id == job_id).first()
        if not job:
            return
        existing = _parse_payload(job.payload_json)
        existing.update(payload_patch)
        job.status = status
        job.completed_at = datetime.utcnow()
        job.payload_json = json.dumps(existing, ensure_ascii=False, default=str)
        db.commit()
        emit_aiops_event(
            event_type="retrain_completed" if status == "completed" else "retrain_failed",
            severity=severity,
            service="aiops",
            stage="retrain",
            model_name=job.model_target,
            status=job.status,
            message=message,
            payload={"job_id": int(job.job_id), **payload_patch},
            db=db,
        )


def _process_one_retrain_job(job_id: int) -> Tuple[bool, str]:
    _mark_job_running(job_id)
    with SessionLocal() as db:
        job = db.query(RetrainJob).filter(RetrainJob.job_id == job_id).first()
        if not job:
            return False, "job_not_found"
        model_target = job.model_target

    try:
        with SessionLocal() as db:
            job = db.query(RetrainJob).filter(RetrainJob.job_id == job_id).first()
            if not job:
                return False, "job_not_found"
            snapshot = _build_retrain_snapshot(job)
        if snapshot["dataset"]["sensor_row_count"] < 120:
            _mark_job_done(
                job_id,
                status="failed",
                payload_patch={"reason": "insufficient_sensor_data", "min_required_rows": 120},
                message="Retrain aborted: insufficient sensor rows",
                severity="MEDIUM",
            )
            return False, "insufficient_sensor_data"

        artifact_path = _write_artifact(snapshot, model_target=model_target, job_id=job_id)
        _mark_job_done(
            job_id,
            status="completed",
            payload_patch={
                "artifact_path": artifact_path,
                "sensor_row_count": snapshot["dataset"]["sensor_row_count"],
                "prediction_row_count": snapshot["dataset"]["prediction_row_count"],
            },
            message="Retrain job completed (snapshot artifact generated)",
            severity="INFO",
        )
        return True, "completed"
    except Exception as exc:
        _mark_job_done(
            job_id,
            status="failed",
            payload_patch={"error": str(exc)},
            message="Retrain job failed",
            severity="HIGH",
        )
        return False, str(exc)


def run_retrain_cycle_once(*, limit: int = 3) -> int:
    with SessionLocal() as db:
        rows = (
            db.query(RetrainJob.job_id)
            .filter(RetrainJob.status == "queued")
            .order_by(RetrainJob.created_at.asc())
            .limit(max(1, min(int(limit), 10)))
            .all()
        )
    processed = 0
    for row in rows:
        job_id = int(row[0])
        _process_one_retrain_job(job_id)
        processed += 1
    return processed


def run_drift_cycle_once() -> bool:
    global _LAST_DRIFT_SIGNATURE, _LAST_DRIFT_EMITTED_AT, _LAST_HEARTBEAT_AT

    now = datetime.utcnow()
    with SessionLocal() as db:
        drift = compute_aiops_drift(db)
        overview = compute_aiops_overview(db)

        if drift.get("drift_detected"):
            events = drift.get("events", [])
            signature = json.dumps(events[:5], ensure_ascii=False, sort_keys=True, default=str)
            should_emit = signature != _LAST_DRIFT_SIGNATURE
            if _LAST_DRIFT_EMITTED_AT and (now - _LAST_DRIFT_EMITTED_AT) < timedelta(minutes=15):
                should_emit = False if signature == _LAST_DRIFT_SIGNATURE else should_emit
            if should_emit:
                emit_aiops_event(
                    event_type="drift_detected",
                    severity="HIGH",
                    service="aiops",
                    stage="monitor",
                    status="alert",
                    message="AIOps drift detected",
                    payload={"events": events[:10], "event_count": len(events)},
                    db=db,
                )
                _LAST_DRIFT_SIGNATURE = signature
                _LAST_DRIFT_EMITTED_AT = now

        if _LAST_HEARTBEAT_AT is None or (now - _LAST_HEARTBEAT_AT) >= timedelta(minutes=10):
            emit_aiops_event(
                event_type="aiops_heartbeat",
                severity="INFO",
                service="aiops",
                stage="monitor",
                status="ok",
                message="AIOps runtime heartbeat",
                payload={
                    "incident_count": overview.get("incident_count", 0),
                    "prediction_count": overview.get("prediction_count", 0),
                    "events_last_24h": overview.get("events_last_24h", 0),
                },
                db=db,
            )
            _LAST_HEARTBEAT_AT = now

    return bool(drift.get("drift_detected"))


def _retrain_worker_loop() -> None:
    interval = max(3, int(os.getenv("AIOPS_RETRAIN_POLL_SECONDS", "15")))
    while not _RUNTIME_STOP.is_set():
        try:
            run_retrain_cycle_once(limit=3)
        except Exception:
            pass
        _RUNTIME_STOP.wait(interval)


def _monitor_worker_loop() -> None:
    interval = max(10, int(os.getenv("AIOPS_MONITOR_INTERVAL_SECONDS", "60")))
    while not _RUNTIME_STOP.is_set():
        try:
            run_drift_cycle_once()
        except Exception:
            pass
        _RUNTIME_STOP.wait(interval)


def start_aiops_runtime() -> None:
    if _RUNTIME_THREADS:
        return
    _RUNTIME_STOP.clear()
    retrain_thread = threading.Thread(target=_retrain_worker_loop, name="aiops-retrain-worker", daemon=True)
    monitor_thread = threading.Thread(target=_monitor_worker_loop, name="aiops-monitor-worker", daemon=True)
    _RUNTIME_THREADS.extend([retrain_thread, monitor_thread])
    for thread in _RUNTIME_THREADS:
        thread.start()
    try:
        emit_aiops_event(
            event_type="aiops_runtime_started",
            severity="INFO",
            service="aiops",
            stage="runtime",
            status="ok",
            message="AIOps background workers started",
            payload={"workers": [thread.name for thread in _RUNTIME_THREADS]},
        )
    except Exception:
        pass


def stop_aiops_runtime() -> None:
    _RUNTIME_STOP.set()
    for thread in list(_RUNTIME_THREADS):
        thread.join(timeout=2.0)
    _RUNTIME_THREADS.clear()
    try:
        emit_aiops_event(
            event_type="aiops_runtime_stopped",
            severity="INFO",
            service="aiops",
            stage="runtime",
            status="stopped",
            message="AIOps background workers stopped",
            payload={},
        )
    except Exception:
        pass

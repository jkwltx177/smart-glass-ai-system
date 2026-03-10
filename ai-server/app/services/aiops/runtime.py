import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.core.database import SessionLocal
from app.models.domain import Prediction, RetrainJob, SensorTimeseries
from app.services.prediction import train_prediction_models
from app.services.prediction.preprocessing import SENSOR_FIELDS
from .analytics import compute_aiops_drift, compute_aiops_overview, queue_retrain_job
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_rmse_gate_error(message: str) -> Dict[str, float]:
    text = str(message or "")
    match = re.search(r"rmse_threshold_exceeded:([0-9.]+)>([0-9.]+)", text)
    if not match:
        return {}
    return {
        "valid_rmse_failure": _safe_float(match.group(1)),
        "rmse_threshold": _safe_float(match.group(2)),
    }


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


def _candidate_model_dir(job_id: int) -> Path:
    base_dir = Path(os.getenv("AIOPS_RETRAIN_ARTIFACT_DIR", "storage/retrain-artifacts"))
    candidate_dir = base_dir / "candidates" / f"job_{int(job_id)}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    return candidate_dir


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
            if model_target.strip().lower() != "prediction":
                _mark_job_done(
                    job_id,
                    status="failed",
                    payload_patch={"reason": "unsupported_model_target", "model_target": model_target},
                    message="Retrain aborted: unsupported model target",
                    severity="MEDIUM",
                )
                return False, "unsupported_model_target"

            model_dir = _candidate_model_dir(job_id)
            result = train_prediction_models(
                db,
                period_months=int(job.period_months or 3),
                model_dir=model_dir,
                preferred_algorithm=os.getenv("PREDICTION_TRAIN_ALGORITHM", "lightgbm"),
                allow_fallback=os.getenv("PREDICTION_TRAIN_ALLOW_FALLBACK", "0").strip().lower() in {"1", "true", "yes"},
            )
            snapshot = {
                "job_id": int(job.job_id),
                "model_target": result.model_target,
                "trained_at": result.trained_at,
                "sample_count": result.sample_count,
                "positive_ratio": result.positive_ratio,
                "metrics": result.metrics,
                "artifact_paths": result.artifact_paths,
                "model_version": result.model_version,
            }

        artifact_path = _write_artifact(snapshot, model_target=model_target, job_id=job_id)
        _mark_job_done(
            job_id,
            status="completed",
            payload_patch={
                "artifact_path": artifact_path,
                "model_artifacts": snapshot.get("artifact_paths", {}),
                "model_version": snapshot.get("model_version"),
                "deployment_status": "ready",
                "sample_count": _safe_int(snapshot.get("sample_count"), 0),
                "positive_ratio": round(_safe_float(snapshot.get("positive_ratio")), 6),
                "metrics": snapshot.get("metrics", {}),
                "gate_passed": True,
                "gate_metric": "failure_probability_rmse",
                "gate_threshold": _safe_float(snapshot.get("metrics", {}).get("rmse_threshold")),
                "gate_value": _safe_float(snapshot.get("metrics", {}).get("valid_rmse_failure")),
            },
            message="Retrain job completed (candidate ready for deploy)",
            severity="INFO",
        )
        return True, "completed"
    except Exception as exc:
        gate_metrics = _parse_rmse_gate_error(str(exc))
        is_gate_failed = bool(gate_metrics)
        payload_patch = {"error": str(exc)}
        if is_gate_failed:
            payload_patch.update(
                {
                    "reason": "rmse_gate_not_passed",
                    "gate_passed": False,
                    "gate_metric": "failure_probability_rmse",
                    "gate_threshold": gate_metrics.get("rmse_threshold", 0.0),
                    "gate_value": gate_metrics.get("valid_rmse_failure", 0.0),
                }
            )
        _mark_job_done(
            job_id,
            status="failed",
            payload_patch=payload_patch,
            message="Retrain job failed: RMSE gate not passed" if is_gate_failed else "Retrain job failed",
            severity="MEDIUM" if is_gate_failed else "HIGH",
        )
        return False, str(exc)


def _should_auto_queue_retrain(db, *, now: datetime) -> bool:
    active_job = (
        db.query(RetrainJob.job_id)
        .filter(RetrainJob.model_target == "prediction")
        .filter(RetrainJob.status.in_(["queued", "running"]))
        .first()
    )
    if active_job:
        return False

    cooldown_minutes = max(10, _safe_int(os.getenv("AIOPS_AUTO_RETRAIN_COOLDOWN_MINUTES", "360"), 360))
    recent_auto_job = (
        db.query(RetrainJob.job_id)
        .filter(RetrainJob.model_target == "prediction")
        .filter(RetrainJob.trigger_reason == "auto_drift")
        .filter(RetrainJob.created_at >= now - timedelta(minutes=cooldown_minutes))
        .order_by(RetrainJob.created_at.desc())
        .first()
    )
    return recent_auto_job is None


def _auto_queue_retrain_if_needed(db, *, drift: Dict[str, Any], now: datetime) -> Optional[Dict[str, Any]]:
    if not drift.get("drift_detected") or not drift.get("retrain_recommended"):
        return None

    categories = {str(event.get("category", "")).strip().lower() for event in drift.get("events", [])}
    auto_categories = {"data_drift", "performance_drift", "service_drift", "model_drift"}
    if not (categories & auto_categories):
        return None
    if not _should_auto_queue_retrain(db, now=now):
        return None

    period_months = max(1, _safe_int(os.getenv("AIOPS_AUTO_RETRAIN_PERIOD_MONTHS", "3"), 3))
    queued = queue_retrain_job(
        db,
        period_months=period_months,
        model_target="prediction",
        trigger_reason="auto_drift",
        requested_by="aiops-runtime",
        payload={
            "requested_from": "aiops.runtime.auto-trigger",
            "detected_categories": sorted(categories),
            "drift_events": drift.get("events", [])[:10],
        },
    )
    emit_aiops_event(
        event_type="auto_retrain_queued",
        severity="HIGH",
        service="aiops",
        stage="retrain",
        model_name="prediction",
        status="queued",
        message="Automatic retrain queued from drift detection",
        payload={
            "job_id": queued.get("job_id"),
            "period_months": period_months,
            "detected_categories": sorted(categories),
        },
        db=db,
    )
    return queued


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
            _auto_queue_retrain_if_needed(db, drift=drift, now=now)

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

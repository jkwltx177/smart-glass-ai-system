import json
import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.domain import AIOpsEvent, Incident, Prediction, RetrainJob, SensorTimeseries
from app.services.prediction.preprocessing import SENSOR_FIELDS
from .events import emit_aiops_event


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_payload(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _calc_incident_latency_seconds(incident: Incident) -> float:
    start = incident.started_at or incident.created_at
    end = incident.ended_at or incident.updated_at or incident.created_at
    if not start or not end:
        return 0.0
    return max(0.0, float((end - start).total_seconds()))


def _avg(values: List[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _recent_events(db: Session, *, hours: int = 24, limit: int = 200) -> List[AIOpsEvent]:
    since = datetime.utcnow() - timedelta(hours=hours)
    return (
        db.query(AIOpsEvent)
        .filter(AIOpsEvent.created_at >= since)
        .order_by(AIOpsEvent.created_at.desc())
        .limit(limit)
        .all()
    )


def compute_aiops_overview(db: Session) -> Dict[str, Any]:
    incidents = db.query(Incident).all()
    predictions = db.query(Prediction).all()
    events_24h = _recent_events(db, hours=24, limit=500)
    critical_events = [e for e in events_24h if str(e.severity).upper() in {"HIGH", "CRITICAL"}]
    fallback_events = [e for e in events_24h if e.event_type in {"pipeline_fallback", "prediction_fallback", "rag_fallback"}]
    latencies = [_calc_incident_latency_seconds(incident) for incident in incidents]
    latest_prediction = (
        db.query(Prediction)
        .order_by(Prediction.predicted_at.desc())
        .first()
    )

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "incident_count": len(incidents),
        "completed_incident_count": sum(1 for item in incidents if str(item.status).upper() == "COMPLETED"),
        "failed_incident_count": sum(1 for item in incidents if str(item.status).upper() == "FAILED"),
        "prediction_count": len(predictions),
        "avg_incident_latency_seconds": _avg(latencies),
        "events_last_24h": len(events_24h),
        "critical_events_last_24h": len(critical_events),
        "fallback_events_last_24h": len(fallback_events),
        "latest_prediction": {
            "model_name": getattr(latest_prediction, "model_name", None),
            "model_version": getattr(latest_prediction, "model_version", None),
            "failure_probability": _safe_float(getattr(latest_prediction, "failure_probability", None)),
            "predicted_rul_minutes": _safe_float(getattr(latest_prediction, "predicted_rul_minutes", None)),
            "anomaly_score": _safe_float(getattr(latest_prediction, "anomaly_score", None)),
        },
    }


def compute_aiops_metrics(db: Session, model_name: Optional[str] = None) -> Dict[str, Any]:
    query = db.query(Prediction)
    if model_name:
        query = query.filter(Prediction.model_name.like(f"%{model_name}%"))
    rows = query.order_by(Prediction.predicted_at.asc()).limit(300).all()

    timestamps = [row.predicted_at.isoformat() for row in rows if row.predicted_at]
    failure_values = [_safe_float(row.failure_probability) for row in rows]
    anomaly_values = [_safe_float(row.anomaly_score) for row in rows]
    rul_values = [_safe_float(row.predicted_rul_minutes) for row in rows]

    recent_events = _recent_events(db, hours=24, limit=500)
    pipeline_events = [e for e in recent_events if e.event_type in {"pipeline_completed", "pipeline_failed"}]
    latency_ms = []
    fallback_count = 0
    for event in pipeline_events:
        payload = _parse_payload(event.payload_json)
        latency_ms.append(_safe_float(payload.get("latency_ms"), 0.0))
        fallback_count += int(_safe_float(payload.get("fallback_count"), 0.0))

    return {
        "model": model_name or "all",
        "timestamps": timestamps,
        "failure_probability_values": failure_values,
        "anomaly_score_values": anomaly_values,
        "predicted_rul_minutes_values": rul_values,
        "summary": {
            "prediction_count": len(rows),
            "avg_failure_probability": _avg(failure_values),
            "avg_anomaly_score": _avg(anomaly_values),
            "avg_predicted_rul_minutes": _avg(rul_values),
            "avg_pipeline_latency_ms_last_24h": _avg(latency_ms),
            "fallback_count_last_24h": fallback_count,
        },
    }


def _sensor_mean(rows: List[SensorTimeseries], field: str) -> float:
    values = [_safe_float(getattr(row, field), math.nan) for row in rows]
    values = [value for value in values if not math.isnan(value)]
    return sum(values) / len(values) if values else 0.0


def compute_aiops_drift(db: Session) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    drift_detected = False

    recent_rows = (
        db.query(SensorTimeseries)
        .order_by(SensorTimeseries.timestamp.desc())
        .limit(120)
        .all()
    )
    baseline_rows = (
        db.query(SensorTimeseries)
        .order_by(SensorTimeseries.timestamp.desc())
        .offset(120)
        .limit(480)
        .all()
    )

    if recent_rows and baseline_rows:
        for field in SENSOR_FIELDS:
            recent_mean = _sensor_mean(recent_rows, field)
            baseline_mean = _sensor_mean(baseline_rows, field)
            delta_ratio = abs(recent_mean - baseline_mean) / max(abs(baseline_mean), 1.0)
            if delta_ratio >= 0.25:
                drift_detected = True
                events.append(
                    {
                        "category": "data_drift",
                        "metric": field,
                        "recent_mean": round(recent_mean, 4),
                        "baseline_mean": round(baseline_mean, 4),
                        "delta_ratio": round(delta_ratio, 4),
                        "severity": "HIGH" if delta_ratio >= 0.5 else "MEDIUM",
                    }
                )

    recent_predictions = (
        db.query(Prediction)
        .order_by(Prediction.predicted_at.desc())
        .limit(50)
        .all()
    )
    baseline_predictions = (
        db.query(Prediction)
        .order_by(Prediction.predicted_at.desc())
        .offset(50)
        .limit(150)
        .all()
    )
    if recent_predictions and baseline_predictions:
        recent_failure = _avg([_safe_float(row.failure_probability) for row in recent_predictions])
        baseline_failure = _avg([_safe_float(row.failure_probability) for row in baseline_predictions])
        recent_anomaly = _avg([_safe_float(row.anomaly_score) for row in recent_predictions])
        baseline_anomaly = _avg([_safe_float(row.anomaly_score) for row in baseline_predictions])

        failure_shift = abs(recent_failure - baseline_failure)
        anomaly_shift = abs(recent_anomaly - baseline_anomaly)
        if failure_shift >= 0.15 or anomaly_shift >= 0.15:
            drift_detected = True
            events.append(
                {
                    "category": "model_drift",
                    "metric": "prediction_distribution",
                    "recent_failure_probability": recent_failure,
                    "baseline_failure_probability": baseline_failure,
                    "recent_anomaly_score": recent_anomaly,
                    "baseline_anomaly_score": baseline_anomaly,
                    "severity": "HIGH" if max(failure_shift, anomaly_shift) >= 0.25 else "MEDIUM",
                }
            )

    recent_fallbacks = (
        db.query(AIOpsEvent)
        .filter(AIOpsEvent.event_type.in_(["pipeline_fallback", "prediction_fallback", "rag_fallback"]))
        .filter(AIOpsEvent.created_at >= datetime.utcnow() - timedelta(hours=24))
        .count()
    )
    older_fallbacks = (
        db.query(AIOpsEvent)
        .filter(AIOpsEvent.event_type.in_(["pipeline_fallback", "prediction_fallback", "rag_fallback"]))
        .filter(AIOpsEvent.created_at >= datetime.utcnow() - timedelta(days=7))
        .filter(AIOpsEvent.created_at < datetime.utcnow() - timedelta(hours=24))
        .count()
    )
    baseline_daily_fallbacks = older_fallbacks / 6.0 if older_fallbacks else 0.0
    if recent_fallbacks >= max(3.0, baseline_daily_fallbacks * 2.0):
        drift_detected = True
        events.append(
            {
                "category": "service_drift",
                "metric": "fallback_rate",
                "recent_24h_count": recent_fallbacks,
                "baseline_daily_count": round(baseline_daily_fallbacks, 2),
                "severity": "HIGH" if recent_fallbacks >= 6 else "MEDIUM",
            }
        )

    return {
        "drift_detected": drift_detected,
        "events": events,
        "generated_at": datetime.utcnow().isoformat(),
    }


def compute_aiops_alerts(db: Session, limit: int = 20) -> Dict[str, Any]:
    recent_events = _recent_events(db, hours=72, limit=limit * 5)
    recent_predictions = (
        db.query(Prediction)
        .order_by(Prediction.predicted_at.desc())
        .limit(limit)
        .all()
    )
    alerts: List[Dict[str, Any]] = []

    for event in recent_events:
        if str(event.severity).upper() not in {"MEDIUM", "HIGH", "CRITICAL"}:
            continue
        alerts.append(
            {
                "type": "event",
                "severity": event.severity,
                "title": event.event_type,
                "service": event.service,
                "stage": event.stage,
                "incident_id": event.incident_id,
                "device_id": event.device_id,
                "status": event.status,
                "message": event.message,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
        )
        if len(alerts) >= limit:
            break

    risky_incident_ids = {alert.get("incident_id") for alert in alerts if alert.get("incident_id")}
    for prediction in recent_predictions:
        probability = _safe_float(prediction.failure_probability)
        anomaly = _safe_float(prediction.anomaly_score)
        rul = _safe_float(prediction.predicted_rul_minutes)
        if probability < 0.8 and anomaly < 0.75 and rul > 60:
            continue
        if int(prediction.incident_id) in risky_incident_ids:
            continue
        severity = "HIGH" if probability >= 0.9 or rul <= 30 else "MEDIUM"
        alerts.append(
            {
                "type": "prediction",
                "severity": severity,
                "title": "high_risk_prediction",
                "service": "prediction",
                "stage": "inference",
                "incident_id": int(prediction.incident_id),
                "device_id": None,
                "status": "open",
                "message": (
                    f"failure_probability={probability:.3f}, "
                    f"anomaly_score={anomaly:.3f}, predicted_rul_minutes={rul:.1f}"
                ),
                "created_at": prediction.predicted_at.isoformat() if prediction.predicted_at else None,
            }
        )
        if len(alerts) >= limit:
            break

    severity_counter = Counter(str(item["severity"]).upper() for item in alerts)
    return {
        "items": alerts[:limit],
        "total": len(alerts[:limit]),
        "severity_summary": dict(severity_counter),
        "generated_at": datetime.utcnow().isoformat(),
    }


def list_model_registry(db: Session) -> Dict[str, Any]:
    rows = (
        db.query(
            Prediction.model_name,
            Prediction.model_version,
            func.count(Prediction.prediction_id),
            func.max(Prediction.predicted_at),
        )
        .group_by(Prediction.model_name, Prediction.model_version)
        .order_by(func.max(Prediction.predicted_at).desc())
        .all()
    )
    items = [
        {
            "name": row[0],
            "version": row[1],
            "prediction_count": int(row[2] or 0),
            "last_used_at": row[3].isoformat() if row[3] else None,
            "status": "active",
        }
        for row in rows
    ]
    if not items:
        items.append(
            {
                "name": "fallback-default",
                "version": "heuristic",
                "prediction_count": 0,
                "last_used_at": None,
                "status": "inactive",
            }
        )
    return {"items": items}


def queue_retrain_job(
    db: Session,
    *,
    period_months: int,
    model_target: str,
    trigger_reason: str,
    requested_by: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    job = RetrainJob(
        model_target=model_target[:100],
        period_months=max(1, min(int(period_months), 24)),
        trigger_reason=trigger_reason[:255],
        requested_by=(requested_by or "")[:100] or None,
        status="queued",
        payload_json=json.dumps(payload or {}, ensure_ascii=False, default=str),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    emit_aiops_event(
        event_type="retrain_requested",
        severity="MEDIUM",
        service="aiops",
        stage="retrain",
        model_name=job.model_target,
        status=job.status,
        message="Retrain job queued",
        payload={
            "job_id": int(job.job_id),
            "period_months": job.period_months,
            "trigger_reason": job.trigger_reason,
            "requested_by": job.requested_by,
        },
        db=db,
    )
    return {
        "job_id": f"retrain_job_{int(job.job_id)}",
        "status": job.status,
        "model_target": job.model_target,
        "period_months": job.period_months,
        "trigger_reason": job.trigger_reason,
        "requested_by": job.requested_by,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def list_retrain_jobs(
    db: Session,
    *,
    status: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    query = db.query(RetrainJob)
    if status:
        query = query.filter(RetrainJob.status == status.lower())

    rows = query.order_by(RetrainJob.created_at.desc()).limit(max(1, min(int(limit), 200))).all()
    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "job_id": f"retrain_job_{int(row.job_id)}",
                "model_target": row.model_target,
                "period_months": int(row.period_months or 0),
                "trigger_reason": row.trigger_reason,
                "requested_by": row.requested_by,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "payload": _parse_payload(row.payload_json),
            }
        )

    summary_rows = db.query(RetrainJob.status, func.count(RetrainJob.job_id)).group_by(RetrainJob.status).all()
    summary = {str(row[0] or "unknown"): int(row[1] or 0) for row in summary_rows}
    return {
        "items": items,
        "total": len(items),
        "status_summary": summary,
        "generated_at": datetime.utcnow().isoformat(),
    }

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _request_json(
    method: str,
    url: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    body = None
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = Request(url=url, data=body, method=method.upper(), headers=req_headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}\n{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error {method} {url}: {exc}") from exc


def _auth_headers(token_type: str, token: str) -> Dict[str, str]:
    return {"Authorization": f"{token_type} {token}"}


def _login(auth_base: str, username: str, password: str) -> tuple[str, str]:
    data = _request_json(
        "POST",
        f"{auth_base.rstrip('/')}/login",
        payload={"username": username, "password": password},
    )
    token = str(data.get("accessToken") or "").strip()
    token_type = str(data.get("tokenType") or "Bearer").strip() or "Bearer"
    if not token:
        raise RuntimeError("Login failed: accessToken missing")
    return token_type, token


def _ensure_device(api_base: str, headers: Dict[str, str], device_id: str) -> None:
    payload = {
        "device_id": device_id,
        "device_name": f"Demo Device {device_id}",
        "vehicle_type": "DemoVehicle",
        "line_or_site": "DemoLine",
        "location": "DemoZone",
        "status": "ACTIVE",
    }
    _request_json("POST", f"{api_base.rstrip('/')}/equipment/devices", payload=payload, headers=headers)


def _create_incident(
    api_base: str,
    *,
    site: str,
    line: str,
    device_type: str,
    equipment_id: str,
    description: str,
) -> int:
    payload = {
        "site": site,
        "line": line,
        "device_type": device_type,
        "equipment_id": equipment_id,
        "description": description,
    }
    data = _request_json("POST", f"{api_base.rstrip('/')}/incidents/", payload=payload)
    incident_id = int(data.get("incident_id"))
    return incident_id


def _ingest_telemetry(
    api_base: str,
    *,
    device_id: str,
    incident_id: int,
    timestamp: datetime,
    engine_rpm: int,
    coolant_temp: float,
    intake_air_temp: float,
    throttle_pos: float,
    fuel_trim: float,
    maf: float,
    failure: bool,
) -> None:
    payload = {
        "incident_id": incident_id,
        "timestamp": timestamp.isoformat(),
        "engine_rpm": engine_rpm,
        "coolant_temp": round(coolant_temp, 2),
        "intake_air_temp": round(intake_air_temp, 2),
        "throttle_pos": round(throttle_pos, 2),
        "fuel_trim": round(fuel_trim, 2),
        "maf": round(maf, 2),
        "failure": bool(failure),
    }
    _request_json(
        "POST",
        f"{api_base.rstrip('/')}/equipment/{device_id}/telemetry",
        payload=payload,
    )


def _predict(api_base: str, incident_id: int) -> Dict[str, Any]:
    return _request_json(
        "POST",
        f"{api_base.rstrip('/')}/predict/",
        payload={"incident_id": str(incident_id)},
    )


def _run_drift_cycle(api_base: str, headers: Dict[str, str]) -> bool:
    data = _request_json(
        "POST",
        f"{api_base.rstrip('/')}/aiops/runtime/drift-cycle",
        headers=headers,
    )
    return bool(data.get("drift_detected"))


def _run_retrain_cycle(api_base: str, headers: Dict[str, str], limit: int = 1) -> int:
    data = _request_json(
        "POST",
        f"{api_base.rstrip('/')}/aiops/runtime/retrain-cycle?limit={int(limit)}",
        headers=headers,
    )
    return int(data.get("processed_jobs") or 0)


def _get_drift(api_base: str) -> Dict[str, Any]:
    return _request_json("GET", f"{api_base.rstrip('/')}/aiops/drift")


def _get_retrain_jobs(api_base: str, headers: Dict[str, str], limit: int = 30) -> Dict[str, Any]:
    return _request_json("GET", f"{api_base.rstrip('/')}/aiops/retrain/jobs?limit={limit}", headers=headers)


def _find_latest_auto_job(jobs_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items = jobs_payload.get("items") if isinstance(jobs_payload, dict) else []
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("trigger_reason") or "").strip().lower() == "auto_drift":
            return item
    return None


def _simulate_telemetry_and_predictions(
    api_base: str,
    *,
    device_id: str,
    incident_id: int,
    baseline_count: int,
    drift_count: int,
    predict_every: int,
) -> None:
    total = baseline_count + drift_count
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=total + 20)

    for i in range(baseline_count):
        t = start + timedelta(seconds=i)
        _ingest_telemetry(
            api_base,
            device_id=device_id,
            incident_id=incident_id,
            timestamp=t,
            engine_rpm=1500 + (i % 80),
            coolant_temp=87.0 + ((i % 5) * 0.2),
            intake_air_temp=36.0 + ((i % 4) * 0.3),
            throttle_pos=29.0 + ((i % 6) * 0.4),
            fuel_trim=2.4 + ((i % 3) * 0.15),
            maf=21.5 + ((i % 5) * 0.25),
            failure=False,
        )
        if (i + 1) % max(1, predict_every) == 0:
            _predict(api_base, incident_id)

    for j in range(drift_count):
        idx = baseline_count + j
        t = start + timedelta(seconds=idx)
        failure_flag = (j % 7 == 0)
        _ingest_telemetry(
            api_base,
            device_id=device_id,
            incident_id=incident_id,
            timestamp=t,
            engine_rpm=2800 + (j % 220),
            coolant_temp=113.0 + ((j % 5) * 0.9),
            intake_air_temp=62.0 + ((j % 4) * 1.0),
            throttle_pos=66.0 + ((j % 6) * 1.1),
            fuel_trim=11.0 + ((j % 3) * 0.8),
            maf=45.0 + ((j % 5) * 1.4),
            failure=failure_flag,
        )
        if (j + 1) % max(1, predict_every // 2 or 1) == 0:
            _predict(api_base, incident_id)


def _print_summary(drift: Dict[str, Any], jobs: Dict[str, Any]) -> None:
    print("\n=== Drift Summary ===")
    print(f"drift_detected      : {bool(drift.get('drift_detected'))}")
    print(f"retrain_recommended : {bool(drift.get('retrain_recommended'))}")
    events = drift.get("events") if isinstance(drift.get("events"), list) else []
    cats = sorted({str(e.get("category", "unknown")) for e in events if isinstance(e, dict)})
    print(f"categories          : {', '.join(cats) if cats else '-'}")
    print(f"event_count         : {len(events)}")

    auto_job = _find_latest_auto_job(jobs)
    print("\n=== Retrain Queue Summary ===")
    if not auto_job:
        print("latest_auto_job     : not found")
        return

    payload = auto_job.get("payload") if isinstance(auto_job.get("payload"), dict) else {}
    print(f"job_id              : {auto_job.get('job_id')}")
    print(f"status              : {auto_job.get('status')}")
    print(f"trigger_reason      : {auto_job.get('trigger_reason')}")
    print(f"created_at          : {auto_job.get('created_at')}")
    print(f"gate_passed         : {payload.get('gate_passed')}")
    print(f"gate_metric         : {payload.get('gate_metric')}")
    print(f"gate_value          : {payload.get('gate_value')}")
    print(f"gate_threshold      : {payload.get('gate_threshold')}")
    reason = payload.get("reason") or payload.get("error")
    if reason:
        print(f"gate_reason         : {reason}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIOps 데모 자동화: 드리프트 유도 -> auto retrain 큐 -> RMSE 게이트 결과 확인"
    )
    parser.add_argument("--auth-base", default="http://localhost:8081/auth")
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--device-id", default="DEMO-AIOPS-01")
    parser.add_argument("--site", default="Plant Demo")
    parser.add_argument("--line", default="Line Demo")
    parser.add_argument("--device-type", default="Engine")
    parser.add_argument("--baseline-count", type=int, default=360)
    parser.add_argument("--drift-count", type=int, default=140)
    parser.add_argument("--predict-every", type=int, default=20)
    parser.add_argument("--run-retrain-cycle", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--poll-max", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        print("[1/7] Login...")
        token_type, access_token = _login(args.auth_base, args.username, args.password)
        headers = _auth_headers(token_type, access_token)

        print("[2/7] Ensure demo device...")
        _ensure_device(args.api_base, headers, args.device_id)

        print("[3/7] Create incident...")
        incident_id = _create_incident(
            args.api_base,
            site=args.site,
            line=args.line,
            device_type=args.device_type,
            equipment_id=args.device_id,
            description=f"AIOps demo run @ {datetime.utcnow().isoformat()}",
        )
        print(f"      incident_id={incident_id}")

        print("[4/7] Inject baseline + drift telemetry and predictions...")
        _simulate_telemetry_and_predictions(
            args.api_base,
            device_id=args.device_id,
            incident_id=incident_id,
            baseline_count=max(130, int(args.baseline_count)),
            drift_count=max(60, int(args.drift_count)),
            predict_every=max(5, int(args.predict_every)),
        )

        print("[5/7] Trigger drift cycle (auto queue expected)...")
        detected = _run_drift_cycle(args.api_base, headers)
        print(f"      drift_detected={detected}")

        print("[6/7] Fetch drift + retrain jobs...")
        drift = _get_drift(args.api_base)
        jobs = _get_retrain_jobs(args.api_base, headers)
        _print_summary(drift, jobs)

        if args.run_retrain_cycle:
            print("[7/7] Run retrain cycle and poll latest auto job...")
            processed = _run_retrain_cycle(args.api_base, headers, limit=1)
            print(f"      processed_jobs={processed}")
            for _ in range(max(1, int(args.poll_max))):
                jobs = _get_retrain_jobs(args.api_base, headers)
                latest = _find_latest_auto_job(jobs)
                status = str((latest or {}).get("status") or "").lower()
                if status and status not in {"queued", "running"}:
                    break
                time.sleep(max(0.2, float(args.poll_seconds)))
            _print_summary(_get_drift(args.api_base), jobs)

        print("\nDemo flow finished.")
        return 0
    except Exception as exc:
        print(f"\nDemo flow failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

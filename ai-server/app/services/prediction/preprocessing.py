from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Sequence

import numpy as np
from sqlalchemy.orm import Session

from app.models.domain import SensorTimeseries


SENSOR_FIELDS = [
    "engine_rpm",
    "coolant_temp",
    "intake_air_temp",
    "throttle_pos",
    "fuel_trim",
    "maf",
]
STAT_FIELDS = ["mean", "std", "min", "max", "slope", "latest"]  # 6 * 6 = 36
CORR_PAIRS = [  # +6 => 42
    ("engine_rpm", "coolant_temp"),
    ("engine_rpm", "throttle_pos"),
    ("engine_rpm", "maf"),
    ("coolant_temp", "fuel_trim"),
    ("throttle_pos", "fuel_trim"),
    ("maf", "fuel_trim"),
]
EXTRA_FIELDS = [  # +4 => total 46
    "failure_ratio",
    "window_seconds",
    "valid_ratio",
    "rpm_to_throttle_mean_ratio",
]

FEATURE_NAMES = (
    [f"{sensor}_{stat}" for sensor in SENSOR_FIELDS for stat in STAT_FIELDS]
    + [f"corr_{a}_{b}" for a, b in CORR_PAIRS]
    + EXTRA_FIELDS
)
FEATURE_COUNT = len(FEATURE_NAMES)
assert FEATURE_COUNT == 46


def _safe_float(value) -> float:
    if value is None:
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _calc_slope(arr: np.ndarray) -> float:
    valid = np.where(~np.isnan(arr))[0]
    if valid.size < 2:
        return 0.0
    x = valid.astype(np.float64)
    y = arr[valid].astype(np.float64)
    x_mean = float(x.mean())
    y_mean = float(y.mean())
    numerator = float(np.sum((x - x_mean) * (y - y_mean)))
    denominator = float(np.sum((x - x_mean) ** 2))
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def _calc_corr(arr_a: np.ndarray, arr_b: np.ndarray) -> float:
    mask = ~np.isnan(arr_a) & ~np.isnan(arr_b)
    if int(mask.sum()) < 2:
        return 0.0
    a = arr_a[mask]
    b = arr_b[mask]
    std_a = float(np.std(a))
    std_b = float(np.std(b))
    if std_a == 0.0 or std_b == 0.0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _rows_to_arrays(window_rows: Sequence[SensorTimeseries]) -> Dict[str, np.ndarray]:
    data: Dict[str, np.ndarray] = {}
    for sensor in SENSOR_FIELDS:
        values = [_safe_float(getattr(row, sensor)) for row in window_rows]
        data[sensor] = np.array(values, dtype=np.float64)
    failures = [_safe_float(getattr(row, "failure")) for row in window_rows]
    data["failure"] = np.array(failures, dtype=np.float64)
    return data


def extract_feature_map(window_rows: Sequence[SensorTimeseries]) -> Dict[str, float]:
    arrays = _rows_to_arrays(window_rows)
    feature_map: Dict[str, float] = {}

    for sensor in SENSOR_FIELDS:
        arr = arrays[sensor]
        valid = arr[~np.isnan(arr)]
        if valid.size == 0:
            mean = std = min_v = max_v = latest = 0.0
        else:
            mean = float(valid.mean())
            std = float(valid.std())
            min_v = float(valid.min())
            max_v = float(valid.max())
            latest = float(valid[-1])
        slope = _calc_slope(arr)
        feature_map[f"{sensor}_mean"] = mean
        feature_map[f"{sensor}_std"] = std
        feature_map[f"{sensor}_min"] = min_v
        feature_map[f"{sensor}_max"] = max_v
        feature_map[f"{sensor}_slope"] = slope
        feature_map[f"{sensor}_latest"] = latest

    for left, right in CORR_PAIRS:
        feature_map[f"corr_{left}_{right}"] = _calc_corr(arrays[left], arrays[right])

    failure_arr = arrays["failure"]
    failure_valid = failure_arr[~np.isnan(failure_arr)]
    feature_map["failure_ratio"] = float(failure_valid.mean()) if failure_valid.size else 0.0

    first_ts = getattr(window_rows[0], "timestamp", None) if window_rows else None
    last_ts = getattr(window_rows[-1], "timestamp", None) if window_rows else None
    if isinstance(first_ts, datetime) and isinstance(last_ts, datetime):
        feature_map["window_seconds"] = max(0.0, float((last_ts - first_ts).total_seconds()))
    else:
        feature_map["window_seconds"] = max(0.0, float(len(window_rows) - 1))

    total_cells = len(window_rows) * len(SENSOR_FIELDS)
    valid_cells = int(sum(np.count_nonzero(~np.isnan(arrays[s])) for s in SENSOR_FIELDS))
    feature_map["valid_ratio"] = float(valid_cells / total_cells) if total_cells else 0.0

    throttle_mean = feature_map["throttle_pos_mean"]
    if abs(throttle_mean) < 1e-6:
        feature_map["rpm_to_throttle_mean_ratio"] = 0.0
    else:
        feature_map["rpm_to_throttle_mean_ratio"] = feature_map["engine_rpm_mean"] / throttle_mean

    return feature_map


def feature_map_to_vector(feature_map: Dict[str, float]) -> List[float]:
    return [float(feature_map.get(name, 0.0)) for name in FEATURE_NAMES]


def _build_sensor_overview(feature_map: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    overview: Dict[str, Dict[str, float]] = {}
    for sensor in SENSOR_FIELDS:
        overview[sensor] = {
            "latest": round(feature_map.get(f"{sensor}_latest", 0.0), 6),
            "mean": round(feature_map.get(f"{sensor}_mean", 0.0), 6),
            "std": round(feature_map.get(f"{sensor}_std", 0.0), 6),
            "slope": round(feature_map.get(f"{sensor}_slope", 0.0), 6),
        }
    return overview


def _build_windows(rows: Sequence[SensorTimeseries], window_size: int, stride: int) -> List[Sequence[SensorTimeseries]]:
    if len(rows) < window_size:
        return [rows] if rows else []
    windows: List[Sequence[SensorTimeseries]] = []
    for start in range(0, len(rows) - window_size + 1, stride):
        windows.append(rows[start : start + window_size])
    if not windows:
        windows.append(rows[-window_size:])
    return windows


def build_timeseries_features_payload(
    db: Session,
    device_id: str,
    limit_rows: int = 720,
    window_size: int = 120,
    stride: int = 30,
) -> Dict:
    rows = (
        db.query(SensorTimeseries)
        .filter(SensorTimeseries.device_id == device_id)
        .order_by(SensorTimeseries.timestamp.desc())
        .limit(limit_rows)
        .all()
    )
    if not rows:
        return {
            "source": "db.sensor_timeseries",
            "device_id": device_id,
            "row_count": 0,
            "window_count": 0,
            "feature_count": FEATURE_COUNT,
            "feature_names": FEATURE_NAMES,
            "features_46": [0.0] * FEATURE_COUNT,
            "feature_map_46": {name: 0.0 for name in FEATURE_NAMES},
            "note": "No timeseries rows found for device",
        }

    rows = list(reversed(rows))
    windows = _build_windows(rows, window_size=window_size, stride=stride)
    latest_window = windows[-1]
    latest_map = extract_feature_map(latest_window)
    latest_vector = feature_map_to_vector(latest_map)

    first_ts = rows[0].timestamp
    last_ts = rows[-1].timestamp

    return {
        "source": "db.sensor_timeseries",
        "device_id": device_id,
        "row_count": len(rows),
        "window_size": window_size,
        "stride": stride,
        "window_count": len(windows),
        "time_range": {"start": str(first_ts), "end": str(last_ts)},
        "latest_window_time_range": {
            "start": str(latest_window[0].timestamp),
            "end": str(latest_window[-1].timestamp),
        },
        "feature_count": FEATURE_COUNT,
        "feature_names": FEATURE_NAMES,
        "features_46": latest_vector,
        "feature_map_46": latest_map,
        "sensor_overview": _build_sensor_overview(latest_map),
        "failure_ratio": latest_map.get("failure_ratio", 0.0),
        "window_seconds": latest_map.get("window_seconds", 0.0),
        "valid_ratio": latest_map.get("valid_ratio", 0.0),
    }

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.models.domain import SensorTimeseries
from .preprocessing import FEATURE_COUNT, extract_feature_map, feature_map_to_vector


@dataclass
class RetrainResult:
    model_target: str
    trained_at: str
    sample_count: int
    positive_ratio: float
    metrics: Dict[str, float]
    artifact_paths: Dict[str, str]
    model_version: str


def _rows_for_period(db: Session, *, period_months: int) -> List[SensorTimeseries]:
    since = datetime.utcnow() - timedelta(days=max(1, int(period_months)) * 30)
    return (
        db.query(SensorTimeseries)
        .filter(SensorTimeseries.timestamp >= since)
        .order_by(SensorTimeseries.device_id.asc(), SensorTimeseries.timestamp.asc())
        .all()
    )


def _split_by_device(rows: Sequence[SensorTimeseries]) -> Dict[str, List[SensorTimeseries]]:
    out: Dict[str, List[SensorTimeseries]] = {}
    for row in rows:
        device_id = str(getattr(row, "device_id", "") or "")
        if not device_id:
            continue
        out.setdefault(device_id, []).append(row)
    return out


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_training_dataset(
    device_rows: Dict[str, List[SensorTimeseries]],
    *,
    window_size: int = 120,
    stride: int = 20,
    horizon_steps: int = 60,
    rul_cap: int = 1440,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    x_rows: List[List[float]] = []
    y_fail: List[int] = []
    y_rul: List[float] = []

    for _device, rows in device_rows.items():
        n = len(rows)
        if n < window_size + 2:
            continue
        for start in range(0, n - window_size - 1, stride):
            end = start + window_size
            window = rows[start:end]
            if len(window) < window_size:
                continue

            feature_map = extract_feature_map(window)
            vector = feature_map_to_vector(feature_map)
            if len(vector) != FEATURE_COUNT:
                continue

            lookahead_end = min(n, end + horizon_steps)
            future = rows[end:lookahead_end]
            if not future:
                continue

            future_fail_indexes = [idx for idx, row in enumerate(future, start=1) if bool(getattr(row, "failure", False))]
            if future_fail_indexes:
                rul_target = min(future_fail_indexes[0], rul_cap)
                fail_target = 1
            else:
                rul_target = min(len(future), rul_cap)
                fail_target = 0

            x_rows.append([_safe_float(v, 0.0) for v in vector])
            y_fail.append(fail_target)
            y_rul.append(float(rul_target))

    if not x_rows:
        return np.zeros((0, FEATURE_COUNT), dtype=np.float32), np.zeros((0,), dtype=np.int32), np.zeros((0,), dtype=np.float32)
    return (
        np.asarray(x_rows, dtype=np.float32),
        np.asarray(y_fail, dtype=np.int32),
        np.asarray(y_rul, dtype=np.float32),
    )


def _time_split(x: np.ndarray, y_cls: np.ndarray, y_rul: np.ndarray, ratio: float = 0.8):
    n = int(x.shape[0])
    split = max(1, min(n - 1, int(n * ratio)))
    return (
        x[:split],
        x[split:],
        y_cls[:split],
        y_cls[split:],
        y_rul[:split],
        y_rul[split:],
    )


def train_prediction_models(
    db: Session,
    *,
    period_months: int,
    model_dir: Path,
    preferred_algorithm: str = "lightgbm",
    allow_fallback: bool = False,
) -> RetrainResult:
    rows = _rows_for_period(db, period_months=period_months)
    device_rows = _split_by_device(rows)
    x, y_cls, y_rul = _build_training_dataset(device_rows)

    if int(x.shape[0]) < 200:
        raise RuntimeError(f"insufficient_training_samples:{int(x.shape[0])}")
    cls_unique = np.unique(y_cls)
    if cls_unique.size < 2:
        raise RuntimeError("insufficient_class_diversity")

    from sklearn.metrics import log_loss, mean_absolute_error, roc_auc_score  # type: ignore

    x_train, x_valid, y_cls_train, y_cls_valid, y_rul_train, y_rul_valid = _time_split(x, y_cls, y_rul, ratio=0.8)
    model_dir.mkdir(parents=True, exist_ok=True)
    failure_path: Path
    rul_path: Path
    meta_path = model_dir / "model_meta.json"
    preferred = (preferred_algorithm or "lightgbm").strip().lower()
    force_sklearn = preferred in {"sklearn", "sklearn_hgbt", "hgbt"}
    algorithm = "lightgbm"
    last_error: Exception | None = None

    try:
        if force_sklearn:
            raise RuntimeError("force_sklearn")
        import lightgbm as lgb  # type: ignore

        cls_train = lgb.Dataset(x_train, label=y_cls_train)
        cls_valid = lgb.Dataset(x_valid, label=y_cls_valid, reference=cls_train)
        reg_train = lgb.Dataset(x_train, label=y_rul_train)
        reg_valid = lgb.Dataset(x_valid, label=y_rul_valid, reference=reg_train)

        cls_params = {
            "objective": "binary",
            "metric": ["binary_logloss", "auc"],
            "learning_rate": 0.05,
            "num_leaves": 31,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbose": -1,
            "seed": 42,
        }
        reg_params = {
            "objective": "regression",
            "metric": ["l1", "l2"],
            "learning_rate": 0.05,
            "num_leaves": 31,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbose": -1,
            "seed": 42,
        }

        cls_model = lgb.train(
            cls_params,
            cls_train,
            num_boost_round=300,
            valid_sets=[cls_valid],
            callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
        )
        reg_model = lgb.train(
            reg_params,
            reg_train,
            num_boost_round=300,
            valid_sets=[reg_valid],
            callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
        )

        cls_pred = np.clip(cls_model.predict(x_valid), 1e-6, 1.0 - 1e-6)
        rul_pred = reg_model.predict(x_valid)
        metrics: Dict[str, float] = {
            "valid_logloss": float(log_loss(y_cls_valid, cls_pred)),
            "valid_auc": float(roc_auc_score(y_cls_valid, cls_pred)),
            "valid_mae_rul": float(mean_absolute_error(y_rul_valid, rul_pred)),
            "train_samples": float(x_train.shape[0]),
            "valid_samples": float(x_valid.shape[0]),
        }

        failure_path = model_dir / "lgbm_failure.txt"
        rul_path = model_dir / "lgbm_rul.txt"
        cls_model.save_model(str(failure_path))
        reg_model.save_model(str(rul_path))
    except Exception as exc:
        last_error = exc
        if preferred == "lightgbm" and not allow_fallback:
            raise RuntimeError(f"lightgbm_training_failed:{exc}") from exc

        import joblib  # type: ignore
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor  # type: ignore

        algorithm = "sklearn_hgbt"
        cls_model = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_depth=8,
            max_iter=300,
            random_state=42,
        )
        reg_model = HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_depth=8,
            max_iter=300,
            random_state=42,
        )
        cls_model.fit(x_train, y_cls_train)
        reg_model.fit(x_train, y_rul_train)
        cls_pred = np.clip(cls_model.predict_proba(x_valid)[:, 1], 1e-6, 1.0 - 1e-6)
        rul_pred = reg_model.predict(x_valid)
        metrics = {
            "valid_logloss": float(log_loss(y_cls_valid, cls_pred)),
            "valid_auc": float(roc_auc_score(y_cls_valid, cls_pred)),
            "valid_mae_rul": float(mean_absolute_error(y_rul_valid, rul_pred)),
            "train_samples": float(x_train.shape[0]),
            "valid_samples": float(x_valid.shape[0]),
        }
        failure_path = model_dir / "sklearn_failure.joblib"
        rul_path = model_dir / "sklearn_rul.joblib"
        joblib.dump(cls_model, failure_path)
        joblib.dump(reg_model, rul_path)

    if preferred == "lightgbm" and algorithm != "lightgbm":
        detail = f":{last_error}" if last_error else ""
        raise RuntimeError(f"lightgbm_not_selected{detail}")

    trained_at = datetime.utcnow()
    version = f"{algorithm}-retrained-{trained_at.strftime('%Y%m%d%H%M%S')}"
    meta = {
        "model_target": "prediction",
        "version": version,
        "algorithm": algorithm,
        "trained_at": trained_at.isoformat(),
        "period_months": int(period_months),
        "sample_count": int(x.shape[0]),
        "positive_ratio": float(np.mean(y_cls)),
        "metrics": metrics,
        "artifacts": {
            "failure_model": str(failure_path),
            "rul_model": str(rul_path),
        },
    }
    with meta_path.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)

    return RetrainResult(
        model_target="prediction",
        trained_at=trained_at.isoformat(),
        sample_count=int(x.shape[0]),
        positive_ratio=float(np.mean(y_cls)),
        metrics={k: round(v, 6) for k, v in metrics.items()},
        artifact_paths={
            "failure_model": str(failure_path),
            "rul_model": str(rul_path),
            "meta": str(meta_path),
        },
        model_version=version,
    )

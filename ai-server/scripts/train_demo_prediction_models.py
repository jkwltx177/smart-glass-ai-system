from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import numpy as np
from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.prediction.preprocessing import FEATURE_NAMES


WINDOW = 120
STRIDE = 30


def _slope(values: np.ndarray) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float32)
    x_mean = float(x.mean())
    y_mean = float(values.mean())
    numerator = float(np.sum((x - x_mean) * (values - y_mean)))
    denominator = float(np.sum((x - x_mean) ** 2))
    return 0.0 if denominator == 0 else numerator / denominator


def _stats(values: np.ndarray) -> dict:
    if values.size == 0:
        return {"latest": 0.0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "slope": 0.0}
    return {
        "latest": float(values[-1]),
        "mean": float(values.mean()),
        "std": float(values.std()),
        "min": float(values.min()),
        "max": float(values.max()),
        "slope": float(_slope(values)),
    }


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or len(b) < 2:
        return 0.0
    sa = float(np.std(a))
    sb = float(np.std(b))
    if sa == 0.0 or sb == 0.0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _to_feature_vector(summary: dict) -> List[float]:
    return [float(summary.get(name, 0.0)) for name in FEATURE_NAMES]


def load_timeseries() -> List[dict]:
    query = text(
        """
        SELECT device_id, timestamp, engine_rpm, coolant_temp, intake_air_temp,
               throttle_pos, fuel_trim, maf, failure
        FROM sensor_timeseries
        ORDER BY device_id, timestamp
        """
    )
    with SessionLocal() as db:
        rows = db.execute(query).mappings().all()
    return [dict(r) for r in rows]


def build_dataset(rows: List[dict]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    by_device = {}
    for row in rows:
        by_device.setdefault(row["device_id"], []).append(row)

    x_rows: List[List[float]] = []
    y_fail: List[float] = []
    y_rul: List[float] = []

    for _, seq in by_device.items():
        arr = np.array(
            [
                [
                    float(r["engine_rpm"] or 0.0),
                    float(r["coolant_temp"] or 0.0),
                    float(r["intake_air_temp"] or 0.0),
                    float(r["throttle_pos"] or 0.0),
                    float(r["fuel_trim"] or 0.0),
                    float(r["maf"] or 0.0),
                    float(r["failure"] or 0.0),
                ]
                for r in seq
            ],
            dtype=np.float32,
        )
        if len(arr) < WINDOW + 1:
            continue

        failure_idx = np.where(arr[:, 6] > 0.5)[0]
        first_failure = int(failure_idx[0]) if len(failure_idx) > 0 else None

        for start in range(0, len(arr) - WINDOW + 1, STRIDE):
            end = start + WINDOW
            win = arr[start:end]
            summary = {
                "engine_rpm": _stats(win[:, 0]),
                "coolant_temp": _stats(win[:, 1]),
                "intake_air_temp": _stats(win[:, 2]),
                "throttle_pos": _stats(win[:, 3]),
                "fuel_trim": _stats(win[:, 4]),
                "maf": _stats(win[:, 5]),
            }
            feature_map = {}
            for sensor in ("engine_rpm", "coolant_temp", "intake_air_temp", "throttle_pos", "fuel_trim", "maf"):
                stat_obj = summary[sensor]
                for stat_name in ("latest", "mean", "std", "min", "max", "slope"):
                    feature_map[f"{sensor}_{stat_name}"] = float(stat_obj.get(stat_name, 0.0))

            feature_map["corr_engine_rpm_coolant_temp"] = _corr(win[:, 0], win[:, 1])
            feature_map["corr_engine_rpm_throttle_pos"] = _corr(win[:, 0], win[:, 3])
            feature_map["corr_engine_rpm_maf"] = _corr(win[:, 0], win[:, 5])
            feature_map["corr_coolant_temp_fuel_trim"] = _corr(win[:, 1], win[:, 4])
            feature_map["corr_throttle_pos_fuel_trim"] = _corr(win[:, 3], win[:, 4])
            feature_map["corr_maf_fuel_trim"] = _corr(win[:, 5], win[:, 4])

            feature_map["failure_ratio"] = float(win[:, 6].mean())
            feature_map["window_seconds"] = float(WINDOW - 1)
            feature_map["valid_ratio"] = 1.0
            throttle_mean = float(summary["throttle_pos"]["mean"])
            feature_map["rpm_to_throttle_mean_ratio"] = (
                0.0 if abs(throttle_mean) < 1e-6 else float(summary["engine_rpm"]["mean"]) / throttle_mean
            )
            x_rows.append(_to_feature_vector(feature_map))

            if first_failure is None:
                y_fail.append(0.0)
                y_rul.append(480.0)
            else:
                future_fail = 1.0 if end >= first_failure else 0.0
                y_fail.append(future_fail)
                rul = max(1.0, float(first_failure - end))
                y_rul.append(rul)

    return np.array(x_rows, dtype=np.float32), np.array(y_fail, dtype=np.float32), np.array(y_rul, dtype=np.float32)


def train_and_save(x: np.ndarray, y_fail: np.ndarray, y_rul: np.ndarray, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    import lightgbm as lgb
    import xgboost as xgb
    import torch
    import torch.nn as nn

    dtrain_fail = lgb.Dataset(x, label=y_fail)
    dtrain_rul = lgb.Dataset(x, label=y_rul)
    lgb_fail = lgb.train({"objective": "binary", "verbosity": -1}, dtrain_fail, num_boost_round=50)
    lgb_rul = lgb.train({"objective": "regression", "verbosity": -1}, dtrain_rul, num_boost_round=50)
    lgb_fail.save_model(str(out_dir / "lgbm_failure.txt"))
    lgb_rul.save_model(str(out_dir / "lgbm_rul.txt"))

    xgb_fail = xgb.XGBClassifier(
        n_estimators=50,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="logloss",
    )
    xgb_rul = xgb.XGBRegressor(
        n_estimators=50,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
    )
    xgb_fail.fit(x, y_fail)
    xgb_rul.fit(x, y_rul)
    xgb_fail.get_booster().save_model(str(out_dir / "xgb_failure.json"))
    xgb_rul.get_booster().save_model(str(out_dir / "xgb_rul.json"))

    class TinyTCN(nn.Module):
        def __init__(self, in_dim: int):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(in_dim, 64),
                nn.ReLU(),
                nn.Linear(64, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
            )

        def forward(self, x):
            return self.net(x)

    x_tensor = torch.tensor(x, dtype=torch.float32)
    y_fail_tensor = torch.tensor(y_fail.reshape(-1, 1), dtype=torch.float32)
    y_rul_tensor = torch.tensor(y_rul.reshape(-1, 1), dtype=torch.float32)

    tcn_fail = TinyTCN(x.shape[1])
    tcn_rul = TinyTCN(x.shape[1])

    opt_fail = torch.optim.Adam(tcn_fail.parameters(), lr=1e-3)
    opt_rul = torch.optim.Adam(tcn_rul.parameters(), lr=1e-3)
    bce = nn.BCEWithLogitsLoss()
    mse = nn.MSELoss()

    for _ in range(80):
        opt_fail.zero_grad()
        loss_fail = bce(tcn_fail(x_tensor), y_fail_tensor)
        loss_fail.backward()
        opt_fail.step()

        opt_rul.zero_grad()
        loss_rul = mse(tcn_rul(x_tensor), y_rul_tensor)
        loss_rul.backward()
        opt_rul.step()

    scripted_fail = torch.jit.script(tcn_fail.eval())
    scripted_rul = torch.jit.script(tcn_rul.eval())
    scripted_fail.save(str(out_dir / "tcn_failure.pt"))
    scripted_rul.save(str(out_dir / "tcn_rul.pt"))


def main() -> None:
    rows = load_timeseries()
    if not rows:
        raise RuntimeError("No rows found in sensor_timeseries.")
    x, y_fail, y_rul = build_dataset(rows)
    if len(x) == 0:
        raise RuntimeError("Failed to build dataset from sensor_timeseries.")
    out_dir = Path(__file__).resolve().parents[1] / "models" / "weights"
    train_and_save(x, y_fail, y_rul, out_dir)
    print(f"Saved model files to: {out_dir}")
    print(f"dataset rows={len(x)} feature_dim={x.shape[1]}")


if __name__ == "__main__":
    main()

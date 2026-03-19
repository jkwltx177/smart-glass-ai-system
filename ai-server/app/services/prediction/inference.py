import math
import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from app.core.config import settings
from app.services.prediction.preprocessing import FEATURE_COUNT, FEATURE_NAMES


AI_SERVER_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MODEL_DIRS = [
    AI_SERVER_ROOT / "models" / "weights",
    PROJECT_ROOT / "models" / "weights",
]

FEATURE_KEYS: List[Tuple[str, str]] = [
    ("engine_rpm", "latest"),
    ("engine_rpm", "mean"),
    ("engine_rpm", "std"),
    ("engine_rpm", "slope"),
    ("coolant_temp", "latest"),
    ("coolant_temp", "mean"),
    ("coolant_temp", "std"),
    ("coolant_temp", "slope"),
    ("intake_air_temp", "latest"),
    ("intake_air_temp", "mean"),
    ("intake_air_temp", "std"),
    ("intake_air_temp", "slope"),
    ("throttle_pos", "latest"),
    ("throttle_pos", "mean"),
    ("throttle_pos", "std"),
    ("throttle_pos", "slope"),
    ("fuel_trim", "latest"),
    ("fuel_trim", "mean"),
    ("fuel_trim", "std"),
    ("fuel_trim", "slope"),
    ("maf", "latest"),
    ("maf", "mean"),
    ("maf", "std"),
    ("maf", "slope"),
]


@dataclass
class PredictionResult:
    failure_probability: float
    predicted_rul_minutes: float
    anomaly_score: float
    model_versions: List[str]
    model_source: str


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _build_features(summary: Optional[Dict]) -> List[float]:
    if not summary:
        return [0.0] * FEATURE_COUNT

    # Preferred path: preprocessed 46-feature vector
    if isinstance(summary, dict):
        raw_vector = summary.get("features_46")
        if isinstance(raw_vector, list) and len(raw_vector) >= FEATURE_COUNT:
            return [_safe_float(v, 0.0) for v in raw_vector[:FEATURE_COUNT]]
        raw_map = summary.get("feature_map_46")
        if isinstance(raw_map, dict):
            return [_safe_float(raw_map.get(name), 0.0) for name in FEATURE_NAMES]

    vector: List[float] = []
    for metric, stat in FEATURE_KEYS:
        metric_obj = summary.get(metric, {}) if isinstance(summary, dict) else {}
        value = metric_obj.get(stat) if isinstance(metric_obj, dict) else 0.0
        vector.append(_safe_float(value, 0.0))

    vector.append(_safe_float(summary.get("failure_ratio"), 0.0))
    vector.append(_safe_float(summary.get("window_size"), 0.0))
    if len(vector) < FEATURE_COUNT:
        vector.extend([0.0] * (FEATURE_COUNT - len(vector)))
    return vector[:FEATURE_COUNT]


def _heuristic_predict(summary: Optional[Dict]) -> PredictionResult:
    metric = summary or {}
    coolant_latest = _safe_float(metric.get("coolant_temp", {}).get("latest") if isinstance(metric.get("coolant_temp"), dict) else 0.0)
    fuel_trim_latest = _safe_float(metric.get("fuel_trim", {}).get("latest") if isinstance(metric.get("fuel_trim"), dict) else 0.0)
    rpm_std = _safe_float(metric.get("engine_rpm", {}).get("std") if isinstance(metric.get("engine_rpm"), dict) else 0.0)
    failure_ratio = _safe_float(metric.get("failure_ratio"), 0.0)

    temp_risk = _clip((coolant_latest - 85.0) / 20.0, 0.0, 1.0)
    fuel_risk = _clip((fuel_trim_latest - 10.0) / 12.0, 0.0, 1.0)
    rpm_risk = _clip(rpm_std / 450.0, 0.0, 1.0)
    raw_score = (0.4 * temp_risk) + (0.25 * fuel_risk) + (0.25 * failure_ratio) + (0.1 * rpm_risk)
    failure_probability = _clip(raw_score, 0.01, 0.99)

    predicted_rul = _clip((1.0 - failure_probability) * 480.0, 15.0, 720.0)
    anomaly_score = _clip((failure_probability * 0.8) + (0.2 * failure_ratio), 0.0, 1.0)

    return PredictionResult(
        failure_probability=round(failure_probability, 4),
        predicted_rul_minutes=round(predicted_rul, 2),
        anomaly_score=round(anomaly_score, 4),
        model_versions=["heuristic-v1"],
        model_source="heuristic",
    )


class Predictor:
    def __init__(self, model_dir: Optional[str] = None):
        configured = model_dir or os.getenv("PREDICTION_MODEL_DIR") or settings.PREDICTION_MODEL_DIR
        configured_path = Path(configured)
        if configured_path.is_absolute():
            self.model_dir = configured_path
        else:
            self.model_dir = AI_SERVER_ROOT / configured_path
        if not self.model_dir.exists():
            for fallback_dir in DEFAULT_MODEL_DIRS:
                if fallback_dir.exists():
                    self.model_dir = fallback_dir
                    break
        self._ready = False
        self._lgbm_fail = None
        self._lgbm_rul = None
        self._xgb_fail = None
        self._xgb_rul = None
        self._sk_fail = None
        self._sk_rul = None
        self._tcn_fail = None
        self._tcn_rul = None
        self._versions: List[str] = []
        self._active_algorithms: Optional[set[str]] = None

    def _load_meta_policy(self) -> None:
        meta_path = self.model_dir / "model_meta.json"
        if not meta_path.exists():
            return
        try:
            with meta_path.open("r", encoding="utf-8") as fh:
                meta = json.load(fh)
            algorithm = str(meta.get("algorithm", "")).strip().lower()
            mapped = {
                "lightgbm": {"lgbm"},
                "lgbm": {"lgbm"},
                "sklearn_hgbt": {"sklearn"},
                "sklearn": {"sklearn"},
                "xgboost": {"xgb"},
                "xgb": {"xgb"},
                "tcn": {"tcn"},
            }.get(algorithm)
            if mapped:
                self._active_algorithms = mapped
        except Exception:
            self._active_algorithms = None

    def _load_lightgbm(self) -> None:
        try:
            import lightgbm as lgb  # type: ignore
        except Exception:
            return

        fail_path = self.model_dir / "lgbm_failure.txt"
        rul_path = self.model_dir / "lgbm_rul.txt"
        if fail_path.exists():
            self._lgbm_fail = lgb.Booster(model_file=str(fail_path))
            self._versions.append(f"lgbm:{fail_path.name}")
        if rul_path.exists():
            self._lgbm_rul = lgb.Booster(model_file=str(rul_path))
            if f"lgbm:{rul_path.name}" not in self._versions:
                self._versions.append(f"lgbm:{rul_path.name}")

    def _load_xgboost(self) -> None:
        try:
            import xgboost as xgb  # type: ignore
        except Exception:
            return

        fail_path = self.model_dir / "xgb_failure.json"
        rul_path = self.model_dir / "xgb_rul.json"
        if fail_path.exists():
            model = xgb.Booster()
            model.load_model(str(fail_path))
            self._xgb_fail = model
            self._versions.append(f"xgb:{fail_path.name}")
        if rul_path.exists():
            model = xgb.Booster()
            model.load_model(str(rul_path))
            self._xgb_rul = model
            if f"xgb:{rul_path.name}" not in self._versions:
                self._versions.append(f"xgb:{rul_path.name}")

    def _load_tcn(self) -> None:
        try:
            import torch  # type: ignore
        except Exception:
            return

        fail_path = self.model_dir / "tcn_failure.pt"
        rul_path = self.model_dir / "tcn_rul.pt"
        if fail_path.exists():
            self._tcn_fail = torch.jit.load(str(fail_path), map_location="cpu")
            self._tcn_fail.eval()
            self._versions.append(f"tcn:{fail_path.name}")
        if rul_path.exists():
            self._tcn_rul = torch.jit.load(str(rul_path), map_location="cpu")
            self._tcn_rul.eval()
            if f"tcn:{rul_path.name}" not in self._versions:
                self._versions.append(f"tcn:{rul_path.name}")

    def _load_sklearn(self) -> None:
        try:
            import joblib  # type: ignore
        except Exception:
            return

        fail_path = self.model_dir / "sklearn_failure.joblib"
        rul_path = self.model_dir / "sklearn_rul.joblib"
        if fail_path.exists():
            try:
                self._sk_fail = joblib.load(fail_path)
                self._versions.append(f"sk:{fail_path.name}")
            except Exception:
                self._sk_fail = None
        if rul_path.exists():
            try:
                self._sk_rul = joblib.load(rul_path)
                if f"sk:{rul_path.name}" not in self._versions:
                    self._versions.append(f"sk:{rul_path.name}")
            except Exception:
                self._sk_rul = None

    def _lazy_load(self) -> None:
        if self._ready:
            return
        self._load_meta_policy()
        self._load_sklearn()
        self._load_lightgbm()
        self._load_xgboost()
        self._load_tcn()
        self._ready = True

    def _is_active(self, key: str) -> bool:
        if not self._active_algorithms:
            return True
        return key in self._active_algorithms

    def _visible_versions(self) -> List[str]:
        if not self._versions:
            return ["ensemble"]
        if not self._active_algorithms:
            return self._versions[:]
        prefix_map = {
            "sklearn": "sk:",
            "lgbm": "lgbm:",
            "xgb": "xgb:",
            "tcn": "tcn:",
        }
        allowed_prefixes = tuple(prefix_map[k] for k in self._active_algorithms if k in prefix_map)
        filtered = [v for v in self._versions if v.startswith(allowed_prefixes)]
        return filtered or self._versions[:]

    @staticmethod
    def _fit_dim(features: List[float], target_dim: int) -> List[float]:
        if target_dim <= 0:
            return features
        if len(features) == target_dim:
            return features
        if len(features) > target_dim:
            return features[:target_dim]
        return features + ([0.0] * (target_dim - len(features)))

    def _predict_lgbm(self, features: List[float]) -> Tuple[Optional[float], Optional[float]]:
        fail = None
        rul = None
        if self._lgbm_fail is not None:
            try:
                dim = int(self._lgbm_fail.num_feature())
                sample = [self._fit_dim(features, dim)]
                fail = float(self._lgbm_fail.predict(sample)[0])
            except Exception:
                fail = None
        if self._lgbm_rul is not None:
            try:
                dim = int(self._lgbm_rul.num_feature())
                sample = [self._fit_dim(features, dim)]
                rul = float(self._lgbm_rul.predict(sample)[0])
            except Exception:
                rul = None
        return fail, rul

    def _predict_xgb(self, features: List[float]) -> Tuple[Optional[float], Optional[float]]:
        if self._xgb_fail is None and self._xgb_rul is None:
            return None, None
        import xgboost as xgb  # type: ignore

        fail = None
        rul = None
        if self._xgb_fail is not None:
            try:
                dim = int(self._xgb_fail.num_features())
                dmat = xgb.DMatrix([self._fit_dim(features, dim)])
                fail = float(self._xgb_fail.predict(dmat)[0])
            except Exception:
                fail = None
        if self._xgb_rul is not None:
            try:
                dim = int(self._xgb_rul.num_features())
                dmat = xgb.DMatrix([self._fit_dim(features, dim)])
                rul = float(self._xgb_rul.predict(dmat)[0])
            except Exception:
                rul = None
        return fail, rul

    def _predict_tcn(self, features: List[float]) -> Tuple[Optional[float], Optional[float]]:
        if self._tcn_fail is None and self._tcn_rul is None:
            return None, None
        import torch  # type: ignore

        fail = None
        rul = None
        with torch.no_grad():
            if self._tcn_fail is not None:
                for dim in (len(features), 46, 26):
                    try:
                        x = torch.tensor([self._fit_dim(features, dim)], dtype=torch.float32)
                        fail_out = self._tcn_fail(x).reshape(-1)[0].item()
                        fail = float(1.0 / (1.0 + math.exp(-fail_out)))
                        break
                    except Exception:
                        continue
            if self._tcn_rul is not None:
                for dim in (len(features), 46, 26):
                    try:
                        x = torch.tensor([self._fit_dim(features, dim)], dtype=torch.float32)
                        rul = float(self._tcn_rul(x).reshape(-1)[0].item())
                        break
                    except Exception:
                        continue
        return fail, rul

    def _predict_sklearn(self, features: List[float]) -> Tuple[Optional[float], Optional[float]]:
        if self._sk_fail is None and self._sk_rul is None:
            return None, None
        arr = [features]
        fail = None
        rul = None
        if self._sk_fail is not None:
            try:
                if hasattr(self._sk_fail, "predict_proba"):
                    fail = float(self._sk_fail.predict_proba(arr)[0][1])
                else:
                    fail = float(self._sk_fail.predict(arr)[0])
            except Exception:
                fail = None
        if self._sk_rul is not None:
            try:
                rul = float(self._sk_rul.predict(arr)[0])
            except Exception:
                rul = None
        return fail, rul

    def predict(self, telemetry_summary: Optional[Dict]) -> PredictionResult:
        self._lazy_load()
        features = _build_features(telemetry_summary)

        fail_preds: List[float] = []
        rul_preds: List[float] = []

        for fail, rul in (
            self._predict_sklearn(features) if self._is_active("sklearn") else (None, None),
            self._predict_lgbm(features) if self._is_active("lgbm") else (None, None),
            self._predict_xgb(features) if self._is_active("xgb") else (None, None),
            self._predict_tcn(features) if self._is_active("tcn") else (None, None),
        ):
            if fail is not None and not math.isnan(fail):
                fail_preds.append(_clip(fail, 0.0, 1.0))
            if rul is not None and not math.isnan(rul):
                rul_preds.append(rul)

        if not fail_preds and not rul_preds:
            return _heuristic_predict(telemetry_summary)

        failure_probability = (
            sum(fail_preds) / len(fail_preds)
            if fail_preds
            else _heuristic_predict(telemetry_summary).failure_probability
        )
        predicted_rul = (
            sum(rul_preds) / len(rul_preds)
            if rul_preds
            else (1.0 - failure_probability) * 480.0
        )
        predicted_rul = _clip(predicted_rul, 1.0, 1440.0)
        anomaly_score = _clip((failure_probability * 0.75) + 0.15, 0.0, 1.0)

        return PredictionResult(
            failure_probability=round(failure_probability, 4),
            predicted_rul_minutes=round(predicted_rul, 2),
            anomaly_score=round(anomaly_score, 4),
            model_versions=self._visible_versions(),
            model_source=(
                "ensemble"
                if not self._active_algorithms
                else ",".join(sorted(self._active_algorithms))
            ),
        )


_PREDICTOR = Predictor()


def predict_from_timeseries_summary(telemetry_summary: Optional[Dict]) -> PredictionResult:
    return _PREDICTOR.predict(telemetry_summary)


def reload_predictor(model_dir: Optional[str] = None) -> None:
    global _PREDICTOR
    _PREDICTOR = Predictor(model_dir=model_dir)

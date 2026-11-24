"""backend/detection/anomaly_detection.py — Real Isolation Forest Anomaly Detection.

Loads the pre-trained Isolation Forest and fitted StandardScaler from ai_models.
Enforces strict feature validation and empirical confidence mapping.
Raises ModelNotFoundError / FeatureValidationError on missing components.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
import numpy as np
import joblib

logger = logging.getLogger(__name__)


class FeatureValidationError(ValueError):
    """Raised when telemetry dictionary is missing required model features."""
    pass


class ModelNotFoundError(FileNotFoundError):
    """Raised when pre-trained model or scaler artifacts are missing."""
    pass


def load_model_version(version_path: str = "ai_models/model_version.json") -> str:
    """Read serialized model version string."""
    if os.path.exists(version_path):
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version", "1.2.0-synthetic-baseline")
        except Exception:
            pass
    return "1.2.0-synthetic-baseline"


class AnomalyDetector:
    """Production-grade multivariate anomaly detector using trained Isolation Forest."""

    DEFAULT_FEATURES: List[str] = [
        "latency_ms",
        "packet_loss_pct",
        "cpu_pct",
        "memory_pct",
        "bandwidth_mbps",
        "interface_up",
        "error_count"
    ]

    def __init__(
        self,
        model_path: str = "ai_models/trained_model.pkl",
        scaler_path: str = "ai_models/scaler.pkl",
        version_path: str = "ai_models/model_version.json"
    ):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.feature_cols = list(self.DEFAULT_FEATURES)

        # 1. Enforce model and scaler existence (NEVER fall back silently)
        if not os.path.exists(self.model_path):
            raise ModelNotFoundError(
                f"Trained IsolationForest model artifact not found at '{self.model_path}'. "
                "Execute 'python ai_models/train_model.py' first."
            )
        if not os.path.exists(self.scaler_path):
            raise ModelNotFoundError(
                f"Fitted StandardScaler artifact not found at '{self.scaler_path}'. "
                "Execute 'python ai_models/train_model.py' first."
            )

        self.model = joblib.load(self.model_path)
        self.scaler = joblib.load(self.scaler_path)
        self.model_version = load_model_version(version_path)
        logger.info("AnomalyDetector loaded trained model (%s) and scaler successfully", self.model_version)

    def _score_to_confidence(self, raw_score: float) -> float:
        """Convert Isolation Forest decision score to an empirical confidence probability [0.0, 1.0].

        Sklearn score_samples returns negative values (typically between -0.8 and -0.3).
        Lower raw_score indicates stronger anomaly.
        """
        # Threshold: roughly -0.5 is anomalous
        # Normalize: map score <= -0.50 into 0.70 - 1.00 confidence
        # map score > -0.50 into 0.05 - 0.50
        anomaly_dist = -raw_score  # higher = more anomalous
        if anomaly_dist >= 0.55:
            conf = 0.80 + min(0.19, (anomaly_dist - 0.55) * 1.5)
        elif anomaly_dist >= 0.50:
            conf = 0.65 + (anomaly_dist - 0.50) * 3.0
        else:
            conf = max(0.05, anomaly_dist * 1.2)

        return round(float(np.clip(conf, 0.0, 1.0)), 3)

    def predict(self, metrics_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Predict whether a given network telemetry vector is anomalous.

        Args:
            metrics_dict: Dictionary containing all numeric features:
                          latency_ms, packet_loss_pct, cpu_pct, memory_pct,
                          bandwidth_mbps, interface_up, error_count.

        Returns:
            Dict: {
                "is_anomaly": bool,
                "anomaly_score": float,
                "confidence": float,
                "model_version": str
            }

        Raises:
            FeatureValidationError: If any required feature is missing.
        """
        # 1. Validate all required features are present and not null
        missing = [c for c in self.feature_cols if c not in metrics_dict or metrics_dict.get(c) is None]
        if missing:
            raise FeatureValidationError(f"Missing required telemetry feature(s) or null: {missing}")

        # 2. Build feature vector in exact column order
        X = np.array([[float(metrics_dict[c]) for c in self.feature_cols]], dtype=float)

        # 3. Scale with the EXACT SAME scaler fitted during training
        X_scaled = self.scaler.transform(X)

        # 4. Predict (-1 = anomaly, 1 = normal in IsolationForest)
        pred = self.model.predict(X_scaled)[0]
        score = float(self.model.score_samples(X_scaled)[0])

        is_anomaly = bool(pred == -1)
        confidence = self._score_to_confidence(score)

        logger.debug("AnomalyDetector inference: is_anomaly=%s, raw_score=%.4f, conf=%.3f", is_anomaly, score, confidence)

        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": round(score, 4),
            "confidence": confidence,
            "model_version": self.model_version
        }

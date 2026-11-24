"""Anomaly Predictor Module for SentinelNet.

Loads trained models (`IsolationForest` and fitted scaler) to provide real-time
single-sample scoring and multi-row batch prediction for network telemetry.
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
import joblib

try:
    from ai_models.preprocessing import Preprocessor
except ImportError:
    from preprocessing import Preprocessor

logger = logging.getLogger("sentinelnet.predict")


class AnomalyPredictor:
    """Predicts network anomalies and degradation scores from live telemetry inputs."""

    def __init__(
        self,
        model_path: str = "ai_models/trained_model.pkl",
        scaler_path: str = "ai_models/scaler.pkl"
    ):
        """Initialize AnomalyPredictor.

        Args:
            model_path: Path to serialized IsolationForest model.
            scaler_path: Path to serialized StandardScaler.
        """
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.model = None
        self.scaler = None
        self.feature_columns = Preprocessor.NUMERIC_FEATURES

        self.load_model()
        logger.info("AnomalyPredictor ready for inference.")

    def load_model(self) -> None:
        """Load trained Isolation Forest and standard scaler from disk."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model checkpoint not found at '{self.model_path}'. Run train_model.py first.")
        if not os.path.exists(self.scaler_path):
            raise FileNotFoundError(f"Fitted scaler not found at '{self.scaler_path}'. Run train_model.py first.")

        self.model = joblib.load(self.model_path)
        self.scaler = joblib.load(self.scaler_path)
        logger.info("Loaded ML model from '%s' and scaler from '%s'", self.model_path, self.scaler_path)

    def predict(self, metrics_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single telemetry dictionary for anomalies.

        Args:
            metrics_dict: Dictionary containing numeric telemetry keys:
                          latency_ms, packet_loss_pct, cpu_pct, memory_pct,
                          bandwidth_mbps, interface_up, error_count.

        Returns:
            Dict containing:
                - is_anomaly (bool): True if flagged as anomalous
                - score (float): Continuous anomaly score [0.0, 1.0]
                - confidence (float): Confidence level [0.0, 1.0]
                - diagnosis_hint (str): Primary diagnostic hint
        """
        # Extract features in strict order
        raw_values = [
            float(metrics_dict.get(col, 0.0)) for col in self.feature_columns
        ]
        X = np.array([raw_values])

        # Standardize features
        X_scaled = self.scaler.transform(X)

        # IsolationForest predict: -1 = anomaly, 1 = normal
        pred = self.model.predict(X_scaled)[0]
        is_anomaly = bool(pred == -1)

        # score_samples returns negative anomaly score (lower is more anomalous)
        raw_score = self.model.score_samples(X_scaled)[0]
        # Invert and normalize to [0.0, 1.0]
        normalized_score = float(np.clip(-raw_score, 0.0, 1.0))
        confidence = float(np.clip(abs(raw_score) * 2.0, 0.50, 0.99))

        diagnosis_hint = self._generate_hint(metrics_dict, is_anomaly)

        return {
            "is_anomaly": is_anomaly,
            "score": round(normalized_score, 4),
            "confidence": round(confidence, 4),
            "diagnosis_hint": diagnosis_hint
        }

    def _generate_hint(self, metrics: Dict[str, Any], is_anomaly: bool) -> str:
        """Generate heuristic diagnostic explanation for the anomaly."""
        if not is_anomaly:
            return "Normal network operation."

        if metrics.get("interface_up", 1) == 0:
            return "Physical Link or Port Down detected (Total Loss)."
        if metrics.get("packet_loss_pct", 0) > 10.0:
            return "Critical Packet Loss burst (Buffer overflow or dirty fiber)."
        if metrics.get("bandwidth_mbps", 0) > 85.0:
            return "High Bandwidth Congestion approaching link saturation."
        if metrics.get("latency_ms", 0) > 75.0:
            return "Severe Round-Trip Latency degradation."
        if metrics.get("cpu_pct", 0) > 85.0:
            return "Switch control-plane CPU overload."
        return "Subtle multivariate anomaly pattern flagged by Isolation Forest."

    def batch_predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run batch anomaly scoring across a DataFrame for backtesting.

        Args:
            df: DataFrame containing the required feature columns.

        Returns:
            pd.DataFrame with added columns: `predicted_anomaly`, `anomaly_score`.
        """
        result_df = df.copy()
        X_raw = df[self.feature_columns].values
        X_scaled = self.scaler.transform(X_raw)

        raw_preds = self.model.predict(X_scaled)
        scores = -self.model.score_samples(X_scaled)

        result_df["predicted_anomaly"] = np.where(raw_preds == -1, 1, 0)
        result_df["anomaly_score"] = np.round(np.clip(scores, 0.0, 1.0), 4)

        logger.info("Batch inference completed on %d rows. Detected %d anomalies.",
                    len(df), int(result_df["predicted_anomaly"].sum()))
        return result_df


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    predictor = AnomalyPredictor()

    sample_normal = {
        "latency_ms": 12.5,
        "packet_loss_pct": 0.0,
        "cpu_pct": 32.0,
        "memory_pct": 42.0,
        "bandwidth_mbps": 45.0,
        "interface_up": 1,
        "error_count": 0
    }
    sample_anomaly = {
        "latency_ms": 220.0,
        "packet_loss_pct": 18.5,
        "cpu_pct": 91.0,
        "memory_pct": 82.0,
        "bandwidth_mbps": 96.0,
        "interface_up": 1,
        "error_count": 45
    }

    print("\n--- Testing AnomalyPredictor ---")
    print("Normal Sample Evaluation:")
    print(predictor.predict(sample_normal))
    print("\nAnomalous Sample Evaluation:")
    print(predictor.predict(sample_anomaly))

"""
backend/detection/prediction.py — Failure Predictor (Trend-Based Risk Scoring)

Analyses historical telemetry time-series data to identify rising trends and
assign a 0–100 risk score to each device.  Uses linear regression (numpy.polyfit)
over a configurable sliding window.

IMPORTANT DISCLAIMER
--------------------
All scores produced by this module are **pattern-based risk estimates** derived
from historical slope analysis.  They are NOT calibrated probabilities.  A score
of 80 does not mean there is an 80% chance of failure — it means the current
trend strongly resembles patterns that have preceded failures in the training data.
Treat scores as a prioritisation signal, not a prediction.

Typical usage::

    predictor = FailurePredictor()

    # Analyse trend of a single metric
    trend = predictor.analyze_trend(history, metric_key="latency_ms", window=10)
    print(trend)
    # → {"slope": 4.2, "intercept": 12.0, "projected_next": 54.2, "direction": "rising"}

    # Composite risk score across all monitored metrics
    result = predictor.risk_score("switch-s2", history)
    print(result["risk_score"])   # e.g. 73

    # Batch assessment across all devices
    all_scores = predictor.batch_risk_assessment(all_device_histories)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np  # type: ignore

logger = logging.getLogger(__name__)


class FailurePredictor:
    """
    Trend-based failure risk scorer.

    Attributes:
        DISCLAIMER: Appended to every risk_score output dict to remind
                    callers that scores are heuristic, not calibrated.
        DEFAULT_WINDOW: Default number of history points to include in
                        the linear regression.
    """

    DISCLAIMER: str = (
        "Pattern-based risk estimate — not a calibrated failure probability. "
        "Use as a prioritisation signal only."
    )
    DEFAULT_WINDOW: int = 10

    # Weights for the composite risk formula
    # Must sum to 1.0
    _METRIC_WEIGHTS: Dict[str, float] = {
        "latency_ms": 0.35,
        "packet_loss_pct": 0.35,
        "cpu_pct": 0.20,
        "memory_pct": 0.10,
    }

    # Normal upper bounds used to normalise current values into 0–1
    _NORMAL_MAX: Dict[str, float] = {
        "latency_ms": 150.0,
        "packet_loss_pct": 10.0,
        "cpu_pct": 100.0,
        "memory_pct": 100.0,
    }

    # ------------------------------------------------------------------ #
    # Trend analysis                                                       #
    # ------------------------------------------------------------------ #

    def analyze_trend(
        self,
        device_metrics_history: List[Dict[str, Any]],
        metric_key: str = "latency_ms",
        window: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Fit a linear regression over the last *window* values of *metric_key*
        and return slope, intercept, projected next value, and trend direction.

        Args:
            device_metrics_history: List of metric dicts ordered oldest → newest.
            metric_key:             Name of the metric to analyse.
            window:                 Number of recent data points to use.
                                    Defaults to DEFAULT_WINDOW.

        Returns:
            Dict with keys:
                - metric_key (str)
                - window_size (int) — actual number of points used
                - slope (float) — rate of change per time-step
                - intercept (float) — y-intercept of the fitted line
                - projected_next_value (float) — extrapolated value at t+1
                - trend_direction (str) — "rising" | "falling" | "stable"
                - r_squared (float) — goodness of fit (0.0 – 1.0)
                - disclaimer (str)
        """
        window = window or self.DEFAULT_WINDOW

        values = [
            float(point[metric_key])
            for point in device_metrics_history
            if metric_key in point
        ]

        if not values:
            return {
                "metric_key": metric_key,
                "window_size": 0,
                "slope": 0.0,
                "intercept": 0.0,
                "projected_next_value": 0.0,
                "trend_direction": "stable",
                "r_squared": 0.0,
                "disclaimer": self.DISCLAIMER,
            }

        # Take the most recent `window` values
        values = values[-window:]
        n = len(values)

        x = np.arange(n, dtype=float)
        y = np.array(values, dtype=float)

        # Fit degree-1 polynomial (linear)
        coeffs = np.polyfit(x, y, deg=1)
        slope = float(coeffs[0])
        intercept = float(coeffs[1])

        projected_next = slope * n + intercept

        # R² score
        y_pred = slope * x + intercept
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Classify direction: threshold = 0.5 units per step
        STABLE_THRESHOLD = 0.5
        if slope > STABLE_THRESHOLD:
            direction = "rising"
        elif slope < -STABLE_THRESHOLD:
            direction = "falling"
        else:
            direction = "stable"

        logger.debug(
            "Trend for metric=%s: slope=%.4f, dir=%s, r²=%.3f over %d points.",
            metric_key, slope, direction, r_squared, n,
        )

        return {
            "metric_key": metric_key,
            "window_size": n,
            "slope": round(slope, 6),
            "intercept": round(intercept, 4),
            "projected_next_value": round(float(projected_next), 4),
            "trend_direction": direction,
            "r_squared": round(r_squared, 4),
            "disclaimer": self.DISCLAIMER,
        }

    # ------------------------------------------------------------------ #
    # Composite risk score                                                 #
    # ------------------------------------------------------------------ #

    def risk_score(
        self,
        device_id: str,
        metrics_history: List[Dict[str, Any]],
        window: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Compute a 0–100 composite risk score for a single device.

        Score formula::

            base_score     = Σ weight[m] * min(1, current_value[m] / normal_max[m])
            trend_penalty  = Σ weight[m] * penalty(slope[m])
            risk_score     = clip((base_score + trend_penalty) * 100, 0, 100)

        where penalty(slope) adds up to 0.30 for a steeply rising metric.

        Args:
            device_id:       Identifier of the device (included in output dict).
            metrics_history: List of metric dicts, oldest → newest.
            window:          Regression window size (defaults to DEFAULT_WINDOW).

        Returns:
            Dict with keys:
                - device_id, risk_score (int 0-100), contributing_factors,
                  per_metric_trends, disclaimer, timestamp.
        """
        window = window or self.DEFAULT_WINDOW

        if not metrics_history:
            return {
                "device_id": device_id,
                "risk_score": 0,
                "contributing_factors": [],
                "per_metric_trends": {},
                "disclaimer": self.DISCLAIMER,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        latest = metrics_history[-1]
        base_score = 0.0
        trend_penalty = 0.0
        contributing_factors: List[str] = []
        per_metric_trends: Dict[str, Any] = {}

        for metric, weight in self._METRIC_WEIGHTS.items():
            # --- Current value component ---
            current = float(latest.get(metric, 0.0))
            normal_max = self._NORMAL_MAX.get(metric, 100.0)
            normalised = min(1.0, current / normal_max)
            base_score += weight * normalised

            # --- Trend component ---
            trend = self.analyze_trend(metrics_history, metric_key=metric, window=window)
            per_metric_trends[metric] = trend
            slope = trend["slope"]

            # Penalty: rising slope earns up to 0.30 extra (saturates at slope=10.0)
            if slope > 0:
                penalty = weight * min(0.30, slope / 10.0 * 0.30)
                trend_penalty += penalty
                if penalty > 0.02:  # only report meaningful contributors
                    contributing_factors.append(
                        f"{metric}: rising trend (slope={slope:.3f}/step), "
                        f"current={current:.1f}, penalty=+{penalty:.3f}"
                    )
            elif trend["trend_direction"] == "rising":
                contributing_factors.append(
                    f"{metric}: elevated (current={current:.1f} / max={normal_max:.0f})"
                )

        # Combine and scale to 0–100
        combined = base_score + trend_penalty
        score_int = int(round(min(100.0, max(0.0, combined * 100))))

        logger.info(
            "Risk score for %s: %d/100 (base=%.3f, trend_penalty=%.3f)",
            device_id, score_int, base_score, trend_penalty,
        )

        return {
            "device_id": device_id,
            "risk_score": score_int,
            "contributing_factors": contributing_factors,
            "per_metric_trends": per_metric_trends,
            "disclaimer": self.DISCLAIMER,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #
    # Batch assessment                                                     #
    # ------------------------------------------------------------------ #

    def batch_risk_assessment(
        self,
        all_device_histories: Dict[str, List[Dict[str, Any]]],
        window: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute risk scores for all devices and return them sorted by
        risk_score descending (highest risk first).

        Args:
            all_device_histories: {device_id: [metrics_dict, ...]} mapping.
            window:               Regression window (defaults to DEFAULT_WINDOW).

        Returns:
            List of risk_score dicts sorted descending by risk_score.
        """
        results: List[Dict[str, Any]] = []
        for device_id, history in all_device_histories.items():
            result = self.risk_score(device_id, history, window=window)
            results.append(result)

        results.sort(key=lambda r: -r["risk_score"])
        logger.info(
            "Batch assessment complete: %d devices. Top risk: %s=%d",
            len(results),
            results[0]["device_id"] if results else "N/A",
            results[0]["risk_score"] if results else 0,
        )
        return results


# ---------------------------------------------------------------------------
# Example / smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
    import random

    predictor = FailurePredictor()

    print("=" * 60)
    print("DEMO 1: Trend analysis — rising latency series")
    print("=" * 60)

    # Simulate rising latency: starts at 10ms, increases ~5ms per step + noise
    rising_history = [
        {"latency_ms": 10 + i * 5 + random.uniform(-2, 2),
         "packet_loss_pct": max(0, i * 0.3 + random.uniform(-0.1, 0.1)),
         "cpu_pct": 30 + i * 2.5 + random.uniform(-3, 3),
         "memory_pct": 50.0 + i * 1.0}
        for i in range(15)
    ]

    trend = predictor.analyze_trend(rising_history, metric_key="latency_ms", window=10)
    print(f"  Metric:    {trend['metric_key']}")
    print(f"  Slope:     {trend['slope']:.3f} ms/step")
    print(f"  Direction: {trend['trend_direction']}")
    print(f"  Projected: {trend['projected_next_value']:.1f} ms (next sample)")
    print(f"  R²:        {trend['r_squared']:.3f}")

    print()
    print("=" * 60)
    print("DEMO 2: Risk score — device with rising trends")
    print("=" * 60)

    result = predictor.risk_score("switch-s2", rising_history, window=10)
    print(f"  Device:  {result['device_id']}")
    print(f"  Score:   {result['risk_score']} / 100")
    print(f"  Factors:")
    for factor in result["contributing_factors"]:
        print(f"    • {factor}")
    print(f"  Note: {result['disclaimer']}")

    print()
    print("=" * 60)
    print("DEMO 3: Batch assessment — 3 devices")
    print("=" * 60)

    # Stable device
    stable_history = [
        {"latency_ms": 7 + random.uniform(-1, 1),
         "packet_loss_pct": 0.1 + random.uniform(0, 0.1),
         "cpu_pct": 35 + random.uniform(-5, 5),
         "memory_pct": 50.0 + random.uniform(-2, 2)}
        for _ in range(15)
    ]

    # Critical device
    critical_history = [
        {"latency_ms": 180 + i * 15 + random.uniform(-5, 5),
         "packet_loss_pct": 10 + i * 2 + random.uniform(0, 1),
         "cpu_pct": 85 + i * 1.5 + random.uniform(-2, 2),
         "memory_pct": 70 + i * 2}
        for i in range(15)
    ]

    all_histories = {
        "switch-s1": stable_history,
        "switch-s2": rising_history,
        "switch-s3": critical_history,
    }

    batch = predictor.batch_risk_assessment(all_histories, window=10)
    for rank, r in enumerate(batch, 1):
        bar = "█" * (r["risk_score"] // 5) + "░" * (20 - r["risk_score"] // 5)
        print(f"  #{rank} {r['device_id']:15s} [{bar}] {r['risk_score']:3d}/100")

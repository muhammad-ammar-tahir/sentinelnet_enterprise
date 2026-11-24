"""backend/detection/fault_detection.py — Fault Detector (Combined Rules + ML).

Combines deterministic threshold rules with the trained Isolation Forest
anomaly detector to detect network faults. Merges and deduplicates signals.
"""

import logging
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.detection.anomaly_detection import AnomalyDetector, FeatureValidationError, ModelNotFoundError

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class Fault:
    """Represents a single detected fault event."""
    fault_type: str          # e.g. LINK_DOWN | PACKET_LOSS_CRITICAL | CONGESTION | anomaly
    target_id: str           # device or link identifier
    severity: str            # critical | warning | info
    confidence: float        # 0.0 – 1.0
    reason: str              # human-readable explanation
    source: str = "rule"     # "rule" or "ml"
    model_version: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    telemetry_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fault_type": self.fault_type,
            "target_id": self.target_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
            "model_version": self.model_version,
            "timestamp": self.timestamp,
            "telemetry_snapshot": self.telemetry_snapshot,
        }


class FaultDetector:
    """Detects network faults by combining threshold-based rules with the trained ML AnomalyDetector."""

    LATENCY_WARNING_MS: float = 150.0
    LATENCY_CRITICAL_MS: float = 300.0
    PACKET_LOSS_WARNING_PCT: float = 5.0
    PACKET_LOSS_LINK_DOWN_PCT: float = 95.0
    CPU_WARNING_PCT: float = 85.0
    CPU_CRITICAL_PCT: float = 95.0
    BANDWIDTH_CONGESTION_PCT: float = 85.0
    BANDWIDTH_CAPACITY_MBPS: float = 100.0

    def __init__(self, anomaly_detector: Optional[AnomalyDetector] = None):
        if anomaly_detector is not None:
            self.anomaly_detector = anomaly_detector
        else:
            try:
                self.anomaly_detector = AnomalyDetector()
            except Exception as e:
                logger.error("Could not load AnomalyDetector: %s. ML detection disabled.", e)
                self.anomaly_detector = None

    def _check_thresholds(self, target_id: str, metrics: Dict[str, Any]) -> List[Fault]:
        """Evaluate deterministic threshold rules against metrics with honest null handling."""
        faults: List[Fault] = []
        snapshot = dict(metrics)

        # 1. Interface Down
        iface_up = metrics.get("interface_up")
        if iface_up is not None and (iface_up == 0 or iface_up is False):
            faults.append(Fault(
                fault_type="INTERFACE_DOWN",
                target_id=target_id,
                severity="critical",
                confidence=1.0,
                reason=f"Interface on {target_id} is down (interface_up=0).",
                source="rule",
                telemetry_snapshot=snapshot,
            ))
            return faults

        # 2. Total Link Down (loss >= 95%)
        raw_loss = metrics.get("packet_loss_pct")
        if raw_loss is not None:
            loss = float(raw_loss)
            if loss >= self.PACKET_LOSS_LINK_DOWN_PCT:
                faults.append(Fault(
                    fault_type="LINK_DOWN",
                    target_id=target_id,
                    severity="critical",
                    confidence=1.0,
                    reason=f"Complete link loss of {loss:.1f}% on {target_id}.",
                    source="rule",
                    telemetry_snapshot=snapshot,
                ))
                return faults

            # 3. Critical Packet Loss (> 5%)
            if loss > self.PACKET_LOSS_WARNING_PCT:
                faults.append(Fault(
                    fault_type="PACKET_LOSS_CRITICAL",
                    target_id=target_id,
                    severity="critical" if loss > 20.0 else "warning",
                    confidence=0.92,
                    reason=f"Packet loss of {loss:.1f}% on {target_id} exceeds SLA threshold.",
                    source="rule",
                    telemetry_snapshot=snapshot,
                ))

        # 4. Latency
        raw_lat = metrics.get("latency_ms")
        if raw_lat is not None:
            latency = float(raw_lat)
            if latency >= self.LATENCY_CRITICAL_MS:
                faults.append(Fault(
                    fault_type="HIGH_LATENCY",
                    target_id=target_id,
                    severity="critical",
                    confidence=0.90,
                    reason=f"Round-trip latency of {latency:.1f}ms exceeds critical threshold.",
                    source="rule",
                    telemetry_snapshot=snapshot,
                ))
            elif latency >= self.LATENCY_WARNING_MS:
                faults.append(Fault(
                    fault_type="HIGH_LATENCY",
                    target_id=target_id,
                    severity="warning",
                    confidence=0.85,
                    reason=f"Latency of {latency:.1f}ms exceeds warning threshold.",
                    source="rule",
                    telemetry_snapshot=snapshot,
                ))

        # 5. CPU Overload (skipped for links or when null)
        raw_cpu = metrics.get("cpu_pct")
        if raw_cpu is not None:
            cpu = float(raw_cpu)
            if cpu >= self.CPU_CRITICAL_PCT:
                faults.append(Fault(
                    fault_type="CPU_OVERLOAD",
                    target_id=target_id,
                    severity="critical",
                    confidence=0.93,
                    reason=f"Critical CPU utilization of {cpu:.1f}% on {target_id}.",
                    source="rule",
                    telemetry_snapshot=snapshot,
                ))
            elif cpu >= self.CPU_WARNING_PCT:
                faults.append(Fault(
                    fault_type="CPU_OVERLOAD",
                    target_id=target_id,
                    severity="warning",
                    confidence=0.88,
                    reason=f"Elevated CPU utilization of {cpu:.1f}% on {target_id}.",
                    source="rule",
                    telemetry_snapshot=snapshot,
                ))

        # 6. Congestion: computed ONLY from real throughput vs configured capacity
        bw = metrics.get("bandwidth_mbps")
        cap = metrics.get("capacity_mbps", self.BANDWIDTH_CAPACITY_MBPS)

        if bw is None or cap is None or float(cap) <= 0.0:
            logger.info("Insufficient data for congestion check on %s (bw=%s, capacity=%s)", target_id, bw, cap)
        else:
            util = (float(bw) / float(cap)) * 100.0
            if util >= self.BANDWIDTH_CONGESTION_PCT:
                faults.append(Fault(
                    fault_type="CONGESTION",
                    target_id=target_id,
                    severity="warning",
                    confidence=0.80,
                    reason=f"Bandwidth utilization {util:.1f}% (measured {bw} Mbps / capacity {cap} Mbps) on {target_id} exceeds threshold.",
                    source="rule",
                    telemetry_snapshot=snapshot,
                ))

        return faults

    def _deduplicate(self, faults: List[Fault]) -> List[Fault]:
        """Merge rule and ML faults: If both rule and ML fired, elevate confidence and annotate reason."""
        if not faults:
            return []

        rule_faults = [f for f in faults if f.source == "rule"]
        ml_faults = [f for f in faults if f.source == "ml"]

        # If rule faults exist, merge ML corroboration into them
        if rule_faults and ml_faults:
            ml_fault = ml_faults[0]
            for rf in rule_faults:
                rf.confidence = min(1.0, rf.confidence + 0.05)
                rf.reason += f" (Corroborated by Isolation Forest model {ml_fault.model_version})"
            # Return rule faults with elevated confidence
            merged = rule_faults
        else:
            merged = faults

        # Sort: critical first, then warning
        merged.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), -f.confidence))
        return merged

    def detect(self, target_id: str, metrics: Dict[str, Any]) -> List[Fault]:
        """Combine deterministic rules with ML anomaly detection.

        1. Evaluates fast rule-based thresholds
        2. Evaluates real IsolationForest anomaly inference
        3. Deduplicates and merges corroborating signals
        """
        faults: List[Fault] = []

        # 1. Rule-based checks
        rule_faults = self._check_thresholds(target_id, metrics)
        faults.extend(rule_faults)

        # 2. ML-based anomaly prediction (using real model)
        ml_features = ["latency_ms", "packet_loss_pct", "cpu_pct", "memory_pct", "bandwidth_mbps", "interface_up", "error_count"]
        missing_ml = [f for f in ml_features if metrics.get(f) is None]

        if missing_ml:
            logger.info("ML inference skipped: missing features %s for %s", missing_ml, target_id)
        elif self.anomaly_detector:
            try:
                ml_res = self.anomaly_detector.predict(metrics)
                if ml_res.get("is_anomaly"):
                    faults.append(Fault(
                        fault_type="anomaly",
                        target_id=target_id,
                        severity="warning" if ml_res["confidence"] < 0.85 else "critical",
                        confidence=ml_res["confidence"],
                        reason=(
                            f"Isolation Forest flagged statistical anomaly (score={ml_res['anomaly_score']}, "
                            f"confidence={ml_res['confidence']})"
                        ),
                        source="ml",
                        model_version=ml_res["model_version"],
                        telemetry_snapshot=dict(metrics)
                    ))
            except FeatureValidationError as fve:
                logger.warning("ML prediction skipped due to missing features for %s: %s", target_id, fve)
            except Exception as ml_err:
                logger.error("ML prediction error for %s: %s", target_id, ml_err)

        # 3. Deduplicate
        return self._deduplicate(faults)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    fd = FaultDetector()

    sample_normal = {
        "latency_ms": 10.0,
        "packet_loss_pct": 0.0,
        "cpu_pct": 25.0,
        "memory_pct": 30.0,
        "bandwidth_mbps": 40.0,
        "interface_up": 1,
        "error_count": 0
    }
    print("Normal test:", fd.detect("s1", sample_normal))

    sample_anomaly = {
        "latency_ms": 250.0,
        "packet_loss_pct": 25.0,
        "cpu_pct": 96.0,
        "memory_pct": 85.0,
        "bandwidth_mbps": 95.0,
        "interface_up": 1,
        "error_count": 500
    }
    print("Anomaly test:", fd.detect("s2", sample_anomaly))

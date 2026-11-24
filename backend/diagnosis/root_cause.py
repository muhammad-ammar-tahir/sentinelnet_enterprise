"""
backend/diagnosis/root_cause.py — Diagnosis Engine (Root-Cause Analysis)

Takes a detected Fault plus the surrounding network context (neighbor metrics,
topology state, historical fault list) and produces ranked hypotheses explaining
the most likely root cause.

Design
------
Each hypothesis type (congestion, link_degradation, device_overload, server_slow,
unknown) has a dedicated scoring function that assigns a confidence value from 0.0
to 1.0 based on matching evidence signals.  All hypothesis scores are computed
independently, then sorted descending.  The caller receives a list of Hypothesis
objects with supporting and contradicting evidence lists for display in the UI.

The ``explain()`` method converts a Hypothesis into a natural-language string
using template substitution — no LLM is required.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Hypothesis:
    """A ranked root-cause hypothesis returned by DiagnosisEngine.diagnose()."""

    hypothesis: str                        # congestion | link_degradation | device_overload | server_slow | unknown
    confidence: float                      # 0.0 – 1.0
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "confidence": round(self.confidence, 4),
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Diagnosis Engine
# ---------------------------------------------------------------------------

class DiagnosisEngine:
    """
    Multi-signal root-cause analysis engine.

    Usage::

        engine = DiagnosisEngine()

        fault = {
            "fault_type": "PACKET_LOSS_CRITICAL",
            "target_id": "switch-s2",
            "severity": "critical",
            "confidence": 0.92,
            "reason": "Packet loss of 28.5%...",
        }

        context = {
            "neighbor_metrics": {
                "switch-s1": {"cpu_pct": 45.0, "bandwidth_mbps": 20.0, "latency_ms": 8.0},
                "switch-s3": {"cpu_pct": 72.0, "bandwidth_mbps": 88.0, "latency_ms": 90.0},
            },
            "topology_state": {
                "total_links": 3,
                "active_links": 2,
                "failed_links": ["s2-s3"],
            },
            "history": [
                {"fault_type": "HIGH_LATENCY", "target_id": "switch-s2", "timestamp": "..."},
            ],
        }

        hypotheses = engine.diagnose(fault, context)
        for h in hypotheses:
            print(engine.explain(h))
    """

    # Human-readable templates for each hypothesis type.
    # Keyword arguments are filled from fault + context signals.
    HYPOTHESIS_TEMPLATES: Dict[str, str] = {
        "congestion": (
            "High bandwidth utilization ({bw:.1f} Mbps, ~{util:.0f}% of link capacity) "
            "combined with elevated latency ({lat:.1f} ms) on {target} indicates TCP buffer "
            "congestion. The SDN controller should reroute traffic to an underutilised backup "
            "path to restore SLA within the sub-second recovery target."
        ),
        "link_degradation": (
            "Persistent packet loss ({loss:.1f}%) with error counter elevation ({errors} errors) "
            "on {target} indicates physical-layer degradation — likely a flapping optical "
            "connector, cable fault, or transceiver bit-error-rate threshold breach. "
            "Recommend physical inspection and OpenFlow link-down event correlation."
        ),
        "device_overload": (
            "CPU utilisation at {cpu:.1f}% on switch {target} has caused control-plane queuing "
            "delays. The device is unable to process OpenFlow PacketIn messages at line rate, "
            "leading to flow-table misses and reactive packet flooding. Consider redistributing "
            "flow-table entries or upgrading the datapath ASIC."
        ),
        "server_slow": (
            "Round-trip latency is elevated only at destination {target} ({lat:.1f} ms), "
            "while upstream switch metrics remain nominal. This asymmetric pattern suggests "
            "server-side processing delay, TCP socket backlog saturation, or application-layer "
            "slow response rather than a network path issue."
        ),
        "unknown": (
            "Multiple anomalous signals are present on {target} but no single hypothesis "
            "dominates with high confidence. Manual investigation is recommended. "
            "Consider capturing a packet trace on the affected segment and reviewing "
            "switch syslog entries for recent configuration changes."
        ),
    }

    # Thresholds used by scoring functions
    _BW_CONGESTION_MBPS = 80.0      # above = congestion signal
    _BW_CAPACITY_MBPS = 100.0
    _LATENCY_HIGH_MS = 50.0         # above = latency signal
    _CPU_HIGH_PCT = 80.0            # above = device overload signal
    _LOSS_LINK_DEG_PCT = 3.0        # above = link degradation signal
    _ERROR_HIGH = 50                 # above = link degradation signal

    # ------------------------------------------------------------------ #
    # Scoring helpers (each returns: confidence, supporting[], contradicting[])
    # ------------------------------------------------------------------ #

    def _score_congestion(
        self,
        fault: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Tuple[float, List[str], List[str]]:
        """Score the 'congestion' hypothesis."""
        supporting: List[str] = []
        contradicting: List[str] = []
        score = 0.0

        metrics = fault.get("telemetry_snapshot", {})
        bw = float(metrics.get("bandwidth_mbps", 0.0))
        lat = float(metrics.get("latency_ms", 0.0))
        loss = float(metrics.get("packet_loss_pct", 0.0))

        # High bandwidth
        if bw >= self._BW_CONGESTION_MBPS:
            score += 0.35
            supporting.append(
                f"Bandwidth {bw:.1f} Mbps ≥ {self._BW_CONGESTION_MBPS:.0f} Mbps threshold."
            )
        else:
            contradicting.append(
                f"Bandwidth {bw:.1f} Mbps is below congestion threshold — link not saturated."
            )

        # High latency co-occurring with high bandwidth
        if lat >= self._LATENCY_HIGH_MS and bw >= self._BW_CONGESTION_MBPS:
            score += 0.30
            supporting.append(
                f"Latency {lat:.1f} ms is elevated alongside high bandwidth — classic "
                "queuing-delay signature."
            )

        # Fault type bonus
        if fault.get("fault_type") in ("CONGESTION", "HIGH_LATENCY"):
            score += 0.20
            supporting.append(
                f"Primary fault is {fault['fault_type']}, directly aligns with congestion."
            )

        # Low loss is consistent with congestion (not a link break)
        if loss < 5.0:
            score += 0.10
            supporting.append(
                "Packet loss is low — indicates buffer overflow drops, not link failure."
            )
        elif loss > 20.0:
            score -= 0.15
            contradicting.append(
                f"Loss {loss:.1f}% is too high for pure congestion — more likely link fault."
            )

        # Neighbor congestion correlation
        neighbor_metrics = context.get("neighbor_metrics", {})
        congested_neighbors = [
            dev for dev, m in neighbor_metrics.items()
            if float(m.get("bandwidth_mbps", 0)) >= self._BW_CONGESTION_MBPS
        ]
        if congested_neighbors:
            score += 0.10
            supporting.append(
                f"Neighbouring devices also show high bandwidth: {', '.join(congested_neighbors)}."
            )

        return max(0.0, min(1.0, score)), supporting, contradicting

    def _score_link_degradation(
        self,
        fault: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Tuple[float, List[str], List[str]]:
        """Score the 'link_degradation' hypothesis."""
        supporting: List[str] = []
        contradicting: List[str] = []
        score = 0.0

        metrics = fault.get("telemetry_snapshot", {})
        loss = float(metrics.get("packet_loss_pct", 0.0))
        errors = int(metrics.get("error_count", 0))
        lat = float(metrics.get("latency_ms", 0.0))
        bw = float(metrics.get("bandwidth_mbps", 0.0))

        # Packet loss is the primary signal
        if loss >= self._LOSS_LINK_DEG_PCT:
            score += 0.35
            supporting.append(
                f"Packet loss {loss:.1f}% ≥ {self._LOSS_LINK_DEG_PCT:.0f}% — "
                "consistent with bit-error-rate elevation on a physical link."
            )
        else:
            contradicting.append(
                f"Packet loss only {loss:.1f}% — insufficient to suggest link degradation."
            )

        # Error counter elevation
        if errors >= self._ERROR_HIGH:
            score += 0.25
            supporting.append(
                f"Error count {errors} ≥ {self._ERROR_HIGH} — hardware-level errors detected."
            )
        elif errors > 0:
            score += 0.10
            supporting.append(f"Non-zero error count ({errors}) observed.")

        # Fault type bonus
        if fault.get("fault_type") in ("LINK_DOWN", "PACKET_LOSS_CRITICAL", "INTERFACE_DOWN"):
            score += 0.20
            supporting.append(
                f"Fault type '{fault['fault_type']}' strongly matches link degradation pattern."
            )

        # Historical faults on same target
        history = context.get("history", [])
        target = fault.get("target_id", "")
        recurring = [h for h in history if h.get("target_id") == target]
        if recurring:
            score += 0.15
            supporting.append(
                f"Found {len(recurring)} prior fault(s) on {target} — recurring pattern "
                "suggests persistent hardware issue."
            )

        # High bandwidth contradicts link being physically broken
        if bw > 50.0 and loss < 10.0:
            score -= 0.10
            contradicting.append(
                f"Traffic is still flowing ({bw:.1f} Mbps) — link is not fully broken."
            )

        topology = context.get("topology_state", {})
        if fault.get("target_id") in topology.get("failed_links", []):
            score += 0.20
            supporting.append(
                "Topology state confirms this link is in a failed state."
            )

        return max(0.0, min(1.0, score)), supporting, contradicting

    def _score_device_overload(
        self,
        fault: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Tuple[float, List[str], List[str]]:
        """Score the 'device_overload' hypothesis."""
        supporting: List[str] = []
        contradicting: List[str] = []
        score = 0.0

        metrics = fault.get("telemetry_snapshot", {})
        cpu = float(metrics.get("cpu_pct", 0.0))
        mem = float(metrics.get("memory_pct", 0.0))
        lat = float(metrics.get("latency_ms", 0.0))

        # CPU is the primary signal
        if cpu >= self._CPU_HIGH_PCT:
            score += 0.40
            supporting.append(
                f"CPU at {cpu:.1f}% — control plane is overloaded; "
                "flow-table lookups will be delayed."
            )
        elif cpu >= 60.0:
            score += 0.15
            supporting.append(f"CPU elevated at {cpu:.1f}% — heading toward overload.")
        else:
            contradicting.append(
                f"CPU at {cpu:.1f}% — insufficient to cause device overload."
            )

        # Memory pressure
        if mem >= 85.0:
            score += 0.20
            supporting.append(
                f"Memory at {mem:.1f}% — risk of control-plane OOM and flow-table eviction."
            )

        # Fault type
        if fault.get("fault_type") == "CPU_OVERLOAD":
            score += 0.25
            supporting.append("Primary fault is CPU_OVERLOAD — directly matches hypothesis.")

        # Latency alone on a device with high CPU
        if lat >= self._LATENCY_HIGH_MS and cpu >= self._CPU_HIGH_PCT:
            score += 0.15
            supporting.append(
                f"Co-occurrence of CPU overload ({cpu:.1f}%) and high latency ({lat:.1f} ms) "
                "is the classic control-plane queuing signature."
            )

        return max(0.0, min(1.0, score)), supporting, contradicting

    def _score_server_slow(
        self,
        fault: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Tuple[float, List[str], List[str]]:
        """Score the 'server_slow' hypothesis."""
        supporting: List[str] = []
        contradicting: List[str] = []
        score = 0.0

        metrics = fault.get("telemetry_snapshot", {})
        lat = float(metrics.get("latency_ms", 0.0))
        cpu = float(metrics.get("cpu_pct", 0.0))
        loss = float(metrics.get("packet_loss_pct", 0.0))
        target = fault.get("target_id", "")

        # Elevated latency at target
        if lat >= self._LATENCY_HIGH_MS:
            score += 0.30
            supporting.append(
                f"Latency {lat:.1f} ms is elevated at {target}."
            )

        # Neighbours are healthy — isolates the fault to this device
        neighbor_metrics = context.get("neighbor_metrics", {})
        healthy_neighbors = [
            dev for dev, m in neighbor_metrics.items()
            if float(m.get("latency_ms", 0)) < self._LATENCY_HIGH_MS
            and float(m.get("cpu_pct", 0)) < self._CPU_HIGH_PCT
        ]
        if healthy_neighbors:
            score += 0.35
            supporting.append(
                f"Neighbouring devices are healthy ({', '.join(healthy_neighbors)}), "
                "isolating the fault to this endpoint."
            )
        else:
            contradicting.append(
                "Neighbours also show degraded metrics — fault is network-wide, not server-local."
            )

        # Low CPU on target despite high latency → server app is the bottleneck
        if lat >= self._LATENCY_HIGH_MS and cpu < 40.0:
            score += 0.20
            supporting.append(
                f"Low CPU ({cpu:.1f}%) with high latency suggests application-layer "
                "slow response (not compute overload)."
            )

        # Low loss is consistent with server-side delay
        if loss < 2.0:
            score += 0.10
            supporting.append(
                f"Minimal packet loss ({loss:.1f}%) — network path is intact; "
                "delay is at the server."
            )

        # 'server' device type bonus
        # (target_id naming convention: "server-" prefix)
        if "server" in target.lower():
            score += 0.10
            supporting.append(
                f"Target '{target}' appears to be a server endpoint by naming convention."
            )

        return max(0.0, min(1.0, score)), supporting, contradicting

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def diagnose(
        self,
        fault: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Hypothesis]:
        """
        Score all hypotheses and return them ranked by confidence.

        Args:
            fault:   A fault dict (as returned by FaultDetector.detect()[n].to_dict()).
                     Required keys: fault_type, target_id; Optional: telemetry_snapshot.
            context: Dict with optional keys:
                       - neighbor_metrics: {device_id: metrics_dict}
                       - topology_state: {active_links, failed_links, ...}
                       - history: [fault_dict, ...]

        Returns:
            List of Hypothesis objects, sorted descending by confidence.
            Only hypotheses with confidence > 0.05 are returned.
        """
        if context is None:
            context = {}

        scorers = {
            "congestion": self._score_congestion,
            "link_degradation": self._score_link_degradation,
            "device_overload": self._score_device_overload,
            "server_slow": self._score_server_slow,
        }

        hypotheses: List[Hypothesis] = []

        for hyp_name, scorer in scorers.items():
            try:
                confidence, supporting, contradicting = scorer(fault, context)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Scorer %s raised: %s", hyp_name, exc)
                continue

            if confidence > 0.05:
                hypotheses.append(Hypothesis(
                    hypothesis=hyp_name,
                    confidence=confidence,
                    supporting_evidence=supporting,
                    contradicting_evidence=contradicting,
                ))

        # Sort descending by confidence
        hypotheses.sort(key=lambda h: -h.confidence)

        # Always append an 'unknown' fallback if top confidence < 0.4
        top_conf = hypotheses[0].confidence if hypotheses else 0.0
        if top_conf < 0.40:
            hypotheses.append(Hypothesis(
                hypothesis="unknown",
                confidence=max(0.0, 0.40 - top_conf),
                supporting_evidence=["No single hypothesis reached high confidence."],
                contradicting_evidence=[],
            ))

        logger.info(
            "DiagnosisEngine ranked %d hypothesis/ses for target=%s: %s",
            len(hypotheses),
            fault.get("target_id", "?"),
            [(h.hypothesis, round(h.confidence, 2)) for h in hypotheses],
        )

        return hypotheses

    def explain(self, hypothesis: Hypothesis, fault: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate a human-readable explanation for a hypothesis.

        Args:
            hypothesis: A Hypothesis returned by diagnose().
            fault:      Optional original fault dict for richer template substitution.

        Returns:
            A multi-sentence explanation string.
        """
        template = self.HYPOTHESIS_TEMPLATES.get(
            hypothesis.hypothesis, self.HYPOTHESIS_TEMPLATES["unknown"]
        )

        # Build substitution kwargs with safe defaults
        metrics = (fault or {}).get("telemetry_snapshot", {})
        target = (fault or {}).get("target_id", "the affected device")

        try:
            explanation = template.format(
                target=target,
                bw=float(metrics.get("bandwidth_mbps", 0.0)),
                util=(float(metrics.get("bandwidth_mbps", 0.0)) / 100.0) * 100,
                lat=float(metrics.get("latency_ms", 0.0)),
                loss=float(metrics.get("packet_loss_pct", 0.0)),
                cpu=float(metrics.get("cpu_pct", 0.0)),
                errors=int(metrics.get("error_count", 0)),
            )
        except (KeyError, ValueError) as exc:
            logger.debug("Template substitution partial failure: %s", exc)
            explanation = template.format_map(
                {
                    "target": target,
                    "bw": 0.0,
                    "util": 0.0,
                    "lat": 0.0,
                    "loss": 0.0,
                    "cpu": 0.0,
                    "errors": 0,
                }
            )

        return explanation


# ---------------------------------------------------------------------------
# Example / smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")

    engine = DiagnosisEngine()

    fault = {
        "fault_type": "PACKET_LOSS_CRITICAL",
        "target_id": "switch-s2",
        "severity": "critical",
        "confidence": 0.92,
        "reason": "Packet loss of 28.5% exceeds SLA threshold.",
        "telemetry_snapshot": {
            "latency_ms": 240.0,
            "packet_loss_pct": 28.5,
            "cpu_pct": 42.0,
            "bandwidth_mbps": 18.0,
            "interface_up": 1,
            "error_count": 820,
            "memory_pct": 55.0,
        },
    }

    context = {
        "neighbor_metrics": {
            "switch-s1": {"cpu_pct": 35.0, "bandwidth_mbps": 15.0, "latency_ms": 7.0},
            "switch-s3": {"cpu_pct": 68.0, "bandwidth_mbps": 20.0, "latency_ms": 12.0},
        },
        "topology_state": {
            "total_links": 3,
            "active_links": 2,
            "failed_links": ["switch-s2--switch-s3"],
        },
        "history": [
            {
                "fault_type": "HIGH_LATENCY",
                "target_id": "switch-s2",
                "timestamp": "2024-01-01T10:00:00Z",
            },
            {
                "fault_type": "PACKET_LOSS_CRITICAL",
                "target_id": "switch-s2",
                "timestamp": "2024-01-01T10:05:00Z",
            },
        ],
    }

    print("=" * 70)
    print("DIAGNOSIS REPORT for switch-s2 (packet loss + error counter)")
    print("=" * 70)

    hypotheses = engine.diagnose(fault, context)
    for rank, h in enumerate(hypotheses, 1):
        print(f"\nRank #{rank}: {h.hypothesis.upper()} (confidence={h.confidence:.2f})")
        print(f"  Supporting  : {'; '.join(h.supporting_evidence) or 'none'}")
        print(f"  Contradicting: {'; '.join(h.contradicting_evidence) or 'none'}")
        print(f"  Explanation : {engine.explain(h, fault)}")

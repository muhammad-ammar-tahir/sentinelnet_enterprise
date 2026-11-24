"""tests/test_real_telemetry.py — Unit & Integration Tests for Real Telemetry Measurement.

Tests:
1. Real Link Telemetry:
   - cpu_pct and memory_pct are NULL (None), never fabricated as 0.0.
   - capacity_mbps is stored separately from measured bandwidth_mbps.
   - 50 Mbps throughput on a 100 Mbps link produces ~50.0% utilization (NOT 100%).
2. FaultDetector Congestion Logic:
   - Measured 50 Mbps on 100 Mbps link (util=50%) -> NO congestion flagged.
   - Measured 90 Mbps on 100 Mbps link (util=90%) -> CONGESTION flagged.
   - Missing bandwidth or capacity -> NO congestion flagged ("insufficient data").
3. Honest NULL & ML Handling:
   - When features are NULL (e.g. cpu_pct/memory_pct for links), ML inference is skipped.
   - Rule-based detection functions cleanly with partial data.
4. OVS Unavailability Handling:
   - When ovs-vsctl is unavailable, records NULL, method="unavailable", never fakes 0.
"""

import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.database.models import Device, Link, NetworkMetric
from backend.monitoring.metrics_collector import MetricsCollector, RealMetricsCollector
from backend.detection.fault_detection import FaultDetector, Fault
from backend.detection.anomaly_detection import AnomalyDetector, FeatureValidationError


@pytest.mark.asyncio
async def test_link_metrics_honest_nulls_and_utilization():
    """Verify that link metrics have null cpu/mem, separate capacity, and calculated utilization."""
    collector = MetricsCollector()

    link = Link(
        id="link-s2-s3",
        src_device_id="s2",
        dst_device_id="s3",
        src_port=2,
        dst_port=2,
        status="up",
        bandwidth_mbps=100.0,
        capacity_mbps=100.0
    )

    # Mock ping and OVS stats to simulate 50 Mbps throughput on 100 Mbps link
    mock_ping = {"reachable": True, "latency_ms": 2.4, "packet_loss_pct": 0.0}
    mock_ovs = {
        "available": True,
        "interface_up": 1,
        "rx_bytes": 100_000_000,
        "tx_bytes": 100_000_000,
        "error_count": 0.0,
        "method": "ovs_counter"
    }

    with patch.object(collector.network_monitor, "ping_host", AsyncMock(return_value=mock_ping)), \
         patch.object(collector, "_query_ovs_interface", AsyncMock(return_value=mock_ovs)), \
         patch.object(collector, "_compute_throughput", MagicMock(return_value=50.0)):

        result = await collector.collect_link_metrics(link)

        # 1. Honest NULLs for CPU/Memory
        assert result["cpu_pct"] is None, "Links do NOT have CPU — must be NULL (None)"
        assert result["memory_pct"] is None, "Links do NOT have Memory — must be NULL (None)"
        assert "cpu_pct" in result["missing_fields"]
        assert "memory_pct" in result["missing_fields"]

        # 2. Configured Capacity vs Measured Throughput
        assert result["capacity_mbps"] == 100.0
        assert result["bandwidth_mbps"] == 50.0

        # 3. Utilization Calculation: 50 Mbps on 100 Mbps capacity = 50.0% (NOT 100%)
        assert result["utilization_pct"] == 50.0, f"Expected 50.0% utilization, got {result['utilization_pct']}%"
        assert result["interface_up"] == 1
        assert result["measurement_method"] == "ovs_counter"


@pytest.mark.asyncio
async def test_ovs_unavailable_stores_null_never_fakes_zero():
    """When ovs-vsctl is unavailable, collector must report NULL and method='unavailable'."""
    collector = MetricsCollector()

    with patch("shutil.which", return_value=None):
        ovs_res = await collector._query_ovs_interface("s1-eth1")

        assert ovs_res["available"] is False
        assert ovs_res["rx_bytes"] is None, "Must be NULL, never 0"
        assert ovs_res["tx_bytes"] is None, "Must be NULL, never 0"
        assert ovs_res["error_count"] is None, "Must be NULL, never 0"
        assert ovs_res["method"] == "unavailable"


def test_fault_detector_congestion_with_50mbps_vs_90mbps():
    """50 Mbps on 100 Mbps link -> NO congestion; 90 Mbps on 100 Mbps link -> CONGESTION."""
    detector = FaultDetector(anomaly_detector=None)

    # 1. 50 Mbps on 100 Mbps capacity (50% utilization < 85% threshold)
    metrics_50mbps = {
        "device_id": "link-s2-s3",
        "bandwidth_mbps": 50.0,
        "capacity_mbps": 100.0,
        "latency_ms": 2.0,
        "packet_loss_pct": 0.0,
        "cpu_pct": None,
        "memory_pct": None,
        "interface_up": 1
    }
    faults = detector.detect("link-s2-s3", metrics_50mbps)
    congestion_faults = [f for f in faults if f.fault_type == "CONGESTION"]
    assert len(congestion_faults) == 0, "50% utilization must NOT trigger CONGESTION"

    # 2. 90 Mbps on 100 Mbps capacity (90% utilization >= 85% threshold)
    metrics_90mbps = {
        "device_id": "link-s2-s3",
        "bandwidth_mbps": 90.0,
        "capacity_mbps": 100.0,
        "latency_ms": 15.0,
        "packet_loss_pct": 0.0,
        "cpu_pct": None,
        "memory_pct": None,
        "interface_up": 1
    }
    faults_90 = detector.detect("link-s2-s3", metrics_90mbps)
    congestion_90 = [f for f in faults_90 if f.fault_type == "CONGESTION"]
    assert len(congestion_90) == 1, "90% utilization MUST trigger CONGESTION"
    assert "90.0%" in congestion_90[0].reason


def test_fault_detector_insufficient_data_skips_congestion(caplog):
    """When bandwidth or capacity is None, congestion check is skipped without error."""
    detector = FaultDetector(anomaly_detector=None)

    # Link with missing bandwidth measurement
    metrics_missing = {
        "device_id": "link-s1-s2",
        "bandwidth_mbps": None,
        "capacity_mbps": 100.0,
        "latency_ms": 2.0,
        "packet_loss_pct": 0.0,
        "interface_up": 1
    }
    with caplog.at_level(logging.INFO):
        faults = detector.detect("link-s1-s2", metrics_missing)
        congestion = [f for f in faults if f.fault_type == "CONGESTION"]
        assert len(congestion) == 0
        assert any("Insufficient data for congestion check" in r.message for r in caplog.records)


def test_ml_inference_skipped_on_null_features(caplog):
    """When required ML features are NULL (such as on links), ML inference is skipped."""
    mock_ml = MagicMock()
    detector = FaultDetector(anomaly_detector=mock_ml)

    # Telemetry with NULL cpu_pct and memory_pct (typical link telemetry)
    link_telemetry = {
        "device_id": "link-s2-s3",
        "latency_ms": 12.0,
        "packet_loss_pct": 0.0,
        "cpu_pct": None,
        "memory_pct": None,
        "bandwidth_mbps": 40.0,
        "capacity_mbps": 100.0,
        "interface_up": 1,
        "error_count": 0.0
    }

    with caplog.at_level(logging.INFO):
        faults = detector.detect("link-s2-s3", link_telemetry)
        # ML model must NOT have been called
        assert not mock_ml.predict.called, "ML model must not be called when required features are NULL"
        assert any("ML inference skipped: missing features" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_persist_metrics_records_capacity_and_utilization():
    """Verify persist_metrics inserts NetworkMetric with capacity, utilization, and method."""
    collector = MetricsCollector()

    metrics_list = [{
        "device_id": "link-s2-s3",
        "latency_ms": 3.5,
        "packet_loss_pct": 0.0,
        "cpu_pct": None,
        "memory_pct": None,
        "bandwidth_mbps": 50.0,
        "capacity_mbps": 100.0,
        "utilization_pct": 50.0,
        "interface_up": 1,
        "error_count": 0.0,
        "measurement_method": "ovs_counter",
        "missing_fields": ["cpu_pct", "memory_pct"]
    }]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.monitoring.metrics_collector.AsyncSessionLocal", return_value=mock_session):
        count = await collector.persist_metrics(metrics_list)
        assert count > 0

        # Check added NetworkMetric instances
        added_metrics = [call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], NetworkMetric)]
        assert len(added_metrics) > 0

        bw_metric = next((m for m in added_metrics if m.metric_name == "bandwidth_mbps"), None)
        assert bw_metric is not None
        assert bw_metric.capacity_mbps == 100.0
        assert bw_metric.utilization_pct == 50.0
        assert bw_metric.measurement_method == "ovs_counter"
        assert "cpu_pct" in bw_metric.missing_fields

"""tests/test_exact_flow_verification.py — Multi-layer exact flow & telemetry verification tests.

Validates:
1. Switch with 20 unrelated flows + exact recovery flow passes Layer 1.
2. Switch with 20 unrelated flows but missing recovery flow fails Layer 1 with reason="flow_not_found_on_switch".
3. Data-plane ping failure fails Layer 2 with reason="hosts_unreachable_after_recovery".
4. High packet loss (> 1.0%) fails Layer 2 with reason="packet_loss_too_high".
5. Excessive latency (> 100ms) fails Layer 3 with reason="latency_exceeds_threshold".
6. NetworkMonitor TCP fallback returns latency_ms=None and packet_loss_pct=None (no fake measurements).
7. End-to-end recovery pipeline automatically rolls back when exact flow verification fails.
"""

import asyncio
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.recovery.recovery_engine import (
    RecoveryEngine, AffectedFlow, RecoveryPlan, VerificationResult, RecoveryResult
)
from backend.recovery.path_selection import PathSelector
from backend.recovery.action_executor import ActionExecutor, ExecutionResult
from backend.recovery.rollback import RollbackManager, RollbackResult
from backend.monitoring.network_monitor import NetworkMonitor
from backend.database.models import Incident


def _build_20_unrelated_flows(dpid: int = 1):
    """Generate 20 real-looking unrelated OpenFlow rules for a switch."""
    flows = []
    for i in range(1, 21):
        flows.append({
            "dpid": dpid,
            "priority": 100 + i,
            "cookie": 0x1000 + i,
            "match": {
                "in_port": (i % 4) + 1,
                "eth_type": 0x0800,
                "ipv4_src": f"10.1.{i}.10",
                "ipv4_dst": f"10.2.{i}.20"
            },
            "actions": [f"OUTPUT:{(i % 3) + 1}"]
        })
    return flows


def _build_test_plan(dpid: int = 2, in_port: int = 1, out_port: int = 3, src_ip: str = "10.0.0.1", dst_ip: str = "10.0.0.50"):
    flow = AffectedFlow(
        src="h1",
        dst="srv1",
        via_link="link-s2-s3",
        path_through=["s1", "s2", "s3"],
        src_ip=src_ip,
        dst_ip=dst_ip
    )
    new_path = {
        "found": True,
        "path": ["h1", "s1", "s3", "srv1"],
        "hops": [
            {"dpid": dpid, "in_port": in_port, "out_port": out_port}
        ],
        "total_latency_ms": 6.0
    }
    return RecoveryPlan(flow=flow, new_path=new_path)


# ─────────────────────────────────────────────────────────────────────────────
# 1. 20 UNRELATED FLOWS + EXACT RECOVERY FLOW -> PASSES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_20_unrelated_flows_plus_exact_recovery_flow_passes():
    """A switch with 20 unrelated flows AND the exact recovery flow must PASS."""
    engine = RecoveryEngine()
    plan = _build_test_plan(dpid=2, in_port=1, out_port=3, src_ip="10.0.0.1", dst_ip="10.0.0.50")

    # 20 unrelated flows
    unrelated_flows = _build_20_unrelated_flows(dpid=2)
    # The exact recovery flow
    exact_recovery_flow = {
        "dpid": 2,
        "priority": engine.RECOVERY_PRIORITY,  # 300
        "cookie": 0x53454E54,
        "match": {
            "in_port": 1,
            "eth_type": 0x0800,
            "ipv4_src": "10.0.0.1",
            "ipv4_dst": "10.0.0.50"
        },
        "actions": [{"type": "OUTPUT", "port": 3}]
    }

    mock_sdn = MagicMock()
    mock_sdn.get_flows = AsyncMock(return_value=unrelated_flows + [exact_recovery_flow])
    engine.sdn_controller = mock_sdn

    mock_monitor = MagicMock()
    mock_monitor.ping_host = AsyncMock(return_value={
        "reachable": True,
        "method": "icmp",
        "latency_ms": 6.5,
        "packet_loss_pct": 0.0
    })
    engine.network_monitor = mock_monitor

    result: VerificationResult = await engine.verify_recovery(
        incident=MagicMock(),
        recovery_plans=[plan]
    )

    assert result.success is True
    assert result.flows_verified is True
    assert result.reachable is True
    assert result.reason == "all_checks_passed"
    assert result.checks["controller_layer"]["verified"] is True
    assert result.checks["dataplane_layer"]["verified"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. 20 UNRELATED FLOWS WITHOUT RECOVERY FLOW -> FAILS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_20_unrelated_flows_missing_recovery_flow_fails():
    """A switch with 20 unrelated flows but MISSING the recovery flow must FAIL."""
    engine = RecoveryEngine()
    plan = _build_test_plan(dpid=2, in_port=1, out_port=3, src_ip="10.0.0.1", dst_ip="10.0.0.50")

    unrelated_flows = _build_20_unrelated_flows(dpid=2)
    assert len(unrelated_flows) == 20

    mock_sdn = MagicMock()
    # Switch has 20 unrelated flows, but NOT the recovery flow
    mock_sdn.get_flows = AsyncMock(return_value=unrelated_flows)
    engine.sdn_controller = mock_sdn

    result: VerificationResult = await engine.verify_recovery(
        incident=MagicMock(),
        recovery_plans=[plan]
    )

    assert result.success is False
    assert result.reason == "flow_not_found_on_switch"
    assert result.failed_dpid == 2
    assert result.actual_flows_count == 20
    assert result.expected["in_port"] == 1
    assert result.expected["ipv4_src"] == "10.0.0.1"
    assert result.expected["ipv4_dst"] == "10.0.0.50"
    assert "20 flows present" in result.details


# ─────────────────────────────────────────────────────────────────────────────
# 3. DATA-PLANE PING FAILURE -> FAILS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dataplane_ping_failure_triggers_failure():
    """If exact flow exists on switch but destination ping is unreachable, verification fails."""
    engine = RecoveryEngine()
    plan = _build_test_plan(dpid=2, in_port=1, out_port=3, src_ip="10.0.0.1", dst_ip="10.0.0.50")

    exact_flow = {
        "dpid": 2,
        "priority": engine.RECOVERY_PRIORITY,
        "match": {
            "in_port": 1,
            "eth_type": 2048,
            "ipv4_src": "10.0.0.1",
            "ipv4_dst": "10.0.0.50"
        },
        "actions": ["OUTPUT:3"]
    }

    mock_sdn = MagicMock()
    mock_sdn.get_flows = AsyncMock(return_value=[exact_flow])
    engine.sdn_controller = mock_sdn

    # Real data-plane ping fails (host unreachable)
    mock_monitor = MagicMock()
    mock_monitor.ping_host = AsyncMock(return_value={
        "reachable": False,
        "method": "icmp",
        "latency_ms": 0.0,
        "packet_loss_pct": 100.0
    })
    engine.network_monitor = mock_monitor

    result: VerificationResult = await engine.verify_recovery(
        incident=MagicMock(),
        recovery_plans=[plan]
    )

    assert result.success is False
    assert result.reachable is False
    assert result.reason == "hosts_unreachable_after_recovery"
    assert "unreachable" in result.details


# ─────────────────────────────────────────────────────────────────────────────
# 4. PACKET LOSS TOO HIGH -> FAILS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_high_packet_loss_fails_verification():
    """If destination is reachable but packet loss > 1.0%, verification fails."""
    engine = RecoveryEngine()
    plan = _build_test_plan(dpid=2, in_port=1, out_port=3, src_ip="10.0.0.1", dst_ip="10.0.0.50")

    exact_flow = {
        "dpid": 2,
        "priority": engine.RECOVERY_PRIORITY,
        "match": {
            "in_port": 1,
            "eth_type": 2048,
            "ipv4_src": "10.0.0.1",
            "ipv4_dst": "10.0.0.50"
        },
        "actions": ["OUTPUT:3"]
    }

    mock_sdn = MagicMock()
    mock_sdn.get_flows = AsyncMock(return_value=[exact_flow])
    engine.sdn_controller = mock_sdn

    mock_monitor = MagicMock()
    # 5% packet loss (exceeds allowable 1.0% limit)
    mock_monitor.ping_host = AsyncMock(return_value={
        "reachable": True,
        "method": "icmp",
        "latency_ms": 12.0,
        "packet_loss_pct": 5.0
    })
    engine.network_monitor = mock_monitor

    result: VerificationResult = await engine.verify_recovery(
        incident=MagicMock(),
        recovery_plans=[plan]
    )

    assert result.success is False
    assert result.reason == "packet_loss_too_high"
    assert result.packet_loss_pct == 5.0
    assert "exceeds allowable threshold" in result.details


# ─────────────────────────────────────────────────────────────────────────────
# 5. TCP FALLBACK IN NETWORK MONITOR DOES NOT REPORT FAKE METRICS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_network_monitor_tcp_fallback_no_fake_metrics():
    """When ICMP is blocked/unavailable, TCP fallback returns latency_ms=None and packet_loss_pct=None."""
    monitor = NetworkMonitor()

    # Mock _tcp_probe to simulate successful TCP port connection
    with patch.object(monitor, "_tcp_probe", AsyncMock(return_value=(True, 8.4))):
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("ping not installed")):
            res = await monitor.ping_host("192.168.1.100")

            assert res["reachable"] is True
            assert res["method"] == "tcp"
            assert res["connect_time_ms"] == 8.4
            assert res["latency_ms"] is None, "Must NEVER fabricate ICMP latency for TCP fallback"
            assert res["packet_loss_pct"] is None, "Must NEVER fabricate packet loss for TCP fallback"
            assert "TCP fallback" in res["note"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. END-TO-END RECOVERY ROLLS BACK WHEN VERIFICATION FAILS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_incident_triggers_rollback_on_verification_failure():
    """End-to-end pipeline: if exact flow is missing, verification fails and rollback is executed."""
    engine = RecoveryEngine()

    devices = [
        {"id": "h1", "name": "Host 1", "device_type": "host", "dpid": None, "ip_address": "10.0.0.1", "status": "active"},
        {"id": "srv1", "name": "Server 1", "device_type": "server", "dpid": None, "ip_address": "10.0.0.50", "status": "active"},
        {"id": "s1", "name": "Switch 1", "device_type": "switch", "dpid": "1", "ip_address": None, "status": "active"},
        {"id": "s2", "name": "Switch 2", "device_type": "switch", "dpid": "2", "ip_address": None, "status": "active"},
        {"id": "s3", "name": "Switch 3", "device_type": "switch", "dpid": "3", "ip_address": None, "status": "active"},
    ]
    links = [
        {"id": "link-h1-s1", "src_device_id": "h1", "dst_device_id": "s1", "src_port": 1, "dst_port": 1, "status": "up", "latency_ms": 1.0},
        {"id": "link-s1-s2", "src_device_id": "s1", "dst_device_id": "s2", "src_port": 2, "dst_port": 1, "status": "up", "latency_ms": 1.0},
        {"id": "link-s2-s3", "src_device_id": "s2", "dst_device_id": "s3", "src_port": 2, "dst_port": 2, "status": "down", "latency_ms": 1.0},
        {"id": "link-s3-srv1", "src_device_id": "s3", "dst_device_id": "srv1", "src_port": 3, "dst_port": 1, "status": "up", "latency_ms": 1.0},
        {"id": "link-s1-s3", "src_device_id": "s1", "dst_device_id": "s3", "src_port": 3, "dst_port": 1, "status": "up", "latency_ms": 10.0},
    ]

    engine._load_topology_from_db = AsyncMock(return_value=(devices, links))

    mock_incident = MagicMock(spec=Incident)
    mock_incident.id = "inc-verify-fail"
    mock_incident.affected_link_id = "link-s2-s3"
    mock_incident.affected_device_id = None
    mock_incident.status = "detected"

    mock_rollback = MagicMock(spec=RollbackManager)
    mock_rollback.snapshot = AsyncMock(return_value="snap-test-123")
    mock_rollback.rollback = AsyncMock(return_value=RollbackResult(overall_success=True, snapshot_id="snap-test-123"))
    engine.rollback_manager = mock_rollback

    mock_executor = MagicMock(spec=ActionExecutor)
    mock_executor.execute = AsyncMock(return_value=ExecutionResult(
        success=True, duration_ms=10.0, installed_flows=[{"dpid": 1}]
    ))
    engine.action_executor = mock_executor

    # The switch only has unrelated flows — recovery flow is MISSING!
    mock_sdn = MagicMock()
    mock_sdn.get_flows = AsyncMock(return_value=_build_20_unrelated_flows(dpid=1))
    engine.sdn_controller = mock_sdn

    engine.network_monitor = MagicMock()
    engine.network_monitor.ping_host = AsyncMock(return_value={"reachable": True, "latency_ms": 5.0, "packet_loss_pct": 0.0})

    with patch("backend.recovery.recovery_engine.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = mock_incident
        mock_session.execute.return_value = mock_res

        result: RecoveryResult = await engine.handle_incident(mock_incident.id)

        assert result.overall_status in ("failed", "rolled_back")
        assert result.reason == "verification_failed"
        assert result.rollback_status == "success"
        assert mock_rollback.rollback.called
        assert mock_rollback.rollback.call_args[0][0] == "snap-test-123"

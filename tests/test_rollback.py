"""tests/test_rollback.py — Safe Transactional Snapshot and Diff-Based Rollback Verification.

Tests:
1. Snapshot failure on any switch:
   - When 1 of N switches fails or returns non-list, snapshot returns None (refusing partial snapshot).
2. RecoveryEngine behavior on snapshot failure:
   - Aborts immediately with success=False, reason="snapshot_failed", escalates incident.
3. Safe diff-based rollback:
   - Identifies and deletes ONLY recovery flows (cookie=0x53454E54).
   - Preserves non-recovery / operator flows without deleting them.
   - Restores missing baseline flows.
4. Verification failure during rollback:
   - When switch is unreachable during rollback or baseline flows are missing,
     overall_success is False, alerts triggered, fails loudly (no fake success).
5. InvalidSnapshot exception:
   - Rollback raises InvalidSnapshot when snapshot is missing or invalid.
6. End-to-end recovery rollback on verification failure:
   - Verifies safety rollback triggers and incident is marked 'rolled_back' in DB.
"""

import asyncio
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from sqlalchemy import select

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database.database import AsyncSessionLocal, init_db
from backend.database.models import Incident
from backend.recovery.recovery_engine import RecoveryEngine, VerificationResult
from backend.recovery.rollback import (
    RollbackManager, RollbackResult, SnapshotError, InvalidSnapshot,
    SENTINELNET_RECOVERY_COOKIE
)
from backend.recovery.action_executor import ActionExecutor, ExecutionResult


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: Verified Snapshot
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_snapshot_refuses_partial_failure():
    """If ANY switch fails during snapshot, return None — NEVER store a partial snapshot."""
    mock_sdn = MagicMock()
    # DPID 1 succeeds, DPID 2 fails, DPID 3 succeeds
    async def mock_get_flows(dpid):
        if dpid == 2:
            raise ConnectionError("Switch DPID 2 connection timeout")
        return [{"priority": 1, "match": {"in_port": 1}, "actions": ["OUTPUT:2"]}]

    mock_sdn.get_flows = AsyncMock(side_effect=mock_get_flows)

    manager = RollbackManager(sdn_controller=mock_sdn, snapshot_dir="./tmp_snapshots")
    result = await manager.snapshot(affected_dpids=[1, 2, 3])

    assert result is None, "Snapshot MUST return None when any switch fails to respond"
    # Ensure no partial snapshot was registered in memory
    assert len(manager._in_memory_snapshots) == 0, "No partial snapshot must be persisted"


@pytest.mark.asyncio
async def test_snapshot_rejects_invalid_flow_response():
    """If switch returns non-list (e.g. None or error dict), refuse snapshot."""
    mock_sdn = MagicMock()
    mock_sdn.get_flows = AsyncMock(return_value=None)

    manager = RollbackManager(sdn_controller=mock_sdn, snapshot_dir="./tmp_snapshots")
    result = await manager.snapshot(affected_dpids=[1])

    assert result is None, "Snapshot MUST return None when switch returns None"


# ─────────────────────────────────────────────────────────────────────────────
# UNIT TESTS: Safe Diff-Based Rollback & Cookie Tagging
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_safe_diff_rollback_preserves_operator_flows():
    """Diff rollback deletes ONLY SentinelNet recovery flows (cookie=0x53454E54).

    Operator flows (monitoring rules, standard default routes) must NEVER be deleted.
    Missing baseline flows must be restored.
    """
    mock_sdn = MagicMock()

    # Original baseline: 2 operator flows
    baseline_flows = [
        {"priority": 0, "match": {}, "actions": ["CONTROLLER:65535"], "cookie": 0},
        {"priority": 100, "match": {"dl_type": 2048, "nw_dst": "10.0.0.99"}, "actions": ["OUTPUT:4"], "cookie": 0x1234}
    ]

    # Current switch state after recovery:
    # - Original flow 1 present
    # - Original flow 2 accidentally dropped
    # - SentinelNet recovery flow added (cookie=0x53454E54)
    # - Important operator flow added while recovery was running (cookie=0x9999)
    current_flows = [
        {"priority": 0, "match": {}, "actions": ["CONTROLLER:65535"], "cookie": 0},
        {"priority": 300, "match": {"in_port": 1, "eth_type": 2048}, "actions": ["OUTPUT:3"], "cookie": SENTINELNET_RECOVERY_COOKIE},
        {"priority": 500, "match": {"in_port": 2}, "actions": ["OUTPUT:5"], "cookie": 0x9999}  # Operator flow!
    ]

    # Post-restoration verified state
    verified_flows = list(baseline_flows)

    mock_sdn.get_flows = AsyncMock(side_effect=[current_flows, verified_flows])
    mock_sdn.delete_flow_entry = AsyncMock(return_value={"result": "deleted"})
    mock_sdn.add_flow_entry = AsyncMock(return_value={"result": "added"})

    manager = RollbackManager(sdn_controller=mock_sdn, snapshot_dir="./tmp_snapshots")

    # Seed valid snapshot
    snapshot_id = "snap_test_diff_1"
    manager._in_memory_snapshots[snapshot_id] = {
        "id": snapshot_id,
        "snapshot_id": snapshot_id,
        "status": "valid",
        "dpids": [1],
        "flows": {"1": baseline_flows}
    }

    result = await manager.rollback(snapshot_id)

    assert result.overall_success is True
    dpid_res = result.dpids["1"]
    assert dpid_res["verified"] is True
    assert dpid_res["deleted_count"] == 1, "Only the 1 recovery flow should be deleted"
    assert dpid_res["restored_count"] == 1, "The 1 missing baseline flow should be restored"

    # Verify what was deleted: only cookie 0x53454E54
    assert mock_sdn.delete_flow_entry.call_count == 1
    del_call = mock_sdn.delete_flow_entry.call_args[0][0]
    assert del_call["cookie"] == SENTINELNET_RECOVERY_COOKIE
    assert del_call["priority"] == 300

    # Verify operator flow (cookie=0x9999) was NEVER deleted
    for call in mock_sdn.delete_flow_entry.call_args_list:
        rule = call[0][0]
        assert rule.get("cookie") != 0x9999, "Operator flow must NOT be deleted!"


@pytest.mark.asyncio
async def test_rollback_fails_loudly_when_switch_unreachable():
    """If switch becomes unreachable during rollback, fail loudly with overall_success=False."""
    mock_sdn = MagicMock()
    mock_sdn.get_flows = AsyncMock(side_effect=ConnectionError("Ryu switch 2 unreachable"))

    mock_alert = MagicMock()
    mock_alert.critical = AsyncMock()

    manager = RollbackManager(
        sdn_controller=mock_sdn,
        snapshot_dir="./tmp_snapshots",
        alert_service=mock_alert
    )

    snapshot_id = "snap_test_unreachable"
    manager._in_memory_snapshots[snapshot_id] = {
        "id": snapshot_id,
        "snapshot_id": snapshot_id,
        "status": "valid",
        "dpids": [2],
        "flows": {"2": [{"priority": 1, "match": {}, "actions": ["OUTPUT:1"]}]}
    }

    result = await manager.rollback(snapshot_id)

    assert result.overall_success is False, "Rollback must report failure when switch is unreachable"
    assert result.dpids["2"]["verified"] is False
    assert "unreachable" in result.dpids["2"]["error"].lower()
    assert mock_alert.critical.called, "Critical alert must be fired on rollback failure"


@pytest.mark.asyncio
async def test_rollback_invalid_snapshot_raises_exception():
    """Attempting rollback with non-existent or invalid status snapshot raises InvalidSnapshot."""
    manager = RollbackManager(snapshot_dir="./tmp_snapshots")

    with pytest.raises(InvalidSnapshot):
        await manager.rollback("non_existent_snapshot_id_999")

    # Also test snapshot marked 'used' or 'invalid'
    manager._in_memory_snapshots["used_snap"] = {"status": "used", "flows": {}}
    with pytest.raises(InvalidSnapshot):
        await manager.rollback("used_snap")


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION TESTS: RecoveryEngine + Rollback
# ─────────────────────────────────────────────────────────────────────────────

class MockFailingVerificationRecoveryEngine(RecoveryEngine):
    """RecoveryEngine test double where post-installation active verification fails."""

    async def verify_recovery(self, incident, recovery_plans, devices):
        return VerificationResult(
            success=False,
            reachable=False,
            latency_ms=999.0,
            packet_loss_pct=100.0,
            flows_verified=False,
            details="Simulated failure: destination unreachable over bypass link, 100% packet loss"
        )


class RecordingRollbackManager(RollbackManager):
    """RollbackManager spy tracking snapshot and rollback invocations."""

    def __init__(self):
        super().__init__()
        self.snapshots_created = []
        self.rollbacks_executed = []

    async def snapshot(self, affected_dpids=None):
        snap_id = f"snap_test_{int(datetime.now(timezone.utc).timestamp())}"
        self.snapshots_created.append(snap_id)
        return snap_id

    async def verify_snapshot_validity(self, snapshot_id: str):
        return True, None

    async def rollback(self, snapshot_id: str):
        self.rollbacks_executed.append(snapshot_id)
        return RollbackResult(overall_success=True, snapshot_id=snapshot_id)


class SuccessfulActionExecutor(ActionExecutor):
    """Simulates flow installation success so pipeline reaches the verification step."""

    async def execute(self, action):
        return ExecutionResult(
            success=True,
            duration_ms=45.0,
            installed_flows=[{"dpid": 1, "in_port": 1, "out_port": 3}]
        )


@pytest.mark.asyncio
async def test_recovery_aborts_when_snapshot_fails():
    """If snapshot fails, RecoveryEngine MUST abort with reason='snapshot_failed' and NOT install flows."""
    mock_rollback = MagicMock()
    mock_rollback.snapshot = AsyncMock(return_value=None)  # Snapshot failed!

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock()

    engine = RecoveryEngine(
        action_executor=mock_executor,
        rollback_manager=mock_rollback
    )

    inc_id = "inc_test_snap_fail_1"
    test_inc = Incident(
        id=inc_id,
        title="Link Failure for snapshot failure test",
        severity="critical",
        status="detected",
        affected_link_id="link-s2-s3"
    )

    devices = [
        {"id": "h1", "device_type": "host", "status": "active"},
        {"id": "srv1", "device_type": "server", "status": "active"},
        {"id": "s1", "device_type": "switch", "dpid": "1", "status": "active"},
        {"id": "s2", "device_type": "switch", "dpid": "2", "status": "active"},
        {"id": "s3", "device_type": "switch", "dpid": "3", "status": "active"},
    ]
    links = [
        {"id": "link-h1-s1", "src_device_id": "h1", "dst_device_id": "s1", "src_port": 1, "dst_port": 1, "link_type": "access", "status": "up", "bandwidth_mbps": 100.0, "latency_ms": 1.0},
        {"id": "link-s1-s2", "src_device_id": "s1", "dst_device_id": "s2", "src_port": 2, "dst_port": 1, "link_type": "primary", "status": "up", "bandwidth_mbps": 100.0, "latency_ms": 1.0},
        {"id": "link-s2-s3", "src_device_id": "s2", "dst_device_id": "s3", "src_port": 2, "dst_port": 1, "link_type": "primary", "status": "down", "bandwidth_mbps": 100.0, "latency_ms": 1.0},
        {"id": "link-s3-srv1", "src_device_id": "s3", "dst_device_id": "srv1", "src_port": 2, "dst_port": 1, "link_type": "access", "status": "up", "bandwidth_mbps": 100.0, "latency_ms": 1.0},
        {"id": "link-s1-s3", "src_device_id": "s1", "dst_device_id": "s3", "src_port": 3, "dst_port": 2, "link_type": "backup", "status": "up", "bandwidth_mbps": 100.0, "latency_ms": 20.0},
    ]

    with patch.object(engine, "_load_topology_from_db", AsyncMock(return_value=(devices, links))):
        with patch("backend.recovery.recovery_engine.AsyncSessionLocal") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_inc_res = MagicMock()
            mock_inc_res.scalar_one_or_none.return_value = test_inc
            mock_session.execute = AsyncMock(return_value=mock_inc_res)
            mock_session.commit = AsyncMock()
            mock_session_ctx.return_value = mock_session

            result = await engine.handle_incident(inc_id)

    assert result.overall_status == "failed"
    assert result.reason == "snapshot_failed"
    assert not mock_executor.execute.called, "Flow installation must NEVER be attempted if snapshot failed!"


@pytest.mark.asyncio
async def test_recovery_rollback_on_verification_failure():
    """Verify that failed active verification triggers safety rollback and updates incident status."""
    inc_id = "inc_test_rollback_1"
    test_incident = Incident(
        id=inc_id,
        title="Link Failure candidate for rollback testing",
        severity="critical",
        status="detected",
        affected_link_id="link-s2-s3",
        root_cause="link_failure",
        confidence_score=0.95,
        detected_at=datetime.now(timezone.utc)
    )

    devices = [
        {"id": "h1", "device_type": "host", "status": "active"},
        {"id": "srv1", "device_type": "server", "status": "active"},
        {"id": "s1", "device_type": "switch", "dpid": "1", "status": "active"},
        {"id": "s2", "device_type": "switch", "dpid": "2", "status": "active"},
        {"id": "s3", "device_type": "switch", "dpid": "3", "status": "active"},
    ]
    links = [
        {"id": "link-h1-s1", "src_device_id": "h1", "dst_device_id": "s1", "src_port": 1, "dst_port": 1, "link_type": "access", "status": "up", "bandwidth_mbps": 100.0, "latency_ms": 1.0},
        {"id": "link-s1-s2", "src_device_id": "s1", "dst_device_id": "s2", "src_port": 2, "dst_port": 1, "link_type": "primary", "status": "up", "bandwidth_mbps": 100.0, "latency_ms": 1.0},
        {"id": "link-s2-s3", "src_device_id": "s2", "dst_device_id": "s3", "src_port": 2, "dst_port": 1, "link_type": "primary", "status": "down", "bandwidth_mbps": 100.0, "latency_ms": 1.0},
        {"id": "link-s3-srv1", "src_device_id": "s3", "dst_device_id": "srv1", "src_port": 2, "dst_port": 1, "link_type": "access", "status": "up", "bandwidth_mbps": 100.0, "latency_ms": 1.0},
        {"id": "link-s1-s3", "src_device_id": "s1", "dst_device_id": "s3", "src_port": 3, "dst_port": 2, "link_type": "backup", "status": "up", "bandwidth_mbps": 100.0, "latency_ms": 20.0},
    ]

    rollback_spy = RecordingRollbackManager()
    action_stub = SuccessfulActionExecutor()

    engine = MockFailingVerificationRecoveryEngine(
        action_executor=action_stub,
        rollback_manager=rollback_spy
    )

    with patch.object(engine, "_load_topology_from_db", AsyncMock(return_value=(devices, links))):
        with patch("backend.recovery.recovery_engine.AsyncSessionLocal") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_inc_res = MagicMock()
            mock_inc_res.scalar_one_or_none.return_value = test_incident
            mock_session.execute = AsyncMock(return_value=mock_inc_res)
            mock_session.commit = AsyncMock()
            mock_session_ctx.return_value = mock_session

            result = await engine.handle_incident(inc_id)

    # 1. Verify result indicates failure and rollback
    assert result.overall_status in ("failed", "rolled_back"), "Recovery must be marked failure/rolled_back when verification fails"
    assert result.rollback_status == "success", "Result must indicate that safety rollback was executed"
    assert result.reason == "verification_failed", f"Expected reason 'verification_failed', got '{result.reason}'"

    # 2. Verify RollbackManager was actually invoked
    assert len(rollback_spy.snapshots_created) == 1, "Snapshot must have been created before flow installation"
    assert len(rollback_spy.rollbacks_executed) == 1, "Rollback must have been executed after verification failure"
    assert rollback_spy.rollbacks_executed[0] == rollback_spy.snapshots_created[0]

    # 3. Verify status marked "rolled_back"
    assert test_incident.status == "rolled_back"


# ─────────────────────────────────────────────────────────────────────────────
# REST API ENDPOINT TESTS (POST /api/recovery/rollback & GET /preview/{id})
# ─────────────────────────────────────────────────────────────────────────────

from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database.database import get_db
from backend.api.auth import get_current_user
from backend.database.models import User, RecoveryAction, Incident, AuditLog


class MockRollbackDb:
    def __init__(self, actions=None, incidents=None):
        self.actions = actions or {}
        self.incidents = incidents or {}
        self.audit_logs = []
        self.committed = False

    async def get(self, model, ident):
        if model == RecoveryAction:
            return self.actions.get(str(ident))
        if model == Incident:
            return self.incidents.get(str(ident))
        return None

    async def insert_audit_log(self, user_id, action_type, target_id, details):
        self.audit_logs.append({
            "user_id": user_id,
            "action": action_type,
            "target_id": target_id,
            "details": details
        })

    def add(self, obj):
        if isinstance(obj, AuditLog):
            self.audit_logs.append({
                "action": obj.action,
                "actor": obj.actor,
                "details": obj.details
            })

    async def commit(self):
        self.committed = True


@pytest.fixture
def mock_operator_user():
    return User(id="usr-op-01", username="operator1", email="operator1@sentinelnet.edu", role="operator")


@pytest.mark.asyncio
async def test_rollback_endpoint_missing_snapshot_returns_400(mock_operator_user):
    """If recovery action has no snapshot_id, rollback endpoint must return 400 Bad Request."""
    action = RecoveryAction(
        id="act_no_snap",
        incident_id="inc_001",
        action_type="reroute",
        status="success",
        parameters={}  # No snapshot_id!
    )
    mock_db = MockRollbackDb(actions={"act_no_snap": action})

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_operator_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/recovery/rollback", json={"recovery_action_id": "act_no_snap"})
            assert resp.status_code == 400
            assert "No snapshot available" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rollback_endpoint_already_rolled_back_returns_400(mock_operator_user):
    """If action is already rolled_back, endpoint must reject with 400 Bad Request."""
    action = RecoveryAction(
        id="act_already_rb",
        incident_id="inc_002",
        action_type="reroute",
        status="rolled_back",
        parameters={"snapshot_id": "snap_123"}
    )
    mock_db = MockRollbackDb(actions={"act_already_rb": action})

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_operator_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/recovery/rollback", json={"recovery_action_id": "act_already_rb"})
            assert resp.status_code == 400
            assert "Already rolled back" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rollback_endpoint_failure_preserves_status_and_logs_audit(mock_operator_user):
    """When rollback fails on switches, endpoint returns 500, preserves action status, and logs audit."""
    action = RecoveryAction(
        id="act_fail_test",
        incident_id="inc_003",
        action_type="reroute",
        status="success",
        parameters={"snapshot_id": "snap_valid_fail"}
    )
    incident = Incident(id="inc_003", title="Fault", severity="critical", status="recovered")
    mock_db = MockRollbackDb(actions={"act_fail_test": action}, incidents={"inc_003": incident})

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_operator_user

    # Mock RollbackManager to simulate partial / failed rollback
    failed_result = RollbackResult(
        overall_success=False,
        snapshot_id="snap_valid_fail",
        error="Switch DPID 2 unreachable during verification"
    )

    with patch("backend.api.routes.RollbackManager.verify_snapshot_validity", AsyncMock(return_value=(True, None))), \
         patch("backend.api.routes.RollbackManager.rollback", AsyncMock(return_value=failed_result)):

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/recovery/rollback", json={"recovery_action_id": "act_fail_test"})
                assert resp.status_code == 500

                # Status must NOT have been changed to rolled_back
                assert action.status == "success"
                assert incident.status == "recovered"

                # Audit log for failure must be recorded
                assert len(mock_db.audit_logs) > 0
                audit_actions = [l["action"] for l in mock_db.audit_logs]
                assert "ROLLBACK_PARTIAL_FAILURE" in audit_actions
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rollback_endpoint_success_verifies_and_updates_status(mock_operator_user):
    """On verified rollback success: status updated, incident escalated, audit written, and result returned."""
    action = RecoveryAction(
        id="act_success_test",
        incident_id="inc_004",
        action_type="reroute",
        status="success",
        parameters={"snapshot_id": "snap_valid_ok"}
    )
    incident = Incident(id="inc_004", title="Fault", severity="critical", status="recovered")
    mock_db = MockRollbackDb(actions={"act_success_test": action}, incidents={"inc_004": incident})

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_operator_user

    success_result = RollbackResult(
        overall_success=True,
        dpids={"1": {"verified": True, "restored_count": 2, "deleted_count": 1}},
        snapshot_id="snap_valid_ok"
    )

    with patch("backend.api.routes.RollbackManager.verify_snapshot_validity", AsyncMock(return_value=(True, None))), \
         patch("backend.api.routes.RollbackManager.rollback", AsyncMock(return_value=success_result)):

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/recovery/rollback", json={"recovery_action_id": "act_success_test"})
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["rollback_result"]["overall_success"] is True

                # Verified status updates
                assert action.status == "rolled_back"
                assert action.result == "rolled_back"
                assert incident.status == "escalated"
                assert mock_db.committed is True

                # Audit log
                audit_actions = [l["action"] for l in mock_db.audit_logs]
                assert "ROLLBACK_SUCCESS" in audit_actions
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rollback_preview_endpoint_returns_diff(mock_operator_user):
    """GET /api/recovery/rollback/preview/{action_id} returns flow diff and impact without side effects."""
    action = RecoveryAction(
        id="act_preview_test",
        incident_id="inc_005",
        action_type="reroute",
        status="success",
        parameters={"snapshot_id": "snap_prev"}
    )
    mock_db = MockRollbackDb(actions={"act_preview_test": action})

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: mock_operator_user

    mock_preview = {
        "snapshot_id": "snap_prev",
        "dpids": [1, 2],
        "flows_to_delete": [{"dpid": 1, "priority": 300, "cookie": "0x53454E54"}],
        "flows_to_restore": [{"dpid": 2, "priority": 0}],
        "total_flows_to_delete": 1,
        "total_flows_to_restore": 1,
        "estimated_impact": "Will delete 1 recovery flow and restore 1 baseline flow across 2 switches.",
        "is_safe": True
    }

    with patch("backend.api.routes.RollbackManager.preview_rollback", AsyncMock(return_value=mock_preview)):
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/recovery/rollback/preview/act_preview_test")
                assert resp.status_code == 200
                data = resp.json()
                assert data["action_id"] == "act_preview_test"
                assert data["total_flows_to_delete"] == 1
                assert data["total_flows_to_restore"] == 1
                assert data["is_safe"] is True

                # Action status must be completely untouched (read-only)
                assert action.status == "success"
        finally:
            app.dependency_overrides.clear()

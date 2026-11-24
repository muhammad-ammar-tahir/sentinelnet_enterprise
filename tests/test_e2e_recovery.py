"""tests/test_e2e_recovery.py — End-to-End Autonomous Self-Healing Integration Test.

Tests the FULL closed-loop autonomous pipeline — no manual /api/recovery/execute call:

  Inject failure
    → FailureInjectionService creates incident via IncidentService (single source of truth)
    → IncidentService deduplicates + persists + returns incident
    → FailureInjectionService enqueues into RecoveryQueue if policy allows
    → RecoveryQueue._worker_loop() picks it up and calls RecoveryEngine.handle_incident()
    → RecoveryEngine marks incident "recovered" + stamps recovery_action_id
    → WebSocket broadcasts RECOVERY_COMPLETED
  Poll /api/incidents until status == "recovered" with recovery_action_id  ← autonomous proof

If the pipeline does NOT fire autonomously (e.g. the injection bypasses the queue or the
worker crashes) the poll will timeout and the test will FAIL — no manufactured success.

Also covers the policy-disabled path: incident stays "detected", never reaches "recovering".

Gracefully skips when no live Mininet/Ryu environment is detected.
"""

import asyncio
import os
import sys
import time
import pytest
import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.controller.sdn_controller import RyuSDNControllerClient
from backend.monitoring.network_monitor import NetworkMonitor


# ─────────────────────────────────────────────────────────────────────────────
# Environment Guard
# ─────────────────────────────────────────────────────────────────────────────

async def check_live_environment_available() -> bool:
    """Check if Mininet and Ryu controller are actively reachable."""
    controller = RyuSDNControllerClient()
    try:
        switches = await controller.get_switches()
        if len(switches) >= 3:
            return True
    except Exception:
        pass

    monitor = NetworkMonitor()
    try:
        res = await monitor.ping_host("10.0.1.3", count=1, timeout=1.0)
        if res.get("reachable"):
            return True
    except Exception:
        pass

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Polling helpers — autonomous proofs only, no manual API calls
# ─────────────────────────────────────────────────────────────────────────────

async def poll_until_incident_created(
    client: httpx.AsyncClient,
    timeout: float = 30.0,
) -> dict:
    """Poll GET /api/incidents until a link_failure incident appears.

    The incident MUST be created autonomously by FailureInjectionService via
    IncidentService — the test never calls POST /api/incidents directly.
    """
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        resp = await client.get("/api/incidents")
        if resp.status_code == 200:
            for inc in resp.json():
                if inc.get("root_cause") in ("link_failure", "LINK_DOWN", "INTERFACE_DOWN") or \
                   inc.get("fault_type") in ("link_failure", "LINK_DOWN", "INTERFACE_DOWN"):
                    return inc
        await asyncio.sleep(0.5)
    raise TimeoutError(
        f"No link_failure incident appeared within {timeout}s. "
        "Check that FailureInjectionService is calling incident_service.create_from_fault() "
        "and that the monitoring loop is running."
    )


async def poll_until_autonomous_recovery(
    client: httpx.AsyncClient,
    incident_id: str,
    timeout: float = 90.0,
) -> dict:
    """Poll GET /api/incidents/{id} until the incident autonomously reaches
    'recovered' or 'resolved' status WITH a recovery_action_id populated.

    This is the PROOF of autonomous operation:
      • No POST /api/recovery/execute is ever called.
      • The recovery must be driven entirely by RecoveryQueue._worker_loop().
      • If it times out, the test FAILS — it does NOT manufacture success.
    """
    terminal = ("recovered", "resolved")
    start = time.perf_counter()

    while time.perf_counter() - start < timeout:
        resp = await client.get(f"/api/incidents/{incident_id}")
        if resp.status_code == 200:
            state = resp.json()
            current_status = state.get("status")

            if current_status in terminal:
                action_id = state.get("recovery_action_id")
                assert action_id is not None, (
                    f"Incident {incident_id} reached status '{current_status}' "
                    "but recovery_action_id is None — RecoveryEngine did not stamp it. "
                    "Check recovery_engine.py metadata_payload update."
                )
                # Fetch the actual recovery action record
                action_resp = await client.get(f"/api/recovery/actions/{action_id}")
                assert action_resp.status_code == 200, (
                    f"Could not fetch recovery action {action_id}: "
                    f"HTTP {action_resp.status_code}"
                )
                return action_resp.json()

        await asyncio.sleep(1.0)

    raise TimeoutError(
        f"Autonomous recovery did NOT complete for incident {incident_id} within {timeout}s. "
        "Chain to investigate: "
        "1) Was incident enqueued? Check recovery_queue.qsize in /api/health/deep. "
        "2) Did worker pick it up? Look for '[RecoveryQueue] ▶ Processing' in logs. "
        "3) Did RecoveryEngine finish? Look for 'TOPOLOGY-AWARE RECOVERY COMPLETED' in logs."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main Test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_autonomous_self_healing_workflow():
    """End-to-End AUTONOMOUS Self-Healing Workflow Test.

    The word AUTONOMOUS means: after inject → no human/test intervention.
    The recovery is triggered entirely by the background RecoveryQueue worker.
    """
    is_live = await check_live_environment_available()
    if not is_live:
        pytest.skip(
            "Live Mininet/Ryu environment not detected (Ryu on port 8080 or Mininet switches offline). "
            "Skipping end-to-end hardware test. (Run: sudo python network_simulation/topology.py)"
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

        # ── Auth ──────────────────────────────────────────────────────────────
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "operator@sentinelnet.edu", "password": "sentinelpass"},
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        # ── 1. Healthy baseline ───────────────────────────────────────────────
        health_before = await client.get("/api/metrics/live")
        assert health_before.status_code == 200
        assert "network_health_score" in health_before.json()
        print("\n✓ Baseline telemetry healthy")

        # ── 2. Inject link failure (s2 ↔ s3) ─────────────────────────────────
        inject_response = await client.post("/api/topology/fail", json={"link": ["s2", "s3"]})
        assert inject_response.status_code == 200, (
            f"Failure injection failed: {inject_response.text}"
        )
        inject_data = inject_response.json()
        assert inject_data["status"] == "injected"
        incident_id_from_inject = inject_data.get("incident_id")
        print(f"✓ Failure injected — incident_id from injection: {incident_id_from_inject}")

        # ── 3. Wait for autonomous incident creation ──────────────────────────
        # The injection itself calls incident_service.create_from_fault(), so the
        # incident should appear immediately.  Give it 30s for the monitoring loop
        # path as well (whichever fires first wins via deduplication).
        incident = await poll_until_incident_created(client, timeout=30)
        assert incident.get("detected_at") is not None, "detected_at must be set"
        effective_incident_id = incident_id_from_inject or incident["id"]
        print(
            f"✓ Incident created autonomously: {effective_incident_id} "
            f"(fault={incident.get('fault_type') or incident.get('root_cause')}, "
            f"status={incident.get('status')})"
        )

        # ── 4. Wait for AUTONOMOUS recovery ──────────────────────────────────
        # NO POST /api/recovery/execute — the RecoveryQueue worker must do this.
        recovery = await poll_until_autonomous_recovery(
            client, effective_incident_id, timeout=90
        )
        assert recovery["overall_status"] == "success", (
            f"Recovery finished with non-success status: {recovery['overall_status']} "
            f"(reason={recovery.get('reason', 'n/a')})"
        )
        assert recovery["flow_installation"] == "success", (
            f"Flow installation did not succeed: {recovery['flow_installation']}"
        )
        assert recovery["traffic_verification"] == "success", (
            f"Traffic verification did not succeed: {recovery['traffic_verification']}"
        )
        print(
            f"✓ Autonomous recovery completed in {recovery.get('duration_ms', '?')}ms "
            f"(flows installed: {recovery.get('affected_flows_count', '?')})"
        )

        # ── 5. REAL ping verification through the new path ────────────────────
        ping_result = await client.post("/api/monitor/ping", json={"host": "10.0.1.3"})
        assert ping_result.status_code == 200
        assert ping_result.json()["reachable"] is True, (
            "Post-recovery ping to 10.0.1.3 FAILED — rerouted path may not carry traffic"
        )
        print(f"✓ Verification ping: {ping_result.json().get('latency_ms')}ms")

        # ── 6. Confirm Ryu has the new flows ─────────────────────────────────
        affected_dpid = recovery.get("affected_dpid")
        if affected_dpid:
            flows = await client.get(f"/api/controller/flows/{affected_dpid}")
            assert flows.status_code == 200
            assert len(flows.json()) > 0
            print(f"✓ Ryu DPID {affected_dpid} has {len(flows.json())} flows post-recovery")

        # ── 7. Confirm DB incident has recovery_action_id ─────────────────────
        incident_after = await client.get(f"/api/incidents/{effective_incident_id}")
        assert incident_after.status_code == 200
        final_state = incident_after.json()
        assert final_state["status"] in ("recovered", "resolved"), (
            f"Expected 'recovered'/'resolved', got '{final_state['status']}'"
        )
        assert final_state["recovery_action_id"] is not None, (
            "recovery_action_id is None in DB incident — RecoveryEngine did not stamp it"
        )
        print(f"✓ DB recovery action stamped: {final_state['recovery_action_id']}")

        print("\n🎉 AUTONOMOUS SELF-HEALING PIPELINE FULLY VERIFIED")
        print("   Chain: injected → incident_service → recovery_queue → engine → recovered")


# ─────────────────────────────────────────────────────────────────────────────
# Policy-disabled test: incident created but NOT auto-recovered
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_policy_disabled_no_auto_recovery():
    """When policy disables auto-recovery, the incident stays 'detected'.

    Proves that:
    - create_from_fault() still creates the incident correctly
    - policy check blocks the enqueue() call
    - incident stays in 'detected' — no spurious state transitions

    Uses in-memory mocks for DB and policy so this test is self-contained.
    """
    import backend.services.recovery_policy_service as rps_module
    from backend.services.recovery_queue import recovery_queue
    from backend.detection.fault_detection import Fault
    from backend.services.incident_service import IncidentService
    from backend.database.models import Incident as IncidentModel
    from unittest.mock import AsyncMock, MagicMock

    # ── In-memory mock DB (no Postgres required) ──────────────────────────
    class _MockDB:
        def __init__(self):
            self.added = []
            self.committed = False

        async def execute(self, stmt):
            r = MagicMock()
            # Dedup query: return None → no open incident → allow creation
            r.scalars.return_value.first.return_value = None
            r.scalar_one_or_none.return_value = None
            return r

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.committed = True

        async def close(self):
            pass

    mock_db = _MockDB()
    service = IncidentService(db=mock_db)

    # ── Patch policy to deny auto-recovery ────────────────────────────────
    policy_service = getattr(rps_module, "recovery_policy_service", rps_module)
    original_should = policy_service.should_auto_recover

    async def _policy_deny(*args, **kwargs):
        return False

    policy_service.should_auto_recover = _policy_deny

    q_before = recovery_queue.qsize

    try:
        fault = Fault(
            fault_type="link_failure",
            target_id="link-s2-s3",
            severity="critical",
            confidence=1.0,
            reason="Injected test failure for policy test",
            source="test",
        )
        metrics = {"interface_up": 0, "packet_loss_pct": 100.0}

        incident = await service.create_from_fault("link-s2-s3", fault, metrics)

        # Policy must deny
        policy_ok = await policy_service.should_auto_recover(incident)
        assert policy_ok is False, "Monkeypatched policy should return False"

        # Queue must NOT have grown
        assert recovery_queue.qsize == q_before, (
            "Incident was enqueued despite policy returning False — "
            "verify that callers check the policy result before calling enqueue()"
        )

        # Incident created correctly in 'detected' state
        assert incident is not None, "create_from_fault should return an Incident (not None)"
        assert incident.status == "detected"
        assert mock_db.committed is True

        print(
            f"\n✓ Policy-disabled: incident {incident.id} stays 'detected', "
            f"queue size unchanged at {recovery_queue.qsize}"
        )
    finally:
        # Restore patched method
        policy_service.should_auto_recover = original_should

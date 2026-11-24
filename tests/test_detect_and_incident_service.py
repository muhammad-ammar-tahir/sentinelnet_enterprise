"""tests/test_detect_and_incident_service.py — Verification of Detect Endpoint and Incident Service.

Tests:
1. DetectRequest schema validation: missing required features (e.g. cpu_pct, memory_pct) -> HTTP 422 Unprocessable Entity.
2. POST /api/detect with normal telemetry: returns empty faults and empty incidents_created.
3. POST /api/detect with anomalous telemetry:
   - Detects faults via rules and Isolation Forest ML.
   - Automatically persists Incident in PostgreSQL database.
   - Broadcasts INCIDENT_CREATED via WebSocket.
   - Enqueues incident to RecoveryQueue when auto-recovery is enabled.
4. IncidentService state transition tests:
   - create_from_fault
   - update_status
   - mark_recovering
   - mark_recovered
   - mark_rolled_back
   - mark_escalated
5. RecoveryQueue enqueue & background worker lifecycle.
"""

import asyncio
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# Ensure root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.database.database import get_db
from backend.database.models import Incident
from backend.api.routes import get_ws_manager
from backend.api.schemas import DetectRequest
from backend.services.incident_service import IncidentService
from backend.services.recovery_queue import RecoveryQueue
from backend.ws.manager import WebSocketEvents


class InMemoryMockDbSession:
    """Mock async DB session storing Incident records in memory."""
    def __init__(self):
        self.incidents = {}
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, Incident):
            self.incidents[obj.id] = obj

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        pass

    async def execute(self, stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()
        if "policies" in stmt_str:
            mock_result.scalars.return_value.all.return_value = []
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        # Deduplication query inside create_from_fault:
        # WHERE status IN ('detected', 'diagnosing', 'recovering', 'mitigating') LIMIT 1
        # We always return None here so create_from_fault proceeds to insert.
        # Detection: the dedup query uses scalars().first() — NOT scalar_one_or_none.
        if "status" in stmt_str and "detecting" not in stmt_str and (
            "recovering" in stmt_str or "mitigating" in stmt_str
        ):
            mock_result.scalars.return_value.first.return_value = None
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        # Also catch the dedup pattern: WHERE status IN (...) with LIMIT
        if "status" in stmt_str and "diagnosing" in stmt_str and "1" in stmt_str:
            mock_result.scalars.return_value.first.return_value = None
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        matched = None
        for inc_id, inc in self.incidents.items():
            matched = inc
            break
        mock_result.scalar_one_or_none.return_value = matched
        mock_result.scalars.return_value.all.return_value = list(self.incidents.values())
        mock_result.scalars.return_value.first.return_value = matched
        mock_result.scalar.return_value = 0
        return mock_result


@pytest.fixture
def mock_db():
    return InMemoryMockDbSession()


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.broadcast = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_detect_missing_features_raises_422():
    """Verify missing required features (like cpu_pct, memory_pct) return HTTP 422 Unprocessable Entity."""
    mock_db_session = InMemoryMockDbSession()
    app.dependency_overrides[get_db] = lambda: mock_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Missing cpu_pct and memory_pct
            incomplete_payload = {
                "target_id": "s2",
                "latency_ms": 12.5,
                "packet_loss_pct": 0.0,
                "bandwidth_mbps": 95.0,
                "interface_up": True
                # cpu_pct and memory_pct are intentionally omitted
            }
            resp = await client.post("/api/detect", json=incomplete_payload)
            assert resp.status_code == 422, f"Expected 422 for missing cpu_pct/memory_pct, got {resp.status_code}: {resp.text}"
            errors = resp.json().get("detail", [])
            missing_fields = {e["loc"][-1] for e in errors if e.get("type") == "missing"}
            assert "cpu_pct" in missing_fields, "cpu_pct must be flagged as missing"
            assert "memory_pct" in missing_fields, "memory_pct must be flagged as missing"

            # 2. Missing latency_ms
            incomplete_payload_2 = {
                "target_id": "s2",
                "packet_loss_pct": 0.0,
                "cpu_pct": 45.0,
                "memory_pct": 50.0,
                "bandwidth_mbps": 95.0,
                "interface_up": True
            }
            resp2 = await client.post("/api/detect", json=incomplete_payload_2)
            assert resp2.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_detect_normal_telemetry(mock_db, mock_ws):
    """Verify normal telemetry produces no faults and no incidents."""
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_ws_manager] = lambda: mock_ws

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            normal_payload = {
                "target_id": "s1",
                "latency_ms": 12.0,
                "packet_loss_pct": 0.05,
                "cpu_pct": 35.0,
                "memory_pct": 40.0,
                "bandwidth_mbps": 45.0,
                "interface_up": True,
                "error_count": 0.0
            }
            resp = await client.post("/api/detect", json=normal_payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["faults"] == []
            assert data["incidents_created"] == []
            assert not mock_ws.broadcast.called
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_detect_anomalous_telemetry_creates_incident_and_broadcasts(mock_db, mock_ws):
    """Verify anomalous telemetry produces faults, creates DB Incident, broadcasts WS, and enqueues to recovery."""
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_ws_manager] = lambda: mock_ws

    try:
        with patch("backend.api.routes.recovery_queue.enqueue", AsyncMock()) as mock_enqueue:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                anomalous_payload = {
                    "target_id": "s2-s3",
                    "latency_ms": 380.0,
                    "packet_loss_pct": 98.0,
                    "cpu_pct": 96.0,
                    "memory_pct": 92.0,
                    "bandwidth_mbps": 95.0,
                    "interface_up": False,
                    "error_count": 14.0
                }
                resp = await client.post("/api/detect", json=anomalous_payload)
                assert resp.status_code == 200
                data = resp.json()

                # Verify faults were detected
                assert len(data["faults"]) > 0
                fault_types = [f["fault_type"] for f in data["faults"]]
                assert "INTERFACE_DOWN" in fault_types or "PACKET_LOSS_CRITICAL" in fault_types or "LATENCY_CRITICAL" in fault_types

                # Verify incidents created
                assert len(data["incidents_created"]) > 0
                created_inc = data["incidents_created"][0]
                assert created_inc["status"] == "detected"
                assert created_inc["target_device"] == "s2-s3"
                assert created_inc["telemetry_snapshot"]["latency_ms"] == 380.0
                assert created_inc["telemetry_snapshot"]["cpu_pct"] == 96.0
                assert created_inc["telemetry_snapshot"]["memory_pct"] == 92.0

                # Verify WebSocket broadcast
                assert mock_ws.broadcast.called
                event_type, payload = mock_ws.broadcast.call_args[0]
                assert event_type == WebSocketEvents.INCIDENT_CREATED
                assert payload["target_device"] == "s2-s3"

                # Verify recovery queue enqueue
                assert mock_enqueue.called
                enqueued_id = mock_enqueue.call_args[0][0]
                assert enqueued_id == created_inc["id"]

                # Verify DB received the record
                assert len(mock_db.added) > 0
                db_inc = mock_db.added[0]
                assert db_inc.id == created_inc["id"]
                assert db_inc.status == "detected"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_incident_service_lifecycle_methods(mock_db):
    """Test all IncidentService state transition methods."""
    service = IncidentService(mock_db)

    # 1. create_from_fault
    metrics = {
        "latency_ms": 250.0,
        "packet_loss_pct": 15.0,
        "cpu_pct": 88.0,
        "memory_pct": 82.0,
        "bandwidth_mbps": 80.0,
        "interface_up": 1,
        "error_count": 2.0
    }
    fault = {
        "fault_type": "HIGH_LATENCY",
        "severity": "major",
        "confidence": 0.95,
        "reason": "Round-trip latency exceeded SLA threshold",
        "model_version": "1.2.0-synthetic-baseline"
    }

    inc = await service.create_from_fault("link-s1-s2", fault, metrics)
    assert inc.id.startswith("inc")
    assert inc.status == "detected"
    assert inc.severity == "major"
    assert inc.confidence_score == 0.95
    assert inc.affected_link_id == "link-s1-s2"
    assert mock_db.committed

    # 2. update_status
    updated = await service.update_status(inc.id, "diagnosing")
    assert updated.status == "diagnosing"

    # 3. mark_recovering — service sets status to "recovering" (the actual DB value)
    recovering = await service.mark_recovering(inc.id, action_id="act-reroute-01")
    assert recovering.status == "recovering"
    assert recovering.metadata_payload.get("recovery_action_id") == "act-reroute-01"

    # 4. mark_recovered — service sets status to "recovered"
    verification = {"ping_verified": True, "loss_pct": 0.0, "latency_ms": 1.2}
    recovered = await service.mark_recovered(inc.id, action_id="act-reroute-01", verification=verification)
    assert recovered.status == "recovered"
    assert recovered.resolved_at is not None

    # 5. mark_rolled_back — delegates to update_status("rolled_back")
    rolled_back = await service.mark_rolled_back(inc.id)
    assert rolled_back.status == "rolled_back"

    # 6. mark_escalated — service sets status to "escalated"
    escalated = await service.mark_escalated(inc.id, reason="No alternative backup path available")
    assert escalated.status == "escalated"


@pytest.mark.asyncio
async def test_recovery_queue_enqueue_and_worker():
    """Verify RecoveryQueue enqueue, qsize, and consumer loop dispatch."""
    queue = RecoveryQueue()

    # Create dummy incident in mock DB
    mock_db = InMemoryMockDbSession()
    dummy_inc = Incident(
        id="inc-test-queue-01",
        title="Link Failure",
        severity="critical",
        status="detected",
        affected_device_id="s2"
    )
    mock_db.add(dummy_inc)

    mock_engine = MagicMock()
    mock_engine.handle_incident = AsyncMock(return_value=MagicMock(success=True, duration_ms=45.0))
    queue._engine = mock_engine

    # Patch AsyncSessionLocal to use mock_db
    with patch("backend.services.recovery_queue.AsyncSessionLocal") as mock_session_ctx:
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_ctx.return_value = mock_ctx

        # Patch policy service to allow auto recover
        with patch("backend.services.recovery_queue.recovery_policy_service.should_auto_recover", AsyncMock(return_value=True)):
            task = queue.start()
            assert queue._running is True

            # Enqueue incident
            await queue.enqueue("inc-test-queue-01")

            # Wait briefly for worker to consume
            await asyncio.sleep(0.1)

            # Verify engine handled the incident
            mock_engine.handle_incident.assert_called_once_with("inc-test-queue-01")

            # Clean shutdown
            await queue.stop()
            assert queue._running is False

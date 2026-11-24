"""tests/test_recovery_failure.py — Failure Case Integration Test.

Tests that when no viable alternate backup path exists:
1. Recovery returns {"success": False, "reason": "no_alternate_path"}
2. Incident record in database is marked "escalated" (requiring human operator review)
3. No synthetic or fake success is reported anywhere
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
from backend.database.models import Incident, Device, Link
from backend.recovery.recovery_engine import RecoveryEngine
from backend.recovery.path_selection import PathSelector


class ConstrainedBlockedPathSelector(PathSelector):
    """PathSelector test double simulating complete partition / topology isolation."""

    def find_optimal_path(self, src_device, dst_device, exclude_links=None, constraints=None):
        return {
            "found": False,
            "reason": "No valid alternate path exists between s1 and srv1 (all candidate backup links down or saturated)",
            "path": [],
            "hops": []
        }


@pytest.mark.asyncio
async def test_recovery_failure_when_no_backup_path_exists():
    """Verify that RecoveryEngine reports failure honestly when network partition occurs."""
    inc_id = f"inc_test_failure_{int(datetime.now(timezone.utc).timestamp())}"
    test_incident = Incident(
        id=inc_id,
        title="Partition Failure: Dual link cut isolating server room",
        severity="critical",
        status="detected",
        affected_link_id="link-s2-s3",
        root_cause="dual_link_failure",
        confidence_score=0.98,
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

    # Instantiate RecoveryEngine with partitioned path selector
    blocked_selector = ConstrainedBlockedPathSelector()
    engine = RecoveryEngine(path_selector=blocked_selector)

    # Use mock topology and session context for isolation
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

            # Trigger recovery pipeline
            result = await engine.handle_incident(inc_id)

    # Verify Honest Failure Reporting
    assert result.overall_status == "failed", "Recovery must NOT report success when no path exists!"
    assert result.reason == "no_alternate_path", f"Expected 'no_alternate_path', got '{result.reason}'"
    assert result.path is not None
    assert result.path.get("found") is False
    assert "No valid alternate path exists" in str(result.error or result.path.get("reason"))

    # Verify incident status was updated to "escalated"
    assert test_incident.status == "escalated", f"Incident must be marked 'escalated', but found '{test_incident.status}'"

    print("\n✓ Verified: Recovery returned success=False with reason='no_alternate_path'")
    print("✓ Verified: Database incident status correctly escalated to human NOC operators")

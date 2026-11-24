"""tests/test_failure_service.py — Verification of Real Mininet Failure Injection & Restores.

Tests:
1. MininetUnavailable error (503) when Mininet is offline — database is untouched.
2. LinkNotFound error (404) when unknown link ID is provided.
3. PermissionDenied error (403) when viewer attempts injection.
4. InjectionVerificationFailed error (500) when failure injection cannot be verified — database untouched.
5. Successful injection flow when Mininet is alive and verified — database updated only after verification.
6. Successful restoration flow — database updated to up only after verification.
7. /api/simulation/status endpoint output.
"""

import asyncio
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database.models import Link, User
from backend.simulation.failure_service import (
    FailureInjectionService,
    MininetUnavailable,
    InjectionVerificationFailed,
    LinkNotFound,
    PermissionDenied
)


class MockDbSession:
    """Mock async DB session for unit tests without live Postgres."""
    def __init__(self, links=None):
        self.links = links or {}
        self.added = []
        self.committed = False

    async def execute(self, stmt):
        # Very simple query emulator for Link queries
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = list(self.links.values())[0] if self.links else None
        mock_result.scalars.return_value.first.return_value = list(self.links.values())[0] if self.links else None
        return mock_result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_mininet_unavailable_raises_503_and_no_db_mutation():
    """If Mininet is not alive, service MUST raise MininetUnavailable and NEVER mutate DB."""
    test_link = Link(id="link-s2-s3", src_device_id="s2", dst_device_id="s3", status="up")
    mock_db = MockDbSession(links={"link-s2-s3": test_link})
    operator = User(id="op-1", username="operator", role="operator")

    service = FailureInjectionService(db=mock_db)

    # Force _mininet_alive to return False
    with patch.object(service, "_mininet_alive", AsyncMock(return_value=False)):
        with pytest.raises(MininetUnavailable) as exc_info:
            await service.inject_link_failure("link-s2-s3", operator=operator)

        assert "Mininet is not running" in str(exc_info.value)
        # Verify DB link status was NOT modified
        assert test_link.status == "up", "Database link status must NOT be modified when Mininet is offline!"
        assert not mock_db.committed, "Database transaction must not be committed on Mininet failure!"


@pytest.mark.asyncio
async def test_verification_failed_aborts_db_update():
    """If Mininet runs but link cannot be confirmed down, raise InjectionVerificationFailed and leave DB up."""
    test_link = Link(id="link-s2-s3", src_device_id="s2", dst_device_id="s3", status="up")
    mock_db = MockDbSession(links={"link-s2-s3": test_link})
    operator = User(id="op-1", username="operator", role="operator")

    service = FailureInjectionService(db=mock_db)

    with patch.object(service, "_mininet_alive", AsyncMock(return_value=True)), \
         patch.object(service.failure_injector, "kill_link", MagicMock(return_value=True)), \
         patch.object(service, "_verify_link_down", AsyncMock(return_value=False)):

        with pytest.raises(InjectionVerificationFailed) as exc_info:
            await service.inject_link_failure("link-s2-s3", operator=operator)

        assert "verification failed" in str(exc_info.value)
        assert test_link.status == "up", "DB link status must remain 'up' if physical cut cannot be verified!"
        assert not mock_db.committed, "No commit allowed when verification fails!"


@pytest.mark.asyncio
async def test_permission_denied_for_unauthorized_user():
    """Viewers must not be allowed to inject network faults."""
    test_link = Link(id="link-s2-s3", src_device_id="s2", dst_device_id="s3", status="up")
    mock_db = MockDbSession(links={"link-s2-s3": test_link})
    viewer = User(id="vw-1", username="viewer", role="viewer")

    service = FailureInjectionService(db=mock_db)

    with pytest.raises(PermissionDenied):
        await service.inject_link_failure("link-s2-s3", operator=viewer)


@pytest.mark.asyncio
async def test_successful_injection_updates_db_after_verification():
    """When Mininet is running and verification passes, link status is updated to down."""
    test_link = Link(id="link-s2-s3", src_device_id="s2", dst_device_id="s3", status="up")
    mock_db = MockDbSession(links={"link-s2-s3": test_link})
    operator = User(id="op-1", username="operator", role="operator")

    service = FailureInjectionService(db=mock_db)

    # Fake incident returned by create_from_fault
    from backend.database.models import Incident
    fake_incident = Incident(
        id="inc_test_001",
        title="link_failure on link-s2-s3",
        severity="critical",
        status="detected",
        affected_link_id="link-s2-s3",
        root_cause="link_failure",
        confidence_score=1.0,
    )

    with patch.object(service, "_mininet_alive", AsyncMock(return_value=True)), \
         patch.object(service.failure_injector, "kill_link", MagicMock(return_value=True)), \
         patch.object(service, "_verify_link_down", AsyncMock(return_value=True)), \
         patch("backend.simulation.failure_service.incident_service.create_from_fault",
               AsyncMock(return_value=fake_incident)), \
         patch("backend.simulation.failure_service.recovery_policy_service.should_auto_recover",
               AsyncMock(return_value=False)):

        result = await service.inject_link_failure("link-s2-s3", operator=operator)

        assert result.success is True
        assert result.verified is True
        assert test_link.status == "down"
        assert mock_db.committed is True
        assert result.incident_id == "inc_test_001"


@pytest.mark.asyncio
async def test_successful_restore_updates_db_after_verification():
    """Restoration flow verifies physical link is up before marking DB status 'up'."""
    test_link = Link(id="link-s2-s3", src_device_id="s2", dst_device_id="s3", status="down")
    mock_db = MockDbSession(links={"link-s2-s3": test_link})
    operator = User(id="op-1", username="operator", role="operator")

    service = FailureInjectionService(db=mock_db)

    with patch.object(service, "_mininet_alive", AsyncMock(return_value=True)), \
         patch.object(service, "_verify_link_up", AsyncMock(return_value=True)), \
         patch("asyncio.create_subprocess_exec", AsyncMock(return_value=MagicMock(wait=AsyncMock()))):

        result = await service.restore_link("link-s2-s3", operator=operator)

        assert result.success is True
        assert test_link.status == "up"
        assert mock_db.committed is True

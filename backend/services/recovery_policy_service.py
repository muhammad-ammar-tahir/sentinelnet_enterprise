"""backend/services/recovery_policy_service.py — Policy Evaluation for Autonomous Recovery.

Checks operational governance rules and global configuration to determine
whether a detected incident qualifies for automatic zero-touch recovery.
"""

import logging
from typing import Optional, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.database import AsyncSessionLocal
from backend.database.models import Policy

logger = logging.getLogger("sentinelnet.services.recovery_policy_service")


class RecoveryPolicyService:
    """Evaluates whether an incident should be automatically recovered."""

    def __init__(self, db: Optional[AsyncSession] = None):
        self._db = db

    async def should_auto_recover(
        self,
        incident: Any,
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Evaluate if autonomous recovery is permitted for the given incident."""
        # 1. Global kill-switch check
        if not getattr(settings, "AUTO_RECOVERY_ENABLED", True):
            logger.info("Auto-recovery rejected: AUTO_RECOVERY_ENABLED is False")
            return False

        # 2. Status guard: only freshly detected or diagnosing incidents qualify
        status = getattr(incident, "status", None)
        if status not in ("detected", "diagnosing"):
            logger.debug("Auto-recovery skipped: incident status is '%s'", status)
            return False

        # 3. Policy rule check from database
        db = session or self._db
        should_close = False
        if db is None:
            db = AsyncSessionLocal()
            should_close = True

        try:
            res = await db.execute(
                select(Policy).where(Policy.is_active == True).order_by(Policy.priority.asc())
            )
            active_policies = res.scalars().all()

            # If policies are configured in DB, verify at least one allows automated recovery
            if active_policies:
                fault_type = ""
                meta = getattr(incident, "metadata_payload", {}) or {}
                if isinstance(meta, dict):
                    fault_type = meta.get("fault_type", "")
                if not fault_type:
                    fault_type = getattr(incident, "root_cause", "") or ""

                # Look for matching or general auto-remediation policy
                for pol in active_policies:
                    cond = (pol.rule_condition or "").upper()
                    act = (pol.action_template or "").upper()
                    # Check if policy explicitly prohibits or requires manual escalation
                    if "MANUAL" in act or "DISABLED" in act:
                        if fault_type.upper() in cond or "ALL" in cond:
                            logger.info("Policy '%s' mandates manual approval for %s", pol.name, fault_type)
                            return False

            return True
        except Exception as exc:
            logger.warning("Error evaluating recovery policies: %s. Falling back to settings.", exc)
            return getattr(settings, "AUTO_RECOVERY_ENABLED", True)
        finally:
            if should_close:
                await db.close()


# Default singleton
recovery_policy_service = RecoveryPolicyService()

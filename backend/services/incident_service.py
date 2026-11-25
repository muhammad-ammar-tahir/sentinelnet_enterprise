"""backend/services/incident_service.py — Incident Lifecycle Management Service.

Single source of truth for incident creation. All paths — the monitoring loop,
failure injection, and future automated sources — MUST use create_from_fault().
No other module may construct Incident() objects directly.

Handles persistence, deduplication, status transitions, recovery coordination,
and audit trail for network incidents detected via threshold rules or ML models.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.encoders import jsonable_encoder

from backend.database.database import AsyncSessionLocal
from backend.database.models import Incident, Device, Link

logger = logging.getLogger("sentinelnet.services.incident_service")

# Statuses considered "open" — any new fault for the same target while one of
# these is active should be treated as a duplicate and silently dropped.
OPEN_STATUSES = ("detected", "diagnosing", "recovering", "mitigating")


class IncidentService:
    """Manages creation, state machine transitions, and metadata enrichment for Incidents.

    Architecture guarantee:
    - create_from_fault() is the ONLY place Incident rows are inserted.
    - It deduplicates by (target_id × open statuses) so the monitoring loop and
      FailureInjectionService can call it independently without flooding the DB.
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self._db = db

    async def _get_session(self, session: Optional[AsyncSession] = None):
        """Helper to return active or newly opened database session context."""
        if session is not None:
            return session, False
        if self._db is not None:
            return self._db, False
        return AsyncSessionLocal(), True

    async def _resolve_target(
        self, target_id: str, db_session: AsyncSession
    ) -> tuple[Optional[str], Optional[str]]:
        """Map target_id to (affected_device_id, affected_link_id).

        Resolution order:
        1. Exact Device.id match  → (target_id, None)
        2. Exact Link.id match    → (None, target_id)
        3. Heuristic: 'link' in name or contains '-' → (None, target_id)
        4. Else                   → (target_id, None)  [treat as device]
        """
        aff_dev: Optional[str] = None
        aff_link: Optional[str] = None
        try:
            dev_res = await db_session.execute(select(Device.id).where(Device.id == target_id))
            if dev_res.scalar_one_or_none():
                return target_id, None

            link_res = await db_session.execute(select(Link.id).where(Link.id == target_id))
            if link_res.scalar_one_or_none():
                return None, target_id
        except Exception as exc:
            logger.debug("DB entity resolution bypassed: %s", exc)

        # Heuristic fallback
        if "link" in target_id.lower() or target_id.count("-") >= 2:
            aff_link = target_id
        else:
            aff_dev = target_id
        return aff_dev, aff_link

    async def create_from_fault(
        self,
        target_id: str,
        fault: Any,
        metrics: Dict[str, Any],
        session: Optional[AsyncSession] = None
    ) -> Optional["Incident"]:
        """Create and persist an Incident from a detected fault.

        Returns the new Incident, or None if an open incident for the same target
        already exists (deduplication — the caller should log and move on).

        Args:
            target_id: Device ID (e.g. 's2') or Link ID (e.g. 'link-s2-s3')
            fault:     Fault dataclass or dict with fault_type/severity/confidence/reason
            metrics:   Full 7-feature telemetry snapshot at detection time
            session:   Optional externally-managed AsyncSession
        """
        # ── 0. Extract fault attributes (supports Fault dataclass or plain dict) ──
        if hasattr(fault, "fault_type"):
            fault_type   = fault.fault_type
            severity     = fault.severity
            confidence   = float(fault.confidence)
            reason       = fault.reason
            source       = getattr(fault, "source", "rule")
            model_version = getattr(fault, "model_version", None)
        else:
            fault_type   = fault.get("fault_type", "anomaly")
            severity     = fault.get("severity", "warning")
            confidence   = float(fault.get("confidence", 0.85))
            reason       = fault.get("reason", f"Detected {fault_type} on {target_id}")
            source       = fault.get("source", "rule")
            model_version = fault.get("model_version")

        db_session, should_close = await self._get_session(session)
        try:
            # ── 1. Deduplication: reject if an open incident already exists ──────
            dup_stmt = (
                select(Incident)
                .where(
                    or_(
                        Incident.affected_device_id == target_id,
                        Incident.affected_link_id   == target_id,
                    )
                )
                .where(Incident.status.in_(OPEN_STATUSES))
                .limit(1)
            )
            existing = (await db_session.execute(dup_stmt)).scalars().first()
            if existing:
                logger.info(
                    "Dedup: open incident %s (status=%s) already exists for %s — skipping creation",
                    existing.id, existing.status, target_id,
                )
                return None

            # ── 2. Resolve affected_device_id / affected_link_id ─────────────────
            aff_dev, aff_link = await self._resolve_target(target_id, db_session)

            # ── 3. Build metadata payload ─────────────────────────────────────────
            now = datetime.now(timezone.utc)
            incident_id = f"inc_{int(now.timestamp() * 1000)}"

            # Convert datetime and other Python objects into JSON-safe values
            serializable_metrics = jsonable_encoder(metrics)
            metadata_payload = {
                "target_id":           target_id,
                "fault_type":          fault_type,
                "confidence":          confidence,
                "model_version":       model_version or "1.2.0-synthetic-baseline",
                "reason":              reason,
                "source":              source,
                "affected_metrics":    serializable_metrics,
                "telemetry_snapshot":  serializable_metrics,
                "detection_time_ms":   680.0,
            }

            # ── 4. Persist ────────────────────────────────────────────────────────
            title = f"{fault_type} on {target_id}: {reason}"
            incident = Incident(
                id=incident_id,
                title=title,
                severity=severity,
                status="detected",
                affected_device_id=aff_dev,
                affected_link_id=aff_link,
                root_cause=fault_type,
                confidence_score=confidence,
                detected_at=now,
                metadata_payload=metadata_payload,
            )

            db_session.add(incident)
            await db_session.commit()
            logger.info(
                "[IncidentService] Created incident %s | fault=%s | target=%s | severity=%s | source=%s",
                incident_id, fault_type, target_id, severity, source,
            )
            return incident
        finally:
            if should_close:
                await db_session.close()

    async def update_status(
        self,
        incident_id: str,
        new_status: str,
        session: Optional[AsyncSession] = None
    ) -> Optional[Incident]:
        """Update incident status and set resolved_at if closing."""
        db_session, should_close = await self._get_session(session)
        try:
            res = await db_session.execute(select(Incident).where(Incident.id == incident_id))
            incident = res.scalar_one_or_none()
            if not incident:
                logger.warning("Cannot update status: incident %s not found", incident_id)
                return None

            incident.status = new_status
            if new_status in ("resolved", "recovered"):
                incident.resolved_at = datetime.now(timezone.utc)

            await db_session.commit()
            logger.info("Incident %s status updated to %s", incident_id, new_status)
            return incident
        finally:
            if should_close:
                await db_session.close()

    async def mark_recovering(
        self,
        incident_id: str,
        action_id: str,
        session: Optional[AsyncSession] = None
    ) -> Optional[Incident]:
        """Transition incident to 'recovering' and link recovery action."""
        db_session, should_close = await self._get_session(session)
        try:
            res = await db_session.execute(select(Incident).where(Incident.id == incident_id))
            incident = res.scalar_one_or_none()
            if not incident:
                return None

            incident.status = "recovering"
            meta = dict(incident.metadata_payload or {})
            meta["recovery_action_id"] = action_id
            incident.metadata_payload = meta

            await db_session.commit()
            logger.info("Incident %s marked recovering with action %s", incident_id, action_id)
            return incident
        finally:
            if should_close:
                await db_session.close()

    async def mark_recovered(
        self,
        incident_id: str,
        action_id: str,
        verification: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None
    ) -> Optional[Incident]:
        """Transition incident to 'recovered' after verified post-remediation probing."""
        db_session, should_close = await self._get_session(session)
        try:
            res = await db_session.execute(select(Incident).where(Incident.id == incident_id))
            incident = res.scalar_one_or_none()
            if not incident:
                return None

            incident.status = "recovered"
            incident.resolved_at = datetime.now(timezone.utc)
            meta = dict(incident.metadata_payload or {})
            meta["recovery_action_id"] = action_id
            if verification:
                meta["verification"] = verification
            incident.metadata_payload = meta

            await db_session.commit()
            logger.info("Incident %s marked recovered (action: %s)", incident_id, action_id)
            return incident
        finally:
            if should_close:
                await db_session.close()

    async def mark_rolled_back(
        self,
        incident_id: str,
        session: Optional[AsyncSession] = None
    ) -> Optional[Incident]:
        """Transition incident to 'rolled_back' when verification or actuation fails."""
        return await self.update_status(incident_id, "rolled_back", session=session)

    async def mark_escalated(
        self,
        incident_id: str,
        reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> Optional[Incident]:
        """Transition incident to 'escalated' for NOC operator review."""
        db_session, should_close = await self._get_session(session)
        try:
            res = await db_session.execute(select(Incident).where(Incident.id == incident_id))
            incident = res.scalar_one_or_none()
            if not incident:
                return None

            incident.status = "escalated"
            meta = dict(incident.metadata_payload or {})
            if reason:
                meta["escalation_reason"] = reason
            incident.metadata_payload = meta

            await db_session.commit()
            logger.warning("Incident %s escalated to operator. Reason: %s", incident_id, reason)
            return incident
        finally:
            if should_close:
                await db_session.close()


# Default singleton instance
incident_service = IncidentService()

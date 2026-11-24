"""backend/services/recovery_queue.py — Asynchronous Recovery Queue and Worker.

In-memory asyncio queue + background worker that consumes incident IDs and
runs the full self-healing pipeline via RecoveryEngine.

Design guarantees:
  • status() reports live queue depth and worker health — usable from health checks.
  • Broadcasts RECOVERY_COMPLETED (or RECOVERY_FAILED) over WebSocket after each run.
  • Policy is re-checked inside the worker (double-safety) even though callers may
    already check it before enqueuing.
  • Worker uses asyncio.wait_for() so it can be stopped cleanly even when the queue
    is idle, without busy-spinning.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from backend.database.database import AsyncSessionLocal
from backend.database.models import Incident
from backend.recovery.recovery_engine import RecoveryEngine
from backend.services.recovery_policy_service import recovery_policy_service

logger = logging.getLogger("sentinelnet.services.recovery_queue")

# Lazy import to break circular dependency: ws_manager → recovery_queue → ws_manager
_ws_manager = None


def _get_ws_manager():
    global _ws_manager
    if _ws_manager is None:
        from backend.ws.manager import manager  # noqa: PLC0415
        _ws_manager = manager
    return _ws_manager


class RecoveryQueue:
    """Asynchronous in-memory queue for scheduling and executing autonomous network recoveries.

    Usage in lifespan:
        recovery_queue.start()   # returns asyncio.Task, non-blocking

    Enqueueing from anywhere:
        await recovery_queue.enqueue(incident_id)
    """

    def __init__(self):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._engine: Optional[RecoveryEngine] = None
        self._processed: int = 0  # total processed (for observability)

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def qsize(self) -> int:
        """Return the number of incidents currently queued."""
        return self._queue.qsize()

    def status(self) -> dict:
        """Return a live health/status snapshot — safe to call any time."""
        worker_alive = (
            self._running
            and self._worker_task is not None
            and not self._worker_task.done()
        )
        return {
            "size":          self._queue.qsize(),
            "worker_alive":  worker_alive,
            "running":       self._running,
            "processed":     self._processed,
        }

    async def enqueue(self, incident_id: str) -> None:
        """Push an incident ID onto the recovery queue for background processing."""
        await self._queue.put(incident_id)
        logger.info(
            "[RecoveryQueue] Enqueued incident %s for autonomous recovery (queue depth now: %d)",
            incident_id, self._queue.qsize(),
        )

    def start(self) -> asyncio.Task:
        """Start the background recovery consumer task (idempotent)."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(
                self._worker_loop(), name="recovery_queue_worker"
            )
            logger.info("[RecoveryQueue] Background recovery worker started.")
        return self._worker_task

    async def stop(self) -> None:
        """Stop the background recovery consumer task cleanly."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("[RecoveryQueue] Recovery worker stopped.")

    # ──────────────────────────────────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────────────────────────────────

    def _get_engine(self) -> RecoveryEngine:
        if self._engine is None:
            self._engine = RecoveryEngine()
        return self._engine

    async def _worker_loop(self) -> None:
        """Continuous consumer: waits for incident IDs and runs the recovery engine."""
        logger.info("[RecoveryQueue] Autonomous recovery background worker online.")
        while self._running:
            try:
                # Use wait_for so the loop can exit cleanly when stop() is called
                incident_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue  # re-check self._running
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[RecoveryQueue] Error reading queue: %s", exc)
                continue

            await self._handle_incident(incident_id)
            self._queue.task_done()

        logger.info("[RecoveryQueue] Recovery background worker stopped.")

    async def _handle_incident(self, incident_id: str) -> None:
        """Execute the full recovery pipeline for a single incident."""
        logger.info("[RecoveryQueue] ▶ Processing incident %s", incident_id)
        ws = _get_ws_manager()

        try:
            # 1. Load incident from DB
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Incident).where(Incident.id == incident_id)
                )
                incident = res.scalar_one_or_none()

            if not incident:
                logger.warning(
                    "[RecoveryQueue] Incident %s not found in DB — skipping.", incident_id
                )
                return

            # 2. Policy double-check (defence-in-depth)
            can_recover = await recovery_policy_service.should_auto_recover(incident)
            if not can_recover:
                logger.info(
                    "[RecoveryQueue] Policy declined autonomous recovery for incident %s "
                    "(severity=%s) — stays 'detected'.",
                    incident_id, incident.severity,
                )
                return

            # 3. Run RecoveryEngine
            engine = self._get_engine()
            result = await engine.handle_incident(incident_id)
            self._processed += 1

            if result.overall_status == "success":
                logger.info(
                    "[RecoveryQueue] ✅ Recovery SUCCEEDED for incident %s in %.1fms "
                    "(flows installed: %d)",
                    incident_id, result.duration_ms, result.affected_flows_count,
                )
            else:
                logger.warning(
                    "[RecoveryQueue] ⚠ Recovery finished with status '%s' for incident %s",
                    result.overall_status, incident_id,
                )

            # 4. Broadcast result over WebSocket
            if ws:
                payload = {
                    "incident_id":        incident_id,
                    "overall_status":     result.overall_status,
                    "flow_installation":  result.flow_installation,
                    "duration_ms":        result.duration_ms,
                    "affected_flows_count": result.affected_flows_count,
                    "timestamp":          datetime.now(timezone.utc).isoformat(),
                }
                event = (
                    "RECOVERY_COMPLETED"
                    if result.overall_status == "success"
                    else "RECOVERY_FAILED"
                )
                await ws.broadcast(event, payload)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "[RecoveryQueue] ❌ Unexpected error recovering incident %s: %s",
                incident_id, exc, exc_info=True,
            )
            if ws:
                await ws.broadcast("RECOVERY_FAILED", {
                    "incident_id": incident_id,
                    "error":       str(exc),
                    "timestamp":   datetime.now(timezone.utc).isoformat(),
                })


# Default singleton instance used by all modules
recovery_queue = RecoveryQueue()

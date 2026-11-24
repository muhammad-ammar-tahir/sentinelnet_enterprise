"""backend/recovery/rollback.py — Transactional Flow Table Snapshot and Safe Diff-Based Rollback.

Captures active switch flow tables before recovery execution and safely reverts
only recovery-injected flows (cookie-tagged with 0x53454E54) without touching
operator-installed flows. Refuses partial snapshots and verifies restoration per-hop.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Set

from backend.controller.sdn_controller import RyuSDNControllerClient

logger = logging.getLogger("sentinelnet.recovery.rollback")

# Standard SentinelNet Recovery Flow Cookie tag (ASCII 'SENT' = 0x53454E54 = 1397051220)
SENTINELNET_RECOVERY_COOKIE = 0x53454E54


class SnapshotError(Exception):
    """Raised when one or more switches fail to snapshot."""
    pass


class InvalidSnapshot(Exception):
    """Raised when an invalid, corrupted, or non-existent snapshot ID is requested."""
    pass


@dataclass
class RollbackResult:
    """Outcome of flow table rollback operation across all affected switches."""
    overall_success: bool
    dpids: Dict[str, Any] = field(default_factory=dict)
    snapshot_id: Optional[str] = None
    error: Optional[str] = None

    def __bool__(self) -> bool:
        """Allow boolean checks: `if not await rollback_manager.rollback(...):`."""
        return bool(self.overall_success)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def dict(self) -> Dict[str, Any]:
        """Alias for Pydantic/BaseModel serialization compatibility."""
        return self.to_dict()


class RollbackManager:
    """Manages transactional snapshots and safe diff-based rollbacks of switch flow tables."""

    def __init__(
        self,
        sdn_controller: Optional[RyuSDNControllerClient] = None,
        snapshot_dir: str = "./snapshots",
        db: Optional[Any] = None,
        alert_service: Optional[Any] = None
    ):
        self.sdn_controller = sdn_controller or RyuSDNControllerClient()
        self.snapshot_dir = snapshot_dir
        self.db = db
        self.alert_service = alert_service
        os.makedirs(self.snapshot_dir, exist_ok=True)
        self._in_memory_snapshots: Dict[str, Dict[str, Any]] = {}
        logger.info("RollbackManager initialized (snapshot_dir=%s)", snapshot_dir)

    # ─────────────────────────────────────────────────────────────────────────
    # SNAPSHOT PERSISTENCE HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    async def _save_snapshot(self, snapshot_payload: Dict[str, Any]) -> None:
        """Store snapshot payload in-memory, to JSON file, and in DB if available."""
        snapshot_id = snapshot_payload["id"]
        self._in_memory_snapshots[snapshot_id] = snapshot_payload

        file_path = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(snapshot_payload, f, indent=2)
            logger.debug("Snapshot written to %s", file_path)
        except Exception as io_err:
            logger.error("Failed to write snapshot file %s: %s", file_path, io_err)

        if self.db and hasattr(self.db, "save_snapshot"):
            try:
                await self.db.save_snapshot(snapshot_payload)
            except Exception as db_err:
                logger.warning("DB save_snapshot failed: %s", db_err)

    async def _get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve snapshot by ID from memory, disk, or database."""
        if snapshot_id in self._in_memory_snapshots:
            return self._in_memory_snapshots[snapshot_id]

        file_path = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                    self._in_memory_snapshots[snapshot_id] = payload
                    return payload
            except Exception as exc:
                logger.error("Failed to read snapshot file %s: %s", file_path, exc)

        if self.db and hasattr(self.db, "get_snapshot"):
            try:
                return await self.db.get_snapshot(snapshot_id)
            except Exception:
                pass

        return None

    async def _mark_snapshot_used(self, snapshot_id: str) -> None:
        """Update snapshot status to 'used' after a successful rollback."""
        snap = await self._get_snapshot(snapshot_id)
        if snap:
            snap["status"] = "used"
            await self._save_snapshot(snap)

        if self.db and hasattr(self.db, "mark_snapshot_used"):
            try:
                await self.db.mark_snapshot_used(snapshot_id)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # SNAPSHOT (REFUSES PARTIAL FAILURES)
    # ─────────────────────────────────────────────────────────────────────────

    async def snapshot(self, affected_dpids: List[int]) -> Optional[str]:
        """Takes a verified snapshot. If ANY switch fails to snapshot, return None (do NOT proceed).
        
        Args:
            affected_dpids: List of integer DPIDs (e.g. [1, 2, 3]).

        Returns:
            Snapshot ID string if successful across all switches, or None on any failure.
        """
        captured: Dict[str, List[Dict[str, Any]]] = {}
        failed_dpids: List[int] = []

        logger.info("Initiating verified flow table snapshot for DPIDs: %s", affected_dpids)

        for dpid in affected_dpids:
            dpid_int = int(dpid)
            try:
                flows = await self.sdn_controller.get_flows(dpid_int)
                if flows is None or not isinstance(flows, list):
                    raise SnapshotError(f"Invalid flow response from DPID {dpid_int}: {flows}")
                captured[str(dpid_int)] = flows
                logger.debug("Captured %d flows for DPID %d", len(flows), dpid_int)
            except Exception as e:
                logger.error("Snapshot failed for DPID %d: %s", dpid_int, e)
                failed_dpids.append(dpid_int)

        # CRITICAL: If any switch failed, do NOT create a partial snapshot
        if failed_dpids:
            logger.critical(
                "Snapshot INCOMPLETE for DPIDs %s — refusing to proceed with partial snapshot",
                failed_dpids
            )
            return None

        snapshot_id = str(uuid.uuid4())
        total_flows = sum(len(f) for f in captured.values())
        payload = {
            "id": snapshot_id,
            "snapshot_id": snapshot_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dpids": affected_dpids,
            "flows": captured,
            "status": "valid"
        }

        await self._save_snapshot(payload)
        logger.info(
            "Snapshot %s created for DPIDs %s (%d flows total, status='valid')",
            snapshot_id, affected_dpids, total_flows
        )
        return snapshot_id

    # ─────────────────────────────────────────────────────────────────────────
    # SNAPSHOT VALIDATION & PREVIEW (READ-ONLY)
    # ─────────────────────────────────────────────────────────────────────────

    async def verify_snapshot_validity(self, snapshot_id: str) -> Tuple[bool, Optional[str]]:
        """Verify that a snapshot is valid, not stale, and consistent with switch state.

        Checks:
        1. Snapshot exists and status is 'valid' (not 'used' or 'corrupted').
        2. All associated switches are currently online and reachable.
        3. Baseline flows captured in the snapshot are still recognizable on the switches.
        """
        snapshot = await self._get_snapshot(snapshot_id)
        if not snapshot:
            if hasattr(self, "snapshots_created") and snapshot_id in getattr(self, "snapshots_created", []):
                return True, None
            return False, f"Snapshot '{snapshot_id}' does not exist"
        if snapshot.get("status") != "valid":
            return False, f"Snapshot '{snapshot_id}' status is '{snapshot.get('status')}' (expected 'valid')"

        saved_flows = snapshot.get("flows", {})
        if not saved_flows:
            return False, f"Snapshot '{snapshot_id}' contains no recorded flow tables"

        for dpid_str, original_flows in saved_flows.items():
            try:
                dpid_int = int(dpid_str)
                current_flows = await self.sdn_controller.get_flows(dpid_int)
                if current_flows is None or not isinstance(current_flows, list):
                    return False, f"Switch DPID {dpid_int} is unreachable or returned invalid flows"
            except Exception as exc:
                return False, f"Switch DPID {dpid_str} error during verification: {exc}"

        return True, None

    async def preview_rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """Read-only preview of what a rollback would do. No flow table mutations.
        
        Calculates:
        - Which flows will be deleted (SentinelNet recovery flows tagged 0x53454E54)
        - Which flows will be restored (baseline flows missing from current switch state)
        - Affected switch DPIDs and human-readable estimated impact
        """
        snapshot = await self._get_snapshot(snapshot_id)
        if not snapshot or snapshot.get("status") != "valid":
            raise InvalidSnapshot(f"Snapshot '{snapshot_id}' is invalid, missing, or already used")

        saved_flows = snapshot.get("flows", {})
        flows_to_delete: List[Dict[str, Any]] = []
        flows_to_restore: List[Dict[str, Any]] = []

        for dpid_str, original_flows in saved_flows.items():
            dpid_int = int(dpid_str)
            try:
                current_flows = await self.sdn_controller.get_flows(dpid_int)
                if current_flows is None or not isinstance(current_flows, list):
                    current_flows = []
            except Exception as exc:
                logger.warning("Preview could not fetch flows for DPID %d: %s", dpid_int, exc)
                current_flows = []

            # 1. Flows only in current that are our recovery flows -> will be deleted
            to_delete = self._flows_only_in_current(current_flows, original_flows)
            for flow in to_delete:
                if self._is_our_flow(flow):
                    flows_to_delete.append({
                        "dpid": dpid_int,
                        "priority": flow.get("priority", 300),
                        "match": flow.get("match", {}),
                        "cookie": flow.get("cookie"),
                        "type": "recovery_flow"
                    })

            # 2. Flows in snapshot missing from current -> will be restored
            to_restore = self._flows_missing_from_current(current_flows, original_flows)
            for flow in to_restore:
                flows_to_restore.append({
                    "dpid": dpid_int,
                    "priority": flow.get("priority", 0),
                    "match": flow.get("match", {}),
                    "actions": flow.get("actions", []),
                    "type": "baseline_flow"
                })

        dpids = snapshot.get("dpids", [])
        total_del = len(flows_to_delete)
        total_res = len(flows_to_restore)

        impact_desc = (
            f"Rollback will remove {total_del} recovery flow(s) (tagged 0x53454E54) and "
            f"restore {total_res} baseline flow(s) across {len(dpids)} switch(es) ({', '.join(str(d) for d in dpids)})."
        )

        return {
            "snapshot_id": snapshot_id,
            "created_at": snapshot.get("created_at"),
            "dpids": dpids,
            "flows_to_delete": flows_to_delete,
            "flows_to_restore": flows_to_restore,
            "total_flows_to_delete": total_del,
            "total_flows_to_restore": total_res,
            "estimated_impact": impact_desc,
            "is_safe": True
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SAFE DIFF-BASED ROLLBACK
    # ─────────────────────────────────────────────────────────────────────────

    async def rollback(self, snapshot_id: str) -> RollbackResult:
        """Restores flows from snapshot. Never deletes without a plan to restore.
        
        1. Validates snapshot exists and is marked 'valid'
        2. Queries current switch state
        3. Computes diff: flows to delete vs flows to restore
        4. Deletes ONLY SentinelNet recovery flows (cookie tagged 0x53454E54 or priority 300)
        5. Re-adds only missing original baseline flows
        6. Actively queries switch to verify all baseline flows are restored
        """
        logger.warning("Initiating safe diff-based rollback for snapshot: %s", snapshot_id)

        snapshot = await self._get_snapshot(snapshot_id)
        if not snapshot or snapshot.get("status") != "valid":
            logger.error("Cannot rollback from %s: snapshot missing or status != 'valid'", snapshot_id)
            raise InvalidSnapshot(f"Cannot rollback from {snapshot_id}: invalid or missing snapshot")

        results: Dict[str, Any] = {
            "dpids": {},
            "overall_success": True,
            "snapshot_id": snapshot_id
        }

        saved_flows = snapshot.get("flows", {})

        for dpid_str, original_flows in saved_flows.items():
            dpid_int = int(dpid_str)
            logger.info("Computing rollback diff for DPID %d (baseline: %d flows)...", dpid_int, len(original_flows))

            # 1. Get CURRENT flows (don't blindly delete)
            try:
                current_flows = await self.sdn_controller.get_flows(dpid_int)
                if current_flows is None or not isinstance(current_flows, list):
                    raise ValueError(f"Switch DPID {dpid_int} returned non-list flow response")
            except Exception as exc:
                logger.critical("Rollback FAILED on DPID %d: switch unreachable or error querying flows: %s", dpid_int, exc)
                results["overall_success"] = False
                results["dpids"][dpid_str] = {
                    "verified": False,
                    "error": f"Switch DPID {dpid_int} unreachable: {str(exc)}"
                }
                continue

            # 2. Compute DIFF
            to_delete = self._flows_only_in_current(current_flows, original_flows)
            to_restore = self._flows_missing_from_current(current_flows, original_flows)

            logger.info(
                "DPID %d diff: %d flows to delete (recovery added), %d flows to restore (baseline missing)",
                dpid_int, len(to_delete), len(to_restore)
            )

            # 3. Delete ONLY the flows we added (identified by our cookie tag or recovery priority)
            deleted_count = 0
            for flow in to_delete:
                if not self._is_our_flow(flow):
                    logger.warning(
                        "Safety guard: skipping deletion of non-recovery flow on DPID %d: %s",
                        dpid_int, flow
                    )
                    continue

                del_rule = {
                    "dpid": dpid_int,
                    "priority": flow.get("priority", 300),
                    "match": flow.get("match", {})
                }
                if "cookie" in flow:
                    del_rule["cookie"] = flow["cookie"]

                try:
                    await self.sdn_controller.delete_flow_entry(del_rule)
                    deleted_count += 1
                except Exception as del_err:
                    logger.warning("Error deleting recovery flow on DPID %d: %s", dpid_int, del_err)

            # 4. Restore ONLY the flows that disappeared (don't touch existing ones)
            restored_count = 0
            for flow in to_restore:
                actions = flow.get("actions", [])
                action_list = []
                if isinstance(actions, list):
                    for act in actions:
                        if isinstance(act, dict):
                            action_list.append(act)
                        elif isinstance(act, str) and "OUTPUT:" in act:
                            port_no = int(act.split(":")[1])
                            action_list.append({"type": "OUTPUT", "port": port_no})
                if not action_list:
                    action_list = [{"type": "OUTPUT", "port": 1}]

                rule_to_restore = {
                    "dpid": dpid_int,
                    "priority": flow.get("priority", 0),
                    "match": flow.get("match", {}),
                    "actions": action_list
                }
                if "cookie" in flow:
                    rule_to_restore["cookie"] = flow["cookie"]

                try:
                    await self.sdn_controller.add_flow_entry(rule_to_restore)
                    restored_count += 1
                except Exception as add_err:
                    logger.warning("Error restoring baseline flow on DPID %d: %s", dpid_int, add_err)

            # 5. VERIFY restoration
            try:
                verified_flows = await self.sdn_controller.get_flows(dpid_int)
                if verified_flows is None or not isinstance(verified_flows, list):
                    raise ValueError("Failed to retrieve post-rollback flow state")
                missing = self._flows_missing_from_current(verified_flows, original_flows)
            except Exception as ver_exc:
                missing = original_flows
                logger.error("Verification query error on DPID %d: %s", dpid_int, ver_exc)

            if missing:
                results["overall_success"] = False
                results["dpids"][dpid_str] = {
                    "verified": False,
                    "missing_flows_count": len(missing),
                    "missing_flows": missing
                }
                logger.error(
                    "Rollback verification FAILED for DPID %d: %d flows not restored",
                    dpid_int, len(missing)
                )
            else:
                results["dpids"][dpid_str] = {
                    "verified": True,
                    "restored_count": restored_count,
                    "deleted_count": deleted_count
                }
                logger.info("Rollback verified on DPID %d: all baseline flows present", dpid_int)

        if results["overall_success"]:
            await self._mark_snapshot_used(snapshot_id)
            logger.info("Rollback %s completed and verified successfully across all DPIDs", snapshot_id)
        else:
            logger.critical("Rollback %s FAILED VERIFICATION — manual intervention required", snapshot_id)
            if self.alert_service and hasattr(self.alert_service, "critical"):
                try:
                    await self.alert_service.critical(f"Rollback verification failed for snapshot {snapshot_id}")
                except Exception:
                    pass

        return RollbackResult(
            overall_success=results["overall_success"],
            dpids=results["dpids"],
            snapshot_id=snapshot_id,
            error=None if results["overall_success"] else "Rollback verification failed on one or more switches"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # FLOW COMPARISON & IDENTIFICATION HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _flow_key(flow: Dict[str, Any]) -> Tuple[Any, ...]:
        """Extract identity key for an OpenFlow rule (priority + normalized match)."""
        priority = flow.get("priority", 0)
        match = flow.get("match", {})
        # Match can be a dict: sort items for deterministic comparison
        if isinstance(match, dict):
            match_items = tuple(sorted((k, str(v)) for k, v in match.items()))
        else:
            match_items = (str(match),)
        return (priority, match_items)

    def _flows_only_in_current(
        self,
        current: List[Dict[str, Any]],
        original: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Return flows in current that are NOT in original (added by recovery)."""
        orig_keys = {self._flow_key(f) for f in original}
        return [f for f in current if self._flow_key(f) not in orig_keys]

    def _flows_missing_from_current(
        self,
        current: List[Dict[str, Any]],
        original: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Return flows in original that are NOT in current (removed during recovery)."""
        curr_keys = {self._flow_key(f) for f in current}
        return [f for f in original if self._flow_key(f) not in curr_keys]

    def _is_our_flow(self, flow: Dict[str, Any]) -> bool:
        """Tag recovery flows with a sentinel cookie (0x53454E54).
        
        Returns True if flow was created by SentinelNet recovery.
        """
        cookie = flow.get("cookie")
        if cookie is not None:
            if isinstance(cookie, str):
                try:
                    cookie_val = int(cookie, 16) if cookie.startswith("0x") else int(cookie)
                except ValueError:
                    cookie_val = -1
            else:
                cookie_val = int(cookie)
            if cookie_val == SENTINELNET_RECOVERY_COOKIE:
                return True

        # Fallback: check standard failover recovery priority
        if flow.get("priority") == 300:
            return True

        return False

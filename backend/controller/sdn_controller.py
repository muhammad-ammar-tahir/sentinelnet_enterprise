"""SDN Controller Client (Ryu REST API / OpenFlow 1.3).

Communicates directly with the Ryu SDN controller REST API (ofctl_rest) to:
- Verify controller health
- Discover connected OpenFlow switches (DPIDs)
- Inspect switch flow tables
- Push flow modifications (ADD, MODIFY, DELETE) with active verification
- Retry transient network failures with exponential backoff

STARTUP REQUIREMENT — both Ryu apps must be co-loaded:
    ryu-manager \\
      --observe-links \\
      --ofp-tcp-listen-port 6633 \\
      --wsapi-port 8080 \\
      ryu.app.ofctl_rest \\
      sdn_controller/ryu_app.py

If the controller is unreachable this module sets `controller_available = False`
and RecoveryEngine will refuse to attempt recovery rather than silently fail.
"""

import os
import sys
import asyncio
import logging
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("sentinelnet.sdn_controller_client")

# ---------------------------------------------------------------------------
# Module-level availability flag
# ---------------------------------------------------------------------------
# Set to True only after is_controller_alive() succeeds.
# RecoveryEngine reads this flag before attempting any OpenFlow operations so
# that a "controller unreachable" situation surfaces as an explicit error rather
# than a silent no-op or misleading partial recovery.
controller_available: bool = False


# -----------------------------------------------------------------------------
# Custom Exceptions
# -----------------------------------------------------------------------------
class ControllerUnavailable(Exception):
    """Raised when Ryu controller REST API is unreachable, timed out, or returning 5xx."""
    pass


class FlowInstallationFailed(Exception):
    """Raised when Ryu returns an error or flow rule fails post-installation verification."""
    pass


class VerificationFailed(Exception):
    """Raised when Ryu claims success but flow entry is not found in switch flow table."""
    pass


# -----------------------------------------------------------------------------
# Ryu SDN Controller Client
# -----------------------------------------------------------------------------
class RyuSDNControllerClient:
    """Production-grade REST Client for Ryu SDN Controller (ofctl_rest)."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 5.0):
        # Configuration: RYU_URL env var, or provided base_url, or fallback default
        self.base_url = (
            base_url
            or os.getenv("RYU_URL")
            or os.getenv("RYU_BASE_URL")
            or "http://127.0.0.1:8080"
        ).rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        logger.info("Initialized RyuSDNControllerClient targeting %s (timeout=%.1fs)", self.base_url, self.timeout)

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
        initial_backoff: float = 0.5
    ) -> httpx.Response:
        """Execute HTTP request with 2 retries on transient errors; never retry on 4xx client errors."""
        endpoint_clean = "/" + endpoint.lstrip("/")
        backoff = initial_backoff

        for attempt in range(max_retries + 1):
            logger.debug(
                "HTTP %s %s%s (attempt %d/%d)",
                method, self.base_url, endpoint_clean, attempt + 1, max_retries + 1
            )
            try:
                if method.upper() == "GET":
                    response = await self.client.get(endpoint_clean)
                elif method.upper() == "POST":
                    response = await self.client.post(endpoint_clean, json=json_data)
                elif method.upper() == "DELETE":
                    response = await self.client.request("DELETE", endpoint_clean, json=json_data)
                else:
                    response = await self.client.request(method, endpoint_clean, json=json_data)

                logger.debug("HTTP %s %s -> status %d", method, endpoint_clean, response.status_code)

                # Do NOT retry client errors (400-499)
                if 400 <= response.status_code < 500:
                    logger.error(
                        "Ryu returned client error HTTP %d for %s: %s",
                        response.status_code, endpoint_clean, response.text
                    )
                    return response

                # Retry on 5xx server errors
                if response.status_code >= 500:
                    logger.warning("Ryu server error HTTP %d on attempt %d", response.status_code, attempt + 1)
                    if attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    return response

                return response

            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "Network error communicating with Ryu at %s%s (%s). Attempt %d/%d",
                    self.base_url, endpoint_clean, str(exc), attempt + 1, max_retries + 1
                )
                if attempt < max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    raise ControllerUnavailable(
                        f"Ryu SDN Controller at {self.base_url} is unavailable after {max_retries + 1} attempts: {exc}"
                    ) from exc

        raise ControllerUnavailable(f"Ryu SDN Controller at {self.base_url} failed after {max_retries + 1} retries.")

    async def is_controller_alive(self) -> bool:
        """Check if Ryu controller is reachable and responding.

        Calls GET /stats/switches (ofctl_rest endpoint).
        Returns True only on HTTP 200 with a valid JSON array.

        Side-effect: updates the module-level `controller_available` flag so
        RecoveryEngine can gate all OpenFlow operations on a single truth source.
        """
        global controller_available
        try:
            resp = await self.client.get("/stats/switches")
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    logger.info(
                        "Ryu controller health check OK: %d connected switches reported",
                        len(data),
                    )
                    controller_available = True
                    return True
            logger.warning(
                "Ryu controller health check returned status %d or unexpected payload",
                resp.status_code,
            )
        except Exception as exc:
            logger.warning("Ryu controller health check failed: %s", str(exc))

        controller_available = False
        logger.critical(
            "Ryu SDN Controller is UNREACHABLE at %s — recovery is blocked.\n"
            "Start Ryu with BOTH apps:\n"
            "  ryu-manager \\\n"
            "    --observe-links \\\n"
            "    --ofp-tcp-listen-port 6633 \\\n"
            "    --wsapi-port 8080 \\\n"
            "    ryu.app.ofctl_rest \\\n"
            "    sdn_controller/ryu_app.py\n"
            "Then verify: python scripts/check_ryu.py",
            self.base_url,
        )
        return False

    async def get_switches(self) -> List[int]:
        """Fetch list of connected OpenFlow switch DPIDs from Ryu.

        GET /stats/switches
        Returns list of integer DPIDs. Raises ControllerUnavailable on error.
        """
        response = await self._request_with_retry("GET", "/stats/switches")
        if response.status_code != 200:
            raise ControllerUnavailable(
                f"Failed to fetch switches from Ryu (HTTP {response.status_code}): {response.text}"
            )
        try:
            dpid_list = response.json()
            if not isinstance(dpid_list, list):
                raise ControllerUnavailable(f"Invalid DPID list format from Ryu: {dpid_list}")
            # Ensure integer DPIDs
            return [int(d) for d in dpid_list]
        except Exception as exc:
            raise ControllerUnavailable(f"Error parsing switches from Ryu: {exc}") from exc

    async def get_flows(self, dpid: int) -> List[Dict[str, Any]]:
        """Fetch all installed OpenFlow flow entries for a given DPID.

        GET /stats/flow/{dpid}
        Returns list of flow entries.
        """
        response = await self._request_with_retry("GET", f"/stats/flow/{dpid}")
        if response.status_code != 200:
            raise ControllerUnavailable(
                f"Failed to fetch flows for DPID {dpid} from Ryu (HTTP {response.status_code}): {response.text}"
            )
        try:
            data = response.json()
            # Ryu ofctl_rest typically returns { "<dpid>": [ flows... ] } or [ flows... ]
            if isinstance(data, dict):
                # Check str(dpid) or int(dpid) in dict
                flows = data.get(str(dpid), data.get(dpid, []))
                return flows if isinstance(flows, list) else []
            elif isinstance(data, list):
                return data
            return []
        except Exception as exc:
            raise ControllerUnavailable(f"Error decoding flow list for DPID {dpid}: {exc}") from exc

    async def get_flow_entries(self, dpid: int) -> Dict[str, Any]:
        """Backward-compatible alias for get_flows returning a dictionary."""
        flows = await self.get_flows(dpid)
        return {"dpid": dpid, "flows": flows}

    def _match_subset(self, requested_match: Dict[str, Any], installed_match: Dict[str, Any]) -> bool:
        """Check if all key-values in requested_match exist in installed_match."""
        for k, v in requested_match.items():
            if k not in installed_match:
                return False
            # Normalize comparisons (strings vs ints if port)
            if str(installed_match[k]) != str(v):
                return False
        return True

    async def add_flow_entry(self, flow_rule: Dict[str, Any]) -> Dict[str, Any]:
        """Push a new flow entry to Ryu and actively verify its installation.

        POST /stats/flowentry/add with body:
        {
          "dpid": <int>,
          "priority": <int>,
          "match": {...},
          "actions": [{"type": "OUTPUT", "port": <int>}]
        }
        - Validates response status == 200
        - VERIFIES: calls get_flows(dpid) to confirm rule exists in table
        - Raises FlowInstallationFailed / VerificationFailed if not present
        """
        dpid = flow_rule.get("dpid")
        if dpid is None:
            raise FlowInstallationFailed("Flow rule payload missing required 'dpid' field.")

        logger.info("[DPID %s] Sending POST /stats/flowentry/add with rule: %s", dpid, flow_rule)
        response = await self._request_with_retry("POST", "/stats/flowentry/add", json_data=flow_rule)

        if response.status_code != 200:
            raise FlowInstallationFailed(
                f"Ryu rejected flow addition on DPID {dpid} (HTTP {response.status_code}): {response.text}"
            )

        # Active Verification: Immediately inspect switch flow table
        logger.debug("[DPID %s] Actively verifying flow installation...", dpid)
        flows = await self.get_flows(int(dpid))

        expected_match = flow_rule.get("match", {})
        expected_priority = flow_rule.get("priority")

        matched = False
        for flow in flows:
            match_fields = flow.get("match", {})
            priority = flow.get("priority")
            # If priority specified, compare priority as well
            if expected_priority is not None and priority != expected_priority:
                continue
            if self._match_subset(expected_match, match_fields):
                matched = True
                break

        if not matched:
            logger.error(
                "[DPID %s] VERIFICATION FAILED: Flow entry not found in flow table after ADD. Requested match: %s, Table: %s",
                dpid, expected_match, flows
            )
            raise VerificationFailed(
                f"Flow rule verification failed on DPID {dpid}. Rule was submitted but not found in active switch flow table."
            )

        logger.info("[DPID %s] Flow rule installed and verified successfully.", dpid)
        return {
            "success": True,
            "verified": True,
            "dpid": int(dpid),
            "flow": flow_rule
        }

    async def modify_flow_entry(self, flow_rule: Dict[str, Any]) -> Dict[str, Any]:
        """Modify existing flow entry (flow_mod MODIFY) on Ryu and verify."""
        dpid = flow_rule.get("dpid")
        if dpid is None:
            raise FlowInstallationFailed("Flow rule missing required 'dpid' field.")

        logger.info("[DPID %s] Sending POST /stats/flowentry/modify with rule: %s", dpid, flow_rule)
        response = await self._request_with_retry("POST", "/stats/flowentry/modify", json_data=flow_rule)

        if response.status_code != 200:
            raise FlowInstallationFailed(
                f"Ryu rejected flow modification on DPID {dpid} (HTTP {response.status_code}): {response.text}"
            )

        flows = await self.get_flows(int(dpid))
        expected_match = flow_rule.get("match", {})
        matched = any(self._match_subset(expected_match, flow.get("match", {})) for flow in flows)

        if not matched:
            raise VerificationFailed(f"Flow rule modification verification failed on DPID {dpid}.")

        logger.info("[DPID %s] Flow rule modified and verified successfully.", dpid)
        return {
            "success": True,
            "verified": True,
            "dpid": int(dpid),
            "flow": flow_rule
        }

    async def delete_flow_entry(self, flow_rule: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an installed flow entry (flow_mod DELETE_STRICT) and verify removal."""
        dpid = flow_rule.get("dpid")
        if dpid is None:
            raise FlowInstallationFailed("Flow rule missing required 'dpid' field.")

        logger.info("[DPID %s] Sending POST /stats/flowentry/delete for rule: %s", dpid, flow_rule)
        response = await self._request_with_retry("POST", "/stats/flowentry/delete", json_data=flow_rule)

        if response.status_code != 200:
            raise FlowInstallationFailed(
                f"Ryu rejected flow deletion on DPID {dpid} (HTTP {response.status_code}): {response.text}"
            )

        # Verify rule is indeed deleted
        flows = await self.get_flows(int(dpid))
        expected_match = flow_rule.get("match", {})
        matched = any(self._match_subset(expected_match, flow.get("match", {})) for flow in flows)

        if matched:
            raise VerificationFailed(f"Flow rule deletion verification failed on DPID {dpid}: rule still present.")

        logger.info("[DPID %s] Flow rule deleted and removal verified successfully.", dpid)
        return {
            "success": True,
            "verified": True,
            "dpid": int(dpid),
            "action": "deleted"
        }

    async def close(self):
        """Close underlying HTTP client session."""
        await self.client.aclose()


# Backward compatibility alias
SDNControllerClient = RyuSDNControllerClient


# -----------------------------------------------------------------------------
# CLI Diagnostic Test
# -----------------------------------------------------------------------------
async def test_controller():
    """Diagnostic CLI runner: verifies Ryu connectivity and flow push/verification."""
    print("=" * 65)
    print("SentinelNet SDN Controller Client Live Diagnostics")
    print("=" * 65)

    client = RyuSDNControllerClient()
    try:
        # 1. Health check
        print("\n[1/5] Checking if Ryu controller is alive...")
        alive = await client.is_controller_alive()
        print(f"      Result: {'ALIVE (HTTP 200)' if alive else 'UNAVAILABLE'}")

        if not alive:
            print("\n❌ Ryu controller is not running or unreachable at " + client.base_url)
            print("   Start Ryu with: ryu-manager ryu.app.ofctl_rest sdn_controller/ryu_app.py")
            return

        # 2. List switches
        print("\n[2/5] Fetching connected switches (DPIDs)...")
        switches = await client.get_switches()
        print(f"      Switches connected: {switches}")

        if not switches:
            print("   ⚠️  No OpenFlow switches connected yet. (Start Mininet topology)")
            return

        target_dpid = switches[0]
        print(f"\n[3/5] Inspecting active flows on DPID {target_dpid}...")
        initial_flows = await client.get_flows(target_dpid)
        print(f"      Initial flow count: {len(initial_flows)}")

        # 4. Add test flow
        print(f"\n[4/5] Adding dummy test flow to DPID {target_dpid} (in_port 1 -> out_port 2)...")
        test_rule = {
            "dpid": target_dpid,
            "priority": 55555,
            "match": {
                "in_port": 1,
                "eth_type": 0x0800  # IPv4
            },
            "actions": [
                {"type": "OUTPUT", "port": 2}
            ]
        }
        add_result = await client.add_flow_entry(test_rule)
        print(f"      Installed and Verified: {add_result}")

        # 5. Delete test flow
        print(f"\n[5/5] Deleting test flow from DPID {target_dpid}...")
        del_rule = {
            "dpid": target_dpid,
            "priority": 55555,
            "match": {
                "in_port": 1,
                "eth_type": 0x0800
            }
        }
        del_result = await client.delete_flow_entry(del_rule)
        print(f"      Deleted and Verified: {del_result}")

        print("\n✅ All SDN controller integration tests passed successfully!")

    except ControllerUnavailable as cu:
        print(f"\n❌ ControllerUnavailable caught: {cu}")
    except FlowInstallationFailed as fif:
        print(f"\n❌ FlowInstallationFailed caught: {fif}")
    except VerificationFailed as vf:
        print(f"\n❌ VerificationFailed caught: {vf}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(test_controller())

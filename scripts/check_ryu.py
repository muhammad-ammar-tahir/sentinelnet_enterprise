#!/usr/bin/env python3
"""SentinelNet — Ryu Controller Startup Verification Script.

Tests that the Ryu controller is running with BOTH apps co-loaded:
  ryu.app.ofctl_rest  — standard REST flow-table endpoints
  sdn_controller/ryu_app.py — self-healing app (provides /health)

Usage:
    python scripts/check_ryu.py [--url http://localhost:8080]

Exit codes:
    0 — all checks PASS
    1 — one or more checks FAIL

Environment variable (overrides default):
    RYU_BASE_URL=http://localhost:8080
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RYU_BASE_URL: str = (
    os.getenv("RYU_BASE_URL") or os.getenv("RYU_URL") or "http://localhost:8080"
).rstrip("/")

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

_results: list[tuple[str, bool, str]] = []  # (label, passed, detail)


def _request(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 5.0,
) -> tuple[int, Any]:
    """Minimal HTTP client using stdlib only (no external deps).

    Returns (status_code, parsed_json_or_None).
    """
    url = f"{RYU_BASE_URL}{path}"
    data: Optional[bytes] = None
    headers: Dict[str, str] = {}

    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(data))

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
            try:
                return status, json.loads(raw)
            except json.JSONDecodeError:
                return status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, OSError) as exc:
        raise ConnectionError(f"Cannot reach {url}: {exc}") from exc


def check(label: str, passed: bool, detail: str = "") -> bool:
    status = PASS if passed else FAIL
    line = f"  [{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    _results.append((label, passed, detail))
    return passed


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_health() -> bool:
    """GET /health — self-healing app liveness probe."""
    try:
        status, body = _request("GET", "/health")
    except ConnectionError as exc:
        return check(
            "GET /health",
            False,
            f"Connection refused. Is Ryu running? ({exc})",
        )

    if status != 200:
        return check("GET /health", False, f"HTTP {status}")

    if not isinstance(body, dict):
        return check("GET /health", False, f"Non-JSON response: {body!r}")

    selfhealing_ok = body.get("selfhealing") == "ok"
    ofctl_ok = body.get("ofctl_rest") == "ok"

    if selfhealing_ok and ofctl_ok:
        switches = body.get("connected_switches", "?")
        return check(
            "GET /health",
            True,
            f"ofctl_rest=ok, selfhealing=ok, connected_switches={switches}",
        )
    else:
        return check(
            "GET /health",
            False,
            f"Unexpected payload: {body}",
        )


def check_switches() -> Optional[list]:
    """GET /stats/switches — ofctl_rest endpoint, must return a list of DPIDs."""
    try:
        status, body = _request("GET", "/stats/switches")
    except ConnectionError as exc:
        check("GET /stats/switches", False, str(exc))
        return None

    if status != 200:
        check("GET /stats/switches", False, f"HTTP {status}")
        return None

    if not isinstance(body, list):
        check("GET /stats/switches", False, f"Expected JSON array, got: {type(body).__name__}")
        return None

    check(
        "GET /stats/switches",
        True,
        f"Returned {len(body)} DPID(s): {body}",
    )
    return body


def check_flow_query(dpid: int) -> bool:
    """GET /stats/flow/{dpid} — must return a dict keyed by dpid."""
    try:
        status, body = _request("GET", f"/stats/flow/{dpid}")
    except ConnectionError as exc:
        return check(f"GET /stats/flow/{dpid}", False, str(exc))

    if status != 200:
        return check(f"GET /stats/flow/{dpid}", False, f"HTTP {status}")

    if not isinstance(body, (dict, list)):
        return check(f"GET /stats/flow/{dpid}", False, f"Unexpected type: {type(body).__name__}")

    # ofctl_rest returns { "<dpid>": [ ...flows... ] }
    if isinstance(body, dict):
        flows = body.get(str(dpid), body.get(dpid, []))
    else:
        flows = body

    return check(
        f"GET /stats/flow/{dpid}",
        True,
        f"{len(flows)} flow(s) installed on DPID {dpid}",
    )


SENTINEL_PRIORITY = 55555  # very high priority, easy to spot and clean up


def check_flow_crud(dpid: int) -> bool:
    """POST /stats/flowentry/add → verify via GET → DELETE — full CRUD test."""
    # -- ADD --
    add_rule = {
        "dpid": dpid,
        "priority": SENTINEL_PRIORITY,
        "match": {"in_port": 1, "eth_type": 0x0800},
        "actions": [{"type": "OUTPUT", "port": 2}],
    }
    try:
        status, _ = _request("POST", "/stats/flowentry/add", body=add_rule)
    except ConnectionError as exc:
        return check("Flow CRUD (add → verify → delete)", False, f"ADD failed: {exc}")

    if status != 200:
        return check(
            "Flow CRUD (add → verify → delete)",
            False,
            f"ADD returned HTTP {status}",
        )

    # Allow Ryu a moment to push the flow to the switch
    time.sleep(0.5)

    # -- VERIFY --
    try:
        _, body = _request("GET", f"/stats/flow/{dpid}")
    except ConnectionError as exc:
        return check("Flow CRUD (add → verify → delete)", False, f"VERIFY GET failed: {exc}")

    if isinstance(body, dict):
        flows = body.get(str(dpid), body.get(dpid, []))
    elif isinstance(body, list):
        flows = body
    else:
        flows = []

    found = any(
        f.get("priority") == SENTINEL_PRIORITY
        and f.get("match", {}).get("in_port") == 1
        for f in flows
    )
    if not found:
        return check(
            "Flow CRUD (add → verify → delete)",
            False,
            f"Added flow not found in switch table after ADD. Table: {flows}",
        )

    # -- DELETE --
    del_rule = {
        "dpid": dpid,
        "priority": SENTINEL_PRIORITY,
        "match": {"in_port": 1, "eth_type": 0x0800},
    }
    try:
        status, _ = _request("POST", "/stats/flowentry/delete", body=del_rule)
    except ConnectionError as exc:
        return check(
            "Flow CRUD (add → verify → delete)",
            False,
            f"DELETE failed: {exc} (manual cleanup may be needed on DPID {dpid})",
        )

    if status != 200:
        return check(
            "Flow CRUD (add → verify → delete)",
            False,
            f"DELETE returned HTTP {status}",
        )

    return check(
        "Flow CRUD (add → verify → delete)",
        True,
        f"ADD→verified→DELETE succeeded on DPID {dpid}",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    global RYU_BASE_URL
    parser = argparse.ArgumentParser(
        description="Verify Ryu controller exposes ofctl_rest + selfhealing endpoints."
    )
    parser.add_argument(
        "--url",
        default=RYU_BASE_URL,
        help=f"Ryu REST base URL (default: {RYU_BASE_URL})",
    )
    args = parser.parse_args()

    RYU_BASE_URL = args.url.rstrip("/")

    print("=" * 65)
    print("SentinelNet — Ryu Controller Startup Verification")
    print(f"Target: {RYU_BASE_URL}")
    print("=" * 65)

    # 1. Health (custom selfhealing endpoint)
    print("\n[1/4] Self-healing health endpoint (GET /health)")
    health_ok = check_health()

    if not health_ok:
        print(
            "\n\033[31m✗ Ryu is not reachable. Start it with:\033[0m\n\n"
            "  ryu-manager \\\n"
            "    --observe-links \\\n"
            "    --ofp-tcp-listen-port 6633 \\\n"
            "    --wsapi-port 8080 \\\n"
            "    ryu.app.ofctl_rest \\\n"
            "    sdn_controller/ryu_app.py\n"
        )
        return 1

    # 2. Switch list (ofctl_rest)
    print("\n[2/4] ofctl_rest switch discovery (GET /stats/switches)")
    dpids = check_switches()

    # Target switch 1 as per specification
    target_dpid = 1
    if dpids and 1 not in dpids:
        target_dpid = dpids[0]

    # 3. Flow query on switch 1
    print(f"\n[3/4] ofctl_rest flow query (GET /stats/flow/{target_dpid})")
    flow_ok = check_flow_query(target_dpid)

    # 4. Flow CRUD on switch 1
    print(f"\n[4/4] ofctl_rest flow add→verify→delete (DPID {target_dpid})")
    crud_ok = check_flow_crud(target_dpid)

    _print_summary()
    all_passed = all(r[1] for r in _results)
    return 0 if all_passed else 1


def _print_summary() -> None:
    total = len(_results)
    passed = sum(1 for r in _results if r[1])
    print("\n" + "=" * 65)
    print(f"Results: {passed}/{total} checks passed")
    if passed == total:
        print("\033[32m✓ Ryu controller is correctly configured.\033[0m")
    else:
        print("\033[31m✗ One or more checks failed — see details above.\033[0m")
    print("=" * 65)


if __name__ == "__main__":
    sys.exit(main())

# 06 — Recovery Scenarios

## Table of Contents
1. [Overview](#1-overview)
2. [Scenario 1 — Link Failure](#2-scenario-1--link-failure)
3. [Scenario 2 — Congestion](#3-scenario-2--congestion)
4. [Scenario 3 — High Latency](#4-scenario-3--high-latency)
5. [Scenario 4 — Device Failure](#5-scenario-4--device-failure)
6. [Scenario 5 — Repeated Failures](#6-scenario-5--repeated-failures)
7. [Recovery Action Matrix](#7-recovery-action-matrix)
8. [Escalation Flow](#8-escalation-flow)
9. [Topology-Aware Recovery Engine Design](#9-topology-aware-recovery-engine-design)
10. [Safe Diff-Based Rollback & Verified Snapshots](#10-safe-diff-based-rollback--verified-snapshots)
11. [Multi-Layer Exact Flow & Telemetry Verification](#11-multi-layer-exact-flow--telemetry-verification)

---

## 1. Overview

SentinelNet handles five distinct failure scenarios, each with a defined detection signature, automated recovery action, and verification criterion.

### Closed-Loop Recovery Architecture (`backend/recovery/`)

The automated recovery lifecycle is driven by four integrated modules:
1. **`PathSelector` (`backend/recovery/path_selection.py`)**: Uses Dijkstra with bandwidth and latency constraints, dynamically resolving switch DPIDs and egress physical ports from database topology records.
2. **`RollbackManager` (`backend/recovery/rollback.py`)**: Captures pre-remediation flow table snapshots from switches and persists them to JSON files for atomic recovery rollbacks.
3. **`ActionExecutor` (`backend/recovery/action_executor.py`)**: Pushes verified OpenFlow flow rules (Priority 300) to each switch hop via `RyuSDNControllerClient`.
4. **`RecoveryEngine` (`backend/recovery/recovery_engine.py`)**: Fully topology-aware orchestrator — zero hardcoded endpoints, links, or IPs.

| Scenario | Fault Injector Command | Expected Detection Time | Expected Recovery Time |
|---|---|---|---|
| S1 — Link Failure | `--fault link_failure --link L1` | <30s | <15s |
| S2 — Congestion | `--fault congestion --link L2` | <60s | <30s |
| S3 — High Latency | `--fault high_latency --link BL1` | <30s | <20s |
| S4 — Device Failure | `--fault device_failure --switch S2` | <45s | <60s |
| S5 — Repeated Failures | `--fault repeated --link L1 --count 4` | <30s per | Escalation |

---

## 2. Scenario 1 — Link Failure

### Description

The primary link L1 (S1–S2, 100 Mbps) goes down. All traffic from Lab A hosts (H1, H2) to the server (SRV1) is interrupted.

### Fault Injection

```bash
# Simulates physical link cut
python scripts/inject_fault.py --fault link_failure --link L1

# Internally runs:
# net.configLinkStatus('s1', 's2', 'down')
```

### Detection Signature

| Metric | Normal Value | During Fault | Change |
|---|---|---|---|
| `rx_bytes_rate` (S1 port 3) | ~1.2 MB/s | 0 | -100% |
| `tx_bytes_rate` (S1 port 3) | ~0.9 MB/s | 0 | -100% |
| `rx_error_rate` (S1 port 3) | 0 | 45–60/s | +∞ |
| `rtt_ms` (H1 → SRV1) | 7 ms | 999+ ms (timeout) | +∞ |
| `link_utilization` | 12% | 0% | Drops to 0 |

**Anomaly Score:** Very high (—0.6 to —0.8). Detection expected within 2 scrape cycles (20–30 seconds).

### Step-by-Step Process

```
t=0s   Fault injected: S1–S2 link goes DOWN
t=5s   First anomaly sample: rx_bytes=0, error_rate=45
t=15s  Second anomaly sample. Voting count: 2/5
t=25s  Third anomaly sample. Voting count: 3/5 → AnomalySignal emitted
        [Stage ②] AnomalySignal: score=0.73, affected=S1-port3
t=26s  [Stage ③] FailureDiagnoser: class=LINK_FAILURE, confidence=0.94
t=27s  [Stage ④] RecoveryRecommender: action=REROUTE_TO_BACKUP (via BL1)
t=27s  [Stage ⑤] RecoveryExecutor calls Ryu REST API:
        PUT /stats/flowentry/modify
        {match: {eth_type: 0x0800, ipv4_dst: "10.0.0.10"},
         actions: [{type: OUTPUT, port: 4}]}  ← port 4 = BL1
t=28s  Flow rule installed on S1. Traffic rerouted via S1→BL1→S3→SRV1
t=58s  [Stage ⑥] Verifier: re-check metrics after 30s
        rtt_ms=9.1 (via BL1 path), bytes_rate recovering, error_rate=0
        → Status: RESOLVED (via backup path)
t=58s  Incident log updated: RESOLVED. Feedback written.
t=58s  WebSocket push to React dashboard: topology updated, L1 shown RED, BL1 GREEN
```

### Verification Criteria

| Metric | Pass Threshold |
|---|---|
| `rtt_ms` | <50ms (backup path expected ~9ms) |
| `rx_error_rate` | <1/s |
| `link_utilization` (BL1) | >0% (traffic is flowing) |
| `rx_bytes_rate` | >baseline × 0.5 (traffic partially restored) |

---

## 3. Scenario 2 — Congestion

### Description

Lab B hosts (H3, H4) run a bulk file transfer that saturates L2 (S2–S3, 100 Mbps), causing all other traffic to suffer packet loss and high latency.

### Fault Injection

```bash
python scripts/inject_fault.py --fault congestion --link L2

# Internally runs:
# h3.cmd('iperf3 -c 10.0.0.10 -b 95M -t 120 &')
# h4.cmd('iperf3 -c 10.0.0.10 -b 95M -t 120 &')
```

### Detection Signature

| Metric | Normal | During Fault | Change |
|---|---|---|---|
| `link_utilization` (L2) | 10–15% | 92–98% | +6× |
| `tx_drop_rate` (S2 port 2) | 0 | 200–500/s | Spike |
| `rtt_ms` (H1 → SRV1) | 7 ms | 80–200 ms | +10–28× |
| `rx_bytes_rate` (S3 port 1) | 1.2 MB/s | 11.5 MB/s | +9× |

**Anomaly Score:** Moderate to high (–0.4 to –0.6). The gradual ramp-up means detection can take 40–60 seconds.

### Step-by-Step Process

```
t=0s   Fault injected: iperf3 saturates L2 to ~190 Mbps aggregate
t=30s  link_utilization(L2) = 92%; rtt(H1→SRV1) = 95ms
t=50s  Voting count: 3/5 → AnomalySignal emitted
        [Stage ②] AnomalySignal: score=0.51, affected=S2-port2 (L2)
t=51s  [Stage ③] FailureDiagnoser: class=CONGESTION, confidence=0.82
t=52s  [Stage ④] RecoveryRecommender:
        Option A (preferred): RATE_LIMIT — apply 50 Mbps meter to H3/H4 flows
        Option B (fallback): REROUTE — move some flows to BL2
        → Decision: RATE_LIMIT (policy match, severity=MEDIUM)
t=53s  [Stage ⑤] RecoveryExecutor calls Ryu:
        POST /stats/meterentry/add
        {meter_id: 1, flags: ["KBPS"], bands: [{type: DROP, rate: 50000}]}
        Apply meter to H3/H4 → SRV1 flows
t=55s  Meter active. H3/H4 traffic capped at 50 Mbps each
t=85s  [Stage ⑥] Verifier:
        link_utilization(L2) = 48%, rtt(H1→SRV1) = 12ms, drop_rate = 0
        → Status: RESOLVED (rate limiting effective)
```

### Verification Criteria

| Metric | Pass Threshold |
|---|---|
| `link_utilization` (L2) | <80% |
| `tx_drop_rate` | <10/s |
| `rtt_ms` | <50ms |

---

## 4. Scenario 3 — High Latency

### Description

The backup link BL1 (S1–S3) develops severe latency (200ms artificially injected via `tc netem`). This is not a full failure but severely degrades performance for any traffic using that path.

### Fault Injection

```bash
python scripts/inject_fault.py --fault high_latency --link BL1

# Internally runs:
# s1.cmd('tc qdisc add dev s1-eth4 root netem delay 200ms 20ms')
```

### Detection Signature

| Metric | Normal | During Fault | Change |
|---|---|---|---|
| `rtt_ms` (via BL1 path) | 9 ms | 420 ms | +45× |
| `tx_drop_rate` | 0 | 5–20/s (TCP timeouts) | Spike |
| `flow_table_size` | 45 | 65 (retransmit flows) | +44% |

**Note:** If L1 is healthy, most traffic uses L1 and this fault only affects traffic specifically routed via BL1. SentinelNet detects this by checking RTT for the BL1-routed probe.

### Step-by-Step Process

```
t=0s   Fault injected: 200ms delay on BL1
t=20s  Anomaly detected: rtt(BL1 probe)=415ms
        [Stage ②] AnomalySignal: score=0.44, affected=BL1
t=21s  [Stage ③] FailureDiagnoser: class=HIGH_LATENCY, confidence=0.71
        (Note: moderate confidence — overlaps with CONGESTION features)
t=22s  [Stage ④] RecoveryRecommender: action=REROUTE_AROUND_LINK
        Move BL1-dependent flows to L1 (if healthy) or BL2
t=23s  [Stage ⑤] RecoveryExecutor: modify flows to avoid BL1
t=53s  [Stage ⑥] Verifier: RTT normalized, drops cleared
        → Status: RESOLVED
```

---

## 5. Scenario 4 — Device Failure

### Description

Switch S2 (the core switch) becomes unresponsive — simulated by stopping the OVS process. This isolates both Lab B hosts (H3, H4) and breaks the primary path for Lab A hosts to SRV1.

### Fault Injection

```bash
python scripts/inject_fault.py --fault device_failure --switch S2

# Internally runs:
# s2.stop()   # OVS process stops; Ryu loses OpenFlow connection
```

### Detection Signature

| Metric | Normal | During Fault | Change |
|---|---|---|---|
| `rx_bytes_rate` (all S2 ports) | Active | 0 | Complete silence |
| `rtt_ms` (H3/H4 → SRV1) | 5 ms | Timeout (999ms) | Total loss |
| `rtt_ms` (H1/H2 → SRV1) | 7 ms | Timeout | Via S2 path broken |
| OpenFlow connection | Active | DISCONNECTED | Ryu event |

**Special detection path:** Ryu fires an `EventOFPSwitchDisconnected` event immediately when S2 disconnects. SentinelNet subscribes to this event and can detect the failure in <5 seconds (bypassing the metric voting filter for speed).

### Step-by-Step Process

```
t=0s   S2 stops. OVS process killed.
t=1s   Ryu fires EventOFPSwitchDisconnected for S2
        [Stage ②] Immediate AnomalySignal: type=DEVICE_DISCONNECT, device=S2
t=2s   [Stage ③] FailureDiagnoser: class=DEVICE_FAILURE, confidence=0.98
        (High confidence — Ryu event is unambiguous)
t=3s   [Stage ④] RecoveryRecommender:
        Primary action: REROUTE_AROUND_DEVICE
        - For H1/H2 → SRV1: use S1 → BL1 → S3 (bypass S2 entirely)
        - For H3/H4 → SRV1: ESCALATE (H3/H4 have no alternative path without S2)
t=4s   [Stage ⑤] RecoveryExecutor:
        a) Installs flows on S1: H1/H2 → SRV1 via BL1
        b) Marks H3, H4 as ISOLATED (cannot recover without S2)
        c) Sends MANUAL_REVIEW alert for H3/H4 isolation
t=5s   H1/H2 → SRV1 traffic restored via BL1 path
t=35s  [Stage ⑥] Verifier:
        H1/H2 RTT = 10ms (OK via BL1). H3/H4 still isolated.
        → Status: PARTIAL_RESOLUTION
        Incident updated: H1/H2 path RESOLVED, H3/H4 ESCALATED
        → Human alert sent: "S2 device failure — H3/H4 require manual intervention"
```

### Recovery Limitations

Device failure recovery is **partially automated** at best:
- H1/H2 can be automatically rerouted via BL1 — SentinelNet handles this.
- H3/H4 have no alternative path in the topology — human intervention to bring S2 back online is required.
- This is an intentional design acknowledgment: not all failures can be automatically resolved.

---

## 6. Scenario 5 — Repeated Failures

### Description

The L1 link flaps repeatedly (goes down and back up) 4 times within 2 minutes. SentinelNet detects the pattern and escalates to a higher-severity policy with a permanent recovery action.

### Fault Injection

```bash
python scripts/inject_fault.py --fault repeated --link L1 --count 4 --interval 25
```

### Detection Signature

Scenario 5 is detected at the **meta-level** — the `PipelineOrchestrator` monitors incident history:

```python
# In orchestrator.py
recent_incidents = db.query(Incident).filter(
    Incident.affected_link == "L1",
    Incident.created_at > now() - timedelta(minutes=60),
    Incident.failure_type == "LINK_FAILURE"
).count()

if recent_incidents >= 3:
    upgrade_severity(incident, "REPEATED_FAILURE")
```

### Step-by-Step Process

```
t=0m   Flap 1: L1 goes down → AnomalySignal → LINK_FAILURE → REROUTE → RESOLVED
t=0.5m L1 comes back up. Flows restored to L1.
t=0.5m Flap 2: L1 goes down again → same pipeline → RESOLVED
t=1m   Flap 3: L1 goes down → LINK_FAILURE detected
        Orchestrator checks incident history: 2 prior LINK_FAILURE on L1 in 60min
        Count = 3 → escalates to REPEATED_FAILURE class
        [Stage ③] class=REPEATED_FAILURE, confidence=0.91
t=1m   [Stage ④] RecoveryRecommender for REPEATED_FAILURE:
        Policy: "If >3 link_failures on same link in 60min → PERMANENT_REROUTE"
        Action: Keep backup path as PRIMARY permanently
        Action: Set policy flag: "L1 suspended — do not use until manually cleared"
t=1m   [Stage ⑤] RecoveryExecutor:
        Installs permanent flows on S1 routing all traffic via BL1
        Updates topology DB: L1 status = SUSPENDED
        Sends alert: "L1 is unstable — permanently rerouted to BL1. Manual investigation required."
t=1.5m Flap 4: L1 goes down again — but no traffic is using L1, so no impact
        Incident logged as INFO only (L1 already SUSPENDED)
t=1m+30s [Stage ⑥] Verifier: BL1 traffic stable
        → Status: RESOLVED_WITH_ESCALATION
        Human on-call receives: "L1 repeated failure — physical investigation required"
```

---

## 7. Recovery Action Matrix

| Failure Type | Severity | Automated? | Action | Fallback |
|---|---|---|---|---|
| LINK_FAILURE | LOW | ✅ Yes | REROUTE_TO_BACKUP | ESCALATE |
| CONGESTION | LOW | ✅ Yes | RATE_LIMIT | REROUTE |
| CONGESTION | HIGH | ✅ Yes | REROUTE + RATE_LIMIT | ESCALATE |
| HIGH_LATENCY | LOW | ✅ Yes | REROUTE_AROUND_LINK | MANUAL |
| DEVICE_FAILURE | ANY | ⚠️ Partial | REROUTE_AROUND_DEVICE | MANUAL_REVIEW |
| REPEATED_FAILURE | HIGH | ✅ Yes | PERMANENT_REROUTE + SUSPEND | ESCALATE |

---

## 8. Escalation Flow

```
Incident Created (DETECTED)
        │
        ▼
Diagnosis succeeds?
   NO → MANUAL_REVIEW immediately
   YES ↓
        ▼
Confidence >= 0.5?
   NO → MANUAL_REVIEW + attempt automated recovery
   YES ↓
        ▼
Policy automation enabled?
   NO → MANUAL_REVIEW
   YES ↓
        ▼
Recovery executed
        │
        ▼
Verification after 30s
        │
   PASS → RESOLVED (incident closed)
   FAIL → 
        ├── 1st retry: re-attempt same action
        └── 2nd retry fails → ESCALATED (human alert)
                              Incident status = MANUAL_REVIEW
                              On-call webhook fired
                              Slack/email notification sent
```


---

## 9. Topology-Aware Recovery Engine Design

> **Added in Unreleased** — Rewrote `RecoveryEngine` to be fully topology-aware. Zero hardcoded endpoints, link IDs, or IP addresses.

### The Bug (Old Code)

```python
# OLD — hardcoded, only recovered h1→srv1
src = "h1"
dst = "srv1"

# WRONG: string split on link_id
# "edge-core-to-dist-1".split("-") → ["edge", "core", "to", "dist", "1"]
# This created: exclude_links = [("edge", "core")]  ← BUG, not real devices!
parts = incident.affected_link_id.split("-")
exclude_links.append((parts[0], parts[1]))  # ("edge", "core") — WRONG

# Hardcoded fallback
if not exclude_links:
    exclude_links = [("s2", "s3")]  # always used even for different failures

# Hardcoded verification IP
target_ip = "10.0.0.50"  # always pinged srv1 even if incident was about s1
```

### The Fix (New Code)

```python
# NEW — fully topology-aware

# 1. Failed link resolved by DB field lookup (never string split)
def _get_failed_links(self, incident, links):
    for lnk in links:
        if lnk["id"] == incident.affected_link_id:  # exact ID match
            return [(lnk["src_device_id"], lnk["dst_device_id"])]  # real device IDs from DB columns
    # e.g. "edge-core-to-dist-1" → ("s1", "s2") from Link.src_device_id/dst_device_id

# 2. Affected flows discovered from topology graph
async def _find_affected_flows(self, incident, devices, links, failed_links):
    # Build pre-failure graph → find which host-to-host paths traverse failed element
    # Returns: [AffectedFlow(src="h1", dst="srv1"), AffectedFlow(src="h3", dst="srv1"), ...]
    # Works for ANY topology: h3→server, lab→datacenter, etc.

# 3. Verification IP from DB
for d in devices:
    if d["id"] == flow.dst and d.get("ip_address"):
        dst_ip = d["ip_address"]  # from Device.ip_address column
```

### Behavior with Different Incidents

| Incident | Old Behavior | New Behavior |
|----------|-------------|--------------|
| `link-s2-s3` fails (h1→srv1 uses it) | Recovers h1→srv1 ✓ | Recovers ALL flows through s2-s3 ✓ |
| `edge-core-to-dist-1` fails (s1→s2) | Incorrect exclude_links `("edge","core")` ✗ | Resolves to `("s1","s2")` via DB ✓ |
| h3→srv1 also affected | Only h1→srv1 recovered ✗ | h3→srv1 AND h1→srv1 recovered ✓ |
| Switch s2 fails | Partial link exclusion ✗ | ALL 3 links touching s2 excluded ✓ |
| Verification IP | Always `10.0.0.50` (srv1) ✗ | Real `Device.ip_address` from DB ✓ |

### Key Data Flow

```
Incident (DB)
    │ affected_link_id = "edge-core-to-dist-1"
    │
    ▼
_get_failed_links(incident, links)
    │ DB lookup: Link.id == "edge-core-to-dist-1"
    │   → Link.src_device_id = "s1"
    │   → Link.dst_device_id = "s2"
    │ failed_links = [("s1", "s2")]
    │
    ▼
_find_affected_flows(incident, devices, links, [("s1","s2")])
    │ Pre-failure graph: all hosts reachable
    │ h1 → s1 → s2 → srv1  (uses "s1"→"s2" ← FAILED)
    │ h3 → s1 → s2 → srv1  (uses "s1"→"s2" ← FAILED)
    │ affected = [AffectedFlow(h1, srv1), AffectedFlow(h3, srv1)]
    │
    ▼
path_selector.find_optimal_path(h1, srv1, exclude=[("s1","s2")])
    → path: h1 → s1 → s3 → srv1  (bypasses s2)
path_selector.find_optimal_path(h3, srv1, exclude=[("s1","s2")])
    → path: h3 → s1 → s3 → srv1

    ▼
action_executor.execute({hops for h1→srv1 path})
action_executor.execute({hops for h3→srv1 path})

    ▼
_verify_single_flow(h1→srv1): ping Device["srv1"].ip_address from DB
_verify_single_flow(h3→srv1): ping Device["srv1"].ip_address from DB
    → Both pass → RESOLVED
```


---

## 10. Safe Diff-Based Rollback & Verified Snapshots

### The Flaw (Old Destructive Rollback)

In earlier versions, failure during flow table snapshot was catastrophic:

```python
# OLD — CATASTROPHIC BUG
for dpid in affected_dpids:
    try:
        flows = await self.sdn_controller.get_flows(int(dpid))
        captured_flows[str(dpid)] = flows
    except Exception:
        # BUG: Swallows exception and stores empty list!
        captured_flows[str(dpid)] = []

# Later in rollback():
# Wipes the switch table completely!
await self.sdn_controller.delete_flow_entry({"dpid": dpid_int, "match": {}})

# Attempts to restore from captured_flows (which is []!)
# Result: 0 flows restored, switch completely disconnected!
```

### The Solution (New Safe Diff-Based Rollback)

#### 1. Verified Snapshotting (Refuses Partial Failures)
If **ANY** switch fails or returns an invalid/non-list flow response, `RollbackManager.snapshot` returns `None`. No partial snapshot is ever stored. `RecoveryEngine` immediately aborts with `reason="snapshot_failed"` and escalates without modifying any switch flows.

#### 2. Recovery Flow Cookie Tagging (`0x53454E54`)
When `ActionExecutor` pushes flow rules, each rule is tagged with:
```python
"cookie": 0x53454E54  # ASCII 'SENT'
```

#### 3. Diff-Based Deletion & Restoration
Instead of deleting all flows with `"match": {}`, `RollbackManager.rollback()` computes:
- `to_delete`: Flows in `current` that were NOT in `original`
- `to_restore`: Flows in `original` that are NOT in `current`

It deletes **ONLY** flows matching SentinelNet's cookie tag (`0x53454E54`) or failover priority (`300`). Operator flows, custom VLANs, and monitoring rules are **never touched**.

```python
for flow in to_delete:
    if not self._is_our_flow(flow):
        logger.warning("Skipping deletion of operator flow: %s", flow)
        continue
    await self.sdn_controller.delete_flow_entry({
        "dpid": dpid_int,
        "priority": flow["priority"],
        "match": flow["match"],
        "cookie": flow.get("cookie")
    })

for flow in to_restore:
    await self.sdn_controller.add_flow_entry(rule_to_restore)
```

#### 4. Active Post-Rollback Verification
After restoring baseline flows, `RollbackManager` queries the switch again to verify every original baseline rule is present. If missing, it marks `overall_success = False` and triggers critical alerts.

---

## 11. Multi-Layer Exact Flow & Telemetry Verification

### The Problem with Old Verification
Previously, recovery verification only performed a vacuous check:
```python
# OLD — INEFFECTIVE CHECK
switch_flows = await self.sdn_controller.get_flows(dpid)
if not switch_flows:
    flows_ok = False
    break
```
If a switch contained 20 pre-existing or unrelated operator flows, the check evaluated to `True` even if the intended recovery flow rule was completely missing or failed to install! Furthermore, if ICMP was restricted by local OS/sandbox environments, fallback mechanisms fabricated mock numbers (`{"latency_ms": 5.0, "packet_loss_pct": 0.0}`).

### Multi-Layer Verification Pipeline (`verify_recovery`)

SentinelNet now executes a four-layer verification protocol:

```
[Layer 1: Controller Flow Check]
   ├── Query Ryu get_flows(dpid)
   ├── Match exact in_port, eth_type=0x0800, ipv4_src, ipv4_dst
   ├── Match exact actions (OUTPUT:port)
   └── Match exact Priority == 300 (RECOVERY_PRIORITY)
          │
          ▼
[Layer 2: Data-Plane Traffic Probing]
   ├── Real ping / reachability probes to target host IPs
   ├── Strict packet loss threshold: loss <= 1.0%
   └── If unreachable or loss > 1.0% → Fails verification
          │
          ▼
[Layer 3: Metric Health Validation]
   ├── Inspect latency and error metrics across affected devices
   └── Strict latency threshold: latency <= 100.0ms
          │
          ▼
[Layer 4: Cross-Check Telemetry]
   └── Compare predicted path latency against actual measured RTT
```

### Exact Flow Matching Specification

Flow matching in Layer 1 tests exact match parameters and actions:
```python
matching = [
    f for f in flows
    if self._flow_matches(f, expected_match)
    and self._actions_match(f.get("actions", []), expected_actions)
    and f.get("priority") == self.RECOVERY_PRIORITY
]

if not matching:
    return VerificationResult(
        success=False,
        reason="flow_not_found_on_switch",
        failed_dpid=dpid,
        expected=expected_match,
        actual_flows_count=len(flows)
    )
```

### Non-Fabricated Telemetry & TCP Fallback (`backend/monitoring/network_monitor.py`)

When ICMP probing encounters local sandbox restrictions or permission limits:
- **Never fabricates fake ICMP metrics**: Does not report simulated 0% packet loss or fake 5.0ms RTT.
- **Explicit TCP Probing**: Probes TCP reachability and accurately reports:
  ```json
  {
    "reachable": true,
    "method": "tcp",
    "connect_time_ms": 4.2,
    "latency_ms": null,
    "packet_loss_pct": null,
    "note": "TCP fallback — ICMP unavailable, latency/loss not measured"
  }
  ```
- Layer 2 verification safely processes TCP connect times when ICMP is unavailable without crashing or doing arithmetic on `None`.

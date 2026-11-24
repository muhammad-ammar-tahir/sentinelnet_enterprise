# SentinelNet — Integration & End-to-End Self-Healing Test Suite

This directory contains integration test suites and automated verification scripts proving that the SentinelNet self-healing pipeline functions end-to-end without synthetic shortcuts or hardcoded success.

---

## Test Files Overview

| Test Script | Target Component | Description |
|---|---|---|
| `test_e2e_recovery.py` | Full Pipeline | Live end-to-end test (baseline metrics ➔ link cut ➔ detection ➔ rerouting ➔ active ICMP ping ➔ Ryu flow verification ➔ DB persistence). Skips gracefully if Mininet/Ryu hardware is not detected. |
| `test_recovery_failure.py` | Honest Rejection | Verifies that when no valid alternate path exists, recovery returns `{"success": False, "reason": "no_alternate_path"}` and marks the incident `escalated` in the database. |
| `test_rollback.py` | Rollback Engine | Verifies that when post-installation verification fails, pre-incident flow snapshots are restored via `RollbackManager` and the incident is marked `rolled_back`. |
| `../test_auth_and_ws.py` | Security & Telemetry | Verifies JWT authentication, token refresh, RBAC privilege gates (viewer 403 / unauthenticated 401), rate limiting (5 req/min), and WebSocket bidirectional streams. |

---

## Prerequisites

1. **Python Dependencies**:
   ```bash
   pip install -r requirements.txt pytest pytest-asyncio rich
   ```

2. **Database Initialization**:
   Ensure the database is seeded:
   ```bash
   python -m backend.database.seed
   ```

3. **(Optional for live hardware testing)** Mininet & Ryu OpenFlow Controller:
   On a Linux VM or WSL2 instance:
   ```bash
   # Terminal 1 — Ryu Controller
   ryu-manager sdn_controller/ryu_app.py --observe-links --ofp-tcp-listen-port 6633 --wsapi-port 8080

   # Terminal 2 — Mininet Simulation
   sudo python network_simulation/topology.py
   ```
   > **Note:** If Mininet is not active, `test_e2e_recovery.py` automatically detects the environment and skips gracefully without failing your build.

---

## Running the Test Suite

Run all tests via pytest:

```bash
pytest tests/ -v -s
```

Run specific test modules:

```bash
# Test honest failure handling (no alternate path):
pytest tests/test_recovery_failure.py -v -s

# Test atomic flow rollback on verification failure:
pytest tests/test_rollback.py -v -s

# Test full end-to-end workflow:
pytest tests/test_e2e_recovery.py -v -s
```

---

## Expected Test Outputs

### 1. Failure Case Output (`test_recovery_failure.py`)
Proves that the system **never fakes success** when network partitions occur:

```text
tests/test_recovery_failure.py::test_recovery_failure_when_no_backup_path_exists 
2026-11-23 18:15:00 [INFO] backend.recovery.recovery_engine: >>> STARTING RECOVERY LIFECYCLE for Incident: inc_test_failure_1700000000 <<<
2026-11-23 18:15:00 [WARNING] backend.recovery.recovery_engine: Recovery aborted: No valid alternate path exists between s1 and srv1. Escalating incident to human operators.

✓ Verified: Recovery returned success=False with reason='no_alternate_path'
✓ Verified: Database incident status correctly escalated to human NOC operators
PASSED
```

### 2. Rollback Verification Output (`test_rollback.py`)
Proves that pre-incident flow snapshots are restored when telemetry verification fails:

```text
tests/test_rollback.py::test_recovery_rollback_on_verification_failure 
2026-11-23 18:15:02 [INFO] backend.recovery.recovery_engine: >>> STARTING RECOVERY LIFECYCLE for Incident: inc_test_rollback_1700000000 <<<
2026-11-23 18:15:02 [WARNING] backend.recovery.recovery_engine: Active verification FAILED (Simulated failure: destination 10.0.0.50 unreachable over bypass link, 100% packet loss). Triggering rollback...

✓ Verified: Flows rolled back and snapshot restored
✓ Verified: Database incident marked 'rolled_back'
PASSED
```

### 3. Graceful Skip Output (`test_e2e_recovery.py`)
When running outside of a live Mininet Linux environment:

```text
tests/test_e2e_recovery.py::test_complete_self_healing_workflow SKIPPED [1] (Live Mininet/Ryu environment not detected (Ryu on port 8080 or Mininet switches offline). Skipping end-to-end hardware test.)
```

---

## Interactive Teacher Demo Script (`scripts/demo.py`)

A rich CLI terminal visualizer demonstrating the entire self-healing sequence to instructors and project evaluators.

### Launch Interactive Demo:
```bash
python scripts/demo.py
```

### Launch Automated Demo (Non-interactive mode):
```bash
python scripts/demo.py --auto
```

### Demonstration Walkthrough Stages:
1. **STAGE 1: Baseline Network Health**: Shows nominal global health score (98.4%), zero active incidents, sub-5ms latency.
2. **STAGE 2: Controlled Chaos**: Prompts operator to inject link failure on core link `s2-s3`.
3. **STAGE 3: Anomaly Detection**: Sub-second telemetry spike detection with elapsed millisecond measurement.
4. **STAGE 4: AI Root-Cause Diagnosis**: Evaluates `DiagnosisEngine` hypotheses with supporting evidence and confidence scores.
5. **STAGE 5: Constrained Shortest-Path Rerouting**: Resolves physical switch DPIDs and physical OpenFlow ports to install bypass flow rules via `s1-s3`.
6. **STAGE 6: Active Telemetry Verification**: Executes real ICMP ping probes through the newly actuated path before resolving the incident.
7. **STAGE 7: Transactional Rollback Safety**: Demonstrates flow reversion to the pre-incident flow table snapshot.

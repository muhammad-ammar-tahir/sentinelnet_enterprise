# 10 — Testing & Evaluation

## Table of Contents
1. [Evaluation Strategy](#1-evaluation-strategy)
2. [KPI Definitions](#2-kpi-definitions)
3. [Experiment Design](#3-experiment-design)
4. [Experiment 1 — Detection Speed](#4-experiment-1--detection-speed)
5. [Experiment 2 — Diagnosis Accuracy](#5-experiment-2--diagnosis-accuracy)
6. [Experiment 3 — Recovery Effectiveness](#6-experiment-3--recovery-effectiveness)
7. [Experiment 4 — System Availability](#7-experiment-4--system-availability)
8. [Experiment 5 — False Positive Rate](#8-experiment-5--false-positive-rate)
9. [Unit & Integration Tests](#9-unit--integration-tests)
10. [How to Run All Experiments](#10-how-to-run-all-experiments)
11. [Expected Results Table](#11-expected-results-table)
12. [Limitations of Evaluation](#12-limitations-of-evaluation)

---

## 1. Evaluation Strategy

SentinelNet is evaluated using **controlled fault injection experiments** in Mininet. Because the network is simulated, faults are deterministic and reproducible — the same script always produces the same failure.

**Evaluation philosophy:**
- Measure what the system does, not what it claims to do
- Report actual numbers, including failures
- Acknowledge the simulation-to-reality gap honestly
- Compare against a baseline of "no self-healing" (manual detection only)

**Baseline for comparison:** A network running the same topology with Ryu but *without* SentinelNet — just standard reactive OpenFlow forwarding with no AI layer. Recovery is performed by a human (simulated as a 5-minute fixed delay).

---

## 2. KPI Definitions

| KPI | Definition | Unit | Target |
|---|---|---|---|
| **Detection Time** | Time from fault injection to `AnomalySignal` emission | seconds | <30s |
| **Diagnosis Accuracy** | Fraction of incidents with correct `failure_type` label | % | >80% |
| **Recovery Time** | Time from `AnomalySignal` to `RESOLVED` status | seconds | <60s |
| **MTTR** | Mean Time To Repair across all resolved incidents | seconds | <90s |
| **Packet Loss** | Percentage of ICMP probes lost during a fault event | % | <5% |
| **System Availability** | Fraction of time network is in `UP` state | % | >99% |
| **False Positive Rate** | Incidents raised during fault-free operation | % | <10% |
| **Recovery Success Rate** | Fraction of automated recoveries that reach `RESOLVED` | % | >85% |

### KPI Measurement Formulas

```
Detection Time     = timestamp(AnomalySignal) - timestamp(fault_injection)

Diagnosis Accuracy = correct_diagnoses / total_diagnosed_incidents × 100

Recovery Time      = timestamp(RESOLVED) - timestamp(AnomalySignal)

MTTR               = Σ(Recovery Time for all RESOLVED) / count(RESOLVED)

Packet Loss (%)    = (probes_lost / probes_sent) × 100
                     [measured by continuous h1→srv1 ICMP at 1pps]

Availability (%)   = (1 - total_downtime_sec / total_experiment_duration_sec) × 100

False Positive Rate = spurious_incidents / total_incidents × 100
                      [during 60-min fault-free baseline run]

Recovery Success Rate = RESOLVED_count / (RESOLVED + FAILED + TIMEOUT) × 100
```

---

## 3. Experiment Design

### Setup

Each experiment runs in a clean Mininet environment with fresh OVS state:
1. `sudo mn -c` — clean previous state
2. `python network/topology.py` — start topology
3. `ryu-manager controller/sentinelnet_controller.py` — start controller
4. Wait 60 seconds for baseline metrics to establish
5. Start continuous ICMP probe: `h1.cmd('ping srv1 -i 1 > /tmp/probe.log &')`
6. Inject fault
7. Record metrics until `RESOLVED` or 5-minute timeout
8. `sudo mn -c` — clean up

### Repetitions

Each fault type is injected **10 times**. Report mean ± standard deviation for all numeric KPIs.

### Ground Truth

Since fault injection is scripted, ground truth labels are known. The `inject_fault.py` script writes a JSON log file with the exact fault type and injection timestamp, which is compared against the incident database post-experiment.

---

## 4. Experiment 1 — Detection Speed

**Goal:** Measure how quickly SentinelNet detects each of the 5 fault types.

**Procedure:**

```bash
# Run 10 trials of each fault type
for i in $(seq 1 10); do
  python scripts/inject_fault.py --fault link_failure --link L1
  sleep 120
  sudo mn -c && python network/topology.py &
  sleep 30
done
```

**Data collected:**
- `fault_injection_ts` — from inject_fault.py log
- `anomaly_signal_ts` — from incidents.created_at in PostgreSQL
- `detection_time = anomaly_signal_ts - fault_injection_ts`

**Measurement script:**
```python
# scripts/measure_detection_time.py
import psycopg2, json
from datetime import datetime

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Load ground truth from inject log
with open('/tmp/experiment_log.json') as f:
    injections = json.load(f)

for inj in injections:
    cur.execute("""
        SELECT created_at FROM incidents
        WHERE created_at > %s AND created_at < %s + interval '5 minutes'
        ORDER BY created_at LIMIT 1
    """, (inj['injected_at'], inj['injected_at']))
    row = cur.fetchone()
    if row:
        detection_time = (row[0] - inj['injected_at']).total_seconds()
        print(f"{inj['fault_type']}: {detection_time:.1f}s")
```

**Expected results for LINK_FAILURE:**
- Min: ~20s (2 scrape intervals + voting)
- Max: ~40s (if fault occurs just after a scrape)
- Mean ± std: 28 ± 6 seconds

---

## 5. Experiment 2 — Diagnosis Accuracy

**Goal:** Measure the Random Forest classifier's accuracy across all 5 fault types.

**Procedure:**

Inject each fault type 20 times (100 total incidents). Compare `incidents.failure_type` against ground truth.

**Metrics:**

```python
# scripts/evaluate_diagnosis.py
from sklearn.metrics import classification_report, confusion_matrix

y_true = ground_truth_labels   # from inject log
y_pred = diagnosed_labels       # from incidents DB

print(classification_report(y_true, y_pred, 
      labels=['LINK_FAILURE','CONGESTION','HIGH_LATENCY',
              'DEVICE_FAILURE','REPEATED_FAILURE']))
print(confusion_matrix(y_true, y_pred))
```

**Expected output:**
```
                   precision  recall  f1-score  support
LINK_FAILURE          0.95     0.90      0.92      20
CONGESTION            0.85     0.90      0.87      20
HIGH_LATENCY          0.75     0.80      0.77      20
DEVICE_FAILURE        0.95     1.00      0.97      20
REPEATED_FAILURE      0.80     0.70      0.74      20
accuracy                                0.86     100
```

**Confusion matrix (expected):**
```
            LF  CO  HL  DF  RF
LF        [ 18   1   1   0   0]
CO        [  0  18   2   0   0]
HL        [  1   3  16   0   0]
DF        [  0   0   0  20   0]
RF        [  1   1   2   0  14] ← most confusion with other types
```

**Note:** HIGH_LATENCY and REPEATED_FAILURE are expected to be the hardest to diagnose correctly due to feature overlap.

---

## 6. Experiment 3 — Recovery Effectiveness

**Goal:** Measure recovery time and success rate for each fault type.

**Procedure:**
- Record `anomaly_signal_ts` and `resolved_ts` for 10 trials per fault type
- Record outcome: SUCCESS / FAILED / TIMEOUT

**Data collection query:**
```sql
SELECT 
    failure_type,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE status = 'RESOLVED') as resolved,
    AVG(recovery_time_ms) FILTER (WHERE status = 'RESOLVED') as avg_recovery_ms,
    STDDEV(recovery_time_ms) FILTER (WHERE status = 'RESOLVED') as std_recovery_ms,
    MIN(recovery_time_ms) FILTER (WHERE status = 'RESOLVED') as min_recovery_ms,
    MAX(recovery_time_ms) FILTER (WHERE status = 'RESOLVED') as max_recovery_ms
FROM incidents
WHERE created_at > '2024-01-01'
GROUP BY failure_type;
```

**Packet loss measurement:**
```bash
# During each experiment, h1 continuously pings srv1
# After experiment, count lost probes in the fault window
grep "Request timeout" /tmp/probe.log | wc -l
# Compare to total probes sent in fault window
```

**Baseline comparison (no SentinelNet):**
- Recovery time: 300 seconds (simulated 5-minute human response)
- Packet loss: 100% during fault duration
- Availability: depends on fault frequency

---

## 7. Experiment 4 — System Availability

**Goal:** Measure overall system availability across a 1-hour continuous operation with fault injection.

**Procedure:**

```bash
# 1-hour experiment: inject random faults every 5–15 minutes
python scripts/run_experiments.py --mode stress --duration 3600 --fault_interval 600
```

**Availability calculation:**
```python
# Total probe time = 3600 seconds
# Count seconds where ping to srv1 succeeded
probe_log = parse_ping_log('/tmp/probe.log')
uptime_seconds = sum(1 for p in probe_log if p['success'])
availability = uptime_seconds / 3600 * 100
print(f"Availability: {availability:.3f}%")
```

**Expected:**
- With SentinelNet: >99% (downtime <36 seconds across 1 hour)
- Without SentinelNet: ~95% (each 5-minute fault = 8.3% downtime for one fault)

---

## 8. Experiment 5 — False Positive Rate

**Goal:** Measure how often SentinelNet raises incidents during fault-free operation.

**Procedure:**

```bash
# Run 60-minute baseline with NO fault injection
python scripts/run_experiments.py --mode baseline --duration 3600
```

**Data collection:**
```sql
SELECT COUNT(*) as spurious_incidents
FROM incidents
WHERE created_at BETWEEN '2024-01-01 09:00:00' AND '2024-01-01 10:00:00'
  AND status != 'MANUAL_REVIEW';  -- manual reviews are expected noise
```

**False positive rate:**
```
FPR = spurious_incidents / (scrape_count / voting_window) × 100
    = spurious_incidents / (360 / 5) × 100
    = spurious_incidents / 72 × 100
```

**Expected:** <5 spurious incidents in 60 minutes → FPR < 7%

**If FPR is high:** Increase the voting window (5 → 7) or raise the anomaly threshold (0.65 → 0.70).

---

## 9. Unit & Integration Tests

### Running Tests

```bash
# All tests
cd backend
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests (requires running DB and Redis)
pytest tests/integration/ -v

# Coverage report
pytest tests/ --cov=app --cov=ai --cov-report=html
```

### Test Structure

```
backend/tests/
├── unit/
│   ├── test_anomaly_detector.py     ← Isolation Forest scoring
│   ├── test_failure_diagnoser.py    ← RF classifier correctness
│   ├── test_recovery_recommender.py ← Policy lookup + k-NN
│   ├── test_pipeline.py             ← Orchestrator stage transitions
│   └── test_schemas.py              ← Pydantic validation
├── integration/
│   ├── test_api_metrics.py          ← GET /api/metrics
│   ├── test_api_incidents.py        ← Incident CRUD
│   ├── test_api_recover.py          ← POST /api/recover
│   └── test_websocket.py            ← WS event stream
└── conftest.py                      ← Fixtures, test DB, mock Ryu
```

### Key Test Cases

```python
# test_anomaly_detector.py
def test_healthy_traffic_not_flagged(detector, healthy_vector):
    score = detector.score(healthy_vector)
    assert not detector.is_anomalous(score)

def test_link_failure_detected(detector, link_failure_vector):
    score = detector.score(link_failure_vector)
    assert detector.is_anomalous(score)
    assert score > 0.65

def test_voting_filter_requires_majority(detector):
    # 2 out of 5 anomalous should NOT trigger
    vectors = [healthy] * 3 + [anomalous] * 2
    result = detector.process_window(vectors)
    assert result.triggered == False

def test_voting_filter_triggers_at_majority(detector):
    vectors = [healthy] * 2 + [anomalous] * 3
    result = detector.process_window(vectors)
    assert result.triggered == True
```

---

## 10. How to Run All Experiments

```bash
# Full evaluation suite (takes ~90 minutes)
python scripts/run_experiments.py --mode full

# This runs:
# 1. 60-min baseline (false positive measurement)
# 2. 10× each of 5 fault types (detection + diagnosis)
# 3. 60-min stress test (availability)
# 4. Generates report: results/experiment_report.json
# 5. Generates charts: results/figures/

# Quick sanity check (5 minutes, 2 trials per fault type)
python scripts/run_experiments.py --mode quick
```

---

## 11. Expected Results Table

> [!IMPORTANT]
> All "Expected" figures below are targets computed from the synthetic-data training distribution. **They have not been verified against real Mininet traffic.** The "Actual (measured)" column shows values obtained during automated integration tests on a local dev machine (Windows 11, SQLite DB, Ryu unavailable — simulated controller). Real Mininet/Ryu measurements will differ.

| KPI | Target | Expected (synthetic baseline) | Actual (measured — dev machine) |
|---|---|---|---|
| Detection Time — LINK_FAILURE | <30s | 28 ± 6s | ~680ms (seed metadata; Ryu unavailable) |
| Detection Time — CONGESTION | <60s | 52 ± 10s | — (requires live Mininet) |
| Detection Time — HIGH_LATENCY | <30s | 23 ± 5s | — (requires live Mininet) |
| Detection Time — DEVICE_FAILURE | <10s | 3 ± 1s | — (requires live Mininet) |
| Diagnosis Accuracy (overall) | >80% | 86% **on synthetic data** | — (requires labelled real traffic) |
| Diagnosis Accuracy — LINK_FAILURE | >90% | 92% **on synthetic data** | — |
| Diagnosis Accuracy — HIGH_LATENCY | >70% | 77% **on synthetic data** | — |
| Recovery Time — LINK_FAILURE | <15s | 10 ± 3s | ~54s (timeout-dominated; 3×5s Ryu retries × 3 DPIDs) |
| Recovery Time — CONGESTION | <30s | 22 ± 8s | — |
| Recovery Time — DEVICE_FAILURE | <60s | 45 ± 12s | — |
| System Availability | >99% | 99.4% | — (requires 1-hr live experiment) |
| False Positive Rate | <10% | <7% | — |
| Recovery Success Rate | >85% | 90% | 100% on seeded topology (3/3 unit tests pass) |

---

## 12. Verification Status

This table reflects what is **actually implemented and tested** in the current codebase.

| Component | Status | Test / Evidence | Notes |
|---|---|---|---|
| JWT Authentication (`/api/auth/login`) | ✅ Verified | `test_auth_and_ws.py` (6/6 pass) | bcrypt + python-jose HS256 |
| Refresh Token (`/api/auth/refresh`) | ✅ Verified | `test_auth_and_ws.py` | 7-day expiry |
| RBAC Role Gates (operator / admin) | ✅ Verified | `test_auth_and_ws.py` | 401/403 confirmed |
| WebSocket Auth (query param + frame) | ✅ Verified | `test_auth_and_ws.py` | 5-second handshake timeout |
| Fault Injection + Incident Creation | ✅ Functional | `scripts/demo.py` (exit 0) | DB record + WS broadcast |
| Anomaly Detection (Isolation Forest) | ✅ Functional | Manual demo | Fault injection creates incidents |
| Path Selection (Dijkstra + constraints) | ✅ Verified | `test_recovery_failure.py` (pass) | Bidirectional graph, constraint enforcement |
| No-Path Escalation | ✅ Verified | `test_recovery_failure.py` | `success=False`, status=`escalated` |
| Recovery Engine Rollback | ✅ Verified | `test_rollback.py` (pass) | `rolled_back=True`, status=`rolled_back` |
| Ryu Flow Installation | ⚠️ Linux/WSL2 only | Manual (requires live Ryu) | Windows: connection refused (expected) |
| Active ICMP Verification | ⚠️ Linux/WSL2 only | Manual (requires Mininet IPs) | Windows: unreachable (expected) |
| Database Migrations (Alembic) | ✅ Functional | `alembic upgrade head` | SQLite + PostgreSQL |
| DB Seed (3 RBAC users) | ✅ Functional | `python -m backend.database.seed` | Idempotent for users |
| Dashboard UI Build | ✅ Passes | `npm run build` (TypeScript) | No component tests yet |
| Frontend Component Tests | ❌ Not implemented | — | No Vitest/Jest coverage |
| Docker Compose | ⚠️ Partial | `docker-compose.yml` exists | `Dockerfile.backend/.frontend` missing |
| MFA (Multi-Factor Auth) | ❌ Cosmetic only | — | UI checkbox only; no TOTP/FIDO2 |
| Prometheus / Grafana | ⚠️ Configured | `docker-compose.yml` | `prometheus.yml` not in repo |
| E2E Test (live Mininet) | ⏭️ Skipped | `test_e2e_recovery.py` | Skips if Ryu not reachable |

---

## 13. Limitations of Evaluation

### L1 — Synthetic Traffic Only

The network carries only `iperf3` and `ping` traffic. Real university networks carry HTTP, video, encrypted VPN, DNS, multicast — all of which create metric patterns that SentinelNet has never seen.

### L2 — Deterministic Faults

Fault injection is scripted and deterministic. Real failures are intermittent, partial, and often correlated (e.g., power outage affects multiple devices simultaneously). SentinelNet is not evaluated against correlated multi-fault scenarios.

### L3 — 10 Trials Is Statistically Weak

10 trials per fault type gives mean ± std but limited statistical power. A production evaluation would require hundreds of trials over weeks of real operation.

### L4 — Human Baseline Is Approximate

The "5-minute manual recovery" baseline is an estimate, not a measured real-world value. Actual human MTTR varies widely.

### L5 — No Cross-Validation of Anomaly Detector

Isolation Forest doesn't have a traditional accuracy metric (it's unsupervised). We evaluate it via false positive rate and detection rate, but cannot compute a traditional confusion matrix without exhaustive labeled test data.

# 05 — AI Modules

> **Status (last updated):** Backend AI detection and diagnosis modules are **fully implemented** (not skeletons). See `backend/detection/fault_detection.py`, `backend/detection/prediction.py`, and `backend/diagnosis/root_cause.py`.

## Table of Contents
1. [Overview](#1-overview)
2. [Module 1 — Fault Detection (Rules + ML)](#2-module-1--fault-detection-rules--ml)
3. [Module 2 — Failure Prediction (Trend-Based Risk)](#3-module-2--failure-prediction-trend-based-risk)
4. [Module 3 — Root-Cause Diagnosis](#4-module-3--root-cause-diagnosis)
5. [Module 4 — Recovery Recommendation](#5-module-4--recovery-recommendation)
6. [Training Data Format](#6-training-data-format)
7. [Model Retraining Pipeline](#7-model-retraining-pipeline)
8. [Limitations & Honest Disclaimers](#8-limitations--honest-disclaimers)

---

## 1. Overview

SentinelNet uses four AI/analytics capabilities in a staged pipeline. Each module is fully implemented with real logic (not placeholder code):

| # | Module | File | Algorithm | Status |
|---|---|---|---|---|
| 1 | Fault Detector | `backend/detection/fault_detection.py` | Threshold rules + Isolation Forest | ✅ Implemented |
| 2 | Failure Predictor | `backend/detection/prediction.py` | Linear regression slope analysis | ✅ Implemented |
| 3 | Diagnosis Engine | `backend/diagnosis/root_cause.py` | Multi-signal scoring + templates | ✅ Implemented |
| 4 | Recovery Recommender | `backend/recovery/recovery_engine.py` | Policy DB + constraint optimization | Skeleton → planned |

All modules use **interpretable, non-black-box methods** — this is a university project where explainability matters more than marginal accuracy gains from deep learning.

---

---

## 2. Module 1 — Fault Detection (Rules + ML)

### File
`backend/detection/fault_detection.py` — class `FaultDetector`

### Purpose

Detect network faults by combining deterministic threshold rules with an optional Isolation Forest anomaly model. Returns typed `Fault` objects with `fault_type`, `severity`, `confidence`, and `reason` fields.

### Detection Pipeline

```
detect(target_id, metrics)
    │
    ├─► check_thresholds()  — Rule-based fault detection
    │       interface_up == 0           → INTERFACE_DOWN   (critical, 1.00)
    │       packet_loss >= 95%          → LINK_DOWN        (critical, 1.00)
    │       packet_loss > 5%            → PACKET_LOSS_CRIT (warning/critical, 0.92)
    │       latency_ms > 300ms          → HIGH_LATENCY     (critical, 0.90)
    │       latency_ms > 150ms          → HIGH_LATENCY     (warning, 0.85)
    │       cpu_pct > 95%               → CPU_OVERLOAD     (critical, 0.93)
    │       cpu_pct > 85%               → CPU_OVERLOAD     (warning, 0.88)
    │       bandwidth > 85% capacity    → CONGESTION       (warning, 0.80)
    │
    └─► check_ml()          — Isolation Forest scoring
            Calls AnomalyPredictor from ai_models/predict.py
            is_anomaly=True AND score >= 0.60 → ML_ANOMALY (warning/critical)
            Suppressed if threshold fault already fires for same target
```

### Fault Object Fields

```python
@dataclass
class Fault:
    fault_type: str           # LINK_DOWN | PACKET_LOSS_CRITICAL | CONGESTION | CPU_OVERLOAD | INTERFACE_DOWN | HIGH_LATENCY | ML_ANOMALY
    target_id: str            # device or link identifier
    severity: str             # critical | warning | info
    confidence: float         # 0.0 – 1.0
    reason: str               # human-readable explanation
    timestamp: str            # ISO8601 UTC
    telemetry_snapshot: dict  # full metrics dict for downstream RCA
```

### Severity Thresholds

| Fault Type | Trigger | Severity | Confidence |
|---|---|---|---|
| `INTERFACE_DOWN` | `interface_up == 0` | critical | 1.00 |
| `LINK_DOWN` | `packet_loss >= 95%` | critical | 1.00 |
| `PACKET_LOSS_CRITICAL` | `packet_loss > 5%` | warning/critical | 0.92 |
| `HIGH_LATENCY` | `latency_ms > 300ms` | critical | 0.90 |
| `HIGH_LATENCY` | `latency_ms > 150ms` | warning | 0.85 |
| `CPU_OVERLOAD` | `cpu_pct > 95%` | critical | 0.93 |
| `CPU_OVERLOAD` | `cpu_pct > 85%` | warning | 0.88 |
| `CONGESTION` | `bandwidth > 85 Mbps` | warning | 0.80 |
| `ML_ANOMALY` | Isolation Forest score ≥ 0.60 | warning/critical | model output |

### Usage

```python
from backend.detection.fault_detection import FaultDetector

detector = FaultDetector()
faults = detector.detect("switch-s2", {
    "latency_ms": 340.0,
    "packet_loss_pct": 28.5,
    "cpu_pct": 97.0,
    "bandwidth_mbps": 92.0,
    "interface_up": 1,
    "error_count": 450,
    "memory_pct": 88.0,
})
for f in faults:
    print(f"[{f.severity}] {f.fault_type}: {f.reason}")
```

### Data Leakage Prevention Guarantee

In earlier iterations, standardizing features before partitioning introduced subtle data leakage from the test distribution into the training scaling parameters.
In `ai_models/preprocessing.py`, the pipeline strictly executes:
```python
# 1. Split FIRST on raw unscaled features
X_train_raw, X_test_raw, y_train, y_test = train_test_split(
    X_raw, y, test_size=0.2, random_state=42, stratify=y
)
# 2. Fit scaler ONLY on X_train_raw
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train_raw)
# 3. Transform test set with train parameters
X_test_scaled = scaler.transform(X_test_raw)
```
This is verified by the unit test in `ai_models/test_preprocessing.py`.

### Algorithm: Isolation Forest (ML Component)

The Isolation Forest model is loaded from `ai_models/trained_model.pkl` (trained by `ai_models/train_model.py`). It's used as an optional second layer — if the model file doesn't exist, `check_ml()` silently returns `[]` and the system runs on threshold rules alone.

### Algorithm: Isolation Forest

Isolation Forest works by randomly partitioning the feature space. Points that are **easy to isolate** (require fewer partitions to separate) are anomalies. It is particularly well-suited to network monitoring because:

1. It's **unsupervised** — only healthy baseline data is needed for training
2. It handles **high-dimensional** feature spaces well
3. It's **fast** at inference — O(n log n) training, O(1) per sample scoring
4. It's **robust** to outliers in the training set (up to `contamination` fraction)

### Input Features (8 features per sample)

| Feature | Description | Unit | Source |
|---|---|---|---|
| `rx_bytes_rate` | Incoming bytes per second (rolling 10s avg) | bytes/s | Ryu port stats |
| `tx_bytes_rate` | Outgoing bytes per second (rolling 10s avg) | bytes/s | Ryu port stats |
| `rx_error_rate` | Receive errors per second | errors/s | Ryu port stats |
| `tx_drop_rate` | Transmit drop rate | drops/s | Ryu port stats |
| `flow_table_size` | Number of active flow entries in switch | count | Ryu flow stats |
| `link_utilization` | % of link bandwidth in use | % (0–100) | Derived: bytes_rate / bw |
| `rtt_ms` | ICMP round-trip time to SRV1 | milliseconds | Host exporter |
| `host_cpu_pct` | Host CPU utilization | % (0–100) | Host exporter |

### Voting Filter

A single anomalous sample does not trigger an alert. The voting rule:

```
If (anomaly_count in last 5 samples >= 3):
    emit AnomalySignal
```

This reduces false positives from transient spikes.

### Training Procedure

```python
from sklearn.ensemble import IsolationForest
import joblib, numpy as np

# X_baseline: (n_samples, 8) — only healthy network state snapshots
model = IsolationForest(
    n_estimators=200,
    max_samples='auto',
    contamination=0.05,   # expect ~5% anomalies in real traffic
    random_state=42
)
model.fit(X_baseline)
joblib.dump(model, 'backend/ai/models/anomaly_detector.pkl')
```

### Anomaly Score Interpretation

| Score Range | Interpretation | Action |
|---|---|---|
| > 0.0 (positive) | Normal — no anomaly | No action |
| -0.1 to 0.0 | Borderline — monitor | Log only |
| -0.3 to -0.1 | Likely anomaly | Trigger voting filter |
| < -0.3 | Strong anomaly | Immediate flag |

> **Note:** Scikit-learn's `decision_function` returns higher scores for inliers. We negate the score for readability (higher = more anomalous).

### Key Hyperparameters

| Parameter | Value | Rationale |
|---|---|---|
| `n_estimators` | 200 | Stability without excessive memory |
| `contamination` | 0.05 | Conservative — expects 5% fault rate in baseline |
| `max_samples` | 'auto' | 256 samples per tree — standard default |
| Voting window | 5 samples (3/5 majority) | 50-second effective delay; tunable |

---

---

## 3. Module 2 — Failure Prediction (Trend-Based Risk)

### File
`backend/detection/prediction.py` — class `FailurePredictor`

### Purpose

Analyse historical telemetry time-series data to identify rising trends and assign a **0–100 risk score** to each device using linear regression (numpy.polyfit). Used to prioritise which devices to inspect before a fault occurs.

> **DISCLAIMER:** All scores are **pattern-based risk estimates** — not calibrated probabilities. A score of 80 means the current trend strongly resembles pre-failure patterns, not that there is an 80% probability of failure.

### Trend Analysis

```python
def analyze_trend(history, metric_key="latency_ms", window=10):
    # Fits degree-1 polynomial over last `window` values via numpy.polyfit
    # Returns: slope, intercept, projected_next_value, trend_direction, r_squared
```

| Return Field | Description |
|---|---|
| `slope` | Rate of change per time-step (units/step) |
| `intercept` | Y-intercept of fitted line |
| `projected_next_value` | Extrapolated value at t+1 |
| `trend_direction` | `"rising"` \| `"stable"` \| `"falling"` (threshold: ±0.5 units/step) |
| `r_squared` | Goodness of fit (0.0 – 1.0) |

### Risk Score Formula

```
base_score     = Σ weight[m] × min(1, current_value[m] / normal_max[m])
trend_penalty  = Σ weight[m] × min(0.30, slope[m] / 10.0 × 0.30)   # only for rising slopes
risk_score     = clip((base_score + trend_penalty) × 100, 0, 100)
```

| Metric | Weight | Normal Max |
|---|---|---|
| `latency_ms` | 0.35 | 150 ms |
| `packet_loss_pct` | 0.35 | 10% |
| `cpu_pct` | 0.20 | 100% |
| `memory_pct` | 0.10 | 100% |

### Batch Assessment

```python
predictor = FailurePredictor()
batch = predictor.batch_risk_assessment({
    "switch-s1": history_s1,
    "switch-s2": history_s2,
})
# Returns list sorted by risk_score descending
```

---

## 4. Module 3 — Root-Cause Diagnosis

### File
`backend/diagnosis/root_cause.py` — class `DiagnosisEngine`

### Purpose

Given a detected `Fault` plus network context (neighbour metrics, topology state, historical faults), produce ranked hypotheses explaining the most likely root cause with supporting/contradicting evidence and human-readable explanations.

### Hypothesis Types

| Hypothesis | Key Signals |
|---|---|
| `congestion` | High bandwidth + elevated latency + low loss |
| `link_degradation` | Packet loss > 3% + error counter elevation + recurring faults |
| `device_overload` | CPU > 80% + latency co-occurrence + memory pressure |
| `server_slow` | Latency at target but healthy neighbours + low CPU + low loss |
| `unknown` | No hypothesis reaches ≥ 0.40 confidence |

### Scoring Design

Each hypothesis has a dedicated scorer that evaluates signals and returns `(confidence, supporting_evidence[], contradicting_evidence[])`:

```python
hypotheses = engine.diagnose(fault, context)
# Returns list of Hypothesis objects sorted by confidence descending
# Only hypotheses with confidence > 0.05 are returned
```

### Hypothesis Object

```python
@dataclass
class Hypothesis:
    hypothesis: str                   # congestion | link_degradation | device_overload | server_slow | unknown
    confidence: float                 # 0.0 – 1.0
    supporting_evidence: List[str]    # bullet-point evidence list
    contradicting_evidence: List[str] # signals that argue against this hypothesis
```

### Human-Readable Explanations

```python
explanation = engine.explain(hypothesis, fault)
# → "High bandwidth utilization (92.0 Mbps, ~92% of link capacity) combined with
#    elevated latency (240.0 ms) on switch-s2 indicates TCP buffer congestion..."
```

Templates are stored in `DiagnosisEngine.HYPOTHESIS_TEMPLATES` — no LLM required.

### Context Schema

```python
context = {
    "neighbor_metrics": {
        "switch-s1": {"cpu_pct": 35.0, "bandwidth_mbps": 15.0, "latency_ms": 7.0},
    },
    "topology_state": {
        "active_links": 2,
        "failed_links": ["switch-s2--switch-s3"],
    },
    "history": [
        {"fault_type": "HIGH_LATENCY", "target_id": "switch-s2", "timestamp": "..."},
    ],
}
```

---

## 5. Module 4 — Recovery Recommendation (Planned)

### Purpose

Given that an anomaly has been detected, classify **which of the 5 failure types** caused it.

> **Important terminology note:** This module is called "Failure Prediction" in the UI but is architecturally a *Failure Diagnoser* — it identifies the current failure type from real-time features, not future failures. True predictive failure forecasting (before the fault occurs) is a planned future enhancement described in the limitations section.

### Algorithm: Random Forest Classifier

| Property | Value |
|---|---|
| `n_estimators` | 100 |
| `max_depth` | None (unlimited, controlled by `min_samples_leaf`) |
| `min_samples_leaf` | 5 |
| `class_weight` | 'balanced' (handles class imbalance) |
| `random_state` | 42 |

### Output Classes

| Class Label | Description | Recovery Target |
|---|---|---|
| `LINK_FAILURE` | A physical or virtual link is down | Reroute to backup path |
| `CONGESTION` | Link utilization >85% sustained | Rate limit or reroute |
| `HIGH_LATENCY` | RTT >100ms (baseline: ~7ms) | Investigate path, reroute |
| `DEVICE_FAILURE` | A switch is unresponsive to controller | Failover, manual escalation |
| `REPEATED_FAILURE` | Same fault type >3× in 60min window | Policy escalation |

### Feature Importance (expected from experiments)

```
rx_error_rate        ████████████████████  (most diagnostic for link failures)
link_utilization     ████████████████      (most diagnostic for congestion)
rtt_ms               ████████████          (most diagnostic for latency faults)
tx_drop_rate         ██████████
flow_table_size      ████████
rx_bytes_rate        ██████
tx_bytes_rate        ████
host_cpu_pct         ███
```

> These are expected relative importances based on the domain. Actual values depend on the synthetic training data generated by `scripts/generate_training_data.py`.

### Training Procedure

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
import joblib

# X: (n_samples, 8), y: (n_samples,) — class labels
clf = RandomForestClassifier(
    n_estimators=100,
    class_weight='balanced',
    min_samples_leaf=5,
    random_state=42
)
clf.fit(X_train, y_train)

# Cross-validation
scores = cross_val_score(clf, X, y, cv=5, scoring='f1_weighted')
print(f"Mean F1: {scores.mean():.3f} ± {scores.std():.3f}")

joblib.dump(clf, 'backend/ai/models/failure_diagnoser.pkl')
```

### Confidence Thresholds

| Confidence | Action |
|---|---|
| ≥ 0.80 | Fully automated recovery |
| 0.50–0.79 | Automated recovery + human notification |
| < 0.50 | Manual review required; recovery still attempted with best-guess |

---

### Purpose

Given a diagnosis result (failure type + affected components), recommend the **best recovery action**.

### Design: Hybrid (Policy-first + k-NN Fallback)

```
Input: (failure_type, severity, affected_device, affected_link)
        │
        ▼
Step 1: Lookup policies table
        │
        ├── MATCH FOUND with action=AUTOMATED
        │       └──► Return policy action (highest confidence)
        │
        └── NO MATCH
                └──► Step 2: k-NN on historical recovery_actions
                        Look at k=5 most similar past incidents
                        Vote on action by success_rate
                        └──► Return recommended action
```

### k-NN Configuration

| Parameter | Value |
|---|---|
| Algorithm | Ball tree (fast for 8-dim space) |
| k | 5 nearest neighbors |
| Distance metric | Euclidean on normalized feature vector |
| Tie-breaking | Weight by historical success rate |

### Recommendation Output

```json
{
  "action": "REROUTE_TO_BACKUP",
  "target_link": "L1",
  "parameters": {
    "new_path": ["S1", "BL1", "S3"],
    "backup_link_id": "BL1"
  },
  "confidence": 0.87,
  "estimated_recovery_time_sec": 8,
  "source": "POLICY"
}
```

### Action Catalog

| Action Code | Description | Ryu API Call |
|---|---|---|
| `REROUTE_TO_BACKUP` | Redirect flows to backup link | Modify S1 flow rules |
| `RATE_LIMIT` | Apply meter entry to throttle flow | `OFPMeterMod` |
| `REROUTE_AROUND_DEVICE` | Bypass a failed switch | Multiple `OFPFlowMod` |
| `RESET_FLOW_TABLE` | Clear and reinstall default flows | `OFPFlowMod` with DELETE |
| `ESCALATE_TO_MANUAL` | Do nothing automated; alert human | Webhook + incident update |

---

## 5. Training Data Format

Training data is stored in PostgreSQL and exported as CSV for model training:

### Anomaly Detector (Baseline — Healthy Data)

```csv
timestamp,rx_bytes_rate,tx_bytes_rate,rx_error_rate,tx_drop_rate,flow_table_size,link_utilization,rtt_ms,host_cpu_pct
2024-01-01T10:00:00Z,1245000,890000,0,0,45,12.4,7.2,8.1
2024-01-01T10:00:10Z,1312000,901000,0,0,45,13.1,7.1,8.3
...
```

**How to collect:** Run `network/topology.py` without fault injection for 2+ hours; Prometheus scrapes are automatically exported.

### Failure Diagnoser (Labeled Fault Data)

```csv
timestamp,rx_bytes_rate,tx_bytes_rate,rx_error_rate,tx_drop_rate,flow_table_size,link_utilization,rtt_ms,host_cpu_pct,label
2024-01-01T11:00:00Z,0,0,45,45,45,0.0,999.9,8.1,LINK_FAILURE
2024-01-01T11:30:00Z,9500000,9500000,2,89,65,95.0,145.3,42.1,CONGESTION
...
```

**Label encoding:** `{LINK_FAILURE:0, CONGESTION:1, HIGH_LATENCY:2, DEVICE_FAILURE:3, REPEATED_FAILURE:4}`

### Generating Telemetry & Model Training

Use the automated scripts in `ai_models/`:

```bash
# 1. Synthesize 10,000 realistic campus telemetry rows with 5% multi-modal failure injection:
python ai_models/generate_training_data.py
# Saves to: ai_models/data/training_data.csv

# 2. Preprocess data, fit Isolation Forest + Random Forest, and export evaluation metrics:
python ai_models/train_model.py
# Saves: ai_models/trained_model.pkl, ai_models/supervised_model.pkl, ai_models/scaler.pkl, ai_models/evaluation.json

# 3. Test real-time inference:
python ai_models/predict.py
```

---

## 6. Model Retraining Pipeline

```
Trigger: 50+ new labeled samples in feedback_buffer
         OR manual trigger via POST /api/models/retrain

Step 1: Export feedback_buffer → CSV
Step 2: Merge with existing training data
Step 3: Retrain Anomaly Detector with new contamination estimate
Step 4: Retrain Failure Diagnoser on merged dataset
Step 5: Cross-validate both models (target F1 > 0.75)
Step 6: If validation passes → replace .pkl files
Step 7: Reload models in FastAPI (zero-downtime via versioned filenames)
Step 8: Log retraining event to audit table
```

---

## 7. Limitations & Honest Disclaimers

> This section is intentionally transparent. Understanding what SentinelNet **cannot** do is as important as knowing what it can.

### L1 — Simulation Gap

**Issue:** All training data comes from Mininet simulations. Real networks have:
- Physical layer effects (cable quality, interference, transceiver failures)
- Proprietary vendor firmware behaviors
- Complex traffic patterns (multimedia, VPN, encrypted flows)
- Hardware-dependent timing

**Impact:** Models trained in Mininet may not generalize to physical university hardware without retraining on real data.

**Mitigation:** The feedback loop is designed to ingest real incident data if SentinelNet were deployed in a real environment.

---

### L2 — Small Training Dataset

**Issue:** With 5 fault types × ~200 samples each = ~1,000 labeled samples, the Random Forest classifier may overfit or underperform on edge cases.

**Impact:** Diagnosis confidence below 0.80 is common for `REPEATED_FAILURE` and `HIGH_LATENCY` (which overlap in features with `CONGESTION`).

**Mitigation:** `class_weight='balanced'` helps; more synthetic data can be generated by `scripts/generate_training_data.py`.

---

### L3 — No True Predictive Forecasting

**Issue:** The "Failure Prediction" module diagnoses the current failure, not an upcoming one. True predictive failure (e.g., "this link will fail in 10 minutes based on error rate trend") is not implemented.

**Why:** Requires time-series forecasting (LSTM or Prophet) and historical failure data with lead times — out of scope for a semester project.

**Future work:** Add a time-series anomaly trend predictor using Facebook Prophet on the RTT and error rate trends.

---

### L4 — Recovery Recommender Cold Start

**Issue:** The k-NN component only improves with incident history. With <50 incidents, it falls back entirely to static policies.

**Impact:** Early in deployment, all recommendations are policy-driven (deterministic), which is actually fine for a semester demo.

---

### L5 — No Concept Drift Detection

**Issue:** Network "normal" changes over time (semester start vs. exam week vs. summer break). The Isolation Forest baseline may become stale.

**Impact:** Increasing false positives as normal traffic patterns drift.

**Mitigation:** Schedule quarterly retraining on fresh baseline data. This is documented but not automated yet.

---

### L6 — Binary Recovery Outcomes

**Issue:** Recovery verification checks whether metrics are back in the normal range, but doesn't validate application-layer health (e.g., "can students actually access the LMS?").

**Future work:** Add synthetic HTTP probe transactions as part of verification.

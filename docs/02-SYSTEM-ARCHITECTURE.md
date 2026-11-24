# 02 — System Architecture

## Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [The 6-Stage Pipeline](#2-the-6-stage-pipeline)
3. [Module Descriptions](#3-module-descriptions)
4. [Data Flow Diagram](#4-data-flow-diagram)
5. [The Feedback Loop](#5-the-feedback-loop)
6. [Component Interaction Map](#6-component-interaction-map)

---

## 1. Architecture Overview

SentinelNet is built as a layered system with four horizontal tiers:

```
┌──────────────────────────────────────────────────────────────┐
│  TIER 4 — PRESENTATION                                       │
│  React Dashboard  │  Grafana Dashboards                      │
└──────────────────────────────────────────────────────────────┘
            │ REST API / WebSocket
┌──────────────────────────────────────────────────────────────┐
│  TIER 3 — APPLICATION                                        │
│  FastAPI Backend  │  AI Pipeline Orchestrator                │
│  PostgreSQL DB    │  Redis Pub/Sub                           │
└──────────────────────────────────────────────────────────────┘
            │ OpenFlow / REST
┌──────────────────────────────────────────────────────────────┐
│  TIER 2 — CONTROL                                            │
│  Ryu SDN Controller  │  Flow Manager  │  Topology Manager    │
└──────────────────────────────────────────────────────────────┘
            │ OpenFlow 1.3
┌──────────────────────────────────────────────────────────────┐
│  TIER 1 — DATA PLANE (SIMULATED)                             │
│  Mininet  │  OVS Switches  │  Virtual Hosts  │  Links        │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. The 6-Stage Pipeline

Each detected network event traverses a deterministic 6-stage pipeline. The pipeline is event-driven: stage N only triggers if stage N-1 produces a positive signal.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ①           ②           ③           ④           ⑤           ⑥           │
│                                                                             │
│ MONITOR  ──► DETECT  ──► DIAGNOSE ──► DECIDE  ──► EXECUTE ──► VERIFY       │
│                                                                             │
│  10-sec      Isolation    Random      ML Recom-   Ryu API     Re-check      │
│  scrape      Forest       Forest      mender +    flow rules  metrics       │
│              score        classifier  Policy DB   & failover               │
│                                                                             │
│                              ◄─────────── Feedback Loop ───────────────    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Stage ① — Monitoring

**Trigger:** Runs continuously on a 10-second Prometheus scrape interval.

**What it does:**
- Ryu's built-in stats collector queries each OpenFlow switch for port statistics (tx_bytes, rx_bytes, tx_errors, rx_errors, tx_dropped, rx_dropped) and flow table entries.
- A lightweight Python exporter running on each Mininet host reports CPU, memory, and ICMP round-trip time to a designated target host.
- All metrics land in Prometheus, queryable via PromQL.

**Output:** A time-series metric snapshot every 10 seconds, stored in Prometheus and mirrored to PostgreSQL's `metrics` table for ML feature extraction.

---

### Stage ② — Detection

**Trigger:** Every new metric snapshot enters the detection pipeline.

**What it does:**
- An Isolation Forest model (trained offline on "healthy" baseline data) assigns an anomaly score to each metric vector.
- If the anomaly score exceeds the configured threshold (default: 0.65 on a 0–1 scale), the snapshot is flagged as anomalous.
- A short-window vote (3 of last 5 samples must be anomalous) prevents single-sample noise from triggering a false alert.

**Output:** `AnomalySignal` object — contains the anomaly score, the flagged metrics, the timestamp, and the affected device/link.

**Escalation:** The signal is written to the `incidents` table with status `DETECTED` and published to the `sentinelnet:incidents` Redis channel.

---

### Stage ③ — Diagnosis

**Trigger:** An `AnomalySignal` with status `DETECTED`.

**What it does:**
- A Random Forest classifier takes the same 8-feature metric vector and predicts which of 5 failure types caused the anomaly.
- The classifier also returns a confidence score per class.
- If confidence < 50%, the incident is flagged for manual review while automated recovery still runs with the best-guess type.

**Failure types:** `LINK_FAILURE`, `CONGESTION`, `HIGH_LATENCY`, `DEVICE_FAILURE`, `REPEATED_FAILURE`

**Output:** `DiagnosisResult` — failure type label, confidence score, affected components (device IDs, link IDs).

**DB update:** Incident record updated with `diagnosis_type` and `confidence`.

---

### Stage ④ — Recovery Decision

**Trigger:** A `DiagnosisResult` with failure type and affected components.

**What it does:**
- The Recovery Recommender looks up the `policies` table for matching rules (failure_type × severity × affected_zone).
- If a policy exists and its action is AUTOMATED, the recommended action is passed forward.
- If no policy matches, the ML recommender predicts the best action from past successful recoveries (collaborative filtering on historical `recovery_actions` data).
- Confidence and estimated recovery time are attached to the decision.

**Output:** `RecoveryDecision` — action type, target device/link, parameters (e.g., new path, rate limit value), estimated duration.

**DB update:** New row in `recovery_actions` with status `PENDING`.

---

### Stage ⑤ — Recovery Execution

**Trigger:** An approved `RecoveryDecision`.

**What it does:**
- The FastAPI backend calls the Ryu REST API to modify the network.
- For link failover: installs new OpenFlow rules redirecting traffic to the backup path.
- For congestion: applies rate limiting via OpenFlow meter entries.
- For device failure: marks the device offline in the topology, reroutes all dependent flows.
- Execution is non-blocking; a timeout (default 15s) triggers escalation.

**Output:** `ExecutionResult` — success/failure, actual duration, error message if any.

**DB update:** `recovery_actions` row updated with status (`SUCCESS`, `FAILED`, `TIMEOUT`).

---

### Stage ⑥ — Verification

**Trigger:** Completed `ExecutionResult` (success or failure).

**What it does:**
- Waits 30 seconds for the network to stabilize post-action.
- Re-collects the same 8 metrics from the affected device/link.
- Runs a lightweight health check: are all KPIs back within normal thresholds?
- If healthy: incident marked `RESOLVED`, feedback data written.
- If not healthy: incident escalated to `MANUAL_REVIEW` and the pipeline re-runs with higher severity.

**Output:** `VerificationResult` — RESOLVED / ESCALATED, post-recovery metrics.

**Feedback:** Outcome + features written to the training feedback buffer for periodic model retraining.

---

## 3. Module Descriptions

| Module | File | Responsibility |
|---|---|---|
| `MetricsCollector` | `backend/monitoring/metrics_collector.py` | Active device poll, interface telemetry & DB persistence loop |
| `DeviceMonitor` | `backend/monitoring/device_monitor.py` | Concurrent health status (CPU, memory, ping, latency) |
| `NetworkMonitor` | `backend/monitoring/network_monitor.py` | Real ICMP ping, packet loss, OVS interface query, iperf3 bandwidth |
| `AnomalyDetector` | `backend/ai/anomaly_detector.py` | Isolation Forest scoring + voting |
| `FailureDiagnoser` | `backend/ai/failure_diagnoser.py` | Random Forest failure classification |
| `RecoveryRecommender` | `backend/ai/recovery_recommender.py` | Policy lookup + ML recommendation |
| `RecoveryEngine` | `backend/recovery/recovery_engine.py` | Orchestrates path selection, flow mods, verification, and rollbacks |
| `PathSelector` | `backend/recovery/path_selection.py` | Constrained Dijkstra with dynamic DPID and port resolution |
| `ActionExecutor` | `backend/recovery/action_executor.py` | Atomic OpenFlow flow mod pusher with per-hop verification |
| `RollbackManager` | `backend/recovery/rollback.py` | Pre-remediation flow table snapshotting and baseline restoration |
| `Verifier` | `backend/services/verifier.py` | Post-action metric health check |
| `PipelineOrchestrator` | `backend/services/orchestrator.py` | Coordinates stages, writes audit log |
| `SentinelNetController` | `sdn_controller/ryu_app.py` | Ryu app — OpenFlow event handling and ofctl_rest server |
| `TopologyManager` | `controller/topology_manager.py` | Live topology state, path computation |
| `FlowManager` | `controller/flow_manager.py` | Install/delete/modify flow rules |
| `IncidentRouter` | `backend/api/incidents.py` | REST endpoints for incident CRUD |
| `MetricsRouter` | `backend/api/metrics.py` | REST endpoints for metric queries |
| `WebSocketManager` | `backend/core/ws_manager.py` | Real-time push to React frontend |

---

## 4. Data Flow Diagram

```
Mininet Hosts/Switches
        │
        │  OpenFlow stats (port counters, flow tables)
        ▼
   Ryu Controller  ──────────────────────────────────────────┐
        │                                                    │
        │  Prometheus exporter endpoint                      │  OpenFlow commands
        ▼                                                    │  (install rules,
   Prometheus ─────────────────────────────┐                │   rate limits)
        │                                  │                │
        │  Metric scrape (every 10s)       │  PromQL        │
        ▼                                  ▼                │
  MetricsCollector                   Grafana UI             │
        │                                                   │
        │  Feature vector [8 metrics]                       │
        ▼                                                   │
  AnomalyDetector (Isolation Forest)                        │
        │                                                   │
        │  AnomalySignal (if score > threshold)             │
        ▼                                                   │
  FailureDiagnoser (Random Forest)                          │
        │                                                   │
        │  DiagnosisResult (type + confidence)              │
        ▼                                                   │
  RecoveryRecommender (Policy DB + ML)                      │
        │                                                   │
        │  RecoveryDecision (action + params)               │
        ▼                                                   │
  RecoveryExecutor ──────────────────────────────────────► Ryu
        │
        │  Wait 30s
        ▼
  Verifier (re-check metrics)
        │
        ├─── RESOLVED ─────► PostgreSQL incidents (status=RESOLVED)
        │                           │
        │                           └─► Redis pub/sub → WebSocket → React
        │
        └─── ESCALATED ────► Manual Review Queue + Alert
```

---

## 5. The Feedback Loop

One of the most important architectural properties of SentinelNet is its feedback loop — the system learns from every incident.

```
Every resolved incident produces:
  (feature_vector, failure_type, action_taken, outcome, recovery_time)
        │
        ▼
  feedback_buffer table in PostgreSQL
        │
        │  When buffer reaches 50 new samples:
        ▼
  Retraining job (nightly or manual trigger)
        │
        ├─► Anomaly Detector: update Isolation Forest contamination
        ├─► Failure Diagnoser: add new labeled samples to Random Forest
        └─► Recovery Recommender: update collaborative filter weights
```

**Why this matters:** Early in deployment, the recommender relies heavily on static policy rules. As incidents accumulate, the ML layer increasingly drives recommendations. The system gets better with use.

**Limitation:** This requires volume. With fewer than ~200 incidents, ML-driven recommendations are unreliable and policy rules dominate. See [05-AI-MODULES.md](05-AI-MODULES.md) for detailed limitations.

---

## 6. Component Interaction Map

```
┌─────────────┐     REST       ┌─────────────┐    SQL     ┌──────────────┐
│   React     │◄──────────────►│   FastAPI   │◄──────────►│  PostgreSQL  │
│  Frontend   │   WebSocket    │   Backend   │            │              │
└─────────────┘                └──────┬──────┘            └──────────────┘
                                      │                          ▲
                               Service calls                     │
                                      │                          │
                    ┌─────────────────┼─────────────────┐        │
                    │                 │                 │        │
             ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐  │
             │  Anomaly    │  │  Recovery   │  │   Verifier  │  │
             │  Detector   │  │  Executor   │  │             │  │
             └──────┬──────┘  └──────┬──────┘  └─────────────┘  │
                    │                │                            │
              ML models         Ryu REST API              Feedback buffer
                    │                │                            │
             ┌──────▼──────┐  ┌──────▼──────┐                    │
             │ Scikit-learn│  │ Ryu SDN     │────────────────────┘
             │ .pkl models │  │ Controller  │
             └─────────────┘  └──────┬──────┘
                                     │ OpenFlow 1.3
                              ┌──────▼──────┐
                              │  Mininet    │
                              │  (OVS + NS) │
                              └─────────────┘
```


---

## 7. Frontend Architecture & Screen Layout (Tier 4)

The frontend is an enterprise-grade React 18 Single Page Application (SPA) designed in strict accordance with the **Cyber Observability** design system (`cyber_observability/DESIGN.md`), providing sub-second situational awareness for NOC commanders and platform operators.

### Viewport Topology & Layout Engine

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ [32px] TELEMETRY STREAM TICKER: Ingress, Packet Loss, Active Substrate, Live Clocks     │
├───────────────────┬─────────────────────────────────────────────────────────────────────┤
│ [64px Sidebar]    │ [64px] TOP BAR: Breadcrumbs · Quick Search (⌘K) · Auto-Recovery Pill│
│                   ├─────────────────────────────────────────────────────────────────────┤
│ SentinelNet Brand │                                                                     │
│                   │                                                                     │
│ OPERATIONS        │                     CORE CONTENT VIEWPORT                           │
│  - Overview       │                                                                     │
│  - Live Topology  │  - DashboardPage: 6 KPI Cards, Mini Topology, Threat Outliers Feed  │
│  - AI Monitoring  │  - LiveTopologyPage: Full SDN Campus Canvas (C0, S1-S3, H1-H4, SRV1)│
│  - Fault Diag     │  - AIMonitoringPage: Isolation Forest Gauge, Waterfall & Simulator  │
│  - Incidents      │  - FaultDiagnosisPage: Master-Detail Root Cause Decision Matrix     │
│                   │  - RecoveryManagementPage: Safety Circuit Breaker & Queue Actuation │
│ AUTOMATION        │  - PoliciesPage: Governance Rules & Automation Priority Matrix      │
│  - Recovery Ops   │  - DevicesInventoryPage: Switch Port Table, IP/MAC, DPID Bindings   │
│  - Policies       │  - PredictiveMaintenancePage: Degradation Curves & Failure Horizon  │
│                   │  - DigitalTwinPage: Air-Gapped Simulation Sandbox & What-If Runner  │
│ INFRASTRUCTURE    │  - IntegrationsPage: 8 Service Connectors & Health Heartbeats       │
│  - Devices        │                                                                     │
│  - Maintenance    │                                                                     │
│  - Digital Twin   │                                                                     │
│  - Integrations   │                                                                     │
│                   │                                                                     │
│ Health: 98.2%     │                                                                     │
└───────────────────┴─────────────────────────────────────────────────────────────────────┘
```

### Design Token Implementation
- **Surface Foundations:** Layered deep glassmorphism (`#0d1322`, `#080e1d`, `#151b2b`, `#191f2f`, `#242a3a`)
- **Signal Accents:** Emerald primary (`#4edea3`), Cyan secondary (`#4cd7f6`), Amber warning (`#f59e0b`), Red fault (`#ef4444`)
- **Typography:** Plus Jakarta Sans (headlines), Inter (operational UI), JetBrains Mono (monospaced telemetry & flow rules)
- **Real-Time Layer:** WebSocket event bus synchronizing live SDN switch stats, anomaly scores, and auto-failovers.

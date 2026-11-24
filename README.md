# SentinelNet — AI-Powered Self-Healing Network

> An autonomous network management system that detects anomalies, diagnoses faults, and executes recovery actions without human intervention — built as a university semester project using Mininet, Ryu SDN controller, Python ML, and a production-grade Cyber Observability React NOC Dashboard.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Ryu](https://img.shields.io/badge/Ryu-4.34-green.svg)](https://ryu-sdn.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.165-orange.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://react.dev)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4-38B2AC.svg)](https://tailwindcss.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Project Status: Academic Prototype

> [!IMPORTANT]
> This is a university semester project. The self-healing pipeline works end-to-end in a controlled environment. Some features are cosmetic or incomplete — see the lists below and [`docs/11-KNOWN-ISSUES.md`](docs/11-KNOWN-ISSUES.md).

**Core self-healing workflow:** ✅ Functional (tested with 4 passing integration tests)  
**Dashboard UI:** ✅ Complete (React/TypeScript, production build passes)  
**Live Mininet/Ryu:** ⚠️ Linux/WSL2 only (Windows shows connection refused — expected)  
**Production hardening:** ⏳ Pending (see Known Issues)

### ✅ What Works

- JWT authentication (bcrypt + python-jose), 15-min access tokens, 7-day refresh tokens
- Role-based access control: admin / operator / viewer gates enforced on dangerous endpoints
- WebSocket streaming: 7 real-time event types, JWT auth via query param or first-frame message
- Fault injection API → creates Incident DB record → broadcasts WebSocket events
- Path selection (Dijkstra, constraint enforcement, bidirectional graph)
- Recovery engine: reroutes traffic, verifies via ping, rolls back on failure
- No-path → `escalated`, verification failure → `rolled_back` (both tested)
- Database (SQLite for dev, PostgreSQL for production), Alembic migrations, idempotent seed
- 3 RBAC user accounts seeded (`admin@sentinelnet.edu`, `operator@sentinelnet.edu`, `viewer@sentinelnet.edu`)
- React NOC dashboard: 12 pages, Tailwind cyber-observability design system
- AI pipeline: Isolation Forest (anomaly detection) + Random Forest (fault classification)

### ❌ What's Not Done Yet

- **MFA** — login UI checkbox is cosmetic; no TOTP/FIDO2 behind it (see KI-01)
- **Docker images** — `docker-compose.yml` exists but `Dockerfile.backend` / `Dockerfile.frontend` do not
- **Frontend component tests** — TypeScript compile only; no Vitest/Jest
- **Real-world accuracy** — AI trained on synthetic data only; real Mininet accuracy not measured
- **`prometheus.yml`** — compose mounts it but the file is not in the repository
- **h4 host link** — seeded device but no switch link (floating node in topology view)

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10+ | Tested on 3.11 |
| Node.js | 18+ | Frontend build |
| PostgreSQL | 15+ | Or SQLite for local dev (`aiosqlite`) |
| Ryu | 4.34 | **Linux/WSL2 only** |
| Mininet | 2.3.0 | **Linux/WSL2 only** (requires `sudo`) |

---

## What It Does

SentinelNet continuously monitors a simulated university campus network, runs AI models to detect abnormal traffic patterns, diagnoses root causes, executes zero-touch automated recovery actions (OpenFlow rerouting, meter rate-limiting, device isolation), and verifies recovery in a closed feedback loop — all orchestrated through a high-density, mission-critical Cyber Observability NOC Dashboard.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SentinelNet Pipeline                         │
│                                                                     │
│  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐  │
│  │ MONITORING│───▶│ DETECTION │───▶│ DIAGNOSIS │───▶│ DECISION  │  │
│  │           │    │           │    │           │    │           │  │
│  │ Mininet   │    │ Isolation │    │ Root-cause │   │ ML Recom- │  │
│  │ + Ryu     │    │ Forest    │    │ Classifier │   │ mendation │  │
│  │ + Prom.   │    │ Threshold │    │            │   │ Engine    │  │
│  └───────────┘    └───────────┘    └───────────┘    └─────┬─────┘  │
│                                                           │        │
│  ┌───────────┐    ┌───────────┐                          │        │
│  │VERIFICATION│◀──│ RECOVERY  │◀─────────────────────────┘        │
│  │           │    │ EXECUTION │                                    │
│  │ Metrics   │    │ Ryu API + │                                    │
│  │ Recheck   │    │ Flow Rules│                                    │
│  └─────┬─────┘    └───────────┘                                    │
│        │                                                           │
│        └─────────────────── Feedback Loop ──────────────────────▶ │
└─────────────────────────────────────────────────────────────────────┘

                 ┌──────────────────────────────────┐
                 │     React NOC Dashboard (SPA)    │
                 │   (Cyber Observability Design)   │
                 │                                  │
                 │  ┌───────────┐  ┌─────────────┐  │
                 │  │Live Topo  │  │Fault Diag   │  │
                 │  └───────────┘  └─────────────┘  │
                 │  ┌───────────┐  ┌─────────────┐  │
                 │  │AI Anomaly │  │Recovery Ops │  │
                 │  └───────────┘  └─────────────┘  │
                 └─────────────────┬────────────────┘
                                   │ REST / WebSocket
                        ┌──────────┴───────────┐
                        │    FastAPI Backend   │
                        │  + PostgreSQL + Redis│
                        └──────────────────────┘
```

---

## Complete Frontend Screen & Mockup Mapping

The frontend replicates all mockups in the workspace matching the `cyber_observability/DESIGN.md` specification:

| Route | Page Component | Mockup Folder | Key Features |
|---|---|---|---|
| `/login` | `LoginPage.tsx` | `sentinelnet_enterprise_login` | Split-screen neural topology canvas, zero-trust gateway, 1-click demo login profiles |
| `/dashboard` | `DashboardPage.tsx` | `sentinelnet_network_overview_dashboard` + `sentinelnet_noc_dashboard_container` | 6 KPI cards, mini SVG topology preview, AI anomaly feed, active remediation table, real-time ticker |
| `/topology` | `LiveTopologyPage.tsx` | `sentinelnet_live_network_topology` | Interactive campus network (C0, S1-S3, H1-H4, SRV1), packet flow anims, live fault injector with instant self-healing |
| `/ai` | `AIMonitoringPage.tsx` | `sentinelnet_ai_monitoring_anomaly_detection` | Semicircular Anomaly Gauge (0.00-1.00), 5-sample voting window, 8-feature attribution waterfall, interactive telemetry slider tester |
| `/diagnosis` | `FaultDiagnosisPage.tsx` | `sentinelnet_fault_diagnosis` | Master-detail RCA engine, Random Forest confidence distribution (5 failure classes), correlated symptoms, 1-click autonomous recovery |
| `/incidents` | `IncidentHistoryPage.tsx` | `sentinelnet_incident_history_analytics` | 30-day incident log, MTTR trends, multi-metric filtering, severity distribution, CSV report export |
| `/recovery` | `RecoveryManagementPage.tsx` | `sentinelnet_recovery_management` | Circuit breaker status, in-flight OpenFlow actuation queue, manual emergency actuation station, verification checks |
| `/policies` | `PoliciesPage.tsx` | `sentinelnet_recovery_policies_rules` | Policy priority matrix, automated vs manual approval gates, interactive policy rule builder modal |
| `/devices` | `DevicesInventoryPage.tsx` | `sentinelnet_devices_inventory` | Complete hardware inventory, DPID, IP/MAC, port traffic counters, operational states, ping trace |
| `/maintenance` | `PredictiveMaintenancePage.tsx` | `sentinelnet_predictive_maintenance` | Component degradation risk index, failure time horizons, proactive remediation scheduling |
| `/digital-twin` | `DigitalTwinPage.tsx` | `sentinelnet_digital_twin_recovery_testing` | Mirrored Mininet sandbox, what-if fault scenario injector, side-by-side production vs twin flow table diff |
| `/integrations` | `IntegrationsPage.tsx` | `sentinelnet_integrations_connections` | 8 connectors: Ryu SDN, Mininet, Prometheus, Grafana, PostgreSQL, Redis, Slack, PagerDuty webhooks |

---

## Tech Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Network Simulation | Mininet | 2.3.0 | Virtual network with Linux kernel namespaces & OVS |
| SDN Controller | Ryu | 4.34 | Centralized OpenFlow 1.3 controller & REST API |
| Metric Collection | Prometheus | 2.50+ | Time-series metric scraping on 10s interval |
| AI / ML | Scikit-learn | 1.4+ | Isolation Forest (unsupervised) + Random Forest (supervised) |
| Backend API | FastAPI | 0.110+ | Async REST endpoints, WebSockets, pipeline orchestrator |
| Database | PostgreSQL | 15+ | Relational store for incidents, metrics, policies |
| Cache / PubSub | Redis | 7+ | Real-time event bus (`sentinelnet:incidents`, `metrics`) |
| Frontend | React + TypeScript | 18.3 / 5.4 | Enterprise NOC SPA (Vite bundler) |
| Styling | Tailwind CSS | 3.4 | Cyber Observability design system tokens (`#0d1322`, `#4edea3`, `#4cd7f6`) |
| Icons & Fonts | Material Symbols + Google Fonts | — | Plus Jakarta Sans (headlines), Inter (body), JetBrains Mono (code/telemetry) |

---

## Folder Structure

```
stitch_sentinelnet_enterprise/
│
├── README.md                          ← You are here
├── CONTRIBUTING.md
├── .env.example
├── .gitignore
├── .dockerignore
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml
│
├── docs/
│   ├── 01-PROJECT-OVERVIEW.md
│   ├── 02-SYSTEM-ARCHITECTURE.md
│   ├── 03-TECH-STACK.md
│   ├── 04-NETWORK-TOPOLOGY.md
│   ├── 05-AI-MODULES.md
│   ├── 06-RECOVERY-SCENARIOS.md
│   ├── 07-API-DESIGN.md
│   ├── 08-DATABASE-SCHEMA.md
│   ├── 09-DEPLOYMENT.md
│   ├── 10-TESTING-EVALUATION.md
│   ├── 11-KNOWN-ISSUES.md        ← Honest limitations
│   └── 12-CHANGELOG.md           ← Per-prompt change history
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── index.css
│       ├── api/                       ← Axios API client modules
│       ├── components/
│       │   ├── layout/                ← AppShell, Sidebar, TopBar, ProtectedRoute
│       │   ├── ui/                    ← StatusBadge, SeverityBadge, KpiCard, Modal...
│       │   ├── topology/              ← TopologyMap (D3), DeviceDetailPanel
│       │   ├── incidents/             ← IncidentTable, IncidentPipelineView
│       │   ├── metrics/               ← MetricsChart (Recharts)
│       │   ├── ai/                    ← AnomalyScoreGauge, ConfidenceBar
│       │   ├── recovery/              ← RecoveryActionCard
│       │   └── policies/              ← PolicyTable
│       ├── contexts/                  ← AuthContext, WebSocketContext
│       ├── hooks/                     ← useTopology, useIncidents, useRecovery...
│       ├── pages/                     ← All 12 production-grade NOC views
│       ├── store/                     ← Zustand uiStore
│       ├── types/                     ← Full TypeScript domain types
│       └── utils/                     ← formatters, classnames, constants
│
├── backend/                           ← FastAPI application & AI pipelines
├── ai_models/                         ← Machine Learning anomaly detection & prediction pipeline
│   ├── generate_training_data.py      ← Generates 10,000 synthetic telemetry rows with multi-modal faults
│   ├── preprocessing.py               ← Preprocessor (cleaning, clipping, StandardScaler persistence)
│   ├── train_model.py                 ← IsolationForest & RandomForest training + evaluation.json export
│   ├── predict.py                     ← AnomalyPredictor class for live & batch inference
│   ├── requirements.txt               ← ML dependencies (scikit-learn, pandas, numpy, joblib)
│   └── README.md                      ← Model architecture, benchmarks, and training guide
├── sdn_controller/                    ← Ryu SDN OpenFlow 1.3 self-healing controller app & REST API
│   ├── ryu_app.py                     ← Main SelfHealingController app (OpenFlow 1.3 + WSGI REST)
│   ├── path_manager.py                ← Dijkstra topology shortest-path & failover flow installer
│   └── README.md                      ← Launching instructions, OpenFlow rule structure & curl examples
└── network_simulation/                ← Mininet topology, fault injection & traffic generator
    ├── topology.py                    ← University campus Mininet topology (s1, s2, s3, h1-h4, srv1)
    ├── failure_injector.py            ← Interactive fault injection console (tc netem, link/device kills)
    ├── traffic_generator.py           ← iperf3 synthetic baseline and bursty traffic generator
    └── README.md                      ← Simulation architecture, demo guide & troubleshooting
```

---

## Quick Start

### 1 — Start the React Frontend

```bash
cd frontend
npm install
npm run dev
# Dashboard opens at: http://localhost:5173
```

### 2 — Initialize Database & Run Migrations

```bash
# Apply schema migrations via Alembic
alembic upgrade head

# Seed realistic Mininet topology and historical telemetry (idempotent)
python -m backend.database.seed
```

### 3 — Start the FastAPI Backend

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload --port 8000
# API Docs: http://localhost:8000/docs
```

### 4 — Train AI Models (Optional if using pre-trained .pkl)

```bash
python ai_models/generate_training_data.py
python ai_models/train_model.py
# Saves trained_model.pkl, supervised_model.pkl, scaler.pkl, evaluation.json
```

### 5 — Start the Ryu Controller

> [!IMPORTANT]
> Both `ryu.app.ofctl_rest` and `sdn_controller/ryu_app.py` must be started together.
> `ofctl_rest` provides the standard REST endpoints (`/stats/switches`, `/stats/flow/{dpid}`, `/stats/flowentry/add`)
> called by SentinelNet's backend to discover switches and install recovery flows.

```bash
ryu-manager \
  --observe-links \
  --ofp-tcp-listen-port 6633 \
  --wsapi-port 8080 \
  ryu.app.ofctl_rest \
  sdn_controller/ryu_app.py
```

Verify controller startup:
```bash
python scripts/check_ryu.py
# Tests /health, /stats/switches, /stats/flow/1, and flow CRUD
```

### 6 — Start Mininet (Linux / WSL2 with sudo)

```bash
# Automated verification mode (pingall + iperf throughput test):
sudo python network_simulation/topology.py --test

# Or enter interactive Mininet CLI:
sudo python network_simulation/topology.py
```

---

### Default Seeded User Accounts (RBAC)

The database seed script initializes three accounts for testing role-based access control:

| Email / Username | Password | Role | Clearance Level & Permissions |
|---|---|---|---|
| `admin@sentinelnet.edu` (`admin`) | `sentinelpass` | `admin` | L3: Full system & policy administration, recovery mode mutation, and actuation |
| `operator@sentinelnet.edu` (`operator`) | `sentinelpass` | `operator` | L2: Automated/manual recovery execution, rollback, and fault injection |
| `viewer@sentinelnet.edu` (`viewer`) | `sentinelpass` | `viewer` | L1: Read-only telemetry, topology map, and incident audit view |

> **Note:** Demo quick-fill profiles on the login page are controlled via `VITE_DEMO_MODE=true` in `frontend/.env`.

---

## Documentation Index

| Doc | Description |
|---|---|
| [01-PROJECT-OVERVIEW](docs/01-PROJECT-OVERVIEW.md) | Problem statement, objectives, scope, expected university project outcomes |
| [02-SYSTEM-ARCHITECTURE](docs/02-SYSTEM-ARCHITECTURE.md) | 6-stage closed-loop pipeline, data flow, feedback loops, frontend architecture |
| [03-TECH-STACK](docs/03-TECH-STACK.md) | Detailed technology choices, rationale, alternatives considered, design system |
| [04-NETWORK-TOPOLOGY](docs/04-NETWORK-TOPOLOGY.md) | Campus network topology, ASCII diagram, IP addressing table, routing paths |
| [05-AI-MODULES](docs/05-AI-MODULES.md) | Isolation Forest anomaly detection, Random Forest diagnosis, recovery recommenders |
| [06-RECOVERY-SCENARIOS](docs/06-RECOVERY-SCENARIOS.md) | 5 failure scenarios, step-by-step traces, verification checks |
| [07-API-DESIGN](docs/07-API-DESIGN.md) | REST endpoints, JSON schemas, WebSocket event specifications |
| [08-DATABASE-SCHEMA](docs/08-DATABASE-SCHEMA.md) | PostgreSQL schema, DDL tables, indexes, example records |
| [09-DEPLOYMENT](docs/09-DEPLOYMENT.md) | Local setup, Docker Compose all-in-one, troubleshooting guide |
| [10-TESTING-EVALUATION](docs/10-TESTING-EVALUATION.md) | Evaluation KPIs, test experiments, verification status table, benchmarks, academic discussion |
| [11-KNOWN-ISSUES](docs/11-KNOWN-ISSUES.md) | Honest list of 10 known limitations: MFA cosmetic, synthetic data, Ryu Linux-only, missing Dockerfiles |
| [12-CHANGELOG](docs/12-CHANGELOG.md) | Per-prompt change history from initial scaffold through integration tests |
| [CONTRIBUTING](CONTRIBUTING.md) | Contribution standards, code style, git branch strategy |

---

## License

MIT © 2024 — University Semester Project

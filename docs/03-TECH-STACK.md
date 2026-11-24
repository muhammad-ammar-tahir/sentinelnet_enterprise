# 03 — Technology Stack

## Table of Contents
1. [Stack at a Glance](#1-stack-at-a-glance)
2. [Network Simulation Layer](#2-network-simulation-layer)
3. [SDN Control Layer](#3-sdn-control-layer)
4. [Monitoring & Observability](#4-monitoring--observability)
5. [AI / ML Layer](#5-ai--ml-layer)
6. [Backend & API](#6-backend--api)
7. [Database & Caching](#7-database--caching)
8. [Frontend](#8-frontend)
9. [DevOps & Tooling](#9-devops--tooling)
10. [Technology Decision Log](#10-technology-decision-log)

---

## 1. Stack at a Glance

| Category | Technology | Version | License |
|---|---|---|---|
| Network simulation | Mininet | 2.3.0 | BSD |
| SDN controller | Ryu | 4.34 | Apache 2.0 |
| Metric collection | Prometheus | 2.50+ | Apache 2.0 |
| Visualization | Grafana | 10+ | AGPL-3.0 |
| ML framework | Scikit-learn | 1.4+ | BSD |
| Numerical compute | NumPy + Pandas | 1.26 / 2.0 | BSD |
| Backend language | Python | 3.10+ | PSF |
| Web framework | FastAPI | 0.110+ | MIT |
| ASGI server | Uvicorn | 0.29+ | BSD |
| Database | PostgreSQL | 15+ | PostgreSQL License |
| ORM | SQLAlchemy | 2.0+ | MIT |
| Cache / Queue | Redis | 7+ | RSAL / BSD |
| Frontend | React | 18+ | MIT |
| UI language | TypeScript | 5+ | Apache 2.0 |
| Build tool | Vite | 5+ | MIT |
| Containerization | Docker + Compose | 24+ / 2+ | Apache 2.0 |

---

## 2. Network Simulation Layer

### Mininet 2.3

| Field | Detail |
|---|---|
| **What it is** | A network emulator that creates virtual networks using real Linux kernel namespaces, Open vSwitch, and virtual Ethernet pairs |
| **Why we use it** | The only tool that simulates a full network (switches, hosts, links) with realistic bandwidth and delay constraints on a single machine — no physical hardware needed |
| **Role in SentinelNet** | Provides the simulated university network: 3 switches, 4 hosts, 1 server, 2 backup links |
| **Key feature used** | `TCLink` for bandwidth and delay constraints; `OVSSwitch` for OpenFlow 1.3 support |
| **Alternative considered** | GNS3 — rejected: heavier, requires router images, harder to script |
| **Limitation** | Kernel namespace overhead limits scalability; not usable on pure Windows (needs Linux or WSL2) |

### Open vSwitch (OVS)

| Field | Detail |
|---|---|
| **What it is** | A production-grade open-source virtual switch used by Mininet as the data plane |
| **Why we use it** | Supports OpenFlow 1.3, which Ryu requires for flow table manipulation |
| **Role** | Acts as each of the 3 simulated switches; Ryu pushes flow rules to OVS via OpenFlow |

---

## 3. SDN Control Layer

### Ryu 4.34

| Field | Detail |
|---|---|
| **What it is** | A Python-based SDN controller framework with OpenFlow 1.0–1.5 support |
| **Why we use it** | Pure Python — integrates naturally with our ML pipeline; has a built-in REST API; actively used in SDN research |
| **Role in SentinelNet** | Central control plane: handles switch connections, topology discovery, flow rule installation, and exposes a REST API for the backend to trigger network changes |
| **Key APIs used** | `ofp_event.EventOFPSwitchFeatures` (switch handshake), `ofp_event.EventOFPPortStatus` (link state), `ofproto_v1_3.OFPFlowMod` (flow rules), Ryu REST API for external calls |
| **Alternative considered** | ONOS — rejected: Java-based, overkill for a semester project, steep learning curve |
| **Limitation** | Ryu is in maintenance mode (no new features post-2020); adequate for academic use but not recommended for new production systems |

---

## 4. Monitoring & Observability

### Prometheus 2.50+

| Field | Detail |
|---|---|
| **What it is** | An open-source time-series database and monitoring toolkit with a pull-based scraping model |
| **Why we use it** | The de-facto standard for infrastructure metrics; excellent Python client library; powerful PromQL query language for threshold alerts and ML feature extraction |
| **Role in SentinelNet** | Scrapes metrics from: (a) Ryu's built-in Prometheus endpoint (port counters, flow counts), (b) custom exporters on Mininet hosts (CPU, RTT) |
| **Scrape interval** | 10 seconds (configurable in `monitoring/prometheus.yml`) |
| **Key metrics collected** | `port_rx_bytes`, `port_tx_bytes`, `port_rx_errors`, `port_tx_dropped`, `flow_table_size`, `host_rtt_ms`, `host_cpu_percent`, `link_utilization_percent` |
| **Alternative considered** | InfluxDB — rejected: more complex setup, less Python-native |

### Grafana 10+

| Field | Detail |
|---|---|
| **What it is** | An open-source visualization and dashboarding platform that connects to Prometheus |
| **Why we use it** | Pre-built dashboards for network metrics; allows non-developer NOC operators to inspect raw time-series without writing code |
| **Role in SentinelNet** | Supplementary to the React dashboard — shows raw metric graphs, alert history, and long-term trends |
| **Dashboards** | Link utilization over time, anomaly score timeline, incident rate per hour |

---

## 5. AI / ML Layer

### Scikit-learn 1.4+

| Field | Detail |
|---|---|
| **What it is** | The standard Python ML library — consistent API, well-tested, excellent documentation |
| **Why we use it** | Provides `IsolationForest` (anomaly detection), `RandomForestClassifier` (failure diagnosis), and `NearestNeighbors` (recovery recommendation) out of the box |
| **Role in SentinelNet** | Powers all 3 AI modules; models serialized as `.pkl` files and loaded at startup |
| **Alternative considered** | PyTorch / TensorFlow — rejected: deep learning is overkill for 8-feature tabular data with limited samples |

### NumPy + Pandas

| Field | Detail |
|---|---|
| **What it is** | Foundation libraries for numerical arrays and tabular data manipulation |
| **Why we use it** | Feature vector construction, sliding window statistics, training data ETL |
| **Role** | Transform raw Prometheus metric dicts into normalized `np.ndarray` for model inference |

### Joblib

| Field | Detail |
|---|---|
| **What it is** | Scikit-learn's recommended serialization and parallel compute library |
| **Why we use it** | Save and load trained `.pkl` models; run cross-validation in parallel during retraining |

---

## 6. Backend & API

### FastAPI 0.110+

| Field | Detail |
|---|---|
| **What it is** | A modern, high-performance Python web framework based on ASGI and Pydantic |
| **Why we use it** | Automatic OpenAPI docs (`/docs`), async support for WebSocket, type-safe request/response schemas with Pydantic, excellent for rapid development |
| **Role in SentinelNet** | Exposes all REST endpoints (`/api/metrics`, `/api/detect`, `/api/incidents`, `/api/recover`), WebSocket for live topology and incident push to the React frontend |
| **Alternative considered** | Flask — rejected: synchronous, lacks native WebSocket, no built-in validation |
| **Alternative considered** | Django REST Framework — rejected: too heavy for a data-centric API |

### Uvicorn

| Field | Detail |
|---|---|
| **What it is** | ASGI server built on `uvloop` and `httptools` |
| **Why we use it** | Required to run FastAPI in async mode; significantly faster than WSGI servers for concurrent WebSocket connections |

### Pydantic 2.0+

| Field | Detail |
|---|---|
| **Role** | Request/response schema validation and serialization; defines all API data contracts |

---

## 7. Database & Caching

### PostgreSQL 15+

| Field | Detail |
|---|---|
| **What it is** | The world's most advanced open-source relational database |
| **Why we use it** | Structured incident and audit data needs ACID transactions, complex JOIN queries, and foreign key constraints — a time-series DB alone is insufficient |
| **Role in SentinelNet** | Stores: devices, links, incidents, recovery_actions, metrics snapshots, policies, users |
| **Alternative considered** | SQLite — rejected: not safe for concurrent async writes from FastAPI |
| **Alternative considered** | MongoDB — rejected: relational data model (incidents ↔ actions ↔ policies) is better served by SQL |

### SQLAlchemy 2.0 + Alembic

| Field | Detail |
|---|---|
| **Role** | ORM for all database interaction; Alembic for schema migrations |

### Redis 7+

| Field | Detail |
|---|---|
| **What it is** | In-memory data structure store supporting pub/sub, streams, and key-value |
| **Why we use it** | The pipeline produces events (AnomalySignal, DiagnosisResult, etc.) that multiple consumers need to react to — Redis pub/sub channels are ideal |
| **Role in SentinelNet** | (a) `sentinelnet:incidents` channel — publishes new incidents to WebSocket manager, (b) `sentinelnet:metrics` stream — latest metric snapshot for fast frontend polling, (c) Recovery action job queue |

---

## 8. Frontend

### React 18 + TypeScript

| Field | Detail |
|---|---|
| **What it is** | A declarative UI library with hooks-based state management; TypeScript adds static type safety |
| **Why we use it** | Component-based architecture matches the NOC dashboard's modular panels; large ecosystem; team familiarity |
| **Role in SentinelNet** | NOC dashboard with: live topology map (D3.js), incident list, AI confidence panel, metric graphs, recovery policy editor |
| **Alternative considered** | Vue.js — equal capability; React chosen for ecosystem size and hiring familiarity |

### Vite

| Field | Detail |
|---|---|
| **Role** | Build tool and dev server; near-instant HMR for fast frontend iteration |

### React Query (TanStack Query)

| Field | Detail |
|---|---|
| **Role** | Data fetching, caching, and synchronization for all REST API calls |

### D3.js

| Field | Detail |
|---|---|
| **Role** | Force-directed graph for the live network topology visualization |

### Tailwind CSS

| Field | Detail |
|---|---|
| **Role** | Utility-first CSS; keeps the dashboard dark-themed and consistent without a UI library |

---

## 9. DevOps & Tooling

### Docker + Docker Compose

| Field | Detail |
|---|---|
| **Role** | Containerizes PostgreSQL, Redis, Prometheus, Grafana, and the FastAPI backend for one-command startup |
| **Note** | Mininet and Ryu run on the host (not in containers) because Mininet needs kernel namespace access |

### pytest

| Field | Detail |
|---|---|
| **Role** | Unit and integration tests for the AI modules, API endpoints, and recovery logic |

### Black + isort + flake8

| Field | Detail |
|---|---|
| **Role** | Python code formatting and linting; enforced in CI |

### ESLint + Prettier

| Field | Detail |
|---|---|
| **Role** | TypeScript/React linting and formatting |

---

## 10. Technology Decision Log

The following decisions were explicitly debated and documented:

| Decision | Options Considered | Choice | Reason |
|---|---|---|---|
| ML framework | PyTorch, TensorFlow, Scikit-learn | **Scikit-learn** | Tabular data, small dataset, fastest dev time |
| SDN controller | ONOS, OpenDaylight, Ryu | **Ryu** | Python, simplest API, university standard |
| Backend framework | Flask, Django, FastAPI | **FastAPI** | Async, WebSocket, auto-docs, type safety |
| Database | PostgreSQL, MongoDB, SQLite | **PostgreSQL** | ACID, relational schema, concurrent writes |
| Anomaly detection algorithm | Z-score, DBSCAN, Isolation Forest | **Isolation Forest** | Unsupervised, no labeled data needed initially |
| Network simulator | GNS3, EVE-NG, Mininet | **Mininet** | Scriptable, Pythonic, OpenFlow native |


---

## 11. Frontend Component Library & Design System

The SentinelNet frontend is built as a modular enterprise component hierarchy:

| Category | Components | Responsibilities |
|---|---|---|
| **Layout** | `AppShell`, `Sidebar`, `TopBar`, `ProtectedRoute` | Ticker strip, navigation drawer, clearance badges, live clock feeds |
| **Topology** | `TopologyMap`, `DeviceDetailPanel` | SVG/D3 force graph, packet animations, OpenFlow port state inspection |
| **Incidents** | `IncidentTable`, `IncidentPipelineView` | 6-stage step progression, severity tags, filterable audit records |
| **AI Telemetry** | `AnomalyScoreGauge`, `ConfidenceBar` | Semicircular score dials, Shapley waterfall, RF class distributions |
| **Recovery** | `RecoveryActionCard` | In-flight execution logs, rollback guards, circuit breaker trip states |
| **Governance** | `PolicyTable` | Policy priority matrix, automated vs manual approval gates |
| **Shared UI** | `StatusBadge`, `SeverityBadge`, `KpiCard`, `Modal`, `EmptyState` | Consistent atomic status indicators, dialogs, loading states |

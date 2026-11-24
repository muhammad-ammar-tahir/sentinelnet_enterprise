# SentinelNet Backend — AI-Powered Self-Healing Network

Production-grade Python backend microservices built with **FastAPI**, **SQLAlchemy**, **Scikit-learn**, and **Ryu REST Client** for automated network observability, anomaly detection, root-cause diagnosis, and closed-loop SDN self-healing.

---

## 📁 Architecture Overview

```
backend/
├── main.py                     # FastAPI application entry & lifecycle
├── config.py                   # Pydantic Settings & environment variables
├── requirements.txt            # Backend dependencies
├── monitoring/                 # Active network & Prometheus metric collection
│   ├── network_monitor.py      # ICMP ping & SNMP counter polling
│   ├── device_monitor.py       # Switch/host availability & health checks
│   └── metrics_collector.py    # Prometheus PromQL client
├── detection/                  # Fault & anomaly detection
│   ├── anomaly_detection.py    # Scikit-learn Isolation Forest ML detector
│   ├── fault_detection.py      # Rule-based + ML hybrid detection
│   └── prediction.py           # Metric trend forecasting & breach prediction
├── diagnosis/                  # Failure analysis
│   └── root_cause.py           # Multi-metric root cause analysis
├── recovery/                   # Self-healing engine
│   ├── recovery_engine.py      # 6-stage lifecycle orchestrator
│   ├── path_selection.py       # Constrained Dijkstra optimal rerouting
│   ├── action_executor.py      # Ryu OpenFlow flow-mod pusher
│   └── rollback.py             # Action snapshot & automatic rollback
├── controller/                 # SDN communication
│   └── sdn_controller.py       # Ryu REST API client (OpenFlow 1.3)
├── database/                   # Persistence
│   ├── database.py             # Async & sync SQLAlchemy engines and sessions
│   ├── models.py               # ORM models (devices, links, incidents, etc.)
│   ├── seed.py                 # Idempotent realistic Mininet seeding script
│   └── migrations/             # Alembic schema migrations
├── ws/                         # Real-Time WebSockets
│   └── manager.py              # ConnectionManager & event broadcaster
└── api/                        # HTTP REST API
    ├── auth.py                 # JWT issuance, refresh, bcrypt hashing & RBAC
    ├── routes.py               # API endpoints (/metrics, /detect, /recovery, /policies)
    └── deps.py                 # FastAPI dependency injection helpers
```

---

## 🚀 Quick Start (Running Backend Alone)

### 1. Prerequisites
- Python 3.10+
- (Optional) PostgreSQL and Redis running locally or via Docker
- (Optional) Mininet & Ryu controller running on Linux or VM

### 2. Setup Virtual Environment
```bash
# Navigate to project root
cd stitch_sentinelnet_enterprise

# Create and activate virtual environment
python -m venv venv

# On Windows:
.\venv\Scripts\activate

# On Linux/macOS:
source venv/bin/activate
```

### 3. Install Backend Dependencies
```bash
pip install -r backend/requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` or set:
```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sentinelnet
RYU_BASE_URL=http://localhost:8080
PROMETHEUS_URL=http://localhost:9090
DEBUG=True
```

### 5. Launch Development Server
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🌐 API Documentation & Interactive Swagger
Once running, open your browser to:
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🧪 Key Endpoints & RBAC Protection

### Authentication & Sessions
| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | Public | Rate-limited (5/min). Issues JWT access & refresh tokens. |
| `POST` | `/api/auth/refresh` | Public | Validates 7-day refresh token, returns new 15-min access token. |
| `GET` | `/api/auth/me` | `viewer` | Returns profile and clearance level of authenticated operator. |

### Telemetry & Remediation
| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `GET` | `/health` | Public | Service health probe. |
| `GET` | `/api/metrics/live` | Public | Instantaneous telemetry aggregations from database. |
| `GET` | `/api/topology` | Public | Current SDN switches, links, and hosts. |
| `GET` | `/api/incidents` | Public | Active and historical failure incidents. |
| `POST` | `/api/detect` | Public | Run anomaly evaluation on telemetry snapshot. |
| `POST` | `/api/recovery/execute` | `operator` | Actuates automated or manual SDN rerouting. |
| `POST` | `/api/recovery/rollback` | `operator` | Rolls back a previously actuated recovery action. |
| `POST` | `/api/topology/fail` | `operator` | Injects synthetic link or device failure. |
| `PUT` | `/api/recovery/mode` | `admin` | Toggles autonomous vs semi-autonomous self-healing mode. |
| `GET` | `/api/policies` | `viewer` | Lists active self-healing rules. |
| `POST` | `/api/policies` | `admin` | Creates a new self-healing policy rule. |
| `PUT` | `/api/policies/{id}` | `admin` | Updates an existing self-healing policy. |
| `DELETE`| `/api/policies/{id}` | `admin` | Deletes a self-healing policy. |

### Real-Time WebSocket Streaming
| Protocol | Path | Auth | Description |
|---|---|---|---|
| `WS` | `/ws/live` | JWT | Real-time broadcast channel (`METRICS_UPDATED`, `ANOMALY_DETECTED`, `INCIDENT_CREATED`, `TOPOLOGY_CHANGED`, `RECOVERY_STARTED`, `RECOVERY_COMPLETED`, `RECOVERY_FAILED`). Rejects unauthorized sockets with closure code `1008`. |


# 09 — Deployment Guide

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Architecture Decisions for Local Run](#2-architecture-decisions-for-local-run)
3. [Manual Setup (Step-by-Step)](#3-manual-setup-step-by-step)
4. [Docker Compose Setup](#4-docker-compose-setup)
5. [Environment Variables Reference](#5-environment-variables-reference)
6. [Verifying Each Component](#6-verifying-each-component)
7. [Stopping Everything](#7-stopping-everything)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Prerequisites

### Operating System

> **Important:** Mininet requires Linux kernel features (network namespaces, Open vSwitch). It **cannot** run natively on Windows or macOS. Use one of:
> - Ubuntu 20.04 / 22.04 LTS (native or VM)
> - WSL2 on Windows 11 with `systemd` and OVS installed
> - A Linux VM (VirtualBox / VMware)

### Software Requirements

| Software | Version | Install |
|---|---|---|
| Python | 3.10+ | `apt install python3.10 python3-pip` |
| Mininet | 2.3.0 | See Section 3.1 |
| Open vSwitch | 2.17+ | `apt install openvswitch-switch` |
| Ryu | 4.34 | `pip install ryu` |
| PostgreSQL | 15+ | `apt install postgresql-15` |
| Redis | 7+ | `apt install redis-server` |
| Node.js | 18+ | `nvm install 18` |
| Docker | 24+ | docs.docker.com/engine/install/ubuntu |
| Docker Compose | 2+ | Included with Docker Desktop |

### Hardware Recommendations

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8 GB |
| Disk | 10 GB | 20 GB |

---

## 2. Architecture Decisions for Local Run

Not all components can run in Docker:

| Component | Run In | Reason |
|---|---|---|
| Mininet + OVS | **Host** | Requires kernel namespaces; Docker isolation breaks OVS |
| Ryu Controller | **Host** | Must connect to OVS via OpenFlow TCP; easier on host |
| PostgreSQL | Docker or Host | Either works |
| Redis | Docker or Host | Either works |
| Prometheus | Docker or Host | Either works |
| FastAPI Backend | Docker or Host | Either works |
| React Frontend | Host (dev) | Vite dev server for HMR |
| Grafana | Docker | Easiest via Compose |

**Recommended hybrid approach:** Mininet + Ryu on host; everything else in Docker.

---

## 3. Manual Setup (Step-by-Step)

### 3.1 — Install Mininet

```bash
git clone https://github.com/mininet/mininet.git
cd mininet
git checkout 2.3.0
sudo util/install.sh -nv      # installs Mininet + OVS + NOX (skip NOX if prompted)
```

Verify:
```bash
sudo mn --test pingall
# Should print: Results: 0% dropped
```

### 3.2 — Install Ryu

```bash
pip install ryu==4.34
# Ryu requires older eventlet:
pip install eventlet==0.30.2
```

Verify:
```bash
ryu-manager --version
# Should print: ryu 4.34
```

### 3.3 — PostgreSQL Setup

```bash
sudo apt install postgresql-15 -y
sudo systemctl start postgresql

# Create database and user
sudo -u postgres psql <<EOF
CREATE USER sentinelnet WITH PASSWORD 'sentinelpass';
CREATE DATABASE sentinelnet OWNER sentinelnet;
GRANT ALL PRIVILEGES ON DATABASE sentinelnet TO sentinelnet;
EOF
```

Apply schema migrations:
```bash
cd backend
alembic upgrade head
```

Seed initial data (devices, links, default policies):
```bash
python scripts/seed_db.py
```

### 3.4 — Redis Setup

```bash
sudo apt install redis-server -y
sudo systemctl start redis-server
redis-cli ping   # should return PONG
```

### 3.5 — Python Backend

```bash
# From project root
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, REDIS_URL, RYU_BASE_URL, SECRET_KEY

# Start FastAPI
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API available at: `http://localhost:8000`
Interactive docs: `http://localhost:8000/docs`

### 3.6 — Ryu Controller

> [!IMPORTANT]
> Both `ryu.app.ofctl_rest` **and** `sdn_controller/ryu_app.py` must be loaded
> in the same `ryu-manager` command.  `ofctl_rest` provides the standard REST
> endpoints (`/stats/switches`, `/stats/flow/{dpid}`, `/stats/flowentry/add`, …)
> that the FastAPI backend calls for switch discovery and flow installation.
> Loading only the custom app means those endpoints are never registered and
> switch discovery + recovery will fail silently.

```bash
# In a new terminal
source venv/bin/activate
ryu-manager \
  --observe-links \
  --ofp-tcp-listen-port 6633 \
  --wsapi-port 8080 \
  ryu.app.ofctl_rest \
  sdn_controller/ryu_app.py
```

Expected output:
```
loading app ryu.app.ofctl_rest
loading app sdn_controller/ryu_app.py
loading app ryu.controller.ofp_handler
loading app ryu.topology.switches
...
[INFO] sentinelnet.sdn_controller: Ryu started with ofctl_rest (REST on :8080) + selfhealing app
[INFO] sentinelnet.sdn_controller: SelfHealingController initialized successfully.
connected socket:<...> address:('127.0.0.1', 6633)
```

After Ryu is running, verify that both apps are correctly loaded:

```bash
python scripts/check_ryu.py
# All 4 checks should print PASS.
# If Mininet is not running yet, checks 3 and 4 are skipped (no switches).
```

### 3.7 — Mininet Topology & Traffic Simulation

```bash
# In a new terminal (requires sudo)
# Run automated verification test:
sudo python network_simulation/topology.py --test

# Or enter interactive Mininet CLI:
sudo python network_simulation/topology.py --controller-ip 127.0.0.1

# Generate synthetic baseline campus traffic:
sudo python network_simulation/traffic_generator.py --baseline

# Inject failures during live demonstrations:
sudo python network_simulation/failure_injector.py
```

Expected Ryu log on switch connections:
```
switch entered. dpid=...
switch entered. dpid=...
switch entered. dpid=...
```

### 3.8 — Prometheus

```bash
# Download Prometheus binary
wget https://github.com/prometheus/prometheus/releases/download/v2.50.0/prometheus-2.50.0.linux-amd64.tar.gz
tar xfz prometheus-*.tar.gz
cd prometheus-2.50.0.linux-amd64

# Start with SentinelNet config
./prometheus --config.file=../../monitoring/prometheus.yml
```

Prometheus UI: `http://localhost:9090`

### 3.9 — Frontend

```bash
# In a new terminal
cd frontend
npm install
npm run dev
```

Dashboard: `http://localhost:5173`

---

## 4. Docker Compose Setup

The Compose file handles PostgreSQL, Redis, Prometheus, Grafana, and the FastAPI backend.
Mininet and Ryu still run on the host.

### docker-compose.yml

```yaml
version: "3.9"

services:

  postgres:
    image: postgres:15-alpine
    container_name: sentinelnet_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: sentinelnet
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d sentinelnet"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: sentinelnet_redis
    restart: unless-stopped
    ports:
      - "6379:6379"

  prometheus:
    image: prom/prometheus:latest
    container_name: sentinelnet_prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    extra_hosts:
      - "host.docker.internal:host-gateway"
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"

  grafana:
    image: grafana/grafana:latest
    container_name: sentinelnet_grafana
    restart: unless-stopped
    ports:
      - "3001:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: sentinelnet_backend
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/sentinelnet
      DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet
      RYU_BASE_URL: http://host.docker.internal:8080
      PROMETHEUS_URL: http://prometheus:9090
      REDIS_URL: redis://redis:6379/0
      ENVIRONMENT: production
    extra_hosts:
      - "host.docker.internal:host-gateway"
    command: >
      sh -c "alembic upgrade head &&
             python -m backend.database.seed &&
             uvicorn backend.main:app --host 0.0.0.0 --port 8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.frontend
    container_name: sentinelnet_frontend
    restart: unless-stopped
    ports:
      - "5173:5173"
    environment:
      VITE_API_BASE_URL: http://localhost:8000/api
      VITE_WS_URL: ws://localhost:8000/ws
      VITE_DEMO_MODE: "false"
    command: npm run dev -- --host 0.0.0.0
    depends_on:
      - backend

volumes:
  postgres_data:
  prometheus_data:
  grafana_data:
```

### Starting Docker Services

```bash
# Build and start all containerized services
docker compose up --build -d

# Check all are healthy
docker compose ps

# View backend logs
docker compose logs -f backend

# Stop all
docker compose down
```

### Accessing Services

| Service | URL | Credentials |
|---|---|---|
| React Dashboard | http://localhost:5173 | admin / password |
| FastAPI Docs | http://localhost:8000/docs | Bearer token from /api/auth/login |
| Prometheus | http://localhost:9090 | None |
| Grafana | http://localhost:3000 | admin / admin |
| PostgreSQL | localhost:5432 | sentinelnet / sentinelpass |

---

## 5. Environment Variables Reference

See [`.env.example`](../.env.example) for the full list. Key variables:

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://sentinelnet:pass@localhost:5432/sentinelnet` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `RYU_BASE_URL` | Ryu REST API URL | `http://localhost:8080` |
| `SECRET_KEY` | JWT signing key (keep secret!) | `your-256-bit-secret` |
| `PROMETHEUS_URL` | Prometheus HTTP endpoint | `http://localhost:9090` |
| `ANOMALY_THRESHOLD` | Isolation Forest trigger threshold | `0.65` |
| `SCRAPE_INTERVAL_SEC` | Metric polling interval | `10` |
| `VOTING_WINDOW` | Anomaly voting window size | `5` |
| `VOTING_MIN_COUNT` | Minimum votes to trigger alert | `3` |

---

## 6. Verifying Each Component

Run the full verification script:
```bash
python scripts/verify_setup.py
```

Or verify manually:

```bash
# 1. Database
psql postgresql://sentinelnet:sentinelpass@localhost:5432/sentinelnet -c "\dt"

# 2. Redis
redis-cli ping

# 3. Ryu API (after starting Ryu + Mininet)
curl http://localhost:8080/v1.0/topology/switches | python3 -m json.tool

# 4. Backend health
curl http://localhost:8000/api/health

# 5. Prometheus
curl http://localhost:9090/-/healthy

# 6. Inject a test fault and check detection
python scripts/inject_fault.py --fault link_failure --link L1 --duration 60
# Monitor: curl http://localhost:8000/api/incidents?limit=5
```

---

## 7. Stopping Everything

```bash
# Stop Docker services
docker compose down

# Stop Mininet (from Mininet CLI)
mininet> exit
sudo mn -c          # clean up OVS state

# Kill Ryu (Ctrl+C in its terminal, or)
pkill -f "ryu-manager"

# Kill backend (Ctrl+C in its terminal)

# Stop Prometheus (Ctrl+C or)
pkill prometheus
```

---

## 8. Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `mn: command not found` | Mininet not in PATH | Add `/usr/local/bin` to PATH, or use `sudo mn` |
| Ryu shows no switches connecting | Mininet using wrong controller IP | Pass `--controller-ip 127.0.0.1` to topology.py |
| `eventlet` import error in Ryu | Wrong eventlet version | `pip install eventlet==0.30.2` |
| PostgreSQL connection refused | Service not started | `sudo systemctl start postgresql` |
| Backend crashes on startup | Missing .env variables | Check all required vars are set in .env |
| `port 6653 already in use` | Old Ryu still running | `pkill -f ryu-manager` |
| OVS bridges not cleaned up | Mininet crashed | `sudo mn -c` |
| `EADDRINUSE 5432` | PostgreSQL port in use | Check if another PG instance is running |
| Docker: backend can't reach Ryu | Ryu runs on host, not in Docker | Set `RYU_BASE_URL=http://host.docker.internal:8080` |


---

## 9. Frontend Verification & Development Server

To preview and interact with the Cyber Observability NOC Dashboard:

```bash
cd frontend
npm install
npm run dev
# Browser opens at: http://localhost:5173
```

### Available Demo Accounts
- **NOC Commander (L3):** `admin@sentinelnet.edu` / `sentinelpass` (Full autonomous actuation & policy editing)
- **Network Operator (L2):** `operator@sentinelnet.edu` / `sentinelpass` (Topology inspection, manual rerouting)
- **1-Click Quick Demo:** Click "admin / L3" or "operator / L2" on the login screen for instant credentials fill.

### Live Topology Fault Injection in UI
1. Navigate to `/topology` (Live Network Topology)
2. Use the **Test Self-Healing** button dock in the upper right:
   - Click **"Cut Link L1"** — watch primary link turn red and traffic reroute via Backup Link BL1 in 820ms.
   - Click **"Congest L2"** — watch utilization rise to 95% and OpenFlow drop meter activate.
   - Click **"Reset Baseline"** — restore all links to healthy normal state.

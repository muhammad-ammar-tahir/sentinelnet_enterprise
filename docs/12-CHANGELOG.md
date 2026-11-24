# 12 — Changelog

All notable changes to SentinelNet are documented here in reverse-chronological order.

---

## [Unreleased] — Frontend Zero-Mock Policy, Global Offline Watchdog & Real API Endpoints Across 7 Pages

### 1. Zero-Mock Policy & Page Refactoring

- **`DashboardPage.tsx`**:
  - Removed hardcoded values (`"INGRESS: 42.8 Gbps"`, `"PACKET LOSS: 0.0001%"`).
  - Wired live query to `GET /api/metrics/live` using `@tanstack/react-query` with 5s polling.
  - Added explicit `"Telemetry unavailable"` status badge with `WifiOff` icon when telemetry is missing or degraded.
  - Removed fake incidents array fallback; wrapped incidents table with `DataStateWrapper` for honest empty states.
  - Added dynamic `"Data freshness"` indicator counting seconds elapsed since last update.

- **`AIMonitoringPage.tsx`**:
  - Replaced fake `setTimeout`-based retraining with real `useMutation` executing `POST /api/models/retrain`.
  - Added real `GET /api/models/info` query displaying active `model_version`, `trained_at`, features list, training sample counts, and evaluation F1.
  - Added real `GET /api/detect/recent` query displaying recent evaluated telemetry scores and sliding window items.
  - Added `"Model not loaded — check logs"` state via `DataStateWrapper`.

- **`RecoveryManagementPage.tsx`**:
  - Removed simulated OpenFlow success timer.
  - Connected "Approve & Execute" button directly to `POST /api/recovery/execute { incident_id }`.
  - Wired live WebSocket event stream capturing `RECOVERY_STARTED`, `RECOVERY_COMPLETED`, and `RECOVERY_FAILED`.
  - Displayed honest multi-state results: `overall_status`, `flow_installation`, `traffic_verification`, and `rollback_status`.
  - Connected "Rollback" button to `POST /api/recovery/rollback { action_id }`.

- **`LiveTopologyPage.tsx`**:
  - Replaced local simulated failure states with real `POST /api/topology/fail { link_id }`.
  - Implemented 503 handling: displays clear `"Mininet not running — cannot inject real failure"` alert if Mininet is inactive.
  - Polling `GET /api/topology` every 5 seconds, with instant cache invalidation on WebSocket `TOPOLOGY_CHANGED` events.
  - Added real link restoration button calling `POST /api/topology/restore { link_id }`.

- **`DigitalTwinPage.tsx`**:
  - Removed hardcoded scenario outcomes.
  - Connected "Simulate" button to real `POST /api/recovery/simulate { incident_id }`.
  - Clearly tagged all output metrics as `"Simulated in NetworkX topology model, not physically measured"`.
  - Displayed predicted latency, packet loss, flow mod operations, and alternate path hops.

- **`IntegrationsPage.tsx`**:
  - Removed simulated handshake timeouts.
  - Each connector now features a real "Test Connection" button calling `POST /api/integrations/test/{id}`.
  - Performs active socket and HTTP checks against PostgreSQL, Ryu, Mininet, and Prometheus.
  - Returns honest `"CONNECTED"`, `"FAILED"`, or `"NOT_IMPLEMENTED"` statuses with real round-trip latency.

- **`FaultDiagnosisPage.tsx`**:
  - Removed hardcoded `MOCK_DIAGNOSES` array.
  - Connected left incident master list to `GET /api/incidents` and detail view to `GET /api/incidents/{id}/diagnosis`.
  - Connected "Execute Recovery" button to `POST /api/recovery/execute`.
  - Managed zero-incident empty states via `DataStateWrapper`.

### 2. New Infrastructure Components

- **`DataStateWrapper.tsx` (`src/components/ui/DataStateWrapper.tsx`)**:
  - Standardized component providing consistent UX for loading skeletons, error states with retry buttons, honest empty placeholders, and children data rendering.
- **`OfflineBanner.tsx` (`src/components/ui/OfflineBanner.tsx`)**:
  - Global backend watchdog embedded in `AppShell.tsx`.
  - Polls `/api/health` every 8s.
  - If 3 consecutive probes fail, displays persistent global warning banner with manual retry capability.

### 3. Backend Endpoints Added (`backend/api/routes.py`)

- `GET /health` and `GET /api/health`: Service health probes.
- `POST /api/models/retrain`: Executes `train_model.py` pipeline in threadpool, reloads in-memory detector, returns duration and evaluation metrics.
- `GET /api/models/info`: Returns model version, features, training samples, and honest metrics.
- `GET /api/detect/recent`: Returns recent detection scores and evaluated telemetry snapshots.
- `POST /api/recovery/simulate`: Performs NetworkX mathematical graph rerouting simulation.
- `POST /api/integrations/test/{id}`: Real connection audit for PostgreSQL, Ryu, Mininet, Prometheus, and external connectors.

### 4. Test Suite Alignment

- Fixed test assertions in `tests/test_rollback.py`, `tests/test_recovery_failure.py`, `tests/test_exact_flow_verification.py`, and `tests/test_e2e_recovery.py` to match honest `RecoveryResult` schema (`overall_status`, `rollback_status`, `flow_installation`, `traffic_verification`).
- Full test suite: **32 passed, 1 skipped, 0 failed**.
- Frontend type-check (`tsc --noEmit`) and production build (`vite build`): **100% clean**.

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [Unreleased] — Multi-Layer Exact Flow Verification & Active Telemetry

### Rewritten — `backend/recovery/recovery_engine.py` (`verify_recovery`)

**Problem in Old Verification:**
- Checked only whether any flow exists on the switch (`if not switch_flows: flows_ok = False`).
- A switch with 20 unrelated or pre-existing operator flows falsely passed verification even if the recovery flow was missing.
- Did not verify exact matches, priorities, or actions.
- Ping fallback in `NetworkMonitor` returned fabricated fake latency (5.0ms) and fake loss (0.0%).

**New Architecture & Guarantees:**
- **Layer 1 (Controller-Level Exact Flow Matching)**:
  - Queries Ryu `get_flows(dpid)` for each hop in the recovery plan.
  - Matches exact flow fields: `in_port`, `eth_type=0x0800`, `ipv4_src`, `ipv4_dst`.
  - Matches exact egress action: `OUTPUT:port`.
  - Matches exact failover priority: `priority == self.RECOVERY_PRIORITY` (300).
  - Returns `reason="flow_not_found_on_switch"`, `failed_dpid`, `expected`, and `actual_flows_count` if missing.
- **Layer 2 (Data-Plane Active Telemetry Probing)**:
  - Probes restored host connectivity via real ping samples.
  - Strict packet loss ceiling: fails if unreachable (`reason="hosts_unreachable_after_recovery"`) or if `packet_loss_pct > 1.0%` (`reason="packet_loss_too_high"`).
- **Layer 3 (Metric-Level Health Validation)**:
  - Validates overall latency health across affected network elements (fails if `latency_ms > 100.0ms`).
- **Layer 4 (Telemetry Cross-Check)**:
  - Compares predicted path latency from `PathSelector` against measured RTT.
- **ActionExecutor & RecoveryEngine Integration**:
  - `ActionExecutor.execute` populates `ipv4_src` and `ipv4_dst` in installed flow rules from `plan.flow`.
  - If verification fails at any layer, `handle_incident` automatically triggers `rollback_manager.rollback()`.

### Improved — `backend/monitoring/network_monitor.py` (Non-Fabricating TCP Fallback)

- When ICMP is unavailable or blocked by sandbox permissions, switches to active TCP probing.
- Returns `latency_ms: None` and `packet_loss_pct: None` alongside real `connect_time_ms`.
- Never reports fabricated ICMP RTT or fake zero-loss telemetry.

### Added — Test Coverage (`tests/test_exact_flow_verification.py`)

- `test_20_unrelated_flows_plus_exact_recovery_flow_passes`: Switch with 20 unrelated flows + exact recovery flow passes.
- `test_20_unrelated_flows_missing_recovery_flow_fails`: Switch with 20 unrelated flows missing recovery flow fails with `reason="flow_not_found_on_switch"`.
- `test_dataplane_ping_failure_triggers_failure`: Host reachability failure returns `reason="hosts_unreachable_after_recovery"`.
- `test_high_packet_loss_fails_verification`: Packet loss > 1.0% returns `reason="packet_loss_too_high"`.
- `test_network_monitor_tcp_fallback_no_fake_metrics`: Verifies TCP fallback never fabricates ICMP metrics.
- `test_handle_incident_triggers_rollback_on_verification_failure`: Proves full recovery pipeline executes safe rollback when verification fails.

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [Unreleased] — Safe Transactional Diff-Based Rollback & Verified Snapshots

### Rewritten — `backend/recovery/rollback.py` (Safe Diff-Based Rollback)

**Catastrophic Problem in Old Implementation:**
- If snapshot failed on any switch, it recorded an empty list `captured[dpid] = []`.
- During rollback, it issued a wildcard flow deletion (`{"dpid": dpid, "match": {}}`), completely purging all switch flow entries.
- It then had zero flows to restore from the empty snapshot list, leaving switches disconnected and crashing network data plane operations.

**New Architecture & Safety Guarantees:**
- **Verified Snapshotting (`RollbackManager.snapshot`)**:
  - Requires valid flow lists from every affected switch.
  - If **ANY** switch fails or returns an invalid/non-list payload, the snapshot is aborted immediately and returns `None`. No partial or empty snapshots are ever persisted.
- **SentinelNet Recovery Flow Cookie Tagging (`0x53454E54`)**:
  - `ActionExecutor` tags all installed recovery flow entries with `cookie=0x53454E54` (`SENTINELNET_RECOVERY_COOKIE`).
- **Diff-Based Flow Reversion (`RollbackManager.rollback`)**:
  - Queries live switch flows before making any changes.
  - Computes exact flow diff:
    - `to_delete`: Flows present in current table but missing from original baseline.
    - `to_restore`: Flows present in original baseline but missing from current table.
  - **Deletes ONLY SentinelNet recovery flows**: Checks `_is_our_flow(flow)` (cookie matches `0x53454E54` or failover priority 300). Operator-installed flows, default routing, and monitoring rules are **NEVER deleted**.
  - **Restores ONLY missing flows**: Re-adds baseline flows without touching surviving rules.
- **Post-Rollback Active Verification**:
  - Queries switches after rollback execution to verify 100% of baseline flows are restored.
  - If verification fails or switch is unreachable, raises critical alarms (`alert_service.critical`), marks `overall_success = False`, and refuses to report false success.
- **Recovery Engine Integration (`backend/recovery/recovery_engine.py`)**:
  - If `rollback_manager.snapshot(...)` returns `None`, the recovery pipeline aborts immediately with `reason="snapshot_failed"` and escalates the incident to human operators without attempting flow modifications.

### Added — Test Coverage (`tests/test_rollback.py`)

- `test_snapshot_refuses_partial_failure`: Snapshot returns `None` when any switch fails.
- `test_snapshot_rejects_invalid_flow_response`: Rejects non-list switch responses.
- `test_safe_diff_rollback_preserves_operator_flows`: Deletes only recovery flows (`cookie=0x53454E54`); preserves custom operator flows.
- `test_rollback_fails_loudly_when_switch_unreachable`: Marks `overall_success=False` and triggers critical alert when switch is down.
- `test_rollback_invalid_snapshot_raises_exception`: Raises `InvalidSnapshot` on unknown or used snapshots.
- `test_recovery_aborts_when_snapshot_fails`: Proves `RecoveryEngine` never installs flows if snapshot failed.
- `test_recovery_rollback_on_verification_failure`: Verifies end-to-end rollback execution and DB status update.

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [Unreleased] — Topology-Aware Recovery Engine & Detect/Incident Pipeline

### Rewritten — `backend/recovery/recovery_engine.py` (Fully Topology-Aware)

**Problem (old code):**
- `src = "h1"`, `dst = "srv1"` hardcoded — recovery only worked for one flow
- `parts = incident.affected_link_id.split("-")` — BUG: `"edge-core-to-dist-1".split("-")` → `("edge", "core")` not `("s1", "s2")`
- `exclude_links = [("s2", "s3")]` default fallback — masked real failures
- `target_ip = "10.0.0.50"` hardcoded — verification always pinged srv1

**New design (zero hardcoding):**
- `_get_failed_links(incident, links)` — looks up `Link.src_device_id` / `Link.dst_device_id` from DB by `Link.id == incident.affected_link_id`. **Never string-splits link IDs.**
- `_find_affected_flows(incident, devices, links, failed_links)` — builds a pre-failure graph, enumerates all host-to-host pairs, traces paths through graph, identifies which flows traverse the failed element
- `_verify_single_flow(flow, devices, hops)` — resolves destination IP from `Device.ip_address` in DB, pings it, verifies Ryu flows on each hop
- Recovers `h1→srv1`, `h3→server`, or **any host-to-host flow** — fully data-driven
- Snapshots **all DPIDs** across all recovery plans (not just the first path)
- Rolls back **all plans** if any flow installation or verification fails
- Broadcasts `RECOVERY_COMPLETED` via WebSocket (ready for integration)

| Before | After |
|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

-----|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

----|
| `src = "h1"` (hardcoded) | `_find_affected_flows()` → all impacted hosts |
| `link_id.split("-")[0]` | DB lookup `Link.src_device_id` |
| `target_ip = "10.0.0.50"` | `Device.ip_address` from DB |
| One flow repaired | ALL affected flows repaired |

### Added — `backend/services/incident_service.py` Heuristic Fallback

- If `target_id` matches no Device or Link FK in DB, falls back to heuristic: IDs containing `-` are treated as links, otherwise as devices. This prevents silent `affected_link_id = NULL` for new incidents.

### Added — `backend/database/models.py` — `Incident.to_dict()` Enriched

- Added `target_device` and `telemetry_snapshot` keys to `Incident.to_dict()` / `dict()`
- `target_device` resolves from `affected_device_id or affected_link_id or metadata.target_id`
- `telemetry_snapshot` extracts from `metadata_payload.affected_metrics` for client consumption

### Added — `backend/main.py` — Continuous Monitoring Loop + Recovery Queue Lifecycle

- `metrics_collection_loop()` runs every 5 seconds in background:
  - Pings each device using `DeviceMonitor.check_device_health()`
  - Probes each link using `NetworkMonitor.ping_host()`
  - Builds full 7-feature metric vector per device/link
  - Calls `fault_detector.detect()`, creates incidents via `incident_service`, broadcasts WebSocket, enqueues to recovery
  - Deduplicates: skips if active incident already exists for target
- `lifespan(app)`:
  - Starts `recovery_queue.start()` background consumer worker
  - Starts `asyncio.create_task(metrics_collection_loop())`
  - On shutdown: cancels monitoring task, awaits `recovery_queue.stop()`

### Added — `backend/api/routes.py` — `/api/detect` Pipeline Complete

- `DetectRequest` with all 7 required features: `target_id`, `latency_ms`, `packet_loss_pct`, `cpu_pct`, `memory_pct`, `bandwidth_mbps`, `interface_up`, `error_count`
- Missing any field → HTTP 422 (Pydantic validation, no fabricated defaults)
- Pipeline: detect → persist incident → WebSocket `INCIDENT_CREATED` → recovery queue enqueue

### Added — Test Suites

| Test File | Coverage | Status |
|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

-----|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

----|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

-----|
| `tests/test_detect_and_incident_service.py` | 7-feature 422 validation, normal telemetry, anomalous telemetry→incident→WS→queue, IncidentService lifecycle, RecoveryQueue worker | ✅ 5/5 PASSED |
| `tests/test_recovery_engine.py` | DB-field link resolution, complex link IDs, device failure exclusion, h1→srv1, h3→srv1, no-path escalation | ✅ 8/8 PASSED |

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [Unreleased] — Code-Quality Pass (Second Review)

### Fixed — Real Mininet Failure Injection & Verification (`/api/topology/fail`)

- **Rewrote `/api/topology/fail`**: Replaced mock database-only status mutation with `FailureInjectionService` (`backend/simulation/failure_service.py`).
- **Physical Execution & Process Isolation**: Evaluates Mininet simulation via subprocess/kernel commands (`ip link set ... down`, `ovs-ofctl`, `mnexec`).
- **Active Post-Cut Verification**: Probes actual interface operstate (`ip link show`, `ovs-ofctl show`). Database state is modified to `down` **ONLY** after physical confirmation.
- **Fail-Safe Offline Guard**: If Mininet is not running, immediately raises `503 Service Unavailable` (`MininetUnavailable`). If the cut fails verification, raises `500 Internal Server Error` (`InjectionVerificationFailed`). Never falls back to blind DB mutation.
- **Added Restoration Endpoint**: `POST /api/topology/restore` to bring back interfaces via `ip link set up` and actively verify recovery before updating DB.
- **Added Simulation Status Endpoint**: `GET /api/simulation/status` to inspect whether Mininet is actively running, active switches, hosts, and failure tracking.
- **Added Full Test Suite**: `tests/test_failure_service.py` covering offline 503 behavior, verification aborts, permission checking, and successful verified state changes.

### Fixed — Frontend (ESLint: 0 errors, 0 warnings)

| File | Issue | Fix |
|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

----|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

-----|
| `AIMonitoringPage.tsx` | Unused state pair `[_flowCount, _setFlowCount]` (error: `no-unused-vars`) | Removed the dead state; `flowCount` was never read or mutated |
| `DashboardPage.tsx` | `(inc: any)` in table map (error: `no-explicit-any`) | Added `IncidentRow` interface at top of file; replaced `any` |
| `IntegrationsPage.tsx` | Unused setter `_setConnectors` (error: `no-unused-vars`) | Replaced `useState` pair with `const connectors = INITIAL_CONNECTORS`; removed unused `useState` import |
| `PoliciesPage.tsx` | `e.target.value as any` in select handler (error: `no-explicit-any`) | Cast to `'AUTOMATED' \| 'MANUAL_APPROVAL'` — the actual union type |
| `PredictiveMaintenancePage.tsx` | Unused setter `_setItems` (error: `no-unused-vars`) | Replaced `useState` pair with `const items = PREDICTIVE_ITEMS`; removed unused `useState` import |
| `AuthContext.tsx` (line 86) | `react-refresh/only-export-components` warning on `useAuth` | Added `// eslint-disable-next-line` — intentional co-location of hook with provider |
| `WebSocketContext.tsx` (line 113) | Same warning on `useWebSocket` | Same suppression with same justification |

### Fixed — Backend

#### `tests/test_e2e_recovery.py`
- **Removed fake-success fallback** in `poll_until_recovery_complete()`. The old code returned a manufactured `{"success": True, "path_installed": True, ...}` dict when the incident polled as `recovered` / `resolved`, bypassing actual API verification.
- **Replacement:** The function now calls `GET /api/recovery/actions/{recovery_action_id}` and returns the real server response. If the action ID is missing, an `AssertionError` is raised immediately.
- **Effect:** If the real recovery pipeline fails, the test fails with a clear assertion error. No manufactured success.

#### `backend/config.py`
- **Removed hardcoded JWT secret default** `"sentinelnet-super-secure-production-jwt-secret-key-2026"`.
- **New policy** implemented in `_validate_jwt_secret()`:
  - **Production (`ENVIRONMENT=production`):** raises `RuntimeError` at startup if `JWT_SECRET` is missing, < 32 chars, or matches any entry in `_KNOWN_DEFAULT_SECRETS`.
  - **Development (any other `ENVIRONMENT`):** logs a loud `WARNING` and applies an insecure placeholder; startup continues.
- **Known-default set** (`_KNOWN_DEFAULT_SECRETS`) covers 8 common placeholder values.

#### `backend/database/seed.py`
- **Removed SHA-256 fallback** in `hash_password()`. The old `except Exception` silently created a weak `sha256(salt+password)` hash if `passlib` failed.
- **Replacement:** raises `RuntimeError` with an actionable message pointing to `pip install passlib[bcrypt] bcrypt`.
- **Removed** now-unused `import hashlib`.

### Changed — Environment Variable Standardisation

| Variable | Old name | New name | Where |
|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

----|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

----|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

----|### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

----|
| Ryu controller URL | `RYU_URL` | `RYU_BASE_URL` | `docker-compose.yml`, `.env.example`, `config.py` |
| Vite API base | `VITE_API_URL` | `VITE_API_BASE_URL` | `docker-compose.yml`, `.env.example` |
| JWT secret | `SECRET_KEY` | `JWT_SECRET` | `.env.example`, `config.py` |
| App environment | `APP_ENV` | `ENVIRONMENT` | `.env.example`, `config.py` |
| JWT algorithm | `ALGORITHM` | `JWT_ALGORITHM` | `.env.example`, `config.py` |
| Database URL | `postgresql://` | `postgresql+asyncpg://` | `.env.example` comment, `docker-compose.yml` |

### Added — `.gitignore`
- Added `*.sqlite` and `*.sqlite3` patterns (were missing; `*.db` was already present).

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [Unreleased] — Cleanup & Documentation Pass (Prompts 10–15)

### Added
- `.gitignore` — Python, Node, model files, secrets, IDE, OS artefacts; whitelists `ai_models/*.pkl`
- `.dockerignore` — Excludes `node_modules`, `__pycache__`, `.env`, docs, tests from Docker build context
- `requirements.txt` — Fully pinned (`==`) to exact installed versions from `pip freeze`
- `requirements-dev.txt` — New; dev-only packages (`pytest`, `pytest-asyncio`, `rich`, `httpx`, `black`, `ruff`)
- `docker-compose.yml` — Services: `postgres:15-alpine`, `prom/prometheus`, `grafana/grafana`, `backend`, `frontend`
- `docs/11-KNOWN-ISSUES.md` — 10 honest documented limitations (MFA cosmetic, synthetic data, Ryu Linux-only, missing Dockerfiles, no component tests, timeout-dominated recovery time, h4 orphan node, non-idempotent audit seed, WS token non-renewal, missing prometheus.yml)
- `docs/12-CHANGELOG.md` — This file

### Changed
- `docs/10-TESTING-EVALUATION.md` — Replaced optimistic "Expected Results" table with **Verification Status** section showing what is actually tested vs. planned; added measured timings (detection ~680ms from seed metadata, recovery pipeline ~54s timeout-dominated); all accuracy figures qualified as "on synthetic data only"
- `README.md` — Added **Project Status** section (academic prototype framing); **What Works** and **What's Not Done Yet** checklists; **Prerequisites** list; fixed duplicate "Step 4" numbering; updated folder structure to include new docs 11–12; updated doc table with new files

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.9.0] — Integration Tests & Demo Script (Prompt 15)

### Added
- `tests/test_e2e_recovery.py` — End-to-end pytest-asyncio test; gracefully skips if Mininet/Ryu are not running (detected by `/api/metrics/live` returning `data_unavailable: true`)
- `tests/test_recovery_failure.py` — Tests no-alternate-path branch: asserts `success=False`, `reason=no_alternate_path`, incident status `escalated` ✅ PASSED
- `tests/test_rollback.py` — Tests failing verification branch: asserts `rolled_back=True`, incident status `rolled_back` ✅ PASSED
- `tests/test_auth_and_ws.py` — 6 auth/RBAC/WebSocket checks ✅ PASSED
- `scripts/demo.py` — Rich terminal CLI, 7 demo stages, `--auto` flag; exits 0 on success

### Fixed
- `backend/recovery/path_selection.py` — Added reverse edge so topology graph is bidirectional; fixed `h1→s1` path not found
- `backend/recovery/recovery_engine.py` — `no_alternate_path` branch now correctly sets `incident.status = "escalated"`; `verification_failed` branch now correctly sets `incident.status = "rolled_back"`
- `backend/api/routes.py` — `/api/topology/fail` now creates an `Incident` DB record and broadcasts both `TOPOLOGY_CHANGED` and `INCIDENT_CREATED` WebSocket events

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.8.0] — JWT Auth, RBAC & WebSocket (Prompts 9–10)

### Added
- `backend/api/auth.py` — Full JWT implementation: `POST /api/auth/login` (bcrypt verify, issues access + refresh tokens), `POST /api/auth/refresh`, `GET /api/auth/me`, `get_current_user()` dependency, `require_role(role)` dependency
- `backend/ws/manager.py` — `ConnectionManager`: `connect()` (validates JWT from query param or first-frame AUTH message, 5-second timeout), `disconnect()`, `broadcast()`, `send_to()`. All 7 event types defined
- `backend/api/routes.py` — Route protection applied: `POST /api/recovery/execute`, `/rollback`, `/api/topology/fail` → operator; `PUT /api/recovery/mode`, policies CRUD → admin
- Added endpoints: `/api/incidents/{id}`, `/api/incidents/{id}/diagnosis`, `/api/monitor/ping`, `/api/controller/flows/{dpid}`

### Changed
- `backend/main.py` — Replaced `allow_origins=["*"]` with `os.getenv("ALLOWED_ORIGINS")` split-list; registers `auth_router` and `api_router`; WebSocket endpoints `/ws/live` and `/ws`
- `backend/database/seed.py` — 3 users seeded (`admin`, `operator`, `viewer`, all password `sentinelpass`, bcrypt); `hash_password()` uses passlib bcrypt with sha256 fallback
- `backend/config.py` — Added `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES=15`, `REFRESH_TOKEN_EXPIRE_DAYS=7`, `ALLOWED_ORIGINS`
- `docs/07-API-DESIGN.md` — Full auth schema, RBAC table, all 8 WS event types
- `README.md` — Added seeded user accounts table with RBAC roles

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.7.0] — Database Initialization & Alembic Migrations (Prompts 7–8)

### Added
- `backend/database/database.py` — Uncommented and rewrote `init_db()`: creates all tables, verifies 8 required table names, raises `DatabaseInitError` on missing tables
- `alembic/` — Alembic migration environment; `env.py` wired to SQLAlchemy async engine; `versions/` with initial migration
- `backend/database/seed.py` — Idempotent seed for topology (devices, links), 3 RBAC users, sample metrics, historical incidents, recovery actions, and policies

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.6.0] — AI/ML Data Leak Fix & Honest Evaluation (Prompt 6)

### Fixed
- `ai_models/preprocessing.py` — Corrected train/test data leakage: `StandardScaler` is now fit **only on training split** and stored as `self.scaler`; test set is transformed with the training scaler. Added unit test asserting test mean ≠ 0 (proving scaler was not fit on test set)

### Changed
- `ai_models/train_model.py` — Replaced single accuracy number with per-class precision/recall/F1, confusion matrix, ROC-AUC, PR-AUC, false positive rate, and detection time. All metrics written to `evaluation.json`

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.5.0] — Recovery Engine & Path Selection (Prompt 5)

### Rewritten
- `backend/recovery/path_selection.py` — `PathSelector.find_optimal_path()`: Dijkstra weighted by `latency + (loss × 100) + load_penalty`; excludes failed links; enforces `min_bandwidth` / `max_latency` constraints; returns full `PathResult` with per-hop DPIDs and port numbers
- `backend/recovery/recovery_engine.py` — `RecoveryEngine.execute_recovery()`: selects path, pushes OpenFlow rules via `sdn_controller`, verifies via `network_monitor.ping_host()`, rolls back on failure; persists `RecoveryAction` to DB

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.4.0] — Real Network Monitoring (Prompt 4)

### Rewritten
- `backend/monitoring/network_monitor.py` — `NetworkMonitor.ping_host()`: real ICMP via `asyncio.create_subprocess_exec("ping", ...)` with output parsing; TCP-socket fallback if ping command not found; never returns hardcoded success
- `backend/monitoring/network_monitor.py` — `measure_latency()`, `run_continuous_monitoring()`, `get_monitoring_summary()` implemented

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.3.0] — Real SDN Controller Client (Prompt 3)

### Rewritten
- `backend/controller/sdn_controller.py` — Replaced stub `return True` methods with real `httpx.AsyncClient` calls to Ryu REST API (`http://127.0.0.1:8080`); `is_controller_alive()`, `get_switches()`, `get_flows()`, `add_flow_entry()`, `delete_flow_entry()`, `install_path()`, `rollback_path()` all implemented; `ControllerUnavailable` exception raised on error

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.2.0] — Real API Endpoints (Prompts 1–2)

### Rewritten
- `backend/api/routes.py`:
  - `GET /api/metrics/live` — Queries `Metric` records from DB, computes aggregations (avg latency, avg packet loss, device counts), computes `network_health_score` with weighted penalties; returns `data_unavailable: true` if DB is empty
  - `GET /api/incidents` — Queries `Incident` table with filters (`status`, `severity`, `device_id`, pagination); returns real rows or `[]`
  - `GET /api/topology` — Queries `Device` and `Link` tables; returns actual graph nodes and edges
  - `POST /api/recovery/execute` — Triggers `RecoveryEngine.execute_recovery()` on a real incident
  - `GET /api/devices` — Real device list from DB
  - `GET /api/health` — Backend + DB + controller reachability check

### 5. Docker Infrastructure & Compose Orchestration

- Created `Dockerfile.backend`: Multi-stage, slim Python 3.11 container with networking utilities (`iputils-ping`, `net-tools`, `procps`), PostgreSQL development libraries, and non-root execution support.
- Created `frontend/Dockerfile.frontend`: Node 20-Alpine container serving Vite NOC frontend.
- Created root `prometheus.yml`: Configured to scrape Prometheus, FastAPI backend (`backend:8000`), and host-gateway Ryu controller (`host.docker.internal:8080`).
- Created default `.env` synchronized with production defaults.
- Updated `docker-compose.yml`:
  - Added `redis:7-alpine` container for queue & event bus.
  - Added `extra_hosts: ["host.docker.internal:host-gateway"]` for seamless host Mininet / Ryu integration.
  - Set `DATABASE_URL_SYNC: postgresql://postgres:postgres@postgres:5432/sentinelnet` for Alembic migrations.
  - Set `PROMETHEUS_URL: http://prometheus:9090` and `REDIS_URL: redis://redis:6379/0`.
- Updated `docs/09-DEPLOYMENT.md` to reflect full compose architecture.

---

## [0.1.0] — Initial Scaffold

- Project structure established: `frontend/`, `backend/`, `ai_models/`, `sdn_controller/`, `network_simulation/`, `docs/`
- React NOC dashboard scaffolded (12 pages, Tailwind cyber-observability design system)
- FastAPI backend with placeholder endpoints returning hardcoded data
- SQLAlchemy ORM models for 8 tables
- AI model stubs (`IsolationForest`, `RandomForest` wrappers)
- Initial documentation suite (`docs/01` through `docs/10`)

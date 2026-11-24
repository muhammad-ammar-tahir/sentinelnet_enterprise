# 07 — API Design

## Table of Contents
1. [API Overview](#1-api-overview)
2. [Authentication](#2-authentication)
3. [Metrics Endpoints](#3-metrics-endpoints)
4. [Detection Endpoints](#4-detection-endpoints)
5. [Incidents Endpoints](#5-incidents-endpoints)
6. [Recovery Endpoints](#6-recovery-endpoints)
7. [Topology Endpoints](#7-topology-endpoints)
8. [Policy Endpoints](#8-policy-endpoints)
9. [AI / Model Endpoints](#9-ai--model-endpoints)
10. [WebSocket Events](#10-websocket-events)
11. [Error Responses](#11-error-responses)

---

## 1. API Overview

| Property | Value |
|---|---|
| Base URL | `http://localhost:8000/api` |
| Protocol | HTTP/1.1, WebSocket |
| Format | JSON (`Content-Type: application/json`) |
| Auth | Bearer JWT (`Authorization: Bearer <token>`) |
| Docs | `http://localhost:8000/docs` (Swagger UI) |
| OpenAPI | `http://localhost:8000/openapi.json` |
| Versioning | URL prefix (`/api/v1/`) — v1 only in this release |

**Global Headers**

| Header | Required | Description |
|---|---|---|
| `Authorization` | Yes (most endpoints) | `Bearer <jwt_token>` |
| `Content-Type` | Yes (POST/PUT) | `application/json` |
| `X-Request-ID` | Optional | Idempotency key; returned in response |

---

## 2. Authentication & Authorization (RBAC)

SentinelNet enforces role-based access control with standard JSON Web Tokens (JWT) signed via HMAC-SHA256 and encrypted passwords using `passlib` (bcrypt).

**Role Hierarchy:**
- `admin`: Full administrative access, policy mutation, mode management, and recovery actuation.
- `operator`: Network telemetry, incident review, failure injection, recovery execution, and rollback.
- `viewer`: Read-only access to metrics, topology, and incidents.

### POST /api/auth/login

Obtain JWT access and refresh tokens. Rate limited to 5 attempts per minute per IP using `slowapi`.

**Request:**
```json
{
  "email": "admin@sentinelnet.edu",
  "password": "sentinelpass"
}
```
*(Also accepts `"username": "admin"`)*

**Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "usr-admin-01",
    "username": "admin",
    "email": "admin@sentinelnet.edu",
    "role": "admin",
    "is_active": true
  },
  "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "tokenType": "bearer",
  "expiresIn": 900
}
```

### POST /api/auth/refresh

Exchange an unexpired 7-day refresh token for a new 15-minute access token.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1Ni..."
}
```

**Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1Ni...",
  "token_type": "bearer",
  "expires_in": 900,
  "accessToken": "eyJhbGciOiJIUzI1Ni...",
  "tokenType": "bearer",
  "expiresIn": 900
}
```

### GET /api/auth/me

Retrieve profile and role information of the currently authenticated operator.

**Headers:**
`Authorization: Bearer <access_token>`

**Response `200 OK`:**
```json
{
  "id": "usr-admin-01",
  "username": "admin",
  "email": "admin@sentinelnet.edu",
  "role": "admin",
  "is_active": true
}
```

---

## 3. Metrics Endpoints

### GET /api/metrics/live (or GET /api/metrics)

Returns real-time aggregated network health and performance metrics computed directly from PostgreSQL `metrics` and `devices` tables via `backend/api/deps.py:get_current_metrics()`.

> **Guaranteed Honesty:** If the database has no metric records or registered devices, this endpoint returns zeros with `"data_unavailable": true`. It **never** returns fake healthy telemetry.

**Response `200 OK` (when telemetry exists in DB):**
```json
{
  "timestamp": "2026-11-23T00:25:00.000000",
  "data_unavailable": false,
  "network_health_score": 96.5,
  "total_devices": 8,
  "devices_up": 8,
  "devices_down": 0,
  "devices_degraded": 0,
  "active_incidents": 0,
  "average_latency_ms": 7.2,
  "packet_loss_rate": 0.0001
}
```

**Response `200 OK` (when database is empty / cold start):**
```json
{
  "timestamp": "2026-11-23T00:25:00.000000",
  "data_unavailable": true,
  "network_health_score": 0.0,
  "total_devices": 0,
  "devices_up": 0,
  "devices_down": 0,
  "devices_degraded": 0,
  "active_incidents": 0,
  "average_latency_ms": 0.0,
  "packet_loss_rate": 0.0,
  "message": "Telemetry database is empty. No live monitoring data available."
}
```

### GET /api/metrics/snapshots

Returns the latest metric snapshot for all monitored devices.

**Query Parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `device_id` | string | all | Filter by device |
| `link_id` | string | all | Filter by link |
| `limit` | int | 100 | Max snapshots to return |
| `since` | ISO8601 | 10 min ago | Start timestamp |

**Response `200 OK`:**
```json
{
  "count": 3,
  "snapshots": [
    {
      "id": "snap_20240101T100010Z_s1p3",
      "timestamp": "2024-01-01T10:00:10Z",
      "device_id": "s1",
      "port": 3,
      "link_id": "L1",
      "metrics": {
        "rx_bytes_rate": 1312000,
        "tx_bytes_rate": 901000,
        "rx_error_rate": 0,
        "tx_drop_rate": 0,
        "flow_table_size": 45,
        "link_utilization": 13.1,
        "rtt_ms": 7.1,
        "host_cpu_pct": 8.3
      },
      "anomaly_score": -0.02,
      "is_anomalous": false
    }
  ]
}
```

### GET /api/metrics/summary

Returns aggregated min/max/avg for each metric over the last N minutes.

**Query Parameters:** `window_minutes` (default: 30), `device_id`

**Response `200 OK`:**
```json
{
  "window_minutes": 30,
  "device_id": "s1",
  "summary": {
    "rtt_ms": { "min": 6.8, "max": 9.2, "avg": 7.3 },
    "link_utilization": { "min": 8.1, "max": 18.4, "avg": 12.6 },
    "rx_error_rate": { "min": 0, "max": 0, "avg": 0.0 }
  }
}
```

---

## 4. Detection Endpoints

### POST /api/detect

Manually submit a metric vector for anomaly detection (for testing/debugging).

**Request:**
```json
{
  "device_id": "s1",
  "port": 3,
  "metrics": {
    "rx_bytes_rate": 0,
    "tx_bytes_rate": 0,
    "rx_error_rate": 55,
    "tx_drop_rate": 50,
    "flow_table_size": 45,
    "link_utilization": 0.0,
    "rtt_ms": 999.0,
    "host_cpu_pct": 8.1
  }
}
```

**Response `200 OK`:**
```json
{
  "anomaly_score": 0.74,
  "is_anomalous": true,
  "threshold": 0.65,
  "top_contributing_features": [
    { "feature": "rx_error_rate", "contribution": 0.38 },
    { "feature": "rtt_ms", "contribution": 0.22 },
    { "feature": "rx_bytes_rate", "contribution": 0.19 }
  ],
  "triggered_incident_id": "inc_20240101_0042"
}
```

### GET /api/detect/status

Returns current state of the detection engine.

**Response `200 OK`:**
```json
{
  "status": "RUNNING",
  "model_version": "v1.2.0",
  "model_loaded_at": "2024-01-01T09:00:00Z",
  "samples_processed_today": 8640,
  "anomalies_flagged_today": 7,
  "last_check_at": "2024-01-01T10:00:10Z"
}
```

---

## 5. Incidents Endpoints

### GET /api/incidents

List all incidents, with optional filters.

**Query Parameters:**

| Param | Type | Description |
|---|---|---|
| `status` | string | `DETECTED`, `DIAGNOSING`, `RECOVERING`, `RESOLVED`, `ESCALATED`, `MANUAL_REVIEW` |
| `failure_type` | string | `LINK_FAILURE`, `CONGESTION`, `HIGH_LATENCY`, `DEVICE_FAILURE`, `REPEATED_FAILURE` |
| `since` | ISO8601 | Start timestamp |
| `limit` | int | Default 50 |
| `offset` | int | Pagination |

**Response `200 OK`:**
```json
{
  "total": 142,
  "limit": 50,
  "offset": 0,
  "incidents": [
    {
      "id": "inc_20240101_0042",
      "created_at": "2024-01-01T10:00:25Z",
      "updated_at": "2024-01-01T10:00:58Z",
      "status": "RESOLVED",
      "failure_type": "LINK_FAILURE",
      "confidence": 0.94,
      "affected_device_ids": ["s1"],
      "affected_link_ids": ["L1"],
      "anomaly_score": 0.74,
      "detection_time_ms": 25400,
      "recovery_time_ms": 33000,
      "recovery_action_id": "ra_20240101_0042",
      "resolved_at": "2024-01-01T10:00:58Z"
    }
  ]
}
```

### GET /api/incidents/{incident_id}

Returns full detail for a single incident including all pipeline stages.

**Response `200 OK`:**
```json
{
  "id": "inc_20240101_0042",
  "status": "RESOLVED",
  "failure_type": "LINK_FAILURE",
  "confidence": 0.94,
  "affected_device_ids": ["s1"],
  "affected_link_ids": ["L1"],
  "anomaly_signal": {
    "score": 0.74,
    "flagged_metrics": ["rx_bytes_rate", "rx_error_rate", "rtt_ms"],
    "detected_at": "2024-01-01T10:00:25Z"
  },
  "diagnosis": {
    "failure_type": "LINK_FAILURE",
    "confidence": 0.94,
    "class_probabilities": {
      "LINK_FAILURE": 0.94,
      "CONGESTION": 0.03,
      "HIGH_LATENCY": 0.02,
      "DEVICE_FAILURE": 0.01,
      "REPEATED_FAILURE": 0.00
    },
    "diagnosed_at": "2024-01-01T10:00:26Z"
  },
  "recovery_action": {
    "id": "ra_20240101_0042",
    "action": "REROUTE_TO_BACKUP",
    "parameters": { "backup_link": "BL1", "affected_switch": "s1" },
    "status": "SUCCESS",
    "executed_at": "2024-01-01T10:00:27Z",
    "completed_at": "2024-01-01T10:00:28Z",
    "duration_ms": 1200
  },
  "verification": {
    "post_metrics": { "rtt_ms": 9.1, "rx_error_rate": 0 },
    "passed": true,
    "verified_at": "2024-01-01T10:00:58Z"
  }
}
```

### PATCH /api/incidents/{incident_id}

Update incident status (e.g., manually resolve or escalate).

**Request:**
```json
{
  "status": "MANUAL_REVIEW",
  "notes": "Investigated — physical cable damaged on L1. Replacement scheduled."
}
```

---

## 6. Recovery Endpoints

### POST /api/recover

Trigger self-healing recovery execution for an existing database incident via `RecoveryEngine`.

> **Note on Implementation Status:** This endpoint requires a valid `incident_id` in the database. If `RecoveryEngine` is uninitialized or not ready, it responds with `501 Not Implemented`. It will **never** fake a successful recovery.

**Request:**
```json
{
  "incident_id": "inc_20240101_0042",
  "action_type": "auto_reroute",
  "override_policy": false
}
```

**Response `200 OK` (when recovery executed and verified):**
```json
{
  "incident_id": "inc_20240101_0042",
  "status": "resolved",
  "action": "rerouted_via_backup",
  "verified": true,
  "new_path": ["h1", "s1", "s3", "srv1"],
  "duration_seconds": 1.15
}
```

**Response `404 Not Found` (when incident_id is not in DB):**
```json
{
  "detail": "Incident with ID 'inc_nonexistent' not found in database."
}
```

**Response `501 Not Implemented` (when RecoveryEngine is unavailable):**
```json
{
  "detail": "RecoveryEngine is not ready or not implemented on this server."
}
```

### GET /api/recovery/{action_id}

Check the status of a recovery action.

**Response `200 OK`:**
```json
{
  "id": "ra_20240101_0043",
  "status": "SUCCESS",
  "action": "REROUTE_TO_BACKUP",
  "executed_at": "2024-01-01T10:05:01Z",
  "completed_at": "2024-01-01T10:05:02Z",
  "duration_ms": 1150,
  "ryu_response": {
    "switch": "s1",
    "flow_mod_applied": true
  }
}
```

### GET /api/recovery/history

Returns all past recovery actions.

**Query Parameters:** `incident_id`, `action`, `status`, `since`, `limit`

---

## 7. Topology Endpoints

### GET /api/topology

Returns the full current network topology state queried directly from PostgreSQL `devices` and `links` tables.

> **Cold-Start Behavior:** If no topology records exist in the database, returns `"data_unavailable": true` with empty `devices: []` and `links: []`.

**Response `200 OK`:**
```json
{
  "data_unavailable": false,
  "devices": [
    { "id": "s1", "name": "Switch Core 1", "type": "switch", "status": "active", "dpid": "0000000000000001", "ip": null, "mac": null, "location": null },
    { "id": "s2", "name": "Switch Dist 2", "type": "switch", "status": "active", "dpid": "0000000000000002", "ip": null, "mac": null, "location": null },
    { "id": "s3", "name": "Switch Backup 3", "type": "switch", "status": "active", "dpid": "0000000000000003", "ip": null, "mac": null, "location": null },
    { "id": "h1", "name": "Host 1 (Admin)", "type": "host", "status": "active", "dpid": null, "ip": "10.0.0.1", "mac": null, "location": null },
    { "id": "srv1", "name": "Main Server", "type": "server", "status": "active", "dpid": null, "ip": "10.0.0.100", "mac": null, "location": null }
  ],
  "links": [
    { "id": "l1", "src": "s1", "dst": "s2", "src_port": 1, "dst_port": 2, "type": "primary", "status": "up", "bandwidth_mbps": 100.0, "current_utilization": 14.5, "latency_ms": 1.2, "packet_loss_rate": 0.0 },
    { "id": "l2", "src": "s1", "dst": "s3", "src_port": 3, "dst_port": 1, "type": "backup", "status": "up", "bandwidth_mbps": 100.0, "current_utilization": 0.0, "latency_ms": 2.1, "packet_loss_rate": 0.0 }
  ]
}
```

### GET /api/topology/paths

Returns all current active flow paths.

---

### POST /api/topology/fail

Inject a real link failure into the active Mininet network simulation.

> **CRITICAL VERIFICATION POLICY:** Unlike earlier mock implementations, this endpoint **never** updates the database blindly. It verifies that Mininet is running and confirms that the OpenFlow interface / physical link is genuinely down (via `ip link` / `ovs-ofctl`). Only after physical confirmation is the link state marked `down` in the database and an incident created. If Mininet is unreachable, it raises `503 Service Unavailable`. If the cut cannot be verified, it raises `500 Internal Server Error`.

**Role:** `operator` or `admin`

**Request:**
```json
{
  "link_id": "link-s2-s3"
}
```
*Note: Shorthand `{"link": ["s2", "s3"]}` or `{"switch": "s2", "interface": "s2-eth2"}` are also accepted.*

**Response `200 OK` (Physical failure confirmed):**
```json
{
  "status": "injected",
  "success": true,
  "link_id": "link-s2-s3",
  "incident_id": "inc_1700000000000",
  "verified_down": true,
  "target": "link:link-s2-s3",
  "details": "Link link-s2-s3 (s2 <-> s3) confirmed down in Mininet.",
  "timestamp": "2026-11-23T17:45:00.000000Z"
}
```

**Response `503 Service Unavailable` (Mininet offline):**
```json
{
  "detail": "Cannot inject real failure: Mininet is not running — cannot inject real failure."
}
```

**Response `500 Internal Server Error` (Verification failed):**
```json
{
  "detail": "Failure injection could not be verified: FailureInjector executed, but link state verification failed (link still up)."
}
```

---

### POST /api/topology/restore

Restores an injected link failure in Mininet, returning the interface to the `UP` state and verifying reachability before setting database link status back to `up`.

**Role:** `operator` or `admin`

**Request:**
```json
{
  "link_id": "link-s2-s3"
}
```

**Response `200 OK`:**
```json
{
  "status": "restored",
  "success": true,
  "link_id": "link-s2-s3",
  "verified_up": true,
  "target": "link:link-s2-s3",
  "details": "Link link-s2-s3 restored and verified up.",
  "timestamp": "2026-11-23T17:45:10.000000Z"
}
```

---

### GET /api/simulation/status

Returns real-time health and execution status of the Mininet simulation environment, active switches, and active injections.

**Response `200 OK`:**
```json
{
  "mininet_running": true,
  "topology": "UniversityTopology (3 switches, 5 hosts, 1 controller)",
  "active_switches": ["s1", "s2", "s3"],
  "active_hosts": ["h1", "h2", "h3", "h4", "srv1"],
  "active_failures": [
    {
      "type": "LINK_DOWN",
      "sw1": "s2",
      "sw2": "s3",
      "timestamp": "2026-11-23T17:45:00.000000",
      "description": "Physical link between s2 and s3 brought down"
    }
  ],
  "detection_mode": "Active Real Simulation",
  "details": "Mininet and OVS switches active"
}
```

---

## 8. Policy Endpoints

### GET /api/policies

List all recovery policies.

**Response `200 OK`:**
```json
{
  "policies": [
    {
      "id": "pol_001",
      "name": "Link Failure Auto-Reroute",
      "failure_type": "LINK_FAILURE",
      "severity": "ANY",
      "zone": "ANY",
      "action": "REROUTE_TO_BACKUP",
      "automation": "AUTOMATED",
      "enabled": true,
      "created_by": "admin",
      "created_at": "2024-01-01T09:00:00Z"
    }
  ]
}
```

### POST /api/policies

Create a new recovery policy.

**Request:**
```json
{
  "name": "Exam Period No Rate Limiting",
  "failure_type": "CONGESTION",
  "severity": "LOW",
  "zone": "lab_a",
  "action": "REROUTE",
  "automation": "AUTOMATED",
  "enabled": true,
  "schedule": {
    "active_from": "08:00",
    "active_until": "18:00",
    "days": ["MON", "TUE", "WED", "THU", "FRI"]
  }
}
```

---

## 9. AI / Model Endpoints

### GET /api/models/status

Returns loaded model info and performance stats.

**Response `200 OK`:**
```json
{
  "anomaly_detector": {
    "version": "1.2.0",
    "algorithm": "IsolationForest",
    "trained_at": "2024-01-01T00:00:00Z",
    "training_samples": 8640,
    "contamination": 0.05,
    "threshold": 0.65
  },
  "failure_diagnoser": {
    "version": "1.1.0",
    "algorithm": "RandomForestClassifier",
    "trained_at": "2024-01-01T00:00:00Z",
    "training_samples": 1000,
    "cv_f1_score": 0.871,
    "classes": ["LINK_FAILURE", "CONGESTION", "HIGH_LATENCY", "DEVICE_FAILURE", "REPEATED_FAILURE"]
  }
}
```

### POST /api/models/retrain

Trigger manual retraining.

**Request:**
```json
{ "models": ["anomaly_detector", "failure_diagnoser"], "dry_run": false }
```

**Response `202 Accepted`:**
```json
{ "job_id": "retrain_20240101_001", "status": "QUEUED", "estimated_duration_sec": 120 }
```

---

## 10. WebSocket Events & Real-Time Remediation

The SentinelNet backend exposes authenticated WebSocket endpoints at `/ws/live` and `/ws`.

### Connection & Authentication

Clients can authenticate either via query parameter or via an initial `AUTH` frame:

**Option 1: Query Parameter**
```javascript
const token = localStorage.getItem('access_token');
const ws = new WebSocket(`ws://localhost:8000/ws/live?token=${token}`);
```

**Option 2: Initial AUTH Frame**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/live');
ws.onopen = () => {
  ws.send(JSON.stringify({ type: 'AUTH', token: `Bearer ${accessToken}` }));
};
```

> **Security Note:** Connections with missing, malformed, or expired tokens are rejected with WebSocket closure code `1008` (Policy Violation).

### Event Types (Server → Client)

#### `CONNECTED` (Handshake confirmation)
```json
{
  "event": "CONNECTED",
  "data": {
    "message": "Connected to SentinelNet Real-Time Stream as admin",
    "user": { "id": "usr-admin-01", "username": "admin", "role": "admin" },
    "server_time": "2026-11-23T17:50:00.000000+00:00"
  },
  "timestamp": "2026-11-23T17:50:00.000000+00:00"
}
```

#### `METRICS_UPDATED` (Telemetry Scrape Cycle)
```json
{
  "event": "METRICS_UPDATED",
  "data": {
    "network_health_score": 98.4,
    "average_latency_ms": 3.4,
    "active_incidents": 1,
    "total_devices": 9
  },
  "timestamp": "2026-11-23T17:50:05.000000+00:00"
}
```

#### `ANOMALY_DETECTED` (Fault Detector / ML Model Trigger)
```json
{
  "event": "ANOMALY_DETECTED",
  "data": {
    "incident_id": "inc-001",
    "target_id": "s2-s3",
    "anomaly_score": 0.82,
    "reason": "Latency exceeded threshold (>50ms)"
  },
  "timestamp": "2026-11-23T17:50:10.000000+00:00"
}
```

#### `INCIDENT_CREATED` (Incident Generation)
```json
{
  "event": "INCIDENT_CREATED",
  "data": {
    "incident_id": "inc-004",
    "severity": "critical",
    "title": "Core Link Failure Detected"
  },
  "timestamp": "2026-11-23T17:50:12.000000+00:00"
}
```

#### `TOPOLOGY_CHANGED` (Link cut / device state mutation)
```json
{
  "event": "TOPOLOGY_CHANGED",
  "data": {
    "target_type": "link",
    "target_id": "s2-s3",
    "failure_type": "link_down",
    "injected_by": "operator"
  },
  "timestamp": "2026-11-23T17:50:15.000000+00:00"
}
```

#### `RECOVERY_STARTED` (Recovery Engine actuation initiated)
```json
{
  "event": "RECOVERY_STARTED",
  "data": {
    "incident_id": "inc-001",
    "operator": "operator",
    "action_type": "auto_reroute"
  },
  "timestamp": "2026-11-23T17:50:18.000000+00:00"
}
```

#### `RECOVERY_COMPLETED` (Self-healing verified successfully)
```json
{
  "event": "RECOVERY_COMPLETED",
  "data": {
    "incident_id": "inc-001",
    "status": "resolved",
    "result": { "status": "resolved", "action": "reroute_via_backup" }
  },
  "timestamp": "2026-11-23T17:50:22.000000+00:00"
}
```

#### `RECOVERY_FAILED` (Actuation error or verification failure)
```json
{
  "event": "RECOVERY_FAILED",
  "data": {
    "incident_id": "inc-001",
    "error": "Controller unreachable timeout"
  },
  "timestamp": "2026-11-23T17:50:25.000000+00:00"
}
```

---

## 11. Error Responses

All error responses follow this structure:

```json
{
  "error": {
    "code": "DEVICE_NOT_FOUND",
    "message": "Device 's5' not found in topology.",
    "request_id": "req_abc123",
    "timestamp": "2024-01-01T10:00:00Z"
  }
}
```

| HTTP Status | Code | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Request body failed schema validation |
| 401 | `UNAUTHORIZED` | Missing or invalid JWT |
| 403 | `FORBIDDEN` | Valid JWT but insufficient role |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Action already in progress |
| 422 | `UNPROCESSABLE` | Valid JSON but semantically invalid |
| 500 | `INTERNAL_ERROR` | Unhandled server error |
| 503 | `SERVICE_UNAVAILABLE` | Ryu controller unreachable |

---

## 12. Diagnostics, Simulation & Connector Testing Endpoints

### 12.1 Health Check Probe
`GET /api/health` & `GET /health`

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "SentinelNet AI Self-Healing Network",
  "version": "1.0.0",
  "environment": "development",
  "timestamp": "2026-11-24T02:00:00.000000"
}
```

### 12.2 Model Retraining
`POST /api/models/retrain`

Triggers real `train_model.py` execution against synthetic and telemetry feedback buffers, evaluates honest metrics, reloads `AnomalyDetector`, and updates serialized artifacts.

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Model retraining complete",
  "job_status": "completed",
  "duration_sec": 1.18,
  "model_version": "1.2.0-retrained",
  "trained_at": "2026-11-24T02:00:00Z",
  "evaluation": {
    "precision": 1.0,
    "recall": 1.0,
    "f1_score": 1.0,
    "roc_auc": 1.0
  }
}
```

### 12.3 Active Model Metadata
`GET /api/models/info`

**Response (200 OK):**
```json
{
  "model_version": "1.2.0-synthetic-baseline",
  "trained_at": "2026-11-23T11:46:18Z",
  "features": [
    "latency_ms", "packet_loss_pct", "cpu_pct", "memory_pct",
    "bandwidth_mbps", "interface_up", "error_count"
  ],
  "training_samples": 8000,
  "total_samples": 10000,
  "evaluation_metrics": {
    "precision": 1.0,
    "recall": 1.0,
    "f1_score": 1.0,
    "roc_auc": 1.0
  },
  "contamination": 0.05,
  "status": "ready"
}
```

### 12.4 Recent Telemetry Detections
`GET /api/detect/recent?limit=20`

**Response (200 OK):**
```json
{
  "count": 1,
  "threshold": 0.65,
  "detections": [
    {
      "incident_id": "inc-01",
      "target_id": "link-s2-s3",
      "severity": "critical",
      "anomaly_score": 0.942,
      "is_anomaly": true,
      "detected_at": "2026-11-24T01:55:00.000000",
      "reason": "Link Failure on link-s2-s3",
      "telemetry": {
        "latency_ms": 999.0,
        "packet_loss_pct": 100.0,
        "interface_up": 0
      }
    }
  ]
}
```

### 12.5 Digital Twin Recovery Simulation
`POST /api/recovery/simulate`

Evaluates path selection and capacity headroom in an in-memory NetworkX graph model. Clearly disclaims real data-plane measurement.

**Request:**
```json
{
  "incident_id": "inc-01"
}
```

**Response (200 OK):**
```json
{
  "incident_id": "inc-01",
  "target": "link-s2-s3",
  "scenario": "Simulated bypass reroute for link-s2-s3",
  "simulated": true,
  "disclaimer": "Simulated in NetworkX topology model, not physically measured",
  "predicted_metrics": {
    "predicted_latency_ms": 12.0,
    "baseline_latency_ms": 7.2,
    "latency_delta_ms": 4.8,
    "predicted_packet_loss_pct": 0.0,
    "flow_mod_rules_required": 4,
    "capacity_headroom_mbps": 85.0,
    "safeguards_verified": true
  },
  "simulated_path": {
    "hops": ["s1", "s3"],
    "path_type": "backup_bypass",
    "avoided_nodes": ["link-s2-s3"]
  },
  "timestamp": "2026-11-24T02:00:00.000000"
}
```

### 12.6 Infrastructure Connector Audit
`POST /api/integrations/test/{integration_id}`

Supports: `postgres`, `ryu`, `mininet`, `prometheus`, `redis`, `grafana`, `slack`.

**Response (200 OK):**
```json
{
  "id": "postgres",
  "status": "CONNECTED",
  "latency_ms": 1.45,
  "message": "PostgreSQL database query successful (1.45 ms)",
  "timestamp": "2026-11-24T02:00:00.000000"
}
```

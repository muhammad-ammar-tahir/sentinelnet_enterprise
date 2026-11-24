# 08 — Database Schema

## Table of Contents
1. [Overview](#1-overview)
2. [Entity Relationship Diagram](#2-entity-relationship-diagram)
3. [Table: devices](#3-table-devices)
4. [Table: links](#4-table-links)
5. [Table: incidents](#5-table-incidents)
6. [Table: metrics](#6-table-metrics)
7. [Table: recovery_actions](#7-table-recovery_actions)
8. [Table: policies](#8-table-policies)
9. [Table: users](#9-table-users)
10. [Table: audit_logs](#10-table-audit_logs)
11. [Indexes](#11-indexes)
12. [Alembic Migrations](#12-alembic-migrations)
13. [Database Seeding & Idempotency](#13-database-seeding--idempotency)
14. [Example Rows](#14-example-rows)

---

## 1. Overview

SentinelNet uses **PostgreSQL 15** (or **SQLite** for local development) as its primary relational store. The schema is designed around four core concepts:

1. **Topology** — network devices and links being monitored (`devices`, `links`)
2. **Events & Telemetry** — anomalies detected and time-series metrics (`incidents`, `metrics`)
3. **Actions & Policies** — self-healing rules and execution records (`recovery_actions`, `policies`)
4. **Operational & Security** — operator accounts and immutable audit logs (`users`, `audit_logs`)

All tables use standard primary keys, foreign key constraints, composite performance indexes, and UTC timestamp tracking. Schema initialization is performed via `backend/database/database.py` with automatic table existence verification, and database versioning is managed via Alembic migrations.

---

## 2. Entity Relationship Diagram

```
┌──────────┐       ┌──────────┐
│  devices │       │  links   │
│          │       │          │
│ id (PK)  │       │ id (PK)  │
│ name     │       │ from_dev ├──► devices.id
│ type     │       │ to_dev   ├──► devices.id
│ status   │       │ type     │
│ zone     │       │ status   │
└────┬─────┘       └────┬─────┘
     │                  │
     │  1              1│
     │  ↓              ↓│  many
     │  ┌──────────────────────┐
     │  │       incidents      │
     └─►│                      │
        │ id (PK)              │
        │ affected_device_ids[]├──► devices.id[]
        │ affected_link_ids[]  ├──► links.id[]
        │ status               │
        │ failure_type         │
        │ anomaly_score        │
        │ confidence           │
        └──────┬───────────────┘
               │1
               │
        many   ↓
     ┌─────────────────────┐       ┌─────────────┐
     │   recovery_actions  │       │   policies  │
     │                     │       │             │
     │ id (PK)             │       │ id (PK)     │
     │ incident_id    ─────┘       │ failure_type│
     │ action              │       │ action      │
     │ status              │       │ severity    │
     │ policy_id      ─────────────► id          │
     └─────────────────────┘       └─────────────┘

┌────────────┐    ┌──────────────────┐    ┌──────────┐
│   metrics  │    │  feedback_buffer │    │  users   │
│            │    │                  │    │          │
│ id (PK)    │    │ id (PK)          │    │ id (PK)  │
│ device_id ─┼──► │ incident_id      │    │ username │
│ link_id   ─┼──► │ feature_vector   │    │ role     │
│ timestamp  │    │ label            │    │ ...      │
│ metrics{}  │    │ action           │    └──────────┘
└────────────┘    │ outcome          │
                  └──────────────────┘
```

---

## 3. Table: devices

Represents each node in the simulated network.

```sql
CREATE TABLE devices (
    id              VARCHAR(50)  PRIMARY KEY,           -- e.g. 's1', 'h1', 'srv1', 'c0'
    name            VARCHAR(100) NOT NULL,
    type            VARCHAR(20)  NOT NULL                -- controller, switch, host, server
                    CHECK (type IN ('controller','switch','host','server')),
    zone            VARCHAR(50),                         -- lab_a, lab_b, core, server_room
    ip_address      INET,
    mac_address     MACADDR,
    status          VARCHAR(20)  NOT NULL DEFAULT 'UP'
                    CHECK (status IN ('UP','DOWN','DEGRADED','UNKNOWN','SUSPENDED')),
    openflow_dpid   BIGINT,                              -- Datapath ID assigned by Ryu
    port_count      SMALLINT,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | VARCHAR(50) | No | Short identifier (matches Mininet name) |
| `name` | VARCHAR(100) | No | Human-readable label |
| `type` | VARCHAR(20) | No | Node type |
| `zone` | VARCHAR(50) | Yes | Physical or logical zone |
| `ip_address` | INET | Yes | IPv4/v6 address |
| `mac_address` | MACADDR | Yes | MAC address |
| `status` | VARCHAR(20) | No | Current status |
| `openflow_dpid` | BIGINT | Yes | OpenFlow Datapath ID |
| `port_count` | SMALLINT | Yes | Number of ports |

---

## 4. Table: links

Represents each network link between two devices.

```sql
CREATE TABLE links (
    id              VARCHAR(50)  PRIMARY KEY,           -- e.g. 'L1', 'BL1'
    name            VARCHAR(100),
    from_device_id  VARCHAR(50)  NOT NULL REFERENCES devices(id),
    to_device_id    VARCHAR(50)  NOT NULL REFERENCES devices(id),
    from_port       SMALLINT,
    to_port         SMALLINT,
    link_type       VARCHAR(20)  NOT NULL DEFAULT 'primary'
                    CHECK (link_type IN ('primary','backup','access')),
    bandwidth_mbps  INTEGER,
    delay_ms        NUMERIC(6,2),
    loss_pct        NUMERIC(5,2) DEFAULT 0,
    status          VARCHAR(20)  NOT NULL DEFAULT 'UP'
                    CHECK (status IN ('UP','DOWN','DEGRADED','SUSPENDED')),
    is_active_path  BOOLEAN      NOT NULL DEFAULT FALSE, -- is traffic currently using this link?
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 5. Table: incidents

Central event table — one row per detected anomaly/fault.

```sql
CREATE TABLE incidents (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id         VARCHAR(50)  UNIQUE,             -- e.g. 'inc_20240101_0042'
    status              VARCHAR(30)  NOT NULL DEFAULT 'DETECTED'
                        CHECK (status IN (
                            'DETECTED','DIAGNOSING','RECOVERING',
                            'VERIFYING','RESOLVED','ESCALATED',
                            'MANUAL_REVIEW','PARTIAL_RESOLUTION'
                        )),
    failure_type        VARCHAR(30)
                        CHECK (failure_type IN (
                            'LINK_FAILURE','CONGESTION','HIGH_LATENCY',
                            'DEVICE_FAILURE','REPEATED_FAILURE'
                        )),
    severity            VARCHAR(10)  NOT NULL DEFAULT 'LOW'
                        CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    affected_device_ids VARCHAR(50)[] DEFAULT '{}',       -- PostgreSQL array
    affected_link_ids   VARCHAR(50)[] DEFAULT '{}',
    anomaly_score       NUMERIC(5,4),                    -- 0.0000 to 1.0000
    confidence          NUMERIC(5,4),
    class_probabilities JSONB,                           -- {LINK_FAILURE: 0.94, ...}
    feature_vector      JSONB,                           -- {rx_bytes_rate: 0, ...}
    detection_time_ms   INTEGER,
    recovery_time_ms    INTEGER,
    resolved_at         TIMESTAMPTZ,
    escalated_at        TIMESTAMPTZ,
    escalation_reason   TEXT,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 6. Table: metrics

Time-series metric snapshots, mirrored from Prometheus for ML and audit.

```sql
CREATE TABLE metrics (
    id                  BIGSERIAL    PRIMARY KEY,
    device_id           VARCHAR(50)  NOT NULL REFERENCES devices(id),
    link_id             VARCHAR(50)  REFERENCES links(id),
    captured_at         TIMESTAMPTZ  NOT NULL,
    rx_bytes_rate       BIGINT,
    tx_bytes_rate       BIGINT,
    rx_error_rate       NUMERIC(10,2),
    tx_drop_rate        NUMERIC(10,2),
    flow_table_size     INTEGER,
    link_utilization    NUMERIC(6,2),
    rtt_ms              NUMERIC(8,2),
    host_cpu_pct        NUMERIC(5,2),
    anomaly_score       NUMERIC(5,4),
    is_anomalous        BOOLEAN      NOT NULL DEFAULT FALSE,
    incident_id         UUID         REFERENCES incidents(id)
);

-- Partition by month for performance
CREATE INDEX idx_metrics_device_time ON metrics(device_id, captured_at DESC);
CREATE INDEX idx_metrics_captured_at ON metrics(captured_at DESC);
```

> **Note:** For large-scale deployments, `metrics` should use TimescaleDB hypertables. For the semester project, a plain PostgreSQL table with a time-based index is sufficient.

---

## 7. Table: recovery_actions

Records every automated or manual recovery action taken.

```sql
CREATE TABLE recovery_actions (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id         UUID         NOT NULL REFERENCES incidents(id),
    policy_id           UUID         REFERENCES policies(id),
    action              VARCHAR(50)  NOT NULL
                        CHECK (action IN (
                            'REROUTE_TO_BACKUP','RATE_LIMIT','REROUTE_AROUND_DEVICE',
                            'RESET_FLOW_TABLE','ESCALATE_TO_MANUAL','PERMANENT_REROUTE'
                        )),
    status              VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','EXECUTING','SUCCESS','FAILED','TIMEOUT')),
    target_device_id    VARCHAR(50)  REFERENCES devices(id),
    target_link_id      VARCHAR(50)  REFERENCES links(id),
    parameters          JSONB,                           -- action-specific params
    ryu_api_response    JSONB,                           -- raw Ryu API response
    initiated_by        VARCHAR(20)  NOT NULL DEFAULT 'AUTOMATED'
                        CHECK (initiated_by IN ('AUTOMATED','MANUAL')),
    initiated_by_user   UUID         REFERENCES users(id),
    executed_at         TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    duration_ms         INTEGER,
    error_message       TEXT,
    retry_count         SMALLINT     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 8. Table: policies

Recovery policy rules evaluated before ML recommendations.

```sql
CREATE TABLE policies (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(100) NOT NULL,
    description         TEXT,
    failure_type        VARCHAR(30),                     -- NULL = match any type
    severity            VARCHAR(10)  DEFAULT 'ANY',
    zone                VARCHAR(50)  DEFAULT 'ANY',
    action              VARCHAR(50)  NOT NULL,
    automation          VARCHAR(20)  NOT NULL DEFAULT 'AUTOMATED'
                        CHECK (automation IN ('AUTOMATED','MANUAL_APPROVAL','DISABLED')),
    priority            SMALLINT     NOT NULL DEFAULT 10, -- lower = higher priority
    enabled             BOOLEAN      NOT NULL DEFAULT TRUE,
    schedule_json       JSONB,                           -- {from, until, days}
    created_by          UUID         REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 9. Table: users

NOC operators and administrators.

```sql
CREATE TABLE users (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    username            VARCHAR(50)  NOT NULL UNIQUE,
    email               VARCHAR(255) NOT NULL UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,           -- bcrypt
    role                VARCHAR(20)  NOT NULL DEFAULT 'viewer'
                        CHECK (role IN ('admin','operator','viewer')),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Role Permissions:**

| Role | View Incidents | Trigger Recovery | Edit Policies | Manage Users |
|---|---|---|---|---|
| `viewer` | ✅ | ❌ | ❌ | ❌ |
| `operator` | ✅ | ✅ | ✅ | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ |

---

## 10. Table: audit_logs

Stores immutable security, remediation, and administrative event audit records.

```sql
CREATE TABLE audit_logs (
    id                  VARCHAR(64)  PRIMARY KEY,
    action              VARCHAR(64)  NOT NULL,
    actor               VARCHAR(64)  NOT NULL,
    details             JSON,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_audit_logs_id ON audit_logs(id);
```

---

## 11. Indexes

SentinelNet defines optimized composite and single-column indexes in `backend/database/models.py` for sub-millisecond query latencies:

```sql
-- Incidents Indexes
CREATE INDEX ix_incidents_status           ON incidents(status);
CREATE INDEX ix_incidents_severity         ON incidents(severity);
CREATE INDEX ix_incidents_detected_at_desc ON incidents(detected_at DESC);

-- Recovery Actions Indexes
CREATE INDEX ix_recovery_actions_incident_id  ON recovery_actions(incident_id);
CREATE INDEX ix_recovery_actions_executed_at  ON recovery_actions(executed_at);

-- Telemetry Metrics Indexes (Essential for time-series charts and aggregation)
CREATE INDEX ix_metrics_device_id_timestamp_desc ON metrics(device_id, timestamp DESC);
CREATE INDEX ix_metrics_timestamp_idx            ON metrics(timestamp);
```

---

## 12. Alembic Migrations

Database schema versioning is managed via **Alembic** with asynchronous driver support (`backend/database/migrations/env.py`).

Configuration files:
- `alembic.ini`: Root configuration pointing to `backend/database/migrations`.
- `backend/database/migrations/env.py`: Async migration runner wrapping `Base.metadata`.
- `backend/database/migrations/versions/0001_initial.py`: Initial schema creation for all 8 tables.

Commands:
```bash
# Upgrade database to latest revision
alembic upgrade head

# Check current database revision
alembic current

# Rollback one migration
alembic downgrade -1
```

---

## 13. Database Seeding & Idempotency

The database seeding script (`backend/database/seed.py`) populates the database with real entities matching Mininet's `UniversityTopology`:

- **SDN Controller (1)**: `c0`
- **Switches (3)**: `s1` (DPID 1), `s2` (DPID 2), `s3` (DPID 3)
- **Hosts (4)**: `h1` (10.0.1.1), `h2` (10.0.1.2), `h3` (10.0.1.3), `h4` (10.0.1.4)
- **Servers (1)**: `srv1` (10.0.0.50)
- **Links (7)**: physical port mappings, including failable `s2-s3` link
- **Incidents (3)**: 1 resolved, 1 rolled back, 1 failed
- **Recovery Actions (2)**: associated with incidents
- **Policy (1)**: default link failure self-healing rule
- **User (1)**: demo operator (`admin` / salted SHA-256 password hash)
- **Metrics (192)**: 60 minutes of historical telemetry (5-minute intervals across 4 devices)
- **Audit Log (1)**: system bootstrap record

### Running the Seed Script:

```bash
# Seed default PostgreSQL database:
python -m backend.database.seed

# Or seed with custom database URL (e.g., local SQLite):
$env:DATABASE_URL="sqlite+aiosqlite:///./sentinelnet.db"; python -m backend.database.seed
```

**Idempotency Guarantee**: The script checks for existing records before inserting and replaces/synchronizes metrics, ensuring repeated executions never fail or produce duplicate primary keys.

---

## 14. Example Rows

### devices

| id | name | type | zone | ip_address | status |
|---|---|---|---|---|---|
| c0 | Ryu SDN Controller | controller | — | 10.0.0.254 | UP |
| s1 | Lab A Switch | switch | lab_a | — | UP |
| s2 | Core Switch | switch | core | — | DOWN |
| s3 | Server Room Switch | switch | server_room | — | UP |
| h1 | Student PC 1 | host | lab_a | 10.0.0.1 | UP |
| srv1 | App Server | server | server_room | 10.0.0.10 | UP |

### links

| id | from | to | type | bandwidth_mbps | status | is_active_path |
|---|---|---|---|---|---|---|
| L1 | s1 | s2 | primary | 100 | DOWN | false |
| L2 | s2 | s3 | primary | 100 | UP | true |
| BL1 | s1 | s3 | backup | 50 | UP | true |
| BL2 | s2 | s3 | backup | 50 | UP | false |

### incidents (most recent)

| external_id | status | failure_type | confidence | affected_links | detection_ms | recovery_ms |
|---|---|---|---|---|---|---|
| inc_20240101_0042 | RESOLVED | LINK_FAILURE | 0.94 | {L1} | 25400 | 33000 |
| inc_20240101_0043 | ESCALATED | DEVICE_FAILURE | 0.98 | {} | 1200 | — |
| inc_20240101_0044 | RESOLVED | CONGESTION | 0.82 | {L2} | 51000 | 32000 |

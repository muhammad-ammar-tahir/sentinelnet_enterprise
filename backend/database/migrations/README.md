# SentinelNet Database Migrations (Alembic)

This directory contains database schema migration scripts managed by [Alembic](https://alembic.sqlalchemy.org/).

## Running Migrations

Ensure your virtual environment is active and `DATABASE_URL` is set in `.env`.

### 1. Upgrade to the Latest Revision
```bash
alembic upgrade head
```

### 2. Check Migration History
```bash
alembic history --verbose
```

### 3. Check Current Database Revision
```bash
alembic current
```

### 4. Create a New Migration Revision (Autogenerate)
```bash
alembic revision --autogenerate -m "describe_changes_here"
```

### 5. Rollback Migration by 1 Step
```bash
alembic downgrade -1
```

## Schema Versions Included
- `0001_initial.py`: Defines all 8 core tables:
  1. `devices` (OpenFlow switches, hosts, server, controller)
  2. `links` (physical and logical links with port numbers)
  3. `incidents` (faults with severity and status indexes)
  4. `recovery_actions` (re-route and mitigation execution records)
  5. `metrics` (time-series telemetry points with composite indexes)
  6. `policies` (autonomous healing rules)
  7. `users` (operator and admin accounts with hashed credentials)
  8. `audit_logs` (security and operational audit trail)

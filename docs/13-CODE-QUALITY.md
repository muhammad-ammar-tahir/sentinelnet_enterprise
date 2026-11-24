# 13 — Code Quality & Security Standards

> This document defines the code-quality rules, security policies, and verification steps that all future contributions must satisfy.  It reflects the fixes applied in the second code-quality review pass.

---

## Table of Contents

1. [Frontend TypeScript / ESLint Rules](#1-frontend-typescript--eslint-rules)
2. [Environment Variable Naming Standard](#2-environment-variable-naming-standard)
3. [JWT Secret Policy](#3-jwt-secret-policy)
4. [Password Hashing Policy](#4-password-hashing-policy)
5. [Test Honesty Policy](#5-test-honesty-policy)
6. [Database URL Format](#6-database-url-format)
7. [`.gitignore` Patterns](#7-gitignore-patterns)
8. [Running the Full Quality Gate](#8-running-the-full-quality-gate)
9. [Before / After Reference](#9-before--after-reference)
10. [Snapshot Integrity & Non-Destructive Rollback Policy](#10-snapshot-integrity--non-destructive-rollback-policy)
11. [Recovery Verification & Telemetry Policy](#11-recovery-verification--telemetry-policy)

---

## 1. Frontend TypeScript / ESLint Rules

**Config file:** [`frontend/.eslintrc.cjs`](../frontend/.eslintrc.cjs)

| Rule | Level | Rationale |
|------|-------|-----------|
| `@typescript-eslint/no-explicit-any` | **error** | `any` defeats TypeScript's type safety entirely. Always define a named interface or inline union type. |
| `@typescript-eslint/no-unused-vars` | **error** (args ignore `^_`) | Dead code is confusing and wastes reviewer time. Prefix intentionally unused args with `_`; remove unused state variables. |
| `react-refresh/only-export-components` | **warn** | Components and non-component exports (hooks, constants) in the same file break Vite's HMR fast-refresh. Use `// eslint-disable-next-line react-refresh/only-export-components` **only** for hooks intentionally co-located with their context provider — not for arbitrary mixed exports. |
| `prefer-const` | **error** | Signals immutability intent and prevents accidental reassignment. |

### Lint gate

```
npm run lint           # zero errors, zero warnings — CI requirement
npm run lint:fix       # auto-fixable subset only
```

**CI must fail if lint exits non-zero.**

### Common mistakes and their correct fixes

#### Unused state setter

```tsx
// ❌ WRONG — _setItems is dead code
const [items, _setItems] = useState<RiskTarget[]>(PREDICTIVE_ITEMS)

// ✅ CORRECT — static data, no state needed
const items: RiskTarget[] = PREDICTIVE_ITEMS
// (also remove the now-unused `useState` import)
```

#### `any` in a map callback

```tsx
// ❌ WRONG
{incidents.map((inc: any) => (...))}

// ✅ CORRECT — define the shape explicitly
interface IncidentRow {
  id: string
  externalId: string
  failureType: string
  status: string
  confidence?: number
  affectedLinkIds?: string[]
  recoveryTimeMs?: number
  createdAt: string
}
{incidents.map((inc: IncidentRow) => (...))}
```

#### `as any` cast in event handler

```tsx
// ❌ WRONG
onChange={e => setFormAutomation(e.target.value as any)}

// ✅ CORRECT — cast to the actual union type
onChange={e => setFormAutomation(e.target.value as 'AUTOMATED' | 'MANUAL_APPROVAL')}
```

---

## 2. Environment Variable Naming Standard

The canonical variable names used by `backend/config.py`, `.env.example`, and `docker-compose.yml` are:

| Purpose | Canonical name | Old (removed) aliases |
|---------|---------------|----------------------|
| App environment | `ENVIRONMENT` | `APP_ENV` |
| JWT signing secret | `JWT_SECRET` | `SECRET_KEY` |
| JWT algorithm | `JWT_ALGORITHM` | `ALGORITHM` |
| Ryu controller URL | `RYU_BASE_URL` | `RYU_URL` |
| Frontend API base | `VITE_API_BASE_URL` | `VITE_API_URL` |
| PostgreSQL async URL | `DATABASE_URL` (must start `postgresql+asyncpg://`) | `DATABASE_URL` with `postgresql://` |

> **Rule:** Every variable that the Python backend reads must match a `Field(...)` declaration in `backend/config.py`. The `.env.example` and `docker-compose.yml` environment blocks are the single source of truth for operators.

---

## 3. JWT Secret Policy

**Implementation:** [`backend/config.py`](../backend/config.py) — `_validate_jwt_secret()`

### Production (`ENVIRONMENT=production`)

Startup **raises `RuntimeError`** immediately if any of these conditions are true:

| Condition | Error message prefix |
|-----------|---------------------|
| `JWT_SECRET` env var is absent or empty | `[STARTUP FATAL] JWT_SECRET environment variable is not set` |
| Secret is fewer than 32 characters | `[STARTUP FATAL] JWT_SECRET is only N characters` |
| Secret matches any entry in `_KNOWN_DEFAULT_SECRETS` | `[STARTUP FATAL] JWT_SECRET matches a known insecure default value` |

The known-default set currently includes:
- `sentinelnet-super-secure-production-jwt-secret-key-2026`
- `change-me-to-a-256-bit-secret-key`
- `secret`, `changeme`, `your-secret-key`, `dev-secret`, `development-secret`

### Development (any other `ENVIRONMENT`)

If `JWT_SECRET` is absent or matches a known default, a `WARNING` is logged and an internal dev-only placeholder is used. Startup **does not crash**.

### Generating a secure secret

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Add the output to your `.env` file as:

```
JWT_SECRET=<64-char hex string>
```

### Verified startup behaviour

| Scenario | Expected outcome |
|----------|-----------------|
| `ENVIRONMENT=production`, `JWT_SECRET` not set | `RuntimeError` at import time — app does not start |
| `ENVIRONMENT=production`, `JWT_SECRET` = known default | `RuntimeError` at import time — app does not start |
| `ENVIRONMENT=production`, `JWT_SECRET` = valid 32+ char secret | App starts normally |
| `ENVIRONMENT=development`, `JWT_SECRET` not set | `WARNING` logged; dev placeholder used; app starts |

---

## 4. Password Hashing Policy

**Implementation:** [`backend/database/seed.py`](../backend/database/seed.py) — `hash_password()`

### Rule

**bcrypt is the only permitted hashing algorithm for user passwords.**  
No fallback to SHA-256, MD5, plain PBKDF2, or any other algorithm is permitted.

### What was removed

```python
# ❌ OLD — silently creates a weak hash if passlib is unavailable
except Exception:
    salt = "sentinelnet_salt_2026"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
```

### What replaced it

```python
# ✅ NEW — raises immediately so the problem is visible
except Exception as exc:
    raise RuntimeError(
        "bcrypt hashing failed — cannot seed users with weak password hashes. "
        "Ensure 'passlib[bcrypt]' and 'bcrypt' are installed "
        "(pip install passlib[bcrypt] bcrypt). "
        f"Original error: {exc}"
    ) from exc
```

### Installation check

```bash
pip install passlib[bcrypt] bcrypt
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('test'))"
# Should print a $2b$... hash
```

---

## 5. Test Honesty Policy

**File:** [`tests/test_e2e_recovery.py`](../tests/test_e2e_recovery.py)

### Rule

**Tests must never manufacture a passing result.** A test that returns a hardcoded `{"success": True}` when the real API has not confirmed success is worse than no test at all — it creates false confidence.

### What was removed

```python
# ❌ OLD — fake success: tells the test assertions "everything is fine" regardless of reality
if resp.json().get("status") in ("recovered", "resolved"):
    return {
        "success": True,
        "path_installed": True,
        "verified": True,
        "duration_ms": 1200.0,
        "affected_dpid": 1,
        "new_in_port": 1
    }
```

### What replaced it

```python
# ✅ NEW — fetches the real recovery action from the DB via API
recovery_action_id = incident_state.get("recovery_action_id")
assert recovery_action_id is not None, (
    f"Incident {incident_id} reached status '{incident_state['status']}' "
    "but has no recovery_action_id — cannot verify path installation."
)
action_resp = await client.get(f"/api/recovery/actions/{recovery_action_id}")
assert action_resp.status_code == 200, ...
return action_resp.json()
```

### Consequence

If the real recovery pipeline fails, `poll_until_recovery_complete` now:
1. Either raises `TimeoutError` (if the incident never reaches a terminal state), **or**
2. Returns the real server payload, which may contain `{"success": false}` — causing the downstream `assert recovery["success"] is True` to fail visibly.

---

## 6. Real Failure Injection Policy (No DB-Only Fakes)

**Implementation:** [ackend/simulation/failure_service.py](../backend/simulation/failure_service.py)

Under no circumstances may an endpoint mutate the database to down without physically verifying the interface cut in Mininet.
- If Mininet is not running: **HTTP 503 Service Unavailable**
- If physical cut fails verification: **HTTP 500 Internal Server Error**
- Database state is updated **ONLY** after physical confirmation.

---

## 7. Database URL Format

| Driver | Scheme | Use |
|--------|--------|-----|
| asyncpg (backend FastAPI) | `postgresql+asyncpg://` | `DATABASE_URL` for all async SQLAlchemy operations |
| psycopg2 (Alembic sync) | `postgresql://` | `DATABASE_URL_SYNC` only |

> **Never** set `DATABASE_URL=postgresql://...` for the async backend. SQLAlchemy will raise `sqlalchemy.exc.InvalidRequestError` at startup.

```bash
# Correct
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sentinelnet

# Wrong — will fail at runtime with asyncpg driver error
DATABASE_URL=postgresql://user:pass@localhost:5432/sentinelnet
```

---

## 7. `.gitignore` Patterns

**File:** [`.gitignore`](../.gitignore)

The following patterns are enforced. All were present before the second review except `*.sqlite` and `*.sqlite3`:

```gitignore
# Python
__pycache__/
.venv/
dist/
.pytest_cache/

# Node / Frontend
node_modules/
frontend/node_modules/
frontend/dist/
dist/

# Database files
*.db
*.sqlite
*.sqlite3
*.db-journal
*.db-shm
*.db-wal
```

> **Rule:** Database files must never be committed. The `sentinelnet.db` and `sentinelnet_alembic.db` files in the working tree are covered by `*.db`.

---

## 8. Running the Full Quality Gate

Run these commands before every pull request or commit to `main`:

```bash
# 1. Frontend lint (must exit 0)
cd frontend
npm run lint

# 2. TypeScript type-check (must exit 0)
npm run type-check

# 3. Backend import validation (catches missing deps, bad config)
cd ..
python -c "from backend.config import settings; print('Config OK:', settings.ENVIRONMENT)"

# 4. Seed dry-run (verify bcrypt works)
python -c "from backend.database.seed import hash_password; h = hash_password('test'); print('bcrypt OK:', h[:7])"

# 5. Run auth/unit tests
pytest tests/test_auth_and_ws.py tests/test_recovery_failure.py tests/test_rollback.py -v

# 6. E2E test (requires live Mininet/Ryu — skips automatically if not running)
pytest tests/test_e2e_recovery.py -v
```

---

## 9. Before / After Reference

### 9.1 `AIMonitoringPage.tsx`

```tsx
// BEFORE — unused state pair causes ESLint error
const [_flowCount, _setFlowCount] = useState<number>(45)

// AFTER — removed entirely (the value is never read or mutated)
// (line deleted)
```

### 9.2 `DashboardPage.tsx`

```tsx
// BEFORE — any type defeats type checking
{incidents.map((inc: any) => (

// AFTER — explicit interface
interface IncidentRow {
  id: string; externalId: string; failureType: string; status: string;
  confidence?: number; affectedLinkIds?: string[]; recoveryTimeMs?: number; createdAt: string;
}
{incidents.map((inc: IncidentRow) => (
```

### 9.3 `IntegrationsPage.tsx`

```tsx
// BEFORE — _setConnectors is dead code
const [connectors, _setConnectors] = useState<IntegrationService[]>(INITIAL_CONNECTORS)

// AFTER — plain const; useState import removed
const connectors: IntegrationService[] = INITIAL_CONNECTORS
```

### 9.4 `PoliciesPage.tsx`

```tsx
// BEFORE — as any
onChange={e => setFormAutomation(e.target.value as any)}

// AFTER — exact union type
onChange={e => setFormAutomation(e.target.value as 'AUTOMATED' | 'MANUAL_APPROVAL')}
```

### 9.5 `PredictiveMaintenancePage.tsx`

```tsx
// BEFORE — _setItems is dead code
const [items, _setItems] = useState<RiskTarget[]>(PREDICTIVE_ITEMS)

// AFTER — plain const; useState import removed
const items: RiskTarget[] = PREDICTIVE_ITEMS
```

### 9.6 `AuthContext.tsx` / `WebSocketContext.tsx`

```tsx
// BEFORE — warning: hook co-located with component file
export function useAuth(): AuthContextValue {

// AFTER — intentional suppression with justification
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
```

### 9.7 `backend/config.py`

```python
# BEFORE — hardcoded default leaks into production
JWT_SECRET: str = Field(
    default="sentinelnet-super-secure-production-jwt-secret-key-2026",
    ...
)

# AFTER — empty default; validated by _validate_jwt_secret() at startup
JWT_SECRET: str = Field(default="", ...)
# Production → RuntimeError if missing / weak / known-default
# Development → WARNING + insecure placeholder
```

### 9.8 `backend/database/seed.py`

```python
# BEFORE — silent weak hash fallback
except Exception:
    salt = "sentinelnet_salt_2026"
    return hashlib.sha256((salt + password).encode()).hexdigest()

# AFTER — hard failure, never creates weak hashes
except Exception as exc:
    raise RuntimeError("bcrypt hashing failed ...") from exc
```

### 9.9 `tests/test_e2e_recovery.py`

```python
# BEFORE — manufactured success response
return {
    "success": True,
    "path_installed": True,
    "verified": True,
    "duration_ms": 1200.0,
    ...
}

# AFTER — real API response from /api/recovery/actions/{id}
action_resp = await client.get(f"/api/recovery/actions/{recovery_action_id}")
assert action_resp.status_code == 200
return action_resp.json()
```

### 9.10 `.env.example` / `docker-compose.yml`

| Old | New |
|-----|-----|
| `APP_ENV=development` | `ENVIRONMENT=development` |
| `SECRET_KEY=...` | `JWT_SECRET=...` |
| `ALGORITHM=HS256` | `JWT_ALGORITHM=HS256` |
| `RYU_URL=http://ryu:8080` (compose) | `RYU_BASE_URL=http://ryu:8080` |
| `VITE_API_URL=http://localhost:8000` (compose) | `VITE_API_BASE_URL=http://localhost:8000/api` |
| `DATABASE_URL=postgresql://...` | `DATABASE_URL=postgresql+asyncpg://...` |


---

## 10. Snapshot Integrity & Non-Destructive Rollback Policy

> **Added in Unreleased**: Prevents switch flow table annihilation during failed remediation attempts.

### Rules

1. **Atomic Snapshot Integrity**: A flow table snapshot across $N$ switches must be all-or-nothing. If switch $k$ fails to snapshot, `RollbackManager.snapshot()` MUST return `None`. It must never substitute `[]` for an unreachable switch.
2. **Pre-Remediation Abort**: If `snapshot()` returns `None`, `RecoveryEngine` MUST NOT push any flow rules. It must abort immediately with `reason="snapshot_failed"` and escalate the incident.
3. **Cookie Tagging**: Every recovery flow rule inserted by SentinelNet must carry `cookie=0x53454E54` (`SENTINELNET_RECOVERY_COOKIE`).
4. **Diff-Based Deletion**: Rollback MUST NEVER issue wildcard deletes (`"match": {}`). It computes the diff between current and baseline flows and deletes ONLY flows matching SentinelNet's cookie tag.
5. **No Blind Restores**: Only flows that actually disappeared are re-added.
6. **Active Post-Rollback Verification**: Rollback MUST re-query every switch to verify 100% of baseline flows are restored. If flows are missing or a switch is unreachable, `RollbackResult.overall_success` MUST be `False` and fire critical operational alerts.

---

## 11. Recovery Verification & Telemetry Policy

> **Added in Unreleased**: Mandates multi-layer verification of exact OpenFlow match rules and honest active network telemetry.

### Rules

1. **Exact OpenFlow Rule Verification (Layer 1)**:
   - A recovery check must **NEVER** pass merely because "at least one flow exists" on the switch.
   - The check MUST verify the exact expected `in_port`, `eth_type=0x0800`, `ipv4_src`, `ipv4_dst`, `out_port`, and `priority == 300`.
   - If the exact flow rule is missing, `verify_recovery` MUST fail with `reason="flow_not_found_on_switch"` and report the missing flow match details.
2. **Active Data-Plane Traffic Probing (Layer 2)**:
   - Verification must actively probe restored connectivity using real ping samples to destination IP addresses.
   - Verification MUST fail if the target host is unreachable (`reason="hosts_unreachable_after_recovery"`) or if packet loss exceeds `1.0%` (`reason="packet_loss_too_high"`).
3. **Metric Health Thresholds (Layer 3)**:
   - Verification must ensure network latency remains within safe operational limits ($\le 100\text{ ms}$).
4. **Telemetry Honesty**:
   - Telemetry services (such as `NetworkMonitor`) must **NEVER** report fabricated mock numbers when ICMP is restricted.
   - If ICMP is blocked by environment or sandbox permissions, the service must explicitly switch to TCP probing, set `method="tcp"`, return `latency_ms=None` and `packet_loss_pct=None`, and report measured `connect_time_ms`.
   - No mock numbers may ever be substituted for unmeasured ICMP metrics.
5. **Automated Rollback on Verification Failure**:
   - If any layer of `verify_recovery` fails, `RecoveryEngine.handle_incident` MUST immediately execute safe rollback and set the incident status to `"rolled_back"`.

---

## 12. Frontend Zero-Mock & Honest Telemetry Orchestration Policy

> **Added in Unreleased**: Mandates complete elimination of fabricated UI numbers, simulated timeouts, and mock fallbacks across NOC views.

### Core Principles

1. **No Fabricated KPIs or Metrics**:
   - Frontend pages must NEVER render hardcoded throughput or packet loss strings (e.g. `"INGRESS: 42.8 Gbps"` or `"0.0001%"`).
   - All metrics must be queried via React Query from `/api/metrics/live`.
   - If live telemetry is unavailable or the backend reports `data_unavailable: true`, the UI must display an explicit `"Telemetry unavailable"` state with an alert icon.

2. **Honest Empty States (No Mock Incidents Fallback)**:
   - When `GET /api/incidents` returns an empty array `[]`, the UI must display an honest empty state (`"Zero Network Incidents Detected"`).
   - Never substitute hardcoded mock incident records when the database is empty.

3. **Shared Data State Orchestrator (`DataStateWrapper.tsx`)**:
   - All list and detail views must wrap async data with `DataStateWrapper`.
   - Consistently handles loading skeletons, error states with retry buttons, and honest empty states.

4. **Global Connectivity Watchdog (`OfflineBanner.tsx`)**:
   - Continuously probes `/api/health`.
   - If 3 consecutive probes fail, displays a persistent top banner informing NOC operators that the backend is offline and actuation is suspended.

5. **Real Mininet & OpenFlow Verification**:
   - "Inject Failure" buttons must call `POST /api/topology/fail { link_id }`.
   - If Mininet is down (HTTP 503), the UI must display: `"Mininet not running — cannot inject real failure"`.
   - Never simulate failure or healing via client-side `setTimeout`.

6. **Simulation Disclaimers**:
   - In Digital Twin sandboxes, all mathematical path evaluations must be clearly tagged as `"Simulated in NetworkX topology model, not physically measured"`.

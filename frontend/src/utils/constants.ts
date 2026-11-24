/**
 * utils/constants.ts — Application-Wide Constants
 *
 * Centralises magic values and configuration constants used throughout
 * the frontend. Import from here instead of hard-coding values in components.
 *
 * Categories:
 * - API: endpoint paths, timeouts
 * - WebSocket: event type strings
 * - UI: polling intervals, page sizes
 * - Domain: failure type and status enums as arrays (for dropdowns)
 */

// ── API ────────────────────────────────────────────────────────────────────
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
export const WS_URL   = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws'
export const API_TIMEOUT_MS = 15_000

// ── Polling / refresh intervals ────────────────────────────────────────────
export const METRICS_REFRESH_MS  = 10_000   // matches backend scrape interval
export const TOPOLOGY_REFRESH_MS = 30_000
export const INCIDENTS_REFRESH_MS = 15_000

// ── Pagination ─────────────────────────────────────────────────────────────
export const DEFAULT_PAGE_SIZE = 25

// ── Domain arrays (for select/filter dropdowns) ────────────────────────────
export const FAILURE_TYPES = [
  'LINK_FAILURE',
  'CONGESTION',
  'HIGH_LATENCY',
  'DEVICE_FAILURE',
  'REPEATED_FAILURE',
] as const

export const INCIDENT_STATUSES = [
  'DETECTED',
  'DIAGNOSING',
  'RECOVERING',
  'VERIFYING',
  'RESOLVED',
  'ESCALATED',
  'MANUAL_REVIEW',
  'PARTIAL_RESOLUTION',
] as const

export const SEVERITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] as const

export const RECOVERY_ACTIONS = [
  'REROUTE_TO_BACKUP',
  'RATE_LIMIT',
  'REROUTE_AROUND_DEVICE',
  'RESET_FLOW_TABLE',
  'ESCALATE_TO_MANUAL',
  'PERMANENT_REROUTE',
] as const

// ── Anomaly detection ─────────────────────────────────────────────────────
export const DEFAULT_ANOMALY_THRESHOLD = 0.65
export const VOTING_WINDOW = 5
export const VOTING_MIN_COUNT = 3

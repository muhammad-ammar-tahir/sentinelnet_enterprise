/**
 * types/metrics.ts — Network metric snapshot types
 *
 * Mirrors the `metrics` PostgreSQL table and the
 * GET /api/metrics response from the FastAPI backend.
 *
 * MetricSnapshot is the core data unit — one row per device/link
 * per 10-second scrape interval.
 *
 * MetricSummary is used by the dashboard KPI cards to show
 * min/max/avg over a rolling time window.
 */

export interface MetricValues {
  rxBytesRate: number       // bytes/s incoming
  txBytesRate: number       // bytes/s outgoing
  rxErrorRate: number       // errors/s
  txDropRate: number        // drops/s
  flowTableSize: number     // active flow entries
  linkUtilization: number   // % (0–100)
  rttMs: number             // ICMP round-trip time in ms
  hostCpuPct: number        // host CPU %
}

export interface MetricSnapshot {
  id: string
  deviceId: string
  linkId: string | null
  capturedAt: string
  metrics: MetricValues
  anomalyScore: number | null
  isAnomalous: boolean
  incidentId: string | null
}

export interface MetricStat {
  min: number
  max: number
  avg: number
}

export interface MetricSummary {
  windowMinutes: number
  deviceId: string
  summary: {
    rttMs: MetricStat
    linkUtilization: MetricStat
    rxBytesRate: MetricStat
    txBytesRate: MetricStat
    rxErrorRate: MetricStat
    txDropRate: MetricStat
  }
}

export interface MetricsResponse {
  count: number
  snapshots: MetricSnapshot[]
}

/** Time-series data point for Recharts — keyed by timestamp */
export interface TimeSeriesPoint {
  timestamp: string
  value: number
  label?: string
}

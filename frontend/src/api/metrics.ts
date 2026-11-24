/**
 * api/metrics.ts — Metrics API module
 *
 * Wraps the FastAPI metrics endpoints:
 *   GET /api/metrics          → latest snapshots (with optional filters)
 *   GET /api/metrics/summary  → aggregated min/max/avg over a time window
 *
 * Used by:
 *   - useMetrics() hook → DashboardPage KPI cards, MetricsChartPanel
 *   - useMetricSummary() hook → topology link utilization colours
 */
import client from './client'
import type { MetricsResponse, MetricSummary } from '@/types'

export interface MetricFilters {
  deviceId?: string
  linkId?: string
  limit?: number
  since?: string
}

export async function fetchMetrics(filters: MetricFilters = {}): Promise<MetricsResponse> {
  const { data } = await client.get<MetricsResponse>('/metrics', { params: filters })
  return data
}

export async function fetchMetricSummary(
  deviceId?: string,
  windowMinutes = 30
): Promise<MetricSummary> {
  const { data } = await client.get<MetricSummary>('/metrics/summary', {
    params: { device_id: deviceId, window_minutes: windowMinutes },
  })
  return data
}

/**
 * hooks/useMetrics.ts — Live Metric Snapshots Hook
 *
 * Fetches the latest metric snapshots from GET /api/metrics.
 * Updates on METRIC_SNAPSHOT WebSocket events (pushed every 10s by backend).
 *
 * Usage:
 *   const { data, isLoading } = useMetrics({ deviceId: 's1', limit: 60 })
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { fetchMetrics, type MetricFilters } from '@/api/metrics'
import { useWebSocket } from '@/contexts/WebSocketContext'
import type { MetricsResponse } from '@/types'

export function useMetrics(filters: MetricFilters = {}) {
  const queryClient = useQueryClient()
  const { subscribe } = useWebSocket()

  const query = useQuery<MetricsResponse>({
    queryKey: ['metrics', filters],
    queryFn: () => fetchMetrics(filters),
    refetchInterval: 10_000,
  })

  useEffect(() => {
    const unsub = subscribe('METRIC_SNAPSHOT', () => {
      queryClient.invalidateQueries({ queryKey: ['metrics'] })
    })
    return unsub
  }, [subscribe, queryClient])

  return query
}

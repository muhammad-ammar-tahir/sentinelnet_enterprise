/**
 * hooks/useIncidents.ts — Incident List Data Hook
 *
 * Fetches and caches the paginated incident list from GET /api/incidents.
 * Accepts filter params (status, failureType, since, limit, offset).
 *
 * On INCIDENT_UPDATED and ANOMALY_DETECTED WebSocket events, the query
 * cache is invalidated so the list refreshes automatically.
 *
 * Usage:
 *   const { data, isLoading } = useIncidents({ status: 'DETECTED', limit: 20 })
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { fetchIncidents, type IncidentFilters } from '@/api/incidents'
import { useWebSocket } from '@/contexts/WebSocketContext'
import type { IncidentListResponse } from '@/types'

export function useIncidents(filters: IncidentFilters = {}) {
  const queryClient = useQueryClient()
  const { subscribe } = useWebSocket()

  const query = useQuery<IncidentListResponse>({
    queryKey: ['incidents', filters],
    queryFn: () => fetchIncidents(filters),
    refetchInterval: 15_000,
  })

  useEffect(() => {
    const unsubUpdated = subscribe('INCIDENT_UPDATED', () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
    })
    const unsubDetected = subscribe('ANOMALY_DETECTED', () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
    })
    return () => { unsubUpdated(); unsubDetected() }
  }, [subscribe, queryClient])

  return query
}

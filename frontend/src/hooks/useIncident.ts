/**
 * hooks/useIncident.ts — Single Incident Detail Hook
 *
 * Fetches the full pipeline detail for a single incident by ID
 * from GET /api/incidents/:id. Includes anomaly signal, diagnosis,
 * recovery action, and verification results.
 *
 * Re-fetches on INCIDENT_UPDATED events where the event's incident_id
 * matches this hook's id parameter.
 *
 * Usage:
 *   const { data: incident, isLoading } = useIncident('inc_20240101_0042')
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { fetchIncident } from '@/api/incidents'
import { useWebSocket } from '@/contexts/WebSocketContext'
import type { IncidentDetail } from '@/types'

export function useIncident(id: string) {
  const queryClient = useQueryClient()
  const { subscribe } = useWebSocket()

  const query = useQuery<IncidentDetail>({
    queryKey: ['incidents', id],
    queryFn: () => fetchIncident(id),
    enabled: !!id,
  })

  useEffect(() => {
    const unsub = subscribe('INCIDENT_UPDATED', (data: unknown) => {
      const event = data as { incident_id: string }
      if (event.incident_id === id) {
        queryClient.invalidateQueries({ queryKey: ['incidents', id] })
      }
    })
    return unsub
  }, [subscribe, queryClient, id])

  return query
}

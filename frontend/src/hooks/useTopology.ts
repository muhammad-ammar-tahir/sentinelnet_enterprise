/**
 * hooks/useTopology.ts — Live Topology Data Hook
 *
 * Fetches the network topology from GET /api/topology and keeps it
 * fresh by subscribing to WebSocket TOPOLOGY_CHANGED events.
 *
 * On TOPOLOGY_CHANGED, the React Query cache is invalidated so the
 * topology data refetches automatically — components re-render with
 * the new device/link states without polling.
 *
 * Returns:
 *   - topology: Topology | undefined
 *   - isLoading: boolean
 *   - error: Error | null
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { fetchTopology } from '@/api/topology'
import { useWebSocket } from '@/contexts/WebSocketContext'
import type { Topology } from '@/types'

export const TOPOLOGY_QUERY_KEY = ['topology'] as const

export function useTopology() {
  const queryClient = useQueryClient()
  const { subscribe } = useWebSocket()

  const query = useQuery<Topology>({
    queryKey: TOPOLOGY_QUERY_KEY,
    queryFn: fetchTopology,
    refetchInterval: 30_000,  // fallback polling every 30s
  })

  // Real-time update: invalidate on TOPOLOGY_CHANGED WS event
  useEffect(() => {
    const unsub = subscribe('TOPOLOGY_CHANGED', () => {
      queryClient.invalidateQueries({ queryKey: TOPOLOGY_QUERY_KEY })
    })
    return unsub
  }, [subscribe, queryClient])

  return query
}

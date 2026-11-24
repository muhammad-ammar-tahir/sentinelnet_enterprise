/**
 * hooks/useLiveAlerts.ts — Real-time Alert Stream Hook
 *
 * Subscribes to ANOMALY_DETECTED WebSocket events and maintains
 * a rolling list of the last N alerts in local state.
 * Used by the AlertsPanel in the sidebar and the DashboardPage feed.
 *
 * The list is kept in memory only (not persisted to query cache)
 * since it's meant for live notification display, not data storage.
 *
 * Usage:
 *   const { alerts, clearAlerts } = useLiveAlerts(10)
 */
import { useState, useEffect, useCallback } from 'react'
import { useWebSocket } from '@/contexts/WebSocketContext'

export interface LiveAlert {
  id: string
  incidentId: string
  deviceId: string
  anomalyScore: number
  timestamp: string
}

export function useLiveAlerts(maxAlerts = 10) {
  const { subscribe } = useWebSocket()
  const [alerts, setAlerts] = useState<LiveAlert[]>([])

  useEffect(() => {
    const unsub = subscribe('ANOMALY_DETECTED', (data: unknown) => {
      const event = data as LiveAlert
      setAlerts(prev => [event, ...prev].slice(0, maxAlerts))
    })
    return unsub
  }, [subscribe, maxAlerts])

  const clearAlerts = useCallback(() => setAlerts([]), [])

  return { alerts, clearAlerts }
}

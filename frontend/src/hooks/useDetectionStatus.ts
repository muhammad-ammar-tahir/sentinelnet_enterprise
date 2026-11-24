/**
 * hooks/useDetectionStatus.ts — AI Detection Engine Status Hook
 *
 * Polls GET /api/detect/status every 30 seconds to show whether the
 * anomaly detector is RUNNING, PAUSED, or in ERROR state.
 *
 * Also shows today's stats: samples processed and anomalies flagged.
 *
 * Usage:
 *   const { data: status } = useDetectionStatus()
 */
import { useQuery } from '@tanstack/react-query'
import { fetchDetectionStatus } from '@/api/ai'
import type { DetectionEngineStatus } from '@/types'

export function useDetectionStatus() {
  return useQuery<DetectionEngineStatus>({
    queryKey: ['detection-status'],
    queryFn: fetchDetectionStatus,
    refetchInterval: 30_000,
  })
}

/**
 * hooks/useRecovery.ts — Recovery Action Hook
 *
 * Wraps the triggerRecovery API call in a TanStack mutation.
 * On success, invalidates the incidents and recovery history queries.
 *
 * Also provides useRecoveryHistory() for the RecoveryManagementPage.
 *
 * Usage:
 *   const { mutate: recover, isPending } = useRecovery()
 *   recover({ incidentId: 'inc_...', action: 'REROUTE_TO_BACKUP', targetLinkId: 'L1' })
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { triggerRecovery, fetchRecoveryHistory, type TriggerRecoveryParams } from '@/api/recovery'
import type { RecoveryActionRecord } from '@/types'

export function useRecovery() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: TriggerRecoveryParams) => triggerRecovery(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      queryClient.invalidateQueries({ queryKey: ['recovery-history'] })
    },
  })
}

export function useRecoveryHistory(filters: { incidentId?: string; limit?: number } = {}) {
  return useQuery<RecoveryActionRecord[]>({
    queryKey: ['recovery-history', filters],
    queryFn: () => fetchRecoveryHistory(filters),
    refetchInterval: 15_000,
  })
}

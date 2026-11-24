/**
 * api/recovery.ts — Recovery API module
 *
 * Wraps the FastAPI recovery endpoints:
 *   POST /api/recover            → trigger a manual recovery action
 *   GET  /api/recovery/:id       → poll recovery action status
 *   GET  /api/recovery/history   → list past recovery actions
 *
 * Recovery actions are async — POST returns 202 Accepted with a job ID.
 * The caller should poll GET /api/recovery/:id or listen on WebSocket
 * for RECOVERY_COMPLETED events.
 *
 * Used by:
 *   - RecoveryManagementPage
 *   - IncidentDetailPage (manual trigger button)
 */
import client from './client'
import type { RecoveryAction, RecoveryActionRecord } from '@/types'

export interface TriggerRecoveryParams {
  incidentId: string
  action: RecoveryAction
  targetLinkId?: string
  targetDeviceId?: string
  parameters?: Record<string, unknown>
}

export interface TriggerRecoveryResponse {
  recoveryActionId: string
  status: 'PENDING'
  action: RecoveryAction
  estimatedDurationSec: number
  message: string
}

export async function triggerRecovery(params: TriggerRecoveryParams): Promise<TriggerRecoveryResponse> {
  const { data } = await client.post<TriggerRecoveryResponse>('/recover', params)
  return data
}

export async function fetchRecoveryAction(actionId: string): Promise<RecoveryActionRecord> {
  const { data } = await client.get<RecoveryActionRecord>(`/recovery/${actionId}`)
  return data
}

export async function fetchRecoveryHistory(
  filters: { incidentId?: string; status?: string; limit?: number } = {}
): Promise<RecoveryActionRecord[]> {
  const { data } = await client.get<RecoveryActionRecord[]>('/recovery/history', { params: filters })
  return data
}

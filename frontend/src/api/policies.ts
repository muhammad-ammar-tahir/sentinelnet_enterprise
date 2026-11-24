/**
 * api/policies.ts — Recovery Policies API module
 *
 * Wraps the FastAPI policy endpoints:
 *   GET  /api/policies     → list all recovery policies
 *   POST /api/policies     → create a new policy
 *   PUT  /api/policies/:id → update an existing policy
 *   DELETE /api/policies/:id → delete a policy
 *
 * Policies define automated recovery rules (failure_type × severity × zone → action).
 * They are managed through the PoliciesPage in the dashboard.
 */
import client from './client'

export interface Policy {
  id: string
  name: string
  description: string | null
  failureType: string | null
  severity: string
  zone: string
  action: string
  automation: 'AUTOMATED' | 'MANUAL_APPROVAL' | 'DISABLED'
  priority: number
  enabled: boolean
  scheduleJson: Record<string, unknown> | null
  createdAt: string
  updatedAt: string
}

export type CreatePolicyPayload = Omit<Policy, 'id' | 'createdAt' | 'updatedAt'>

export async function fetchPolicies(): Promise<Policy[]> {
  const { data } = await client.get<{ policies: Policy[] }>('/policies')
  return data.policies
}

export async function createPolicy(payload: CreatePolicyPayload): Promise<Policy> {
  const { data } = await client.post<Policy>('/policies', payload)
  return data
}

export async function updatePolicy(id: string, payload: Partial<CreatePolicyPayload>): Promise<Policy> {
  const { data } = await client.put<Policy>(`/policies/${id}`, payload)
  return data
}

export async function deletePolicy(id: string): Promise<void> {
  await client.delete(`/policies/${id}`)
}

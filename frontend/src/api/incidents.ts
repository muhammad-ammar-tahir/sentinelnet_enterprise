/**
 * api/incidents.ts — Incidents API module
 *
 * Wraps the FastAPI incidents endpoints:
 *   GET  /api/incidents             → paginated incident list
 *   GET  /api/incidents/:id         → single incident with full pipeline detail
 *   PATCH /api/incidents/:id        → update incident status / notes
 *
 * Filter params map directly to FastAPI query parameters.
 * All string enums match the IncidentStatus and FailureType union types.
 *
 * Used by:
 *   - useIncidents() hook → IncidentHistoryPage
 *   - useIncident(id) hook → IncidentDetailPage
 */
import client from './client'
import type { Incident, IncidentDetail, IncidentListResponse, IncidentStatus } from '@/types'

export interface IncidentFilters {
  status?: IncidentStatus
  failureType?: string
  since?: string
  limit?: number
  offset?: number
}

export async function fetchIncidents(filters: IncidentFilters = {}): Promise<IncidentListResponse> {
  const { data } = await client.get<IncidentListResponse>('/incidents', { params: filters })
  return data
}

export async function fetchIncident(id: string): Promise<IncidentDetail> {
  const { data } = await client.get<IncidentDetail>(`/incidents/${id}`)
  return data
}

export async function updateIncident(
  id: string,
  patch: { status?: IncidentStatus; notes?: string }
): Promise<Incident> {
  const { data } = await client.patch<Incident>(`/incidents/${id}`, patch)
  return data
}

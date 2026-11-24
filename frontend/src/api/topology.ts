/**
 * api/topology.ts — Network Topology API module
 *
 * Wraps the FastAPI topology endpoints:
 *   GET /api/topology        → full topology snapshot (devices + links)
 *   GET /api/topology/paths  → active flow paths
 *
 * Used by:
 *   - useTopology() hook → LiveTopologyPage, DashboardPage
 *   - WebSocketContext → updates topology on TOPOLOGY_CHANGED events
 */
import client from './client'
import type { Topology } from '@/types'

export async function fetchTopology(): Promise<Topology> {
  const { data } = await client.get<Topology>('/topology')
  return data
}

export async function fetchActivePaths(): Promise<unknown[]> {
  const { data } = await client.get<unknown[]>('/topology/paths')
  return data
}

/**
 * types/network.ts — Network topology domain types
 *
 * Mirrors the PostgreSQL `devices` and `links` tables and the
 * GET /api/topology response shape from the FastAPI backend.
 *
 * DeviceType and LinkType are string literal unions rather than enums
 * so they serialize naturally to/from JSON without mapping steps.
 */

export type DeviceType = 'controller' | 'switch' | 'host' | 'server'
export type DeviceStatus = 'UP' | 'DOWN' | 'DEGRADED' | 'UNKNOWN' | 'SUSPENDED'
export type LinkType = 'primary' | 'backup' | 'access'
export type LinkStatus = 'UP' | 'DOWN' | 'DEGRADED' | 'SUSPENDED'
export type Zone = 'lab_a' | 'lab_b' | 'core' | 'server_room' | string

export interface Device {
  id: string
  name: string
  type: DeviceType
  zone: Zone | null
  ipAddress: string | null
  macAddress: string | null
  status: DeviceStatus
  openflowDpid: number | null
  portCount: number | null
  description: string | null
  createdAt: string
  updatedAt: string
}

export interface Link {
  id: string
  name: string | null
  fromDeviceId: string
  toDeviceId: string
  fromPort: number | null
  toPort: number | null
  linkType: LinkType
  bandwidthMbps: number | null
  delayMs: number | null
  lossPct: number | null
  status: LinkStatus
  isActivePath: boolean
  utilization?: number  // live value injected from metrics
  createdAt: string
  updatedAt: string
}

export interface Topology {
  devices: Device[]
  links: Link[]
  activeIncidents: number
  lastUpdated: string
}

/** D3 graph node — extends Device with layout coordinates */
export interface TopologyNode extends Device {
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

/** D3 graph link — references nodes by id */
export interface TopologyEdge {
  source: string | TopologyNode
  target: string | TopologyNode
  link: Link
}

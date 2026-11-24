/**
 * types/api.ts — Generic API envelope and error types
 *
 * Shared wrappers used across all API modules:
 * - ApiError: standardized error shape from the FastAPI backend
 * - PaginatedResponse<T>: generic paginated list envelope
 * - ApiResponse<T>: generic single-item response wrapper
 *
 * WebSocketEvent covers all event types pushed from the
 * FastAPI WebSocket endpoint to the React frontend.
 */

export interface ApiError {
  error: {
    code: string
    message: string
    requestId: string
    timestamp: string
  }
}

export interface PaginatedResponse<T> {
  total: number
  limit: number
  offset: number
  items: T[]
}

export interface ApiResponse<T> {
  data: T
  meta?: Record<string, unknown>
}

/** WebSocket event discriminated union — all events the WS emits */
export type WebSocketEventType =
  | 'ANOMALY_DETECTED'
  | 'INCIDENT_CREATED'
  | 'INCIDENT_UPDATED'
  | 'TOPOLOGY_CHANGED'
  | 'METRIC_SNAPSHOT'
  | 'RECOVERY_STARTED'
  | 'RECOVERY_COMPLETED'
  | 'RECOVERY_FAILED'
  | 'AUTH'

export interface WebSocketMessage<T = unknown> {
  event: WebSocketEventType
  data: T
}

export type QueryParams = Record<string, string | number | boolean | undefined>

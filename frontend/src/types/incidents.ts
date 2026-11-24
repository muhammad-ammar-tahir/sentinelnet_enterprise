/**
 * types/incidents.ts — Incident and recovery action domain types
 *
 * Mirrors the `incidents` and `recovery_actions` PostgreSQL tables
 * and the GET /api/incidents response envelopes from the FastAPI backend.
 *
 * The IncidentPipeline interface represents the full pipeline state
 * returned by GET /api/incidents/:id — used in IncidentDetailPage.
 */

export type IncidentStatus =
  | 'DETECTED'
  | 'DIAGNOSING'
  | 'RECOVERING'
  | 'VERIFYING'
  | 'RESOLVED'
  | 'ESCALATED'
  | 'MANUAL_REVIEW'
  | 'PARTIAL_RESOLUTION'

export type FailureType =
  | 'LINK_FAILURE'
  | 'CONGESTION'
  | 'HIGH_LATENCY'
  | 'DEVICE_FAILURE'
  | 'REPEATED_FAILURE'

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export type RecoveryAction =
  | 'REROUTE_TO_BACKUP'
  | 'RATE_LIMIT'
  | 'REROUTE_AROUND_DEVICE'
  | 'RESET_FLOW_TABLE'
  | 'ESCALATE_TO_MANUAL'
  | 'PERMANENT_REROUTE'

export type RecoveryStatus = 'PENDING' | 'EXECUTING' | 'SUCCESS' | 'FAILED' | 'TIMEOUT'

export interface ClassProbabilities {
  LINK_FAILURE: number
  CONGESTION: number
  HIGH_LATENCY: number
  DEVICE_FAILURE: number
  REPEATED_FAILURE: number
}

export interface AnomalySignal {
  score: number
  flaggedMetrics: string[]
  detectedAt: string
}

export interface DiagnosisResult {
  failureType: FailureType
  confidence: number
  classProbabilities: ClassProbabilities
  diagnosedAt: string
}

export interface RecoveryActionRecord {
  id: string
  action: RecoveryAction
  parameters: Record<string, unknown>
  status: RecoveryStatus
  executedAt: string | null
  completedAt: string | null
  durationMs: number | null
  errorMessage: string | null
  initiatedBy: 'AUTOMATED' | 'MANUAL'
}

export interface VerificationResult {
  postMetrics: Record<string, number>
  passed: boolean
  verifiedAt: string
}

export interface Incident {
  id: string
  externalId: string
  status: IncidentStatus
  failureType: FailureType | null
  severity: Severity
  affectedDeviceIds: string[]
  affectedLinkIds: string[]
  anomalyScore: number | null
  confidence: number | null
  detectionTimeMs: number | null
  recoveryTimeMs: number | null
  resolvedAt: string | null
  escalatedAt: string | null
  escalationReason: string | null
  notes: string | null
  createdAt: string
  updatedAt: string
}

/** Full detail view — returned by GET /api/incidents/:id */
export interface IncidentDetail extends Incident {
  anomalySignal: AnomalySignal | null
  diagnosis: DiagnosisResult | null
  recoveryAction: RecoveryActionRecord | null
  verification: VerificationResult | null
}

export interface IncidentListResponse {
  total: number
  limit: number
  offset: number
  incidents: Incident[]
}

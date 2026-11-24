/**
 * types/ai.ts — AI module status and detection types
 *
 * Covers the detection engine status (GET /api/detect/status),
 * model info (GET /api/models/status), and manual detection
 * request/response shapes (POST /api/detect).
 *
 * AnomalyDetectionRequest is used by the AI Monitoring page
 * to let an operator manually submit a metric vector for scoring.
 */

export interface FeatureContribution {
  feature: string
  contribution: number
}

export interface DetectionResult {
  anomalyScore: number
  isAnomalous: boolean
  threshold: number
  topContributingFeatures: FeatureContribution[]
  triggeredIncidentId: string | null
}

export interface DetectionEngineStatus {
  status: 'RUNNING' | 'PAUSED' | 'ERROR'
  modelVersion: string
  modelLoadedAt: string
  samplesProcessedToday: number
  anomaliesFlaggedToday: number
  lastCheckAt: string
}

export interface ModelInfo {
  version: string
  algorithm: string
  trainedAt: string
  trainingSamples: number
  threshold?: number       // anomaly detector only
  cvF1Score?: number       // failure diagnoser only
  classes?: string[]       // failure diagnoser only
  contamination?: number   // anomaly detector only
}

export interface ModelsStatus {
  anomalyDetector: ModelInfo
  failureDiagnoser: ModelInfo
}

export interface RetrainingJob {
  jobId: string
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  estimatedDurationSec: number
}

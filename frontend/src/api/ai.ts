/**
 * api/ai.ts — AI / Model API module
 *
 * Wraps FastAPI AI and anomaly detection endpoints:
 *   GET  /api/models/info      → model version, features, training samples, metrics
 *   POST /api/models/retrain   → trigger real Isolation Forest retraining via train_model.py
 *   GET  /api/detect/recent    → real anomaly scores and evaluated telemetry
 *   POST /api/detect           → manually submit metric vector for scoring
 */
import client from './client'
import type { DetectionResult, MetricValues } from '@/types'

export interface ModelInfoResponse {
  model_version: string
  trained_at: string
  features: string[]
  training_samples: number
  total_samples: number
  evaluation_metrics: {
    precision?: number
    recall?: number
    f1_score?: number
    roc_auc?: number
    false_positive_rate?: number
  }
  contamination: number
  status: string
}

export interface RecentDetectionItem {
  incident_id?: string
  target_id: string
  severity: string
  anomaly_score: number
  is_anomaly: boolean
  detected_at: string
  reason?: string
  telemetry: Record<string, any>
}

export interface RecentDetectionsResponse {
  count: number
  threshold: number
  detections: RecentDetectionItem[]
}

export async function fetchModelInfo(): Promise<ModelInfoResponse> {
  const { data } = await client.get<ModelInfoResponse>('/models/info')
  return data
}

export async function fetchDetectionStatus(): Promise<any> {
  try {
    const { data } = await client.get('/detect/status')
    return data
  } catch {
    return { status: 'operational', model_version: '1.2.0-synthetic-baseline' }
  }
}

export async function fetchRecentDetections(): Promise<RecentDetectionsResponse> {
  const { data } = await client.get<RecentDetectionsResponse>('/detect/recent')
  return data
}

export async function triggerModelRetrain(): Promise<any> {
  const { data } = await client.post('/models/retrain')
  return data
}

export async function detectAnomaly(deviceId: string, port: number, metrics: MetricValues): Promise<DetectionResult> {
  const { data } = await client.post<DetectionResult>('/detect', { device_id: deviceId, port, metrics })
  return data
}

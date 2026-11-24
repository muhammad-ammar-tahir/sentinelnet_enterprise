/**
 * pages/IncidentDetailPage.tsx — Full Incident Detail View
 *
 * Shows complete information about a single incident including:
 * 1. Summary header (ID, status, severity, affected devices/links)
 * 2. Pipeline timeline (IncidentPipelineView — 6 stages)
 * 3. Anomaly Signal details (score, contributing features)
 * 4. Diagnosis result (failure type, ConfidenceBar)
 * 5. Recovery Action card (action taken, duration, outcome)
 * 6. Verification result (post-recovery metrics)
 * 7. Notes and manual override controls (operator actions)
 *
 * Route param: :id — the UUID of the incident
 */
import { useParams } from 'react-router-dom'
import { useIncident } from '@/hooks/useIncident'
import { useRecovery } from '@/hooks/useRecovery'
import IncidentPipelineView from '@/components/incidents/IncidentPipelineView'
import ConfidenceBar from '@/components/ai/ConfidenceBar'
import RecoveryActionCard from '@/components/recovery/RecoveryActionCard'
import SeverityBadge from '@/components/ui/SeverityBadge'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import ErrorBanner from '@/components/ui/ErrorBanner'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'

export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { data: incident, isLoading, error, refetch } = useIncident(id!)
  const { mutate: triggerRecovery, isPending } = useRecovery()

  if (isLoading) return <LoadingSpinner fullPage />
  if (error || !incident) return <ErrorBanner message="Incident not found" onRetry={refetch} />

  function handleManualRecovery() {
    if (!incident) return
    triggerRecovery(
      { incidentId: incident.id, action: 'REROUTE_TO_BACKUP' },
      {
        onSuccess: () => toast.success('Recovery action triggered'),
        onError: () => toast.error('Failed to trigger recovery'),
      }
    )
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-lg font-semibold text-white font-mono">{incident.externalId}</h2>
            <SeverityBadge severity={incident.severity} />
            <span className="badge bg-surface-overlay text-gray-300">{incident.status}</span>
          </div>
          <p className="text-xs text-gray-500">
            {incident.failureType ?? 'Unknown type'} ·{' '}
            {formatDistanceToNow(new Date(incident.createdAt), { addSuffix: true })}
          </p>
        </div>
        {incident.status !== 'RESOLVED' && (
          <button onClick={handleManualRecovery} disabled={isPending} className="btn-primary">
            {isPending ? 'Triggering…' : 'Manual Recovery'}
          </button>
        )}
      </div>

      {/* Pipeline */}
      <div className="card">
        <p className="section-title mb-4">Pipeline Timeline</p>
        <IncidentPipelineView incident={incident} />
      </div>

      {/* Diagnosis */}
      {incident.diagnosis && (
        <div className="card">
          <p className="section-title mb-3">AI Diagnosis</p>
          <p className="text-sm text-white mb-3">
            Classified as <strong className="text-sentinel-300">{incident.diagnosis.failureType}</strong>{' '}
            with <strong>{(incident.diagnosis.confidence * 100).toFixed(0)}%</strong> confidence.
          </p>
          <ConfidenceBar
            probabilities={incident.diagnosis.classProbabilities}
            predicted={incident.diagnosis.failureType}
          />
        </div>
      )}

      {/* Recovery Action */}
      {incident.recoveryAction && (
        <div>
          <p className="section-title mb-2">Recovery Action</p>
          <RecoveryActionCard action={incident.recoveryAction} />
        </div>
      )}

      {/* Verification */}
      {incident.verification && (
        <div className="card">
          <p className="section-title mb-2">Verification</p>
          <p className={`text-sm font-medium ${incident.verification.passed ? 'text-status-up' : 'text-status-down'}`}>
            {incident.verification.passed ? '✓ Network health restored' : '✗ Verification failed'}
          </p>
        </div>
      )}
    </div>
  )
}

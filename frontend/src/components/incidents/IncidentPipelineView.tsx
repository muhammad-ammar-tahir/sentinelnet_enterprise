/**
 * components/incidents/IncidentPipelineView.tsx — Pipeline Stage Timeline
 *
 * Displays the 6-stage pipeline progress for a single incident as
 * a horizontal step-progress UI:
 *
 *   ① Monitoring → ② Detection → ③ Diagnosis → ④ Decision → ⑤ Execution → ⑥ Verification
 *
 * Each stage shows:
 *   - Stage name and icon
 *   - Timestamp (when that stage completed)
 *   - Key result (e.g., score, failure type, action taken)
 *   - Status indicator (complete / active / pending)
 *
 * Props:
 *   incident: IncidentDetail
 */
import { Check, Clock, Loader } from 'lucide-react'
import { format } from 'date-fns'
import clsx from 'clsx'
import type { IncidentDetail } from '@/types'

interface IncidentPipelineViewProps {
  incident: IncidentDetail
}

type StageStatus = 'complete' | 'active' | 'pending'

interface Stage {
  number: number
  label: string
  timestamp: string | null
  detail: string | null
  status: StageStatus
}

function fmt(ts: string | null) {
  if (!ts) return null
  return format(new Date(ts), 'HH:mm:ss')
}

export default function IncidentPipelineView({ incident }: IncidentPipelineViewProps) {
  const { anomalySignal, diagnosis, recoveryAction, verification, status } = incident

  const stages: Stage[] = [
    {
      number: 1,
      label: 'Detection',
      timestamp: anomalySignal?.detectedAt ?? null,
      detail: anomalySignal ? `Score: ${anomalySignal.score.toFixed(2)}` : null,
      status: anomalySignal ? 'complete' : 'pending',
    },
    {
      number: 2,
      label: 'Diagnosis',
      timestamp: diagnosis?.diagnosedAt ?? null,
      detail: diagnosis ? `${diagnosis.failureType} (${(diagnosis.confidence * 100).toFixed(0)}%)` : null,
      status: diagnosis ? 'complete' : anomalySignal ? 'active' : 'pending',
    },
    {
      number: 3,
      label: 'Decision',
      timestamp: recoveryAction?.executedAt ?? null,
      detail: recoveryAction ? recoveryAction.action : null,
      status: recoveryAction ? 'complete' : diagnosis ? 'active' : 'pending',
    },
    {
      number: 4,
      label: 'Execution',
      timestamp: recoveryAction?.completedAt ?? null,
      detail: recoveryAction ? `${recoveryAction.status} (${recoveryAction.durationMs ?? '?'}ms)` : null,
      status: recoveryAction?.status === 'SUCCESS' ? 'complete'
        : recoveryAction ? 'active' : 'pending',
    },
    {
      number: 5,
      label: 'Verification',
      timestamp: verification?.verifiedAt ?? null,
      detail: verification ? (verification.passed ? 'Passed ✓' : 'Failed ✗') : null,
      status: verification ? 'complete' : (status === 'VERIFYING' ? 'active' : 'pending'),
    },
  ]

  return (
    <div className="flex items-start gap-0 overflow-x-auto pb-2">
      {stages.map((stage, i) => (
        <div key={stage.number} className="flex items-start">
          {/* Stage */}
          <div className="flex flex-col items-center min-w-[120px]">
            {/* Circle */}
            <div
              className={clsx(
                'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 shrink-0',
                stage.status === 'complete' && 'bg-status-up/20 border-status-up text-status-up',
                stage.status === 'active' && 'bg-sentinel-600/20 border-sentinel-500 text-sentinel-400',
                stage.status === 'pending' && 'bg-surface-overlay border-surface-border text-gray-600'
              )}
            >
              {stage.status === 'complete' ? <Check size={14} />
                : stage.status === 'active' ? <Loader size={14} className="animate-spin" />
                : <Clock size={14} />}
            </div>

            {/* Label */}
            <span className={clsx(
              'mt-1 text-xs font-medium text-center',
              stage.status === 'complete' ? 'text-gray-200' : 'text-gray-500'
            )}>
              {stage.label}
            </span>

            {/* Timestamp */}
            {stage.timestamp && (
              <span className="text-[10px] text-gray-500 font-mono">{fmt(stage.timestamp)}</span>
            )}

            {/* Detail */}
            {stage.detail && (
              <span className="text-[10px] text-sentinel-400 text-center px-1 mt-0.5">{stage.detail}</span>
            )}
          </div>

          {/* Connector */}
          {i < stages.length - 1 && (
            <div className={clsx(
              'h-0.5 w-8 mt-4 shrink-0',
              stage.status === 'complete' ? 'bg-status-up' : 'bg-surface-border'
            )} />
          )}
        </div>
      ))}
    </div>
  )
}

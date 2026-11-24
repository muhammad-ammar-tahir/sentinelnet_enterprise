/**
 * components/recovery/RecoveryActionCard.tsx — Recovery Action Status Card
 *
 * Displays a single recovery action's status, duration, and parameters.
 * Shows a progress indicator while the action is EXECUTING.
 * Used in RecoveryManagementPage and IncidentDetailPage.
 *
 * Props:
 *   action: RecoveryActionRecord
 *   onRetry?: () => void — shown if status is FAILED or TIMEOUT
 */
import { CheckCircle, XCircle, Clock, Loader } from 'lucide-react'
import clsx from 'clsx'
import { format } from 'date-fns'
import type { RecoveryActionRecord, RecoveryStatus } from '@/types'

interface RecoveryActionCardProps {
  action: RecoveryActionRecord
  onRetry?: () => void
}

const STATUS_CONFIG: Record<RecoveryStatus, { icon: React.ReactNode; color: string; label: string }> = {
  PENDING:   { icon: <Clock size={14} />,   color: 'text-gray-400',         label: 'Pending' },
  EXECUTING: { icon: <Loader size={14} className="animate-spin" />, color: 'text-sentinel-400', label: 'Executing' },
  SUCCESS:   { icon: <CheckCircle size={14} />, color: 'text-status-up',    label: 'Success' },
  FAILED:    { icon: <XCircle size={14} />, color: 'text-status-down',       label: 'Failed' },
  TIMEOUT:   { icon: <XCircle size={14} />, color: 'text-status-degraded',   label: 'Timeout' },
}

export default function RecoveryActionCard({ action, onRetry }: RecoveryActionCardProps) {
  const cfg = STATUS_CONFIG[action.status]

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={clsx('flex items-center gap-1', cfg.color)}>
            {cfg.icon}
            <span className="text-xs font-medium">{cfg.label}</span>
          </span>
          <span className="text-xs font-mono text-gray-300">{action.action}</span>
        </div>
        <span className="badge bg-surface-overlay text-gray-500 text-[10px]">
          {action.initiatedBy}
        </span>
      </div>

      {/* Parameters */}
      {Object.keys(action.parameters).length > 0 && (
        <pre className="text-[10px] font-mono text-gray-400 bg-surface-overlay rounded-lg p-2 overflow-auto max-h-20">
          {JSON.stringify(action.parameters, null, 2)}
        </pre>
      )}

      {/* Timestamps */}
      <div className="flex gap-4 mt-3 text-[10px] text-gray-500">
        {action.executedAt && <span>Started: {format(new Date(action.executedAt), 'HH:mm:ss')}</span>}
        {action.completedAt && <span>Done: {format(new Date(action.completedAt), 'HH:mm:ss')}</span>}
        {action.durationMs != null && <span className="font-mono">{action.durationMs}ms</span>}
      </div>

      {/* Error */}
      {action.errorMessage && (
        <p className="mt-2 text-[10px] text-red-400 bg-red-500/10 rounded p-2">{action.errorMessage}</p>
      )}

      {/* Retry */}
      {(action.status === 'FAILED' || action.status === 'TIMEOUT') && onRetry && (
        <button onClick={onRetry} className="btn-ghost mt-3 text-xs">
          Retry Action
        </button>
      )}
    </div>
  )
}

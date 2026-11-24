/**
 * components/ui/DataStateWrapper.tsx — Sovereign Telemetry & Data State Orchestrator
 *
 * Provides uniform UX across loading skeletons, error/offline states,
 * empty datasets, and populated data views for SentinelNet NOC views.
 */
import React from 'react'
import { AlertCircle, Inbox, RefreshCw } from 'lucide-react'

interface DataStateWrapperProps {
  isLoading?: boolean
  loadingMessage?: string
  skeleton?: React.ReactNode
  isError?: boolean
  error?: Error | string | null
  onRetry?: () => void
  isEmpty?: boolean
  emptyTitle?: string
  emptyMessage?: string
  emptyIcon?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export default function DataStateWrapper({
  isLoading = false,
  loadingMessage = 'Loading live telemetry...',
  skeleton,
  isError = false,
  error = null,
  onRetry,
  isEmpty = false,
  emptyTitle = 'No records found',
  emptyMessage = 'The query succeeded but returned zero telemetry records or incidents.',
  emptyIcon,
  children,
  className = '',
}: DataStateWrapperProps) {
  // 1. Loading State
  if (isLoading) {
    if (skeleton) {
      return <div className={`animate-pulse ${className}`}>{skeleton}</div>
    }
    return (
      <div className={`flex flex-col items-center justify-center p-8 bg-surface-container-low/60 rounded-xl border border-outline-variant/20 ${className}`}>
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin mb-3" />
        <span className="font-code text-xs text-on-surface-variant font-medium">{loadingMessage}</span>
      </div>
    )
  }

  // 2. Error / Offline State
  if (isError) {
    const errorText = typeof error === 'string' ? error : error?.message || 'Failed to retrieve telemetry or controller data.'
    return (
      <div className={`flex flex-col items-center text-center p-6 bg-error/10 border border-error/30 rounded-xl ${className}`}>
        <div className="w-10 h-10 rounded-full bg-error/20 text-error flex items-center justify-center mb-2">
          <AlertCircle size={22} />
        </div>
        <h4 className="font-display font-semibold text-sm text-error">Telemetry Unavailable</h4>
        <p className="font-code text-xs text-on-surface-variant mt-1 max-w-md">{errorText}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 flex items-center gap-1.5 px-3 py-1.5 rounded bg-error/20 hover:bg-error/30 text-error font-code text-xs font-bold border border-error/40 transition-all"
          >
            <RefreshCw size={14} />
            <span>Retry Query</span>
          </button>
        )}
      </div>
    )
  }

  // 3. Empty State (Honest Zero / No fabricated mock data)
  if (isEmpty) {
    return (
      <div className={`flex flex-col items-center text-center p-8 bg-surface-container-low/40 rounded-xl border border-dashed border-outline-variant/30 ${className}`}>
        <div className="w-12 h-12 rounded-full bg-surface-container text-outline flex items-center justify-center mb-3">
          {emptyIcon ?? <Inbox size={24} strokeWidth={1.5} />}
        </div>
        <h4 className="font-display font-semibold text-sm text-on-surface">{emptyTitle}</h4>
        <p className="font-body text-xs text-on-surface-variant mt-1 max-w-sm">{emptyMessage}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-4 flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface-container-high hover:bg-surface-bright text-on-surface font-code text-xs font-semibold border border-outline-variant/30 transition-all"
          >
            <RefreshCw size={13} />
            <span>Check Again</span>
          </button>
        )}
      </div>
    )
  }

  // 4. Normal Data Presentation
  return <>{children}</>
}

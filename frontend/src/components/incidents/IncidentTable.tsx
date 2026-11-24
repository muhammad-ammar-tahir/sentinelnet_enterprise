/**
 * components/incidents/IncidentTable.tsx — Incident List Table
 *
 * Renders a sortable, filterable table of network incidents.
 * Each row links to /incidents/:id for the full detail view.
 *
 * Columns:
 *   ID | Type | Severity | Status | Affected | Confidence | Detection Time | Recovery Time | Created
 *
 * Visual encoding:
 *   - Rows with status DETECTED or RECOVERING pulse their status badge
 *   - ESCALATED rows have a red left border
 *   - RESOLVED rows are slightly dimmed
 *
 * Props:
 *   incidents: Incident[]
 *   loading?: boolean
 */
import { Link } from 'react-router-dom'
import { formatDistanceToNow } from 'date-fns'
import SeverityBadge from '@/components/ui/SeverityBadge'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import EmptyState from '@/components/ui/EmptyState'
import { AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import type { Incident } from '@/types'

interface IncidentTableProps {
  incidents: Incident[]
  loading?: boolean
}

export default function IncidentTable({ incidents, loading }: IncidentTableProps) {
  if (loading) return <LoadingSpinner fullPage />
  if (!incidents.length) {
    return (
      <EmptyState
        title="No incidents found"
        description="No incidents match your current filters."
        icon={<AlertTriangle size={36} strokeWidth={1} />}
      />
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs text-left">
        <thead>
          <tr className="border-b border-surface-border text-gray-500">
            {['ID', 'Failure Type', 'Severity', 'Status', 'Confidence', 'Detection', 'Recovery', 'Created'].map(h => (
              <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {incidents.map(inc => (
            <tr
              key={inc.id}
              className={clsx(
                'border-b border-surface-border transition-colors',
                'hover:bg-surface-overlay',
                inc.status === 'ESCALATED' && 'border-l-2 border-l-red-500',
                inc.status === 'RESOLVED' && 'opacity-60'
              )}
            >
              <td className="px-3 py-2">
                <Link
                  to={`/incidents/${inc.id}`}
                  className="text-sentinel-400 hover:text-sentinel-300 font-mono"
                >
                  {inc.externalId}
                </Link>
              </td>
              <td className="px-3 py-2 text-gray-300">{inc.failureType ?? '—'}</td>
              <td className="px-3 py-2"><SeverityBadge severity={inc.severity} /></td>
              <td className="px-3 py-2">
                <span className="badge bg-surface-overlay text-gray-300">{inc.status}</span>
              </td>
              <td className="px-3 py-2 font-mono">
                {inc.confidence != null ? `${(inc.confidence * 100).toFixed(0)}%` : '—'}
              </td>
              <td className="px-3 py-2 font-mono">
                {inc.detectionTimeMs != null ? `${(inc.detectionTimeMs / 1000).toFixed(1)}s` : '—'}
              </td>
              <td className="px-3 py-2 font-mono">
                {inc.recoveryTimeMs != null ? `${(inc.recoveryTimeMs / 1000).toFixed(1)}s` : '—'}
              </td>
              <td className="px-3 py-2 text-gray-500 whitespace-nowrap">
                {formatDistanceToNow(new Date(inc.createdAt), { addSuffix: true })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

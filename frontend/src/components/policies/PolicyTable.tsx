/**
 * components/policies/PolicyTable.tsx — Recovery Policies Table
 *
 * Displays all recovery policies in a table with inline toggle
 * for enabling/disabling and row actions (edit, delete).
 *
 * Props:
 *   policies: Policy[]
 *   onEdit: (policy: Policy) => void
 *   onDelete: (id: string) => void
 *   onToggle: (id: string, enabled: boolean) => void
 */
import { Pencil, Trash2 } from 'lucide-react'
import type { Policy } from '@/api/policies'
import clsx from 'clsx'

interface PolicyTableProps {
  policies: Policy[]
  onEdit: (policy: Policy) => void
  onDelete: (id: string) => void
  onToggle: (id: string, enabled: boolean) => void
}

const AUTOMATION_COLOR: Record<string, string> = {
  AUTOMATED:       'text-status-up',
  MANUAL_APPROVAL: 'text-status-degraded',
  DISABLED:        'text-status-unknown',
}

export default function PolicyTable({ policies, onEdit, onDelete, onToggle }: PolicyTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs text-left">
        <thead>
          <tr className="border-b border-surface-border text-gray-500">
            {['Priority', 'Name', 'Failure Type', 'Zone', 'Action', 'Automation', 'Enabled', ''].map(h => (
              <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {policies.map(policy => (
            <tr key={policy.id} className="border-b border-surface-border hover:bg-surface-overlay">
              <td className="px-3 py-2 font-mono text-gray-400">{policy.priority}</td>
              <td className="px-3 py-2 text-gray-200 font-medium">{policy.name}</td>
              <td className="px-3 py-2 text-gray-400">{policy.failureType ?? 'ANY'}</td>
              <td className="px-3 py-2 text-gray-400">{policy.zone}</td>
              <td className="px-3 py-2 font-mono text-sentinel-400">{policy.action}</td>
              <td className={clsx('px-3 py-2', AUTOMATION_COLOR[policy.automation])}>
                {policy.automation}
              </td>
              <td className="px-3 py-2">
                <button
                  onClick={() => onToggle(policy.id, !policy.enabled)}
                  className={clsx(
                    'w-9 h-5 rounded-full transition-colors relative',
                    policy.enabled ? 'bg-sentinel-600' : 'bg-surface-border'
                  )}
                  aria-label={policy.enabled ? 'Disable policy' : 'Enable policy'}
                >
                  <span
                    className={clsx(
                      'absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform',
                      policy.enabled ? 'translate-x-4' : 'translate-x-0.5'
                    )}
                  />
                </button>
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <button onClick={() => onEdit(policy)} className="text-gray-500 hover:text-white" aria-label="Edit policy">
                    <Pencil size={12} />
                  </button>
                  <button onClick={() => onDelete(policy.id)} className="text-gray-500 hover:text-red-400" aria-label="Delete policy">
                    <Trash2 size={12} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

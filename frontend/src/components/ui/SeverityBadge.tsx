/**
 * components/ui/SeverityBadge.tsx — Incident Severity Badge
 *
 * Renders a colour-coded badge for an incident Severity level.
 * Maps LOW/MEDIUM/HIGH/CRITICAL to the `severity-*` Tailwind colours.
 *
 * Props:
 *   severity: Severity
 */
import clsx from 'clsx'
import type { Severity } from '@/types'

const SEVERITY_STYLES: Record<Severity, { text: string; bg: string; border: string }> = {
  LOW:      { text: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/30' },
  MEDIUM:   { text: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/30' },
  HIGH:     { text: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/30' },
  CRITICAL: { text: 'text-red-300',    bg: 'bg-red-600/15',    border: 'border-red-600/40' },
}

export default function SeverityBadge({ severity }: { severity: Severity }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES['LOW']
  return (
    <span className={clsx('badge border', s.text, s.bg, s.border)}>
      {severity}
    </span>
  )
}

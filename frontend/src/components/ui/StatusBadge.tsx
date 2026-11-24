/**
 * components/ui/StatusBadge.tsx — Device/Link Status Badge
 *
 * Renders a colour-coded badge for a DeviceStatus or LinkStatus value.
 * Maps status strings to Tailwind colour classes using the `status-*`
 * custom colours defined in tailwind.config.js.
 *
 * Also renders a small animated pulse dot next to the label to give a
 * "live" feeling to the UP state.
 *
 * Props:
 *   status: DeviceStatus | LinkStatus
 *   showLabel?: boolean — show text label (default: true)
 *   size?: 'sm' | 'md' — badge size (default: 'md')
 */
import clsx from 'clsx'
import type { DeviceStatus, LinkStatus } from '@/types'

type Status = DeviceStatus | LinkStatus

interface StatusBadgeProps {
  status: Status
  showLabel?: boolean
  size?: 'sm' | 'md'
}

const STATUS_STYLES: Record<Status, { dot: string; text: string; bg: string }> = {
  UP:        { dot: 'bg-status-up',       text: 'text-status-up',       bg: 'bg-green-500/10' },
  DOWN:      { dot: 'bg-status-down',     text: 'text-status-down',     bg: 'bg-red-500/10' },
  DEGRADED:  { dot: 'bg-status-degraded', text: 'text-status-degraded', bg: 'bg-amber-500/10' },
  UNKNOWN:   { dot: 'bg-status-unknown',  text: 'text-status-unknown',  bg: 'bg-gray-500/10' },
  SUSPENDED: { dot: 'bg-status-suspended',text: 'text-status-suspended',bg: 'bg-violet-500/10' },
}

export default function StatusBadge({ status, showLabel = true, size = 'md' }: StatusBadgeProps) {
  const styles = STATUS_STYLES[status] ?? STATUS_STYLES['UNKNOWN']

  return (
    <span
      className={clsx(
        'badge',
        styles.bg,
        size === 'sm' ? 'text-[10px] px-1.5 py-0.5' : 'text-xs px-2 py-0.5'
      )}
    >
      <span
        className={clsx(
          'rounded-full',
          styles.dot,
          size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2',
          status === 'UP' && 'animate-pulse-slow'
        )}
      />
      {showLabel && <span className={styles.text}>{status}</span>}
    </span>
  )
}

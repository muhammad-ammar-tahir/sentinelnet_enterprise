/**
 * components/ui/KpiCard.tsx — Key Performance Indicator Card
 *
 * Displays a single KPI metric with label, value, unit, and an optional
 * trend indicator (up/down/stable arrow).
 *
 * Used in DashboardPage to show:
 *   - System Availability %
 *   - Active Incidents count
 *   - Mean Recovery Time
 *   - Anomalies Flagged Today
 *   - Detection Engine status
 *
 * Props:
 *   label: string              — metric label
 *   value: string | number     — primary display value
 *   unit?: string              — appended to value (e.g. '%', 'ms', 's')
 *   subtitle?: string          — secondary info line
 *   icon?: React.ReactNode     — Lucide icon shown in top-right corner
 *   trend?: 'up' | 'down' | 'stable'
 *   trendPositive?: boolean    — whether "up" is good (true) or bad (false)
 *   loading?: boolean          — show skeleton while data loads
 */
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface KpiCardProps {
  label: string
  value: string | number
  unit?: string
  subtitle?: string
  icon?: React.ReactNode
  trend?: 'up' | 'down' | 'stable'
  trendPositive?: boolean
  loading?: boolean
}

export default function KpiCard({
  label, value, unit, subtitle, icon, trend, trendPositive = true, loading = false,
}: KpiCardProps) {
  const trendColor =
    trend === 'stable' ? 'text-gray-400'
    : (trend === 'up') === trendPositive ? 'text-status-up'
    : 'text-status-down'

  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus

  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-start justify-between">
        <span className="section-title">{label}</span>
        {icon && <span className="text-gray-500">{icon}</span>}
      </div>

      {loading ? (
        <div className="h-8 w-24 bg-surface-overlay rounded animate-pulse" />
      ) : (
        <div className="flex items-end gap-1">
          <span className="metric-value">{value}</span>
          {unit && <span className="text-gray-400 text-sm pb-0.5">{unit}</span>}
        </div>
      )}

      {(subtitle || trend) && (
        <div className="flex items-center gap-2 mt-1">
          {trend && <TrendIcon size={12} className={trendColor} />}
          {subtitle && <span className="text-xs text-gray-500">{subtitle}</span>}
        </div>
      )}
    </div>
  )
}

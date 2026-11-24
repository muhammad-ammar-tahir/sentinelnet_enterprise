/**
 * components/metrics/MetricsChart.tsx — Time-Series Line Chart
 *
 * Renders a Recharts ResponsiveLineChart for a single metric over time.
 * Used in DashboardPage and IncidentDetailPage to show how a metric
 * evolved before, during, and after a fault event.
 *
 * Visual design:
 * - Dark background matching the dashboard surface
 * - Sentinel blue line with a subtle area fill
 * - Fault event marked with a vertical red reference line
 * - Tooltip shows exact value and timestamp on hover
 *
 * Props:
 *   data: TimeSeriesPoint[]    — [{timestamp, value}]
 *   label: string              — chart title / Y-axis label
 *   unit?: string              — unit appended to tooltip value
 *   faultAt?: string           — ISO timestamp of fault injection (draws red line)
 *   height?: number
 */
import {
  ResponsiveContainer, XAxis, YAxis,
  Tooltip, CartesianGrid, ReferenceLine, Area, AreaChart,
} from 'recharts'
import { format } from 'date-fns'
import type { TimeSeriesPoint } from '@/types'

interface MetricsChartProps {
  data: TimeSeriesPoint[]
  label: string
  unit?: string
  faultAt?: string
  height?: number
}

// Custom tooltip for dark theme
const CustomTooltip = ({ active, payload, label: ts, unit }: {
  active?: boolean; payload?: Array<{ value: number }>; label?: string; unit?: string
}) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-surface-overlay border border-surface-border rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-gray-400">{ts ? format(new Date(ts), 'HH:mm:ss') : ''}</p>
      <p className="text-sentinel-300 font-mono font-semibold">
        {payload[0].value.toFixed(2)}{unit ? ` ${unit}` : ''}
      </p>
    </div>
  )
}

export default function MetricsChart({ data, label, unit, faultAt, height = 200 }: MetricsChartProps) {
  return (
    <div className="card">
      <p className="section-title mb-3">{label}</p>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="sentinelGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#1eb4f8" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#1eb4f8" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={ts => format(new Date(ts as string), 'HH:mm')}
            tick={{ fill: '#6b7280', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#6b7280', fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            unit={unit}
          />
          <Tooltip content={<CustomTooltip unit={unit} />} />
          {faultAt && (
            <ReferenceLine
              x={faultAt}
              stroke="#ef4444"
              strokeDasharray="4 2"
              label={{ value: 'Fault', fill: '#ef4444', fontSize: 10 }}
            />
          )}
          <Area
            type="monotone"
            dataKey="value"
            stroke="#1eb4f8"
            strokeWidth={1.5}
            fill="url(#sentinelGrad)"
            dot={false}
            activeDot={{ r: 3, fill: '#1eb4f8' }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

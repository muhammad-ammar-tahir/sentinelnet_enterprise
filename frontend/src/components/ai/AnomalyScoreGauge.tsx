/**
 * components/ai/AnomalyScoreGauge.tsx — Anomaly Score Gauge
 *
 * Displays the current Isolation Forest anomaly score as a semi-circular
 * gauge using SVG arcs. The needle and colour zone indicate severity:
 *   0.0–0.4   → Green  (normal)
 *   0.4–0.65  → Amber  (borderline)
 *   0.65–1.0  → Red    (anomalous)
 *
 * Also shows the numerical score and threshold line.
 *
 * Props:
 *   score: number         — 0.0 to 1.0 (higher = more anomalous)
 *   threshold?: number    — threshold line position (default: 0.65)
 *   label?: string
 */
interface AnomalyScoreGaugeProps {
  score: number
  threshold?: number
  label?: string
}

function scoreToAngle(score: number): number {
  // Maps 0–1 score to -90° to +90° (semicircle)
  return -90 + score * 180
}

function scoreColor(score: number, threshold: number): string {
  if (score >= threshold) return '#ef4444'
  if (score >= threshold * 0.7) return '#f59e0b'
  return '#22c55e'
}

export default function AnomalyScoreGauge({ score, threshold = 0.65, label = 'Anomaly Score' }: AnomalyScoreGaugeProps) {
  const cx = 100
  const cy = 100
  const r = 70
  const angle = scoreToAngle(Math.min(1, Math.max(0, score)))
  const color = scoreColor(score, threshold)

  // Needle endpoint
  const rad = (angle * Math.PI) / 180
  const nx = cx + r * Math.cos(rad)
  const ny = cy + r * Math.sin(rad)

  return (
    <div className="flex flex-col items-center gap-1">
      <svg viewBox="0 0 200 120" className="w-40">
        {/* Background arc */}
        <path
          d="M 30 100 A 70 70 0 0 1 170 100"
          fill="none"
          stroke="#30363d"
          strokeWidth={12}
          strokeLinecap="round"
        />
        {/* Threshold marker */}
        <line
          x1={cx}
          y1={cy}
          x2={cx + r * Math.cos(scoreToAngle(threshold) * Math.PI / 180)}
          y2={cy + r * Math.sin(scoreToAngle(threshold) * Math.PI / 180)}
          stroke="#ef4444"
          strokeWidth={2}
          strokeDasharray="4 2"
          opacity={0.7}
        />
        {/* Needle */}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={color} strokeWidth={2.5} strokeLinecap="round" />
        {/* Centre dot */}
        <circle cx={cx} cy={cy} r={4} fill={color} />
        {/* Score text */}
        <text x={cx} y={cy + 20} textAnchor="middle" fill={color} fontSize={18} fontWeight="bold" fontFamily="monospace">
          {score.toFixed(2)}
        </text>
      </svg>
      <span className="text-xs text-gray-400">{label}</span>
    </div>
  )
}

/**
 * components/ai/ConfidenceBar.tsx — Classification Confidence Bar
 *
 * Renders a horizontal stacked bar showing the probability distribution
 * across all 5 failure type classes from the Random Forest classifier.
 *
 * The predicted class (highest probability) is highlighted.
 * Useful in IncidentDetailPage to show how confident the diagnosis was.
 *
 * Props:
 *   probabilities: ClassProbabilities
 *   predicted: FailureType
 */
import type { ClassProbabilities, FailureType } from '@/types'
import clsx from 'clsx'

interface ConfidenceBarProps {
  probabilities: ClassProbabilities
  predicted: FailureType
}

const CLASS_COLORS: Record<string, string> = {
  LINK_FAILURE:     'bg-red-500',
  CONGESTION:       'bg-amber-500',
  HIGH_LATENCY:     'bg-yellow-500',
  DEVICE_FAILURE:   'bg-purple-500',
  REPEATED_FAILURE: 'bg-pink-500',
}

export default function ConfidenceBar({ probabilities, predicted }: ConfidenceBarProps) {
  const entries = Object.entries(probabilities) as [FailureType, number][]
  entries.sort((a, b) => b[1] - a[1])

  return (
    <div className="space-y-2">
      {entries.map(([cls, prob]) => (
        <div key={cls} className="flex items-center gap-2">
          <span
            className={clsx(
              'text-[10px] w-32 shrink-0',
              cls === predicted ? 'text-white font-semibold' : 'text-gray-500'
            )}
          >
            {cls.replace('_', ' ')}
          </span>
          <div className="flex-1 bg-surface-overlay rounded-full h-2 overflow-hidden">
            <div
              className={clsx('h-2 rounded-full transition-all', CLASS_COLORS[cls] ?? 'bg-gray-500')}
              style={{ width: `${(prob * 100).toFixed(0)}%`, opacity: cls === predicted ? 1 : 0.5 }}
            />
          </div>
          <span className="text-[10px] font-mono text-gray-400 w-10 text-right">
            {(prob * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  )
}

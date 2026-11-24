/**
 * components/ui/ErrorBanner.tsx — Error Display Banner
 *
 * Displays an error message in a styled alert box.
 * Used when an API call fails and the component needs to show
 * the error to the user rather than silently failing.
 *
 * Props:
 *   message: string — error message to display
 *   onRetry?: () => void — optional retry callback (shows Retry button)
 */
import { AlertCircle } from 'lucide-react'

interface ErrorBannerProps {
  message: string
  onRetry?: () => void
}

export default function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-500/10 p-4">
      <AlertCircle size={16} className="text-red-400 mt-0.5 shrink-0" />
      <div className="flex-1">
        <p className="text-sm text-red-300">{message}</p>
        {onRetry && (
          <button onClick={onRetry} className="mt-2 text-xs text-red-400 hover:text-red-200 underline">
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

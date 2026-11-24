/**
 * components/ui/EmptyState.tsx — Empty Data Placeholder
 *
 * Rendered when a list or data section has no items to show.
 * Provides a contextual icon, message, and optional action button.
 *
 * Props:
 *   title: string
 *   description?: string
 *   icon?: React.ReactNode
 *   action?: { label: string; onClick: () => void }
 */
import { InboxIcon } from 'lucide-react'

interface EmptyStateProps {
  title: string
  description?: string
  icon?: React.ReactNode
  action?: { label: string; onClick: () => void }
}

export default function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="mb-4 text-gray-600">
        {icon ?? <InboxIcon size={40} strokeWidth={1} />}
      </div>
      <p className="text-sm font-medium text-gray-300">{title}</p>
      {description && <p className="mt-1 text-xs text-gray-500 max-w-xs">{description}</p>}
      {action && (
        <button onClick={action.onClick} className="btn-primary mt-4">
          {action.label}
        </button>
      )}
    </div>
  )
}

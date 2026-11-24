/**
 * components/ui/LoadingSpinner.tsx — Spinner / Loading Indicator
 *
 * A simple centred spinner used as a full-page or inline loading state.
 * Size is configurable via the `size` prop.
 *
 * Props:
 *   size?: 'sm' | 'md' | 'lg' — controls spinner diameter (default: 'md')
 *   fullPage?: boolean — if true, centres in the full viewport height
 */
import clsx from 'clsx'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  fullPage?: boolean
}

const SIZE_CLASS = { sm: 'w-5 h-5 border-2', md: 'w-8 h-8 border-2', lg: 'w-12 h-12 border-[3px]' }

export default function LoadingSpinner({ size = 'md', fullPage = false }: LoadingSpinnerProps) {
  return (
    <div className={clsx('flex items-center justify-center', fullPage && 'h-full min-h-[400px]')}>
      <div
        className={clsx(
          'animate-spin rounded-full border-sentinel-500 border-t-transparent',
          SIZE_CLASS[size]
        )}
      />
    </div>
  )
}

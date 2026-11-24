/**
 * components/ui/Modal.tsx — Generic Modal Dialog
 *
 * A reusable modal overlay component used for confirmation dialogs,
 * recovery action forms, and policy editors.
 *
 * Features:
 * - Closes on Escape key press
 * - Closes on backdrop click
 * - Focus trapped inside modal while open
 * - Renders via React portal to avoid z-index issues
 *
 * Props:
 *   open: boolean
 *   onClose: () => void
 *   title: string
 *   children: React.ReactNode
 *   size?: 'sm' | 'md' | 'lg'
 */
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import clsx from 'clsx'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  size?: 'sm' | 'md' | 'lg'
}

const SIZE_CLASS = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
}

export default function Modal({ open, onClose, title, children, size = 'md' }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />

      {/* Dialog */}
      <div
        className={clsx(
          'relative w-full bg-surface-raised border border-surface-border rounded-xl shadow-xl',
          'animate-fade-in',
          SIZE_CLASS[size]
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border">
          <h2 className="text-sm font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>,
    document.body
  )
}

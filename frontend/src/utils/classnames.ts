/**
 * utils/classnames.ts — Tailwind Class Merging Utility
 *
 * Re-exports a configured `cn()` helper that combines:
 *   - clsx: conditional class joining
 *   - tailwind-merge: deduplication of conflicting Tailwind classes
 *
 * Usage:
 *   cn('px-4 py-2', isActive && 'bg-sentinel-600', 'px-6')
 *   → 'py-2 bg-sentinel-600 px-6'  (px-4 is overridden by px-6 via twMerge)
 *
 * Import this instead of importing clsx and twMerge separately.
 */
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

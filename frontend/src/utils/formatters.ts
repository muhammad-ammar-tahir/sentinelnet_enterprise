/**
 * utils/formatters.ts — Data Formatting Utilities
 *
 * Pure helper functions for formatting raw data values
 * into human-readable strings for display in the UI.
 *
 * All functions are pure (no side effects) and independently testable.
 * Import specific functions rather than the whole module to keep bundles lean.
 */

/**
 * Format a byte count into a human-readable string.
 * formatBytes(1312000) → "1.25 MB/s"
 */
export function formatBytes(bytes: number, suffix = ''): string {
  if (bytes < 1024) return `${bytes} B${suffix}`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB${suffix}`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB${suffix}`
  return `${(bytes / 1024 ** 3).toFixed(1)} GB${suffix}`
}

/**
 * Format milliseconds into a human-readable duration string.
 * formatDuration(33000) → "33.0s"
 * formatDuration(90500) → "1m 30s"
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rem = Math.round(s % 60)
  return `${m}m ${rem}s`
}

/**
 * Format a 0–1 score as a percentage string.
 * formatConfidence(0.937) → "93.7%"
 */
export function formatConfidence(score: number): string {
  return `${(score * 100).toFixed(1)}%`
}

/**
 * Truncate a string to maxLen characters with an ellipsis.
 * truncate('very long string', 10) → 'very long…'
 */
export function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen - 1) + '…'
}

/**
 * Map a failure type code to a human-readable label.
 */
export function formatFailureType(type: string): string {
  const MAP: Record<string, string> = {
    LINK_FAILURE:     'Link Failure',
    CONGESTION:       'Congestion',
    HIGH_LATENCY:     'High Latency',
    DEVICE_FAILURE:   'Device Failure',
    REPEATED_FAILURE: 'Repeated Failure',
  }
  return MAP[type] ?? type
}

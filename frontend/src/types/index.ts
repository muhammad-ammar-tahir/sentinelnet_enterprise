/**
 * types/index.ts — Re-export barrel for all domain types
 *
 * Import from here rather than individual type files:
 *   import { Incident, Device, Metric } from '@/types'
 *
 * This keeps imports tidy across the codebase and makes
 * refactoring the type module structure non-breaking.
 */
export * from './network'
export * from './incidents'
export * from './metrics'
export * from './ai'
export * from './auth'
export * from './api'

/**
 * Shared utilities for render job status handling
 */

export type NormalizedJobStatus = 
  | 'complete'
  | 'failed'
  | 'rendering'
  | 'pending'
  | 'unknown'

/**
 * Normalizes job status strings to a consistent set of values
 * Used across ProductionBoard, ProductionExecutionBay, and other components
 */
export function normalizeJobStatus(status: string | undefined | null): NormalizedJobStatus {
  if (!status) return 'unknown'
  
  const normalized = status.trim().toLowerCase()
  
  // Complete states
  if (normalized === 'complete' || normalized === 'completed' || normalized === 'success') {
    return 'complete'
  }
  
  // Failed states
  if (normalized === 'failed' || normalized === 'error' || normalized === 'cancelled') {
    return 'failed'
  }
  
  // Rendering states
  if (normalized === 'rendering' || normalized === 'processing' || normalized === 'running' || normalized === 'in_progress') {
    return 'rendering'
  }
  
  // Pending states
  if (normalized === 'pending' || normalized === 'queued' || normalized === 'created') {
    return 'pending'
  }
  
  return 'unknown'
}

/**
 * Returns user-friendly label for normalized status
 */
export function getStatusLabel(status: NormalizedJobStatus): string {
  switch (status) {
    case 'complete':
      return 'Ready'
    case 'failed':
      return 'Failed'
    case 'rendering':
      return 'Rendering'
    case 'pending':
      return 'Pending'
    default:
      return 'Unknown'
  }
}

/**
 * Returns CSS class for status badge styling
 */
export function getStatusClassName(status: NormalizedJobStatus): string {
  switch (status) {
    case 'complete':
      return 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200'
    case 'failed':
      return 'border-rose-400/40 bg-rose-500/10 text-rose-200'
    case 'rendering':
      return 'border-cyan-400/40 bg-cyan-500/10 text-cyan-200'
    case 'pending':
      return 'border-amber-400/40 bg-amber-500/10 text-amber-200'
    default:
      return 'border-zinc-600/40 bg-zinc-700/10 text-zinc-300'
  }
}

/**
 * Checks if status is terminal (no further updates expected)
 */
export function isTerminalStatus(status: NormalizedJobStatus): boolean {
  return status === 'complete' || status === 'failed'
}

/**
 * Checks if status indicates job is actively processing
 */
export function isActiveStatus(status: NormalizedJobStatus): boolean {
  return status === 'rendering' || status === 'pending'
}

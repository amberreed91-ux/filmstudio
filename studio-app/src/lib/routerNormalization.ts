/**
 * Router payload-normalization visibility helpers.
 *
 * Backend source of truth: `RunwayRouterAdapter` records
 * `job.metadata["router_execution"]["payload_normalized"] = True` plus a
 * `payload_normalization_warnings` list when the production-router wire
 * payload is auto-adjusted before submission. The `ROUTER_PAYLOAD_NORMALIZED`
 * stage log prefix is the same signal in log form.
 *
 * No business logic lives in components — they call these pure helpers.
 */

export const ROUTER_NORMALIZATION_TOOLTIP =
  'Payload automatically optimized to 1 primary reference image, 16:9 aspect ratio, and 5s duration for Runway router eligibility.'

export const ROUTER_NORMALIZATION_BADGE_LABEL = 'Auto-Optimized'

type AnyRecord = Record<string, unknown>

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function warningMentionsNormalization(warning: unknown): boolean {
  if (typeof warning !== 'string') return false
  const text = warning.toLowerCase()
  return (
    text.includes('router_payload_normalized') ||
    text.includes('secondary_references_') ||
    text.includes('non_verified_aspect') ||
    text.includes('non_verified_duration') ||
    text.includes('unsupported_flag_stripped') ||
    text.includes('unsupported_input_flag_preserved') ||
    text.includes('prompttext_coerced_to_string')
  )
}

/**
 * True when the job's execution metadata shows the Runway router adapter
 * auto-normalized the generation payload. Accepts the render-job shape
 * (`job.metadata.router_execution`) and never throws on malformed input.
 */
export function isRouterPayloadNormalized(job: unknown): boolean {
  const record = asRecord(job)
  if (!record) return false
  const metadata = asRecord(record.metadata)
  if (!metadata) return false
  const execution = asRecord(metadata.router_execution)
  if (!execution) return false
  if (execution.payload_normalized === true) return true
  const warnings = execution.payload_normalization_warnings
  if (Array.isArray(warnings) && warnings.some(warningMentionsNormalization)) return true
  const flatWarnings = (execution as AnyRecord).warnings
  if (Array.isArray(flatWarnings) && flatWarnings.some(warningMentionsNormalization)) return true
  return false
}

/**
 * Returns the raw normalization warning strings for tooltip/detail display.
 * Returns an empty array when the job was not normalized.
 */
export function getRouterNormalizationWarnings(job: unknown): string[] {
  const record = asRecord(job)
  if (!record) return []
  const metadata = asRecord(record.metadata)
  if (!metadata) return []
  const execution = asRecord(metadata.router_execution)
  if (!execution) return []
  const candidates = execution.payload_normalization_warnings
  if (!Array.isArray(candidates)) return []
  return candidates.filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
}

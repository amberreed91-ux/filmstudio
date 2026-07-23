import type { ProviderDurationConstraint } from './studioApi'

export type StoryboardImageStatus = 'idle' | 'loading' | 'ready' | 'failed' | 'unavailable' | 'generating'

export function initialStoryboardImageState(imageUrl: string | undefined, generating: boolean): StoryboardImageStatus {
  if (generating) return 'generating'
  return imageUrl && imageUrl.trim() ? 'loading' : 'unavailable'
}

export function chooseDurationForProvider(
  requestedSeconds: number,
  constraint: ProviderDurationConstraint | undefined,
  fallbackSeconds: number,
): number {
  const requested = Number.isFinite(requestedSeconds) ? Math.round(requestedSeconds) : fallbackSeconds
  if (!constraint) return Math.max(1, Math.min(60, requested))
  const valid = constraint.valid_durations_seconds.length > 0
    ? constraint.valid_durations_seconds
    : [fallbackSeconds]
  if (constraint.supports_custom_duration) {
    return Math.max(1, Math.min(60, requested))
  }
  return valid.reduce((best, value) => (
    Math.abs(value - requested) < Math.abs(best - requested) ? value : best
  ), valid[0])
}

import type { ProviderDurationConstraint } from './studioApi'

export type StoryboardImageStatus = 'idle' | 'loading' | 'ready' | 'failed' | 'unavailable' | 'generating'
export type PrevisRenderEngine = 'Wan 2.2' | 'LTX-Video' | 'Auto (Best Available)'
export type PrevisShotPlanningPayload = {
  purpose?: string
  framing?: string
  camera?: string
  blocking?: string
  composition?: string
  atmosphere?: string
  production?: string
  continuity?: string
  sound?: string
  transition?: string
  rationale?: string
}

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

export function providerIdForPrevisEngine(engine: PrevisRenderEngine): string | undefined {
  if (engine === 'Auto (Best Available)') return undefined
  return 'runway'
}

export function promptChangedAfterEnhancement(original: string, enhanced: string): boolean {
  const normalize = (value: string) => value.trim().replace(/\s+/g, ' ').toLowerCase()
  return normalize(enhanced).length > 0 && normalize(original) !== normalize(enhanced)
}

export function buildShotPlanningRenderPayload(details: PrevisShotPlanningPayload): PrevisShotPlanningPayload {
  return Object.fromEntries(
    Object.entries(details)
      .map(([key, value]) => [key, typeof value === 'string' ? value.trim() : ''])
      .filter(([, value]) => value.length > 0),
  )
}

export function buildStoryboardRenderReferences(storyboardImageUrl: string | undefined, contractReferences: string[] = []): string[] {
  const storyboardReference = storyboardImageUrl?.trim()
  return Array.from(new Set([
    ...(storyboardReference ? [storyboardReference] : []),
    ...contractReferences,
  ]))
}

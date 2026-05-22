import type { ProviderStatus, RenderJob } from './studioApi'

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function providerModeFromStatus(provider: ProviderStatus | null | undefined): string {
  const mode = asString(provider?.provider_mode).trim().toLowerCase()
  if (mode) return mode
  if (provider?.is_simulated || provider?.is_mock) return 'mock_success'
  if (provider?.ready_for_hosted_generation) return 'hosted_api'
  return 'unavailable'
}

export function providerModeFromJob(job: RenderJob | null | undefined): string {
  const normalized = asRecord(job?.output_payload?.metadata?.provider_response_normalized)
  const metadata = asRecord(normalized?.metadata)
  const mode = asString(metadata?.provider_mode).trim().toLowerCase()
  if (mode) return mode
  return ''
}

export function providerTruthLabel(provider: ProviderStatus | null | undefined): string {
  if (!provider) return 'Provider unavailable'
  if (provider.display_label) return provider.display_label

  const mode = providerModeFromStatus(provider)
  if (mode === 'mock_success') {
    return `${provider.name}: Mock Success Mode`
  }
  if (mode === 'hosted_api' && provider.ready_for_hosted_generation) {
    return `${provider.name}: Real provider mode active`
  }
  if ((provider.missing_requirements || []).includes('api_key')) {
    return `${provider.name}: hosted unavailable (api_key required)`
  }
  return `${provider.name}: unavailable`
}

export function generateSceneOutcomeCopy(mode: string): string {
  if (mode === 'mock_success') {
    return 'This generated a mock preview. Add a Runway API key and disable test mode for hosted generation.'
  }
  if (mode === 'hosted_api') {
    return 'Submitting to Runway…'
  }
  return 'Generation submitted.'
}

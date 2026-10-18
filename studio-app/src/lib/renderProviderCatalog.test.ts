import { describe, expect, it } from 'vitest'
import {
  providerUnavailableReason,
  providerIsUsable,
  selectableRenderProviders,
  visibleUnavailableProviders,
  type ProviderStatus,
} from './studioApi'

function provider(over: Partial<ProviderStatus> = {}): ProviderStatus {
  return {
    provider_id: 'runway',
    name: 'Runway',
    status: 'available',
    is_simulated: false,
    enabled: true,
    ready_for_hosted_generation: true,
    api_key_configured: true,
    provider_mode: 'hosted_api',
    missing_requirements: [],
    capabilities: ['video_generation'],
    active_jobs: 0,
    queued_jobs: 0,
    ...over,
  }
}

describe('shared render provider catalog', () => {
  it('treats enabled ready hosted providers as selectable and usable', () => {
    const runway = provider()
    expect(selectableRenderProviders([runway])).toEqual([runway])
    expect(providerIsUsable(runway)).toBe(true)
    expect(providerUnavailableReason(runway)).toBe('')
  })

  it('drops disabled cloud providers from selectable but keeps enabled-unconfigured visible with a reason', () => {
    const disabled = provider({ enabled: false, ready_for_hosted_generation: false })
    // Disabled providers are not a choice at all.
    expect(selectableRenderProviders([disabled])).toEqual([])
    expect(providerIsUsable(disabled)).toBe(false)
    expect(providerUnavailableReason(disabled)).toBe('disabled')

    const unconfigured = provider({
      status: 'unavailable',
      ready_for_hosted_generation: false,
      api_key_configured: false,
      missing_requirements: ['api_key'],
    })
    // Enabled but unconfigured: still selectable in the picker, with its real
    // reason surfaced instead of pretending it is ready.
    expect(selectableRenderProviders([unconfigured])).toContain(unconfigured)
    expect(visibleUnavailableProviders([unconfigured])).toContain(unconfigured)
    expect(providerUnavailableReason(unconfigured)).toBe('api_key')
  })

  it('reports missing requirements as the unavailability reason', () => {
    const unconfigured = provider({
      status: 'unavailable',
      ready_for_hosted_generation: false,
      api_key_configured: false,
      missing_requirements: ['api_key'],
    })
    expect(providerIsUsable(unconfigured)).toBe(false)
    expect(providerUnavailableReason(unconfigured)).toBe('api_key')
  })

  it('never selects providers the backend lists as disabled', () => {
    const localLtx = provider({
      provider_id: 'local_ltx',
      name: 'Local LTX (Phosphene)',
      status: 'disabled',
      provider_mode: 'unavailable',
      enabled: false,
      ready_for_hosted_generation: false,
    })
    const h3 = provider({
      provider_id: 'minimax_h3_local',
      name: 'MiniMax H3 Local',
      status: 'unsupported',
      provider_mode: 'unavailable',
      enabled: false,
      ready_for_hosted_generation: false,
      missing_requirements: ['cuda_runtime'],
    })
    const selected = selectableRenderProviders([localLtx, h3])
    expect(selected).toEqual([])
    expect(providerUnavailableReason(h3)).toBe('disabled')
    expect(visibleUnavailableProviders([localLtx, h3])).toEqual([])
  })

  it('exposes local_ltx as a selectable local option only when enabled, without faking readiness', () => {
    const localLtxEnabled = provider({
      provider_id: 'local_ltx',
      name: 'Local LTX (Phosphene)',
      status: 'available',
      provider_mode: 'local',
      enabled: true,
      ready_for_hosted_generation: false,
    })
    // Enabled + local mode: selectable, and usable once the local service is
    // actually reachable (provider_mode === 'local' is only set by the backend
    // for the local adapters; readiness itself is validated by the adapter).
    expect(selectableRenderProviders([localLtxEnabled])).toContain(localLtxEnabled)
    expect(providerIsUsable(localLtxEnabled)).toBe(true)
    expect(providerUnavailableReason(localLtxEnabled)).toBe('')
  })

  it('filters retired OpenRouter video providers even if a stale API catalog returns them', () => {
    const retired = [
      provider({ provider_id: 'openrouter' }),
      provider({ provider_id: 'openrouter-video' }),
    ]
    expect(selectableRenderProviders(retired)).toEqual([])
    expect(visibleUnavailableProviders(retired)).toEqual([])
  })

  it('keeps the simulated demo provider always usable', () => {
    const demo = provider({
      provider_id: 'simulation',
      name: 'Simulation (Demo)',
      is_simulated: true,
      provider_mode: 'mock_success',
      enabled: true,
      ready_for_hosted_generation: false,
    })
    expect(providerIsUsable(demo)).toBe(true)
  })

  it('tolerates null/undefined catalogs', () => {
    expect(selectableRenderProviders(null)).toEqual([])
    expect(selectableRenderProviders(undefined)).toEqual([])
    expect(providerIsUsable(null)).toBe(false)
  })
})

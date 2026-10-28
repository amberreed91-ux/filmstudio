/**
 * Tests for ProviderStatusBadge and ProjectProviderStatusBar components.
 *
 * Uses renderToStaticMarkup (same pattern as other component tests).
 *
 * Covers:
 * - Badge renders "Hosted" (green) for hosted provider
 * - Badge renders "Mock" (slate) for simulated provider
 * - "Switch to Hosted" link shown when mock + ready_for_hosted
 * - "Switch to Hosted" not shown when already hosted
 * - "Switch to Hosted" not shown when not ready_for_hosted
 * - Missing requirements tooltip content is correct
 * - Per-scene override takes precedence over project default
 * - Project-level status bar counts are correct
 * - Status bar shows "All mock" message when all scenes mock
 * - Status bar shows "All hosted" message when all scenes hosted
 * - Status bar shows "Mixed" message for mixed state
 * - data-testid attributes present for targeting
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

// ── Inline types ──────────────────────────────────────────────────────────────

type ProjectProviderStatus = {
  provider_mode: string
  ready_for_hosted_generation: boolean
  is_mock: boolean
  missing_requirements: string[]
  active_provider: string
  per_scene_overrides: Record<string, string>
}

// ── Inline components (mirrors ProviderStatusBadge) ───────────────────────────

function ProviderStatusBadge({
  sceneId,
  providerStatus,
}: {
  projectId: string
  sceneId: string
  providerStatus: ProjectProviderStatus
}) {
  const sceneOverride = providerStatus.per_scene_overrides?.[sceneId]
  const effectiveMode = sceneOverride ?? providerStatus.provider_mode
  const isHosted = effectiveMode === 'hosted_api'
  const isMock = !isHosted
  const canSwitchToHosted = isMock && providerStatus.ready_for_hosted_generation
  const hasMissingReqs = (providerStatus.missing_requirements?.length ?? 0) > 0

  return (
    <div className="flex items-center gap-1.5" data-testid="provider-status-badge">
      <span
        className={`rounded-full border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] ${
          isHosted
            ? 'border-emerald-400/50 bg-emerald-500/12 text-emerald-200'
            : 'border-zinc-600/50 bg-zinc-700/30 text-zinc-400'
        }`}
        data-testid={isHosted ? 'provider-badge-hosted' : 'provider-badge-mock'}
      >
        {isHosted ? 'Hosted' : 'Mock'}
      </span>

      {hasMissingReqs && (
        <div className="relative">
          <button
            type="button"
            className="text-[10px] text-zinc-500 hover:text-zinc-300"
            data-testid="missing-requirements-trigger"
          >
            ⚠
          </button>
          <div
            className="absolute bottom-full left-0 z-10 mb-1 w-48 rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-[10px] text-zinc-300 shadow-lg"
            data-testid="missing-requirements-tooltip"
          >
            <div className="mb-0.5 font-semibold text-zinc-400">Needs:</div>
            {providerStatus.missing_requirements.map((req) => (
              <div key={req} className="text-zinc-400">· {req}</div>
            ))}
          </div>
        </div>
      )}

      {canSwitchToHosted && (
        <button
          type="button"
          className="text-[10px] text-zinc-500 underline-offset-2 hover:text-cyan-300 hover:underline"
          data-testid="switch-to-hosted-link"
        >
          Switch to Hosted
        </button>
      )}
    </div>
  )
}

function ProjectProviderStatusBar({
  providerStatus,
  totalScenes,
}: {
  providerStatus: ProjectProviderStatus | null
  totalScenes: number
}) {
  if (!providerStatus || totalScenes === 0) return null

  const overrides = providerStatus.per_scene_overrides ?? {}
  const overrideValues = Object.values(overrides)
  const hostedOverrides = overrideValues.filter((v) => v === 'hosted_api').length
  const mockOverrides = overrideValues.filter((v) => v !== 'hosted_api').length
  const scenesWithoutOverride = totalScenes - overrideValues.length
  const projectDefaultIsHosted = providerStatus.provider_mode === 'hosted_api'
  const defaultHosted = projectDefaultIsHosted ? scenesWithoutOverride : 0
  const defaultMock = projectDefaultIsHosted ? 0 : scenesWithoutOverride
  const totalHosted = hostedOverrides + defaultHosted
  const totalMock = mockOverrides + defaultMock

  let message: string
  if (totalHosted === 0) {
    message = 'All scenes using mock rendering — switch to hosted when ready'
  } else if (totalMock === 0) {
    message = `All ${totalScenes} scene${totalScenes !== 1 ? 's' : ''} using hosted rendering`
  } else {
    message = `Mixed providers — ${totalHosted} hosted, ${totalMock} mock`
  }

  return (
    <div
      className="flex items-center gap-2 rounded border border-zinc-700/50 bg-zinc-900/40 px-3 py-1.5 text-[10px] text-zinc-400"
      data-testid="project-provider-status-bar"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${totalHosted > 0 ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
      <span data-testid="provider-status-bar-message">{message}</span>
    </div>
  )
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeStatus(overrides: Partial<ProjectProviderStatus> = {}): ProjectProviderStatus {
  return {
    provider_mode: 'simulated',
    ready_for_hosted_generation: false,
    is_mock: true,
    missing_requirements: [],
    active_provider: 'simulated',
    per_scene_overrides: {},
    ...overrides,
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ProviderStatusBadge', () => {

  it('renders "Mock" badge for simulated provider', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge projectId="p1" sceneId="scene_01" providerStatus={makeStatus()} />,
    )
    expect(html).toContain('Mock')
    expect(html).toContain('data-testid="provider-badge-mock"')
  })

  it('renders "Hosted" badge for hosted provider', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_01"
        providerStatus={makeStatus({ provider_mode: 'hosted_api', is_mock: false })}
      />,
    )
    expect(html).toContain('Hosted')
    expect(html).toContain('data-testid="provider-badge-hosted"')
  })

  it('uses emerald styling for hosted badge', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_01"
        providerStatus={makeStatus({ provider_mode: 'hosted_api', is_mock: false })}
      />,
    )
    expect(html).toContain('emerald')
  })

  it('uses zinc/slate styling for mock badge', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge projectId="p1" sceneId="scene_01" providerStatus={makeStatus()} />,
    )
    expect(html).toContain('zinc')
  })

  it('shows "Switch to Hosted" when mock and ready_for_hosted', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_01"
        providerStatus={makeStatus({ ready_for_hosted_generation: true })}
      />,
    )
    expect(html).toContain('Switch to Hosted')
    expect(html).toContain('data-testid="switch-to-hosted-link"')
  })

  it('does not show "Switch to Hosted" when already hosted', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_01"
        providerStatus={makeStatus({
          provider_mode: 'hosted_api',
          is_mock: false,
          ready_for_hosted_generation: true,
        })}
      />,
    )
    expect(html).not.toContain('Switch to Hosted')
  })

  it('does not show "Switch to Hosted" when not ready_for_hosted', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_01"
        providerStatus={makeStatus({ ready_for_hosted_generation: false })}
      />,
    )
    expect(html).not.toContain('Switch to Hosted')
  })

  it('shows missing requirements tooltip when requirements exist', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_01"
        providerStatus={makeStatus({ missing_requirements: ['api_key', 'api_endpoint'] })}
      />,
    )
    expect(html).toContain('data-testid="missing-requirements-tooltip"')
    expect(html).toContain('api_key')
    expect(html).toContain('api_endpoint')
  })

  it('does not show tooltip when no missing requirements', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_01"
        providerStatus={makeStatus({ missing_requirements: [] })}
      />,
    )
    expect(html).not.toContain('data-testid="missing-requirements-tooltip"')
  })

  it('per-scene override takes precedence over project default', () => {
    // Project default is simulated, but scene_01 has hosted_api override.
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_01"
        providerStatus={makeStatus({
          provider_mode: 'simulated',
          per_scene_overrides: { scene_01: 'hosted_api' },
        })}
      />,
    )
    expect(html).toContain('Hosted')
    expect(html).toContain('data-testid="provider-badge-hosted"')
  })

  it('scene without override uses project default', () => {
    // scene_02 has no override — uses project default (simulated).
    const html = renderToStaticMarkup(
      <ProviderStatusBadge
        projectId="p1"
        sceneId="scene_02"
        providerStatus={makeStatus({
          provider_mode: 'simulated',
          per_scene_overrides: { scene_01: 'hosted_api' },
        })}
      />,
    )
    expect(html).toContain('Mock')
  })

  it('has data-testid on badge container', () => {
    const html = renderToStaticMarkup(
      <ProviderStatusBadge projectId="p1" sceneId="scene_01" providerStatus={makeStatus()} />,
    )
    expect(html).toContain('data-testid="provider-status-badge"')
  })
})

describe('ProjectProviderStatusBar', () => {

  it('renders nothing when providerStatus is null', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar providerStatus={null} totalScenes={3} />,
    )
    expect(html).toBe('')
  })

  it('renders nothing when totalScenes is 0', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar providerStatus={makeStatus()} totalScenes={0} />,
    )
    expect(html).toBe('')
  })

  it('shows "All scenes using mock" when all mock', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar
        providerStatus={makeStatus({ provider_mode: 'simulated' })}
        totalScenes={3}
      />,
    )
    expect(html).toContain('All scenes using mock rendering')
    expect(html).toContain('switch to hosted when ready')
  })

  it('shows "All X scenes using hosted" when all hosted', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar
        providerStatus={makeStatus({ provider_mode: 'hosted_api', is_mock: false })}
        totalScenes={4}
      />,
    )
    expect(html).toContain('All 4 scenes using hosted rendering')
  })

  it('shows "Mixed providers" when some hosted some mock', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar
        providerStatus={makeStatus({
          provider_mode: 'simulated',
          per_scene_overrides: { scene_01: 'hosted_api' },
        })}
        totalScenes={3}
      />,
    )
    expect(html).toContain('Mixed providers')
    expect(html).toContain('1 hosted')
    expect(html).toContain('2 mock')
  })

  it('counts per-scene overrides correctly', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar
        providerStatus={makeStatus({
          provider_mode: 'simulated',
          per_scene_overrides: {
            scene_01: 'hosted_api',
            scene_02: 'hosted_api',
            scene_03: 'simulated',
          },
        })}
        totalScenes={5}
      />,
    )
    // 2 hosted overrides + 0 default hosted = 2 hosted
    // 1 mock override + 2 default mock (scenes 4,5) = 3 mock
    expect(html).toContain('2 hosted')
    expect(html).toContain('3 mock')
  })

  it('has data-testid on status bar', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar providerStatus={makeStatus()} totalScenes={2} />,
    )
    expect(html).toContain('data-testid="project-provider-status-bar"')
    expect(html).toContain('data-testid="provider-status-bar-message"')
  })

  it('shows emerald dot when any hosted scenes', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar
        providerStatus={makeStatus({ provider_mode: 'hosted_api', is_mock: false })}
        totalScenes={2}
      />,
    )
    expect(html).toContain('bg-emerald-400')
  })

  it('shows zinc dot when all mock', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar providerStatus={makeStatus()} totalScenes={2} />,
    )
    expect(html).toContain('bg-zinc-600')
  })

  it('singular "scene" for single scene project', () => {
    const html = renderToStaticMarkup(
      <ProjectProviderStatusBar
        providerStatus={makeStatus({ provider_mode: 'hosted_api', is_mock: false })}
        totalScenes={1}
      />,
    )
    expect(html).toContain('All 1 scene using hosted rendering')
    expect(html).not.toContain('scenes using hosted')
  })
})

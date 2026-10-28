/**
 * ProviderStatusBadge
 *
 * Per-scene provider status indicator for the Production Board scene card.
 *
 * Shows:
 * - "Hosted" badge (green) when using a real provider
 * - "Mock" badge (slate) when using simulated rendering
 * - A quiet "Switch to Hosted" link when mock but hosted is available
 * - A tooltip listing missing requirements when they exist
 *
 * Never alarming. Always informational.
 */

import { useState } from 'react'
import { setSceneProviderOverride, type ProjectProviderStatus } from '../lib/studioApi'

type ProviderStatusBadgeProps = {
  projectId: string
  sceneId: string
  providerStatus: ProjectProviderStatus
  /** Called after a successful override so the parent can refresh */
  onOverrideApplied?: () => void
}

export default function ProviderStatusBadge({
  projectId,
  sceneId,
  providerStatus,
  onOverrideApplied,
}: ProviderStatusBadgeProps) {
  const [switching, setSwitching] = useState(false)
  const [switchError, setSwitchError] = useState('')
  const [tooltipOpen, setTooltipOpen] = useState(false)

  // Determine effective mode for this scene.
  const sceneOverride = providerStatus.per_scene_overrides?.[sceneId]
  const effectiveMode = sceneOverride ?? providerStatus.provider_mode
  const isHosted = effectiveMode === 'hosted_api'
  const isMock = !isHosted
  const canSwitchToHosted = isMock && providerStatus.ready_for_hosted_generation
  const hasMissingReqs = (providerStatus.missing_requirements?.length ?? 0) > 0

  async function handleSwitchToHosted() {
    if (switching) return
    setSwitching(true)
    setSwitchError('')
    try {
      await setSceneProviderOverride(projectId, sceneId, 'hosted_api')
      onOverrideApplied?.()
    } catch (err) {
      setSwitchError(err instanceof Error ? err.message : 'Switch failed.')
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="flex items-center gap-1.5" data-testid="provider-status-badge">
      {/* Main badge */}
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

      {/* Missing requirements tooltip */}
      {hasMissingReqs && (
        <div className="relative">
          <button
            type="button"
            onMouseEnter={() => setTooltipOpen(true)}
            onMouseLeave={() => setTooltipOpen(false)}
            onFocus={() => setTooltipOpen(true)}
            onBlur={() => setTooltipOpen(false)}
            className="text-[10px] text-zinc-500 hover:text-zinc-300"
            aria-label="Missing requirements"
            data-testid="missing-requirements-trigger"
          >
            ⚠
          </button>
          {tooltipOpen && (
            <div
              className="absolute z-[9999] w-48 max-w-[12rem] overflow-hidden rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-[10px] text-zinc-300 shadow-lg pointer-events-none"
              style={{
                top: '100%',
                left: '50%',
                transform: 'translateX(-50%)',
                marginTop: '4px',
              }}
              data-testid="missing-requirements-tooltip"
            >
              <div className="mb-0.5 font-semibold text-zinc-400">Needs:</div>
              {providerStatus.missing_requirements.map((req) => (
                <div key={req} className="text-zinc-400 break-words">· {req}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Quiet "Switch to Hosted" link */}
      {canSwitchToHosted && (
        <button
          type="button"
          onClick={handleSwitchToHosted}
          disabled={switching}
          aria-busy={switching}
          className="text-[10px] text-zinc-500 underline-offset-2 hover:text-cyan-300 hover:underline disabled:opacity-40"
          data-testid="switch-to-hosted-link"
        >
          {switching ? '…' : 'Switch to Hosted'}
        </button>
      )}

      {switchError && (
        <span className="text-[10px] text-rose-400" data-testid="switch-error">
          {switchError}
        </span>
      )}
    </div>
  )
}


// ── Project-level provider status bar ────────────────────────────────────────

type ProjectProviderStatusBarProps = {
  providerStatus: ProjectProviderStatus | null
  totalScenes: number
}

export function ProjectProviderStatusBar({
  providerStatus,
  totalScenes,
}: ProjectProviderStatusBarProps) {
  if (!providerStatus || totalScenes === 0) return null

  const overrides = providerStatus.per_scene_overrides ?? {}
  const overrideValues = Object.values(overrides)
  const hostedOverrides = overrideValues.filter((v) => v === 'hosted_api').length
  const mockOverrides = overrideValues.filter((v) => v !== 'hosted_api').length

  // Scenes without an override use the project default.
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
      <span
        className={`h-1.5 w-1.5 rounded-full ${totalHosted > 0 ? 'bg-emerald-400' : 'bg-zinc-600'}`}
      />
      <span data-testid="provider-status-bar-message">{message}</span>
    </div>
  )
}

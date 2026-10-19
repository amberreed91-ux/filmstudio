// @vitest-environment jsdom
// Phase 2B item 3: the canonical thread no longer submits renders.
// Contract under test: at the render step the panel shows a clear
// "not available" notice naming the single submit path (Generation
// Readiness in Previs), renders NO render/submit buttons or dialogs, and
// performs no network call on mount.
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import CanonicalWorkflowPanel from './CanonicalWorkflowPanel'
import type { CanonicalWorkflowRun } from '../lib/canonicalWorkflowApi'

const hookState = vi.hoisted(() => ({
  run: null as CanonicalWorkflowRun | null,
}))

vi.mock('../hooks/useCanonicalWorkflow', () => ({
  useCanonicalWorkflow: () => ({
    run: hookState.run,
    sceneContext: { scriptId: 'script-1', sequenceId: '', beatIds: [] },
    availableRuns: [],
    currentBlueprintVersionId: 'sbv-approved',
    transitions: [],
    loading: false,
    polling: false,
    action: '',
    error: '',
    setError: vi.fn(),
    accept: vi.fn(),
    perform: vi.fn(),
    refresh: vi.fn(),
  }),
}))

function packageReadyRun(): CanonicalWorkflowRun {
  return {
    run_id: 'run-single',
    project_id: 'project-1',
    script_id: 'script-1',
    scene_id: 'scene_001',
    blueprint_id: 'sbp-1',
    blueprint_version_id: 'sbv-approved',
    status: 'package_ready',
    context_hash: 'hash-1',
    data: {
      identifiers: {},
      creative_context: {},
      continuity_context: {},
      artifacts: {},
      approvals: {},
      failures: [],
    },
    created_at: '2026-10-18T00:00:00Z',
    updated_at: '2026-10-18T00:00:00Z',
  }
}

function renderPanel() {
  return render(
    <CanonicalWorkflowPanel
      projectId="project-1"
      sceneId="scene_001"
      sceneContext={{ scriptId: 'script-1', sequenceId: '', beatIds: [] }}
      surface="previs"
      renderProvider="runway"
      renderProviderLabel="Runway"
    />,
  )
}

describe('canonical render unavailability (Phase 2B)', () => {
  afterEach(() => {
    cleanup()
    hookState.run = null
    vi.restoreAllMocks()
  })

  it('shows a not-available notice with the reason at the render step', () => {
    hookState.run = packageReadyRun()
    renderPanel()
    const notice = screen.getByTestId('canonical-render-unavailable')
    expect(notice).toBeInTheDocument()
    expect(notice).toHaveTextContent('Render from this thread is not available')
    expect(notice).toHaveTextContent('Generation Readiness')
  })

  it('renders no render buttons or dialogs and performs no network call', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('must not fetch'))
    hookState.run = packageReadyRun()
    renderPanel()
    expect(screen.queryByTestId('single-shot-render-toggle')).toBeNull()
    expect(screen.queryByTestId('whole-package-render-toggle')).toBeNull()
    expect(screen.queryByTestId('single-shot-render-dialog')).toBeNull()
    expect(screen.queryByTestId('whole-package-render-dialog')).toBeNull()
    expect(screen.queryByTestId('single-shot-confirm-button')).toBeNull()
    expect(screen.queryByTestId('whole-package-confirm')).toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('shows no notice before the render step', () => {
    hookState.run = null
    renderPanel()
    expect(screen.queryByTestId('canonical-render-unavailable')).toBeNull()
  })
})

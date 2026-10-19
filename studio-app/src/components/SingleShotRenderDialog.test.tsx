// @vitest-environment jsdom
// D5 guarded single-shot render (Phase A6, frontend).
//
// Contract under test: the dialog opens with nothing preselected and performs
// NO network call on panel mount or dialog open; the dry-run estimate fires
// only from the Check-cost click; confirming one shot posts exactly one
// storyboard_shot_id without the full-package flag; the whole-package control
// is separate and sends allow_full_package:true.
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    perform: (_label: string, operation: () => Promise<unknown>) => {
      void operation().catch(() => undefined)
    },
    refresh: vi.fn(),
  }),
}))

const shotPrompt = (order: number) =>
  `Shot ${order} medium. MAYA holds the silence in the edit bay. ` + 'x'.repeat(800)

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
      artifacts: {
        production_package: {
          package_id: 'pkg-1',
          payload: {
            shots: [1, 2, 3, 4, 5].map((order) => ({
              storyboard_shot_id: `sbs-00${order}`,
              shot_id: `scene_001_shot_00${order}`,
              prompt: shotPrompt(order),
              parameters: { duration: 5, duration_seconds: 5, ratio: '16:9' },
              previs_image_id: `previs-00${order}`,
              reference_assets: [],
              continuity: {},
              staging: '',
            })),
          },
        },
      },
      approvals: {},
      failures: [],
    },
    created_at: '2026-10-18T00:00:00Z',
    updated_at: '2026-10-18T00:00:00Z',
  }
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 })
}

function packageTimestampRun(packageCreatedAt: string | null, boardApprovedAt: string | null): CanonicalWorkflowRun {
  const run = packageReadyRun()
  return {
    ...run,
    data: {
      ...run.data,
      artifacts: {
        ...run.data.artifacts,
        production_package: {
          ...run.data.artifacts.production_package as Record<string, unknown>,
          ...(packageCreatedAt === null ? { created_at: undefined } : { created_at: packageCreatedAt }),
        },
      },
      approvals: {
        storyboard: {
          version_id: 'sbv-approved',
          approved_at: boardApprovedAt,
          approved_by: 'creator',
        },
      },
    },
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

describe('SingleShotRenderDialog', () => {
  afterEach(() => {
    cleanup()
    hookState.run = null
    vi.restoreAllMocks()
  })

  it('performs no network call on mount or dialog open, with nothing preselected', async () => {
    hookState.run = packageReadyRun()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}))
    renderPanel()

    expect(screen.getByTestId('single-shot-render-toggle')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('single-shot-render-toggle'))
    expect(screen.getByTestId('single-shot-render-dialog')).toBeInTheDocument()
    const radios = screen.getAllByRole('radio')
    expect(radios).toHaveLength(5)
    expect(radios.every((radio) => !(radio as HTMLInputElement).checked)).toBe(true)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows the 600-character prompt preview and named characters for the picked shot', () => {
    hookState.run = packageReadyRun()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}))
    renderPanel()

    fireEvent.click(screen.getByTestId('single-shot-render-toggle'))
    fireEvent.click(screen.getByDisplayValue('sbs-002'))

    const dialog = screen.getByTestId('single-shot-confirm')
    expect(dialog.textContent).toContain('1 Runway submission')
    const preview = dialog.querySelector('pre')
    expect(preview?.textContent).toBe(shotPrompt(2).slice(0, 600))
    expect(preview?.textContent).toHaveLength(600)
    expect(dialog.textContent).toContain('MAYA')
  })

  it('dry-runs only on Check-cost click and confirms one shot without the full-package flag', async () => {
    hookState.run = packageReadyRun()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/renders/estimate')) {
        return Promise.resolve(jsonResponse({
          run_id: 'run-single',
          ceiling_credits: 300,
          ceiling_env_var: 'RUNWAY_RENDER_MAX_CREDITS',
          estimates: [{
            storyboard_shot_id: 'sbs-002',
            shot_id: 'scene_001_shot_002',
            planned_duration_seconds: 5,
            effective_duration_seconds: 5,
            estimated_credits: 20,
            resolved_model: 'gen4.5',
            estimate_available: true,
          }],
        }))
      }
      return Promise.resolve(jsonResponse({ run: packageReadyRun(), transitions: [] }))
    })
    renderPanel()

    fireEvent.click(screen.getByTestId('single-shot-render-toggle'))
    fireEvent.click(screen.getByDisplayValue('sbs-002'))
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('single-shot-check-cost'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [estimateUrl, estimateInit] = fetchMock.mock.calls[0]
    expect(String(estimateUrl)).toContain('/renders/estimate')
    expect(JSON.parse(String((estimateInit as RequestInit).body))).toEqual({
      storyboard_shot_ids: ['sbs-002'],
    })
    await waitFor(() => expect(screen.getByTestId('single-shot-estimate').textContent).toContain('20'))

    const confirm = screen.getByTestId('single-shot-confirm')
    expect(confirm.textContent).toContain('I understand this spends Runway credits')
    fireEvent.click(screen.getByLabelText(/I understand this spends Runway credits/))
    fireEvent.click(screen.getByTestId('single-shot-confirm-button'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const [renderUrl, renderInit] = fetchMock.mock.calls[1]
    expect(String(renderUrl).endsWith('/renders')).toBe(true)
    expect(JSON.parse(String((renderInit as RequestInit).body))).toEqual({
      provider: 'runway',
      retry_confirmed: false,
      storyboard_shot_ids: ['sbs-002'],
      allow_full_package: false,
      acknowledge_unknown_cost: false,
      duration_seconds: 5,
    })
  })

  it('requires the unknown-cost acknowledgement when no estimate is available', async () => {
    hookState.run = packageReadyRun()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/renders/estimate')) {
        return Promise.resolve(jsonResponse({
          run_id: 'run-single',
          ceiling_credits: 300,
          ceiling_env_var: 'RUNWAY_RENDER_MAX_CREDITS',
          estimates: [{
            storyboard_shot_id: 'sbs-002',
            shot_id: 'scene_001_shot_002',
            planned_duration_seconds: 5,
            effective_duration_seconds: 5,
            estimated_credits: null,
            resolved_model: null,
            estimate_available: false,
          }],
        }))
      }
      return Promise.resolve(jsonResponse({ run: packageReadyRun(), transitions: [] }))
    })
    renderPanel()

    fireEvent.click(screen.getByTestId('single-shot-render-toggle'))
    fireEvent.click(screen.getByDisplayValue('sbs-002'))
    fireEvent.click(screen.getByTestId('single-shot-check-cost'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(screen.getByLabelText(/accept the unknown cost/)).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText(/I understand this spends Runway credits/))
    const confirmButton = screen.getByText('Confirm: render this one shot')
    expect(confirmButton).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/accept the unknown cost/))
    expect(confirmButton).not.toBeDisabled()
    fireEvent.click(confirmButton)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))).toMatchObject({
      storyboard_shot_ids: ['sbs-002'],
      acknowledge_unknown_cost: true,
    })
  })

  it('labels the cost estimate as a router dry-run, not a quote for the submit path', async () => {
    hookState.run = packageReadyRun()
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/renders/estimate')) {
        return Promise.resolve(jsonResponse({
          run_id: 'run-single',
          ceiling_credits: 300,
          ceiling_env_var: 'RUNWAY_RENDER_MAX_CREDITS',
          estimate_source: 'runway_router_dry_run',
          estimates: [{
            storyboard_shot_id: 'sbs-002',
            shot_id: 'scene_001_shot_002',
            planned_duration_seconds: 5,
            effective_duration_seconds: 5,
            estimated_credits: 20,
            resolved_model: 'gen4.5',
            estimate_available: true,
          }],
        }))
      }
      return Promise.resolve(jsonResponse({ run: packageReadyRun(), transitions: [] }))
    })
    renderPanel()

    fireEvent.click(screen.getByTestId('single-shot-render-toggle'))
    fireEvent.click(screen.getByDisplayValue('sbs-002'))
    fireEvent.click(screen.getByTestId('single-shot-check-cost'))
    await waitFor(() => expect(screen.getByTestId('single-shot-estimate')).toBeInTheDocument())
    const label = screen.getByTestId('single-shot-estimate').textContent || ''
    expect(label).toContain('Router dry-run estimate')
    expect(label).toContain('not a quote')
  })

  it('warns when the package predates the thread\'s board approval, and stays silent otherwise', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}))

    hookState.run = packageTimestampRun('2026-10-10T12:00:00+00:00', '2026-10-12T12:00:00+00:00')
    const { unmount } = renderPanel()
    fireEvent.click(screen.getByTestId('single-shot-render-toggle'))
    expect(screen.getByTestId('stale-package-warning').textContent).toContain('built before the board approval')
    unmount()
    cleanup()

    hookState.run = packageTimestampRun('2026-10-12T12:00:00+00:00', '2026-10-10T12:00:00+00:00')
    renderPanel()
    fireEvent.click(screen.getByTestId('single-shot-render-toggle'))
    expect(screen.queryByTestId('stale-package-warning')).not.toBeInTheDocument()
  })

  it('queues the whole package only behind its own control with allow_full_package', async () => {
    hookState.run = packageReadyRun()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ run: packageReadyRun(), transitions: [] }),
    )
    renderPanel()

    fireEvent.click(screen.getByTestId('whole-package-render-toggle'))
    expect(screen.getByTestId('whole-package-render-dialog').textContent).toContain('5 shots')
    fireEvent.click(screen.getByLabelText(/spends Runway credits for all 5 shots/))
    fireEvent.click(screen.getByLabelText(/No cost estimate is shown/))
    fireEvent.click(screen.getByTestId('whole-package-confirm'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url).endsWith('/renders')).toBe(true)
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      allow_full_package: true,
      acknowledge_unknown_cost: true,
    })
    expect(JSON.parse(String((init as RequestInit).body))).not.toHaveProperty('storyboard_shot_ids')
  })
})

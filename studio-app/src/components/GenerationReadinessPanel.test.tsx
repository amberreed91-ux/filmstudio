// @vitest-environment jsdom
// Generation Preflight UI workstream — focused panel tests.
//
// Contract under test: the panel is a pure display + safety surface over the
// backend's own preflight result. It never evaluates readiness itself, never
// invents blockers or plan data, disables Generate while blocked/stale/errored,
// and re-checks with the backend before generation can proceed.
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import GenerationReadinessPanel from './GenerationReadinessPanel'
import { getGenerationPreflight, type GenerationPreflight } from '../lib/studioApi'

vi.mock('../lib/studioApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/studioApi')>()
  return {
    ...actual,
    getGenerationPreflight: vi.fn(),
  }
})

const mockPreflight = vi.mocked(getGenerationPreflight)

const cameraInstruction = (overrides: Record<string, unknown> = {}) => ({
  dimension: 'framing',
  value: 'establishing_shot',
  instruction_source: 'AI_SUGGESTED',
  source_version: 'sbv_test',
  ...overrides,
})

const blockedShot = (order: number, blockers: string[]) => ({
  shot_id: `scene_001_shot_00${order}`,
  storyboard_shot_id: `sbs_00${order}`,
  shot_order: order,
  prompt: `Shot ${order} prompt`,
  duration_seconds: 5,
  camera_instructions: [cameraInstruction()],
  references: [],
  reference_version: 'none',
  generation_context_id: `genctx_${order}`,
  shot_version: 'abc123',
  blockers,
})

const readyShot = (order: number) => ({
  shot_id: `scene_001_shot_00${order}`,
  storyboard_shot_id: `sbs_00${order}`,
  shot_order: order,
  prompt: `Shot ${order} prompt`,
  duration_seconds: 5,
  camera_instructions: [cameraInstruction({ instruction_source: 'USER_SPECIFIED', value: '35mm handheld' })],
  references: ['/previs-assets/frame.png'],
  reference_version: 'refver1',
  generation_context_id: `genctx_${order}`,
  shot_version: 'abc123',
  blockers: [] as string[],
})

const blockedPreflight = (overrides: Partial<GenerationPreflight> = {}): GenerationPreflight => ({
  project_id: 'project-1',
  scene_id: 'scene_001',
  ready: false,
  blockers: [
    'Shot scene_001_shot_001: reference gate: Generation blocked: Scene scene_001 for setting scene_001. no approved canonical environment reference is available',
    'Shot scene_001_shot_002: Camera \'framing\' is an unapproved AI suggestion (\'medium_shot\')',
  ],
  shot_count: 2,
  entries: [
    blockedShot(1, ['reference gate: no approved canonical environment reference is available']),
    blockedShot(2, ["Camera 'framing' is an unapproved AI suggestion ('medium_shot')"]),
  ],
  manifest: {
    manifest_version: 1,
    scene: { scene_id: 'scene_001', scene_version: 'scv1' },
    storyboard: { storyboard_version: 'sbv1' },
    shots: [1, 2].map((order) => ({
      shot_id: `scene_001_shot_00${order}`,
      storyboard_shot_id: `sbs_00${order}`,
      shot_order: order,
      shot_version: 'abc123',
      shot_duration_seconds: 5,
      shot_prompt: `Shot ${order} prompt text`,
      camera_instructions: [cameraInstruction()],
      camera_plan: {},
      references: [],
      reference_version: 'none',
      generation_context_id: `genctx_${order}`,
      parameters: {},
    })),
    batch: {
      total_duration_seconds: 10,
      shot_count: 2,
    },
    manifest_fingerprint: 'fp123',
  },
  cost_estimate: {
    provider: 'runway',
    per_shot: [
      { model: 'gen4.5', duration_seconds: 5, estimated_credits: 60, estimated: true },
      { model: 'gen4.5', duration_seconds: 5, estimated_credits: 60, estimated: true },
    ],
    total_duration_seconds: 10,
    estimated_total_credits: 120,
    estimated: true,
    unpriced_shot_count: 0,
  },
  ...overrides,
})

const readyPreflight = (overrides: Partial<GenerationPreflight> = {}): GenerationPreflight => ({
  ...blockedPreflight(),
  ready: true,
  blockers: [],
  entries: [readyShot(1), readyShot(2)],
  manifest: blockedPreflight().manifest && {
    ...blockedPreflight().manifest!,
    shots: [1, 2].map((order) => ({
      shot_id: `scene_001_shot_00${order}`,
      storyboard_shot_id: `sbs_00${order}`,
      shot_order: order,
      shot_version: 'abc123',
      shot_duration_seconds: 5,
      shot_prompt: `Shot ${order} prompt text`,
      camera_instructions: [cameraInstruction({ instruction_source: 'USER_SPECIFIED', value: '35mm handheld' })],
      camera_plan: {},
      references: ['/previs-assets/frame.png'],
      reference_version: 'refver1',
      generation_context_id: `genctx_${order}`,
      parameters: {},
    })),
    batch: {
      total_duration_seconds: 10,
      shot_count: 2,
    },
  },
  ...overrides,
})

function renderPanel(props: Partial<Parameters<typeof GenerationReadinessPanel>[0]> = {}) {
  return render(
    <GenerationReadinessPanel
      projectId="project-1"
      sceneId="scene_001"
      onGenerate={vi.fn()}
      {...props}
    />,
  )
}

async function renderResolvedPanel(props: Partial<Parameters<typeof GenerationReadinessPanel>[0]> = {}) {
  const utils = renderPanel(props)
  await waitFor(() => expect(screen.getByTestId('generation-readiness')).toBeInTheDocument())
  return utils
}

/** Open the manifest details and expand one shot's plan section. */
function openManifestShot(order: number) {
  fireEvent.click(screen.getByText('Review Generation Plan'))
  const shot = screen.getByTestId(`manifest-shot-${order}`)
  fireEvent.click(shot.querySelector('button')!)
  return shot
}

describe('GenerationReadinessPanel', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows BLOCKED with the backend’s actual blockers, per-shot blockers, and the no-credits notice', async () => {
    mockPreflight.mockResolvedValue(blockedPreflight())
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-status-blocked')).toHaveTextContent('BLOCKED')
    expect(screen.getByTestId('preflight-blockers')).toHaveTextContent('no approved canonical environment reference')
    expect(screen.getByTestId('preflight-blockers')).toHaveTextContent("unapproved AI suggestion")
    expect(screen.getByTestId('preflight-shot-1')).toHaveTextContent('reference gate')
    expect(screen.getByTestId('preflight-shot-2')).toHaveTextContent('unapproved AI suggestion')
    expect(screen.getByTestId('preflight-no-credits')).toHaveTextContent('No provider credits can be spent')
  })

  it('shows READY with the backend’s planned generation when the backend reports ready', async () => {
    mockPreflight.mockResolvedValue(readyPreflight())
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-status-ready')).toHaveTextContent('READY')
    expect(screen.getByTestId('preflight-plan')).toHaveTextContent('Ready to Generate')
    expect(screen.getByTestId('preflight-shot-count')).toHaveTextContent('Shots: 2')
  })

  it('renders shot-specific blockers so the failing shot is identifiable', async () => {
    mockPreflight.mockResolvedValue(blockedPreflight())
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-shot-1')).toHaveTextContent('Shot 1 · Blocked')
    expect(screen.getByTestId('preflight-shot-2')).toHaveTextContent('Shot 2 · Blocked')
    expect(screen.queryByTestId('preflight-shot-3')).not.toBeInTheDocument()
  })

  it('displays missing references exactly as the backend reports them', async () => {
    mockPreflight.mockResolvedValue(blockedPreflight())
    await renderResolvedPanel()
    const shot1 = screen.getByTestId('preflight-shot-1')
    expect(shot1).toHaveTextContent('no approved canonical environment reference is available')
  })

  it('shows the camera approval blocker for unapproved AI-suggested camera', async () => {
    mockPreflight.mockResolvedValue(blockedPreflight())
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-shot-2')).toHaveTextContent("Camera 'framing' is an unapproved AI suggestion ('medium_shot')")
  })

  it('shows a prompt integrity blocker verbatim when the backend reports one', async () => {
    const promptIntegrity = blockedPreflight({
      blockers: ['Shot scene_001_shot_001: prompt integrity: BOARD prompt ends with a legacy truncation artifact'],
      entries: [blockedShot(1, ['prompt integrity: BOARD prompt ends with a legacy truncation artifact']), blockedShot(2, ['reference gate: no approved canonical environment reference is available'])],
    })
    mockPreflight.mockResolvedValue(promptIntegrity)
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-shot-1')).toHaveTextContent('prompt integrity: BOARD prompt ends with a legacy truncation artifact')
    expect(screen.getByTestId('preflight-blockers')).toHaveTextContent('Prompt integrity')
  })

  it('shows a cost-gate blocker with the backend’s reason, unshortened', async () => {
    const costBlocked = blockedPreflight({
      blockers: ['Shot scene_001_shot_001: cost gate: Estimated cost 300 credits exceeds the per-generation limit of 100. Confirm explicitly to proceed. (gen4.5: 5s)'],
      entries: [blockedShot(1, ['cost gate: Estimated cost 300 credits exceeds the per-generation limit of 100. Confirm explicitly to proceed. (gen4.5: 5s)']), blockedShot(2, [])],
    })
    mockPreflight.mockResolvedValue(costBlocked)
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-blockers')).toHaveTextContent('Cost')
    expect(screen.getByTestId('preflight-blockers')).toHaveTextContent('exceeds the per-generation limit of 100')
    expect(screen.getByTestId('preflight-shot-1')).toHaveTextContent('(gen4.5: 5s)')
  })

  it('renders scene-mint refusals as creator guidance instead of raw codes', async () => {
    const refused = blockedPreflight({
      blockers: ['Shot scene_001_shot_001: ENVIRONMENT_BASIS_GAP at batch authorization'],
      entries: [blockedShot(1, ['CONFIRMATION_DIGEST_MISMATCH for scene_001_shot_001']), blockedShot(2, [])],
    })
    mockPreflight.mockResolvedValue(refused)
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-blockers')).toHaveTextContent('environment list is out of date')
    expect(screen.getByTestId('preflight-blockers')).not.toHaveTextContent('ENVIRONMENT_BASIS_GAP')
    expect(screen.getByTestId('preflight-shot-1')).toHaveTextContent('changed after confirmation')
    expect(screen.getByTestId('preflight-shot-1')).not.toHaveTextContent('CONFIRMATION_DIGEST_MISMATCH')
  })

  it('displays the selected execution provider separately from the creative manifest', async () => {
    mockPreflight.mockResolvedValue(readyPreflight())
    await renderResolvedPanel({ renderProviderLabel: 'Runway Router' })
    expect(screen.getByTestId('preflight-provider')).toHaveTextContent('Execution provider: Runway Router')
    expect(screen.queryByTestId('preflight-model')).not.toBeInTheDocument()
    expect(screen.getByTestId('preflight-plan')).not.toHaveTextContent('AUTO: registry-compatible default for the provider')
  })

  it('displays the backend’s estimated cost before generation', async () => {
    mockPreflight.mockResolvedValue(readyPreflight())
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-estimated-cost')).toHaveTextContent('Estimated cost: 120 credits')
  })

  it('expands the Review Generation Plan manifest with per-shot details, camera provenance, and full prompts', async () => {
    mockPreflight.mockResolvedValue(readyPreflight())
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-manifest')).toHaveTextContent('Review Generation Plan')
    const shot1 = openManifestShot(1)
    expect(shot1).toHaveTextContent('Shot 1 prompt text')
    expect(shot1).toHaveTextContent('USER SPECIFIED')
    expect(shot1).toHaveTextContent('35mm handheld')
    expect(shot1).toHaveTextContent('Shot version: abc123')
  })

  it('disables Generate while the backend reports the scene blocked', async () => {
    mockPreflight.mockResolvedValue(blockedPreflight())
    await renderResolvedPanel()
    const generate = screen.getByTestId('preflight-generate') as HTMLButtonElement
    expect(generate).toBeDisabled()
  })

  it('enables Generate when the backend reports the scene ready', async () => {
    mockPreflight.mockResolvedValue(readyPreflight())
    await renderResolvedPanel()
    const generate = screen.getByTestId('preflight-generate') as HTMLButtonElement
    expect(generate).toBeEnabled()
  })

  it('performs a final preflight before generating and refreshes blockers when the fresh check is blocked', async () => {
    const onGenerate = vi.fn()
    mockPreflight.mockResolvedValueOnce(readyPreflight())
    renderPanel({ onGenerate })
    const generate = await waitFor(() => {
      const button = screen.getByTestId('preflight-generate') as HTMLButtonElement
      expect(button).toBeEnabled()
      return button
    })
    // Scene changed between Check and Generate: the fresh preflight is the
    // authoritative one, and it is blocked.
    mockPreflight.mockResolvedValueOnce(blockedPreflight())
    fireEvent.click(generate)
    expect(onGenerate).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByTestId('preflight-status-blocked')).toBeInTheDocument())
    expect(screen.getByTestId('preflight-blockers')).toHaveTextContent('no approved canonical environment reference')
  })

  it('marks the displayed readiness stale when the scene changes and requires a new preflight', async () => {
    mockPreflight.mockResolvedValue(readyPreflight())
    const { rerender } = renderPanel()
    await waitFor(() => expect(screen.getByTestId('preflight-status-ready')).toBeInTheDocument())
    const callsBefore = mockPreflight.mock.calls.length
    // User switches scene: the old verdict must not authorize the new state.
    rerender(
      <GenerationReadinessPanel projectId="project-1" sceneId="scene_002" onGenerate={vi.fn()} />,
    )
    expect(screen.getByTestId('preflight-stale')).toHaveTextContent('stale')
    const generate = screen.getByTestId('preflight-generate') as HTMLButtonElement
    expect(generate).toBeDisabled()
    expect(mockPreflight.mock.calls.length).toBe(callsBefore)
  })

  it('shows the loading state while the preflight request is in flight', async () => {
    let resolvePreflight: (value: GenerationPreflight) => void = () => {}
    mockPreflight.mockReturnValue(new Promise<GenerationPreflight>((resolve) => { resolvePreflight = resolve }))
    renderPanel()
    expect(screen.getByTestId('preflight-checking')).toHaveTextContent('Checking generation readiness...')
    resolvePreflight(blockedPreflight())
    await waitFor(() => expect(screen.getByTestId('preflight-status-blocked')).toBeInTheDocument())
  })

  it('shows the backend error state and keeps generation disabled', async () => {
    mockPreflight.mockRejectedValue(new Error('Backend unavailable'))
    renderPanel()
    await waitFor(() => expect(screen.getByTestId('preflight-error')).toBeInTheDocument())
    expect(screen.getByTestId('preflight-error')).toHaveTextContent('Backend unavailable')
    expect(screen.getByTestId('preflight-generate')).toBeDisabled()
  })

  it('summarizes the multi shot batch as N shots / X ready / Y blocked without a score', async () => {
    mockPreflight.mockResolvedValue(blockedPreflight())
    await renderResolvedPanel()
    const summary = screen.getByTestId('preflight-multishot-summary')
    expect(summary).toHaveTextContent('2 shots · 0 ready · 2 blocked')
    expect(summary).toHaveTextContent('the scene cannot render until all required shots pass preflight')
  })

  it('shows individual shot details including per-shot plan data from the manifest', async () => {
    mockPreflight.mockResolvedValue(readyPreflight())
    await renderResolvedPanel()
    const shot1 = openManifestShot(1)
    expect(shot1).toHaveTextContent('· 5s')
    expect(shot1).toHaveTextContent('shot v abc123')
    expect(shot1).toHaveTextContent('/previs-assets/frame.png')
    expect(shot1).toHaveTextContent('Reference version: refver1')
  })

  it('labels the generation mode as Studio Multi Shot, not Runway Multi Shot', async () => {
    mockPreflight.mockResolvedValue(readyPreflight())
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-mode')).toHaveTextContent('Generation mode: Studio Multi Shot')
    expect(screen.getByTestId('preflight-mode')).not.toHaveTextContent('Runway Multi Shot')
    expect(screen.getByTestId('preflight-plan')).toHaveTextContent('2 individual shot generations')
  })

  it('shows an AI-suggested camera as awaiting approval and not renderable', async () => {
    mockPreflight.mockResolvedValue(blockedPreflight())
    await renderResolvedPanel()
    const shot1 = openManifestShot(1)
    expect(screen.getByTestId('camera-ai-suggested')).toHaveTextContent('AI suggestion awaiting approval — not renderable')
    expect(shot1).toHaveTextContent('establishing_shot')
  })

  it('shows BLOCKED with per-shot authorization failures when the backend refuses batch authorization', async () => {
    const authRefused = readyPreflight({
      authorization: {
        ready: false,
        project_id: 'project-1',
        scene_id: 'scene_001',
        shot_count: 2,
        passed_count: 1,
        failed_count: 1,
        digest_expectations: 'absent',
        shots: [
          { shot_id: 'scene_001_shot_001', ok: true, failure_code: null, failure_category: null, message: null, policy_version: null, digest: 'skipped_no_expectations' },
          { shot_id: 'scene_001_shot_002', ok: false, failure_code: 'unsupported_reference_capacity', failure_category: 'reference_capacity', message: 'Shot scene_001_shot_002 exceeds the currently supported reference capacity (4 references).', policy_version: 'v2', digest: 'skipped_no_expectations' },
        ],
      },
    })
    mockPreflight.mockResolvedValue(authRefused)
    await renderResolvedPanel()
    // A rejected batch must never appear ready, even though readiness passed.
    expect(screen.getByTestId('preflight-status-blocked')).toHaveTextContent('BLOCKED')
    expect(screen.getByTestId('preflight-authorization-failures')).toHaveTextContent(
      'exceeds the currently supported reference capacity',
    )
    expect(screen.getByTestId('preflight-auth-shot-scene_001_shot_002')).toHaveTextContent('scene_001_shot_002')
    const generate = screen.getByTestId('preflight-generate') as HTMLButtonElement
    expect(generate).toBeDisabled()
  })

  it('keeps Generate enabled when batch authorization passes alongside readiness', async () => {
    const authReady = readyPreflight({
      authorization: {
        ready: true,
        shot_count: 2,
        passed_count: 2,
        failed_count: 0,
        digest_expectations: 'absent',
        shots: [
          { shot_id: 'scene_001_shot_001', ok: true, failure_code: null, failure_category: null, message: null, policy_version: null, digest: 'skipped_no_expectations' },
          { shot_id: 'scene_001_shot_002', ok: true, failure_code: null, failure_category: null, message: null, policy_version: null, digest: 'skipped_no_expectations' },
        ],
      },
    })
    mockPreflight.mockResolvedValue(authReady)
    await renderResolvedPanel()
    expect(screen.getByTestId('preflight-status-ready')).toHaveTextContent('READY')
    expect(screen.queryByTestId('preflight-authorization-failures')).not.toBeInTheDocument()
    const generate = screen.getByTestId('preflight-generate') as HTMLButtonElement
    expect(generate).toBeEnabled()
  })

  it('refuses to generate from the fresh check when authorization fails after a ready display', async () => {
    const onGenerate = vi.fn()
    mockPreflight.mockResolvedValueOnce(readyPreflight())
    renderPanel({ onGenerate })
    const generate = await waitFor(() => {
      const button = screen.getByTestId('preflight-generate') as HTMLButtonElement
      expect(button).toBeEnabled()
      return button
    })
    // Authorization refused between Check and Generate: nothing generates.
    mockPreflight.mockResolvedValueOnce(
      readyPreflight({
        authorization: {
          ready: false,
          shot_count: 2,
          passed_count: 0,
          failed_count: 2,
          shots: [
            { shot_id: 'scene_001_shot_001', ok: false, failure_code: 'upstream_blockers', failure_category: 'generation_contract', message: 'Shot scene_001_shot_001 carries unresolved readiness blockers.', policy_version: null, digest: 'skipped_no_expectations' },
            { shot_id: 'scene_001_shot_002', ok: false, failure_code: 'upstream_blockers', failure_category: 'generation_contract', message: 'Shot scene_001_shot_002 carries unresolved readiness blockers.', policy_version: null, digest: 'skipped_no_expectations' },
          ],
        },
      }),
    )
    fireEvent.click(generate)
    expect(onGenerate).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByTestId('preflight-status-blocked')).toBeInTheDocument())
    expect(screen.getByTestId('preflight-authorization-failures')).toHaveTextContent('unresolved readiness blockers')
  })

  it('single take: nothing preselected, exact prompt excerpt, spend ack, one id on confirm', async () => {
    const longPrompt = `TAKE PROMPT Dreama holds the silence. ${'x'.repeat(562)}TAILMARKER-BEYOND-600${'y'.repeat(200)}`
    const preflight = readyPreflight({
      credit_ceiling_credits: 300,
      credit_ceiling_env_var: 'RUNWAY_RENDER_MAX_CREDITS',
      entries: [
        {
          ...readyShot(1),
          prompt: longPrompt,
          character_focus: ['Dreama'],
          prior_render_submissions: 2,
          cost_estimate: { model: 'router', duration_seconds: 5, estimated_credits: 60, estimated: true },
        },
        readyShot(2),
      ],
    })
    mockPreflight.mockResolvedValue(preflight)
    const onGenerateSingleShot = vi.fn()
    await renderResolvedPanel({ onGenerateSingleShot })
    expect(screen.getByTestId('single-take-section')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('single-take-toggle'))
    // Nothing preselected: no confirm surface until a shot is picked.
    expect(screen.getByTestId('single-take-dialog')).toBeInTheDocument()
    expect(screen.queryByTestId('single-take-confirm')).toBeNull()
    // One network call so far (the initial preflight); opening picks nothing.
    expect(mockPreflight).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByDisplayValue('sbs_001'))
    const confirm = screen.getByTestId('single-take-confirm')
    expect(confirm).toHaveTextContent('1 Runway submission')
    expect(confirm).toHaveTextContent('2 prior Runway submissions')
    expect(confirm).toHaveTextContent('Characters: Dreama')
    expect(confirm).toHaveTextContent('Duration: 5s')
    expect(confirm).toHaveTextContent(longPrompt.slice(0, 600))
    expect(confirm).not.toHaveTextContent('TAILMARKER-BEYOND-600')
    expect(screen.getByTestId('single-take-estimate')).toHaveTextContent('Runway cost estimate (advisory')
    expect(screen.getByTestId('single-take-estimate')).toHaveTextContent('60 credits')
    expect(screen.getByTestId('single-take-estimate')).toHaveTextContent('ceiling 300 (RUNWAY_RENDER_MAX_CREDITS)')
    // Spend checkbox gates the confirm button.
    const button = screen.getByTestId('single-take-confirm-button')
    expect(button).toBeDisabled()
    fireEvent.click(screen.getByText(/I understand this spends Runway credits/))
    expect(button).not.toBeDisabled()
    fireEvent.click(button)
    expect(onGenerateSingleShot).toHaveBeenCalledTimes(1)
    expect(onGenerateSingleShot).toHaveBeenCalledWith({
      storyboardShotIds: ['sbs_001'],
      allowFullPackage: false,
      acknowledgeUnknownCost: true,
    })
  })

  it('single take: hidden while the scene is blocked', async () => {
    mockPreflight.mockResolvedValue(blockedPreflight())
    await renderResolvedPanel({ onGenerateSingleShot: vi.fn() })
    expect(screen.getByTestId('preflight-status-blocked')).toBeInTheDocument()
    expect(screen.queryByTestId('single-take-section')).toBeNull()
  })

  it('shows the actual per-shot prompt without truncation and Prompt unavailable when absent', async () => {
    const noPrompt = readyPreflight()
    noPrompt.manifest!.shots = noPrompt.manifest!.shots!.map((shot, index) => ({
      ...shot,
      shot_prompt: index === 0 ? shot.shot_prompt : '',
    }))
    mockPreflight.mockResolvedValue(noPrompt)
    await renderResolvedPanel()
    openManifestShot(1)
    expect(screen.getByTestId('shot-prompt-1')).toHaveTextContent('Shot 1 prompt text')
    const shot2 = screen.getByTestId('manifest-shot-2')
    fireEvent.click(shot2.querySelector('button')!)
    expect(screen.getByTestId('shot-prompt-2')).toHaveTextContent('Prompt unavailable')
  })
})

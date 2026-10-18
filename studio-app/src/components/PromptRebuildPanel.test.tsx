// @vitest-environment jsdom
// PromptRebuildPanel: explicit rebuild, unticked per-shot confirms with
// before/after diffs, skipped/refused reporting, clone notice.
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import PromptRebuildPanel from './PromptRebuildPanel'
import { rebuildShotPrompts, type StoryboardShot } from '../lib/studioApi'

vi.mock('../lib/studioApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/studioApi')>()
  return { ...actual, rebuildShotPrompts: vi.fn() }
})

const mockRebuild = vi.mocked(rebuildShotPrompts)

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function testShot(shotId: string, shotNumber: number): StoryboardShot {
  return {
    storyboard_shot_id: `sbs_${shotId}`,
    blueprint_id: 'sbp_test',
    version_id: 'sbv_test',
    project_id: 'project_test',
    scene_id: 'scene_001',
    shot_id: shotId,
    shot_number: shotNumber,
    status: 'draft',
    intent: {},
    visual_plan: {},
    continuity_plan: {},
    render_contract: {
      provider_neutral_prompt: 'A held look.',
      prompt_components: [],
      structured_parameters: {},
      reference_assets: [],
      duration_seconds: 5,
      aspect_ratio: '16:9',
      seed_locked: false,
      render_readiness: 'ready',
      render_blockers: [],
      provenance: {},
    },
    department_notes: [],
    rationale: '',
    locked: false,
    created_at: '',
    updated_at: '',
    metadata: {},
  }
}

const shots = [testShot('scene_001_shot_001', 1), testShot('scene_001_shot_002', 2)]

function renderPanel(versionStatus: string | null = 'draft') {
  return render(
    <PromptRebuildPanel
      blueprintId="sbp_test"
      versionId="sbv_test"
      versionStatus={versionStatus}
      shots={shots}
      onChanged={() => {}}
    />,
  )
}

describe('PromptRebuildPanel', () => {
  it('explains approved-clone versus draft-in-place before anything runs', () => {
    renderPanel('approved')
    expect(screen.getByText(/mints exactly one new draft/)).toBeInTheDocument()
    cleanup()
    renderPanel('draft')
    expect(screen.getByText(/updates its shots in place/)).toBeInTheDocument()
  })

  it('lists confirm-required shots unticked with diffs and rebuilds only ticked ones', async () => {
    mockRebuild.mockResolvedValueOnce({
      blueprint_id: 'sbp_test',
      version_id: 'sbv_test',
      cloned_from_version_id: null,
      rebuilt: [],
      skipped_hand_edited: [],
      refused_empty_block: [],
      confirm_required: [
        {
          shot_id: 'scene_001_shot_001',
          storyboard_shot_id: 'sbs_scene_001_shot_001',
          before_sha256: 'aaa',
          after_sha256: 'bbb',
          before: 'Legacy builder wording.',
          after: 'Current builder wording.',
        },
      ],
      reference_lock_info: [],
      rebuilt_by: 'creator',
    })
    renderPanel()
    fireEvent.click(screen.getByTestId('prompt-rebuild-run'))
    await waitFor(() => expect(mockRebuild).toHaveBeenCalledWith('sbp_test', 'sbv_test', []))
    const checkbox = screen.getByTestId('rebuild-confirm-scene_001_shot_001')
    expect(checkbox).not.toBeChecked()
    const confirmButton = screen.getByTestId('prompt-rebuild-confirmed')
    expect(confirmButton).toBeDisabled()
    fireEvent.click(confirmButton)
    expect(mockRebuild).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByTestId('rebuild-diff-toggle-scene_001_shot_001'))
    expect(screen.getByText('Legacy builder wording.')).toBeInTheDocument()
    expect(screen.getByText('Current builder wording.')).toBeInTheDocument()

    mockRebuild.mockResolvedValueOnce({
      blueprint_id: 'sbp_test',
      version_id: 'sbv_test',
      cloned_from_version_id: null,
      rebuilt: [
        {
          shot_id: 'scene_001_shot_001',
          storyboard_shot_id: 'sbs_scene_001_shot_001',
          before_sha256: 'aaa',
          after_sha256: 'bbb',
          block_characters: ['MAYA'],
        },
      ],
      skipped_hand_edited: [],
      refused_empty_block: [],
      confirm_required: [],
      reference_lock_info: [],
      rebuilt_by: 'creator',
    })
    fireEvent.click(checkbox)
    fireEvent.click(confirmButton)
    await waitFor(() =>
      expect(mockRebuild).toHaveBeenCalledWith('sbp_test', 'sbv_test', ['scene_001_shot_001']),
    )
    await waitFor(() => expect(screen.getByText(/Shot 1 rebuilt/)).toBeInTheDocument())
    expect(screen.getByText(/locked block: MAYA/)).toBeInTheDocument()
  })

  it('reports skipped hand-edits, refusals, and the new-draft notice', async () => {
    mockRebuild.mockResolvedValueOnce({
      blueprint_id: 'sbp_test',
      version_id: 'sbv_new',
      cloned_from_version_id: 'sbv_test',
      rebuilt: [],
      skipped_hand_edited: ['scene_001_shot_001'],
      refused_empty_block: ['scene_001_shot_002'],
      confirm_required: [],
      reference_lock_info: [{ character_name: 'MAYA', lock_status: 'locked' }],
      rebuilt_by: 'creator',
    })
    renderPanel('approved')
    fireEvent.click(screen.getByTestId('prompt-rebuild-run'))
    await waitFor(() => expect(screen.getByTestId('prompt-rebuild-summary')).toBeInTheDocument())
    expect(screen.getByText(/New draft version created/)).toBeInTheDocument()
    expect(screen.getByText(/Skipped hand-edited/)).toBeInTheDocument()
    expect(screen.getByText(/Refused/)).toBeInTheDocument()
    expect(screen.getByText(/information only/)).toBeInTheDocument()
  })

  it('surfaces backend errors without losing the panel', async () => {
    mockRebuild.mockRejectedValueOnce(new Error('Prompt rebuild runs only on the current version'))
    renderPanel()
    fireEvent.click(screen.getByTestId('prompt-rebuild-run'))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/only on the current version/))
  })
})

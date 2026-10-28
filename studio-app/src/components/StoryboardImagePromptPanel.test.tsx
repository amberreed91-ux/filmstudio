// @vitest-environment jsdom
// D4 image prompt panel: UTF-16 counter, gate states, removed summary,
// edit gating, and explicit approve (never auto-approves on render).
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import StoryboardImagePromptPanel from './StoryboardImagePromptPanel'
import { removedSummary, stateLabel } from '../lib/storyboardPromptCopy'
import {
  approveShotImagePrompt,
  editShotImagePrompt,
  reapproveShotImagePrompt,
  utf16Length,
  type StoryboardShot,
} from '../lib/studioApi'

vi.mock('../lib/studioApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/studioApi')>()
  return {
    ...actual,
    deriveShotImagePrompt: vi.fn(),
    editShotImagePrompt: vi.fn(),
    approveShotImagePrompt: vi.fn(),
    reapproveShotImagePrompt: vi.fn(),
  }
})

const mockEdit = vi.mocked(editShotImagePrompt)
const mockApprove = vi.mocked(approveShotImagePrompt)
const mockReapprove = vi.mocked(reapproveShotImagePrompt)

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function shot(overrides: Partial<StoryboardShot> = {}): StoryboardShot {
  return {
    storyboard_shot_id: 'sbs_test_001',
    blueprint_id: 'sbp_test',
    version_id: 'sbv_test',
    project_id: 'project_test',
    scene_id: 'scene_001',
    shot_id: 'scene_001_shot_001',
    shot_number: 1,
    status: 'draft',
    intent: {},
    visual_plan: {},
    continuity_plan: {},
    render_contract: {
      provider_neutral_prompt: 'A held look across the platform.',
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
    ...overrides,
  }
}

describe('utf16Length', () => {
  it('counts UTF-16 code units, not code points', () => {
    expect(utf16Length('abc')).toBe(3)
    // Non-BMP characters (e.g. emoji) occupy two UTF-16 units each.
    expect(utf16Length('🎬')).toBe(2)
    expect(utf16Length('a🎬b')).toBe(4)
    expect(utf16Length('')).toBe(0)
  })
})

describe('removedSummary', () => {
  it('summarizes the compactor record for human review', () => {
    expect(
      removedSummary({
        origin: 'compactor',
        rules_applied_json: JSON.stringify(['drop_rationale', 'drop_duplicates']),
        dropped_segments_json: JSON.stringify(['a', 'b', 'c']),
        chars_removed: 812,
      }),
    ).toBe('compactor removed 812 chars · rules: drop_rationale, drop_duplicates · 3 segments dropped')
  })

  it('stays silent for human edits and empty records', () => {
    expect(removedSummary({ origin: 'human' })).toBeNull()
    expect(removedSummary(null)).toBeNull()
    expect(removedSummary({ origin: 'compactor' })).toBeNull()
  })
})

describe('StoryboardImagePromptPanel', () => {
  it('shows the gate message and blocks board language for a proposal', () => {
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={{
          image_prompt: 'A look across the platform, golden hour.',
          origin: 'compactor',
          status: 'proposed',
          state: 'unapproved',
          gate_message: 'Shot scene_001_shot_001: image prompt is a proposal, not yet approved.',
          utf16_length: 42,
          chars_removed: 900,
          rules_applied_json: JSON.stringify(['drop_rationale']),
          dropped_segments_json: JSON.stringify(['x']),
        }}
        onChanged={() => {}}
      />,
    )
    expect(screen.getByText(/image prompt is a proposal, not yet approved/)).toBeInTheDocument()
    expect(screen.getByText(/compactor removed 900 chars/)).toBeInTheDocument()
    expect(screen.getByTestId('image-prompt-count-1')).toHaveTextContent(
      `${utf16Length('A look across the platform, golden hour.')}/1000 UTF-16`,
    )
    // Rendering never approves.
    expect(mockApprove).not.toHaveBeenCalled()
  })

  it('marks the counter red when the draft exceeds 1000 UTF-16 units', () => {
    const long = `x${'🎬'.repeat(600)}`
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={{ image_prompt: long, state: 'over_limit', gate_message: 'over the limit', utf16_length: utf16Length(long) }}
        onChanged={() => {}}
      />,
    )
    const counter = screen.getByTestId('image-prompt-count-1')
    expect(counter).toHaveTextContent('— over the limit')
    expect(counter.className).toContain('text-rose-300')
    expect(screen.getByTestId('image-prompt-approve-1')).toBeDisabled()
    expect(screen.getByTestId('image-prompt-save-1')).toBeDisabled()
  })

  it('names the visible reason when Save is disabled over the limit', () => {
    const long = `x${'🎬'.repeat(600)}`
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={{ image_prompt: long, state: 'over_limit', gate_message: 'over the limit', utf16_length: utf16Length(long) }}
        onChanged={() => {}}
      />,
    )
    // Fix A UX trap: the silently-disabled Save button must show a visible reason.
    expect(screen.getByTestId('image-prompt-overlimit-1')).toHaveTextContent(/Save disabled/)
    expect(screen.getByTestId('image-prompt-save-1')).toHaveAttribute('title', expect.stringMatching(/over the/))
  })

  it('approves explicitly and refreshes through onChanged', async () => {
    const onChanged = vi.fn()
    mockApprove.mockResolvedValue({ status: 'approved' })
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={{ image_prompt: 'A look.', state: 'unapproved', status: 'proposed', origin: 'compactor' }}
        onChanged={onChanged}
      />,
    )
    fireEvent.click(screen.getByTestId('image-prompt-approve-1'))
    await waitFor(() => expect(mockApprove).toHaveBeenCalledWith('sbp_test', 'sbs_test_001'))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it('saves hand edits and surfaces backend errors', async () => {
    mockEdit.mockRejectedValueOnce(new Error('Image prompt is 1001 UTF-16 units'))
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={{ image_prompt: 'A look.', state: 'unapproved' }}
        onChanged={() => {}}
      />,
    )
    fireEvent.change(screen.getByTestId('image-prompt-edit-1'), { target: { value: 'A longer look.' } })
    fireEvent.click(screen.getByTestId('image-prompt-save-1'))
    await waitFor(() => expect(mockEdit).toHaveBeenCalledWith('sbp_test', 'sbs_test_001', 'A longer look.'))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('1001 UTF-16 units'))
  })

  it('shows the ready state once approved', () => {
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={{ image_prompt: 'A look.', state: 'ready', status: 'approved', origin: 'human', approved_by: 'creator', render_ready: true }}
        onChanged={() => {}}
      />,
    )
    expect(screen.getByText('render-ready')).toBeInTheDocument()
  })
})

describe('stateLabel (honest box)', () => {
  it('names the situation and the next step instead of echoing state words', () => {
    expect(stateLabel('missing')).toMatch(/No image prompt yet/)
    expect(stateLabel('unapproved')).toMatch(/saving is not approving/)
    expect(stateLabel('stale')).toMatch(/Board text changed/)
    expect(stateLabel('over_limit')).toMatch(/Over the Runway limit/)
    expect(stateLabel('ready')).toBe('render-ready')
  })

  it('renders the honest label in the badge', () => {
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={{ image_prompt: 'A look.', state: 'stale', status: 'approved', origin: 'human' }}
        onChanged={() => {}}
      />,
    )
    expect(screen.getByText(/Board text changed/)).toBeInTheDocument()
  })
})

describe('re-approve against rebuilt text', () => {
  function staleApproved() {
    return {
      image_prompt: 'A look.',
      state: 'stale',
      status: 'approved',
      origin: 'human',
      approved_by: 'creator',
    } as const
  }

  it('offers re-approval only for stale previously-approved prompts', () => {
    const { unmount } = render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={staleApproved()}
        onChanged={() => {}}
      />,
    )
    expect(screen.getByTestId('image-prompt-reapprove-1')).toBeInTheDocument()
    expect(screen.getByTestId('image-prompt-reapprove-confirm-1')).not.toBeChecked()
    unmount()
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={{ image_prompt: 'A look.', state: 'unapproved', status: 'proposed', origin: 'compactor' }}
        onChanged={() => {}}
      />,
    )
    expect(screen.queryByTestId('image-prompt-reapprove-1')).not.toBeInTheDocument()
  })

  it('shows the canonical before/after diff from the rebuild record', () => {
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot({ metadata: { prompt_rebuild: { before_prompt: 'Old board text.', after_prompt: 'New board text.' } } })}
        entry={staleApproved()}
        onChanged={() => {}}
      />,
    )
    expect(screen.getByTestId('image-prompt-rebuild-before-1')).toHaveTextContent('Old board text.')
    expect(screen.getByTestId('image-prompt-rebuild-after-1')).toHaveTextContent('New board text.')
  })

  it('keeps the button disabled until the per-shot confirm is ticked', async () => {
    const onChanged = vi.fn()
    mockReapprove.mockResolvedValue({ status: 'approved' })
    render(
      <StoryboardImagePromptPanel
        blueprintId="sbp_test"
        shot={shot()}
        entry={staleApproved()}
        onChanged={onChanged}
      />,
    )
    const button = screen.getByTestId('image-prompt-reapprove-1')
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(mockReapprove).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('image-prompt-reapprove-confirm-1'))
    expect(button).not.toBeDisabled()
    fireEvent.click(button)
    await waitFor(() => expect(mockReapprove).toHaveBeenCalledWith('sbp_test', 'sbs_test_001', true))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })
})

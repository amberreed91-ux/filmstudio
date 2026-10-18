// @vitest-environment jsdom
// AI camera approval control — creator decision workflow tests.
//
// Contract under test: the control is an explicit, per-shot creator action
// over the backend's existing approval workflow. It shows the pending AI
// suggestion verbatim, states what approving locks and that a new draft
// version is created, binds the request to the version on screen, and never
// approves anything by merely rendering (no auto-approve on load).
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import AiCameraApproval from './AiCameraApproval'
import { approveAiCamera, type StoryboardShot } from '../lib/studioApi'

vi.mock('../lib/studioApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/studioApi')>()
  return {
    ...actual,
    approveAiCamera: vi.fn(),
  }
})

const mockApprove = vi.mocked(approveAiCamera)

const FRAMING = 'Wide establishing shot. Camera far back. Full environment visible.'

const shot = (overrides: Partial<StoryboardShot> = {}): StoryboardShot =>
  ({
    storyboard_shot_id: 'sbs_a7648698ad00',
    blueprint_id: 'sbp_1',
    version_id: 'sbv_3b88a1e0ef95',
    project_id: 'project_5907c60cddbc',
    scene_id: 'scene_002',
    shot_id: 'scene_002_shot_001',
    shot_number: 1,
    status: 'approved',
    intent: {},
    visual_plan: { framing: FRAMING },
    continuity_plan: {},
    render_contract: {
      provider_neutral_prompt: 'Recovered board prompt.',
      prompt_components: [],
      structured_parameters: {},
      reference_assets: [],
      duration_seconds: 5,
      aspect_ratio: '16:9',
      render_readiness: 'blocked',
      render_blockers: [],
      provenance: {},
    },
    department_notes: [],
    rationale: '',
    locked: false,
    created_at: '2026-09-26T19:30:21Z',
    updated_at: '2026-09-26T20:17:28Z',
    metadata: {},
    ...overrides,
  }) as StoryboardShot

function renderControl(props: Partial<Parameters<typeof AiCameraApproval>[0]> = {}) {
  return render(
    <AiCameraApproval
      projectId="project_5907c60cddbc"
      sceneId="scene_002"
      shot={shot()}
      onApproved={vi.fn()}
      {...props}
    />,
  )
}

afterEach(() => {
  cleanup()
  mockApprove.mockReset()
})

describe('AiCameraApproval', () => {
  it('shows the AI-suggested framing verbatim with provenance and no auto-approval', () => {
    renderControl()
    expect(screen.getByText(/Camera far back\. Full environment visible\./)).toBeInTheDocument()
    expect(screen.getByText('AI_SUGGESTED')).toBeInTheDocument()
    expect(screen.getByText(/new draft storyboard version/i)).toBeInTheDocument()
    expect(screen.getByText(/Continuity review/i)).toBeInTheDocument()
    expect(mockApprove).not.toHaveBeenCalled()
  })

  it('sends the version binding on approval', async () => {
    mockApprove.mockResolvedValue({
      storyboard_shot_id: 'sbs_new_clone',
      version_id: 'sbv_new_draft',
      approved_camera: { framing: FRAMING },
      approved_by: 'creator',
    })
    const onApproved = vi.fn()
    renderControl({ onApproved })

    fireEvent.click(screen.getByTestId('approve-ai-camera-1'))
    await waitFor(() => expect(mockApprove).toHaveBeenCalledTimes(1))
    expect(mockApprove).toHaveBeenCalledWith(
      'project_5907c60cddbc',
      'scene_002',
      'sbs_a7648698ad00',
      { approvedBy: 'creator', expectedVersionId: 'sbv_3b88a1e0ef95' },
    )
    await waitFor(() => expect(onApproved).toHaveBeenCalledTimes(1))
    expect(await screen.findByText(/approved for this shot/i)).toBeInTheDocument()
  })

  it('shows the locked values after a persisted approval', async () => {
    mockApprove.mockResolvedValue({
      storyboard_shot_id: 'sbs_new_clone',
      version_id: 'sbv_new_draft',
      approved_camera: { framing: FRAMING },
      approved_by: 'creator',
    })
    renderControl()
    fireEvent.click(screen.getByTestId('approve-ai-camera-1'))
    await waitFor(() => expect(screen.getByText(/Locked: framing:/i)).toBeInTheDocument())
    expect(screen.getByText(/A new draft storyboard version was created/i)).toBeInTheDocument()
  })

  it('surfaces a refused approval instead of pretending it succeeded', async () => {
    mockApprove.mockRejectedValue(new Error('Camera approval refused: version mismatch'))
    renderControl()
    fireEvent.click(screen.getByTestId('approve-ai-camera-1'))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/version mismatch/i))
    expect(screen.queryByText(/approved for this shot/i)).not.toBeInTheDocument()
  })

  it('shows a persisted approval state instead of a second decision button', () => {
    renderControl({
      shot: shot({
        render_contract: {
          ...shot().render_contract,
          structured_parameters: { camera_plan: { framing: FRAMING } },
        },
      }),
    })
    expect(screen.getByText(/Camera decision approved/i)).toBeInTheDocument()
    expect(screen.queryByTestId('approve-ai-camera-1')).not.toBeInTheDocument()
    expect(mockApprove).not.toHaveBeenCalled()
  })

  it('shows no pending suggestion when the visual plan carries no framing', () => {
    renderControl({ shot: shot({ visual_plan: { framing: '' } }) })
    expect(screen.getByText(/No pending AI camera suggestion/i)).toBeInTheDocument()
    expect(screen.queryByTestId('approve-ai-camera-1')).not.toBeInTheDocument()
  })
})

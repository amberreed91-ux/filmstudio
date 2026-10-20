// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { SceneDirectionPanel } from './SceneDirectionPanel'
import { buildScene002Fixture } from './__fixtures__/sceneDirectionFixture'
import { useSceneDirection } from '../hooks/useSceneDirection'
import type { CoverageObligationStatus, SceneDirection } from '../lib/sceneDirectionApi'

vi.mock('../hooks/useSceneDirection', () => ({ useSceneDirection: vi.fn() }))

const editCoverage = vi.fn()
const editLine = vi.fn()
const save = vi.fn()
let activeData: SceneDirection = buildScene002Fixture()

function mockScene(scene: SceneDirection, dirty = false) {
  activeData = scene
  vi.mocked(useSceneDirection).mockReturnValue({
    data: activeData, busy: false, dirty, error: '', editLine, removeLine: vi.fn(), addLine: vi.fn(),
    editCoverage, editHandoff: vi.fn(), editSettingReference: vi.fn(), save, reload: vi.fn(),
  } as unknown as ReturnType<typeof useSceneDirection>)
}

type ContentSpec = { id: string; text: string; shot?: number; omitted?: boolean }
type DialogueSpec = { id: string; text: string; character: string; shot?: number; omitted?: boolean }

/** Compact scene builder mirroring the live contract for grid tests. */
function buildGridScene(options: { shotCount: number; contents: ContentSpec[]; dialogue: DialogueSpec[]; version?: string }): SceneDirection {
  const statusOf = (entry: { shot?: number; omitted?: boolean }): CoverageObligationStatus =>
    entry.omitted ? 'EXPLICITLY_OMITTED' : entry.shot != null ? 'ASSIGNED' : 'UNASSIGNED'
  const shotIdOf = (shot?: number): string | null => (shot == null ? null : `grid_shot_00${shot}`)
  const shots = Array.from({ length: options.shotCount }, (_, index) => ({
    shot_id: `grid_shot_00${index + 1}`,
    shot_number: index + 1,
    shot_kind: '',
    locked: false,
    opening_state: '',
    action_change: '',
    ending_state: '',
    frame_url: null,
    saved_frame_url: null,
    frame_changed: false,
    previous_ending_state: '',
    dialogue_disposition: 'UNASSIGNED' as const,
    dialogue_disposition_reason: '',
  }))
  return {
    project_id: 'grid-film',
    scene_id: 'grid-scene',
    version_id: options.version ?? 'grid_v1',
    version_status: 'approved',
    canonical_setting_id: null,
    setting_reference_decision: null,
    setting_reference_options: [],
    dialogue: options.dialogue.map(line => ({
      line_id: line.id, character: line.character, text: line.text, shot_id: shotIdOf(line.shot),
    })),
    coverage_obligations: [
      ...options.contents.map(unit => ({
        obligation_type: 'content' as const,
        obligation_id: unit.id,
        source_text: unit.text,
        source_start: null,
        source_end: null,
        status: statusOf(unit),
        shot_id: shotIdOf(unit.shot),
        reason: unit.omitted ? 'skipped on purpose in fixture' : '',
        reason_required: Boolean(unit.omitted),
      })),
      ...options.dialogue.map(line => ({
        obligation_type: 'dialogue' as const,
        obligation_id: line.id,
        source_text: line.text,
        source_start: null,
        source_end: null,
        status: statusOf(line),
        shot_id: shotIdOf(line.shot),
        reason: line.omitted ? 'skipped on purpose in fixture' : '',
        reason_required: Boolean(line.omitted),
      })),
    ],
    coverage_decisions: [
      ...options.contents.map(unit => ({
        obligation_type: 'content' as const,
        obligation_id: unit.id,
        status: statusOf(unit),
        shot_id: shotIdOf(unit.shot),
        reason: unit.omitted ? 'skipped on purpose in fixture' : '',
      })),
      ...options.dialogue.map(line => ({
        obligation_type: 'dialogue' as const,
        obligation_id: line.id,
        status: statusOf(line),
        shot_id: shotIdOf(line.shot),
        reason: line.omitted ? 'skipped on purpose in fixture' : '',
      })),
      ...shots.map(shot => ({
        obligation_type: 'shot_content' as const,
        obligation_id: shot.shot_id,
        status: 'UNASSIGNED' as const,
        shot_id: null,
        reason: '',
      })),
      ...shots.map(shot => ({
        obligation_type: 'shot_dialogue' as const,
        obligation_id: shot.shot_id,
        status: 'UNASSIGNED' as const,
        shot_id: null,
        reason: '',
      })),
    ],
    coverage_blocked: false,
    coverage_blockers: [],
    unassigned_line_ids: options.dialogue.filter(line => line.shot == null && !line.omitted).map(line => line.id),
    shots,
    saved: true,
  }
}

/** scene_001-shaped: V.O. cue, spoken fragments, one spoken line, skipped CUT TO, shot 5 empty. */
function buildScene001Shaped(): SceneDirection {
  return buildGridScene({
    shotCount: 5,
    contents: [
      { id: 'content_a', text: 'Chicago is alive. The L train moves through the skyline.', shot: 1 },
      { id: 'content_b', text: 'Lake Michigan reflecting the sunset.', shot: 2 },
      { id: 'content_c', text: 'Maya walks through the city watching small moments.', shot: 3 },
      { id: 'content_vo', text: 'MAYA (V.O.)', shot: 4 },
      { id: 'content_d1', text: 'People think the end of the world is fire.', shot: 4 },
      { id: 'content_d2', text: 'But the hardest part is remembering when it was beautiful.', shot: 4 },
      { id: 'content_cut', text: 'CUT TO:', omitted: true },
    ],
    dialogue: [
      { id: 'dialogue_1', text: 'People think the end of the world is fire. But the hardest part is remembering when it was beautiful.', character: 'MAYA', shot: 4 },
    ],
  })
}

const renderPanel = (onSaved: () => void = vi.fn()) =>
  render(<SceneDirectionPanel projectId="grid-film" sceneId="grid-scene" versionId="grid_v1" activeShotNumber={1} onSaved={onSaved} />)

beforeEach(() => {
  cleanup()
  vi.clearAllMocks()
  mockScene(buildScene001Shaped())
})

describe('Coverage grid (section C replacement)', () => {
  it('asks which shot each line belongs to and reports shots covered', () => {
    renderPanel()
    expect(screen.getByText('Which shot does each line belong to?')).toBeTruthy()
    expect(screen.getByTestId('coverage-grid-progress')).toHaveTextContent('4 of 5 shots covered')
    for (let shot = 1; shot <= 5; shot += 1) {
      expect(screen.getByTestId(`coverage-grid-column-${shot}`)).toHaveTextContent(`Shot ${shot}`)
    }
  })

  it('renders one dot per shot for every line with text-plus-color column status', () => {
    renderPanel()
    const grid = screen.getByTestId('coverage-grid')
    for (const rowId of ['content_a', 'content_b', 'content_c', 'content_vo', 'content_d1', 'content_d2', 'dialogue_1']) {
      expect(within(screen.getByTestId(`coverage-grid-row-${rowId}`)).getAllByRole('button')).toHaveLength(5)
    }
    // Dots are real keyboard-operable buttons with pressed state.
    const selected = within(screen.getByTestId('coverage-grid-row-content_a')).getByRole('button', { name: 'Assign content_a to Shot 1' })
    expect(selected.tagName).toBe('BUTTON')
    expect(selected).toHaveAttribute('aria-pressed', 'true')
    expect(within(screen.getByTestId('coverage-grid-row-content_a')).getByRole('button', { name: 'Assign content_a to Shot 2' })).toHaveAttribute('aria-pressed', 'false')
    // Covered columns read green with a line count; the empty column reads red.
    expect(screen.getByTestId('coverage-grid-column-4')).toHaveTextContent('4 lines')
    expect(screen.getByTestId('coverage-grid-column-4').textContent).toMatch(/4 lines/)
    expect(screen.getByTestId('coverage-grid-column-4').querySelector('span:last-child')?.className).toMatch(/emerald/)
    expect(screen.getByTestId('coverage-grid-column-5')).toHaveTextContent('Needs a line')
    expect(screen.getByTestId('coverage-grid-column-5').querySelector('span:last-child')?.className).toMatch(/rose/)
    expect(grid).toBeTruthy()
  })

  it('tapping a content dot assigns through the existing editCoverage call with the same payload', () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Assign content_a to Shot 2' }))
    expect(editCoverage).toHaveBeenCalledWith('content', 'content_a', { status: 'ASSIGNED', shot_id: 'grid_shot_002', reason: '' })
  })

  it('tapping a dialogue dot mirrors the assignment to the spoken line', () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: 'Assign spoken line dialogue_1 to Shot 2' }))
    expect(editCoverage).toHaveBeenCalledWith('dialogue', 'dialogue_1', { status: 'ASSIGNED', shot_id: 'grid_shot_002', reason: '' })
    expect(editLine).toHaveBeenCalledWith('dialogue_1', { shot_id: 'grid_shot_002' })
  })

  it('turns the donor column red when its last line moves away', () => {
    mockScene(buildGridScene({
      shotCount: 2,
      contents: [{ id: 'content_lone', text: 'Only line on shot 1.', shot: 1 }],
      dialogue: [],
    }))
    renderPanel()
    expect(screen.getByTestId('coverage-grid-column-1')).toHaveTextContent('1 line')
    fireEvent.click(screen.getByRole('button', { name: 'Assign content_lone to Shot 2' }))
    expect(editCoverage).toHaveBeenCalledWith('content', 'content_lone', { status: 'ASSIGNED', shot_id: 'grid_shot_002', reason: '' })

    cleanup()
    vi.clearAllMocks()
    mockScene(buildGridScene({
      shotCount: 2,
      contents: [{ id: 'content_lone', text: 'Only line on shot 1.', shot: 2 }],
      dialogue: [],
    }))
    renderPanel()
    expect(screen.getByTestId('coverage-grid-column-1')).toHaveTextContent('Needs a line')
    expect(screen.getByTestId('coverage-grid-column-1').querySelector('span:last-child')?.className).toMatch(/rose/)
    expect(screen.getByTestId('coverage-grid-status')).toHaveTextContent('Shot 1 needs a line.')
  })

  it('keeps the V.O. cue, each spoken line, and the stay-together block as separate rows', () => {
    renderPanel()
    expect(screen.getByTestId('coverage-grid-row-content_vo')).toHaveTextContent('V.O. cue')
    expect(screen.getByTestId('coverage-grid-row-dialogue_1')).toHaveTextContent('Spoken line')
    const block = screen.getByTestId('coverage-grid-row-spoken-block')
    expect(block).toHaveTextContent('stays together on one shot')
    expect(within(block).getAllByRole('button')).toHaveLength(5)
    // The block is together on shot 4, matching every spoken line.
    expect(within(block).getByRole('button', { name: 'Keep all spoken lines together on Shot 4' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(within(block).getByRole('button', { name: 'Keep all spoken lines together on Shot 2' }))
    expect(editCoverage).toHaveBeenCalledWith('dialogue', 'dialogue_1', { status: 'ASSIGNED', shot_id: 'grid_shot_002', reason: '' })
    expect(editLine).toHaveBeenCalledWith('dialogue_1', { shot_id: 'grid_shot_002' })
  })

  it('renders skipped-on-purpose lines muted with no dots', () => {
    renderPanel()
    const row = screen.getByTestId('coverage-grid-row-content_cut')
    expect(row).toHaveTextContent('CUT TO:')
    expect(row).toHaveTextContent('skipped on purpose')
    expect(within(row).queryAllByRole('button')).toHaveLength(0)
  })

  it('blocks save with a message while a shot is empty and saves once every shot has a line', async () => {
    const onSaved = vi.fn()
    render(<SceneDirectionPanel projectId="grid-film" sceneId="grid-scene" versionId="grid_v1" activeShotNumber={1} onSaved={onSaved} />)
    expect(screen.getByText('Saving never changes your approved version.')).toBeTruthy()
    // The single save button stays enabled so the click can answer.
    const saveButton = screen.getByRole('button', { name: 'Save as new draft' })
    expect(saveButton).toBeEnabled()
    fireEvent.click(saveButton)
    expect(screen.getByTestId('coverage-grid-notice')).toHaveTextContent('Not yet: shot 5 still needs a line.')
    expect(save).not.toHaveBeenCalled()

    cleanup()
    vi.clearAllMocks()
    mockScene(buildGridScene({
      shotCount: 2,
      contents: [
        { id: 'content_1', text: 'First line.', shot: 1 },
        { id: 'content_2', text: 'Second line.', shot: 2 },
      ],
      dialogue: [],
    }), true)
    const coveredSaved = vi.fn()
    const { rerender } = render(<SceneDirectionPanel projectId="grid-film" sceneId="grid-scene" versionId="grid_v1" activeShotNumber={1} onSaved={coveredSaved} />)
    expect(screen.getByTestId('coverage-grid-status')).toHaveTextContent('Every shot has a line. You can save.')
    const successor = { ...activeData, version_id: 'grid_v2' }
    vi.mocked(save).mockResolvedValue(successor)
    fireEvent.click(screen.getByRole('button', { name: 'Save as new draft' }))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(coveredSaved).toHaveBeenCalledTimes(1)
    mockScene(successor)
    rerender(<SceneDirectionPanel projectId="grid-film" sceneId="grid-scene" versionId="grid_v1" activeShotNumber={1} onSaved={coveredSaved} />)
    await waitFor(() => expect(screen.getByTestId('save-success')).toHaveTextContent('Saved as new draft grid_v2'))
    expect(screen.getByTestId('save-success')).toHaveTextContent('Approved image prompts carry over where the shot text did not change.')
  })

  it('holds every advanced control inside the single collapsed Advanced section', () => {
    renderPanel()
    const advanced = screen.getByTestId('coverage-advanced')
    expect(advanced.tagName).toBe('DETAILS')
    expect(advanced).not.toHaveAttribute('open')
    expect(within(advanced).getByTestId('coverage-section-content')).toBeTruthy()
    expect(within(advanced).getByTestId('coverage-section-dialogue')).toBeTruthy()
    expect(within(advanced).getByTestId('coverage-section-shot-content')).toBeTruthy()
    expect(within(advanced).getByTestId('coverage-section-shot-dialogue')).toBeTruthy()
    expect(within(advanced).getByTestId('coverage-tab-content')).toBeTruthy()
  })

  it('builds generically for any scene size', () => {
    mockScene(buildScene002Fixture())
    renderPanel()
    expect(screen.getByTestId('coverage-grid-progress')).toHaveTextContent('0 of 5 shots covered')
    // 40 content rows plus 10 spoken lines plus the stay-together block row.
    expect(within(screen.getByTestId('coverage-grid-row-content_01')).getAllByRole('button')).toHaveLength(5)
    expect(within(screen.getByTestId('coverage-grid-row-line_01')).getAllByRole('button')).toHaveLength(5)
    expect(within(screen.getByTestId('coverage-grid-row-spoken-block')).getAllByRole('button')).toHaveLength(5)
    expect(screen.getByTestId('coverage-grid-status')).toHaveTextContent('Shots 1, 2, 3, 4 and 5 need a line.')
  })
})

describe('Coverage grid keyboard (one Tab stop per row)', () => {
  it('gives every script line exactly one Tab stop on its assigned dot', () => {
    mockScene(buildGridScene({
      shotCount: 3,
      contents: [
        { id: 'kb_a', text: 'First line.', shot: 2 },
        { id: 'kb_b', text: 'Second line.' },
        { id: 'kb_c', text: 'Third line.', omitted: true },
      ],
      dialogue: [
        { id: 'kb_d1', text: 'Spoken one.', character: 'MAYA', shot: 3 },
      ],
    }))
    renderPanel()
    // Assigned content rows: the owner's dot is the single tab stop.
    const dotsA = within(screen.getByTestId('coverage-grid-row-kb_a')).getAllByRole('button')
    expect(dotsA).toHaveLength(3)
    expect(dotsA.map(dot => dot.tabIndex)).toEqual([-1, 0, -1])
    // Unassigned rows: the first dot is the single tab stop.
    const dotsB = within(screen.getByTestId('coverage-grid-row-kb_b')).getAllByRole('button')
    expect(dotsB.map(dot => dot.tabIndex)).toEqual([0, -1, -1])
    // Dialogue rows behave the same.
    const dotsD = within(screen.getByTestId('coverage-grid-row-kb_d1')).getAllByRole('button')
    expect(dotsD.map(dot => dot.tabIndex)).toEqual([-1, -1, 0])
    // Skipped rows render no dots, so they are never tab stops.
    expect(within(screen.getByTestId('coverage-grid-row-kb_c')).queryAllByRole('button')).toHaveLength(0)
    // The stay-together block is one more single-stop group.
    const blockDots = within(screen.getByTestId('coverage-grid-row-spoken-block')).getAllByRole('button')
    expect(blockDots).toHaveLength(3)
    expect(blockDots.filter(dot => dot.tabIndex === 0)).toHaveLength(1)
  })

  it('moves between shots with arrows and selects, jumping with Home and End', () => {
    mockScene(buildGridScene({
      shotCount: 4,
      contents: [{ id: 'kb_move', text: 'Movable line.', shot: 1 }],
      dialogue: [],
    }))
    renderPanel()
    const dots = within(screen.getByTestId('coverage-grid-row-kb_move')).getAllByRole('button')
    dots[0].focus()
    expect(document.activeElement).toBe(dots[0])
    fireEvent.keyDown(dots[0], { key: 'ArrowRight' })
    expect(editCoverage).toHaveBeenCalledWith('content', 'kb_move', { status: 'ASSIGNED', shot_id: 'grid_shot_002', reason: '' })
    expect(document.activeElement).toBe(dots[1])
    fireEvent.keyDown(dots[1], { key: 'End' })
    expect(editCoverage).toHaveBeenCalledWith('content', 'kb_move', { status: 'ASSIGNED', shot_id: 'grid_shot_004', reason: '' })
    expect(document.activeElement).toBe(dots[3])
    fireEvent.keyDown(dots[3], { key: 'ArrowRight' })
    expect(editCoverage).toHaveBeenCalledWith('content', 'kb_move', { status: 'ASSIGNED', shot_id: 'grid_shot_001', reason: '' })
    expect(document.activeElement).toBe(dots[0])
    fireEvent.keyDown(dots[0], { key: 'Home' })
    expect(editCoverage).toHaveBeenCalledWith('content', 'kb_move', { status: 'ASSIGNED', shot_id: 'grid_shot_001', reason: '' })
    // Labels keep naming the line and the shot for every dot in the row.
    expect(dots[1]).toHaveAttribute('aria-label', 'Assign kb_move to Shot 2')
  })

  it('selects spoken lines with arrows and mirrors the assignment', () => {
    mockScene(buildGridScene({
      shotCount: 3,
      contents: [],
      dialogue: [{ id: 'kb_sp', text: 'Spoken.', character: 'DRE', shot: 1 }],
    }))
    renderPanel()
    const dots = within(screen.getByTestId('coverage-grid-row-kb_sp')).getAllByRole('button')
    dots[0].focus()
    fireEvent.keyDown(dots[0], { key: 'ArrowLeft' })
    // Wraps to the last shot and selects it through the mirrored path.
    expect(editCoverage).toHaveBeenCalledWith('dialogue', 'kb_sp', { status: 'ASSIGNED', shot_id: 'grid_shot_003', reason: '' })
    expect(editLine).toHaveBeenCalledWith('kb_sp', { shot_id: 'grid_shot_003' })
    expect(document.activeElement).toBe(dots[2])
  })

  it('falls back to the first dot when the owner names a shot off the board', () => {
    const scene = buildGridScene({
      shotCount: 3,
      contents: [{ id: 'kb_ghost', text: 'Haunted line.', shot: 1 }],
      dialogue: [],
    })
    scene.coverage_decisions = scene.coverage_decisions.map(row =>
      row.obligation_type === 'content' && row.obligation_id === 'kb_ghost'
        ? { ...row, shot_id: 'grid_shot_009' }
        : row,
    )
    mockScene(scene)
    renderPanel()
    const dots = within(screen.getByTestId('coverage-grid-row-kb_ghost')).getAllByRole('button')
    expect(dots.map(dot => dot.tabIndex)).toEqual([0, -1, -1])
  })
})

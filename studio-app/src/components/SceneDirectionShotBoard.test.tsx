// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { SceneDirectionPanel } from './SceneDirectionPanel'
import { buildScene002Fixture } from './__fixtures__/sceneDirectionFixture'
import { useSceneDirection } from '../hooks/useSceneDirection'
import type { SceneDirection } from '../lib/sceneDirectionApi'

vi.mock('../hooks/useSceneDirection', () => ({ useSceneDirection: vi.fn() }))

const editCoverage = vi.fn()
const save = vi.fn()
let activeData: SceneDirection = buildScene002Fixture()

function mockScene(scene: SceneDirection, dirty = false) {
  activeData = scene
  vi.mocked(useSceneDirection).mockReturnValue({
    data: activeData, busy: false, dirty, error: '', editLine: vi.fn(), removeLine: vi.fn(), addLine: vi.fn(),
    editCoverage, editHandoff: vi.fn(), editSettingReference: vi.fn(), save, reload: vi.fn(),
  } as unknown as ReturnType<typeof useSceneDirection>)
}

const renderPanel = () => render(<SceneDirectionPanel projectId="project_5907c60cddbc" sceneId="scene_002" versionId="sbv_a6096cb1fea5" activeShotNumber={1} onSaved={vi.fn()} />)

/** Assign content lines to shots in the fixture scene. */
function assignContent(scene: SceneDirection, entries: Array<[string, string]>): SceneDirection {
  const next = structuredClone(scene)
  next.coverage_decisions = next.coverage_decisions.map(row => {
    const hit = row.obligation_type === 'content' ? entries.find(([line]) => line === row.obligation_id) : undefined
    return hit ? { ...row, status: 'ASSIGNED' as const, shot_id: hit[1] } : row
  })
  return next
}

function assignDialogue(scene: SceneDirection, shotId: string): SceneDirection {
  const next = structuredClone(scene)
  next.coverage_decisions = next.coverage_decisions.map(row =>
    row.obligation_type === 'dialogue' ? { ...row, status: 'ASSIGNED' as const, shot_id: shotId } : row)
  next.dialogue = next.dialogue.map(line => ({ ...line, shot_id: shotId }))
  return next
}

beforeEach(() => {
  cleanup()
  vi.clearAllMocks()
  mockScene(buildScene002Fixture())
  Element.prototype.scrollIntoView = vi.fn()
})

describe('Shot board (section C rework)', () => {
  it('renders five chips with text state and scrolls to the card on click', () => {
    let scene = buildScene002Fixture()
    scene = assignContent(scene, [['content_01', 'scene_002_shot_002']])
    mockScene(scene)
    renderPanel()
    const nav = screen.getByRole('navigation', { name: 'Shot chips' })
    const chips = within(nav).getAllByRole('button')
    expect(chips).toHaveLength(5)
    expect(chips[1]).toHaveTextContent('Shot 2 · covered')
    expect(chips[4]).toHaveTextContent('Shot 5 · needs a line')
    // Text plus color: covered reads emerald, stuck reads rose.
    expect(chips[1].className).toMatch(/emerald/)
    expect(chips[4].className).toMatch(/rose/)
    fireEvent.click(chips[4])
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
    expect(document.getElementById('shot-board-card-scene_002_shot_005')).toBeTruthy()
  })

  it('shows shot progress and the blocking summary from the payload', () => {
    const scene = assignContent(buildScene002Fixture(), [['content_01', 'scene_002_shot_002']])
    scene.coverage_blockers = ['canonical dialogue unresolved: line_01']
    mockScene(scene)
    renderPanel()
    expect(screen.getByTestId('shot-board-progress')).toHaveTextContent('1 of 5 shots covered')
    const summaries = screen.getAllByRole('status').map(node => node.textContent || '')
    expect(summaries.some(text => text.includes('What is blocking render: canonical dialogue unresolved: line_01'))).toBe(true)
  })

  it('renders each per-state message with kind and next action', () => {
    const base = buildScene002Fixture()
    base.shots = base.shots.map(shot => shot.shot_id === 'scene_002_shot_005' ? { ...shot, shot_kind: '' } : shot)
    const scene = assignContent(base, [['content_01', 'scene_002_shot_002']])
    mockScene(scene)
    renderPanel()
    // Covered card names its lines.
    expect(within(screen.getByTestId('shot-board-card-2')).getByText(/Covered — 1 line explicitly assigned/)).toBeTruthy()
    // Ineligible empty card explains why silence is unavailable and what to do.
    expect(within(screen.getByTestId('shot-board-card-4')).getByText(/Needs a line/)).toBeTruthy()
    expect(within(screen.getByTestId('shot-board-card-4')).getByText(/cannot be silent/)).toBeTruthy()
    expect(within(screen.getByTestId('shot-board-card-5')).getByText(/Assign a line in section A above, or move a line here/)).toBeTruthy()
    // Eligible empty card offers silence with a required reason box.
    expect(within(screen.getByTestId('shot-board-card-1')).getByText(/Silence allowed/)).toBeTruthy()
    // Recorded kind, or \"kind not recorded\" when the builder stored nothing.
    expect(screen.getAllByText(/kind not recorded/).length).toBeGreaterThan(0)
  })

  it('never renders a one-option select without a reason and next action', () => {
    mockScene(buildScene002Fixture())
    renderPanel()
    const section = screen.getByTestId('coverage-section-shot-content')
    for (const select of within(section).queryAllByRole('combobox')) {
      const options = within(select as HTMLElement).getAllByRole('option').filter(option => !(option as HTMLOptionElement).disabled)
      expect(options.length).toBeGreaterThanOrEqual(2)
    }
  })

  it('previews both sides of a move and wires the apply to the existing editCoverage payload', () => {
    const scene = assignContent(buildScene002Fixture(), [
      ['content_01', 'scene_002_shot_002'],
      ['content_02', 'scene_002_shot_004'],
      ['content_03', 'scene_002_shot_004'],
      ['content_04', 'scene_002_shot_004'],
    ])
    mockScene(scene)
    renderPanel()
    const card = screen.getByTestId('shot-board-card-5')
    fireEvent.change(within(card).getByRole('combobox', { name: 'Move a line to shot 5' }), { target: { value: 'content_02' } })
    const preview = within(card).getAllByRole('status').map(node => node.textContent || '')
    expect(preview.some(text => text.includes('Shot 4 keeps 2 lines. Shot 5 gets 1.'))).toBe(true)
    fireEvent.click(within(card).getByRole('button', { name: 'Move line to Shot 5' }))
    expect(editCoverage).toHaveBeenCalledWith('content', 'content_02', { shot_id: 'scene_002_shot_005' })
  })

  it('blocks a move that would empty the donor and suggests another line', () => {
    const scene = assignContent(buildScene002Fixture(), [
      ['content_01', 'scene_002_shot_002'],
      ['content_02', 'scene_002_shot_004'],
      ['content_03', 'scene_002_shot_004'],
    ])
    mockScene(scene)
    renderPanel()
    const card = screen.getByTestId('shot-board-card-5')
    const select = within(card).getByRole('combobox', { name: 'Move a line to shot 5' })
    // The donor-emptying option is disabled with its reason inline.
    const lone = within(select).getByRole('option', { name: /content_01/ }) as HTMLOptionElement
    expect(lone.disabled).toBe(true)
    expect(lone.textContent).toMatch(/would leave that shot empty/)
    fireEvent.change(select, { target: { value: 'content_01' } })
    const blocked = within(card).getAllByRole('status').map(node => node.textContent || '').join('\n')
    expect(blocked).toMatch(/would be left with no lines/)
    expect(blocked).toMatch(/Try content_02/)
    expect(within(card).getByRole('button', { name: 'Move line to Shot 5' })).toBeDisabled()
  })

  it('shows the V.O. cue and spoken lines separately with the block kept together', () => {
    const base = buildScene002Fixture()
    base.coverage_obligations = base.coverage_obligations.map(row =>
      row.obligation_id === 'content_01' ? { ...row, source_text: 'MAYA (V.O.)' } : row)
    let scene = assignContent(base, [['content_01', 'scene_002_shot_004']])
    scene = assignDialogue(scene, 'scene_002_shot_004')
    mockScene(scene)
    renderPanel()
    const group = screen.getByTestId('vo-group')
    expect(group).toHaveTextContent('Cue content_01')
    expect(group).toHaveTextContent('Shot 4')
    expect(group).toHaveTextContent('Spoken-dialogue block · one unit that stays together · together on Shot 4')

    cleanup()
    vi.clearAllMocks()
    mockScene(assignDialogue(base, 'scene_002_shot_002'))
    renderPanel()
    expect(screen.getByTestId('vo-group')).toHaveTextContent('no shot yet — assign it in section A')
  })

  it('keeps the static what-saving-does note and names the new draft version after save', async () => {
    mockScene(buildScene002Fixture(), true)
    const onSaved = vi.fn()
    const panel = <SceneDirectionPanel projectId="project_5907c60cddbc" sceneId="scene_002" versionId="sbv_a6096cb1fea5" activeShotNumber={1} onSaved={onSaved} />
    const { rerender } = render(panel)
    expect(screen.getByText(/What saving does: saving mints a new DRAFT successor version/)).toBeTruthy()
    expect(screen.getByText(/Approved image prompts move across where the shot text did not change/)).toBeTruthy()
    // The save response model returns version_id but no prompt-carry fields,
    // so the note stays static and only the draft version is dynamic. The
    // real hook swaps in the successor as the new data; emulate that here.
    const successor = { ...activeData, version_id: 'sbv_newdraft0001' }
    vi.mocked(save).mockResolvedValue(successor)
    fireEvent.click(screen.getByRole('button', { name: 'Review & save decisions' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm & save decisions' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))
    mockScene(successor)
    rerender(<SceneDirectionPanel projectId="project_5907c60cddbc" sceneId="scene_002" versionId="sbv_a6096cb1fea5" activeShotNumber={1} onSaved={onSaved} />)
    await waitFor(() => expect(screen.getByTestId('save-success')).toHaveTextContent('Saved as new draft sbv_newdraft0001'))
  })
})

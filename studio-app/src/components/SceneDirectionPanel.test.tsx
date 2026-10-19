// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { SceneDirectionPanel } from './SceneDirectionPanel'
import { buildScene002Fixture } from './__fixtures__/sceneDirectionFixture'
import { useSceneDirection } from '../hooks/useSceneDirection'
import type { SceneDirection, SettingReferenceOption } from '../lib/sceneDirectionApi'
import { LEGACY_SCENE002_REFERENCE_ID, SCENE002_SETTING_ID } from '../lib/settingReferenceApi'

vi.mock('../hooks/useSceneDirection', () => ({ useSceneDirection: vi.fn() }))

const exactOption: SettingReferenceOption = {
  ref_id: 'ref_set_canonical', image_url: 'https://assets.example.test/setting.png',
  target_type: 'setting', target_id: SCENE002_SETTING_ID, kind: 'environment',
  approval_state: 'approved', canonical: true,
}
/** Scene-targeted rows the API must never hand to the selector. */
const legacySceneTargetedOption: SettingReferenceOption = {
  ref_id: LEGACY_SCENE002_REFERENCE_ID, image_url: 'https://assets.example.test/legacy.png',
  target_type: 'setting', target_id: 'scene_002', kind: 'environment',
  approval_state: 'approved', canonical: true,
}
const wrongTargetOption: SettingReferenceOption = {
  ref_id: 'ref_set_other_entity', image_url: 'https://assets.example.test/other.png',
  target_type: 'setting', target_id: 'loc-other', kind: 'environment',
  approval_state: 'approved', canonical: true,
}

const data: SceneDirection = {
  project_id: 'film', scene_id: 'scene_1', version_id: 'v1', version_status: 'draft',
  canonical_setting_id: SCENE002_SETTING_ID,
  setting_reference_decision: null,
  setting_reference_options: [exactOption, legacySceneTargetedOption, wrongTargetOption],
  dialogue: [{ line_id: 'dlg1', character: 'MAYA', text: 'Exact canonical words.', shot_id: null }],
  coverage_obligations: [{ obligation_type: 'content' as const, obligation_id: 'content1', source_text: 'Maya stands.', source_start: 4, source_end: 16, status: 'UNASSIGNED' as const, shot_id: null, reason: '', reason_required: false }],
  coverage_decisions: [
    { obligation_type: 'content' as const, obligation_id: 'content1', status: 'UNASSIGNED' as const, shot_id: null, reason: '' },
    { obligation_type: 'dialogue' as const, obligation_id: 'dlg1', status: 'UNASSIGNED' as const, shot_id: null, reason: '' },
    { obligation_type: 'shot_dialogue' as const, obligation_id: 'shot1', status: 'UNASSIGNED' as const, shot_id: null, reason: '' },
    { obligation_type: 'shot_content' as const, obligation_id: 'shot1', status: 'UNASSIGNED' as const, shot_id: null, reason: '' },
  ],
  coverage_blocked: true, coverage_blockers: ['unresolved coverage'], unassigned_line_ids: ['dlg1'],
  shots: [{ shot_id: 'shot1', shot_number: 1, shot_kind: 'close_up', locked: false, opening_state: '', action_change: '', ending_state: '', frame_url: null, saved_frame_url: null, frame_changed: false, previous_ending_state: '', dialogue_disposition: 'UNASSIGNED', dialogue_disposition_reason: '' }],
  saved: false,
}

const editCoverage = vi.fn()
const editLine = vi.fn()
const editSettingReference = vi.fn()
const save = vi.fn()
let activeData: SceneDirection = structuredClone(data)

function mockEditor(overrides: Partial<SceneDirection> = {}, dirty = false) {
  activeData = { ...structuredClone(data), ...overrides }
  vi.mocked(useSceneDirection).mockReturnValue({
    data: activeData, busy: false, dirty, error: '', editLine, removeLine: vi.fn(), addLine: vi.fn(),
    editCoverage, editHandoff: vi.fn(), editSettingReference, save, reload: vi.fn(),
  } as unknown as ReturnType<typeof useSceneDirection>)
}

const renderPanel = () => render(<SceneDirectionPanel projectId="film" sceneId="scene_1" versionId="v1" activeShotNumber={1} onSaved={vi.fn()} />)

beforeEach(() => {
  cleanup()
  vi.clearAllMocks()
  mockEditor()
})

describe('SceneDirectionPanel coverage decisions', () => {
  it('shows exact canonical speaker/text, content, and unresolved status with no shot selected', () => {
    renderPanel()
    expect(screen.getByText('Exact canonical words.')).toBeTruthy()
    expect(screen.getByText('MAYA · canonical source wording')).toBeTruthy()
    expect(screen.getByText('Maya stands.')).toBeTruthy()
    expect(screen.getByText('Current status: Unassigned')).toBeTruthy()
    expect(screen.getByRole('combobox', { name: 'Coverage decision for dialogue 1' })).toHaveValue('UNASSIGNED')
    expect(screen.queryByRole('combobox', { name: 'Owning shot for dialogue 1' })).toBeNull()
    expect(screen.getByText('Coverage remains blocked until every required obligation has an explicit supported decision.')).toBeTruthy()
  })

  it('serializes a creator-selected owner and offers reason-required omission', () => {
    renderPanel()
    const lineCard = screen.getByText('Exact canonical words.').closest('fieldset')!
    fireEvent.change(within(lineCard).getByRole('combobox', { name: 'Coverage decision for dialogue 1' }), { target: { value: 'ASSIGNED' } })
    expect(editCoverage).toHaveBeenCalledWith('dialogue', 'dlg1', { status: 'ASSIGNED', shot_id: null, reason: '' })
    expect(editLine).toHaveBeenCalledWith('dlg1', { shot_id: null })

    cleanup()
    mockEditor({ coverage_decisions: data.coverage_decisions.map(row => row.obligation_type === 'dialogue' ? { ...row, status: 'ASSIGNED' as const } : row) }, true)
    renderPanel()
    const assignedCard = screen.getByText('Exact canonical words.').closest('fieldset')!
    fireEvent.change(within(assignedCard).getByRole('combobox', { name: 'Owning shot for dialogue 1' }), { target: { value: 'shot1' } })
    expect(editCoverage).toHaveBeenCalledWith('dialogue', 'dlg1', { shot_id: 'shot1' })
    expect(editLine).toHaveBeenCalledWith('dlg1', { shot_id: 'shot1' })

    cleanup()
    mockEditor({ coverage_decisions: data.coverage_decisions.map(row => row.obligation_type === 'dialogue' ? { ...row, status: 'EXPLICITLY_OMITTED' as const } : row) }, true)
    renderPanel()
    expect(screen.getByRole('textbox', { name: 'Omission reason for dialogue 1' })).toBeRequired()
  })

  it('keeps unresolved obligations visible in explicit coverage decisions', () => {
    renderPanel()
    expect(screen.getByRole('combobox', { name: 'Coverage decision for content 1' })).toHaveValue('UNASSIGNED')
    expect(screen.getByRole('combobox', { name: 'Dialogue disposition for shot 1' })).toHaveValue('UNASSIGNED')
    // Shot 1 is a close-up with no lines: the board replaces the dead
    // one-option disposition select with text that says why and what to do.
    expect(screen.queryByRole('combobox', { name: 'Content disposition for shot 1' })).toBeNull()
    expect(screen.getByText(/Needs a line — this close_up cannot be silent/)).toBeTruthy()
  })
})

describe('SceneDirectionPanel setting reference selection', () => {
  it('accepts empty options and never selects a reference automatically', () => {
    mockEditor({ setting_reference_options: [] })
    renderPanel()
    const select = screen.getByRole('combobox', { name: 'Canonical setting reference' })
    expect(select).toHaveValue('')
    expect(screen.getByRole('option', { name: 'Choose a reference' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: new RegExp(SCENE002_SETTING_ID) })).toBeNull()
    expect(editSettingReference).not.toHaveBeenCalled()
    expect(save).not.toHaveBeenCalled()
  })

  it('names the exact setting entity and the unblock steps when no option is eligible', () => {
    mockEditor({ setting_reference_options: [] })
    renderPanel()
    expect(screen.getByText(new RegExp(`No approved references are registered for ${SCENE002_SETTING_ID} yet`))).toBeTruthy()
    expect(screen.getByText(/register the image as a candidate for that exact setting/)).toBeTruthy()
    expect(screen.getByText(/References approved for a different setting never appear here/)).toBeTruthy()
  })

  it('never auto-selects a reference when exact options are available', () => {
    renderPanel()
    expect(screen.getByRole('combobox', { name: 'Canonical setting reference' })).toHaveValue('')
    expect(editSettingReference).not.toHaveBeenCalled()
  })

  it('submits the selected exact reference ID even when another canonical row has the same URI', () => {
    mockEditor({ setting_reference_options: [
      exactOption,
      { ...exactOption, ref_id: 'ref_set_same_uri', image_url: exactOption.image_url },
    ] })
    renderPanel()
    fireEvent.change(screen.getByRole('combobox', { name: 'Canonical setting reference' }), { target: { value: 'ref_set_canonical' } })
    expect(editSettingReference).toHaveBeenCalledTimes(1)
    expect(editSettingReference).toHaveBeenCalledWith({
      canonical_setting_id: SCENE002_SETTING_ID,
      reference_id: 'ref_set_canonical',
    })

    // Clearing the choice is an explicit "no selection", never an inferred one.
    cleanup()
    editSettingReference.mockClear()
    mockEditor({ setting_reference_decision: { canonical_setting_id: SCENE002_SETTING_ID, reference_id: 'ref_set_canonical' } })
    renderPanel()
    expect(screen.getByRole('combobox', { name: 'Canonical setting reference' })).toHaveValue('ref_set_canonical')
    fireEvent.change(screen.getByRole('combobox', { name: 'Canonical setting reference' }), { target: { value: '' } })
    expect(editSettingReference).toHaveBeenCalledWith(null)
  })

  it('rejects an invalid or missing selection instead of inventing one', () => {
    renderPanel()
    const select = screen.getByRole('combobox', { name: 'Canonical setting reference' })
    fireEvent.change(select, { target: { value: 'ref_not_an_option' } })
    fireEvent.change(select, { target: { value: LEGACY_SCENE002_REFERENCE_ID } })
    // No ineligible reference ID may ever reach the decision; an unset choice
    // stays an explicit "no selection" instead of an inferred reference.
    const recorded = editSettingReference.mock.calls.map(([decision]) => decision)
    expect(recorded.every(decision => decision == null)).toBe(true)
    const renderedValues = screen.getAllByRole('option').map(option => (option as HTMLOptionElement).value)
    expect(renderedValues).not.toContain('ref_not_an_option')
    expect(renderedValues).not.toContain(LEGACY_SCENE002_REFERENCE_ID)
  })

  it('fails closed for candidate, unapproved, noncanonical, wrong-kind, wrong-target, and legacy options', () => {
    mockEditor({ setting_reference_options: [
      exactOption,
      { ...exactOption, ref_id: 'ref_candidate', approval_state: 'candidate', canonical: false },
      { ...exactOption, ref_id: 'ref_unapproved', approval_state: 'rejected', canonical: true },
      { ...exactOption, ref_id: 'ref_noncanonical', approval_state: 'approved', canonical: false },
      { ...exactOption, ref_id: 'ref_wrong_kind', kind: 'character_full' },
      legacySceneTargetedOption,
      wrongTargetOption,
    ] })
    renderPanel()
    const renderedValues = screen.getAllByRole('option').map(option => (option as HTMLOptionElement).value)
    expect(renderedValues).toContain(exactOption.ref_id)
    for (const ineligible of ['ref_candidate', 'ref_unapproved', 'ref_noncanonical', 'ref_wrong_kind', LEGACY_SCENE002_REFERENCE_ID, wrongTargetOption.ref_id]) {
      expect(renderedValues).not.toContain(ineligible)
    }
  })

  it('never presents legacy scene-targeted or wrong-target references as options', () => {
    mockEditor({ setting_reference_options: [exactOption, legacySceneTargetedOption, wrongTargetOption] })
    renderPanel()
    const options = screen.getAllByRole('option').map(option => option.textContent || '')
    expect(options.some(text => text.includes(exactOption.ref_id))).toBe(true)
    expect(options.some(text => text.includes(LEGACY_SCENE002_REFERENCE_ID))).toBe(false)
    expect(options.some(text => text.includes('scene_002'))).toBe(false)
    expect(options.some(text => text.includes('loc-other'))).toBe(false)
  })
})

describe('SceneDirectionPanel coverage workspace (60 obligations)', () => {
  function mockScene(scene: SceneDirection, dirty = false) {
    activeData = scene
    vi.mocked(useSceneDirection).mockReturnValue({
      data: activeData, busy: false, dirty, error: '', editLine, removeLine: vi.fn(), addLine: vi.fn(),
      editCoverage, editHandoff: vi.fn(), editSettingReference, save, reload: vi.fn(),
    } as unknown as ReturnType<typeof useSceneDirection>)
  }

  it('displays all 60 obligations as UNRESOLVED with 0 / 60 progress and decides nothing on open', () => {
    mockScene(buildScene002Fixture())
    renderPanel()
    // Progress indicator reports the real state: nothing resolved.
    expect(screen.getByTestId('coverage-resolved-count')).toHaveTextContent('0 / 60 resolved')
    // Four sections, each labeled with its obligation count.
    expect(screen.getByTestId('coverage-tab-content')).toHaveTextContent('40 obligations')
    expect(screen.getByTestId('coverage-tab-dialogue')).toHaveTextContent('10 obligations')
    expect(screen.getByTestId('coverage-tab-shot_content')).toHaveTextContent('5 obligations')
    expect(screen.getByTestId('coverage-tab-shot_dialogue')).toHaveTextContent('5 obligations')
    // Every one of the 60 obligations is visible and visibly UNRESOLVED.
    expect(within(screen.getByTestId('coverage-section-content')).getAllByText('UNRESOLVED')).toHaveLength(40)
    expect(within(screen.getByTestId('coverage-section-dialogue')).getAllByText('UNRESOLVED')).toHaveLength(10)
    expect(within(screen.getByTestId('coverage-section-shot-content')).getAllByText('UNRESOLVED')).toHaveLength(5)
    expect(within(screen.getByTestId('coverage-section-shot-dialogue')).getAllByText('UNRESOLVED')).toHaveLength(5)
    // All five approved shots are listed by identity.
    for (const shotId of ['scene_002_shot_001', 'scene_002_shot_002', 'scene_002_shot_003', 'scene_002_shot_004', 'scene_002_shot_005']) {
      expect(screen.getAllByText(shotId).length).toBeGreaterThanOrEqual(3)
    }
    // Opening the interface resolves nothing and saves nothing.
    expect(editCoverage).not.toHaveBeenCalled()
    expect(editSettingReference).not.toHaveBeenCalled()
    expect(save).not.toHaveBeenCalled()
  })

  it('reports the resolved count as creator decisions are recorded', () => {
    const scene = buildScene002Fixture()
    scene.dialogue = scene.dialogue.map(line => ({ ...line, shot_id: 'scene_002_shot_002' }))
    scene.coverage_decisions = scene.coverage_decisions.map(row => {
      if (row.obligation_type === 'dialogue') return { ...row, status: 'ASSIGNED' as const, shot_id: 'scene_002_shot_002' }
      if (row.obligation_type === 'content' && row.obligation_id === 'content_01') return { ...row, status: 'ASSIGNED' as const, shot_id: 'scene_002_shot_003' }
      return row
    })
    mockScene(scene)
    renderPanel()
    // 10 dialogue + 1 content explicitly assigned, plus the two shot-level
    // obligations those creator assignments satisfy: 13 of 60.
    expect(screen.getByTestId('coverage-resolved-count')).toHaveTextContent('13 / 60 resolved')
    expect(within(screen.getByTestId('coverage-section-dialogue')).queryAllByText('UNRESOLVED')).toHaveLength(0)
    expect(within(screen.getByTestId('coverage-section-shot-dialogue')).getAllByText('UNRESOLVED')).toHaveLength(4)
    expect(within(screen.getByTestId('coverage-section-shot-content')).getAllByText('UNRESOLVED')).toHaveLength(4)
    expect(within(screen.getByTestId('coverage-section-content')).getAllByText('UNRESOLVED')).toHaveLength(39)
  })

  it('offers only the decision types the contract permits in each section', () => {
    mockScene(buildScene002Fixture())
    renderPanel()
    const optionValues = (name: string) => within(screen.getByRole('combobox', { name })).getAllByRole('option').map(option => (option as HTMLOptionElement).value)
    // Content and dialogue: assigned or explicitly omitted — never silence.
    expect(optionValues('Coverage decision for content 1')).toEqual(['UNASSIGNED', 'ASSIGNED', 'EXPLICITLY_OMITTED'])
    expect(optionValues('Coverage decision for dialogue 1')).toEqual(['UNASSIGNED', 'ASSIGNED', 'EXPLICITLY_OMITTED'])
    // Shot dialogue: omission or intentional silence with a reason.
    expect(optionValues('Dialogue disposition for shot 1')).toEqual(['UNASSIGNED', 'INTENTIONAL_SILENCE', 'EXPLICITLY_OMITTED'])
    // Shot content: intentional silence only on an eligible establishing shot;
    // an ineligible empty shot shows why instead of a one-option select.
    expect(optionValues('Content disposition for shot 1')).toEqual(['UNASSIGNED', 'INTENTIONAL_SILENCE'])
    expect(screen.queryByRole('combobox', { name: 'Content disposition for shot 2' })).toBeNull()
    expect(within(screen.getByTestId('shot-board-card-2')).getByText(/Needs a line/)).toBeTruthy()
  })

  it('requires an explicit shot for assignments and a reason for omission or silence', () => {
    const scene = buildScene002Fixture()
    scene.coverage_decisions = scene.coverage_decisions.map(row => {
      if (row.obligation_type === 'content' && row.obligation_id === 'content_01') return { ...row, status: 'ASSIGNED' as const }
      if (row.obligation_type === 'content' && row.obligation_id === 'content_02') return { ...row, status: 'EXPLICITLY_OMITTED' as const }
      if (row.obligation_type === 'dialogue' && row.obligation_id === 'line_01') return { ...row, status: 'ASSIGNED' as const }
      if (row.obligation_type === 'shot_dialogue' && row.obligation_id === 'scene_002_shot_001') return { ...row, status: 'EXPLICITLY_OMITTED' as const }
      if (row.obligation_type === 'shot_content' && row.obligation_id === 'scene_002_shot_001') return { ...row, status: 'INTENTIONAL_SILENCE' as const }
      return row
    })
    mockScene(scene)
    renderPanel()
    expect(screen.getByRole('combobox', { name: 'Owning shot for content 1' })).toBeRequired()
    expect(screen.getByRole('textbox', { name: 'Omission reason for content 2' })).toBeRequired()
    expect(screen.getByRole('combobox', { name: 'Owning shot for dialogue 1' })).toBeRequired()
    expect(screen.getByRole('textbox', { name: 'Dialogue disposition reason for shot 1' })).toBeRequired()
    expect(screen.getByRole('textbox', { name: 'Content disposition reason for shot 1' })).toBeRequired()
  })

  it('reviews every decision before commit and saves only on explicit confirm', async () => {
    mockScene(buildScene002Fixture(), true)
    const onSaved = vi.fn()
    render(<SceneDirectionPanel projectId="project_5907c60cddbc" sceneId="scene_002" versionId="sbv_a6096cb1fea5" activeShotNumber={1} onSaved={onSaved} />)
    // Opening never opens a review and never saves.
    expect(screen.queryByTestId('save-review')).toBeNull()
    expect(save).not.toHaveBeenCalled()
    // The review lists what would be committed, before anything is committed.
    fireEvent.click(screen.getByRole('button', { name: 'Review & save decisions' }))
    const review = screen.getByTestId('save-review')
    expect(review).toHaveTextContent('0 resolved and 60 UNRESOLVED')
    expect(review).toHaveTextContent('sbv_a6096cb1fea5')
    expect(review).toHaveTextContent('The approved source version is not modified')
    const rows = Array.from(review.querySelectorAll('li')).map(row => row.textContent || '')
    expect(rows).toHaveLength(60)
    expect(rows[0]).toContain('content · content_01 → UNRESOLVED')
    expect(save).not.toHaveBeenCalled()
    // Back to editing without saving.
    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }))
    expect(screen.queryByTestId('save-review')).toBeNull()
    expect(save).not.toHaveBeenCalled()
    // Only the explicit confirm commits.
    fireEvent.click(screen.getByRole('button', { name: 'Review & save decisions' }))
    vi.mocked(save).mockResolvedValue(activeData)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm & save decisions' }))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(onSaved).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.queryByTestId('save-review')).toBeNull())
  })
})

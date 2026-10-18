// @vitest-environment jsdom
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ReferenceSpace from './ReferenceSpace'
import { APP_ROUTES } from '../routes'

const mocks = vi.hoisted(() => ({
  listCharacters: vi.fn(),
  listScenes: vi.fn(),
  getReferenceLibrary: vi.fn(),
  listReferenceAssets: vi.fn(),
  addReferenceLibraryAsset: vi.fn(),
  uploadReferenceLibraryAsset: vi.fn(),
  approveReferenceLibraryAsset: vi.fn(),
  designateReferenceLibraryCanonical: vi.fn(),
  removeReferenceLibraryAsset: vi.fn(),
  approveLook: vi.fn(),
  reviseLook: vi.fn(),
  lookRefresh: vi.fn(),
  generateCasting: vi.fn(),
  lookOverride: null as null | unknown[],
  listRenderJobs: vi.fn(),
  getPrevisImagePresets: vi.fn(),
  generatePrevisImage: vi.fn(),
  bindGeneratedStillToShot: vi.fn(),
}))

const defaultLook = {
  character_id: 'char-maya',
  project_id: 'project-a',
  name: 'Maya',
  age: null,
  description: 'Lead crossing the loft at dawn.',
  physical_description: '',
  visual_prompt_summary: '',
  status: 'locked',
  version: 2,
  profile_revision: 'rev-7',
  face_image_url: 'https://cdn.test/maya-face.png',
  body_image_url: null,
  approved_at: '2026-10-10T00:00:00Z',
  candidates: [],
}

vi.mock('../lib/studioApi', () => ({
  listCharacters: mocks.listCharacters,
  listScenes: mocks.listScenes,
  listRenderJobs: mocks.listRenderJobs,
  buildStudioApiUrl: (path: string) => `https://studio.test${path}`,
}))
vi.mock('../lib/previsImageApi', () => ({
  MAX_GENERATED_STILLS: 12,
  PREVIS_ASPECT_RATIOS: ['16:9', '1:1', '9:16'],
  resolveAssetUrl: (url: string | null | undefined) => (url ? (/^https?:\/\//.test(url) ? url : `https://studio.test${url}`) : null),
  getPrevisImagePresets: mocks.getPrevisImagePresets,
  generatePrevisImage: mocks.generatePrevisImage,
  bindGeneratedStillToShot: mocks.bindGeneratedStillToShot,
}))
vi.mock('../lib/visualTrainingApi', () => ({
  getReferenceLibrary: mocks.getReferenceLibrary,
  listReferenceAssets: mocks.listReferenceAssets,
  addReferenceLibraryAsset: mocks.addReferenceLibraryAsset,
  uploadReferenceLibraryAsset: mocks.uploadReferenceLibraryAsset,
  approveReferenceLibraryAsset: mocks.approveReferenceLibraryAsset,
  designateReferenceLibraryCanonical: mocks.designateReferenceLibraryCanonical,
  removeReferenceLibraryAsset: mocks.removeReferenceLibraryAsset,
}))
vi.mock('../hooks/useCharacterLooks', () => ({
  useCharacterLooks: () => ({
    looks: (mocks.lookOverride ?? [defaultLook]) as typeof defaultLook[],
    loading: false,
    error: '',
    busy: false,
    refresh: mocks.lookRefresh,
    approve: mocks.approveLook,
    revise: mocks.reviseLook,
    upload: vi.fn(),
    generate: mocks.generateCasting,
  }),
}))
vi.mock('../components/StudioShell', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectGuard', () => ({ default: ({ children }: { children: ReactNode }) => createElement('div', null, children) }))
vi.mock('../components/ProjectContextBar', () => ({ default: () => createElement('div', null, 'Project context') }))
vi.mock('../hooks/useProjectRouteContext', () => ({ useProjectRouteContext: () => ({ projectId: 'project-a', projectError: '' }) }))

const canonicalAsset = {
  ref_id: 'ref_canon_1',
  kind: 'character_face',
  image_url: 'https://cdn.test/maya-canon.png',
  source_shot_id: 'scene_001_shot_002',
  project_id: 'project-a',
  target_type: 'character',
  target_id: 'char-maya',
  category: 'face',
  approval_state: 'approved',
  canonical: true,
  source_kind: 'confirmed',
  reference_role: 'face',
  look_id: 'default',
  lock_status: 'locked',
}

const supportingAsset = {
  ref_id: 'ref_sup_1',
  kind: 'character_full',
  image_url: 'https://cdn.test/maya-full.png',
  source_shot_id: null,
  project_id: 'project-a',
  target_type: 'character',
  target_id: 'char-maya',
  category: 'full_body',
  approval_state: 'approved',
  canonical: false,
  source_kind: 'uploaded',
}

const candidateAsset = {
  ref_id: 'ref_cand_1',
  kind: 'character_full',
  image_url: 'https://cdn.test/maya-cand.png',
  source_shot_id: null,
  project_id: 'project-a',
  target_type: 'character',
  target_id: 'char-maya',
  category: 'face',
  approval_state: 'candidate',
  canonical: false,
  source_kind: 'uploaded',
}

const settingSupporting = {
  ref_id: 'ref_set_wide',
  kind: 'environment',
  image_url: 'https://cdn.test/harbor-wide.png',
  source_shot_id: null,
  project_id: 'project-a',
  target_type: 'setting',
  target_id: 'loc-harbor',
  category: 'wide',
  approval_state: 'approved',
  canonical: false,
  source_kind: 'uploaded',
}

const settingCandidate = {
  ref_id: 'ref_set_cand',
  kind: 'environment',
  image_url: 'https://cdn.test/harbor-cand.png',
  source_shot_id: null,
  project_id: 'project-a',
  target_type: 'setting',
  target_id: 'loc-harbor',
  category: 'wide',
  approval_state: 'candidate',
  canonical: false,
  source_kind: 'uploaded',
}

const settingLibrary = {
  project_id: 'project-a',
  target_type: 'setting',
  target_id: 'loc-harbor',
  canonical: null,
  supporting: [settingSupporting],
  candidates: [settingCandidate],
  categories: ['wide'],
  coverage: 'not_covered',
}

function spaceData({
  characters = [{ id: 'char-maya', project_id: 'project-a', name: 'Maya' }],
  assets = [canonicalAsset, supportingAsset, candidateAsset],
  library = { project_id: 'project-a', target_type: 'character', target_id: 'char-maya', canonical: canonicalAsset, supporting: [supportingAsset], candidates: [candidateAsset], categories: ['face'], coverage: 'covered' },
  scenes = [{ scene_id: 'scene_001', scene_name: 'Morning' }],
}: {
  characters?: unknown[]
  assets?: unknown[]
  library?: unknown
  scenes?: unknown[]
} = {}) {
  mocks.listCharacters.mockResolvedValue({ characters })
  mocks.listReferenceAssets.mockResolvedValue({ reference_assets: assets, count: assets.length })
  mocks.getReferenceLibrary.mockResolvedValue(library)
  mocks.listScenes.mockResolvedValue({ scenes })
  mocks.listRenderJobs.mockResolvedValue([
    { id: 'job-1', project_id: 'project-a', shot_id: 'scene_001_shot_001', provider: 'runway', status: 'complete', progress: 100, retry_count: 0, created_at: '', updated_at: '' },
    { id: 'job-2', project_id: 'project-a', shot_id: 'scene_001_shot_002', provider: 'runway', status: 'complete', progress: 100, retry_count: 0, created_at: '', updated_at: '' },
  ])
}

function renderSpace() {
  return render(createElement(MemoryRouter, { initialEntries: ['/studio/reference-space?project_id=project-a'] },
    createElement(Routes, null, createElement(Route, { path: '/studio/reference-space', element: createElement(ReferenceSpace) })),
  ))
}

const draftLookWithCasting = {
  ...defaultLook,
  status: 'draft',
  approved_at: null,
  face_image_url: null,
  candidates: [
    { image_url: 'https://cdn.test/maya-cast-1.png', role: 'face', source: 'Generated casting option — awaiting selection', generation_id: 'job-1', matches_current_profile: true },
    { image_url: 'https://cdn.test/maya-cast-2.png', role: 'face', source: 'Generated casting option — awaiting selection', generation_id: 'job-1', matches_current_profile: false },
  ],
  casting_generations: [],
}

const generatedCandidateAsset = {
  ref_id: 'ref_cast_abc',
  kind: 'character_face',
  image_url: 'https://cdn.test/maya-cast-1.png',
  source_shot_id: 'casting:job-1',
  project_id: 'project-a',
  target_type: 'character',
  target_id: 'char-maya',
  category: 'casting',
  approval_state: 'candidate',
  canonical: false,
  source_kind: 'generated',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.lookOverride = null
  mocks.approveLook.mockResolvedValue({ profile_revision: 'rev-7' })
  mocks.reviseLook.mockResolvedValue({})
  mocks.generateCasting.mockResolvedValue({ character_id: 'char-maya' })
  mocks.getPrevisImagePresets.mockResolvedValue({
    style_presets: [{ id: 'none', label: 'No style preset', prompt_fragment: '' }, { id: 'cinematic_35mm', label: 'Cinematic 35mm', prompt_fragment: 'shot on 35mm film' }],
    lighting_presets: [{ id: 'none', label: 'No lighting preset', prompt_fragment: '' }, { id: 'soft_window', label: 'Soft window', prompt_fragment: 'soft window light' }],
    aspect_ratios: ['16:9', '1:1', '9:16'],
    max_prompt_chars: 1200,
  })
  mocks.generatePrevisImage.mockResolvedValue({
    project_id: 'project-a',
    mode: 'character',
    image_url: '/outputs/reference_generation/project-a/still-1.png',
    seed: 314,
    aspect_ratio: '16:9',
    style_preset: 'cinematic_35mm',
    lighting_preset: 'soft_window',
    provider: 'dashscope',
    model: 'qwen-image-max',
    prompt: 'Maya at the loft window\nOne fictional character only.',
    created_at: '2026-10-17T00:00:00Z',
  })
  mocks.bindGeneratedStillToShot.mockResolvedValue({ ...candidateAsset, ref_id: 'ref_gen_1' })
  spaceData()
})
afterEach(cleanup)

describe('Reference Space', () => {
  it('distinguishes canonical, supporting, and candidate references with real provenance', async () => {
    renderSpace()
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    expect(await screen.findByTestId('reference-space-upload-input')).toBeInTheDocument()
    expect(screen.getByText('Canonical reference · locked')).toBeInTheDocument()
    expect(screen.getAllByText(/ref_canon_1/).length).toBeGreaterThan(0)
    expect(screen.getByText('Candidates awaiting approval (1)')).toBeInTheDocument()
    expect(screen.getByText(/Approval makes a candidate supporting evidence/)).toBeInTheDocument()
    expect(screen.getByText(/from shot/)).toBeInTheDocument()
    expect(screen.getByText(/scene_001_shot_002/)).toBeInTheDocument()
  })

  it('compares a candidate against the canonical reference without scores or auto-approval', async () => {
    const { container } = renderSpace()
    fireEvent.click(await screen.findByLabelText('Compare candidate ref_cand_1'))
    expect(await screen.findByText('Comparison · decision aid, not approval')).toBeInTheDocument()
    expect(screen.getByText('Current canonical reference')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/similarity|score|match %/i)
    expect(screen.queryByText(/auto-approved/)).toBeNull()
  })

  it('registers uploads and URLs as candidates and approves without touching canonical', async () => {
    mocks.uploadReferenceLibraryAsset.mockResolvedValue({ reference_asset: candidateAsset })
    mocks.addReferenceLibraryAsset.mockResolvedValue(candidateAsset)
    mocks.approveReferenceLibraryAsset.mockResolvedValue({ ...candidateAsset, approval_state: 'approved' })
    renderSpace()
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    expect(await screen.findByTestId('reference-space-upload-input')).toBeInTheDocument()

    const file = new File(['pixels'], 'wardrobe.png', { type: 'image/png' })
    fireEvent.change(screen.getByTestId('reference-space-upload-input'), { target: { files: [file] } })
    await waitFor(() => expect(mocks.uploadReferenceLibraryAsset).toHaveBeenCalled())
    expect(mocks.uploadReferenceLibraryAsset.mock.calls[0][1]).toBe('character')
    expect(mocks.uploadReferenceLibraryAsset.mock.calls[0][2]).toBe('char-maya')
    expect(await screen.findByText(/registered as a candidate/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Reference image URL'), { target: { value: 'https://cdn.test/extra.png' } })
    fireEvent.click(screen.getByLabelText('Add image URL reference'))
    await waitFor(() => expect(mocks.addReferenceLibraryAsset).toHaveBeenCalled())
    const added = mocks.addReferenceLibraryAsset.mock.calls[0][3] as { approval_state: string; canonical?: boolean }
    expect(added.approval_state).toBe('candidate')

    fireEvent.click(screen.getByLabelText('Approve candidate ref_cand_1'))
    await waitFor(() => expect(mocks.approveReferenceLibraryAsset).toHaveBeenCalledWith('project-a', 'character', 'char-maya', 'ref_cand_1'))
    expect(await screen.findByText(/canonical reference is unchanged/)).toBeInTheDocument()
  })

  it('keeps unavailable APIs distinct from empty collections and failures', async () => {
    spaceData()
    mocks.listCharacters.mockRejectedValue(new Error('characters offline'))
    renderSpace()
    expect(await screen.findByText(/Character list unavailable: characters offline/)).toBeInTheDocument()
    expect(screen.queryByText(/both failed to load/)).toBeNull()

    cleanup()
    spaceData({ characters: [], assets: [], scenes: [], library: { project_id: 'project-a', target_type: 'character', target_id: 'x', canonical: null, supporting: [], candidates: [], categories: [], coverage: 'not_covered' } })
    renderSpace()
    expect(await screen.findByText(/No characters are registered for this project yet/)).toBeInTheDocument()
    expect(screen.getByText(/No confirmed references are registered for this project yet/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('uses the authoritative look service for approve and revise, never local state', async () => {
    renderSpace()
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    expect(screen.queryByText('Approve look')).toBeNull()
    fireEvent.click(screen.getByText('Reopen as draft'))
    await waitFor(() => expect(mocks.reviseLook).toHaveBeenCalled())
    expect(await screen.findByText(/reopened as a draft revision/)).toBeInTheDocument()
  })

  it('links only to valid existing Studio workflows', async () => {
    const { container } = renderSpace()
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    const hrefs = Array.from(container.querySelectorAll('a')).map((anchor) => anchor.getAttribute('href') || '')
    expect(hrefs.length).toBeGreaterThan(0)
    expect(hrefs.every((href) => href.startsWith('/studio/'))).toBe(true)
    expect(hrefs.some((href) => href.startsWith('/studio/production-board?project_id=project-a'))).toBe(true)
    expect(hrefs.some((href) => href.startsWith('/studio/screening-room?project_id=project-a'))).toBe(true)
    expect(hrefs.some((href) => href.startsWith('/studio/archive?project_id=project-a'))).toBe(true)
  })

  it('starts casting generation from the character look section using the existing contract', async () => {
    mocks.lookOverride = [draftLookWithCasting]
    renderSpace()
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Casting direction'), { target: { value: 'softer light' } })
    fireEvent.click(screen.getByText('Generate 3 casting options'))
    await waitFor(() => expect(mocks.generateCasting).toHaveBeenCalled())
    const [look, direction] = mocks.generateCasting.mock.calls[0] as [typeof draftLookWithCasting, string]
    expect(look.character_id).toBe('char-maya')
    expect(direction).toBe('softer light')
    expect(await screen.findByText(/Casting generation started/)).toBeInTheDocument()
  })

  it('shows generation progress and failures truthfully', async () => {
    mocks.lookOverride = [{ ...draftLookWithCasting, casting_generations: [{ id: 'job-9', status: 'running', requested_count: 3, completed_count: 1, direction: '', error: null, created_at: '', matches_current_profile: true }] }]
    renderSpace()
    expect(await screen.findByText(/Generating casting options/)).toBeInTheDocument()
    cleanup()
    mocks.lookOverride = [{ ...draftLookWithCasting, casting_generations: [{ id: 'job-9', status: 'failed', requested_count: 3, completed_count: 0, direction: '', error: 'Provider offline', created_at: '', matches_current_profile: true }] }]
    renderSpace()
    expect(await screen.findByText('Provider offline')).toBeInTheDocument()
  })

  it('approves a selected generated candidate as the look face through the revision-safe path', async () => {
    mocks.lookOverride = [draftLookWithCasting]
    renderSpace()
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Select candidate 1 as face identity'))
    fireEvent.click(screen.getByText('Approve look with selected face'))
    await waitFor(() => expect(mocks.approveLook).toHaveBeenCalled())
    const [look, face] = mocks.approveLook.mock.calls[0] as [typeof draftLookWithCasting, string]
    expect(look.character_id).toBe('char-maya')
    expect(face).toBe('https://cdn.test/maya-cast-1.png')
    expect(await screen.findByText(/approved at revision/)).toBeInTheDocument()
  })

  it('explains a stale-profile approval rejection with a refresh path', async () => {
    mocks.lookOverride = [draftLookWithCasting]
    mocks.approveLook.mockResolvedValue(null)
    renderSpace()
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Select candidate 1 as face identity'))
    fireEvent.click(screen.getByText('Approve look with selected face'))
    expect(await screen.findByText(/profile may have changed/)).toBeInTheDocument()
    expect(await screen.findByText(/Refresh the library/)).toBeInTheDocument()
  })

  it('re-fetches the library when new look candidates land, so persisted portraits are reviewable', async () => {
    mocks.lookOverride = [draftLookWithCasting]
    const { rerender } = renderSpace()
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    const callsBefore = mocks.getReferenceLibrary.mock.calls.length
    mocks.lookOverride = [{
      ...draftLookWithCasting,
      candidates: [...draftLookWithCasting.candidates, { image_url: 'https://cdn.test/maya-cast-3.png', role: 'face', source: 'Generated casting option — awaiting selection', generation_id: 'job-2', matches_current_profile: true }],
    }]
    rerender(createElement(MemoryRouter, { initialEntries: ['/studio/reference-space?project_id=project-a'] },
      createElement(Routes, null, createElement(Route, { path: '/studio/reference-space', element: createElement(ReferenceSpace) })),
    ))
    await waitFor(() => expect(mocks.getReferenceLibrary.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('lists synced generated candidates as unapproved with their casting provenance', async () => {
    spaceData({
      library: { project_id: 'project-a', target_type: 'character', target_id: 'char-maya', canonical: canonicalAsset, supporting: [supportingAsset], candidates: [generatedCandidateAsset], categories: ['casting', 'face'], coverage: 'covered' },
    })
    renderSpace()
    expect(await screen.findByText('Candidates awaiting approval (1)')).toBeInTheDocument()
    expect(screen.getByText(/casting · generated/)).toBeInTheDocument()
    // The synced candidate appears both in the review list and in shot provenance.
    expect(screen.getAllByText(/ref_cast_abc/).length).toBeGreaterThanOrEqual(2)
  })

  it('offers canonical designation for an eligible setting reference and not for ineligible rows', async () => {
    spaceData({
      assets: [canonicalAsset, supportingAsset, candidateAsset, settingSupporting, settingCandidate],
      library: settingLibrary,
    })
    renderSpace()
    // While the character target is selected, no designation action is offered —
    // even though the loaded rows include an eligible setting reference.
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Designate canonical reference ref_set_wide' })).toBeNull()

    fireEvent.click(await screen.findByRole('button', { name: /loc-harbor/ }))
    expect(await screen.findByRole('button', { name: 'Designate canonical reference ref_set_wide' })).toBeInTheDocument()
    // Candidates are never offered designation, only approval.
    expect(screen.queryByRole('button', { name: 'Designate canonical reference ref_set_cand' })).toBeNull()
  })

  it('designates the approved setting reference through the generic canonical contract', async () => {
    spaceData({
      assets: [canonicalAsset, supportingAsset, candidateAsset, settingSupporting, settingCandidate],
      library: settingLibrary,
    })
    mocks.designateReferenceLibraryCanonical.mockResolvedValue({ reference_asset: { ...settingSupporting, canonical: true } })
    renderSpace()
    fireEvent.click(await screen.findByRole('button', { name: /loc-harbor/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Designate canonical reference ref_set_wide' }))

    await waitFor(() => expect(mocks.designateReferenceLibraryCanonical).toHaveBeenCalledTimes(1))
    expect(mocks.designateReferenceLibraryCanonical).toHaveBeenCalledWith('project-a', 'loc-harbor', 'ref_set_wide')
    // Success is acknowledged and the library is re-read so the new authority is shown.
    expect(await screen.findByText(/Designated canonical for this setting/)).toBeInTheDocument()
    await waitFor(() => expect(mocks.getReferenceLibrary.mock.calls.filter((call) => call[1] === 'setting' && call[2] === 'loc-harbor').length).toBeGreaterThanOrEqual(2))
  })

  it('reports a rejected designation honestly and marks nothing canonical', async () => {
    spaceData({
      assets: [canonicalAsset, supportingAsset, candidateAsset, settingSupporting, settingCandidate],
      library: settingLibrary,
    })
    mocks.designateReferenceLibraryCanonical.mockRejectedValue(new Error('Only an approved environment reference can be canonical'))
    renderSpace()
    fireEvent.click(await screen.findByRole('button', { name: /loc-harbor/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Designate canonical reference ref_set_wide' }))

    expect(await screen.findByText(/Only an approved environment reference can be canonical/)).toBeInTheDocument()
    expect(screen.queryByText(/Designated canonical for this setting/)).toBeNull()
    // The failure confers no authority: the setting still has no canonical anchor.
    expect(screen.getByText(/No canonical reference is registered for this target yet/)).toBeInTheDocument()
  })

  it('generates a still from the character tab using the backend contract', async () => {
    renderSpace()
    expect(await screen.findByRole('tab', { name: 'Character Generator' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Who is this person\?/), { target: { value: 'Maya in a wool coat' } })
    fireEvent.click(screen.getByRole('button', { name: '1:1' }))
    fireEvent.change(screen.getByLabelText('Style preset'), { target: { value: 'cinematic_35mm' } })
    fireEvent.change(screen.getByLabelText('Seed'), { target: { value: '314' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate still' }))

    await waitFor(() => expect(mocks.generatePrevisImage).toHaveBeenCalledTimes(1))
    expect(mocks.generatePrevisImage).toHaveBeenCalledWith({
      project_id: 'project-a',
      mode: 'character',
      prompt: 'Maya in a wool coat',
      aspect_ratio: '1:1',
      style_preset: 'cinematic_35mm',
      lighting_preset: 'none',
      seed: 314,
    })
    expect(await screen.findByTestId('generated-reference-still')).toBeInTheDocument()
    expect(screen.getAllByText(/seed 314/).length).toBeGreaterThan(0)
  })

  it('switches to the setting tab and refuses to bind a setting still to the selected character', async () => {
    renderSpace()
    // Wait for the character target to resolve before choosing a tab, so the
    // assertion is about the tab choice and not about load timing.
    expect(await screen.findByText('Maya · look v2')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('tab', { name: 'Setting Generator' }))
    expect(await screen.findByText(/the selected target is a character/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Where does this scene live\?/), { target: { value: 'A rain-slick loading dock' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate still' }))
    await waitFor(() => expect(mocks.generatePrevisImage).toHaveBeenCalled())
    expect(mocks.generatePrevisImage.mock.calls[0][0].mode).toBe('setting')
    await screen.findByTestId('generated-reference-still')
    expect(screen.getByRole('button', { name: 'Bind to Shot Reference' })).toBeDisabled()
    expect(mocks.bindGeneratedStillToShot).not.toHaveBeenCalled()
  })

  it('binds a generated still to a recorded shot as a candidate with provenance', async () => {
    renderSpace()
    expect(await screen.findByRole('tab', { name: 'Character Generator' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Who is this person\?/), { target: { value: 'Maya in a wool coat' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate still' }))
    await screen.findByTestId('generated-reference-still')

    fireEvent.change(screen.getByLabelText('Shot for generated still seed 314'), { target: { value: 'scene_001_shot_002' } })
    fireEvent.click(screen.getByRole('button', { name: 'Bind to Shot Reference' }))

    await waitFor(() => expect(mocks.bindGeneratedStillToShot).toHaveBeenCalledTimes(1))
    const [projectId, target, image, shotId] = mocks.bindGeneratedStillToShot.mock.calls[0]
    expect(projectId).toBe('project-a')
    expect(target).toEqual({ kind: 'character', targetId: 'char-maya' })
    expect(image.image_url).toBe('/outputs/reference_generation/project-a/still-1.png')
    expect(shotId).toBe('scene_001_shot_002')
    expect(await screen.findByText(/as a candidate/)).toBeInTheDocument()
  })

  it('reports a failed generation without inventing a result', async () => {
    mocks.generatePrevisImage.mockRejectedValue(new Error('The image provider is busy or its allowance is exhausted.'))
    renderSpace()
    fireEvent.change(await screen.findByLabelText(/Who is this person\?/), { target: { value: 'Maya in a wool coat' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate still' }))
    expect(await screen.findByText(/The image provider is busy/)).toBeInTheDocument()
    expect(screen.queryByTestId('generated-reference-still')).toBeNull()
  })

  it('registers the room while keeping Production Desk, Integrity Engine, and Universe intact', () => {
    const space = APP_ROUTES.find((route) => route.path === '/studio/reference-space')
    const desk = APP_ROUTES.find((route) => route.path === '/studio/production-desk')
    const engine = APP_ROUTES.find((route) => route.path === '/studio/integrity')
    const universe = APP_ROUTES.find((route) => route.path === '/studio/universe-graph')
    expect(space?.title).toBe('Reference Space')
    expect(space?.placement).toBe('primary')
    expect(space?.element).toBeTruthy()
    expect(desk?.title).toBe('Production Desk')
    expect(engine?.title).toBe('Production Integrity Engine')
    expect(universe?.element).toBeTruthy()
  })
})

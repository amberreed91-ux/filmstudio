// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { CreatorDecisionWorkspace } from './CreatorDecisionWorkspace'
import { useSceneDirection } from '../hooks/useSceneDirection'
import { buildScene002Fixture } from './__fixtures__/sceneDirectionFixture'
import * as settingApi from '../lib/settingReferenceApi'
import * as visualApi from '../lib/visualTrainingApi'
import { SCENE002_PROJECT_ID, SCENE002_SETTING_ID } from '../lib/settingReferenceApi'
import type { SceneDirection } from '../lib/sceneDirectionApi'

vi.mock('../hooks/useSceneDirection', () => ({ useSceneDirection: vi.fn() }))

vi.mock('../lib/settingReferenceApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/settingReferenceApi')>()
  return {
    ...actual,
    listSettingReferences: vi.fn(),
    createSettingReference: vi.fn(),
    uploadSettingReference: vi.fn(),
    approveSettingReference: vi.fn(),
    rejectSettingReference: vi.fn(),
    designateSettingReferenceCanonical: vi.fn(),
  }
})

vi.mock('../lib/visualTrainingApi', () => ({
  getReferenceLibrary: vi.fn(),
  listReferenceAssets: vi.fn(),
  approveReferenceLibraryAsset: vi.fn(),
  uploadReferenceLibraryAsset: vi.fn(),
  addReferenceLibraryAsset: vi.fn(),
  designateReferenceLibraryCanonical: vi.fn(),
  removeReferenceLibraryAsset: vi.fn(),
}))

function mockDirection(data: SceneDirection | null, error = '') {
  vi.mocked(useSceneDirection).mockReturnValue({
    data, busy: false, dirty: false, error,
    editLine: vi.fn(), removeLine: vi.fn(), addLine: vi.fn(),
    editCoverage: vi.fn(), editHandoff: vi.fn(), editSettingReference: vi.fn(),
    save: vi.fn(), reload: vi.fn(),
  } as unknown as ReturnType<typeof useSceneDirection>)
}

const renderWorkspace = (sceneId: string | null = 'scene_001', versionId: string | null = 'v1') =>
  render(
    <CreatorDecisionWorkspace
      projectId={SCENE002_PROJECT_ID}
      sceneId={sceneId}
      versionId={versionId}
      activeShotNumber={1}
      onSaved={vi.fn()}
    />,
  )

beforeEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.mocked(settingApi.listSettingReferences).mockResolvedValue({
    project_id: SCENE002_PROJECT_ID,
    target_type: 'setting',
    target_id: SCENE002_SETTING_ID,
    reference_assets: [],
    count: 0,
  })
  vi.mocked(visualApi.getReferenceLibrary).mockResolvedValue({
    project_id: SCENE002_PROJECT_ID,
    target_type: 'setting',
    target_id: 'loc-b543d669',
    canonical: null,
    supporting: [],
    candidates: [],
    categories: [],
    coverage: 'not_covered',
  })
})

describe('CreatorDecisionWorkspace setting authority scope', () => {
  it('holds a resolving status instead of a panel that could point at the wrong entity', async () => {
    mockDirection(null)
    renderWorkspace()
    expect(await screen.findByText(/Resolving the scene's setting entity/)).toBeTruthy()
    expect(screen.queryByTestId('setting-reference-authority')).toBeNull()
    expect(settingApi.listSettingReferences).not.toHaveBeenCalled()
    expect(visualApi.getReferenceLibrary).not.toHaveBeenCalled()
  })

  it('scopes authority to the open scene\u2019s canonical setting entity, not the scene_002 default', async () => {
    mockDirection({ ...buildScene002Fixture(), canonical_setting_id: 'loc-b543d669' })
    renderWorkspace()
    await waitFor(() => expect(visualApi.getReferenceLibrary).toHaveBeenCalledTimes(1))
    expect(visualApi.getReferenceLibrary).toHaveBeenCalledWith(SCENE002_PROJECT_ID, 'setting', 'loc-b543d669')
    expect(settingApi.listSettingReferences).not.toHaveBeenCalled()
    expect(await screen.findByTestId('setting-reference-authority')).toBeTruthy()
  })

  it('falls back to the default authority scope when the scene has no canonical entity', async () => {
    mockDirection({ ...buildScene002Fixture(), canonical_setting_id: null })
    renderWorkspace()
    await waitFor(() => expect(settingApi.listSettingReferences).toHaveBeenCalledTimes(1))
    expect(visualApi.getReferenceLibrary).not.toHaveBeenCalled()
  })

  it('renders the default authority scope when no scene is open', async () => {
    mockDirection(null)
    renderWorkspace(null, null)
    expect(screen.getByText(/Open a scene to capture/)).toBeTruthy()
    await waitFor(() => expect(settingApi.listSettingReferences).toHaveBeenCalledTimes(1))
    expect(visualApi.getReferenceLibrary).not.toHaveBeenCalled()
  })
})

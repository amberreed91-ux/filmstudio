// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useSceneDirection } from './useSceneDirection'
import { getSceneDirection, saveSceneDirection, type SceneDirection, type SettingReferenceOption } from '../lib/sceneDirectionApi'
import { SCENE002_SETTING_ID } from '../lib/settingReferenceApi'

vi.mock('../lib/sceneDirectionApi', () => ({
  getSceneDirection: vi.fn(),
  saveSceneDirection: vi.fn(),
}))

const exactOption: SettingReferenceOption = {
  ref_id: 'ref_set_canonical', image_url: 'https://assets.example.test/setting.png',
  target_type: 'setting', target_id: SCENE002_SETTING_ID, kind: 'environment',
  approval_state: 'approved', canonical: true,
}

const direction: SceneDirection = {
  project_id: 'project_5907c60cddbc', scene_id: 'scene_002', version_id: 'v1', version_status: 'draft',
  canonical_setting_id: SCENE002_SETTING_ID,
  setting_reference_decision: null,
  setting_reference_options: [exactOption],
  dialogue: [],
  coverage_obligations: [],
  coverage_decisions: [],
  unassigned_line_ids: [],
  coverage_blocked: true,
  coverage_blockers: ['unresolved coverage'],
  shots: [],
  saved: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getSceneDirection).mockResolvedValue(structuredClone(direction))
  vi.mocked(saveSceneDirection).mockResolvedValue(structuredClone(direction))
})

describe('useSceneDirection setting reference decision', () => {
  it('loads with no reference selected — nothing is chosen automatically', async () => {
    const { result } = renderHook(() => useSceneDirection('project_5907c60cddbc', 'scene_002', 'v1'))
    await waitFor(() => expect(result.current.data).not.toBeNull())
    expect(result.current.data?.setting_reference_decision).toBeNull()
    expect(saveSceneDirection).not.toHaveBeenCalled()
  })

  it('saves an explicit creator selection as the exact reference ID', async () => {
    const { result } = renderHook(() => useSceneDirection('project_5907c60cddbc', 'scene_002', 'v1'))
    await waitFor(() => expect(result.current.data).not.toBeNull())

    act(() => {
      result.current.editSettingReference({ canonical_setting_id: SCENE002_SETTING_ID, reference_id: exactOption.ref_id })
    })
    await act(async () => { await result.current.save() })

    expect(saveSceneDirection).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(saveSceneDirection).mock.calls[0][2]
    expect(payload.expected_version_id).toBe('v1')
    expect(payload.setting_reference_decision).toEqual({
      canonical_setting_id: SCENE002_SETTING_ID,
      reference_id: exactOption.ref_id,
    })
  })

  it('submits an explicit null when no reference has been selected', async () => {
    const { result } = renderHook(() => useSceneDirection('project_5907c60cddbc', 'scene_002', 'v1'))
    await waitFor(() => expect(result.current.data).not.toBeNull())
    await act(async () => { await result.current.save() })

    const payload = vi.mocked(saveSceneDirection).mock.calls[0][2]
    expect(payload.setting_reference_decision).toBeNull()
  })
})

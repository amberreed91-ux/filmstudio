// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { SettingReferenceAuthorityPanel } from './SettingReferenceAuthorityPanel'
import {
  LEGACY_SCENE002_REFERENCE_ID,
  SCENE002_PROJECT_ID,
  SCENE002_SETTING_ID,
  type SettingReferenceAsset,
} from '../lib/settingReferenceApi'
import * as settingApi from '../lib/settingReferenceApi'
import * as visualApi from '../lib/visualTrainingApi'
import { approveReferenceLibraryAsset, getReferenceLibrary, listReferenceAssets } from '../lib/visualTrainingApi'
import type { ReferenceAsset, ReferenceLibrary } from '../lib/visualTrainingApi'

vi.mock('../lib/settingReferenceApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/settingReferenceApi')>()
  return {
    ...actual,
    listSettingReferences: vi.fn(),
    createSettingReference: vi.fn(),
    uploadSettingReference: vi.fn(),
    approveSettingReference: vi.fn(),
    designateSettingReferenceCanonical: vi.fn(),
  }
})

// The legacy library endpoints trigger creator reference sync; the exact
// lifecycle panel must never reach them. The generic-entity branch uses the
// reference-library lifecycle (the same reads Reference Space uses).
vi.mock('../lib/visualTrainingApi', () => ({
  getReferenceLibrary: vi.fn(),
  listReferenceAssets: vi.fn(),
  approveReferenceLibraryAsset: vi.fn(),
  uploadReferenceLibraryAsset: vi.fn(),
  addReferenceLibraryAsset: vi.fn(),
  designateReferenceLibraryCanonical: vi.fn(),
  removeReferenceLibraryAsset: vi.fn(),
}))

const row = (over: Partial<SettingReferenceAsset> = {}): SettingReferenceAsset => ({
  ref_id: 'ref_set_a',
  project_id: SCENE002_PROJECT_ID,
  kind: 'environment',
  image_url: 'https://assets.example.test/setting.png',
  source_shot_id: null,
  target_type: 'setting',
  target_id: SCENE002_SETTING_ID,
  category: 'environment',
  approval_state: 'candidate',
  canonical: false,
  source_kind: 'confirmed',
  created_at: '2026-10-01T00:00:00+00:00',
  ...over,
})

const legacyRow = row({ ref_id: LEGACY_SCENE002_REFERENCE_ID, target_id: 'scene_002', approval_state: 'approved' })

function mockList(rows: SettingReferenceAsset[]) {
  vi.mocked(settingApi.listSettingReferences).mockResolvedValue({
    project_id: SCENE002_PROJECT_ID,
    target_type: 'setting',
    target_id: SCENE002_SETTING_ID,
    reference_assets: rows,
    count: rows.length,
  })
}

beforeEach(() => {
  cleanup()
  vi.clearAllMocks()
  mockList([])
})

describe('SettingReferenceAuthorityPanel', () => {
  it('opens with only the sync-free scoped read and performs no lifecycle action', async () => {
    mockList([row(), row({ ref_id: 'ref_set_b', approval_state: 'approved' }), legacyRow])
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} />)

    await waitFor(() => expect(settingApi.listSettingReferences).toHaveBeenCalledTimes(1))
    expect(settingApi.listSettingReferences).toHaveBeenCalledWith(SCENE002_PROJECT_ID)

    // Legacy sync-triggering endpoints are never touched.
    expect(getReferenceLibrary).not.toHaveBeenCalled()
    expect(listReferenceAssets).not.toHaveBeenCalled()
    expect(approveReferenceLibraryAsset).not.toHaveBeenCalled()
    // Opening the panel never approves, designates, or registers anything.
    expect(settingApi.approveSettingReference).not.toHaveBeenCalled()
    expect(settingApi.designateSettingReferenceCanonical).not.toHaveBeenCalled()
    expect(settingApi.createSettingReference).not.toHaveBeenCalled()
    expect(settingApi.uploadSettingReference).not.toHaveBeenCalled()

    await screen.findByText('ref_set_a')
    expect(screen.getByTestId('state-ref_set_a')).toHaveTextContent('candidate')
    expect(screen.getByTestId('state-ref_set_b')).toHaveTextContent('approved')
    // Legacy scene-targeted rows are never presented.
    expect(screen.queryByText(new RegExp(LEGACY_SCENE002_REFERENCE_ID))).toBeNull()
  })

  it('shows an empty state without inventing a reference', async () => {
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} />)
    expect(await screen.findByText('No references are registered for this exact setting yet.')).toBeTruthy()
    expect(settingApi.approveSettingReference).not.toHaveBeenCalled()
    expect(settingApi.designateSettingReferenceCanonical).not.toHaveBeenCalled()
  })

  it('approves only the exact reference ID the creator clicked', async () => {
    mockList([row()])
    vi.mocked(settingApi.approveSettingReference).mockResolvedValue({ reference_asset: row({ approval_state: 'approved' }) })
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Approve reference ref_set_a' }))
    await waitFor(() => expect(settingApi.approveSettingReference).toHaveBeenCalledTimes(1))
    expect(settingApi.approveSettingReference).toHaveBeenCalledWith(SCENE002_PROJECT_ID, 'ref_set_a')
    // Approval never canonicalizes and never registers anything new.
    expect(settingApi.designateSettingReferenceCanonical).not.toHaveBeenCalled()
    expect(settingApi.createSettingReference).not.toHaveBeenCalled()
    expect(settingApi.uploadSettingReference).not.toHaveBeenCalled()
    expect(settingApi.listSettingReferences).toHaveBeenCalledTimes(2)
  })

  it('designates canonical only from an approved reference, as its own action', async () => {
    mockList([row(), row({ ref_id: 'ref_set_b', approval_state: 'approved' })])
    vi.mocked(settingApi.designateSettingReferenceCanonical).mockResolvedValue({ reference_asset: row({ ref_id: 'ref_set_b', approval_state: 'approved', canonical: true }) })
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} />)

    expect(await screen.findByRole('button', { name: 'Approve reference ref_set_a' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Designate canonical reference ref_set_a' })).toBeNull()

    fireEvent.click(await screen.findByRole('button', { name: 'Designate canonical reference ref_set_b' }))
    await waitFor(() => expect(settingApi.designateSettingReferenceCanonical).toHaveBeenCalledTimes(1))
    expect(settingApi.designateSettingReferenceCanonical).toHaveBeenCalledWith(SCENE002_PROJECT_ID, 'ref_set_b')
    expect(settingApi.approveSettingReference).not.toHaveBeenCalled()
    expect(settingApi.createSettingReference).not.toHaveBeenCalled()
  })

  it('registers a new candidate for the exact setting scope only', async () => {
    mockList([])
    vi.mocked(settingApi.createSettingReference).mockResolvedValue({ reference_asset: row() })
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} />)

    fireEvent.change(await screen.findByLabelText('Reference image URI'), { target: { value: 'https://assets.example.test/new.png' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register reference' }))
    await waitFor(() => expect(settingApi.createSettingReference).toHaveBeenCalledTimes(1))
    expect(settingApi.createSettingReference).toHaveBeenCalledWith(SCENE002_PROJECT_ID, 'https://assets.example.test/new.png')
    // Registration never approves or canonicalizes what it just created.
    expect(settingApi.approveSettingReference).not.toHaveBeenCalled()
    expect(settingApi.designateSettingReferenceCanonical).not.toHaveBeenCalled()
  })

  it('renders nothing and issues no request for any other project', () => {
    render(<SettingReferenceAuthorityPanel projectId="film_1" />)
    expect(screen.queryByTestId('setting-reference-authority')).toBeNull()
    expect(settingApi.listSettingReferences).not.toHaveBeenCalled()
  })
})

describe('SettingReferenceAuthorityPanel for another setting entity', () => {
  const SETTING_ID = 'loc-b543d669'

  const libRow = (over: Partial<ReferenceAsset> = {}): ReferenceAsset => ({
    ref_id: 'ref_lib_a',
    kind: 'environment',
    image_url: 'https://assets.example.test/golden.png',
    project_id: SCENE002_PROJECT_ID,
    target_type: 'setting',
    target_id: SETTING_ID,
    approval_state: 'candidate',
    canonical: false,
    ...over,
  })

  function mockLibrary(over: Partial<ReferenceLibrary> = {}) {
    vi.mocked(visualApi.getReferenceLibrary).mockResolvedValue({
      project_id: SCENE002_PROJECT_ID,
      target_type: 'setting',
      target_id: SETTING_ID,
      canonical: null,
      supporting: [],
      candidates: [],
      categories: [],
      coverage: 'not_covered',
      ...over,
    })
  }

  beforeEach(() => {
    mockLibrary()
  })

  it('reads the reference library for the exact setting scope, never the exact lifecycle', async () => {
    mockLibrary({ candidates: [libRow(), libRow({ ref_id: 'ref_lib_b', approval_state: 'approved' })] })
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} settingId={SETTING_ID} />)

    await waitFor(() => expect(visualApi.getReferenceLibrary).toHaveBeenCalledTimes(1))
    expect(visualApi.getReferenceLibrary).toHaveBeenCalledWith(SCENE002_PROJECT_ID, 'setting', SETTING_ID)
    expect(settingApi.listSettingReferences).not.toHaveBeenCalled()
    expect(listReferenceAssets).not.toHaveBeenCalled()

    await screen.findByText('ref_lib_a')
    expect(screen.getByTestId('state-ref_lib_a')).toHaveTextContent('candidate')
    expect(screen.getByTestId('state-ref_lib_b')).toHaveTextContent('approved')
    // The library scope is named so a creator can tell which entity this is.
    expect(screen.getAllByText(new RegExp(SETTING_ID)).length).toBeGreaterThan(0)
  })

  it('shows scoped guidance without inventing a reference', async () => {
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} settingId={SETTING_ID} />)
    expect(await screen.findByText(new RegExp(`No references are registered for setting ${SETTING_ID} yet`))).toBeTruthy()
    expect(visualApi.approveReferenceLibraryAsset).not.toHaveBeenCalled()
    expect(visualApi.designateReferenceLibraryCanonical).not.toHaveBeenCalled()
  })

  it('drops legacy, wrong-target, and non-environment rows', async () => {
    mockLibrary({ candidates: [
      libRow(),
      libRow({ ref_id: LEGACY_SCENE002_REFERENCE_ID }),
      libRow({ ref_id: 'ref_lib_other', target_id: 'loc-other' }),
      libRow({ ref_id: 'ref_lib_face', kind: 'character_full' }),
    ] })
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} settingId={SETTING_ID} />)

    await screen.findByText('ref_lib_a')
    expect(screen.queryByText(new RegExp(LEGACY_SCENE002_REFERENCE_ID))).toBeNull()
    expect(screen.queryByText('ref_lib_other')).toBeNull()
    expect(screen.queryByText('ref_lib_face')).toBeNull()
  })

  it('approves only the exact reference ID the creator clicked', async () => {
    mockLibrary({ candidates: [libRow()] })
    vi.mocked(visualApi.approveReferenceLibraryAsset).mockResolvedValue(libRow({ approval_state: 'approved' }))
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} settingId={SETTING_ID} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Approve reference ref_lib_a' }))
    await waitFor(() => expect(visualApi.approveReferenceLibraryAsset).toHaveBeenCalledTimes(1))
    expect(visualApi.approveReferenceLibraryAsset).toHaveBeenCalledWith(SCENE002_PROJECT_ID, 'setting', SETTING_ID, 'ref_lib_a')
    expect(visualApi.designateReferenceLibraryCanonical).not.toHaveBeenCalled()
    expect(settingApi.approveSettingReference).not.toHaveBeenCalled()
    expect(visualApi.getReferenceLibrary).toHaveBeenCalledTimes(2)
  })

  it('designates canonical only from an approved reference, as its own action', async () => {
    mockLibrary({ supporting: [libRow({ ref_id: 'ref_lib_b', approval_state: 'approved' })] })
    vi.mocked(visualApi.designateReferenceLibraryCanonical).mockResolvedValue(libRow({ ref_id: 'ref_lib_b', approval_state: 'approved', canonical: true }))
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} settingId={SETTING_ID} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Designate canonical reference ref_lib_b' }))
    await waitFor(() => expect(visualApi.designateReferenceLibraryCanonical).toHaveBeenCalledTimes(1))
    expect(visualApi.designateReferenceLibraryCanonical).toHaveBeenCalledWith(SCENE002_PROJECT_ID, SETTING_ID, 'ref_lib_b')
    expect(visualApi.approveReferenceLibraryAsset).not.toHaveBeenCalled()
    expect(settingApi.designateSettingReferenceCanonical).not.toHaveBeenCalled()
  })

  it('offers no reject action outside the exact lifecycle', async () => {
    mockLibrary({ candidates: [libRow()], supporting: [libRow({ ref_id: 'ref_lib_b', approval_state: 'approved' })] })
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} settingId={SETTING_ID} />)

    await screen.findByText('ref_lib_a')
    expect(screen.queryByRole('button', { name: 'Reject reference ref_lib_a' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Reject reference ref_lib_b' })).toBeNull()
  })

  it('registers a new candidate for the exact setting scope only', async () => {
    vi.mocked(visualApi.addReferenceLibraryAsset).mockResolvedValue(libRow())
    render(<SettingReferenceAuthorityPanel projectId={SCENE002_PROJECT_ID} settingId={SETTING_ID} />)

    fireEvent.change(await screen.findByLabelText('Reference image URI'), { target: { value: 'https://assets.example.test/new.png' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register reference' }))
    await waitFor(() => expect(visualApi.addReferenceLibraryAsset).toHaveBeenCalledTimes(1))
    expect(visualApi.addReferenceLibraryAsset).toHaveBeenCalledWith(
      SCENE002_PROJECT_ID,
      'setting',
      SETTING_ID,
      expect.objectContaining({
        kind: 'environment',
        image_url: 'https://assets.example.test/new.png',
        approval_state: 'candidate',
      }),
    )
    expect(visualApi.approveReferenceLibraryAsset).not.toHaveBeenCalled()
    expect(visualApi.designateReferenceLibraryCanonical).not.toHaveBeenCalled()
    expect(settingApi.createSettingReference).not.toHaveBeenCalled()
  })
})

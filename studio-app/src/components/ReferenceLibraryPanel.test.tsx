// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import ReferenceLibraryPanel from './ReferenceLibraryPanel'
import type { ReferenceLibrary } from '../lib/visualTrainingApi'

const library = (targetType: 'character' | 'setting'): ReferenceLibrary => ({
  project_id: 'film-a',
  target_type: targetType,
  target_id: targetType === 'character' ? 'maya' : 'scene-1',
  canonical: {
    ref_id: 'canonical',
    kind: targetType === 'character' ? 'character_face' : 'environment',
    image_url: 'https://cdn.example/canonical.png',
    project_id: 'film-a',
    target_type: targetType,
    target_id: targetType === 'character' ? 'maya' : 'scene-1',
    category: 'face',
    canonical: true,
    approval_state: 'approved',
    source_kind: 'confirmed',
  },
  supporting: [{
    ref_id: 'supporting',
    kind: targetType === 'character' ? 'character_full' : 'environment',
    image_url: 'https://cdn.example/supporting.png',
    project_id: 'film-a',
    target_type: targetType,
    target_id: targetType === 'character' ? 'maya' : 'scene-1',
    category: 'night',
    canonical: false,
    approval_state: 'approved',
    source_kind: 'uploaded',
  }],
  candidates: [{
    ref_id: 'candidate',
    kind: targetType === 'character' ? 'character_full' : 'environment',
    image_url: 'https://cdn.example/candidate.png',
    project_id: 'film-a',
    target_type: targetType,
    target_id: targetType === 'character' ? 'maya' : 'scene-1',
    category: 'generated',
    canonical: false,
    approval_state: 'candidate',
    source_kind: 'generated',
  }],
  categories: ['face', 'night', 'generated'],
  coverage: 'covered',
})

vi.mock('../lib/visualTrainingApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/visualTrainingApi')>()
  return {
    ...actual,
    getReferenceLibrary: vi.fn(async (_project: string, target: 'character' | 'setting') => library(target)),
    addReferenceLibraryAsset: vi.fn(),
    uploadReferenceLibraryAsset: vi.fn(),
    approveReferenceLibraryAsset: vi.fn(),
    removeReferenceLibraryAsset: vi.fn(),
  }
})

import { addReferenceLibraryAsset, uploadReferenceLibraryAsset } from '../lib/visualTrainingApi'
const mockAdd = vi.mocked(addReferenceLibraryAsset)
const mockUpload = vi.mocked(uploadReferenceLibraryAsset)

describe('ReferenceLibraryPanel', () => {
  afterEach(() => cleanup())

  it('renders locked canonical, supporting category, and candidate approval state for a character', async () => {
    render(<ReferenceLibraryPanel projectId="film-a" targetType="character" targetId="maya" />)
    expect(screen.getByText('Visual reference library')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('Canonical reference · locked')).toBeTruthy())
    expect(screen.getByText(/^night/)).toBeTruthy()
    expect(screen.getByText('Candidate references awaiting approval')).toBeTruthy()
  })

  it('keeps settings scoped separately from character references', async () => {
    render(<ReferenceLibraryPanel projectId="film-a" targetType="scene" targetId="scene-1" />)
    expect(screen.getByRole('region', { name: 'setting visual reference library' })).toBeTruthy()
    await waitFor(() => expect(screen.getByText('Candidate references awaiting approval')).toBeTruthy())
    expect(screen.getByText('Canonical reference · locked')).toBeTruthy()
  })

  it('offers both Upload Reference and Add Image URL entry points', async () => {
    render(<ReferenceLibraryPanel projectId="film-a" targetType="character" targetId="maya" />)
    await waitFor(() => expect(screen.getByTestId('reference-upload-button')).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Add image URL reference' })).toBeTruthy()
    expect(screen.getByTestId('reference-upload-input')).toBeTruthy()
  })

  it('uploads a character reference and refreshes the library', async () => {
    mockUpload.mockResolvedValueOnce({ ref_id: 'upl-1' } as never)
    render(<ReferenceLibraryPanel projectId="film-a" targetType="character" targetId="maya" />)
    await waitFor(() => expect(screen.getByTestId('reference-upload-button')).toBeTruthy())

    const input = screen.getByTestId('reference-upload-input') as HTMLInputElement
    const file = new File(['png'], 'maya-night.png', { type: 'image/png' })
    Object.defineProperty(input, 'files', { value: [file] })
    input.dispatchEvent(new Event('change', { bubbles: true }))

    await waitFor(() => expect(mockUpload).toHaveBeenCalled())
    const [, targetType, targetId, uploadedFile, category] = mockUpload.mock.calls[0]
    expect(targetType).toBe('character')
    expect(targetId).toBe('maya')
    expect(uploadedFile).toBe(file)
    expect(category).toBe('face')
    await waitFor(() => expect(screen.getByRole('status')).toBeTruthy())
    expect(screen.getByRole('status').textContent).toContain('candidate')
  })

  it('uploads a setting reference scoped to the scene target', async () => {
    mockUpload.mockResolvedValueOnce({ ref_id: 'upl-2' } as never)
    render(<ReferenceLibraryPanel projectId="film-a" targetType="scene" targetId="scene-1" />)
    await waitFor(() => expect(screen.getByTestId('reference-upload-button')).toBeTruthy())

    const input = screen.getByTestId('reference-upload-input') as HTMLInputElement
    const file = new File(['png'], 'wide.png', { type: 'image/png' })
    Object.defineProperty(input, 'files', { value: [file] })
    input.dispatchEvent(new Event('change', { bubbles: true }))

    await waitFor(() => expect(mockUpload).toHaveBeenCalled())
    const [, targetType, targetId] = mockUpload.mock.calls.at(-1)!
    expect(targetType).toBe('setting')
    expect(targetId).toBe('scene-1')
  })

  it('surfaces actionable upload errors and allows retry', async () => {
    mockUpload.mockRejectedValueOnce(new Error('Choose a valid, still JPEG, PNG, or WebP image under 24 megapixels.'))
    render(<ReferenceLibraryPanel projectId="film-a" targetType="character" targetId="maya" />)
    await waitFor(() => expect(screen.getByTestId('reference-upload-button')).toBeTruthy())

    const input = screen.getByTestId('reference-upload-input') as HTMLInputElement
    const file = new File(['not-an-image'], 'broken.png', { type: 'image/png' })
    Object.defineProperty(input, 'files', { value: [file] })
    input.dispatchEvent(new Event('change', { bubbles: true }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.getByRole('alert').textContent).toContain('Choose a valid')
    expect((screen.getByTestId('reference-upload-button') as HTMLButtonElement).disabled).toBe(false)
  })

  it('adds URL references as candidates instead of approved', async () => {
    mockAdd.mockResolvedValueOnce({ ref_id: 'url-1' } as never)
    render(<ReferenceLibraryPanel projectId="film-a" targetType="character" targetId="maya" />)
    await waitFor(() => expect(screen.getByLabelText('Supporting reference image URL')).toBeTruthy())

    fireEvent.change(screen.getByLabelText('Supporting reference image URL'), { target: { value: 'https://cdn.example/profile.png' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add image URL reference' }))

    await waitFor(() => expect(mockAdd).toHaveBeenCalled())
    expect(mockAdd.mock.calls[0][3].approval_state).toBe('candidate')
  })

  it('shows the ingestion source badge on candidates', async () => {
    render(<ReferenceLibraryPanel projectId="film-a" targetType="character" targetId="maya" />)
    await waitFor(() => expect(screen.getByTestId('candidate-source-candidate')).toBeTruthy())
    expect(screen.getByTestId('candidate-source-candidate').textContent).toBe('url')
  })
})

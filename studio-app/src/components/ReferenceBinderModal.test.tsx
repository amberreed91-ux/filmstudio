// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

afterEach(() => cleanup())
import '@testing-library/jest-dom/vitest'
import ReferenceBinderModal from './ReferenceBinderModal'
import type { GeneratedPrevisImage } from '../lib/previsImageApi'

const image: GeneratedPrevisImage = {
  project_id: 'project-a',
  mode: 'character',
  image_url: 'https://cdn.test/still-1.png',
  seed: 314,
  aspect_ratio: '16:9',
  style_preset: 'cinematic_35mm',
  lighting_preset: 'soft_window',
  provider: 'dashscope',
  model: 'qwen-image-max',
  prompt: 'Maya in a wool coat\nOne fictional character only',
  created_at: '2026-10-17T00:00:00Z',
}

const shots = [{ shotId: 'scene_001_shot_002', sceneId: 'scene_001', sceneName: 'Loft' }]

describe('ReferenceBinderModal', () => {
  it('renders nothing when closed', () => {
    render(
      <ReferenceBinderModal
        image={null}
        targetLabel="Maya"
        shots={shots}
        initialShotId=""
        hasLockedCanonical={false}
        binding={false}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    )
    expect(screen.queryByTestId('reference-binder-modal')).toBeNull()
  })

  it('shows provenance and binds without confirmation when no locked canonical', () => {
    const onConfirm = vi.fn()
    render(
      <ReferenceBinderModal
        image={image}
        targetLabel="Maya"
        shots={shots}
        initialShotId="scene_001_shot_002"
        hasLockedCanonical={false}
        binding={false}
        onClose={() => {}}
        onConfirm={onConfirm}
      />,
    )
    expect(screen.getByTestId('reference-binder-modal')).toBeInTheDocument()
    expect(screen.getByText(/Maya in a wool coat/)).toBeInTheDocument()
    expect(screen.getByText('314')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm bind candidate to shot' }))
    expect(onConfirm).toHaveBeenCalledWith('scene_001_shot_002')
  })

  it('requires explicit acknowledgement when a locked canonical exists', () => {
    const onConfirm = vi.fn()
    render(
      <ReferenceBinderModal
        image={image}
        targetLabel="Maya"
        shots={shots}
        initialShotId="scene_001_shot_002"
        hasLockedCanonical
        binding={false}
        onClose={() => {}}
        onConfirm={onConfirm}
      />,
    )
    const confirm = screen.getByRole('button', { name: 'Confirm bind candidate to shot' })
    expect(confirm).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Confirm canonical stays unchanged'))
    expect(confirm).not.toBeDisabled()
    fireEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledWith('scene_001_shot_002')
  })
})

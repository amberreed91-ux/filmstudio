import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CameraPresetPicker from './CameraPresetPicker'
import { useCameraPresets } from '../hooks/useCameraPresets'
vi.mock('../hooks/useCameraPresets', () => ({ useCameraPresets: vi.fn() }))
const catalog = {
  presets: [{ id: 'rack', label: 'Rack focus', category: 'Focus', description: 'Shift attention to the person behind the glass.', camera: 'Shift focus from glass to face.', framing: 'Close-up' }],
  views: [{ id: 'eye', label: 'Eye level', camera: 'Eye-level view.' }],
  framings: [{ id: 'wide', label: 'Wide', framing: 'Wide framing.' }],
  lenses: [{ id: 'wide-cinema', label: 'Wide cinema prime', category: 'Spherical', description: 'Clean wide-to-normal field of view with minimal distortion.', lens_language: 'Wide cinema prime.' }],
  focal_lengths: [{ id: '24mm', label: '24mm', mm: 24, framing_hint: 'Wide.' }],
  apertures: [{ id: 'f2.8', label: 'f/2.8', f_stop: 'f/2.8', depth_hint: 'Shallow.' }],
}
const current = { camera: 'Hold still.', framing: 'Medium shot.', lens: '', focal_length: '', aperture: '' }
const render = (disabled = false, onApply = vi.fn()) => renderToStaticMarkup(<CameraPresetPicker current={current} onApply={onApply} disabled={disabled} />)
describe('CameraPresetPicker', () => {
  beforeEach(() => vi.mocked(useCameraPresets).mockReturnValue({ catalog, loading: false, error: '', retry: vi.fn() }))
  it('shows server descriptions and current plan without applying a preset on render', () => {
    const apply = vi.fn()
    const html = render(false, apply)
    expect(html).toContain('Rack focus')
    expect(html).toContain('Shift attention to the person behind the glass.')
    expect(html).toContain('Hold still.')
    expect(html).toContain('Apply to this shot')
    expect(apply).not.toHaveBeenCalled()
  })
  it('renders the four optics columns when catalog data is present', () => {
    const html = render()
    expect(html).toContain('Camera')
    expect(html).toContain('Lens')
    expect(html).toContain('Focal length')
    expect(html).toContain('Aperture')
    expect(html).toContain('Wide cinema prime')
    expect(html).toContain('24mm')
    expect(html).toContain('f/2.8')
  })
  it('shows a recoverable catalog error while preserving the current direction', () => {
    vi.mocked(useCameraPresets).mockReturnValue({ catalog: null, loading: false, error: 'Catalog unavailable', retry: vi.fn() })
    const html = render()
    expect(html).toContain('role="alert"')
    expect(html).toContain('Retry camera presets')
    expect(html).toContain('Hold still.')
  })
  it('shows loading and empty states', () => {
    vi.mocked(useCameraPresets).mockReturnValue({ catalog: null, loading: true, error: '', retry: vi.fn() })
    expect(render()).toContain('Loading camera presets')
    vi.mocked(useCameraPresets).mockReturnValue({ catalog: { presets: [], views: [], framings: [], lenses: [], focal_lengths: [], apertures: [] }, loading: false, error: '', retry: vi.fn() })
    expect(render()).toContain('No camera match this filter')
  })
  it('disables preset selection when editing is disabled', () => {
    expect(render(true)).toMatch(/disabled="" aria-selected="false"/)
  })
})
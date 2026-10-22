import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import RenderPromptScopeNote from './RenderPromptScopeNote'

describe('RenderPromptScopeNote', () => {
  it('renders three labeled field groups with targets and status', () => {
    const html = renderToStaticMarkup(<RenderPromptScopeNote />)
    expect(html).toContain('data-testid="render-prompt-scope-note"')
    expect(html).toContain('data-testid="scope-group-take"')
    expect(html).toContain('data-testid="scope-group-board"')
    expect(html).toContain('data-testid="scope-group-image"')
    expect(html).toContain('Previs take direction')
    expect(html).toContain('Board canonical text')
    expect(html).toContain('Runway image prompt')
    expect(html).toContain('writes to previs-render-prompt')
    expect(html).toContain('writes to blueprint version')
    expect(html).toContain('writes to Runway render')
    expect(html).toContain('take-status')
    expect(html).toContain('board-status')
    expect(html).toContain('image-status')
  })
})

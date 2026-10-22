import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import RenderPromptScopeNote from './RenderPromptScopeNote'

describe('RenderPromptScopeNote', () => {
  it('names the previs-take scope and the approved board image prompt', () => {
    const html = renderToStaticMarkup(<RenderPromptScopeNote />)
    expect(html).toContain('data-testid="render-prompt-scope-note"')
    expect(html).toContain('previs take')
    expect(html).toContain('approved board image prompt')
    expect(html).not.toContain('sent with this take.')
  })
})

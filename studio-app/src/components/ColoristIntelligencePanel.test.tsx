import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ColoristIntelligencePanel from './ColoristIntelligencePanel'

describe('ColoristIntelligencePanel', () => {
  it('renders colorist department controls', () => {
    const client = new QueryClient()
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <ColoristIntelligencePanel
          projectId="project_color"
          sceneId="scene_001"
          shotId="scene_001_shot_001"
          sceneContext={{ description: 'A cold hallway with amber practicals.', color_palette: ['teal', 'amber'] }}
        />
      </QueryClientProvider>,
    )

    expect(html).toContain('data-testid="colorist-intelligence-panel"')
    expect(html).toContain('Colorist')
    expect(html).toContain('Look development')
    expect(html).toContain('Look')
    expect(html).toContain('Plan')
    expect(html).toContain('Slots')
    expect(html).toContain('Assess')
    expect(html).toContain('Final')
    expect(html).toContain('Inspect')
  })
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CinematographerIntelligencePanel from './CinematographerIntelligencePanel'

describe('CinematographerIntelligencePanel', () => {
  it('renders the cinematographer intelligence entry point', () => {
    const client = new QueryClient()
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <CinematographerIntelligencePanel
          projectId="project_cam"
          sceneId="scene_001"
          shotId="scene_001_shot_001"
          sceneContext={{ visual_description: 'A quiet close-up by a practical lamp.' }}
        />
      </QueryClientProvider>,
    )

    expect(html).toContain('Cinematographer')
    expect(html).toContain('Composition, lens, movement, lighting')
    expect(html).toContain('Plan')
    expect(html).toContain('Slots')
    expect(html).toContain('Assess')
    expect(html).toContain('Inspect')
  })
})

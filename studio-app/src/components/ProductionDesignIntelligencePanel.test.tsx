import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ProductionDesignIntelligencePanel from './ProductionDesignIntelligencePanel'

function renderPanel() {
  const client = new QueryClient()
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <ProductionDesignIntelligencePanel
        projectId="project-pd"
        sceneId="scene_001"
        sceneContext={{
          location: 'INT. SAFEHOUSE - NIGHT',
          description: 'A key sits beside a cracked mirror.',
          characters: ['Mara'],
          props: ['key'],
        }}
      />
    </QueryClientProvider>,
  )
}

describe('ProductionDesignIntelligencePanel', () => {
  it('renders production design department controls', () => {
    const html = renderPanel()

    expect(html).toContain('data-testid="production-design-intelligence-panel"')
    expect(html).toContain('Production Designer')
    expect(html).toContain('Environments, props, costumes')
    expect(html).toContain('Plan')
    expect(html).toContain('Slots')
    expect(html).toContain('Assess')
    expect(html).toContain('Inspect')
  })
})

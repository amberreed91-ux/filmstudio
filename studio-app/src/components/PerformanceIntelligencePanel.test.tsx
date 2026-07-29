import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import PerformanceIntelligencePanel from './PerformanceIntelligencePanel'

describe('PerformanceIntelligencePanel', () => {
  it('renders the performance intelligence entry point', () => {
    const client = new QueryClient()
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <PerformanceIntelligencePanel projectId="project_perf" initialSceneId="scene_001" />
      </QueryClientProvider>,
    )

    expect(html).toContain('Performance Intelligence')
    expect(html).toContain('Motivation, subtext, relationship pressure')
    expect(html).toContain('scene_001')
    expect(html).toContain('Analyze')
  })
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import PerformanceAudioPanel from './PerformanceAudioPanel'

describe('PerformanceAudioPanel', () => {
  it('renders the performance audio entry point', () => {
    const client = new QueryClient()
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <PerformanceAudioPanel projectId="project_audio" sceneId="scene_001" />
      </QueryClientProvider>,
    )

    expect(html).toContain('Performance Audio')
    expect(html).toContain('Voice direction, dialogue cues')
    expect(html).toContain('Build Plan')
    expect(html).toContain('Execution')
    expect(html).toContain('Assess')
  })
})

import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import CastingIntelligencePanel from './CastingIntelligencePanel'

describe('CastingIntelligencePanel', () => {
  it('renders casting controls without score language', () => {
    const queryClient = new QueryClient()
    const html = renderToStaticMarkup(
      <QueryClientProvider client={queryClient}>
        <CastingIntelligencePanel projectId="project-casting" />
      </QueryClientProvider>,
    )

    expect(html).toContain('Casting Intelligence')
    expect(html).toContain('Build Roles')
    expect(html).toContain('Role coverage')
    expect(html.toLowerCase()).not.toContain('score')
    expect(html).not.toContain('%')
  })
})

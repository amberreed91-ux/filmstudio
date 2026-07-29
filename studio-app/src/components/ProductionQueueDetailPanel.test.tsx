import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ProductionQueueDetailPanel from './ProductionQueueDetailPanel'

describe('ProductionQueueDetailPanel', () => {
  it('renders bounded queue item inspection controls', () => {
    const html = renderToStaticMarkup(<ProductionQueueDetailPanel projectId="project_q" />)

    expect(html).toContain('Production Queue')
    expect(html).toContain('Inspectable work items')
    expect(html).toContain('Waiting')
    expect(html).toContain('Provider')
    expect(html).toContain('No queue items match this view.')
  })
})

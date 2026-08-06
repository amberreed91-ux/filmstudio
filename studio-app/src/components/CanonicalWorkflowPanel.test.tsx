import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import CanonicalWorkflowPanel from './CanonicalWorkflowPanel'

vi.mock('../hooks/useCanonicalWorkflow', () => ({
  useCanonicalWorkflow: () => ({
    run: null,
    availableRuns: [],
    currentBlueprintVersionId: 'blueprint-version-1',
    transitions: [],
    loading: false,
    polling: false,
    action: '',
    error: '',
    setError: vi.fn(),
    accept: vi.fn(),
    perform: vi.fn(),
    refresh: vi.fn(),
  }),
}))

describe('CanonicalWorkflowPanel', () => {
  it('renders exact project and scene context with an explicit start action', () => {
    const html = renderToStaticMarkup(
      <CanonicalWorkflowPanel
        projectId="project-1"
        sceneId="scene-2"
        sceneContext={{ scriptId: 'script-1', sequenceId: 'sequence-2', beatIds: ['beat-1'] }}
        surface="previs"
      />,
    )

    expect(html).toContain('data-project-id="project-1"')
    expect(html).toContain('data-scene-id="scene-2"')
    expect(html).toContain('data-workflow-status="not_started"')
    expect(html).toContain('Start approved production thread')
    expect(html).toMatch(/<button type="button" class="[^"]*">Start approved production thread<\/button>/)
  })
})

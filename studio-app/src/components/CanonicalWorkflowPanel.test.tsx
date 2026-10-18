import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

import CanonicalWorkflowPanel from './CanonicalWorkflowPanel'

const state = vi.hoisted(() => ({
  sceneContext: null as null | { scriptId: string; sequenceId: string; beatIds: string[] },
}))

vi.mock('../hooks/useCanonicalWorkflow', () => ({
  useCanonicalWorkflow: () => ({
    run: null,
    sceneContext: state.sceneContext,
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
  afterEach(() => { state.sceneContext = null })
  it('uses server-resolved script context to enable an older saved film', () => {
    state.sceneContext = { scriptId: 'script_saved', sequenceId: '', beatIds: [] }
    const html = renderToStaticMarkup(<CanonicalWorkflowPanel projectId="project-1" sceneId="scene-2" sceneContext={{ scriptId: '', sequenceId: '', beatIds: [] }} surface="previs" />)
    expect(html).toMatch(/<button type="button" class="[^"]*">Start approved production thread<\/button>/)
    expect(html).not.toContain('Save this film')
  })

  it('names the selected real provider in the production panel', () => {
    const html = renderToStaticMarkup(<CanonicalWorkflowPanel projectId="project-1" sceneId="scene-2" sceneContext={{ scriptId: 'script-1', sequenceId: '', beatIds: [] }} surface="previs" renderProvider="runway" renderProviderLabel="Runway" />)
    expect(html).toContain('Runway')
    expect(html).not.toContain('simulated provider')
    expect(html).toContain('Retries and revisions retain their original render provider')
  })

  it('labels the Previs step as simulated-only regardless of the render provider picker', () => {
    const html = renderToStaticMarkup(<CanonicalWorkflowPanel projectId="project-1" sceneId="scene-2" sceneContext={{ scriptId: 'script-1', sequenceId: '', beatIds: [] }} surface="previs" renderProvider="runway" renderProviderLabel="Runway" />)
    expect(html).toContain('data-testid="canonical-previs-provider"')
    expect(html).toContain('Simulated previs: instant, no cost')
    expect(html).not.toContain('New Previs uses the server default')
  })

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

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  beginCanonicalWorkflow,
  listCanonicalWorkflows,
  renderCanonicalProductionPackage,
} from './canonicalWorkflowApi'

const emptyList = { runs: [], current_blueprint_version_id: 'blueprint-version-2' }

describe('canonical workflow API', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('lists the exact project and scene without duplicating the API prefix', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(emptyList), { status: 200 }),
    )

    await listCanonicalWorkflows('project alpha', 'scene/one')

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/projects/project%20alpha/production-threads?scene_id=scene%2Fone')
    expect(String(url)).not.toContain('/api/api/')
    expect((init?.method || 'GET').toUpperCase()).toBe('GET')
  })

  it('begins a thread with explicit canonical identifiers and ordered beats', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ run: {}, transitions: [] }), { status: 200 }),
    )

    await beginCanonicalWorkflow({
      projectId: 'project-1',
      sceneId: 'scene-1',
      scriptId: 'script-1',
      sequenceId: 'sequence-1',
      beatIds: ['beat-1', 'beat-2'],
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/projects/project-1/scenes/scene-1/production-thread')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({
      script_id: 'script-1',
      sequence_id: 'sequence-1',
      beat_ids: ['beat-1', 'beat-2'],
    })
  })

  it('rejects undefined identifiers before issuing a request', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')

    expect(() => listCanonicalWorkflows('undefined', 'scene-1')).toThrow('Project ID is required')
    expect(() => renderCanonicalProductionPackage('null')).toThrow('Workflow ID is required')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('uses one POST against the existing run when render is confirmed', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ run: {}, transitions: [] }), { status: 200 }),
    )

    await renderCanonicalProductionPackage('run-1', true)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/production-threads/run-1/renders')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ provider: 'simulated', retry_confirmed: true })
  })
})

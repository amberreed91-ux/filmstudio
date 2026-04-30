import { afterEach, describe, expect, it, vi } from 'vitest'
import { getStudioProject } from './studioApi'

describe('getStudioProject', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('includes session_id query when provided', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ project_id: 'proj-1' }), { status: 200 }),
    )

    await getStudioProject('proj-1', { sessionId: 'session-123' })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/projects/proj-1?session_id=session-123')
  })

  it('omits session_id query when absent', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ project_id: 'proj-2' }), { status: 200 }),
    )

    await getStudioProject('proj-2')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/projects/proj-2')
    expect(String(url)).not.toContain('session_id=')
  })

  it('preserves execution_summary.scene_intent from project response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          project_id: 'test-scene-intent',
          execution_summary: {
            production_signal: { message: 'Render in progress' },
            scene_intent: { type: 'intent_label', label: 'quiet emotional moment' },
          },
        }),
        { status: 200 },
      ),
    )

    const project = await getStudioProject('test-scene-intent')
    expect(project.execution_summary?.scene_intent).toEqual({
      type: 'intent_label',
      label: 'quiet emotional moment',
    })
  })
})

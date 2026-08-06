import { afterEach, describe, expect, it, vi } from 'vitest'

import { getStitchDownload, getStitchStatus, triggerStitch } from './stitchingApi'

describe('film stitching API routes', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses the canonical trigger, status, and download paths and methods', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({
        job: { project_id: 'project-1', status: 'pending' },
        advisory: 'Stitch started.',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        project_id: 'project-1',
        status: 'running',
        progress: 25,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        output_url: '/outputs/project-1/stitched.mp4',
        download_url: '/outputs/project-1/stitched.mp4',
        mock_mode: true,
        advisory: 'Ready.',
      }), { status: 200 }))

    await triggerStitch('project-1')
    await getStitchStatus('project-1')
    await getStitchDownload('project-1')

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method || 'GET']))
      .toEqual([
        ['/api/f51/studio/projects/project-1/stitch', 'POST'],
        ['/api/f51/studio/projects/project-1/stitch/status', 'GET'],
        ['/api/f51/studio/projects/project-1/stitch/download', 'GET'],
      ])
  })
})

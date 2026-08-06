import { afterEach, describe, expect, it, vi } from 'vitest'

import { getExportDownload, getExportStatus, triggerExport } from './exportApi'

describe('final export API routes', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses the canonical trigger, status, and download paths and methods', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({
        job: { project_id: 'project-1', status: 'pending' },
        advisory: 'Export started.',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        project_id: 'project-1',
        status: 'running',
        progress: 25,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        output_url: '/outputs/project-1/final.mp4',
        download_url: '/outputs/project-1/final.mp4',
        mock_mode: true,
        advisory: 'Ready.',
      }), { status: 200 }))

    await triggerExport('project-1', { resolution: '1080p' })
    await getExportStatus('project-1')
    await getExportDownload('project-1')

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method || 'GET']))
      .toEqual([
        ['/api/f51/studio/projects/project-1/export', 'POST'],
        ['/api/f51/studio/projects/project-1/export/status', 'GET'],
        ['/api/f51/studio/projects/project-1/export/download', 'GET'],
      ])
  })
})

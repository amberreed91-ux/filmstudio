import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createClipRevision,
  getEditorialRevisionIntelligence,
  getTimelineIntelligence,
  getProjectDecisionGate,
  getStudioProject,
  resolveStudioApiBase,
  seedDemoStudioProject,
} from './studioApi'

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

describe('getProjectDecisionGate', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('normalizes wrapped decision gate payloads', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          gate: {
            project_id: 'proj-wrap',
            gate_status: 'ready',
            current_stage: 'package',
            blockers: [],
            warnings: [],
            ready_signals: ['Package is ready'],
            recommended_next_action: 'Ready: approved cut can be packaged.',
            evidence: {},
            advisory_only: true,
            auto_approval_triggered: false,
            auto_regeneration_triggered: false,
          },
        }),
        { status: 200 },
      ),
    )

    const gate = await getProjectDecisionGate('proj-wrap')
    expect(gate.gate_status).toBe('ready')
    expect(gate.recommended_next_action).toContain('approved cut')
  })
})

describe('getTimelineIntelligence', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches project timeline intelligence from the dedicated endpoint', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          project_id: 'proj-timeline',
          assembly_kind: 'stitched_film',
          clip_count: 3,
          pacing_read: 'Readable pulse.',
          tension_curve: 'Escalation lands.',
          slow_sections: [],
          escalation_points: [],
          emotional_residue_points: [],
          abrupt_transition_flags: [],
          tonal_consistency_read: 'Stable.',
          advisory_notes: [],
        }),
        { status: 200 },
      ),
    )

    await getTimelineIntelligence('proj-timeline')

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/projects/proj-timeline/timeline-intelligence')
  })
})

describe('getEditorialRevisionIntelligence', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('calls editorial revision intelligence endpoint with revision ids and emphasis', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          project_id: 'proj-edit',
          baseline_revision_id: 'rev-a',
          comparison_revision_id: 'rev-b',
          baseline_summary: {},
          comparison_summary: {},
          pacing_tradeoff: 'x',
          escalation_tradeoff: 'x',
          emotional_residue_tradeoff: 'x',
          tonal_consistency_tradeoff: 'x',
          structural_clarity_tradeoff: 'x',
          strongest_difference: 'x',
          advisory_notes: [],
        }),
        { status: 200 },
      ),
    )

    await getEditorialRevisionIntelligence('proj-edit', {
      baselineRevisionId: 'rev-a',
      comparisonRevisionId: 'rev-b',
      revisionEmphasis: 'emotional_residue',
    })

    const [url] = fetchMock.mock.calls[0]
    const urlText = String(url)
    expect(urlText).toContain('/api/f51/studio/projects/proj-edit/editorial-revision-intelligence')
    expect(urlText).toContain('baseline_revision_id=rev-a')
    expect(urlText).toContain('comparison_revision_id=rev-b')
    expect(urlText).toContain('revision_emphasis=emotional_residue')
  })
})

describe('clip revision API helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses centralized API base for clip revision calls', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ revision: { revision_id: 'rev-1' } }), { status: 200 }),
    )

    await createClipRevision('proj-clip', {
      review_id: 'review-1',
      original_job_id: 'job-1',
      provider: 'mock_success',
      revision_prompt: 'tighten pacing',
      revision_reason: 'continuity',
    })

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/projects/proj-clip/clip-revisions')
  })
})

describe('seed demo studio project helper', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('posts to the demo seed endpoint with deterministic project id', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          project_id: 'demo_studio_cinematic_001',
          study_room_url: '/studio/study-room?project_id=demo_studio_cinematic_001',
          previs_url: '/studio/previs?project_id=demo_studio_cinematic_001',
          production_url: '/studio/production-board?project_id=demo_studio_cinematic_001',
          screening_url: '/studio/screening-room?project_id=demo_studio_cinematic_001',
          crew_ops_url: '/studio/scheduler?project_id=demo_studio_cinematic_001',
        }),
        { status: 200 },
      ),
    )

    await seedDemoStudioProject()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/dev/seed-demo-project')
    expect((init?.method || '').toUpperCase()).toBe('POST')
    expect(String(init?.body || '')).toContain('demo_studio_cinematic_001')
  })
})

describe('resolveStudioApiBase', () => {
  it('defaults to localhost 8010 when no env is provided', () => {
    expect(resolveStudioApiBase({})).toBe('http://127.0.0.1:8010')
  })

  it('prefers configured VITE_API_BASE_URL when provided', () => {
    expect(resolveStudioApiBase({ VITE_API_BASE_URL: 'http://10.1.2.3:9000/' })).toBe('http://10.1.2.3:9000')
  })

  it('normalizes stale local 8012 configuration to 8010', () => {
    expect(resolveStudioApiBase({ VITE_API_BASE_URL: 'http://127.0.0.1:8012' })).toBe('http://127.0.0.1:8010')
    expect(resolveStudioApiBase({ VITE_STUDIO_API_BASE: 'http://localhost:8012/' })).toBe('http://127.0.0.1:8010')
  })
})

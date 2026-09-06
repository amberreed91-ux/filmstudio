import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createClipRevision,
  createCameraGrammarPlan,
  createWorkflowVersion,
  buildCameraGrammarRenderContext,
  getEditorialRevisionIntelligence,
  getTimelineIntelligence,
  getProjectWorkflow,
  getProjectDecisionGate,
  getStudioProject,
  enhancePrevisPrompt,
  generatePrevisScene,
  approvePrevisImage,
  getScreeningManifest,
  approveScreeningOutput,
  getCurrentFilmCut,
  updateFilmCutTimeline,
  approveFilmCut,
  generateSceneStoryboard,
  generateScenePipeline,
  recommendGenerationSettings,
  refreshRenderJobOutputUrl,
  recordWorkflowDecision,
  retryRenderJobForAdherence,
  buildStudioApiUrl,
  resolveStudioApiBase,
  seedDemoStudioProject,
  updateWorkflowPhase,
  triggerDebate,
} from './studioApi'

describe('camera grammar API', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends the visible Previs prompt and take settings to the backend', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ job_id: 'j', status: 'pending', scene_id: 's' })))
    const renderSettings = { prompt: 'Close on her left hand. She keeps the key.', duration_seconds: 8, resolution: '1080p' as const, seed: 0 }
    await generatePrevisScene('p', 's', { provider: 'openrouter-video', shotNumber: 2, takeNumber: 3, renderSettings })
    const [url, request] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('provider=openrouter-video')
    expect(String(url)).toContain('take_number=3')
    expect(JSON.parse(String(request?.body))).toEqual(renderSettings)
    expect(new Headers(request?.headers).get('Content-Type')).toBe('application/json')
  })

  it('creates camera grammar plans through the cinematography API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          plan: {
            plan_id: 'cam-plan-1',
            project_id: 'project_cam',
            plan_scope: 'scene',
            status: 'active',
            source_fingerprint: 'abc',
            source_summary: '',
            grammar_axes: [],
            composition_intent: 'isolation',
            lens_intent: 'observational_normal',
            movement_intent: 'locked_observation',
            lighting_intent: 'motivated_practical',
            framing_intent: 'medium',
            depth_strategy: '',
            blocking_strategy: '',
            screen_direction_strategy: '',
            visual_storytelling_rationale: '',
            render_slot_suggestions: [],
            evidence_refs: [],
            memory_refs: [],
            spine_refs: [],
            confidence_label: 'emerging',
            creator_note: '',
            advisory_only: true,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
            metadata: {},
          },
          reasoning_record_id: '',
          stale_existing_plan_ids: [],
          advisory_only: true,
        }),
        { status: 200 },
      ),
    )

    const result = await createCameraGrammarPlan('project_cam', {
      scene_id: 'scene_001',
      scene_context: { visual_description: 'A held frame.' },
    })

    expect(result.plan.plan_id).toBe('cam-plan-1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/projects/project_cam/cinematography/plans')
    expect(JSON.parse(String(init?.body))).toMatchObject({ scene_id: 'scene_001' })
  })

  it('builds camera grammar render context through the slot endpoint', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          plan_id: 'cam-plan-1',
          project_id: 'project_cam',
          camera_direction: 'medium framing',
          lighting_direction: 'practical light',
          slot_suggestions: [],
          evidence_refs: [],
          budget: { camera_limit: 70, lighting_limit: 60 },
          advisory_only: true,
          metadata: {},
        }),
        { status: 200 },
      ),
    )

    const result = await buildCameraGrammarRenderContext('project_cam', {
      plan_id: 'cam-plan-1',
      provider: 'runway',
    })

    expect(result.budget.camera_limit).toBe(70)
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/projects/project_cam/cinematography/render-context')
  })
})

describe('enhancePrevisPrompt', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('preserves exact context-supplied provenance from the API response', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          enhanced_prompt: 'A materially richer Chicago shot.',
          original_prompt: 'A Chicago shot.',
          study_memories_used: 8,
          scene_context_used: true,
          character_profiles_used: 2,
          enhancement_attempts: 2,
        }),
        { status: 200 },
      ),
    )

    const result = await enhancePrevisPrompt('film-1', {
      scene_id: 'scene_001',
      prompt_text: 'A Chicago shot.',
    })

    expect(result.study_memories_used).toBe(8)
    expect(result.scene_context_used).toBe(true)
    expect(result.enhancement_attempts).toBe(2)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/film-1/previs/enhance-prompt')
    expect(JSON.parse(String(init?.body))).toEqual({
      scene_id: 'scene_001',
      prompt_text: 'A Chicago shot.',
    })
  })
})

describe('generateSceneStoryboard', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('defaults storyboard generation to Qwen Image Max', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          image_url: '/previs-assets/proj-1/scene_001_storyboard_qwen.png',
          status: 'complete',
          provider: 'dashscope',
          model: 'qwen-image-max',
        }),
        { status: 200 },
      ),
    )

    const result = await generateSceneStoryboard('proj-1', 'scene_001', 'qwen-image-max', 2)

    expect(result.model).toBe('qwen-image-max')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/proj-1/scenes/scene_001/storyboard?provider=qwen-image-max')
    expect(String(url)).toContain('shot_number=2')
    expect((init?.method || '').toUpperCase()).toBe('POST')
  })

  it('can request the legacy storyboard provider', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          image_url: 'https://image.pollinations.ai/prompt/test',
          status: 'complete',
          provider: 'pollinations',
          model: 'pollinations.ai',
        }),
        { status: 200 },
      ),
    )

    await generateSceneStoryboard('proj-1', 'scene_001', 'pollinations')

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('provider=pollinations')
  })
})

describe('Previs lifecycle API', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('threads the exact storyboard shot into generation', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        job_id: 'job-previs-1',
        status: 'pending',
        scene_id: 'scene_001',
        previs_image_id: 'previs-1',
        storyboard_shot_id: 'storyboard-shot-1',
        duplicate: false,
      }), { status: 200 }),
    )

    const result = await generatePrevisScene('project-1', 'scene_001', {
      shotNumber: 2,
      takeNumber: 3,
      storyboardShotId: 'storyboard-shot-1',
      allowApprovedRevision: true,
    })

    expect(result.previs_image_id).toBe('previs-1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/project-1/previs/generate-scene/scene_001')
    expect(String(url)).toContain('storyboard_shot_id=storyboard-shot-1')
    expect(String(url)).toContain('allow_approved_revision=true')
    expect((init?.method || '').toUpperCase()).toBe('POST')
  })

  it('uses the deliberate approval endpoint', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        id: 'previs-1', project_id: 'project-1', scene_id: 'scene_001', image_path: 'https://media.test/1.mp4',
        job_id: 'job-1', status: 'approved', prompt_used: 'held close-up', fallback: false,
        approved: true, attempt_number: 1, metadata: {}, created_at: 'now', updated_at: 'now',
      }), { status: 200 }),
    )

    await approvePrevisImage('project-1', 'previs-1', 'creator')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/project-1/previs/records/previs-1/approve')
    expect(JSON.parse(String(init?.body))).toEqual({ approved_by: 'creator' })
  })
})

describe('Screening Room lifecycle API', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the project-scoped browser-safe manifest', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        project_id: 'project-1',
        outputs: [],
        current_final_output: null,
        completion_status: 'in_progress',
        warnings: [],
      }), { status: 200 }),
    )
    await getScreeningManifest('project-1')
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/project-1/screening/manifest?refresh=true')
  })

  it('sends explicit creator confirmation for approval', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        screening_output_id: 'screening-1', project_id: 'project-1', source_type: 'render_job',
        source_id: 'job-1', output_type: 'shot', playback_url: '/screening/media/1', mime_type: 'video/mp4',
        media_status: 'available', approved: true, metadata: {}, created_at: 'now', updated_at: 'now',
      }), { status: 200 }),
    )
    await approveScreeningOutput('project-1', 'screening-1', 'creator')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/project-1/screening/outputs/screening-1/approve')
    expect(JSON.parse(String(init?.body))).toEqual({ confirmed: true, approved_by: 'creator' })
  })
})

describe('Film Cut lifecycle API', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  const cut = {
    cut_id: 'cut-v2', project_id: 'project-1', version_number: 2, status: 'draft',
    source_cut_id: 'cut-v1', scene_order: ['scene_001'], timeline: [], metadata: {},
    created_at: 'now', updated_at: 'now',
  }

  it('loads the canonical current Film Cut', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ film_cut: cut }), { status: 200 }),
    )
    const result = await getCurrentFilmCut('project-1')
    expect(result.film_cut.cut_id).toBe('cut-v2')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/projects/project-1/film-cut')
  })

  it('threads the expected version and explicit confirmation into timeline updates', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ film_cut: cut }), { status: 200 }),
    )
    await updateFilmCutTimeline('project-1', {
      expected_cut_id: 'cut-v2',
      scene_order: ['scene_001'],
      timeline: [{ scene_id: 'scene_001', clip_id: 'clip-1' }],
      creator_confirmation: true,
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/project-1/film-cut/timeline')
    expect(JSON.parse(String(init?.body))).toMatchObject({
      expected_cut_id: 'cut-v2', creator_confirmation: true,
    })
  })

  it('uses the explicit Film Cut approval endpoint', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ film_cut: { ...cut, status: 'approved' } }), { status: 200 }),
    )
    await approveFilmCut('project-1', 'cut-v2')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/projects/project-1/film-cut/cut-v2/approve')
    expect(JSON.parse(String(init?.body))).toEqual({ creator_confirmation: true, approved_by: 'creator' })
  })
})

describe('recommendGenerationSettings', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns duration constraints with the recommendation', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          scene_id: 'scene_001',
          shot_number: 2,
          recommended: {
            duration_seconds: 6,
            fps: 16,
            resolution: '720p',
            model: 'Wan 2.2',
          },
          duration_constraint: {
            provider: 'Wan 2.2',
            supports_custom_duration: true,
            valid_durations_seconds: [4, 8, 12, 16, 20],
            nearest_valid_duration_seconds: 8,
            advisory: 'Editable.',
          },
          reasoning: 'Enough time for the push-in to register.',
          study_memories_used: 1,
        }),
        { status: 200 },
      ),
    )

    const result = await recommendGenerationSettings('proj-1', {
      scene_id: 'scene_001',
      shot_number: 2,
      shot_type: 'close',
    })

    expect(result.duration_constraint.nearest_valid_duration_seconds).toBe(8)
    expect(result.reasoning).toContain('push-in')
  })

  it('backfills duration constraints from an older backend response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          scene_id: 'scene_001',
          shot_number: 1,
          recommended: {
            duration_seconds: 8,
            fps: 12,
            resolution: '720p',
            model: 'Wan 2.2',
          },
          reasoning: 'The establishing frame needs room to settle.',
          study_memories_used: 2,
        }),
        { status: 200 },
      ),
    )

    const result = await recommendGenerationSettings('proj-1', {
      scene_id: 'scene_001',
      shot_number: 1,
      shot_type: 'wide',
    })

    expect(result.duration_constraint).toMatchObject({
      provider: 'Wan 2.2',
      supports_custom_duration: true,
      nearest_valid_duration_seconds: 8,
    })
  })
})

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

describe('generateScenePipeline', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('calls the scene pipeline endpoint with manual post-render soundtrack payload', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 'complete',
          project_id: 'proj-scene',
          scene_id: 'scene_003',
          shots: [],
          stitch: {
            project_id: 'proj-scene',
            scene_id: 'scene_003',
            clip_count: 2,
            output_path: '/tmp/scene.mp4',
            output_url: '/outputs/scene.mp4',
            status: 'completed',
          },
          output_url: '/outputs/scene.mp4',
          score_ambient_provider: 'manual_post_render',
          soundtrack_status: 'manual_post_render',
        }),
        { status: 200 },
      ),
    )

    const response = await generateScenePipeline('proj-scene', 'scene_003', {
      provider: 'happyhorse',
      overwrite: true,
      score_ambient_provider: 'manual_post_render',
      soundtrack: {
        enabled: true,
        audio_source_type: 'local_file',
        local_audio_path: '/tmp/score.wav',
        volume: 0.18,
      },
    })

    expect(response.result?.status).toBe('complete')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/projects/proj-scene/scenes/scene_003/pipeline/generate')
    expect(init?.method).toBe('POST')
    const body = JSON.parse(String(init?.body))
    expect(body).toEqual({
      provider: 'happyhorse',
      overwrite: true,
      on_audio_overrun: 'freeze_last_frame',
      score_ambient_provider: 'manual_post_render',
      soundtrack: {
        enabled: true,
        audio_source_type: 'local_file',
        local_audio_path: '/tmp/score.wav',
        volume: 0.18,
      },
    })
  })

  it('returns an error object when scene pipeline generation fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Scene soundtrack enabled but missing audio source' }), { status: 400 }),
    )

    const response = await generateScenePipeline('proj-scene', 'scene_003', {
      score_ambient_provider: 'manual_post_render',
      soundtrack: { enabled: true, audio_source_type: 'local_file' },
    })

    expect(response.error).toContain('Scene soundtrack enabled but missing audio source')
    expect(response.result).toBeUndefined()
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

describe('render refresh helper', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('posts to the refresh-url endpoint for a render job', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ output_url: 'https://example.com/fresh.mp4' }), { status: 200 }),
    )

    await refreshRenderJobOutputUrl('job-123')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/render/jobs/job-123/refresh-url')
    expect((init?.method || '').toUpperCase()).toBe('POST')
  })
})

describe('retryRenderJobForAdherence', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('posts to the explicit adherence retry endpoint with combined strategy', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ strategy: 'combined_reorder_and_fresh_seeds', jobs_submitted: [] }), { status: 200 }),
    )

    await retryRenderJobForAdherence('job-adherence', 2)

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/render/jobs/job-adherence/adherence-retry')
    expect((init?.method || '').toUpperCase()).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({
      max_attempts: 2,
      submission_strategy: 'combined_reorder_and_fresh_seeds',
    })
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
  it('defaults to relative URLs when no env is provided', () => {
    expect(resolveStudioApiBase({})).toBe('')
  })

  it('prefers configured VITE_API_BASE_URL when provided', () => {
    expect(resolveStudioApiBase({ VITE_API_BASE_URL: 'http://10.1.2.3:9000/' })).toBe('http://10.1.2.3:9000')
  })

  it('normalizes stale local 8012 configuration to relative proxy URLs', () => {
    expect(resolveStudioApiBase({ VITE_API_BASE_URL: 'http://127.0.0.1:8012' })).toBe('')
    expect(resolveStudioApiBase({ VITE_STUDIO_API_BASE: 'http://localhost:8012/' })).toBe('')
  })

  it('joins API paths without duplicating an /api base suffix', () => {
    expect(buildStudioApiUrl('/api/f51/studio/projects', 'https://studio.example/api/'))
      .toBe('https://studio.example/api/f51/studio/projects')
    expect(buildStudioApiUrl('/api/f51/studio/projects', 'https://studio.example'))
      .toBe('https://studio.example/api/f51/studio/projects')
    expect(buildStudioApiUrl('/outputs/project/final.mp4', 'https://studio.example/api'))
      .toBe('https://studio.example/outputs/project/final.mp4')
    expect(buildStudioApiUrl('/api/f51/studio/projects', ''))
      .toBe('/api/f51/studio/projects')
  })
})

describe('co-director debate API', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('uses the mounted canonical debate prefix', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ debate: { debate_id: 'debate-1' } }), { status: 200 }),
    )

    await triggerDebate({ project_id: 'project-1', query: 'Hold on the final reaction?' })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/api/f51/studio/debate/trigger')
    expect((init?.method || '').toUpperCase()).toBe('POST')
  })
})

describe('getSceneRationale', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches rationale with correct URL', async () => {
    const mockResponse = {
      rationale: 'A melancholic scene at SHORELINE where MARA takes the frame.',
      scene_context: { scene_id: 'scene_001', characters: ['MARA'], location: 'SHORELINE', emotional_tone: 'melancholic', scene_heading: 'EXT. SHORELINE - DAWN' },
      emotional_context: { emotional_register: 'melancholic reflection', tonal_direction: 'escalating', active_motifs: [] },
      scene_position: 1,
      total_scenes: 5,
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mockResponse), { status: 200 }),
    )

    const { getSceneRationale } = await import('./studioApi')
    const result = await getSceneRationale('proj-1', 'scene_001')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/f51/studio/projects/proj-1/scenes/scene_001/rationale')
    expect(result.rationale).toBe(mockResponse.rationale)
    expect(result.scene_position).toBe(1)
  })

  it('throws on 404', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Scene not found' }), { status: 404 }),
    )

    const { getSceneRationale } = await import('./studioApi')
    await expect(getSceneRationale('proj-1', 'nonexistent')).rejects.toThrow()
  })
})

describe('studio workflow API', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads project workflow summary from the canonical workflow route', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          project_state: {
            project_id: 'project_s9',
            current_phase: 'screening',
            workflow_status: 'waiting_creator',
            created_at: '2026-07-27T00:00:00Z',
            updated_at: '2026-07-27T00:00:00Z',
          },
          collaborators: [],
          active_gates: [],
          active_versions: [],
          open_tasks: [],
          recent_events: [],
        }),
        { status: 200 },
      ),
    )

    const result = await getProjectWorkflow('project_s9')

    expect(result.project_state.current_phase).toBe('screening')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/f51/studio/projects/project_s9/workflow')
  })

  it('creates workflow versions with JSON payloads', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          version_id: 'sw_ver_1',
          project_id: 'project_s9',
          artifact_type: 'scene',
          artifact_id: 'scene_001',
          version_number: 1,
          status: 'draft',
          created_at: '2026-07-27T00:00:00Z',
          updated_at: '2026-07-27T00:00:00Z',
        }),
        { status: 200 },
      ),
    )

    const result = await createWorkflowVersion('project_s9', {
      artifact_type: 'scene',
      artifact_id: 'scene_001',
      created_by: 'owner',
    })

    const [, init] = fetchMock.mock.calls[0]
    expect(result.version_id).toBe('sw_ver_1')
    expect((init?.method || '').toUpperCase()).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({
      artifact_type: 'scene',
      artifact_id: 'scene_001',
      created_by: 'owner',
    })
  })

  it('records workflow decisions against a gate', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          decision_id: 'sw_dec_1',
          project_id: 'project_s9',
          gate_id: 'sw_gate_1',
          actor_id: 'producer',
          actor_role: 'producer',
          decision: 'approve',
          created_at: '2026-07-27T00:00:00Z',
        }),
        { status: 200 },
      ),
    )

    const result = await recordWorkflowDecision('project_s9', 'sw_gate_1', {
      actor_id: 'producer',
      actor_role: 'producer',
      decision: 'approve',
      rationale: 'Ready for the next room.',
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/workflow/gates/sw_gate_1/decisions')
    expect((init?.method || '').toUpperCase()).toBe('POST')
    expect(result.decision).toBe('approve')
  })

  it('updates workflow phase with a PUT request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          project_id: 'project_s9',
          current_phase: 'screening',
          workflow_status: 'waiting_creator',
          created_at: '2026-07-27T00:00:00Z',
          updated_at: '2026-07-27T00:00:00Z',
        }),
        { status: 200 },
      ),
    )

    const result = await updateWorkflowPhase('project_s9', {
      actor_id: 'producer',
      phase: 'screening',
      workflow_status: 'waiting_creator',
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/workflow/phase')
    expect((init?.method || '').toUpperCase()).toBe('PUT')
    expect(result.current_phase).toBe('screening')
  })
})

import { http, HttpResponse, delay } from 'msw'
import {
  PROJECT,
  APPROVAL_GATES,
  CREW,
  PIPELINE_STAGES,
  RENDER_QUEUE,
} from '../data/mock'

// ---------------------------------------------------------------------------
// Shared fixture builders
// ---------------------------------------------------------------------------

function buildStudioProject(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    project_id: PROJECT.id,
    title: PROJECT.name,
    updated_at: new Date().toISOString(),
    source_stats: {
      scene_count: PROJECT.scenes,
      shot_count: PROJECT.shots,
      render_count: 18,
      character_count: 7,
      word_count: 4200,
      target_runtime_minutes: 94,
      source_filename: 'neon_afterglow_v2.4.fountain',
    },
    render_provider: {
      provider_name: 'Runway',
      provider_model: 'Deco GPUS',
      status: 'running',
      mode: 'batch',
    },
    production_bible: {
      creative_intent:
        'Neo-noir thriller exploring surveillance capitalism through the lens of a jaded detective in a rain-soaked megacity. Tone: cinematic, morally ambiguous, visually lush.',
    },
    render_provider_integrations: [
      {
        provider: 'Runway',
        selected: true,
        status: 'active',
        live_generation: 'enabled',
        requires: ['api_key', 'bucket'],
      },
      {
        provider: 'RunPod',
        selected: false,
        status: 'standby',
        live_generation: 'enabled',
        requires: ['api_key'],
      },
      {
        provider: 'Local',
        selected: false,
        status: 'standby',
        live_generation: 'disabled',
        requires: [],
      },
      {
        provider: 'AMD MI300X',
        selected: false,
        status: 'standby',
        live_generation: 'enabled',
        requires: ['api_key', 'api_endpoint'],
        gpu: 'MI300X',
        runtime: 'ROCm',
        models: ['ltx-2', 'hunyuan-video'],
      },
    ],
    shot_approval_gates: APPROVAL_GATES.map((g) => ({
      ...g,
      shot_id: `shot_${g.id}_001`,
    })),
    crew_agents: CREW.map((member) => ({
      agent_id: member.id,
      name: member.name,
      task: member.task,
      status: 'active',
      color: member.color,
      department:
        member.id === 'director'
          ? 'directing'
          : member.id === 'storyboard'
            ? 'visual_development'
            : member.id === 'editor'
              ? 'post_production'
              : member.id === 'cinematographer'
                ? 'camera'
                : 'sound',
      contributions: [],
    })),
    storyboard_wall: [
      { shot_id: 'shot_001', scene: 'Scene 1', description: 'Establishing shot of city', status: 'approved' },
      { shot_id: 'shot_002', scene: 'Scene 2', description: 'Detective enters office', status: 'pending' },
      { shot_id: 'shot_003', scene: 'Scene 3', description: 'Surveillance footage reveal', status: 'flagged' },
    ],
    render_queue: RENDER_QUEUE.map((r, i) => ({
      render_id: `render_${String(i).padStart(3, '0')}`,
      shot_id: r.id,
      status: r.status.toLowerCase().replace(' ', '_'),
      progress: r.progress,
      eta: r.eta,
      cost_per_minute: r.cost,
      priority: r.priority,
      provider: i % 3 === 0 ? 'Runway' : (i % 3 === 1 ? 'RunPod' : 'AMD MI300X'),
    })),
    rights_safety_clearance_board: {
      overall_status: 'cleared',
      music: { status: 'cleared', notes: 'All tracks licensed' },
      talent: { status: 'cleared', notes: '7 talent releases on file' },
      locations: { status: 'cleared', notes: 'Permits valid through shoot end date' },
    },
    reference_study_library: {
      studies: [],
    },
    interactive_modules: {
      automated_dailies_selects: {
        items: RENDER_QUEUE.slice(0, 4).map((r, i) => ({
          render_id: `render_${String(i).padStart(3, '0')}`,
          shot_id: r.id,
          selected: false,
          score: 0,
          qc_note: '',
        })),
      },
    },
    producer_dashboard: {
      last_updated: new Date().toISOString(),
      dailies_count: 3,
      screening_status: 'scheduled',
    },
    project_dashboard: {
      cards: PIPELINE_STAGES.map((s) => ({
        id: s.id,
        label: s.label,
        status: s.status,
        progress: s.progress,
        detail: s.detail || null,
      })),
    },
    agent_activity_timeline: CREW.slice(0, 3).map((member, i) => ({
      agent_id: member.id,
      event: member.task,
      timestamp: new Date(Date.now() - i * 120000).toISOString(),
    })),
    continuity_register: {
      last_checked: new Date().toISOString(),
      open_issues: 2,
      issues: [
        { id: 'cont_001', scene: 'Scene 4B', type: 'prop', description: 'Detective badge missing in close-up' },
        { id: 'cont_002', scene: 'Scene 7', type: 'dialogue', description: 'Line 47 version mismatch' },
      ],
    },
    risk_register: [
      'Weather delay risk for Scene 12 (rooftop) — 20% probability',
      'Budget contingency at 12% — monitor weekly',
      'Key grip on medical leave — backup confirmed',
    ],
    next_actions: [
      'Review Scene 4B continuity flag',
      'Approve final color grade for Scene 1–3',
      'Schedule music cue recording for Scene 9',
    ],
    ...overrides,
  }
}

function buildStudioOverview(): Record<string, unknown> {
  return {
    build: '2.4.1',
    projects: [
      {
        project_id: PROJECT.id,
        title: PROJECT.name,
        updated_at: new Date().toISOString(),
        scene_count: PROJECT.scenes,
        shot_count: PROJECT.shots,
      },
    ],
    latest_project: buildStudioProject(),
  }
}

function buildStudyReference(): Record<string, unknown> {
  return {
    reference_id: `ref_${Date.now()}`,
    filename: 'reference_clip.mp4',
    content_type: 'video/mp4',
    rights_status: 'analysis_only',
    allowed_use: 'Study and inspiration only — not for reproduction',
    study_focus: 'cinematography, editing, sound, and production design',
    source_stats: {
      duration_seconds: 90,
      resolution: '1920x1080',
      frame_rate: 24,
    },
    extraction_status: 'complete',
    study_cards: [
      {
        agent: 'director',
        department: 'directing',
        study_focus: 'Slow push-in during emotional monologue',
        observations_to_make: [
          'Negative space used to convey isolation',
          'Practical lighting creates natural focal point',
          'Camera movement matches emotional arc',
        ],
        reusable_principles: [
          'Push in on emotional beats, pull back on action',
          'Use environmental elements as framing devices',
        ],
        forbidden_uses: ['Do not replicate exact blocking in similar scene types'],
        handoff_to: ['cinematographer', 'editor'],
      },
      {
        agent: 'cinematographer',
        department: 'camera',
        study_focus: 'Low-key lighting with single practical source',
        observations_to_make: [
          'Motivated light source visible in frame',
          'Deep shadows create mystery without losing subject',
        ],
        reusable_principles: [
          'Single motivated source > multiple artificial lights',
          'Shadows tell the story when the subject cannot',
        ],
        forbidden_uses: [],
        handoff_to: ['director'],
      },
      {
        agent: 'editor',
        department: 'post_production',
        study_focus: 'Match cut connecting two disparate locations',
        observations_to_make: [
          'Shape and rhythm of movement create continuity',
          'Sound bridge reinforces emotional connection',
        ],
        reusable_principles: ['Match movement, not subject, for seamless transitions'],
        forbidden_uses: [],
        handoff_to: ['director', 'sound_designer'],
      },
    ],
    risk_register: [
      'Reference clip contains third-party music — separate clearance may be needed for any recreation',
      'Aspect ratio difference from current project — recalculate framing',
    ],
    next_actions: [
      'Share relevant frames with cinematographer for lighting reference',
      'Add inspired sequences to storyboard mood board',
      'Log specific cuts for editing rhythm reference',
    ],
  }
}

// ---------------------------------------------------------------------------
// All 11 API handlers
// ---------------------------------------------------------------------------

export const handlers = [
  // GET /api/f51/studio/overview
  http.get('/api/f51/studio/overview', async () => {
    await delay(120)
    return HttpResponse.json(buildStudioOverview())
  }),

  // GET /api/f51/studio/projects/:projectId
  http.get('/api/f51/studio/projects/:projectId', async ({ params }) => {
    await delay(150)
    const { projectId } = params
    if (!projectId) return HttpResponse.json({ detail: 'Project ID required' }, { status: 400 })
    return HttpResponse.json(buildStudioProject({ project_id: String(projectId) }))
  }),

  // POST /api/f51/studio/demo-project
  http.post('/api/f51/studio/demo-project', async ({ request }) => {
    await delay(200)
    const form = await request.formData()
    const demoId = form.get('demo_id') || 'neon_aftertaste'
    return HttpResponse.json(
      buildStudioProject({ project_id: `demo-${demoId}-${Date.now()}` }),
    )
  }),

  // POST /api/f51/studio/ingest-script
  http.post('/api/f51/studio/ingest-script', async ({ request }) => {
    await delay(300)
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json(
      buildStudioProject({
        title: String(body.title || 'Untitled Project'),
        source_stats: {
          scene_count: 0,
          shot_count: 0,
          render_count: 0,
          character_count: 0,
          word_count: body.script_text ? String(body.script_text).split(/\s+/).length : 0,
          target_runtime_minutes: null,
          source_filename: null,
        },
        production_bible: { creative_intent: String(body.creative_intent || '') },
        render_provider: { provider_name: String(body.render_provider || ''), status: 'standby' },
      }),
    )
  }),

  // POST /api/f51/studio/study-reference-prompt
  http.post('/api/f51/studio/study-reference-prompt', async () => {
    await delay(400)
    return HttpResponse.json(buildStudyReference())
  }),

  // POST /api/f51/studio/study-reference
  http.post('/api/f51/studio/study-reference', async ({ request }) => {
    await delay(500)
    await request.formData()
    return HttpResponse.json(
      buildStudyReference(),
    )
  }),

  // POST /api/f51/studio/projects/:projectId/simulate-screening
  http.post('/api/f51/studio/projects/:projectId/simulate-screening', async ({ params }) => {
    await delay(250)
    const { projectId } = params
    const gates = APPROVAL_GATES.map((g) => ({
      ...g,
      shot_id: `shot_${g.id}_001`,
      // After screening simulation, creative gate moves to passed
      status: g.id === 'creative' ? 'passed' : g.status,
    }))
    return HttpResponse.json(
      buildStudioProject({
        project_id: String(projectId),
        shot_approval_gates: gates,
        producer_dashboard: { last_updated: new Date().toISOString(), dailies_count: 3, screening_status: 'complete' },
      }),
    )
  }),

  // POST /api/f51/studio/projects/:projectId/review-shot
  http.post('/api/f51/studio/projects/:projectId/review-shot', async ({ params, request }) => {
    await delay(150)
    const { projectId } = params
    const body = await request.json() as { shot_id?: string; decision?: string }
    if (!body.shot_id) return HttpResponse.json({ detail: 'shot_id required' }, { status: 400 })
    const updatedGates = APPROVAL_GATES.map((g) => ({
      ...g,
      shot_id: `shot_${g.id}_001`,
    }))
    return HttpResponse.json(
      buildStudioProject({ project_id: String(projectId), shot_approval_gates: updatedGates }),
    )
  }),

  // POST /api/f51/studio/projects/:projectId/dailies-select
  http.post('/api/f51/studio/projects/:projectId/dailies-select', async ({ params, request }) => {
    await delay(150)
    const { projectId } = params
    const body = await request.json() as { render_id?: string; selected?: boolean; score?: number; qc_note?: string }
    if (!body.render_id) return HttpResponse.json({ detail: 'render_id required' }, { status: 400 })
    const currentProject = buildStudioProject({ project_id: String(projectId) })
    const dailiesItems = (currentProject.interactive_modules as Record<string, unknown>).automated_dailies_selects as { items?: Array<Record<string, unknown>> }
    if (dailiesItems?.items) {
      const item = dailiesItems.items.find((i) => i.render_id === body.render_id)
      if (item) {
        item.selected = body.selected
        item.score = body.score ?? 0
        item.qc_note = body.qc_note ?? ''
      }
    }
    return HttpResponse.json(currentProject)
  }),

  // POST /api/f51/studio/projects/:projectId/retry-render/:renderId
  http.post('/api/f51/studio/projects/:projectId/retry-render/:renderId', async ({ params }) => {
    await delay(200)
    const { projectId, renderId } = params
    const currentProject = buildStudioProject({ project_id: String(projectId) })
    const queue = (currentProject.render_queue as Array<Record<string, unknown>>).map((r) => {
      if (r.render_id === renderId) {
        return { ...r, status: 'queued', progress: 0, eta: 'pending' }
      }
      return r
    })
    return HttpResponse.json({ ...currentProject, render_queue: queue })
  }),

  // POST /api/f51/studio/projects/:projectId/render-mode
  http.post('/api/f51/studio/projects/:projectId/render-mode', async ({ params, request }) => {
    await delay(150)
    const { projectId } = params
    const body = await request.json() as { live_mode?: boolean; provider_name?: string }
    return HttpResponse.json(
      buildStudioProject({
        project_id: String(projectId),
        render_provider: {
          provider_name: body.provider_name || 'Runway',
          status: body.live_mode ? 'running' : 'standby',
          mode: body.live_mode ? 'live' : 'batch',
        },
      }),
    )
  }),

  // GET /api/f51/studio/memory/:projectId - Agent memory
  http.get('/api/f51/studio/memory/:projectId', async ({ params }) => {
    await delay(50)
    const { projectId } = params
    return HttpResponse.json({
      project_id: String(projectId),
      project: {
        tone: 'noir',
        genre: 'thriller',
        visual_style: ['rain-soaked streets', 'neon signs'],
        color_grade: 'desaturated teal',
        lighting_mood: ['high contrast'],
        key_decisions: [],
      },
      scenes: {
        'scene-1': {
          scene_id: 'scene-1',
          location_name: 'Detective Office',
          time_of_day: 'night',
          weather: null,
          camera_choices: ['wide establishing'],
          lighting_notes: ['tighten'],
          color_palette: [],
          props_in_scene: [],
          character_positions: {},
          generated_shots: [],
          approved_shots: [],
        },
      },
      characters: {},
      style: {
        project_id: String(projectId),
        camera_language: 'cinematic wide',
        lighting_approach: 'high contrast noir',
        color_palette: ['teal', 'orange'],
        pacing_notes: '',
        frame_composition: '',
        movement_style: '',
        lens_preferences: [],
      },
      reviews: [],
      versions: [],
    })
  }),

  // POST /api/f51/studio/memory/:projectId/init
  http.post('/api/f51/studio/memory/:projectId/init', async ({ params }) => {
    await delay(50)
    return HttpResponse.json({
      status: 'success',
      version: 2,
      memory: {
        project_id: String(params.projectId),
        tone: 'noir',
        genre: 'thriller',
      },
    })
  }),
]

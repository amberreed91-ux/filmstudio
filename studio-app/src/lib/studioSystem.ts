import type { StudioOverview, StudioProject } from './studioApi'
import type { ProductionMode, SlateVariant } from './studioWorkspaceState'
import { getDailiesItems, getPipelineStages, getProjectStats, getProviderSummaries, getRenderQueueRows } from './studioSelectors'

type RecordLike = Record<string, unknown>

export type ProjectIdentity = {
  title: string
  genre: string
  tone: string
  audience: string
  influences: string[]
  budgetLevel: string
  productionMode: ProductionMode
  stage: string
  logline: string
  commercialPositioning: string
  festivalViability: string
}

export type WorkflowStageCard = {
  id: string
  label: string
  status: 'ready' | 'active' | 'watch' | 'pending'
  assignedAgents: string[]
  deliverables: string[]
  pendingApprovals: number
  revisionCount: number
  note: string
}

export type AgentContribution = {
  id: string
  department: string
  comment: string
  focus: string
  noveltyScore: number
}

export type AgentProfile = {
  id: string
  name: string
  role: string
  mission: string
  authorityBoundaries: string[]
  inputs: string[]
  outputs: string[]
  collaborationRules: string[]
  currentTask: string
  activityStatus: string
  performanceScore: number
  redundancyScore: number
  evaluation: {
    usefulness: number
    quality: number
    novelty: number
    alignment: number
    improvement: number
  }
  recentContributions: AgentContribution[]
  isDemo?: boolean
}

export type CrewThread = {
  id: string
  title: string
  objective: string
  status: 'aligned' | 'needs-escalation' | 'resolved'
  participants: string[]
  comments: AgentContribution[]
  escalation: string
  overlapSummary?: string
}

export type MemoryEntry = {
  id: string
  type: 'project' | 'character' | 'scene' | 'visual' | 'taste' | 'lesson'
  label: string
  detail: string
}

export type ReflectionCard = {
  id: string
  title: string
  worked: string
  failed: string
  redundant: string
  change: string
  improvement: string
}

export type OrchestrationSnapshot = {
  controllerStatus: string
  activeAgents: string[]
  bottlenecks: string[]
  nextBestActions: string[]
  approvalGates: string[]
  branchingOptions: string[]
}

export type SlateProjectCard = {
  id: string
  sourceProjectId: string
  title: string
  stage: string
  genre: string
  tone: string
  mode: ProductionMode
  status: string
  tagLine: string
  quickFacts: string[]
  archived: boolean
  kind: 'project' | 'duplicate' | 'branch'
  variantId?: string
}

const ROLE_SPECS: Record<string, {
  role: string
  department: string
  mission: string
  authorityBoundaries: string[]
  inputs: string[]
  outputs: string[]
  collaborationRules: string[]
  focus: string
}> = {
  director: {
    role: 'Director',
    department: 'Direction',
    mission: 'Guard tone, character arc, scene objective, and emotional payoff across the slate.',
    authorityBoundaries: ['Final tone lock', 'Performance emphasis', 'Scene objective approval'],
    inputs: ['creative intent', 'benchmark takes', 'producer priorities'],
    outputs: ['tone notes', 'performance notes', 'approval or revision call'],
    collaborationRules: ['Do not rewrite cinematography coverage notes.', 'Escalate only when emotional payoff slips.'],
    focus: 'tone',
  },
  cinematographer: {
    role: 'Cinematographer',
    department: 'Camera',
    mission: 'Own blocking, lensing, coverage, and visual motif while staying production-feasible.',
    authorityBoundaries: ['Coverage plan', 'Blocking adjustments', 'Lighting language'],
    inputs: ['director tone notes', 'storyboard beats', 'location constraints'],
    outputs: ['coverage plan', 'lighting plan', 'camera continuity notes'],
    collaborationRules: ['Hand pacing concerns to editorial.', 'Keep blocking notes distinct from performance notes.'],
    focus: 'coverage',
  },
  storyboard_artist: {
    role: 'Storyboard Artist',
    department: 'Previs',
    mission: 'Translate scene objective into readable blocking and shot geography.',
    authorityBoundaries: ['Frame sequencing', 'Blocking visualization', 'Coverage readability'],
    inputs: ['script beats', 'director notes', 'camera language'],
    outputs: ['shot sequence', 'blocking map', 'coverage alternatives'],
    collaborationRules: ['Avoid duplicating cinematography lens notes.', 'Surface alternate blocking only when coverage clarity improves.'],
    focus: 'blocking',
  },
  editor: {
    role: 'Editor',
    department: 'Editorial',
    mission: 'Shape pacing, editorial rhythm, transition logic, and emotional release.',
    authorityBoundaries: ['Editorial rhythm', 'Cut points', 'Transition strategy'],
    inputs: ['dailies selects', 'director take choices', 'sound bridge ideas'],
    outputs: ['pacing notes', 'transition notes', 'cut recommendations'],
    collaborationRules: ['Do not override sound palette choices.', 'Speak only to rhythm, payoff, and structural clarity.'],
    focus: 'pacing',
  },
  sound_designer: {
    role: 'Sound Designer',
    department: 'Sound',
    mission: 'Shape diegetic and non-diegetic sound so scenes land with clarity and atmosphere.',
    authorityBoundaries: ['Sound motif', 'diegetic ambience', 'non-diegetic swell planning'],
    inputs: ['editorial rhythm', 'scene transitions', 'tone references'],
    outputs: ['sound palette', 'bridge notes', 'mix priorities'],
    collaborationRules: ['Do not duplicate editorial pacing notes.', 'Anchor comments in sound perspective only.'],
    focus: 'sound',
  },
  production_designer: {
    role: 'Production Designer',
    department: 'Design',
    mission: 'Protect visual motif, world texture, and production feasibility of environments and props.',
    authorityBoundaries: ['Set dressing priorities', 'prop continuity', 'location texture'],
    inputs: ['creative intent', 'rights constraints', 'scene locations'],
    outputs: ['design notes', 'prop continuity', 'world-building flags'],
    collaborationRules: ['Do not restate director tone notes.', 'Only escalate when design harms continuity or feasibility.'],
    focus: 'visual motif',
  },
  render_coordinator: {
    role: 'Render Coordinator',
    department: 'Production',
    mission: 'Keep coverage execution, render feasibility, and delivery timing aligned to studio priorities.',
    authorityBoundaries: ['Render routing', 'queue priority', 'delivery timing'],
    inputs: ['approval gates', 'provider state', 'budget mode'],
    outputs: ['render queue plan', 'risk callouts', 'delivery ETA'],
    collaborationRules: ['Speak to production feasibility, not story taste.', 'Escalate when schedule threatens scene objective.'],
    focus: 'production feasibility',
  },
  continuity_supervisor: {
    role: 'Continuity Supervisor',
    department: 'Continuity',
    mission: 'Track continuity across blocking, wardrobe, geography, and editorial match points.',
    authorityBoundaries: ['Continuity flags', 'match cut checks', 'visual consistency signoff'],
    inputs: ['shot approvals', 'character and location memory', 'dailies'],
    outputs: ['continuity log', 'match warnings', 'reset notes'],
    collaborationRules: ['Do not repeat production design notes unless continuity breaks.', 'Flag specifics only.'],
    focus: 'continuity',
  },
  rights_and_safety_reviewer: {
    role: 'Rights & Safety Reviewer',
    department: 'Clearance',
    mission: 'Protect rights, commercial positioning, and festival viability by clearing creative risks early.',
    authorityBoundaries: ['Rights gate', 'safety gate', 'distribution risk flag'],
    inputs: ['rights board', 'risk register', 'marketing direction'],
    outputs: ['clearance notes', 'festival risks', 'commercial viability flags'],
    collaborationRules: ['Do not duplicate creative notes.', 'Speak only to legal, safety, and market impact.'],
    focus: 'commercial positioning',
  },
}

function asRecord(value: unknown): RecordLike {
  return typeof value === 'object' && value !== null ? (value as RecordLike) : {}
}

function asString(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value : fallback
}

function titleCase(value: string) {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function inferGenre(project: StudioProject | null) {
  const intent = `${project?.title || ''} ${project?.production_bible?.creative_intent || ''}`.toLowerCase()
  if (intent.includes('noir')) return 'Neon noir thriller'
  if (intent.includes('document')) return 'Documentary'
  if (intent.includes('comedy')) return 'Comedy drama'
  return 'Prestige genre drama'
}

export function inferProductionMode(project: StudioProject | null): ProductionMode {
  const intent = `${project?.production_bible?.creative_intent || ''} ${project?.render_provider?.provider_name || ''}`.toLowerCase()
  if (intent.includes('festival') || intent.includes('prestige') || intent.includes('intimate')) return 'prestige'
  if (intent.includes('doc')) return 'documentary'
  if (intent.includes('stream')) return 'streaming'
  if (intent.includes('experimental')) return 'experimental'
  if (intent.includes('demo') || intent.includes('indie') || (project?.source_stats?.shot_count || 0) <= 6) return 'indie'
  return 'commercial'
}

function inferTone(project: StudioProject | null) {
  const intent = project?.production_bible?.creative_intent || ''
  if (intent) return titleCase(intent.split(' with ')[0] || intent)
  return 'Controlled, atmospheric tension'
}

function inferAudience(mode: ProductionMode) {
  switch (mode) {
    case 'commercial': return 'Four-quadrant theatrical audience'
    case 'streaming': return 'Streaming-first binge audience'
    case 'documentary': return 'Issue-driven nonfiction audience'
    case 'experimental': return 'Art-house and gallery audience'
    case 'prestige': return 'Awards-season drama audience'
    default: return 'Indie thriller audience'
  }
}

function inferBudget(project: StudioProject | null, mode: ProductionMode) {
  const shots = project?.source_stats?.shot_count || 0
  if (mode === 'commercial') return 'Upper-mid budget'
  if (mode === 'prestige') return 'Selective premium spend'
  if (mode === 'experimental') return 'Lean concept budget'
  return shots > 12 ? 'Disciplined indie budget' : 'Prototype budget'
}

function inferInfluences(project: StudioProject | null) {
  const intent = `${project?.production_bible?.creative_intent || ''}`.toLowerCase()
  const influences = ['Michael Mann night texture', 'Fincher editorial precision']
  if (intent.includes('noir')) influences.unshift('Wong Kar-wai neon melancholy')
  if (intent.includes('intimate')) influences.push('Barry Jenkins emotional close coverage')
  return influences.slice(0, 3)
}

function inferStageLabel(project: StudioProject | null) {
  const dailies = getDailiesItems(project)
  const renders = getRenderQueueRows(project)
  if (dailies.some((item) => item.selected)) return 'Post-production'
  if (renders.length) return 'Production'
  if (project?.crew_agents?.length) return 'Pre-production'
  if (project?.production_bible) return 'Script'
  return 'Development'
}

export function buildProjectIdentity(project: StudioProject | null, overrideMode?: ProductionMode): ProjectIdentity {
  const mode = overrideMode || inferProductionMode(project)
  const title = project?.title || 'Untitled Film'
  const tone = inferTone(project)
  return {
    title,
    genre: inferGenre(project),
    tone,
    audience: inferAudience(mode),
    influences: inferInfluences(project),
    budgetLevel: inferBudget(project, mode),
    productionMode: mode,
    stage: inferStageLabel(project),
    logline: `${title} is playing as a ${tone.toLowerCase()} piece built around character pressure, spatial tension, and a clear scene objective per sequence.`,
    commercialPositioning: mode === 'prestige' ? 'Awards corridor with premium trailer cut potential' : 'Clear hook for platform packaging and campaign positioning',
    festivalViability: mode === 'experimental' || mode === 'prestige' ? 'Strong festival viability if tone discipline holds through post' : 'Selective festival viability, stronger as a market-facing genre package',
  }
}

function stageStatus(index: number, activeIndex: number, completionBias: number): WorkflowStageCard['status'] {
  if (index < activeIndex) return 'ready'
  if (index === activeIndex) return completionBias > 70 ? 'active' : 'watch'
  return 'pending'
}

export function buildWorkflowStages(project: StudioProject | null, mode: ProductionMode): WorkflowStageCard[] {
  const basePipeline = getPipelineStages(project)
  const stats = getProjectStats(project)
  const activeIndex =
    project?.source_stats?.shot_count
      ? basePipeline.some((stage) => stage.status === 'active')
        ? 3
        : project?.crew_agents?.length
          ? 2
          : 1
      : 0
  const approvals = Array.isArray(project?.shot_approval_gates) ? project.shot_approval_gates.length : 0
  const riskCount = Array.isArray(project?.risk_register) ? project.risk_register.length : 0

  const stageDefinitions = [
    {
      id: 'development',
      label: 'Development',
      assignedAgents: ['director', 'rights_and_safety_reviewer'],
      deliverables: ['Logline lock', 'tone targets', 'commercial positioning brief'],
      note: 'Studio leadership sets genre promise, audience, and slate fit.',
    },
    {
      id: 'script',
      label: 'Script',
      assignedAgents: ['director', 'editor'],
      deliverables: ['Scene objectives', 'character arc map', 'dialogue pass'],
      note: 'Scene intent and emotional payoff are being clarified beat by beat.',
    },
    {
      id: 'pre-production',
      label: 'Pre-production',
      assignedAgents: ['storyboard_artist', 'cinematographer', 'production_designer'],
      deliverables: ['Blocking plans', 'coverage map', 'visual motif bible'],
      note: 'Coverage and blocking are lining up against production feasibility.',
    },
    {
      id: 'production',
      label: 'Production',
      assignedAgents: ['render_coordinator', 'cinematographer', 'continuity_supervisor'],
      deliverables: ['Benchmark take', 'continuity-safe alternates', 'approved dailies'],
      note: 'Benchmark renders are establishing tone, blocking, and usable coverage.',
    },
    {
      id: 'post-production',
      label: 'Post-production',
      assignedAgents: ['editor', 'sound_designer'],
      deliverables: ['Editorial rhythm pass', 'sound bridge plan', 'color route'],
      note: 'Pacing and sonic handoff determine whether the emotional payoff lands.',
    },
    {
      id: 'release',
      label: 'Release',
      assignedAgents: ['rights_and_safety_reviewer', 'director'],
      deliverables: ['Festival strategy', 'campaign hooks', 'distribution posture'],
      note: 'The studio controller is packaging the film for market and festival fit.',
    },
  ]

  return stageDefinitions.map((stage, index) => ({
    ...stage,
    status: stageStatus(index, activeIndex, stats.reviewedShots * 12),
    pendingApprovals: Math.max(0, approvals - index),
    revisionCount: Math.max(0, Math.min(5, riskCount + (mode === 'experimental' ? 2 : 1) - index)),
  }))
}

function tokenize(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((token) => token && !['the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'only'].includes(token))
}

function overlapScore(a: string, b: string) {
  const aTokens = new Set(tokenize(a))
  const bTokens = new Set(tokenize(b))
  const shared = Array.from(aTokens).filter((token) => bTokens.has(token)).length
  const total = new Set([...aTokens, ...bTokens]).size || 1
  return shared / total
}

function buildContribution(agentId: string, project: StudioProject | null, identity: ProjectIdentity, stage: string, index: number): AgentContribution {
  const preview = getRenderQueueRows(project)[0]
  const selectedDailies = getDailiesItems(project).filter((item) => item.selected)
  const focusMap: Record<string, { comment: string; focus: string }> = {
    director: {
      comment: `Keep the tone anchored in ${identity.tone.toLowerCase()} and let the scene objective stay on the benchmark take until the emotional payoff for ${project?.title || 'the film'} feels earned.`,
      focus: 'tone',
    },
    cinematographer: {
      comment: `Tighten blocking around ${preview?.shotId || 'the benchmark setup'} and preserve clean coverage before chasing texture, so the visual motif stays legible without hurting production feasibility.`,
      focus: 'coverage',
    },
    storyboard_artist: {
      comment: `The blocking pass should privilege geography first, then layer alternate coverage so every beat of the character arc reads without confusing screen direction.`,
      focus: 'blocking',
    },
    editor: {
      comment: `Hold the cut a half-beat longer before the reveal; the editorial rhythm wants more breath so the pacing lands instead of rushing the emotional payoff.`,
      focus: 'pacing',
    },
    sound_designer: {
      comment: `Use diegetic room tone under the cut and reserve the non-diegetic lift for the transition, so the scene change carries tension without flattening the pace.`,
      focus: 'sound',
    },
    production_designer: {
      comment: `Push the neon practicals and wet-surface visual motif only where continuity can hold across takes; the set texture should amplify tone, not compete with blocking.`,
      focus: 'visual motif',
    },
    render_coordinator: {
      comment: `Route the benchmark render first and protect turnaround on the hero coverage; production feasibility is strongest when approvals clear before we widen the queue.`,
      focus: 'production feasibility',
    },
    continuity_supervisor: {
      comment: `Track wardrobe, eye-line, and prop continuity through ${selectedDailies.length ? 'the approved dailies' : 'the next review pass'} so the character arc survives the coverage handoff.`,
      focus: 'continuity',
    },
    rights_and_safety_reviewer: {
      comment: `Clear any rights-sensitive motifs now; commercial positioning and festival viability both improve when the clearance lane is settled before post shapes the campaign story.`,
      focus: 'commercial positioning',
    },
  }
  const fallback = {
    comment: `${titleCase(agentId)} is covering ${stage.toLowerCase()} with a note specific to continuity, production feasibility, and emotional clarity.`,
    focus: 'craft',
  }
  const selected = focusMap[agentId] || fallback
  return {
    id: `${agentId}-${index}`,
    department: titleCase(agentId),
    comment: selected.comment,
    focus: selected.focus,
    noveltyScore: Math.max(58, 92 - index * 4),
  }
}

function dedupeContributions(contributions: AgentContribution[]) {
  const kept: AgentContribution[] = []
  const overlap: string[] = []

  for (const contribution of contributions) {
    const previous = kept.find((existing) => overlapScore(existing.comment, contribution.comment) > 0.4)
    if (previous) {
      overlap.push(`${contribution.department} overlapped ${previous.department} on ${previous.focus}; the weaker note was suppressed so each lane stays role-specific.`)
      continue
    }
    kept.push(contribution)
  }

  return { kept, overlap }
}

export function buildAgentProfiles(project: StudioProject | null, mode: ProductionMode) {
  const sourceAgents = Array.isArray(project?.crew_agents) ? project.crew_agents : []
  const pipelineStage = inferStageLabel(project)
  const identity = buildProjectIdentity(project, mode)
  // Agents are live only when crew_agents comes from the backend.
  // When the array is empty, buildAgentProfiles synthesizes profiles from
  // ROLE_SPECS + project metadata — they are template-derived, not live agent output.
  const hasLiveAgents = sourceAgents.length > 0

  const profiles: AgentProfile[] = sourceAgents.map((rawAgent, index) => {
    const agent = asRecord(rawAgent)
    const agentId = asString(agent.agent, `crew_${index}`)
    const spec = ROLE_SPECS[agentId] || {
      role: titleCase(agentId),
      department: titleCase(agentId),
      mission: 'Protect film craft through a clearly scoped discipline lens.',
      authorityBoundaries: ['Scoped creative lane'],
      inputs: ['project direction'],
      outputs: ['discipline-specific note'],
      collaborationRules: ['Avoid duplicating another department.'],
      focus: 'craft',
    }
    const candidateContributions = [
      buildContribution(agentId, project, identity, pipelineStage, index),
      {
        id: `${agentId}-handoff`,
        department: spec.department,
        comment: `Current handoff: ${spec.role} is shaping ${spec.focus} so the ${pipelineStage.toLowerCase()} pass supports ${mode} positioning without repeating another department's note.`,
        focus: spec.focus,
        noveltyScore: 66,
      },
    ]
    const deduped = dedupeContributions(candidateContributions)
    const redundancyPenalty = deduped.overlap.length * 12

    return {
      id: agentId,
      name: titleCase(agentId),
      role: spec.role,
      mission: spec.mission,
      authorityBoundaries: spec.authorityBoundaries,
      inputs: spec.inputs,
      outputs: spec.outputs,
      collaborationRules: spec.collaborationRules,
      currentTask: asString(agent.current_task, asString(agent.status, `Covering ${pipelineStage}`)),
      activityStatus: asString(agent.status, 'active'),
      performanceScore: Math.max(62, 90 - redundancyPenalty + (index % 3)),
      redundancyScore: Math.min(40, redundancyPenalty + index * 2),
      evaluation: {
        usefulness: 84 - index,
        quality: 82 - (index % 4),
        novelty: Math.max(60, 88 - redundancyPenalty),
        alignment: 86 - (index % 5),
        improvement: 74 + (index % 6),
      },
      recentContributions: deduped.kept,
      isDemo: false,
    }
  })

  // If no live agents, return demo profiles derived from ROLE_SPECS.
  // Each profile's isDemo: true signals that contributions are generated
  // from project metadata templates, not from a live agent backend.
  if (!hasLiveAgents) {
    const demoIds = ['director', 'cinematographer', 'editor', 'sound_designer', 'production_designer']
    return demoIds.map((agentId, index) => {
      const spec = ROLE_SPECS[agentId] || {
        role: titleCase(agentId),
        department: titleCase(agentId),
        mission: 'Protect film craft through a clearly scoped discipline lens.',
        authorityBoundaries: ['Scoped creative lane'],
        inputs: ['project direction'],
        outputs: ['discipline-specific note'],
        collaborationRules: ['Avoid duplicating another department.'],
        focus: 'craft',
      }
      const candidateContributions = [
        buildContribution(agentId, project, identity, pipelineStage, index),
        {
          id: `${agentId}-handoff`,
          department: spec.department,
          comment: `Current handoff: ${spec.role} is shaping ${spec.focus} so the ${pipelineStage.toLowerCase()} pass supports ${mode} positioning without repeating another department's note.`,
          focus: spec.focus,
          noveltyScore: 66,
        },
      ]
      const deduped = dedupeContributions(candidateContributions)
      return {
        id: agentId,
        name: titleCase(agentId),
        role: spec.role,
        mission: spec.mission,
        authorityBoundaries: spec.authorityBoundaries,
        inputs: spec.inputs,
        outputs: spec.outputs,
        collaborationRules: spec.collaborationRules,
        currentTask: `Covering ${pipelineStage}`,
        activityStatus: 'active',
        performanceScore: Math.max(62, 90 - index * 2),
        redundancyScore: 0,
        evaluation: {
          usefulness: 80,
          quality: 78,
          novelty: 72,
          alignment: 82,
          improvement: 74,
        },
        recentContributions: deduped.kept,
        isDemo: true,
      }
    })
  }

  return profiles
}

export function buildCrewThreads(agents: AgentProfile[]): CrewThread[] {
  const comments = agents.flatMap((agent) => agent.recentContributions.map((contribution) => ({
    ...contribution,
    department: agent.role,
  })))

  const toneComments = comments.filter((comment) => ['tone', 'coverage', 'blocking'].includes(comment.focus))
  const postComments = comments.filter((comment) => ['pacing', 'sound', 'continuity'].includes(comment.focus))
  const marketComments = comments.filter((comment) => ['commercial positioning', 'production feasibility', 'visual motif'].includes(comment.focus))

  const toneDeduped = dedupeContributions(toneComments)
  const postDeduped = dedupeContributions(postComments)
  const marketDeduped = dedupeContributions(marketComments)

  return [
    {
      id: 'tone-thread',
      title: 'Tone, Blocking, and Coverage',
      objective: 'Keep scene objective, blocking clarity, and visual motif aligned before approvals lock.',
      status: toneDeduped.overlap.length ? 'needs-escalation' : 'aligned',
      participants: toneDeduped.kept.map((comment) => comment.department),
      comments: toneDeduped.kept,
      escalation: 'Director settles tone if blocking and coverage start describing the same problem.',
      overlapSummary: toneDeduped.overlap[0],
    },
    {
      id: 'post-thread',
      title: 'Editorial Rhythm and Sound',
      objective: 'Protect pacing, diegetic texture, and continuity through the handoff into post.',
      status: postDeduped.overlap.length ? 'needs-escalation' : 'aligned',
      participants: postDeduped.kept.map((comment) => comment.department),
      comments: postDeduped.kept,
      escalation: 'Editor resolves any overlap between pacing notes and sound bridge notes.',
      overlapSummary: postDeduped.overlap[0],
    },
    {
      id: 'market-thread',
      title: 'Production Feasibility and Release Posture',
      objective: 'Balance schedule, rights, and commercial positioning so the film can ship cleanly.',
      status: marketDeduped.overlap.length ? 'needs-escalation' : 'aligned',
      participants: marketDeduped.kept.map((comment) => comment.department),
      comments: marketDeduped.kept,
      escalation: 'Studio controller resolves if feasibility and market notes drift into the same lane.',
      overlapSummary: marketDeduped.overlap[0],
    },
  ]
}

export function buildMemoryEntries(project: StudioProject | null, identity: ProjectIdentity, lockedDecisions: string[], leadershipNotes: string[]): MemoryEntry[] {
  const rightsBoard = asRecord(project?.rights_safety_clearance_board)
  const knownCharacters = Array.isArray(asRecord(project?.production_bible).known_characters)
    ? (asRecord(project?.production_bible).known_characters as unknown[]).map((value) => String(value))
    : []
  const knownLocations = Array.isArray(asRecord(project?.production_bible).known_locations)
    ? (asRecord(project?.production_bible).known_locations as unknown[]).map((value) => String(value))
    : []

  return [
    {
      id: 'project-memory',
      type: 'project',
      label: 'Project Memory',
      detail: `Tone lock: ${identity.tone}. Mode: ${identity.productionMode}. Locked decisions: ${lockedDecisions.length || 0}.`,
    },
    {
      id: 'character-memory',
      type: 'character',
      label: 'Character Memory',
      detail: knownCharacters.length ? `${knownCharacters.join(', ')} are being tracked for continuity and character arc drift.` : 'Character arc tracking starts once named characters are locked.',
    },
    {
      id: 'scene-memory',
      type: 'scene',
      label: 'Scene Memory',
      detail: knownLocations.length ? `${knownLocations.join(' / ')} define the current scene objective geography.` : 'Scene geography will populate after the breakdown pass.',
    },
    {
      id: 'visual-memory',
      type: 'visual',
      label: 'Visual Memory',
      detail: `Visual motif anchors on ${identity.influences.join(', ')} with continuity checks on blocking and lighting.`,
    },
    {
      id: 'taste-memory',
      type: 'taste',
      label: 'User Taste Profile',
      detail: `The studio keeps favoring ${identity.tone.toLowerCase()}, legible coverage, and emotionally precise pacing.`,
    },
    {
      id: 'lesson-memory',
      type: 'lesson',
      label: 'Distilled Lessons',
      detail: leadershipNotes[0] || asString(rightsBoard.status, 'Clear role lanes early so notes stay novel and production-feasible.'),
    },
  ]
}

export function buildReflections(project: StudioProject | null, threads: CrewThread[]): ReflectionCard[] {
  const firstRisk = Array.isArray(project?.risk_register) ? project.risk_register[0] : 'No major regression is active.'
  return threads.map((thread, index) => ({
    id: thread.id,
    title: `${thread.title} Reflection`,
    worked: `The ${thread.participants[0] || 'lead'} lane stayed specific to ${thread.objective.toLowerCase()}.`,
    failed: firstRisk || 'No failure registered.',
    redundant: thread.overlapSummary || 'No duplicate commentary survived the suppression pass.',
    change: index === 0 ? 'Tighten role boundaries before the next approval gate.' : 'Push cleaner handoffs so each department owns a distinct craft problem.',
    improvement: 'Novelty stayed ahead of redundancy, so the next pass should move faster through approvals.',
  }))
}

export function buildOrchestration(project: StudioProject | null, workflow: WorkflowStageCard[], threads: CrewThread[], identity: ProjectIdentity): OrchestrationSnapshot {
  const producer = asRecord(project?.producer_dashboard)
  const approvalQueue = Array.isArray(producer.approval_queue) ? producer.approval_queue : []
  const blockers = Array.isArray(producer.blockers) ? producer.blockers.map((value) => String(value)) : []
  const priorityFocus = Array.isArray(producer.priority_focus) ? producer.priority_focus.map((value) => String(value)) : []

  return {
    controllerStatus: `${identity.stage} is live. The studio controller is pacing the film as a ${identity.productionMode} package.`,
    activeAgents: approvalQueue.slice(0, 4).map((entry) => titleCase(asString(asRecord(entry).agent, 'studio controller'))),
    bottlenecks: blockers.length ? blockers : threads.filter((thread) => thread.status === 'needs-escalation').map((thread) => thread.title),
    nextBestActions: priorityFocus.length ? priorityFocus : workflow.slice(0, 3).map((stage) => `Advance ${stage.label.toLowerCase()} by clearing ${stage.pendingApprovals} approval gate(s).`),
    approvalGates: (Array.isArray(project?.shot_approval_gates) ? project.shot_approval_gates : []).slice(0, 4).map((gate) => {
      const raw = asRecord(gate)
      return `${asString(raw.shot_id, 'Shot')} → ${asString(raw.next_gate, 'pending gate')}`
    }),
    branchingOptions: [
      'Branch a more commercial trailer-cut emphasis.',
      'Branch a prestige pacing pass with longer dramatic holds.',
      'Branch an alternate visual motif package for festival positioning.',
    ],
  }
}

export function buildSlateCards(overview: StudioOverview | null, variants: SlateVariant[], archivedProjectIds: string[]) {
  const archived = new Set(archivedProjectIds)
  const baseCards: SlateProjectCard[] = (overview?.projects || []).map((project) => {
    const projectLike = {
      project_id: project.project_id,
      title: project.title,
      source_stats: {
        scene_count: project.scene_count,
        shot_count: project.shot_count,
      },
    } as StudioProject
    const mode = inferProductionMode(projectLike)
    return {
      id: project.project_id,
      sourceProjectId: project.project_id,
      title: project.title || 'Untitled Film',
      stage: project.scene_count && project.scene_count > 1 ? 'Pre-production' : 'Development',
      genre: inferGenre(projectLike),
      tone: inferTone(projectLike),
      mode,
      status: archived.has(project.project_id) ? 'Archived locally' : 'Active in slate',
      tagLine: `${project.scene_count || 0} scenes, ${project.shot_count || 0} shots, and a live studio path to production.`,
      quickFacts: [
        `${project.scene_count || 0} scenes`,
        `${project.shot_count || 0} shots`,
        `${mode} mode`,
      ],
      archived: archived.has(project.project_id),
      kind: 'project',
    }
  })

  const variantCards: SlateProjectCard[] = variants.map((variant) => ({
    id: variant.id,
    sourceProjectId: variant.sourceProjectId,
    title: variant.title,
    stage: variant.stage,
    genre: 'Alternate creative direction',
    tone: variant.kind === 'branch' ? 'Contrastive take exploration' : 'Operational duplicate for revisions',
    mode: variant.mode,
    status: variant.archived ? 'Archived locally' : 'Variant ready',
    tagLine: variant.notes,
    quickFacts: [
      titleCase(variant.kind),
      variant.mode,
      new Date(variant.createdAt).toLocaleDateString(),
    ],
    archived: variant.archived,
    kind: variant.kind,
    variantId: variant.id,
  }))

  return [...variantCards, ...baseCards]
}

export function buildStudioDashboard(overview: StudioOverview | null, activeProject: StudioProject | null, identity: ProjectIdentity, agents: AgentProfile[], orchestration: OrchestrationSnapshot) {
  const stats = getProjectStats(activeProject)
  const providers = getProviderSummaries(activeProject)
  return {
    headline: `${identity.title} is moving through ${identity.stage.toLowerCase()} with ${identity.productionMode} priorities.`,
    activeProjects: overview?.projects?.length || 0,
    shotsReviewed: stats.reviewedShots,
    agentTasks: stats.runningTasks,
    pendingApprovals: stats.pendingApprovals,
    activityFeed: agents.slice(0, 5).map((agent) => ({
      role: agent.role,
      beat: `${agent.role} is focused on ${agent.recentContributions[0]?.focus || 'craft'} and ${agent.currentTask.toLowerCase()}.`,
    })),
    bottlenecks: orchestration.bottlenecks,
    upcomingDecisions: orchestration.nextBestActions,
    providerPressure: providers.map((provider) => `${provider.name} is carrying ${provider.jobs} queue item(s) at ${provider.load}% load.`),
  }
}

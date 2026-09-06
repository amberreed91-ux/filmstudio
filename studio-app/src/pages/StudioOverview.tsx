import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import StudioShell, { AGENTS, CollapsibleSection, EmptyStateCard, MetricCard, TabGroup } from '../components/StudioShell'
import StudioBrainExecutivePanel from '../components/StudioBrainExecutivePanel'
import StudioBrainOrchestrationPanel from '../components/StudioBrainOrchestrationPanel'
import { useStudio } from '../context/StudioContext'
import {
  buildLocalFallbackExport,
  createProject,
  downloadJson,
  fetchExportPackage,
  generateScenes,
  listProjects,
  retrieveReferenceMemory,
} from '../lib/studioApi'
import { withProjectQuery } from '../lib/projectContext'

const FALLBACK_AGENTS = {
  director: { name: 'Director', icon: '🎬' },
  cinematographer: { name: 'Cinematographer', icon: '🎥' },
  editor: { name: 'Editor', icon: '✂️' },
  archivist: { name: 'Memory Archivist', icon: '🧠' },
}

const STUDIO_AGENTS = AGENTS || FALLBACK_AGENTS
const DIRECTOR_AGENT = STUDIO_AGENTS.director || FALLBACK_AGENTS.director
const CINEMATOGRAPHER_AGENT = STUDIO_AGENTS.cinematographer || FALLBACK_AGENTS.cinematographer
const EDITOR_AGENT = STUDIO_AGENTS.editor || FALLBACK_AGENTS.editor
const ARCHIVIST_AGENT = STUDIO_AGENTS.archivist || FALLBACK_AGENTS.archivist

const RECENT_ACTIVITY = [
  `${DIRECTOR_AGENT.icon} ${DIRECTOR_AGENT.name} approved Scene 12`,
  `${CINEMATOGRAPHER_AGENT.icon} ${CINEMATOGRAPHER_AGENT.name} refined Scene 10 lighting`,
  `${EDITOR_AGENT.icon} ${EDITOR_AGENT.name} flagged pacing dip`,
  `${ARCHIVIST_AGENT.icon} ${ARCHIVIST_AGENT.name} applied reference pattern`,
]

type AnyRecord = Record<string, unknown>

function asRecord(value: unknown): AnyRecord {
  return value && typeof value === 'object' ? (value as AnyRecord) : {}
}

function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value))
}

export default function StudioOverview() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { overview, project, loadProject } = useStudio()
  const queryProjectId = (searchParams.get('project_id') || '').trim()
  const activeProjectId = queryProjectId || project?.project_id || overview?.latest_project?.project_id || ''
  const requestedProjectLoadRef = useRef('')
  const [exportMessage, setExportMessage] = useState('')
  const [projectSaveMessage, setProjectSaveMessage] = useState('')
  const [overviewTab, setOverviewTab] = useState<'activity' | 'issues' | 'rooms' | 'memory'>('activity')
  const [persistedProjects, setPersistedProjects] = useState<Array<{ project_id: string; title: string }>>([])
  const [studioIntelligence, setStudioIntelligence] = useState<{
    visual: Array<Record<string, unknown>>
    pacing: Array<Record<string, unknown>>
    motif: Array<Record<string, unknown>>
    tone: Array<Record<string, unknown>>
    studio_intelligence_score: number
    total_references: number
    committed_references: number
  }>({
    visual: [],
    pacing: [],
    motif: [],
    tone: [],
    studio_intelligence_score: 0,
    total_references: 0,
    committed_references: 0,
  })
  const projectOptions = useMemo(() => (overview?.projects || []).filter((p) => typeof p.project_id === 'string' && p.project_id), [overview?.projects])
  const mergedProjectOptions = useMemo(() => {
    const fromOverview = projectOptions.map((p) => ({ project_id: p.project_id, title: p.title || p.project_id }))
    const map = new Map<string, { project_id: string; title: string }>()
    for (const row of [...persistedProjects, ...fromOverview]) {
      if (!row.project_id) continue
      map.set(row.project_id, row)
    }
    return Array.from(map.values())
  }, [persistedProjects, projectOptions])
  const hasScript = localStorage.getItem('studio_script_exists') === '1'
  const hasScenes = localStorage.getItem('studio_scenes_generated') === '1'
  const hasApproved = localStorage.getItem('studio_approved_scenes') === '1'
  const nextDirective = !hasScript
    ? "Start in Writer's Room"
    : !hasScenes
      ? 'Generate Scenes'
      : !hasApproved
        ? 'Review Scenes'
        : 'Watch Cut'
  const nextDirectiveBaseLink = !hasScript ? '/studio/writers-room' : !hasScenes ? '/studio/writers-room' : !hasApproved ? '/studio/previs' : '/studio/screening-room'
  const nextDirectiveLink = withProjectQuery(nextDirectiveBaseLink, activeProjectId)
  const creativeTension = useMemo(() => {
    try {
      const raw = localStorage.getItem('studio:lastBundle')
      if (!raw) return { score: 0, total_conflicts: 0, high_conflicts: 0 }
      const parsed = JSON.parse(raw) as Record<string, unknown>
      const scoreBlock = (parsed.creative_tension_score || {}) as Record<string, unknown>
      return {
        score: typeof scoreBlock.score === 'number' ? scoreBlock.score : 0,
        total_conflicts: typeof scoreBlock.total_conflicts === 'number' ? scoreBlock.total_conflicts : 0,
        high_conflicts: typeof scoreBlock.high_conflicts === 'number' ? scoreBlock.high_conflicts : 0,
      }
    } catch {
      return { score: 0, total_conflicts: 0, high_conflicts: 0 }
    }
  }, [])
  const executionSummary = useMemo(() => {
    const fromProject = asRecord(project?.execution_summary)
    if (Object.keys(fromProject).length > 0) return fromProject
    try {
      const localRaw = localStorage.getItem('studio:lastBundle')
      return localRaw ? asRecord(JSON.parse(localRaw)) : {}
    } catch {
      return {}
    }
  }, [project?.execution_summary])
  const scenes = useMemo(() => asArray<AnyRecord>(executionSummary.scenes), [executionSummary.scenes])
  const filmStructure = useMemo(() => asRecord(executionSummary.film_structure), [executionSummary.film_structure])
  const filmProgress = useMemo(() => asRecord(executionSummary.film_progress), [executionSummary.film_progress])
  const productionSummary = useMemo(() => asRecord(executionSummary.production_summary), [executionSummary.production_summary])
  const screeningSummary = useMemo(() => asRecord(executionSummary.screening_summary), [executionSummary.screening_summary])
  const archiveSummary = useMemo(() => asRecord(executionSummary.archive_summary), [executionSummary.archive_summary])
  const renderAssetSummary = useMemo(() => asRecord(executionSummary.render_asset_summary), [executionSummary.render_asset_summary])
  const cutAnalysis = useMemo(() => asRecord(executionSummary.cut_analysis), [executionSummary.cut_analysis])
  const sequenceFlow = useMemo(() => asRecord(executionSummary.sequence_flow), [executionSummary.sequence_flow])
  const endingImpact = useMemo(() => asRecord(executionSummary.ending_impact), [executionSummary.ending_impact])
  const filmValidation = useMemo(() => asRecord(executionSummary.film_validation), [executionSummary.film_validation])
  const continuityReport = useMemo(() => asRecord(executionSummary.scene_continuity_report), [executionSummary.scene_continuity_report])
  const progressionReport = useMemo(() => asRecord(executionSummary.narrative_progression_score), [executionSummary.narrative_progression_score])
  const archiveSnapshots = useMemo(() => asArray<AnyRecord>(executionSummary.archive_snapshots), [executionSummary.archive_snapshots])
  const sceneIterations = useMemo(() => asArray<AnyRecord>(executionSummary.scene_iterations), [executionSummary.scene_iterations])
  const directorReferenceMemory = useMemo(() => asRecord(executionSummary.director_reference_memory), [executionSummary.director_reference_memory])
  const approvedScenesCount = useMemo(() => {
    try {
      const raw = JSON.parse(localStorage.getItem('studio:approvedScenes') || '[]')
      return Array.isArray(raw) ? raw.length : 0
    } catch {
      return 0
    }
  }, [])
  const studiedReferenceCount = useMemo(() => {
    const datasets = asArray<AnyRecord>(directorReferenceMemory.datasets)
    return datasets.filter((row) => Boolean(row.studied)).length
  }, [directorReferenceMemory.datasets])
  const openIssues = useMemo(() => {
    const issues: string[] = []
    issues.push(...asArray<string>(cutAnalysis.weak_moments).map((row) => `Cut: ${row}`))
    issues.push(...asArray<string>(filmValidation.issues).map((row) => `Film: ${row}`))
    issues.push(...asArray<string>(sequenceFlow.issues).map((row) => `Flow: ${row}`))
    const blocked = asNumber(productionSummary.blocked_scenes) ?? 0
    if (blocked > 0) issues.push(`Production: ${blocked} blocked scene${blocked === 1 ? '' : 's'}`)
    return issues.slice(0, 6)
  }, [cutAnalysis.weak_moments, filmValidation.issues, sequenceFlow.issues, productionSummary.blocked_scenes])
  const healthCards = useMemo(() => {
    const storyScore = clampPercent((asNumber(progressionReport.progression_score) ?? 0.6) * 100)
    const continuityScore = clampPercent((asNumber(continuityReport.continuity_score) ?? 0.6) * 100)
    const flowScore = clampPercent((asNumber(sequenceFlow.flow_score) ?? 0.65) * 100)
    const endingScore = clampPercent((asNumber(endingImpact.impact_score) ?? 0.65) * 100)
    const cinematicScore = clampPercent((flowScore + endingScore) / 2)
    const totalScenes = asNumber(productionSummary.total_scenes) ?? scenes.length
    const lockedScenes = asNumber(productionSummary.locked_scenes) ?? approvedScenesCount
    const productionScore = totalScenes > 0 ? clampPercent((lockedScenes / totalScenes) * 100) : 0
    const statusFor = (score: number) => (score >= 80 ? 'Strong' : score >= 60 ? 'Watch' : 'Needs Focus')
    return [
      { label: 'Story Health', score: Math.round(storyScore), status: statusFor(storyScore), accent: 'text-emerald-300', bar: 'from-emerald-400 to-emerald-200' },
      { label: 'Continuity Health', score: Math.round(continuityScore), status: statusFor(continuityScore), accent: 'text-amber-300', bar: 'from-amber-400 to-amber-200' },
      { label: 'Cinematic Health', score: Math.round(cinematicScore), status: statusFor(cinematicScore), accent: 'text-cyan-300', bar: 'from-cyan-400 to-cyan-200' },
      { label: 'Production Status', score: Math.round(productionScore), status: totalScenes > 0 ? statusFor(productionScore) : 'No Data', accent: 'text-indigo-300', bar: 'from-indigo-400 to-indigo-200' },
    ]
  }, [progressionReport.progression_score, continuityReport.continuity_score, sequenceFlow.flow_score, endingImpact.impact_score, productionSummary.total_scenes, productionSummary.locked_scenes, scenes.length, approvedScenesCount])
  const roomPreviews = useMemo(() => {
    const totalScenes = asNumber(filmStructure.total_scenes) ?? scenes.length
    const renderCount = asNumber(renderAssetSummary.total_assets) ?? asArray(executionSummary.image_render_assets).length
    const blocked = asNumber(productionSummary.blocked_scenes) ?? 0
    const locked = asNumber(productionSummary.locked_scenes) ?? approvedScenesCount
    const playable = asNumber(screeningSummary.playable_scene_count) ?? approvedScenesCount
    const snapshots = asNumber(archiveSummary.total_snapshots) ?? archiveSnapshots.length
    return [
      { title: 'Development Room', status: totalScenes > 0 ? 'Story map active' : 'No project loaded', to: withProjectQuery('/studio/lobby', activeProjectId), preview: totalScenes > 0 ? `${totalScenes} scene${totalScenes === 1 ? '' : 's'}` : 'Generate scenes to populate this panel' },
      { title: "Writer's Room", status: hasScript ? 'Script loaded' : 'No script loaded', to: withProjectQuery('/studio/writers-room', activeProjectId), preview: hasScript ? 'Ready for scene generation' : 'Load a script to begin' },
      { title: 'Previs Room', status: totalScenes > 0 ? 'Scene board available' : 'No scenes generated', to: withProjectQuery('/studio/previs', activeProjectId), preview: totalScenes > 0 ? `${totalScenes} scenes • ${renderCount} render assets` : 'Generate scenes to populate this panel' },
      { title: 'Production Board', status: totalScenes > 0 ? 'Tracking review state' : 'No production data', to: withProjectQuery('/studio/production-board', activeProjectId), preview: totalScenes > 0 ? `locked ${locked} • blocked ${blocked}` : 'Generate scenes to populate this panel' },
      { title: 'Screening Room', status: playable > 0 ? 'Cut playable' : 'No cut available yet', to: withProjectQuery('/studio/screening-room', activeProjectId), preview: playable > 0 ? `${playable} playable scene${playable === 1 ? '' : 's'}` : 'Approve scenes in Previs first' },
      { title: 'Archive', status: snapshots > 0 ? 'Snapshots available' : 'No archive snapshots yet', to: withProjectQuery('/studio/archive', activeProjectId), preview: snapshots > 0 ? `${snapshots} snapshot${snapshots === 1 ? '' : 's'}` : 'No archive snapshots yet' },
      { title: 'Study Room', status: studiedReferenceCount > 0 ? 'Reference memory active' : 'No studied datasets', to: withProjectQuery('/studio/study-room', activeProjectId), preview: studiedReferenceCount > 0 ? `${studiedReferenceCount} studied dataset${studiedReferenceCount === 1 ? '' : 's'}` : 'Study references to train style memory' },
    ]
  }, [activeProjectId, filmStructure.total_scenes, scenes.length, renderAssetSummary.total_assets, executionSummary.image_render_assets, productionSummary.blocked_scenes, productionSummary.locked_scenes, screeningSummary.playable_scene_count, archiveSummary.total_snapshots, archiveSnapshots.length, hasScript, approvedScenesCount, studiedReferenceCount])
  const dominantStyleSummary = useMemo(() => {
    const topVisual = (studioIntelligence.visual || [])[0]
    const topPacing = (studioIntelligence.pacing || [])[0]
    const topMotif = (studioIntelligence.motif || [])[0]
    const visualText = topVisual && typeof topVisual.pattern === 'string' ? topVisual.pattern : 'static framing'
    const pacingText = topPacing && typeof topPacing.pattern === 'string' ? topPacing.pattern : 'slow pacing'
    const motifText = topMotif && typeof topMotif.pattern === 'string' ? topMotif.pattern : 'delayed reveals'
    return `Your studio favors ${pacingText}, ${visualText}, and ${motifText}.`
  }, [studioIntelligence.visual, studioIntelligence.pacing, studioIntelligence.motif])
  const recentActivity = useMemo(() => {
    try {
      const raw = localStorage.getItem('studio:agentActivity')
      const parsed = raw ? JSON.parse(raw) : []
      if (!Array.isArray(parsed) || parsed.length === 0) return RECENT_ACTIVITY
      return parsed
        .map((entry) => String((entry as Record<string, unknown>)?.message || '').trim())
        .filter(Boolean)
        .slice(0, 4)
    } catch {
      return RECENT_ACTIVITY
    }
  }, [])
  const derivedRecentActivity = useMemo(() => {
    const logs: string[] = []
    if (archiveSnapshots.length > 0) logs.push(`${STUDIO_AGENTS.archivist.icon} ${STUDIO_AGENTS.archivist.name} captured ${archiveSnapshots.length} archive snapshot${archiveSnapshots.length === 1 ? '' : 's'}`)
    if (sceneIterations.length > 0) logs.push(`${STUDIO_AGENTS.editor.icon} ${STUDIO_AGENTS.editor.name} tracked ${sceneIterations.length} scene iteration${sceneIterations.length === 1 ? '' : 's'}`)
    if (approvedScenesCount > 0) logs.push(`${STUDIO_AGENTS.director.icon} ${STUDIO_AGENTS.director.name} approved ${approvedScenesCount} scene${approvedScenesCount === 1 ? '' : 's'}`)
    const successfulRenders = asNumber(renderAssetSummary.successful_assets) ?? 0
    if (successfulRenders > 0) logs.push(`${STUDIO_AGENTS.cinematographer.icon} ${STUDIO_AGENTS.cinematographer.name} delivered ${successfulRenders} render asset${successfulRenders === 1 ? '' : 's'}`)
    if (studiedReferenceCount > 0) logs.push(`${STUDIO_AGENTS.archivist.icon} ${STUDIO_AGENTS.archivist.name} studied ${studiedReferenceCount} director dataset${studiedReferenceCount === 1 ? '' : 's'}`)
    return logs.length > 0 ? logs : recentActivity
  }, [archiveSnapshots.length, sceneIterations.length, approvedScenesCount, renderAssetSummary.successful_assets, studiedReferenceCount, recentActivity])
  const renderQaSnapshot = useMemo(() => {
    try {
      const raw = localStorage.getItem('studio:lastBundle')
      if (!raw) return { avg: 0, highRisk: 0 }
      const parsed = JSON.parse(raw) as Record<string, unknown>
      const scenes = Array.isArray(parsed.scenes) ? parsed.scenes : []
      let sum = 0
      let count = 0
      let highRisk = 0
      for (const scene of scenes) {
        if (!scene || typeof scene !== 'object') continue
        const faithfulness = (scene as Record<string, unknown>).script_faithfulness as Record<string, unknown> | undefined
        const score = typeof faithfulness?.score === 'number' ? faithfulness.score : null
        if (typeof score === 'number') {
          sum += score
          count += 1
        }
        if (String(faithfulness?.risk || '').toLowerCase() === 'high') highRisk += 1
      }
      return { avg: count > 0 ? sum / count : 0, highRisk }
    } catch {
      return { avg: 0, highRisk: 0 }
    }
  }, [])

  useEffect(() => {
    void (async () => {
      const response = await listProjects()
      setPersistedProjects((response.projects || []).map((p) => ({ project_id: p.project_id, title: p.title || p.project_id })))
    })()
  }, [])

  useEffect(() => {
    if (!queryProjectId) {
      requestedProjectLoadRef.current = ''
      return
    }
    if (project?.project_id === queryProjectId) {
      requestedProjectLoadRef.current = ''
      return
    }
    if (requestedProjectLoadRef.current === queryProjectId) return
    requestedProjectLoadRef.current = queryProjectId
    void loadProject(queryProjectId).catch(() => {
      requestedProjectLoadRef.current = ''
    })
  }, [loadProject, project?.project_id, queryProjectId])

  useEffect(() => {
    let cancelled = false
    async function hydrateStudioIntelligence() {
      if (!activeProjectId) return
      try {
        const payload = await retrieveReferenceMemory(activeProjectId, { scope: 'studio-overview' })
        if (cancelled) return
        const block = payload.studio_intelligence as Record<string, unknown> | undefined
        const refs = Array.isArray(payload.references) ? payload.references : []
        const committedRefs = refs.filter((entry) => {
          const status = String((entry as Record<string, unknown>).status || 'staged').toLowerCase()
          return status === 'committed' || status === 'used'
        })
        setStudioIntelligence({
          visual: Array.isArray(block?.visual) ? (block?.visual as Array<Record<string, unknown>>) : [],
          pacing: Array.isArray(block?.pacing) ? (block?.pacing as Array<Record<string, unknown>>) : [],
          motif: Array.isArray(block?.motif) ? (block?.motif as Array<Record<string, unknown>>) : [],
          tone: Array.isArray(block?.tone) ? (block?.tone as Array<Record<string, unknown>>) : [],
          studio_intelligence_score:
            typeof block?.studio_intelligence_score === 'number' ? block.studio_intelligence_score : 0,
          total_references: refs.length,
          committed_references: committedRefs.length,
        })
      } catch {
        if (!cancelled) {
          setStudioIntelligence({ visual: [], pacing: [], motif: [], tone: [], studio_intelligence_score: 0, total_references: 0, committed_references: 0 })
        }
      }
    }
    void hydrateStudioIntelligence()
    return () => {
      cancelled = true
    }
  }, [activeProjectId])

  function renderPatternRows(label: string, rows: Array<Record<string, unknown>>) {
    const sortedRows = [...rows].sort(
      (a, b) => Number(b.confidence || 0) - Number(a.confidence || 0),
    )
    return (
      <div className="rounded-lg border border-white/10 bg-black/35 p-3">
        <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-300">{label}</div>
        <div className="mt-2 space-y-2">
          {sortedRows.length === 0 ? (
            <div className="text-[11px] text-zinc-500">No patterns yet</div>
          ) : (
            sortedRows.slice(0, 3).map((row, index) => (
              <div key={`${label}-${index}`} className="rounded border border-white/10 bg-zinc-900/60 p-2 text-[11px]">
                <div className="text-zinc-100">{String(row.pattern || 'unknown')}</div>
                <div className="text-cyan-200">confidence: {Number(row.confidence || 0).toFixed(2)}</div>
                <div className="text-zinc-400">source: {String(row.source_reference || 'unknown')}</div>
              </div>
            ))
          )}
        </div>
      </div>
    )
  }
  return (
    <StudioShell title="Studio Overview" subtitle="Your film at a glance. What's working. What needs attention.">
      <div className="relative isolate min-h-screen w-full overflow-hidden" style={{ background: 'var(--color-surface-0)' }}>
        {/* Film grain overlay */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.03]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
          }}
        />

        <div className="relative z-10 mx-auto w-full max-w-7xl px-4 py-8 text-zinc-100 sm:px-6 lg:px-8">
          <div className="space-y-8">
          {/* Hero Section - "The Gate" */}
          <section className="relative overflow-hidden rounded-2xl border p-12" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border)' }}>
            <div className="text-[11px] uppercase tracking-[0.2em]" style={{ color: 'var(--color-accent)' }}>The Gate</div>
            <h1 className="mt-4 text-5xl font-light tracking-tight" style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}>
              Direct. Shape. Remember.
            </h1>
          </section>

          {/* Stats Row */}
          <section className="grid grid-cols-4 gap-4">
            <div className="rounded-lg border p-4" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
              <div className="text-2xl font-light" style={{ color: 'var(--color-text-primary)' }}>{mergedProjectOptions.length}</div>
              <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>Projects</div>
            </div>
            <div className="rounded-lg border p-4" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
              <div className="text-2xl font-light" style={{ color: 'var(--color-text-primary)' }}>{asNumber(renderAssetSummary.total_assets) ?? 0}</div>
              <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>Rendering</div>
            </div>
            <div className="rounded-lg border p-4" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
              <div className="text-2xl font-light" style={{ color: 'var(--color-text-primary)' }}>{approvedScenesCount}</div>
              <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>Approved</div>
            </div>
            <div className="rounded-lg border p-4" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
              <div className="text-2xl font-light" style={{ color: 'var(--color-text-primary)' }}>{scenes.length - approvedScenesCount}</div>
              <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>Drafts</div>
            </div>
          </section>

          {/* Film Cards Grid */}
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {roomPreviews.slice(0, 6).map((room) => (
              <Link
                key={room.title}
                to={room.to}
                className="group relative overflow-hidden rounded-lg border p-5 transition-all hover:border-[#00d4aa]"
                style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}
              >
                <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>{room.title}</div>
                <div className="mt-2 text-sm" style={{ color: 'var(--color-text-primary)' }}>{room.status}</div>
                <div className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>{room.preview}</div>
                <div className="mt-3 h-1 w-full rounded-full" style={{ background: 'var(--color-surface-2)' }}>
                  <div className="h-full w-1/2 rounded-full" style={{ background: 'var(--color-accent)' }} />
                </div>
              </Link>
            ))}
          </section>

          {/* AI Crew Presence Panel */}
          <section className="rounded-lg border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
            <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>AI Crew Presence</div>
            <div className="mt-4 space-y-3">
              <div className="flex items-center gap-3">
                <span className="w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
                <span className="text-sm" style={{ color: 'var(--color-text-primary)' }}>{DIRECTOR_AGENT.name}</span>
                <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Active</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
                <span className="text-sm" style={{ color: 'var(--color-text-primary)' }}>{CINEMATOGRAPHER_AGENT.name}</span>
                <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Active</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
                <span className="text-sm" style={{ color: 'var(--color-text-primary)' }}>{EDITOR_AGENT.name}</span>
                <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Active</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
                <span className="text-sm" style={{ color: 'var(--color-text-primary)' }}>{ARCHIVIST_AGENT.name}</span>
                <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Active</span>
              </div>
            </div>
          </section>

          {/* Project Controls */}
          <section className="rounded-lg border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
            <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>Current Project</div>
            <button
              type="button"
              className="mt-3 w-full rounded-lg border px-4 py-2 text-left text-sm transition hover:border-[#00d4aa]"
              style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border)', color: 'var(--color-text-primary)' }}
            >
              {project?.title || 'No project loaded'}
            </button>
            {mergedProjectOptions.length > 0 ? (
              <select
                value={activeProjectId}
                onChange={(event) => {
                  if (event.target.value) {
                    localStorage.setItem('studio:activeProjectId', event.target.value)
                    navigate(`/studio/overview?project_id=${encodeURIComponent(event.target.value)}`, { replace: true })
                    void loadProject(event.target.value)
                  }
                }}
                className="mt-2 w-full rounded-lg border px-4 py-2 text-sm outline-none transition focus:border-[#00d4aa]"
                style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border)', color: 'var(--color-text-primary)' }}
              >
                {mergedProjectOptions.map((option) => (
                  <option key={option.project_id} value={option.project_id}>
                    {option.title || option.project_id}
                  </option>
                ))}
              </select>
            ) : null}
            <button
              type="button"
              onClick={async () => {
                const created = await createProject({ title: `Studio Project ${new Date().toLocaleDateString()}` })
                if (!created.project?.project_id) return
                localStorage.setItem('studio:activeProjectId', created.project.project_id)
                setProjectSaveMessage('Project created')
                await loadProject(created.project.project_id)
                const response = await listProjects()
                setPersistedProjects((response.projects || []).map((p) => ({ project_id: p.project_id, title: p.title || p.project_id })))
              }}
              className="mt-2 w-full rounded-lg border px-4 py-2 text-sm font-semibold transition hover:border-[#00d4aa]"
              style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
            >
              Create New Project
            </button>
            <button
              type="button"
              onClick={async () => {
                const safeProjectId = activeProjectId || 'local_project'
                try {
                  const exported = await fetchExportPackage(safeProjectId, 'pitch-pack')
                  downloadJson(`${safeProjectId}-pitch-pack.json`, exported)
                  setExportMessage('Export created')
                } catch {
                  const fallback = buildLocalFallbackExport('pitch-pack')
                  downloadJson(`${safeProjectId}-pitch-pack-fallback.json`, fallback)
                  setExportMessage('Export created (local fallback)')
                }
              }}
              className="mt-2 w-full rounded-lg border px-4 py-2 text-sm font-semibold transition hover:border-[#00d4aa]"
              style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
            >
              Export Pitch Pack
            </button>
            {exportMessage ? <div className="mt-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{exportMessage}</div> : null}
            {projectSaveMessage ? <div className="mt-2 text-xs" style={{ color: '#22c55e' }}>{projectSaveMessage}</div> : null}
          </section>

          {Boolean(localStorage.getItem('studio:lastBundle')) && !activeProjectId ? (
            <section className="rounded-2xl border border-amber-300/25 bg-amber-500/10 p-4 shadow-xl">
              <div className="text-[11px] uppercase tracking-[0.14em] text-amber-200">Migration</div>
              <div className="mt-2 text-sm text-zinc-100">Save this local film as a project</div>
              <button
                type="button"
                onClick={async () => {
                  const script = localStorage.getItem('studio:lastScript') || ''
                  const created = await createProject({ title: 'Migrated Local Film' })
                  if (!created.project?.project_id) {
                    setProjectSaveMessage('Unable to create project for migration')
                    return
                  }
                  localStorage.setItem('studio:activeProjectId', created.project.project_id)
                  if (script.trim()) {
                    await generateScenes(created.project.project_id, script)
                  }
                  setProjectSaveMessage('Local film saved to project')
                  await loadProject(created.project.project_id)
                }}
                className="mt-3 rounded-lg border border-amber-300/45 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-amber-100"
              >
                Save this local film as a project
              </button>
            </section>
          ) : null}

          <section className="rounded-[1.5rem] border border-cyan-300/30 bg-cyan-400/10 p-5 shadow-[0_24px_80px_rgba(34,211,238,0.1)] backdrop-blur-xl">
            <div className="text-[11px] uppercase tracking-[0.14em] text-cyan-200">What To Do Next</div>
            <div className="mt-2 text-lg font-semibold text-zinc-100">{nextDirective}</div>
            <Link to={nextDirectiveLink} className="mt-3 inline-flex rounded-xl border border-cyan-300/45 bg-cyan-400/15 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline transition hover:-translate-y-0.5 hover:bg-cyan-400/20">
              Continue
            </Link>
          </section>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {healthCards.map((card) => (
              <MetricCard
                key={card.label}
                label={card.label}
                value={card.score}
                status={card.status}
                accentClass={card.accent}
                barClass={card.bar}
              />
            ))}
          </section>
          <StudioBrainOrchestrationPanel executionSummary={executionSummary} />
          {activeProjectId ? <StudioBrainExecutivePanel projectId={activeProjectId} /> : null}
          <section className="rounded-2xl border border-cyan-300/25 bg-cyan-400/10 p-4 shadow-[0_20px_70px_rgba(34,211,238,0.08)] backdrop-blur-xl">
            <div className="text-[11px] uppercase tracking-[0.14em] text-cyan-200">Render QA Snapshot</div>
            <div className="mt-2 text-sm text-zinc-100">Average Script Faithfulness: {renderQaSnapshot.avg.toFixed(3)}</div>
            <div className="mt-1 text-xs text-zinc-300">High-Risk Scenes: {renderQaSnapshot.highRisk}</div>
          </section>
          <section className="rounded-2xl border border-rose-300/25 bg-rose-400/10 p-4 shadow-[0_20px_70px_rgba(244,63,94,0.08)] backdrop-blur-xl">
            <div className="text-[11px] uppercase tracking-[0.14em] text-rose-200">Creative Tension Score</div>
            <div className="mt-2 text-2xl font-semibold text-zinc-100">{creativeTension.score.toFixed(3)}</div>
            <div className="mt-1 text-xs text-zinc-300">
              conflicts: {creativeTension.total_conflicts} · high: {creativeTension.high_conflicts}
            </div>
          </section>
          <section className="rounded-2xl border border-indigo-300/25 bg-indigo-400/10 p-4 shadow-[0_20px_70px_rgba(99,102,241,0.08)] backdrop-blur-xl">
            <div className="text-[11px] uppercase tracking-[0.14em] text-indigo-200">Audio Crew Presence</div>
            <div className="mt-2 space-y-1 text-xs text-zinc-200">
              <div><span className="text-indigo-200">🎚 Sound Designer</span> - shaping ambience, silence, and impact hits</div>
              <div><span className="text-indigo-200">🎼 Composer</span> - shaping score motifs and emotional arc</div>
            </div>
          </section>

          <section className="grid grid-cols-1 gap-5 md:grid-cols-6 xl:grid-cols-12">
            <article className="xl:col-span-12 rounded-[1.5rem] border border-cyan-300/25 bg-white/[0.045] p-5 shadow-[0_28px_90px_rgba(0,0,0,0.34)] backdrop-blur-2xl">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-xs uppercase tracking-[0.14em] text-cyan-200">Studio Intelligence</h3>
                <div className="text-xs text-cyan-100">
                  score: <span className="font-semibold">{studioIntelligence.studio_intelligence_score.toFixed(3)}</span>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.12em]">
                <span className="rounded border border-white/15 bg-black/30 px-2 py-1 text-zinc-300">Total References: {studioIntelligence.total_references}</span>
                <span className="rounded border border-emerald-400/35 bg-emerald-500/10 px-2 py-1 text-emerald-200">Committed: {studioIntelligence.committed_references}</span>
              </div>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                {renderPatternRows('Visual', studioIntelligence.visual)}
                {renderPatternRows('Pacing', studioIntelligence.pacing)}
                {renderPatternRows('Motif', studioIntelligence.motif)}
                {renderPatternRows('Tone', studioIntelligence.tone)}
              </div>
              <div className="mt-3 rounded-lg border border-cyan-300/25 bg-black/30 px-3 py-2 text-xs text-zinc-200">
                <span className="uppercase tracking-[0.12em] text-cyan-200">Dominant Style</span>
                <div className="mt-1">{dominantStyleSummary}</div>
              </div>
              {studioIntelligence.visual.length === 0 &&
              studioIntelligence.pacing.length === 0 &&
              studioIntelligence.motif.length === 0 &&
              studioIntelligence.tone.length === 0 ? (
                <div className="mt-3 rounded-lg border border-dashed border-cyan-300/25 bg-black/25 px-3 py-3 text-xs text-zinc-300">
                  <div>Your studio has not learned from any references yet.</div>
                  <Link
                    to="/studio/study-room"
                    className="mt-2 inline-flex rounded-md border border-cyan-300/40 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline"
                  >
                    Open Study Room
                  </Link>
                </div>
              ) : null}
            </article>
            <article className="xl:col-span-5 rounded-[1.5rem] border border-white/12 bg-white/[0.045] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.3)] backdrop-blur-xl">
              <h3 className="text-xs uppercase tracking-[0.14em] text-zinc-300">Current Project Panel</h3>
              <div className="mt-4 grid grid-cols-1 items-center gap-4 sm:grid-cols-[1fr_auto]">
                <div className="space-y-1 text-sm text-zinc-200">
                  <div>Title: <span className="text-zinc-100">{project?.title || 'No project loaded'}</span></div>
                  <div>Total Scenes: <span className="text-zinc-100">{asNumber(filmStructure.total_scenes) ?? scenes.length}</span></div>
                  <div>Completion: <span className="text-zinc-100">{`${Math.round(clampPercent((asNumber(filmProgress.completion_percent) ?? 0) * 100))}%`}</span></div>
                  <div>Ready to Screen: <span className="text-zinc-100">{filmProgress.ready_to_screen ? 'YES' : 'NO'}</span></div>
                </div>
                <div className="relative grid h-24 w-24 place-items-center rounded-full border border-cyan-300/40">
                  <div className="absolute inset-1 rounded-full border-4 border-cyan-300/20 border-t-cyan-300" />
                  <span className="text-sm font-semibold text-cyan-200">{`${Math.round(clampPercent((asNumber(filmProgress.completion_percent) ?? 0) * 100))}%`}</span>
                </div>
              </div>
            </article>

            <article className="xl:col-span-4 rounded-[1.5rem] border border-amber-300/25 bg-amber-400/10 p-5 shadow-[0_24px_80px_rgba(245,158,11,0.08)] backdrop-blur-xl">
              <h3 className="text-xs uppercase tracking-[0.14em] text-amber-200">Next Best Action</h3>
              <div className="mt-3 text-lg font-semibold text-zinc-100">
                {scenes.length > 0 ? `Scene ${String((scenes[0]?.scene_id || 'scene_001')).replace('scene_', '')} needs your review` : 'Generate scenes to continue'}
              </div>
              <p className="mt-2 text-xs text-zinc-300">
                {scenes.length > 0 ? 'Review continuity, pacing, and motif progression before final cut.' : 'No scenes yet. Start in Writer’s Room and generate scenes.'}
              </p>
              <button
                type="button"
                onClick={() => {
                  navigate('/studio/previs', {
                    state: {
                      target_scene_id: String(scenes[0]?.scene_id || 'scene_001'),
                    },
                  })
                }}
                className="mt-4 rounded-xl border border-amber-300/45 bg-amber-400/15 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-amber-100 transition hover:-translate-y-0.5 hover:bg-amber-400/20"
              >
                Review Scene
              </button>
            </article>

            <article className="xl:col-span-3 rounded-[1.5rem] border border-cyan-300/25 bg-cyan-400/10 p-5 shadow-[0_24px_80px_rgba(34,211,238,0.08)] backdrop-blur-xl">
              <h3 className="text-xs uppercase tracking-[0.14em] text-cyan-200">Co-Director Note</h3>
              <blockquote className="mt-3 border-l-2 border-cyan-300/45 pl-3 text-sm italic text-zinc-200">
                {STUDIO_AGENTS.director.icon} {STUDIO_AGENTS.director.name}: “The emotional beat at the end of Scene 12 feels rushed. Hold the transition for one more breath.”
              </blockquote>
            </article>
          </section>

          <section className="rounded-[1.5rem] border border-white/12 bg-white/[0.045] p-5 shadow-[0_28px_90px_rgba(0,0,0,0.34)] backdrop-blur-2xl">
            <TabGroup
              className="mb-3"
              value={overviewTab}
              onChange={(next) => setOverviewTab(next)}
              options={[
                { id: 'activity', label: 'Activity' },
                { id: 'issues', label: 'Issues' },
                { id: 'rooms', label: 'Rooms' },
                { id: 'memory', label: 'Memory' },
              ]}
            />

            {overviewTab === 'activity' ? (
              <div className="space-y-2">
                {derivedRecentActivity.map((activity) => (
                  <div key={activity} className="rounded-xl border border-white/10 bg-black/35 px-3 py-2 text-xs text-zinc-200 transition hover:border-amber-300/30 hover:bg-black/45">{activity}</div>
                ))}
              </div>
            ) : null}

            {overviewTab === 'issues' ? (
              <div className="space-y-2">
                {openIssues.length > 0 ? openIssues.map((issue) => (
                  <div key={issue} className="rounded-xl border border-white/10 bg-black/35 px-3 py-2 text-xs text-zinc-200 transition hover:border-rose-300/30 hover:bg-black/45">{issue}</div>
                )) : (
                  <EmptyStateCard title="No Active Issues" message="Generate scenes to populate this panel." />
                )}
              </div>
            ) : null}

            {overviewTab === 'rooms' ? (
              <CollapsibleSection title="Room Preview Grid" defaultOpen>
              <div className="mt-1 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {roomPreviews.map((room) => (
                  <article key={room.title} className="rounded-2xl border border-white/10 bg-black/35 p-4 shadow-[0_14px_45px_rgba(0,0,0,0.18)] transition-all duration-200 hover:-translate-y-0.5 hover:border-amber-300/45 hover:bg-black/45">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100">{room.title}</div>
                        <div className="mt-1 text-[11px] text-zinc-400">{room.status}</div>
                      </div>
                      <span className="h-2 w-2 rounded-full bg-cyan-300/80" />
                    </div>
                    <div className="mt-3 rounded-md border border-white/10 bg-zinc-900/60 px-2 py-1 text-[11px] text-zinc-300">{room.preview}</div>
                    <Link to={room.to} className="mt-3 inline-flex rounded-md border border-amber-300/35 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-100 no-underline">
                      Open
                    </Link>
                  </article>
                ))}
              </div>
              </CollapsibleSection>
            ) : null}

            {overviewTab === 'memory' ? (
              <div className="space-y-2 text-xs text-zinc-200">
                <div className="rounded-xl border border-white/10 bg-black/35 px-3 py-2">Total references: {studioIntelligence.total_references}</div>
                <div className="rounded-xl border border-white/10 bg-black/35 px-3 py-2">Committed references: {studioIntelligence.committed_references}</div>
                <div className="rounded-xl border border-white/10 bg-black/35 px-3 py-2">Intelligence score: {studioIntelligence.studio_intelligence_score.toFixed(3)}</div>
              </div>
            ) : null}
          </section>
          </div>
        </div>
      </div>
    </StudioShell>
  )
}

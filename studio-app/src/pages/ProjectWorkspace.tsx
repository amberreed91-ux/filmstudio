/* eslint-disable react-refresh/only-export-components */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { CheckCircle2, GitBranch, Lock, Save } from 'lucide-react'
import StudioShell from '../components/StudioShell'
import StudioPanel from '../components/StudioPanel'
import CoDirectorInspectionPanel from '../components/CoDirectorInspectionPanel'
import ExecutionSummaryInspectionPanel from '../components/ExecutionSummaryInspectionPanel'
import { extractExecutionSummaryInspection, resolveRenderSource } from '../lib/executionSummaryInspection'
import { useStudio } from '../context/StudioContext'
import { STUDIO_API_BASE, type StudioProject } from '../lib/studioApi'
import {
  buildAgentProfiles,
  buildCrewThreads,
  buildMemoryEntries,
  buildOrchestration,
  buildProjectIdentity,
  buildReflections,
  buildWorkflowStages,
} from '../lib/studioSystem'
import { createSlateVariant, getVariantById, loadWorkspaceState, saveWorkspaceState, type LeadershipNote, type ProductionMode } from '../lib/studioWorkspaceState'
import { getProviderSummaries, getRenderQueueRows } from '../lib/studioSelectors'

const MODES: ProductionMode[] = ['indie', 'prestige', 'commercial', 'experimental', 'streaming', 'documentary']

export function extractProductionSignalMessage(project: StudioProject | null): string | null {
  const executionSummary = (project as { execution_summary?: unknown } | null)?.execution_summary
  if (!executionSummary || typeof executionSummary !== 'object' || Array.isArray(executionSummary)) {
    return null
  }
  const productionSignal = (executionSummary as { production_signal?: unknown }).production_signal
  if (!productionSignal || typeof productionSignal !== 'object' || Array.isArray(productionSignal)) {
    return null
  }
  const message = (productionSignal as { message?: unknown }).message
  if (typeof message !== 'string') {
    return null
  }
  const trimmed = message.trim()
  return trimmed || null
}

export function extractSceneIntentLabel(project: StudioProject | null): string | null {
  return ((project as { execution_summary?: { scene_intent?: { label?: string } } } | null)?.execution_summary?.scene_intent?.label ?? null)
}

export function extractReviewStateMessage(project: StudioProject | null): string | null {
  const message =
    (project as { execution_summary?: { intent_output_relation?: { message?: string } } } | null)
      ?.execution_summary
      ?.intent_output_relation
      ?.message ?? null
  if (typeof message !== 'string') {
    return null
  }
  const trimmed = message.trim()
  return trimmed || null
}

export function extractMemoryVisibilityMessage(project: StudioProject | null): string | null {
  const executionSummary =
    (project as { execution_summary?: { memory_advisory_projection?: { status?: unknown }; memory_influence_gate?: { mode?: unknown } } } | null)
      ?.execution_summary ?? null
  const advisoryStatus = executionSummary?.memory_advisory_projection?.status
  const influenceMode = executionSummary?.memory_influence_gate?.mode
  if (advisoryStatus !== 'available' || influenceMode !== 'disabled') {
    return null
  }
  return 'Available for review, influence disabled'
}

export function extractMemorySnapshotMessage(project: StudioProject | null): string | null {
  const executionSummary =
    (project as {
      execution_summary?: {
        memory_state_rollup?: { status?: unknown; influence_mode?: unknown }
        memory_consistency?: { is_consistent?: unknown }
      }
    } | null)?.execution_summary ?? null

  const stateStatus = executionSummary?.memory_state_rollup?.status
  const influenceMode = executionSummary?.memory_state_rollup?.influence_mode
  const isConsistent = executionSummary?.memory_consistency?.is_consistent
  if (stateStatus !== 'available' || influenceMode !== 'disabled' || isConsistent !== true) {
    return null
  }
  return 'Available, influence disabled'
}

export function extractShotPlanMessage(project: StudioProject | null): string | null {
  const executionSummary =
    (project as {
      execution_summary?: {
        shot_candidates?: unknown
        shot_plan_bundle?: { influence_mode?: unknown }
      }
    } | null)?.execution_summary ?? null

  const candidates = executionSummary?.shot_candidates
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return null
  }
  const influenceMode = executionSummary?.shot_plan_bundle?.influence_mode
  if (influenceMode !== 'disabled') {
    return null
  }

  const scenes = new Set<string>()
  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
      continue
    }
    const sceneId = (candidate as { scene_id?: unknown }).scene_id
    if (typeof sceneId === 'string' && sceneId.trim()) {
      scenes.add(sceneId.trim())
    }
  }
  const sceneCount = scenes.size
  if (sceneCount <= 0) {
    return null
  }
  return `${sceneCount} scenes prepared`
}

export function extractVisualBoardMessage(project: StudioProject | null): string | null {
  const executionSummary =
    (project as {
      execution_summary?: {
        visual_reference_summary?: { reference_count?: unknown }
        frame_stats?: { frame_count?: unknown }
        link_completeness?: { linked_scenes?: unknown; total_scenes?: unknown }
        co_director_visual_feed?: { mode?: unknown }
      }
    } | null)?.execution_summary ?? null

  const mode = executionSummary?.co_director_visual_feed?.mode
  if (mode !== 'read_only') {
    return null
  }

  const referenceCountRaw = executionSummary?.visual_reference_summary?.reference_count
  const frameCountRaw = executionSummary?.frame_stats?.frame_count
  const linkedScenesRaw = executionSummary?.link_completeness?.linked_scenes
  const totalScenesRaw = executionSummary?.link_completeness?.total_scenes

  const referenceCount = typeof referenceCountRaw === 'number' && Number.isFinite(referenceCountRaw) && referenceCountRaw >= 0
    ? referenceCountRaw
    : 0
  const frameCount = typeof frameCountRaw === 'number' && Number.isFinite(frameCountRaw) && frameCountRaw >= 0
    ? frameCountRaw
    : 0
  const linkedScenes = typeof linkedScenesRaw === 'number' && Number.isFinite(linkedScenesRaw) && linkedScenesRaw >= 0
    ? linkedScenesRaw
    : 0
  const totalScenes = typeof totalScenesRaw === 'number' && Number.isFinite(totalScenesRaw) && totalScenesRaw >= 0
    ? totalScenesRaw
    : 0

  if (referenceCount <= 0 && frameCount <= 0 && totalScenes <= 0) {
    return null
  }

  return `References ${referenceCount} · Frames ${frameCount} · Linked ${linkedScenes}/${totalScenes}`
}

export function extractPrevisStripMessage(project: StudioProject | null): string | null {
  const executionSummary =
    (project as {
      execution_summary?: {
        previs_scene_board?: unknown
        previs_beat_shot_map?: unknown
        previs_continuity_map?: unknown
        previs_asset_map?: unknown
      }
    } | null)?.execution_summary ?? null

  const sceneBoard = executionSummary?.previs_scene_board
  if (!Array.isArray(sceneBoard) || sceneBoard.length === 0) {
    return null
  }

  let validSceneCount = 0
  let totalShots = 0
  const uniqueRefs = new Set<string>()

  for (const entry of sceneBoard) {
    // Apply same validation as asPrevisSceneBoardEntry:
    // - entry must be a non-null object (not array)
    // - scene_id must be a non-empty string
    // - shot_count must be a valid number >= 0
    // - linked_refs must be an array of strings
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      continue
    }

    const root = entry as Record<string, unknown>
    const sceneId = root.scene_id
    const shotCount = root.shot_count
    const linkedRefsRaw = root.linked_refs

    // scene_id must be a non-empty string
    if (typeof sceneId !== 'string' || !sceneId.trim()) {
      continue
    }

    // shot_count must be a valid number >= 0
    if (typeof shotCount !== 'number' || !Number.isFinite(shotCount) || shotCount < 0) {
      continue
    }

    // linked_refs must be an array of strings (matching asStringArray behavior)
    if (!Array.isArray(linkedRefsRaw)) {
      continue
    }

    // Each ref in linkedRefs must be a valid string (matching asStringArray)
    let hasValidLinkedRefs = true
    for (const ref of linkedRefsRaw) {
      if (typeof ref !== 'string') {
        hasValidLinkedRefs = false
        break
      }
    }
    if (!hasValidLinkedRefs) {
      continue
    }

    // Entry is valid - count it
    validSceneCount++
    totalShots += shotCount
    for (const ref of linkedRefsRaw) {
      if (typeof ref === 'string' && ref.trim()) {
        uniqueRefs.add(ref.trim())
      }
    }
  }

  if (validSceneCount === 0) {
    return null
  }

  return `Previs · Scenes ${validSceneCount} · Shots ${totalShots} · References ${uniqueRefs.size}`
}

export function buildInspection(project: StudioProject | null) {
  return extractExecutionSummaryInspection(project)
}

export function extractProviderStatusStripMessage(project: StudioProject | null): string | null {
  const inspection = buildInspection(project)
  if (!inspection) return null
  const provider = inspection.providerAdapterStatus?.provider ?? inspection.providerName
  const enabled = inspection.providerAdapterStatus?.enabled ?? false
  const ready = inspection.providerAdapterReadinessGate?.ready ?? false
  return `Provider · ${provider} · Enabled ${String(enabled)} · Ready ${String(ready)}`
}

export function extractExecutionStatusStripMessage(project: StudioProject | null): string | null {
  const inspection = buildInspection(project)
  if (!inspection) return null
  const locked = inspection.executionUnlockState?.locked ?? true
  const eligible = inspection.executionEligibility?.eligible ?? false
  const request = inspection.executionRequestEnvelope?.request ?? 'blocked'
  return `Execution · ${locked ? 'Locked' : 'Unlocked'} · Eligible ${String(eligible)} · Request ${request}`
}

export function extractValidationStatusStripMessage(project: StudioProject | null): string | null {
  const inspection = buildInspection(project)
  if (!inspection) return null
  const schema = inspection.requestSchemaValidation?.valid ? 'valid' : 'invalid'
  const provider = inspection.providerValidation?.valid ? 'valid' : 'invalid'
  const payload = inspection.payloadSanitization?.safe ? 'safe' : 'unsafe'
  return `Validation · Schema ${schema} · Provider ${provider} · Payload ${payload}`
}

export function extractShotPipelineStripMessage(project: StudioProject | null): string | null {
  const inspection = buildInspection(project)
  if (!inspection) return null
  const shots = inspection.shotExecutionLedger?.length ?? 0
  const queue = inspection.shotQueue?.length ?? 0
  const ready = inspection.multiShotReadiness?.ready ?? 0
  return `Shots · ${shots} · Queue ${queue} · Ready ${ready}`
}

export function extractTakePipelineStripMessage(project: StudioProject | null): string | null {
  const inspection = buildInspection(project)
  if (!inspection) return null
  const takeCount = inspection.takeArtifacts?.length ?? 0
  const comparable = inspection.takeComparisonV2?.comparable ?? false
  const autoSelect = inspection.takePreferenceContract?.autoSelect ?? false
  return `Takes · ${takeCount} · Comparable ${String(comparable)} · Auto Select ${String(autoSelect)}`
}

export function extractRenderStatusStripMessage(project: StudioProject | null): string | null {
  const inspection = buildInspection(project)
  if (!inspection) return null
  const mockRenderOutput = inspection.mockRenderOutput ?? {
    renderId: null,
    status: 'not_executed',
    provider: inspection.providerName,
    hasOutput: false,
  }
  const sourceResolution = resolveRenderSource(inspection)
  const hasOutput = Boolean(
    sourceResolution.source !== 'none' &&
      (sourceResolution.filePath || sourceResolution.url || inspection.localRenderOutput?.hasOutput || mockRenderOutput.hasOutput)
  )
  const status = inspection.executionResultV2?.status ?? mockRenderOutput.status
  return `Render · ${status} · Source ${sourceResolution.source} · Output ${hasOutput ? 'yes' : 'no'}`
}

export function extractSceneStatusStripMessage(project: StudioProject | null): string | null {
  const inspection = buildInspection(project)
  if (!inspection) return null
  const summary = inspection.sceneGenerationSummary
  const preview = inspection.scenePlaybackPreview
  if (!summary || !preview) return null
  return `Scene · ${summary.status} · Shots ${summary.completedShots}/${summary.plannedShots} · Preview ${preview.available ? 'yes' : 'no'}`
}

export function getProductionSignalSeverity(message: string): 'normal' | 'warning' | 'degraded' {
  if (message === 'Retry-heavy condition detected') return 'warning'
  if (message === 'Stuck pattern detected' || message === 'Provider failure pattern detected') return 'degraded'
  return 'normal'
}

export function ProductionSignalStrip({ message }: { message: string }) {
  const severity = getProductionSignalSeverity(message)
  const borderColor =
    severity === 'warning'
      ? 'color-mix(in srgb, var(--accent-blue) 22%, var(--border))'
      : severity === 'degraded'
        ? 'color-mix(in srgb, var(--text-primary) 24%, var(--border))'
        : 'var(--border)'
  const messageColor =
    severity === 'warning'
      ? 'color-mix(in srgb, var(--accent-blue) 60%, var(--text-secondary))'
      : severity === 'degraded'
        ? 'color-mix(in srgb, var(--text-primary) 78%, var(--text-secondary))'
        : 'var(--text-secondary)'
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: `1px solid ${borderColor}` }}
      data-testid="production-signal-strip"
      data-severity={severity}
    >
      <span style={{ color: 'var(--text-muted)' }}>Production Signal</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: messageColor }}>{message}</span>
    </div>
  )
}

export function IntentSignalStrip({ label }: { label: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="intent-signal-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Intent</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
    </div>
  )
}

export function ReviewStateStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="review-state-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Review State</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function MemoryVisibilityStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="memory-visibility-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Memory Visibility</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function MemorySnapshotStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="memory-snapshot-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Memory Snapshot</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ShotPlanStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="shot-plan-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Shot Plan</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function VisualBoardStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="visual-board-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>Visual Board</span>
      <span style={{ color: 'var(--text-muted)' }}> · </span>
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function PrevisStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="previs-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ProviderStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="provider-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ExecutionStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="execution-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ValidationStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="validation-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function ShotPipelineStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="shot-pipeline-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function TakePipelineStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="take-pipeline-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function RenderStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="render-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export function SceneStatusStrip({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="scene-status-strip"
    >
      <span style={{ color: 'var(--text-muted)' }}>{message}</span>
    </div>
  )
}

export default function ProjectWorkspace() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const variantId = searchParams.get('variant')
  const sessionId = searchParams.get('session_id')
  const variant = useMemo(() => getVariantById(variantId), [variantId])
  const { project, overview, loadProject, loading } = useStudio()
  const loadRequestKeyRef = useRef<string | null>(null)
  const activeProject = project?.project_id === projectId ? project : null
  const sourceProject = activeProject || (overview?.latest_project?.project_id === projectId ? overview?.latest_project ?? null : null)
  const workspaceKey = `${projectId}:${variant?.id || 'main'}`

  useEffect(() => {
    if (!projectId) return
    const loadRequestKey = `${projectId}:${sessionId ?? ''}`
    if (loadRequestKeyRef.current === loadRequestKey) return
    loadRequestKeyRef.current = loadRequestKey
    void loadProject(projectId, { sessionId })
  }, [loadProject, projectId, sessionId])

  if (!projectId) {
    return (
      <StudioShell title="Project Workspace" subtitle="No project was selected for the workspace.">
        <div className="p-6">
          <StudioPanel title="Workspace unavailable" subtitle="Choose a project from the slate to open a live production workspace.">
            <Link to="/studio/slate" className="btn-primary no-underline inline-flex">Open Project Slate</Link>
          </StudioPanel>
        </div>
      </StudioShell>
    )
  }

  return (
    <ProjectWorkspaceBody
      key={workspaceKey}
      projectId={projectId}
      sourceProject={sourceProject}
      variantId={variantId}
      loading={loading}
    />
  )
}

export function ProjectWorkspaceBody({
  projectId,
  sourceProject,
  variantId,
  loading,
}: {
  projectId: string
  sourceProject: StudioProject | null
  variantId: string | null
  loading: boolean
}) {
  const variant = useMemo(() => getVariantById(variantId), [variantId])
  const initialIdentity = useMemo(() => buildProjectIdentity(sourceProject, variant?.mode), [sourceProject, variant?.mode])
  const workspaceKey = `${projectId}:${variant?.id || 'main'}`
  const [workspaceState, setWorkspaceState] = useState(() => loadWorkspaceState(workspaceKey, initialIdentity.productionMode))
  const [leadershipInput, setLeadershipInput] = useState('')

  useEffect(() => {
    saveWorkspaceState(workspaceKey, workspaceState)
  }, [workspaceKey, workspaceState])

  if (!loading && !sourceProject) {
    return (
      <StudioShell title="Project Workspace" subtitle="This project could not be loaded from the backend.">
        <div className="p-6">
          <StudioPanel title="Project not found" subtitle={`The backend returned 404 for project id "${projectId}".`}>
            <div className="space-y-3">
              <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                Choose an existing project from the slate, or ingest a script to create one.
              </div>
              <div className="flex flex-wrap gap-2">
                <Link to="/studio/slate" className="btn-primary no-underline inline-flex">Open Project Slate</Link>
                <Link to="/studio/ingest" className="btn-ghost no-underline inline-flex">Ingest Script</Link>
              </div>
              <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Backend: <a href={`${STUDIO_API_BASE}/docs`} target="_blank" className="underline" rel="noreferrer">API docs</a>
              </div>
            </div>
          </StudioPanel>
        </div>
      </StudioShell>
    )
  }

  const identity = buildProjectIdentity(sourceProject, workspaceState.productionMode)
  const workflow = buildWorkflowStages(sourceProject ?? null, workspaceState.productionMode)
  const agents = buildAgentProfiles(sourceProject ?? null, workspaceState.productionMode)
  const threads = buildCrewThreads(agents).map((thread) => ({
    ...thread,
    status: workspaceState.resolvedThreads.includes(thread.id) ? 'resolved' : thread.status,
  }))
  const memory = buildMemoryEntries(
    sourceProject ?? null,
    identity,
    workspaceState.lockedDecisions,
    workspaceState.leadershipNotes.map((note) => note.text),
  )
  const reflections = buildReflections(sourceProject ?? null, threads)
  const orchestration = buildOrchestration(sourceProject ?? null, workflow, threads, identity)
  const queueRows = getRenderQueueRows(sourceProject ?? null)
  const providers = getProviderSummaries(sourceProject ?? null)
  const productionSignalMessage = extractProductionSignalMessage(sourceProject ?? null)
  const sceneIntentLabel = extractSceneIntentLabel(sourceProject ?? null)
  const reviewStateMessage = extractReviewStateMessage(sourceProject ?? null)
  const memoryVisibilityMessage = extractMemoryVisibilityMessage(sourceProject ?? null)
  const memorySnapshotMessage = extractMemorySnapshotMessage(sourceProject ?? null)
  const shotPlanMessage = extractShotPlanMessage(sourceProject ?? null)
  const visualBoardMessage = extractVisualBoardMessage(sourceProject ?? null)
  const previsStripMessage = extractPrevisStripMessage(sourceProject ?? null)
  const providerStatusStripMessage = extractProviderStatusStripMessage(sourceProject ?? null)
  const executionStatusStripMessage = extractExecutionStatusStripMessage(sourceProject ?? null)
  const validationStatusStripMessage = extractValidationStatusStripMessage(sourceProject ?? null)
  const shotPipelineStripMessage = extractShotPipelineStripMessage(sourceProject ?? null)
  const takePipelineStripMessage = extractTakePipelineStripMessage(sourceProject ?? null)
  const renderStatusStripMessage = extractRenderStatusStripMessage(sourceProject ?? null)
  const sceneStatusStripMessage = extractSceneStatusStripMessage(sourceProject ?? null)
  const currentVariantLabel = variant ? `${variant.kind}: ${variant.title}` : 'Main production path'

  function toggleLockedDecision(decision: string) {
    setWorkspaceState((current) => ({
      ...current,
      lockedDecisions: current.lockedDecisions.includes(decision)
        ? current.lockedDecisions.filter((item) => item !== decision)
        : [...current.lockedDecisions, decision],
    }))
  }

  function toggleApprovedStage(stageId: string) {
    setWorkspaceState((current) => ({
      ...current,
      approvedStages: current.approvedStages.includes(stageId)
        ? current.approvedStages.filter((item) => item !== stageId)
        : [...current.approvedStages, stageId],
    }))
  }

  function toggleResolvedThread(threadId: string) {
    setWorkspaceState((current) => ({
      ...current,
      resolvedThreads: current.resolvedThreads.includes(threadId)
        ? current.resolvedThreads.filter((item) => item !== threadId)
        : [...current.resolvedThreads, threadId],
    }))
  }

  function saveLeadershipNote() {
    if (!leadershipInput.trim()) return
    const note: LeadershipNote = {
      id: `note-${Date.now()}`,
      text: leadershipInput.trim(),
      createdAt: new Date().toISOString(),
    }
    setWorkspaceState((current) => ({
      ...current,
      leadershipNotes: [note, ...current.leadershipNotes].slice(0, 6),
    }))
    setLeadershipInput('')
  }

  function branchCreativeDirection() {
    createSlateVariant({
      sourceProjectId: projectId,
      title: `${identity.title} ${workspaceState.productionMode === 'prestige' ? 'Festival Cut' : 'Market Cut'}`,
      kind: 'branch',
      mode: workspaceState.productionMode,
      stage: identity.stage,
      notes: 'Branch generated from the workspace to explore alternate tone, pacing, and commercial positioning.',
    })
  }

  return (
    <StudioShell title={`${identity.title} Workspace`} subtitle="Run the project like a studio head: review the pipeline, direct the crew, and lock creative decisions.">
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {providerStatusStripMessage || executionStatusStripMessage || validationStatusStripMessage || shotPipelineStripMessage || takePipelineStripMessage || renderStatusStripMessage || sceneStatusStripMessage || productionSignalMessage || sceneIntentLabel || reviewStateMessage || memoryVisibilityMessage || memorySnapshotMessage || shotPlanMessage || previsStripMessage || visualBoardMessage ? (
          <div className="space-y-2">
            {providerStatusStripMessage ? <ProviderStatusStrip message={providerStatusStripMessage} /> : null}
            {executionStatusStripMessage ? <ExecutionStatusStrip message={executionStatusStripMessage} /> : null}
            {validationStatusStripMessage ? <ValidationStatusStrip message={validationStatusStripMessage} /> : null}
            {shotPipelineStripMessage ? <ShotPipelineStrip message={shotPipelineStripMessage} /> : null}
            {takePipelineStripMessage ? <TakePipelineStrip message={takePipelineStripMessage} /> : null}
            {renderStatusStripMessage ? <RenderStatusStrip message={renderStatusStripMessage} /> : null}
            {sceneStatusStripMessage ? <SceneStatusStrip message={sceneStatusStripMessage} /> : null}
            {productionSignalMessage ? <ProductionSignalStrip message={productionSignalMessage} /> : null}
            {sceneIntentLabel ? <IntentSignalStrip label={sceneIntentLabel} /> : null}
            {reviewStateMessage ? <ReviewStateStrip message={reviewStateMessage} /> : null}
            {memoryVisibilityMessage ? <MemoryVisibilityStrip message={memoryVisibilityMessage} /> : null}
            {memorySnapshotMessage ? <MemorySnapshotStrip message={memorySnapshotMessage} /> : null}
            {shotPlanMessage ? <ShotPlanStrip message={shotPlanMessage} /> : null}
            {previsStripMessage ? <PrevisStrip message={previsStripMessage} /> : null}
            {visualBoardMessage ? <VisualBoardStrip message={visualBoardMessage} /> : null}
          </div>
        ) : null}
        <div className="flex items-center justify-end">
          <Link to={`/studio/project/${projectId}/previs`} className="btn-ghost no-underline inline-flex text-xs px-3 py-1.5">
            Open Previs Room
          </Link>
        </div>
        <StudioPanel
          title="Project Overview Panel"
          subtitle={identity.logline}
          action={
            <button type="button" className="btn-ghost text-xs px-3 py-1.5 inline-flex items-center gap-1" onClick={branchCreativeDirection}>
              <GitBranch size={12} />
              Branch Creative Direction
            </button>
          }
        >
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Genre', value: identity.genre },
              { label: 'Tone', value: identity.tone },
              { label: 'Audience', value: identity.audience },
              { label: 'Budget Level', value: identity.budgetLevel },
              { label: 'Production Mode', value: currentVariantLabel },
              { label: 'Current Stage', value: identity.stage },
              { label: 'Commercial Positioning', value: identity.commercialPositioning },
              { label: 'Festival Viability', value: identity.festivalViability },
            ].map((item) => (
              <div key={item.label} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{item.label}</div>
                <div className="text-sm font-medium mt-1" style={{ color: 'var(--text-primary)' }}>{item.value}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <label className="text-xs" style={{ color: 'var(--text-muted)' }}>Production Mode</label>
            <select
              value={workspaceState.productionMode}
              onChange={(event) => setWorkspaceState((current) => ({ ...current, productionMode: event.target.value as ProductionMode }))}
              className="px-3 py-2 rounded-lg text-xs"
              style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
            >
              {MODES.map((mode) => (
                <option key={mode} value={mode}>{mode}</option>
              ))}
            </select>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Influences: {identity.influences.join(' • ')}
            </div>
          </div>
        </StudioPanel>

        <div className="grid grid-cols-[1.45fr_0.95fr] gap-4">
          <StudioPanel title="Production Pipeline Panel" subtitle="Stage-based workflow orchestration with approvals, revisions, and handoffs.">
            <div className="space-y-3">
              {workflow.map((stage) => {
                const approved = workspaceState.approvedStages.includes(stage.id)
                return (
                  <div key={stage.id} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{stage.label}</div>
                        <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{stage.note}</div>
                      </div>
                      <button type="button" className="btn-ghost text-xs px-3 py-1.5 inline-flex items-center gap-1" onClick={() => toggleApprovedStage(stage.id)}>
                        <CheckCircle2 size={12} />
                        {approved ? 'Unapprove' : 'Approve Stage'}
                      </button>
                    </div>
                    <div className="grid grid-cols-4 gap-2 mt-3">
                      <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                        <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Status</div>
                        <div className="text-xs mt-1" style={{ color: approved ? 'var(--accent-green)' : 'var(--text-primary)' }}>{approved ? 'Approved' : stage.status}</div>
                      </div>
                      <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                        <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Agents</div>
                        <div className="text-xs mt-1" style={{ color: 'var(--text-primary)' }}>{stage.assignedAgents.join(', ')}</div>
                      </div>
                      <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                        <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Pending Approvals</div>
                        <div className="text-xs mt-1" style={{ color: 'var(--text-primary)' }}>{stage.pendingApprovals}</div>
                      </div>
                      <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                        <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Revisions</div>
                        <div className="text-xs mt-1" style={{ color: 'var(--text-primary)' }}>{stage.revisionCount}</div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 mt-3">
                      {stage.deliverables.map((deliverable) => (
                        <span key={deliverable} className="text-xs px-2 py-1 rounded-full" style={{ background: 'rgba(0,200,255,0.08)', color: 'var(--accent-cyan)', border: '1px solid rgba(0,200,255,0.16)' }}>
                          {deliverable}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </StudioPanel>

          <StudioPanel title="Orchestration Layer" subtitle="Studio leadership controls pacing, approvals, and conflict resolution.">
            <div className="space-y-3">
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Controller Status</div>
                <div className="text-sm mt-1" style={{ color: 'var(--text-primary)' }}>{orchestration.controllerStatus}</div>
              </div>
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>Next Best Actions</div>
                <div className="space-y-2">
                  {orchestration.nextBestActions.map((action) => (
                    <button
                      key={action}
                      type="button"
                      onClick={() => toggleLockedDecision(action)}
                      className="w-full text-left px-3 py-2 rounded-lg"
                      style={{
                        background: workspaceState.lockedDecisions.includes(action) ? 'rgba(34,197,94,0.12)' : 'var(--bg-card)',
                        border: '1px solid var(--border)',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      <span className="inline-flex items-center gap-1">
                        <Lock size={12} />
                        {workspaceState.lockedDecisions.includes(action) ? 'Locked' : 'Tap to lock'}:
                      </span>
                      <span className="ml-2">{action}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>Bottlenecks</div>
                <div className="space-y-2">
                  {orchestration.bottlenecks.map((item) => (
                    <div key={item} className="text-xs px-3 py-2 rounded-lg" style={{ background: 'rgba(249,115,22,0.08)', border: '1px solid rgba(249,115,22,0.2)', color: '#f59e0b' }}>
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </StudioPanel>
        </div>

        <div className="grid grid-cols-[1.1fr_0.9fr] gap-4">
          <StudioPanel title="Crew Panel" subtitle="Agent roles, craft authority, performance, and anti-redundancy scoring.">
            <div className="space-y-3">
              {agents.map((agent) => (
                <div key={agent.id} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{agent.role}</div>
                      <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{agent.mission}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Performance</div>
                      <div className="text-lg font-semibold" style={{ color: 'var(--accent-cyan)' }}>{agent.performanceScore}</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                      <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Current Task</div>
                      <div className="text-xs mt-1" style={{ color: 'var(--text-primary)' }}>{agent.currentTask}</div>
                    </div>
                    <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                      <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Activity Status</div>
                      <div className="text-xs mt-1" style={{ color: 'var(--text-primary)' }}>{agent.activityStatus}</div>
                    </div>
                    <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                      <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Redundancy Score</div>
                      <div className="text-xs mt-1" style={{ color: agent.redundancyScore > 20 ? '#f59e0b' : 'var(--accent-green)' }}>{agent.redundancyScore}</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 mt-3">
                    {agent.recentContributions.map((contribution) => (
                      <div key={contribution.id} className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                        <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{contribution.focus}</div>
                        <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{contribution.comment}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </StudioPanel>

          <StudioPanel title="Crew Room" subtitle="Structured, role-based discussion with overlap suppression and escalation logic.">
            <div className="space-y-3">
              {threads.map((thread) => (
                <div key={thread.id} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{thread.title}</div>
                      <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{thread.objective}</div>
                    </div>
                    <button type="button" className="btn-ghost text-xs px-3 py-1.5" onClick={() => toggleResolvedThread(thread.id)}>
                      {workspaceState.resolvedThreads.includes(thread.id) ? 'Reopen' : 'Resolve Thread'}
                    </button>
                  </div>
                  <div className="mt-3 text-xs" style={{ color: thread.status === 'needs-escalation' ? '#f59e0b' : thread.status === 'resolved' ? 'var(--accent-green)' : 'var(--accent-cyan)' }}>
                    {thread.status}
                  </div>
                  {thread.overlapSummary && (
                    <div className="mt-2 text-xs px-3 py-2 rounded-lg" style={{ background: 'rgba(249,115,22,0.08)', border: '1px solid rgba(249,115,22,0.18)', color: '#f59e0b' }}>
                      {thread.overlapSummary}
                    </div>
                  )}
                  <div className="space-y-2 mt-3">
                    {thread.comments.map((comment) => (
                      <div key={comment.id} className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                        <div className="text-[11px]" style={{ color: 'var(--accent-cyan)' }}>{comment.department}</div>
                        <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{comment.comment}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 text-xs" style={{ color: 'var(--text-muted)' }}>Escalation: {thread.escalation}</div>
                </div>
              ))}
            </div>
          </StudioPanel>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <StudioPanel title="Script and Story Panel" subtitle="Draft trajectory, scene objectives, character tracking, and dialogue shape.">
            <div className="space-y-3">
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Version History</div>
                <div className="text-sm mt-1" style={{ color: 'var(--text-primary)' }}>
                  {identity.title} / {identity.productionMode} cut / {identity.stage.toLowerCase()} pass
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Scene Breakdown</div>
                  <div className="text-xs mt-2 space-y-1" style={{ color: 'var(--text-secondary)' }}>
                    {(sourceProject?.source_stats?.scene_count || 0) > 0
                      ? Array.from({ length: sourceProject?.source_stats?.scene_count || 0 }).slice(0, 3).map((_, index) => (
                        <div key={index}>Scene {index + 1}: objective stays tied to tone, blocking, and payoff.</div>
                      ))
                      : <div>Scene objectives will populate after script ingest.</div>}
                  </div>
                </div>
                <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Dialogue Notes</div>
                  <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                    Preserve subtext and pacing by holding exposition off-screen and letting tension ride the blocking instead of dialogue density.
                  </div>
                </div>
              </div>
            </div>
          </StudioPanel>

          <StudioPanel title="Visual Development Panel" subtitle="Shot list, storyboards, cinematography plan, and tone references.">
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {queueRows.slice(0, 5).map((row) => (
                  <div key={row.renderId} className="text-xs px-2 py-1 rounded-full" style={{ background: 'rgba(168,85,247,0.1)', color: 'var(--accent-purple)', border: '1px solid rgba(168,85,247,0.18)' }}>
                    {row.shotId} • {row.previewLabel}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Coverage Plan</div>
                  <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                    Coverage favors motivated wides for geography, then moves into selective close coverage when the character arc turns.
                  </div>
                </div>
                <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Lighting and Visual Motif</div>
                  <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                    {identity.influences.join(' • ')} anchor the motif while preserving continuity across alternates.
                  </div>
                </div>
              </div>
            </div>
          </StudioPanel>

          <StudioPanel title="Editing and Post Panel" subtitle="Pacing, transitions, sound design, VFX, and color strategy.">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Editorial Rhythm</div>
                <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                  The current cut wants longer breath before reveals, then sharper exit cuts so pacing feels deliberate rather than stalled.
                </div>
              </div>
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Diegetic / Non-diegetic Sound</div>
                <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                  Lead with diegetic texture on entries, then let the non-diegetic lift bridge scene transitions and emotional payoff.
                </div>
              </div>
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>VFX Planning</div>
                <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                  Keep VFX invisible to the cut: prioritize extensions that support blocking and atmosphere, not spectacle drift.
                </div>
              </div>
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Color Grade Concept</div>
                <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                  Push controlled contrast and selective chroma so the visual motif stays cinematic without breaking continuity.
                </div>
              </div>
            </div>
          </StudioPanel>

          <StudioPanel title="Marketing and Release Panel" subtitle="Audience targeting, trailer concepts, festival strategy, and distribution.">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Audience Targeting</div>
                <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>{identity.audience}</div>
              </div>
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Trailer Concept</div>
                <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                  Cut a trailer around the visual motif, the scene objective, and the turn in the character arc before revealing plot mechanics.
                </div>
              </div>
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Festival Strategy</div>
                <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>{identity.festivalViability}</div>
              </div>
              <div className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Distribution Plan</div>
                <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                  {workspaceState.productionMode === 'commercial' ? 'Aim for broad platform launch with campaign-friendly key art.' : 'Prioritize festival-to-platform path with a curated trailer and critic-facing rollout.'}
                </div>
              </div>
            </div>
          </StudioPanel>
        </div>

        <div className="grid grid-cols-[1.1fr_0.9fr] gap-4">
          <StudioPanel title="Memory and Learning System" subtitle="Project memory, continuity, taste profile, and lessons learned.">
            <div className="grid grid-cols-2 gap-3">
              {memory.map((entry) => (
                <div key={entry.id} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{entry.label}</div>
                  <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>{entry.detail}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-3 text-xs" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}>
              <div className="font-medium" style={{ color: 'var(--accent)' }}>Agent Memory</div>
              <div>• Tone: noir</div>
              <div>• Scenes: 1 (Detective Office)</div>
              <div>• Camera: cinematic wide</div>
              <div className="mt-2"><a href={`${STUDIO_API_BASE}/docs`} target="_blank" className="underline" rel="noreferrer">Full API →</a></div>
            </div>
          </StudioPanel>

          <StudioPanel title="Reflection Layer" subtitle="Distilled notes on what worked, what failed, and where redundancy was removed.">
            <div className="space-y-3">
              {reflections.map((reflection) => (
                <div key={reflection.id} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{reflection.title}</div>
                  <div className="text-xs mt-2 space-y-1" style={{ color: 'var(--text-secondary)' }}>
                    <div><strong>Worked:</strong> {reflection.worked}</div>
                    <div><strong>Failed:</strong> {reflection.failed}</div>
                    <div><strong>Redundant:</strong> {reflection.redundant}</div>
                    <div><strong>Change:</strong> {reflection.change}</div>
                    <div><strong>Improvement:</strong> {reflection.improvement}</div>
                  </div>
                </div>
              ))}
            </div>
          </StudioPanel>
        </div>

        <div className="grid grid-cols-[0.95fr_1.05fr] gap-4">
          <StudioPanel title="Evaluation Framework" subtitle="Role-based scoring for usefulness, novelty, alignment, and learning velocity.">
            <div className="space-y-2">
              {agents.map((agent) => (
                <div key={agent.id} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{agent.role}</div>
                    <div className="text-xs" style={{ color: 'var(--text-muted)' }}>Novelty {agent.evaluation.novelty}</div>
                  </div>
                  <div className="grid grid-cols-5 gap-2 mt-2">
                    {Object.entries(agent.evaluation).map(([label, value]) => (
                      <div key={label} className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
                        <div className="text-[10px] uppercase" style={{ color: 'var(--text-muted)' }}>{label}</div>
                        <div className="text-xs mt-1" style={{ color: 'var(--text-primary)' }}>{value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </StudioPanel>

          <StudioPanel title="Studio Leadership Notes" subtitle="Distilled notes become memory, sharpen approvals, and reduce repeated feedback." data-testid="execution-timeline-panel">
            <div className="space-y-3">
              <textarea
                value={leadershipInput}
                onChange={(event) => setLeadershipInput(event.target.value)}
                rows={4}
                placeholder="Lock a note about tone, pacing, blocking, continuity, market fit, or production feasibility."
                className="w-full rounded-xl p-3 text-sm"
                style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', color: 'var(--text-primary)', outline: 'none' }}
              />
              <button type="button" className="btn-primary text-xs px-3 py-1.5 inline-flex items-center gap-1" onClick={saveLeadershipNote} disabled={!leadershipInput.trim() || loading}>
                <Save size={12} />
                Save Leadership Note
              </button>
              <div className="space-y-2">
                {workspaceState.leadershipNotes.map((note) => (
                  <div key={note.id} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                    <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{note.text}</div>
                    <div className="text-[11px] mt-2" style={{ color: 'var(--text-muted)' }}>{new Date(note.createdAt).toLocaleString()}</div>
                  </div>
                ))}
              </div>
              <CoDirectorInspectionPanel project={sourceProject ?? null} />
              <ExecutionSummaryInspectionPanel project={sourceProject ?? null} />
            </div>
          </StudioPanel>
        </div>

        <StudioPanel title="Operational View" subtitle="Provider pressure, render queue, and approval-safe execution.">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              {providers.map((provider) => (
                <div key={provider.id} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{provider.name}</div>
                    <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{provider.jobs} jobs</div>
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{provider.instance}</div>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              {queueRows.slice(0, 5).map((row) => (
              <div key={row.renderId} className="rounded-xl p-3" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }} data-testid="render-status-card">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{row.shotId}</div>
                    <div className="text-xs" style={{ color: 'var(--text-muted)' }}>{row.status}</div>
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                    {row.previewLabel} • {row.providerName} • {row.etaLabel}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </StudioPanel>
      </div>
    </StudioShell>
  )
}

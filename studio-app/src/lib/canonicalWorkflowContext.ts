import type { CanonicalWorkflowRun, CanonicalWorkflowStatus } from './canonicalWorkflowApi'

type AnyRecord = Record<string, unknown>

export type CanonicalSceneContext = {
  scriptId: string
  sequenceId: string
  beatIds: string[]
}

export type CanonicalWorkflowAction =
  | 'begin'
  | 'generate_previs'
  | 'approve_previs'
  | 'create_package'
  | 'render'
  | 'polling'
  | 'retry_render'
  | 'sync_screening'
  | 'approve_screening'
  | 'analyze_editorial'
  | 'choose_editorial_decision'
  | 'update_cut'
  | 'approve_cut'
  | 'create_revision'
  | 'render_revision'
  | 'revision_polling'
  | 'retry_revision'
  | 'complete'

function record(value: unknown): AnyRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as AnyRecord
    : null
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

export function extractCanonicalSceneContext(
  project: { execution_summary?: unknown } | null | undefined,
  sceneId: string,
): CanonicalSceneContext {
  const summary = record(project?.execution_summary)
  const scenes = Array.isArray(summary?.scenes) ? summary.scenes : []
  const scene = scenes.map(record).find((row) => text(row?.scene_id) === sceneId.trim())
  const beats = Array.isArray(scene?.beats) ? scene.beats : []
  return {
    scriptId: text(scene?.script_id) || text(summary?.script_id),
    sequenceId: text(scene?.sequence_id),
    beatIds: beats
      .map(record)
      .map((beat) => text(beat?.beat_id))
      .filter(Boolean),
  }
}

export function workflowArtifactIds(run: CanonicalWorkflowRun, key: string, idKey: string): string[] {
  const value = run.data.artifacts[key]
  if (!Array.isArray(value)) return []
  return value
    .map(record)
    .map((row) => text(row?.[idKey]))
    .filter(Boolean)
}

export function workflowIdentifierList(run: CanonicalWorkflowRun, key: string): string[] {
  const value = run.data.identifiers[key]
  return Array.isArray(value) ? value.map(text).filter(Boolean) : []
}

export function isRevisionSubmitted(run: CanonicalWorkflowRun): boolean {
  const revision = record(run.data.artifacts.revision)
  return text(revision?.status) === 'submitted'
}

export function nextCanonicalWorkflowAction(
  status: CanonicalWorkflowStatus | null,
  surface: 'previs' | 'screening',
  revisionSubmitted = false,
): CanonicalWorkflowAction {
  if (!status) return 'begin'
  const actions: Record<CanonicalWorkflowStatus, CanonicalWorkflowAction> = {
    blueprint_approved: 'generate_previs',
    previs_generated: 'approve_previs',
    previs_approved: 'create_package',
    package_ready: 'render',
    render_queued: 'polling',
    render_completed: 'sync_screening',
    render_failed: 'retry_render',
    screening_ready: surface === 'screening' ? 'approve_screening' : 'complete',
    screening_approved: surface === 'screening' ? 'analyze_editorial' : 'complete',
    editorial_analyzed: surface === 'screening' ? 'choose_editorial_decision' : 'complete',
    editorial_decided: surface === 'screening' ? 'update_cut' : 'complete',
    cut_updated: surface === 'screening' ? 'approve_cut' : 'complete',
    cut_approved: surface === 'screening' ? 'create_revision' : 'complete',
    revision_pending: surface === 'screening'
      ? revisionSubmitted ? 'revision_polling' : 'render_revision'
      : 'complete',
    revision_completed: 'complete',
    revision_failed: surface === 'screening' ? 'retry_revision' : 'complete',
  }
  return actions[status]
}

export function isCanonicalPollingStatus(run: CanonicalWorkflowRun | null): boolean {
  return run?.status === 'render_queued'
    || (run?.status === 'revision_pending' && isRevisionSubmitted(run))
}

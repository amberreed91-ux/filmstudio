import type { StudioProject } from '../lib/studioApi'
import { extractExecutionSummaryInspection, resolveRenderSource } from '../lib/executionSummaryInspection'

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


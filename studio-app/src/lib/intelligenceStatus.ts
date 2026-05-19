import type { ContinuityIssue, FrameAnalysis, StyleDriftIssue } from './studioApi'
import { continuityIssueTouchesAsset } from './continuityIntelligence'

/** Section titles shown across Study Room, Previs, Screening, Crew Ops */
export const INTELLIGENCE_LABELS = {
  visualEvidence: 'Visual Evidence',
  keyframes: 'Keyframes',
  frameAnalysis: 'Frame Analysis',
  embeddings: 'Visual Embeddings',
  semanticMemory: 'Semantic Memory',
  semanticSearch: 'Semantic Search',
  continuityNotes: 'Continuity Notes',
  directorSignature: 'Director Signature',
  styleDrift: 'Style Drift',
} as const

/** Unified pipeline / coverage states (user-facing) */
export type IntelligencePipelineState =
  | 'Ready'
  | 'Needs keyframes'
  | 'Needs frame analysis'
  | 'Needs embeddings'
  | 'Needs memory build'
  | 'Not enough evidence yet'

export const INTELLIGENCE_EMPTY = {
  uploadReferenceVideo: 'Upload a reference video to start building visual evidence.',
  extractKeyframesFirst: 'Extract keyframes before frame analysis.',
  runAnalysisBeforeMemory: 'Run frame analysis before semantic memory.',
  styleDriftMinAnalyzedFrames: 'Need at least 5 analyzed frames to detect style drift.',
  noContinuityIssues: 'No continuity issues detected yet.',
  continuityNeedsVisualPipeline: 'Not enough visual evidence yet. Extract keyframes and run frame analysis.',
  noStyleDriftRows: 'No style drift issues detected for this scope yet.',
  projectFindingsSceneNeedsLinks:
    'Project-level findings available. Scene-specific mapping needs more linked metadata.',
  semanticSearchHint: 'Search semantic memory once cinematic memory has been built.',
} as const

const NEXT = {
  keyframes: 'Extract keyframes to capture visual evidence from this asset.',
  frameAnalysis: 'Run frame analysis on keyframes to describe lighting, mood, and composition.',
  embeddings: 'Generate visual embeddings after frame analysis so frames can be matched and retrieved.',
  memory: 'Build cinematic memory so semantic search can surface related moments.',
  continuity: 'Run continuity analysis from Study Room when you have analyzed frames across assets.',
  directorSignature: 'Build the director signature from analyzed frames to anchor style comparisons.',
  styleDrift: 'Run style drift detection when a director signature exists and enough frames are analyzed.',
  styleDriftFrames: INTELLIGENCE_EMPTY.styleDriftMinAnalyzedFrames,
  allSet: 'This asset is ready for memory search and style checks. Review continuity and drift panels for advisories.',
} as const

export function countCompleteAnalyses(analyses: FrameAnalysis[]): number {
  return analyses.filter((a) => (a.status || '').toLowerCase() === 'complete').length
}

export function countCompleteEmbeddingsForAsset(
  embeddings: Array<{ asset_id: string; status: string }>,
  assetId: string,
): number {
  return embeddings.filter((e) => e.asset_id === assetId && (e.status || '').toLowerCase() === 'complete').length
}

export function countMemoryRecordsForAsset(
  records: Array<{ asset_id: string }>,
  assetId: string,
): number {
  return records.filter((r) => r.asset_id === assetId).length
}

export function countContinuityForAsset(issues: ContinuityIssue[], assetId: string): number {
  return issues.filter((i) => continuityIssueTouchesAsset(i, assetId)).length
}

export function countStyleDriftForAsset(issues: StyleDriftIssue[], assetId: string): number {
  return issues.filter((i) => i.asset_id === assetId).length
}

function stateForKeyframes(count: number): IntelligencePipelineState {
  return count > 0 ? 'Ready' : 'Needs keyframes'
}

function stateForAnalyses(keyframeCount: number, completeAnalysisCount: number): IntelligencePipelineState {
  if (completeAnalysisCount > 0) return 'Ready'
  if (keyframeCount > 0) return 'Needs frame analysis'
  return 'Needs keyframes'
}

function stateForEmbeddings(completeAnalysisCount: number, embeddingCount: number): IntelligencePipelineState {
  if (embeddingCount > 0) return 'Ready'
  if (completeAnalysisCount > 0) return 'Needs embeddings'
  if (completeAnalysisCount === 0) return 'Needs frame analysis'
  return 'Needs keyframes'
}

function stateForMemory(embeddingCount: number, memoryCount: number): IntelligencePipelineState {
  if (memoryCount > 0) return 'Ready'
  if (embeddingCount > 0) return 'Needs memory build'
  if (embeddingCount === 0) return 'Needs embeddings'
  return 'Needs frame analysis'
}

function stateForContinuitySignals(completeAnalysisCount: number): IntelligencePipelineState {
  return completeAnalysisCount > 0 ? 'Ready' : 'Not enough evidence yet'
}

function stateForStyleDrift(analyzedCompleteCount: number): IntelligencePipelineState {
  return analyzedCompleteCount < 5 ? 'Not enough evidence yet' : 'Ready'
}

function stateForDirectorSignature(
  hasSignature: boolean,
  analyzedCompleteCount: number,
): IntelligencePipelineState {
  if (hasSignature) return 'Ready'
  if (analyzedCompleteCount >= 3) return 'Not enough evidence yet'
  return 'Not enough evidence yet'
}

export type AssetIntelligenceStatusRow = {
  label: string
  count: number
  state: IntelligencePipelineState
}

export function buildAssetIntelligenceCard(input: {
  keyframeCount: number
  analyses: FrameAnalysis[]
  embeddingsCompleteCount: number
  memoryRecordCount: number
  continuityIssueCount: number
  styleDriftCount: number
  projectHasDirectorSignature: boolean
}): { rows: AssetIntelligenceStatusRow[]; nextAction: string } {
  const completeAnalyses = countCompleteAnalyses(input.analyses)
  const k = input.keyframeCount
  const emb = input.embeddingsCompleteCount
  const mem = input.memoryRecordCount

  const rows: AssetIntelligenceStatusRow[] = [
    { label: INTELLIGENCE_LABELS.visualEvidence, count: 1, state: 'Ready' },
    { label: INTELLIGENCE_LABELS.keyframes, count: k, state: stateForKeyframes(k) },
    { label: INTELLIGENCE_LABELS.frameAnalysis, count: completeAnalyses, state: stateForAnalyses(k, completeAnalyses) },
    { label: INTELLIGENCE_LABELS.embeddings, count: emb, state: stateForEmbeddings(completeAnalyses, emb) },
    { label: INTELLIGENCE_LABELS.semanticMemory, count: mem, state: stateForMemory(emb, mem) },
    {
      label: INTELLIGENCE_LABELS.continuityNotes,
      count: input.continuityIssueCount,
      state: stateForContinuitySignals(completeAnalyses),
    },
    {
      label: INTELLIGENCE_LABELS.directorSignature,
      count: input.projectHasDirectorSignature ? 1 : 0,
      state: stateForDirectorSignature(input.projectHasDirectorSignature, completeAnalyses),
    },
    {
      label: INTELLIGENCE_LABELS.styleDrift,
      count: input.styleDriftCount,
      state: stateForStyleDrift(completeAnalyses),
    },
  ]

  let nextAction: string = NEXT.allSet
  if (k === 0) nextAction = NEXT.keyframes
  else if (completeAnalyses === 0) nextAction = NEXT.frameAnalysis
  else if (emb === 0) nextAction = NEXT.embeddings
  else if (mem === 0) nextAction = NEXT.memory
  else if (completeAnalyses < 5) nextAction = NEXT.styleDriftFrames
  else if (!input.projectHasDirectorSignature && completeAnalyses >= 3) nextAction = NEXT.directorSignature

  return { rows, nextAction }
}

/** Map API / internal errors to calm copy (never raw 404 strings in UI). */
export function humanizeIntelligenceLoadError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('not found') || m.includes('404')) {
    return 'This project is not available or intelligence data has not been loaded yet.'
  }
  return 'Intelligence data could not be loaded. Try again after selecting a valid project.'
}

// ============================================================================
// PREVIS INTELLIGENCE SUMMARY
// ============================================================================
export type PrevisIntelligenceSummary = {
  matchedVisualSource: string | null
  relatedReferencesCount: number
  continuityWarningsCount: number
  directorSignatureAlignment: 'aligned' | 'unknown' | 'needs_more_data'
  styleDriftWarningsCount: number
  nextAction: string
}

export function buildPrevisIntelligenceSummary(input: {
  sceneId: string
  matchedSourceName?: string
  relatedMemoryCount: number
  sceneContinuityIssueCount: number
  projectHasDirectorSignature: boolean
  completeAnalysisCount: number
  sceneStyleDriftCount: number
}): PrevisIntelligenceSummary {
  const alignment: PrevisIntelligenceSummary['directorSignatureAlignment'] =
    input.projectHasDirectorSignature ? 'aligned' : input.completeAnalysisCount >= 3 ? 'unknown' : 'needs_more_data'

  let nextAction = 'Visual analysis ready for review.'
  if (!input.projectHasDirectorSignature && input.completeAnalysisCount < 3) {
    nextAction = 'Build director signature from at least 3 analyzed frames to enable alignment checks.'
  } else if (input.relatedMemoryCount === 0) {
    nextAction = 'No related reference found yet. Link relevant source material or build cinematic memory.'
  } else if (input.sceneContinuityIssueCount > 0) {
    nextAction = 'Review continuity warnings below.'
  } else if (input.sceneStyleDriftCount > 0) {
    nextAction = 'Review style drift warnings below.'
  }

  return {
    matchedVisualSource: input.matchedSourceName || null,
    relatedReferencesCount: input.relatedMemoryCount,
    continuityWarningsCount: input.sceneContinuityIssueCount,
    directorSignatureAlignment: alignment,
    styleDriftWarningsCount: input.sceneStyleDriftCount,
    nextAction,
  }
}

// ============================================================================
// SCREENING ROOM INTELLIGENCE SUMMARY
// ============================================================================
export type ScreeningIntelligenceSummary = {
  continuityWarningsCount: number
  styleDriftWarningsCount: number
  relatedMemoryReferencesCount: number
  reviewState: 'ready' | 'has_warnings' | 'not_enough_data'
  packageState: 'ready' | 'not_packaged'
  advisories: string[]
}

export function buildScreeningIntelligenceSummary(input: {
  sceneId: string
  sceneContinuityIssueCount: number
  sceneStyleDriftCount: number
  relatedMemoryCount: number
  isPackaged: boolean
}): ScreeningIntelligenceSummary {
  const advisories: string[] = []

  if (input.sceneContinuityIssueCount > 0) {
    advisories.push(`${input.sceneContinuityIssueCount} continuity warning${input.sceneContinuityIssueCount > 1 ? 's' : ''}`)
  }
  if (input.sceneStyleDriftCount > 0) {
    advisories.push(`${input.sceneStyleDriftCount} style drift warning${input.sceneStyleDriftCount > 1 ? 's' : ''}`)
  }

  const reviewState: ScreeningIntelligenceSummary['reviewState'] =
    input.sceneContinuityIssueCount > 0 || input.sceneStyleDriftCount > 0 ? 'has_warnings' : 'ready'

  return {
    continuityWarningsCount: input.sceneContinuityIssueCount,
    styleDriftWarningsCount: input.sceneStyleDriftCount,
    relatedMemoryReferencesCount: input.relatedMemoryCount,
    reviewState,
    packageState: input.isPackaged ? 'ready' : 'not_packaged',
    advisories,
  }
}

// ============================================================================
// CREW OPS INTELLIGENCE DASHBOARD
// ============================================================================
export type CrewOpsDashboard = {
  uploadedAssetCount: number
  totalKeyframesExtracted: number
  totalAnalysesCompleted: number
  totalEmbeddingsGenerated: number
  totalMemoryRecords: number
  projectContinuityIssueCount: number
  projectStyleDriftIssueCount: number
  directorSignatureExists: boolean
  directorSignatureConfidence: number
  overallReadiness: 'ready' | 'in_progress' | 'needs_work'
}

export function buildCrewOpsDashboard(input: {
  assetCount: number
  totalKeyframes: number
  completedAnalysesCount: number
  totalEmbeddings: number
  memoryRecordCount: number
  continuityIssueCount: number
  styleDriftIssueCount: number
  hasDirectorSignature: boolean
  directorSignatureConfidence?: number
}): CrewOpsDashboard {
  const readiness: CrewOpsDashboard['overallReadiness'] =
    input.totalEmbeddings > 0 && input.memoryRecordCount > 0
      ? 'ready'
      : input.totalKeyframes > 0 || input.completedAnalysesCount > 0
        ? 'in_progress'
        : 'needs_work'

  return {
    uploadedAssetCount: input.assetCount,
    totalKeyframesExtracted: input.totalKeyframes,
    totalAnalysesCompleted: input.completedAnalysesCount,
    totalEmbeddingsGenerated: input.totalEmbeddings,
    totalMemoryRecords: input.memoryRecordCount,
    projectContinuityIssueCount: input.continuityIssueCount,
    projectStyleDriftIssueCount: input.styleDriftIssueCount,
    directorSignatureExists: input.hasDirectorSignature,
    directorSignatureConfidence: input.directorSignatureConfidence || 0,
    overallReadiness: readiness,
  }
}

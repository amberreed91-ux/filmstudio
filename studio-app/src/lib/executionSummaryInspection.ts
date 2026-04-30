import type { StudioProject } from './studioApi'

export type RenderBehavior = 'stable' | 'retry_heavy' | 'in_progress' | 'stuck' | 'unknown'

export type ExecutionSummaryInspectionSnapshot = {
  providerName: string
  lifecycleState: string
  productionSignal: ProductionSignalSnapshot | null
  sceneIntent: SceneIntentSnapshot | null
  intentSignal: IntentSignalSnapshot | null
  intentOutputSignal: IntentOutputSignalSnapshot | null
  intentOutputRelation: IntentOutputRelationSnapshot | null
  providerStatus: string | null
  hasOutputArtifacts: boolean
  hasError: boolean
  latestUpdatedAt: string | null
  renderBehavior: RenderBehavior | null
  interventionSuggestion: InterventionSuggestionSnapshot | null
  recurringPattern: RecurringPatternSnapshot | null
  memoryAdvisoryProjection: MemoryAdvisoryProjectionSnapshot | null
  memorySnapshotSummary: MemorySnapshotSummarySnapshot | null
  memoryStateRollup: MemoryStateRollupSnapshot | null
  memoryConsistency: MemoryConsistencySnapshot | null
  memoryCategoryPresence: MemoryCategoryPresenceSnapshot | null
  coDirectorMemoryVisibility: CoDirectorMemoryVisibilitySnapshot | null
  coDirectorMemoryAdvisory: CoDirectorMemoryAdvisorySnapshot | null
  coDirectorMemoryAuthorityBoundary: CoDirectorMemoryAuthorityBoundarySnapshot | null
  coDirectorVisualFeed?: CoDirectorVisualFeedSnapshot | null
  visualReferences?: VisualReferenceSnapshot[] | null
  visualReferenceIndexes?: VisualReferenceIndexesSnapshot | null
  visualReferenceSummary?: VisualReferenceSummarySnapshot | null
  visualPatternSummary?: VisualPatternSummarySnapshot | null
  sceneVisualIdentity?: SceneVisualIdentitySnapshot | null
  visualConsistency?: VisualConsistencySnapshot | null
  visualTension?: VisualTensionSnapshot | null
  frameMetadata?: FrameMetadataSnapshot[] | null
  frameStats?: FrameStatsSnapshot | null
  frameAnalysisSnapshot?: FrameAnalysisSnapshot | null
  sceneVisualLinks?: SceneVisualLinksSnapshot | null
  linkCompleteness?: LinkCompletenessSnapshot | null
  shotCandidates?: ShotCandidateSnapshot[] | null
  shotCoverage?: ShotCoverageSnapshot | null
  shotPlanBundle?: ShotPlanBundleSnapshot | null
  shotIntent?: ShotIntentSnapshot | null
  shotVariety?: ShotVarietySnapshot | null
  sceneCoverage?: SceneCoverageSnapshot | null
  shotPlanningSummary?: ShotPlanningSummarySnapshot | null
  shotAdvisoryNote?: ShotAdvisoryNoteSnapshot | null
  sceneSequence?: SceneSequenceSnapshot | null
  sceneAssembly?: SceneAssemblySnapshot | null
  sequenceStatus?: SequenceStatusSnapshot | null
  sceneContinuityCheck?: SceneContinuityCheckSnapshot | null
  scenePlaybackStatus?: ScenePlaybackStatusSnapshot | null
  coDirectorVisualObservation?: CoDirectorVisualObservationSnapshot | null
  coDirectorShotObservation?: CoDirectorShotObservationSnapshot | null
  coDirectorObservationSummary?: CoDirectorObservationSummarySnapshot | null
  coDirectorObservationContract?: CoDirectorObservationContractSnapshot | null
  outputInfluenceGuardV2?: OutputInfluenceGuardV2Snapshot | null
  visualDecisionBoundary?: VisualDecisionBoundarySnapshot | null
  shotExecutionLock?: ShotExecutionLockSnapshot | null
  boundaryAudit?: BoundaryAuditSnapshot | null
  studioSafetyState?: StudioSafetyStateSnapshot | null
  promptInfluenceGateV1?: PromptInfluenceGateV1Snapshot | null
  visualPromptTokens?: string[] | null
  shotPromptTokens?: string[] | null
  promptEnvelope?: PromptEnvelopeSnapshot | null
  promptSafetyContract?: PromptSafetyContractSnapshot | null
  renderActivationGateV1?: RenderActivationGateV1Snapshot | null
  renderRequest?: RenderRequestSnapshot | null
  renderOutput?: RenderOutputSnapshot | null
  outputReview?: OutputReviewSnapshot | null
  outputEvaluation?: OutputEvaluationSnapshot | null
  retryGate?: RetryGateSnapshot | null
  executionSnapshot?: ExecutionSnapshotSnapshot | null
  iterationRecord?: IterationRecordSnapshot | null
  takeHistory?: TakeHistorySnapshot | null
  takeArtifacts?: TakeArtifactSnapshot[] | null
  retrySnapshot?: RetrySnapshotSnapshot | null
  takeComparison?: TakeComparisonSnapshot | null
  takeComparisonV2?: TakeComparisonV2Snapshot | null
  takePreferenceContract?: TakePreferenceContractSnapshot | null
  takeAdvisoryNote?: TakeAdvisoryNoteSnapshot | null
  outputReviewMatrix?: OutputReviewMatrixRowSnapshot[] | null
  loopReadiness?: LoopReadinessSnapshot | null
  nextTakePreview?: NextTakePreviewSnapshot | null
  loopConstraint?: LoopConstraintSnapshot | null
  loopAdvisory?: LoopAdvisorySnapshot | null
  loopContract?: LoopContractSnapshot | null
  loopExecutionPlan?: LoopExecutionPlanSnapshot | null
  simulatedIteration?: SimulatedIterationSnapshot | null
  simulatedOutput?: SimulatedOutputSnapshot | null
  loopResultSnapshot?: LoopResultSnapshot | null
  loopExecutionContract?: LoopExecutionContractSnapshot | null
  executionPermission?: ExecutionPermissionSnapshot | null
  executionRequest?: ExecutionRequestSnapshot | null
  executionStatus?: ExecutionStatusSnapshot | null
  executionResult?: ExecutionResultSnapshot | null
  providerPayload?: ProviderPayloadSnapshot | null
  providerPayloadV2?: ProviderPayloadV2Snapshot | null
  handoffEnvelope?: HandoffEnvelopeSnapshot | null
  handoffAudit?: HandoffAuditSnapshot | null
  executionResultV2?: ExecutionResultV2Snapshot | null
  mockRenderOutput?: MockRenderOutputSnapshot
  executionPathTrace?: ExecutionPathTraceSnapshot
  localRenderOutput?: LocalRenderOutputSnapshot | null
  localArtifactLog?: LocalArtifactLogSnapshot | null
  outputSync?: OutputSyncSnapshot | null
  executionMonitor?: ExecutionMonitorSnapshot | null
  providerConfigSnapshot?: ProviderConfigSnapshot | null
  providerCredentialState?: ProviderCredentialStateSnapshot | null
  providerSelectionState?: ProviderSelectionStateSnapshot | null
  providerReadinessSummary?: ProviderReadinessSummarySnapshot | null
  providerCapability?: ProviderCapabilitySnapshot | null
  providerControlContract?: ProviderControlContractSnapshot | null
  providerSafetyContract?: ProviderSafetyContractSnapshot | null
  providerAdapterStatus?: ProviderAdapterStatusSnapshot | null
  providerAdapterReadinessGate?: ProviderAdapterReadinessGateSnapshot | null
  executionContract?: ExecutionContractSnapshot | null
  executionUnlockState?: ExecutionUnlockStateSnapshot | null
  executionEligibility?: ExecutionEligibilitySnapshot | null
  executionRequestEnvelope?: ExecutionRequestEnvelopeSnapshot | null
  requestSchemaValidation?: RequestSchemaValidationSnapshot | null
  providerValidation?: ProviderValidationSnapshot | null
  payloadSanitization?: PayloadSanitizationSnapshot | null
  shotQueue?: ShotQueueEntrySnapshot[] | null
  multiShotReadiness?: MultiShotReadinessSnapshot | null
  multiShotResults?: MultiShotResultSnapshot[] | null
  shotExecutionLedger?: ShotExecutionLedgerEntrySnapshot[] | null
  multiShotExecutionLedger?: MultiShotExecutionLedgerEntrySnapshot[] | null
  multiShotTakeArtifacts?: MultiShotTakeArtifactSnapshot[] | null
  sceneGenerationSummary?: SceneGenerationSummarySnapshot | null
  scenePlaybackPreview?: ScenePlaybackPreviewSnapshot | null
  multiShotExecutionContract?: MultiShotExecutionContractSnapshot | null
  validationInspection?: ValidationInspectionSnapshot
  previsSceneBoard?: PrevisSceneBoardEntrySnapshot[] | null
  previsBeatShotMap?: PrevisBeatShotMapEntrySnapshot[] | null
  previsContinuityMap?: PrevisContinuityMapEntrySnapshot[] | null
  previsAssetMap?: PrevisAssetMapEntrySnapshot[] | null
  previsContract?: PrevisContractSnapshot | null
}

export type InterventionSuggestionSnapshot = {
  level: 'advisory'
  message: string
  source: string
}

export type ProductionSignalSnapshot = {
  type: 'production_signal'
  message: string
}

export type SceneIntentSnapshot = {
  type: 'intent_label'
  label: string
}

export type IntentSignalSnapshot = {
  type: 'intent_presence'
  message: string
}

export type IntentOutputSignalSnapshot = {
  type: 'intent_output_presence'
  message: string
}

export type IntentOutputRelationSnapshot = {
  type: 'intent_output_relation'
  state: 'ready_for_review'
  message: string
}

export type RecurringPatternSnapshot = {
  type: 'provider_failure_pattern' | 'stuck_pattern'
  count: number
  providerName: string | null
  message: string
}

export type MemoryAdvisoryProjectionSnapshot = {
  status: string
  message: string
}

export type MemorySnapshotSummarySnapshot = {
  candidateCount: number
  recordCount: number
  aggregateCount: number
  advisoryStatus: string
  influenceMode: string
}

export type MemoryCategoryPresenceSnapshot = {
  characterPairs: boolean
  locations: boolean
  timeOfDay: boolean
}

export type MemoryStateRollupSnapshot = {
  status: 'available' | 'unavailable'
  candidateCount: number
  influenceMode: string
  advisoryStatus: 'available' | 'unavailable'
}

export type MemoryConsistencySnapshot = {
  isConsistent: boolean
  hasRequiredFields: boolean
  gateDisabled: boolean
  authorityNone: boolean
}

export type CoDirectorMemoryVisibilitySnapshot = {
  hasMemoryCandidates: boolean
  hasMemoryRecords: boolean
  hasMemoryAggregate: boolean
  influenceMode: string
  advisoryStatus: string
}

export type CoDirectorMemoryAdvisorySnapshot = {
  status: string
  message: string
}

export type CoDirectorMemoryAuthorityBoundarySnapshot = {
  authority: string
  memoryInfluence: string
  reason: string
}

export type CoDirectorVisualFeedSnapshot = {
  referenceSummary: VisualReferenceSummarySnapshot
  frameSnapshot: FrameAnalysisSnapshot
  linkage: LinkCompletenessSnapshot
  alignment: {
    state: string
    note: string
  }
  mode: 'read_only'
}

export type VisualReferenceSnapshot = {
  id: string
  type: string
  source: string
  label: string
  sceneId: string | null
}

export type VisualReferenceIndexesSnapshot = {
  byReferenceId: Record<string, VisualReferenceSnapshot>
  bySceneId: Record<string, string[]>
  byType: Record<string, string[]>
}

export type VisualReferenceSummarySnapshot = {
  referenceCount: number
  linkedSceneCount: number
  typeCount: number
}

export type VisualPatternSummarySnapshot = {
  dominantTypes: string[]
  typeCounts: Record<string, number>
}

export type SceneVisualIdentitySnapshot = Record<string, string[]>

export type VisualConsistencySnapshot = {
  consistent: boolean
  varianceLevel: 'none' | 'low' | 'high'
}

export type VisualTensionSnapshot = {
  tensionScenes: string[]
}

export type FrameMetadataSnapshot = {
  frameId: string
  artifactId: string
  timestamp: number
}

export type FrameStatsSnapshot = {
  frameCount: number
  artifactCount: number
}

export type FrameAnalysisSnapshot = {
  frameMetadata: FrameMetadataSnapshot[]
  frameStats: FrameStatsSnapshot
}

export type SceneVisualLinksSnapshot = Record<string, string[]>

export type LinkCompletenessSnapshot = {
  linkedScenes: number
  totalScenes: number
}

export type ShotCandidateSnapshot = {
  sceneId: string
  shotId: string
  sourceRefs: string[]
}

export type ShotCoverageSnapshot = Record<string, { candidateCount: number }>

export type ShotPlanBundleSnapshot = {
  shotCandidates: ShotCandidateSnapshot[]
  shotCoverage: ShotCoverageSnapshot
  influenceMode: string
}

export type ShotIntentSnapshot = Record<string, 'dialogue_focus' | 'establishing' | 'general'>

export type ShotVarietySnapshot = {
  diversity: 'none' | 'low' | 'balanced'
}

export type SceneCoverageSnapshot = Record<string, 'covered' | 'partial'>

export type ShotPlanningSummarySnapshot = {
  coveredScenes: number
  totalScenes: number
  variety: 'none' | 'low' | 'balanced'
}

export type ShotAdvisoryNoteSnapshot = {
  note: string
}

export type SceneSequenceSnapshot = {
  sceneId: string
  shots: string[]
}[]

export type SceneAssemblySnapshot = {
  sceneCount: number
  assembled: boolean
  shotsAvailable: number
}

export type SequenceStatusSnapshot = {
  scenes: number
  shots: number
  assembled: boolean
}

export type SceneContinuityCheckSnapshot = {
  visualConsistency: 'none' | 'low' | 'high'
  shotVariety: 'none' | 'low' | 'balanced'
  assembled: boolean
  status: 'ready' | 'incomplete'
}

export type ScenePlaybackStatusSnapshot = {
  playbackReady: boolean
  sceneCount: number
  shotsAvailable: number
  status: 'ready' | 'incomplete'
}

export type CoDirectorVisualObservationSnapshot = {
  note: string
}

export type CoDirectorShotObservationSnapshot = {
  note: string
}

export type CoDirectorObservationSummarySnapshot = {
  notes: string[]
}

export type CoDirectorObservationContractSnapshot = {
  mode: 'read_only'
  authority: 'none'
  influence: 'disabled'
}

export type OutputInfluenceGuardV2Snapshot = {
  outputInfluence: boolean
  reason: string
}

export type VisualDecisionBoundarySnapshot = {
  visualDecisionAuthority: string
  reason: string
}

export type ShotExecutionLockSnapshot = {
  shotExecutionEnabled: boolean
  reason: string
}

export type BoundaryAuditSnapshot = {
  memorySafe: boolean
  visualSafe: boolean
  shotSafe: boolean
  renderSafe: boolean
  coDirectorSafe: boolean
  overallSafe: boolean
}

export type StudioSafetyStateSnapshot = {
  studioState: 'safe_for_control_phase' | 'not_ready'
}

export type PromptInfluenceGateV1Snapshot = {
  promptInfluenceEnabled: boolean
  scope: 'advisory_only'
  reason: string
}

export type PromptEnvelopeSnapshot = {
  baseIntent: string
  visualTokens: string[]
  shotTokens: string[]
}

export type PromptSafetyContractSnapshot = {
  promptOverride: boolean
  structureLocked: boolean
  tokenInjectionOnly: boolean
  reason: string
}

export type RenderActivationGateV1Snapshot = {
  renderEnabled: boolean
  mode: 'single_shot'
  reason: string
}

export type RenderRequestSnapshot = {
  shotId: string
  sceneId: string
  prompt: PromptEnvelopeSnapshot
}

export type RenderOutputSnapshot = {
  renderId: string
  shotId: string
  status: 'pending'
  promptSnapshot: PromptEnvelopeSnapshot
}

export type OutputReviewSnapshot = {
  renderId: string
  alignment: string
  coverage: string
  status: 'pending'
}

export type OutputEvaluationSnapshot = {
  hasOutput: boolean
  validStructure: boolean
  renderIdPresent: boolean
  status: 'valid' | 'invalid' | 'none'
}

export type RetryGateSnapshot = {
  retryAllowed: boolean
  reason: string
}

export type ExecutionSnapshotSnapshot = {
  iteration: number
  maxIterations: number
  status: 'idle' | 'ready' | 'in_progress' | 'complete'
  renderAttempted: boolean
  retryAllowed: boolean
  finalized: boolean
}

export type IterationRecordSnapshot = {
  iteration: number
  status: string
  renderId: string | null
  coverage: string
  alignment: string
}

export type TakeHistorySnapshot = {
  takes: IterationRecordSnapshot[]
}

export type TakeArtifactSnapshot = {
  iteration: number
  renderId: string | null
  status: string
  filePath?: string | null
  url?: string | null
}

export type RetrySnapshotSnapshot = {
  allowed: boolean
  iteration: number
  status: string
}

export type TakeComparisonSnapshot = {
  bestTake: null
  comparisonReady: boolean
}

export type TakeComparisonV2Snapshot = {
  comparable: boolean
  differences: string[]
}

export type TakePreferenceContractSnapshot = {
  autoSelect: boolean
  authority: 'manual_only'
}

export type TakeAdvisoryNoteSnapshot = {
  note: string
}

export type OutputReviewMatrixRowSnapshot = {
  takeId: number
  alignment: string
  coverage: string
  validStructure: boolean
}

export type LoopReadinessSnapshot = {
  ready: boolean
  reason: string
}

export type NextTakePreviewSnapshot = {
  nextIteration: number
  willRetry: boolean
}

export type LoopConstraintSnapshot = {
  maxIterations: number
  remaining: number
}

export type LoopAdvisorySnapshot = {
  note: string
}

export type LoopContractSnapshot = {
  autoLoop: boolean
  executionMode: 'manual_only'
  reason: string
}

export type LoopExecutionPlanSnapshot = {
  execute: boolean
  nextIteration: number
  reason: string
}

export type SimulatedIterationSnapshot = {
  iteration: number
  status: string
}

export type SimulatedOutputSnapshot = {
  renderId: string | null
  status: 'pending' | 'simulated' | 'none'
}

export type LoopResultSnapshot = {
  iteration: number
  outputStatus: 'pending' | 'simulated' | 'none'
}

export type LoopExecutionContractSnapshot = {
  mode: 'safe_simulation'
  realExecution: boolean
  reason: string
}

export type ExecutionPermissionSnapshot = {
  allowed: boolean
  mode: 'blocked' | 'single_shot'
  reason: string
}

export type ExecutionRequestSnapshot = {
  enabled: boolean
  shotId: string | null
  prompt: PromptEnvelopeSnapshot | null
}

export type ExecutionStatusSnapshot = {
  state: 'idle' | 'ready' | 'blocked'
  reason: string
}

export type ExecutionResultSnapshot = {
  executed: boolean
  renderId: null
  status: 'not_executed'
}

export type ProviderPayloadSnapshot = {
  shotId: string | null
  prompt: PromptEnvelopeSnapshot | null
}

export type ProviderPayloadV2Snapshot = {
  provider: string
  shotId: string | null
  prompt: PromptEnvelopeSnapshot | null
}

export type HandoffEnvelopeSnapshot = {
  requestId: string
  provider: string
  enabled: boolean
}

export type HandoffAuditSnapshot = {
  requested: boolean
  allowed: boolean
  blockedReason: string
  timestamp: null
}

export type ExecutionResultV2Snapshot = {
  executed: boolean
  renderId: string | null
  status: 'success' | 'failed' | 'skipped' | 'not_executed'
  provider?: string | null
  meta?: ExecutionResultV2MetaSnapshot
}

export type ExecutionResultV2MetaSnapshot = {
  filePath: string | null
  url: string | null
}

export type MockRenderOutputSnapshot = {
  renderId: string | null
  status: string
  provider: string
  hasOutput: boolean
}

export type LocalRenderOutputSnapshot = {
  hasOutput: boolean
  renderId: string | null
  filePath: string | null
  artifactType: string | null
  status: string
}

export type LocalArtifactLogSnapshot = {
  executed: boolean
  shotId: string | null
  filePath: string | null
  timestamp: null
}

export type ExecutionPathTraceSnapshot = {
  intentPresent: boolean
  requestValid: boolean
  eligible: boolean
  blocked: boolean
}

export type OutputSyncSnapshot = {
  synced: boolean
  renderId: string | null
}

export type ExecutionMonitorSnapshot = {
  state: string
  result: string
}

export type ExecutionContractSnapshot = {
  mode: 'single_shot_only'
  autoExecution: boolean
  looping: boolean
  reason: string
}

export type ProviderConfigSnapshot = {
  defaultProvider: string
  enabledProviders: string[]
  qualityPriority: string
  realProvidersEnabled: boolean
}

export type ProviderCredentialStateSnapshot = {
  provider: string
  enabled: boolean
  credentialPresent: boolean
  credentialSource: 'none' | 'env' | 'config_present'
  reason: string
}

export type ProviderSelectionStateSnapshot = {
  requestedProvider: string | null
  selectedProvider: string
  allowed: boolean
  fallbackUsed: boolean
  reason: string
}

export type ProviderReadinessSummarySnapshot = {
  provider: string
  enabled: boolean
  credentialPresent: boolean
  canExecute: boolean
  reason: string
}

export type ProviderCapabilitySnapshot = {
  provider: string
  enabled: boolean
  networkRequired: boolean
  supportsRender: boolean
  supportsStreaming: boolean
  supportsSync: boolean
  supportsMultiShot: boolean
  requiresCredentials: boolean
}

export type ProviderControlContractSnapshot = {
  selectionMode: 'manual_only'
  autoExecution: boolean
  executionOnSelect: boolean
  reason: string
}

export type ProviderSafetyContractSnapshot = {
  realProviderExecutionEnabled: boolean
  reason: string
}

export type ProviderAdapterStatusSnapshot = {
  provider: string
  enabled: boolean
}

export type ProviderAdapterReadinessGateSnapshot = {
  ready: boolean
}

export type ExecutionUnlockStateSnapshot = {
  locked: boolean
}

export type ExecutionEligibilitySnapshot = {
  eligible: boolean
}

export type ExecutionRequestEnvelopeSnapshot = {
  request: string
}

export type RequestSchemaValidationSnapshot = {
  valid: boolean
}

export type ProviderValidationSnapshot = {
  valid: boolean
}

export type PayloadSanitizationSnapshot = {
  safe: boolean
}

export type ShotQueueEntrySnapshot = {
  shotId: string
  sceneId: string | null
  status: string
}

export type MultiShotReadinessSnapshot = {
  ready: number
}

export type MultiShotResultSnapshot = {
  shotId: string
  sceneId: string
  renderId: string
  status: string
  provider: string
}

export type ShotExecutionLedgerEntrySnapshot = {
  shotId: string
  sceneId: string | null
  status: string
  renderId: string | null
  filePath?: string | null
  url?: string | null
}

export type MultiShotExecutionLedgerEntrySnapshot = {
  shotId: string
  status: string
  renderId: string | null
}

export type MultiShotTakeArtifactSnapshot = {
  iteration: number
  shotId: string
  renderId: string
  status: string
}

export type SceneGenerationSummarySnapshot = {
  plannedShots: number
  completedShots: number
  provider: string
  status: 'complete' | 'partial' | 'not_started'
}

export type ScenePlaybackPreviewSnapshot = {
  available: boolean
  shotCount: number
  renderIds: string[]
  status: string
}

export type MultiShotExecutionContractSnapshot = {
  provider: 'mock_only'
  maxShotsPerRun: number
  realProvidersEnabled: boolean
  retriesEnabled: boolean
  asyncEnabled: boolean
  reason: string
}

export type ValidationInspectionSnapshot = {
  advisoryDisposition: string | null
  advisoryConfidence: number | null
  packageFidelity: number | null
  toneAlignment: number | null
  motifAlignment: number | null
  continuityAlignment: number | null
  cinematicAlignment: number | null
  issueCount: number | null
  criticalIssueCount: number
  warningCount: number
}

export type PrevisSceneBoardEntrySnapshot = {
  sceneId: string
  shotCount: number
  linkedRefs: string[]
}

export type PrevisBeatShotMapEntrySnapshot = {
  beatId: string
  sceneId: string
  shots: string[]
}

export type PrevisContinuityMapEntrySnapshot = {
  sceneId: string
  checks: string[]
}

export type PrevisAssetMapEntrySnapshot = {
  assetId: string
  scenes: string[]
}

export type PrevisContractSnapshot = {
  mode: 'read_only'
  authority: 'none'
  executionEnabled: boolean
}

export type RenderSourceResolutionSnapshot = {
  source: 'real' | 'local' | 'mock' | 'none'
  filePath: string | null
  url: string | null
}

export function resolveRenderSource(
  summary: ExecutionSummaryInspectionSnapshot | null
): RenderSourceResolutionSnapshot {
  if (!summary) {
    return { source: 'none', filePath: null, url: null }
  }

  const realFilePath = summary.executionResultV2?.meta?.filePath ?? null
  const realUrl = summary.executionResultV2?.meta?.url ?? null
  if (realFilePath || realUrl) {
    return {
      source: 'real',
      filePath: realFilePath,
      url: realUrl,
    }
  }

  const localFilePath = summary.localRenderOutput?.filePath ?? summary.localArtifactLog?.filePath ?? null
  const localUrl =
    summary.shotExecutionLedger?.find((entry) => typeof entry.url === 'string')?.url ??
    summary.takeArtifacts?.find((entry) => typeof entry.url === 'string')?.url ??
    null
  if (localFilePath || localUrl) {
    return {
      source: 'local',
      filePath: localFilePath,
      url: localUrl,
    }
  }

  if (summary.mockRenderOutput) {
    return {
      source: 'mock',
      filePath: null,
      url: null,
    }
  }

  return { source: 'none', filePath: null, url: null }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asText(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function asBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (normalized === 'true') return true
    if (normalized === 'false') return false
  }
  return null
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return null
}

function asRenderBehavior(value: unknown): RenderBehavior | null {
  const text = asText(value)
  if (!text) {
    return null
  }
  if (
    text === 'stable' ||
    text === 'retry_heavy' ||
    text === 'in_progress' ||
    text === 'stuck' ||
    text === 'unknown'
  ) {
    return text
  }
  return null
}

function asInterventionSuggestion(value: unknown): InterventionSuggestionSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const level = asText(root.level)
  const message = asText(root.message)
  const source = asText(root.source)
  if (level !== 'advisory' || !message || !source) {
    return null
  }
  return { level: 'advisory', message, source }
}

function asProductionSignal(value: unknown): ProductionSignalSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const type = asText(root.type)
  const message = asText(root.message)
  if (type !== 'production_signal' || !message) {
    return null
  }
  return { type: 'production_signal', message }
}

function asSceneIntent(value: unknown): SceneIntentSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const type = asText(root.type)
  const label = asText(root.label)
  if (type !== 'intent_label' || !label) {
    return null
  }
  return { type: 'intent_label', label }
}

function asIntentSignal(value: unknown): IntentSignalSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const type = asText(root.type)
  const message = asText(root.message)
  if (type !== 'intent_presence' || !message) {
    return null
  }
  return { type: 'intent_presence', message }
}

function asIntentOutputSignal(value: unknown): IntentOutputSignalSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const type = asText(root.type)
  const message = asText(root.message)
  if (type !== 'intent_output_presence' || !message) {
    return null
  }
  return { type: 'intent_output_presence', message }
}

function asIntentOutputRelation(value: unknown): IntentOutputRelationSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const type = asText(root.type)
  const state = asText(root.state)
  const message = asText(root.message)
  if (type !== 'intent_output_relation' || state !== 'ready_for_review' || !message) {
    return null
  }
  return { type: 'intent_output_relation', state: 'ready_for_review', message }
}

function asRecurringPattern(value: unknown): RecurringPatternSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const type = asText(root.type)
  const providerName = asText(root.provider_name)
  const message = asText(root.message)
  const count = asNumber(root.count)
  if (type !== 'provider_failure_pattern' && type !== 'stuck_pattern') {
    return null
  }
  if (!message || count === null || count < 0) {
    return null
  }
  if (type === 'provider_failure_pattern' && !providerName) {
    return null
  }
  return { type, count, providerName: providerName ?? null, message }
}

function asMemoryAdvisoryProjection(value: unknown): MemoryAdvisoryProjectionSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const status = asText(root.status)
  const message = asText(root.message)
  if (!status || !message) {
    return null
  }
  return { status, message }
}

function asMemorySnapshotSummary(value: unknown): MemorySnapshotSummarySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const candidateCount = asNumber(root.candidate_count)
  const recordCount = asNumber(root.record_count)
  const aggregateCount = asNumber(root.aggregate_count)
  const advisoryStatus = asText(root.advisory_status)
  const influenceMode = asText(root.influence_mode)
  if (
    candidateCount === null ||
    recordCount === null ||
    aggregateCount === null ||
    candidateCount < 0 ||
    recordCount < 0 ||
    aggregateCount < 0 ||
    !advisoryStatus ||
    !influenceMode
  ) {
    return null
  }
  return {
    candidateCount,
    recordCount,
    aggregateCount,
    advisoryStatus,
    influenceMode,
  }
}

function asMemoryCategoryPresence(value: unknown): MemoryCategoryPresenceSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const characterPairs = asBoolean(root.character_pairs)
  const locations = asBoolean(root.locations)
  const timeOfDay = asBoolean(root.time_of_day)
  if (characterPairs === null || locations === null || timeOfDay === null) {
    return null
  }
  return {
    characterPairs,
    locations,
    timeOfDay,
  }
}

function asMemoryStateRollup(value: unknown): MemoryStateRollupSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const status = asText(root.status)
  const candidateCount = asNumber(root.candidate_count)
  const influenceMode = asText(root.influence_mode)
  const advisoryStatus = asText(root.advisory_status)
  if (
    (status !== 'available' && status !== 'unavailable') ||
    candidateCount === null ||
    candidateCount < 0 ||
    !influenceMode ||
    (advisoryStatus !== 'available' && advisoryStatus !== 'unavailable')
  ) {
    return null
  }
  return {
    status,
    candidateCount,
    influenceMode,
    advisoryStatus,
  }
}

function asMemoryConsistency(value: unknown): MemoryConsistencySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const isConsistent = asBoolean(root.is_consistent)
  const hasRequiredFields = asBoolean(root.has_required_fields)
  const gateDisabled = asBoolean(root.gate_disabled)
  const authorityNone = asBoolean(root.authority_none)
  if (
    isConsistent === null ||
    hasRequiredFields === null ||
    gateDisabled === null ||
    authorityNone === null
  ) {
    return null
  }
  return {
    isConsistent,
    hasRequiredFields,
    gateDisabled,
    authorityNone,
  }
}

function asCoDirectorMemoryVisibility(value: unknown): CoDirectorMemoryVisibilitySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const hasMemoryCandidates = asBoolean(root.has_memory_candidates)
  const hasMemoryRecords = asBoolean(root.has_memory_records)
  const hasMemoryAggregate = asBoolean(root.has_memory_aggregate)
  const influenceMode = asText(root.influence_mode)
  const advisoryStatus = asText(root.advisory_status)
  if (
    hasMemoryCandidates === null ||
    hasMemoryRecords === null ||
    hasMemoryAggregate === null ||
    !influenceMode ||
    !advisoryStatus
  ) {
    return null
  }
  return {
    hasMemoryCandidates,
    hasMemoryRecords,
    hasMemoryAggregate,
    influenceMode,
    advisoryStatus,
  }
}

function asCoDirectorMemoryAdvisory(value: unknown): CoDirectorMemoryAdvisorySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const status = asText(root.status)
  const message = asText(root.message)
  if (!status || !message) {
    return null
  }
  return { status, message }
}

function asCoDirectorMemoryAuthorityBoundary(value: unknown): CoDirectorMemoryAuthorityBoundarySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const authority = asText(root.authority)
  const memoryInfluence = asText(root.memory_influence)
  const reason = asText(root.reason)
  if (!authority || !memoryInfluence || !reason) {
    return null
  }
  return { authority, memoryInfluence, reason }
}

function asCoDirectorVisualFeed(value: unknown): CoDirectorVisualFeedSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }

  const referenceSummary = asVisualReferenceSummary(root.reference_summary)
  const frameSnapshot = asFrameAnalysisSnapshot(root.frame_snapshot)

  const linkageRoot = asRecord(root.linkage)
  const linkedScenes = asNumber(linkageRoot?.linked_scenes)
  const totalScenes = asNumber(linkageRoot?.total_scenes)
  if (
    linkedScenes === null ||
    totalScenes === null ||
    linkedScenes < 0 ||
    totalScenes < 0
  ) {
    return null
  }

  const alignmentRoot = asRecord(root.alignment)
  const state = asText(alignmentRoot?.state)
  const noteRaw = alignmentRoot?.note
  const mode = asText(root.mode)
  if (!referenceSummary || !frameSnapshot || !state || typeof noteRaw !== 'string' || mode !== 'read_only') {
    return null
  }

  return {
    referenceSummary,
    frameSnapshot,
    linkage: {
      linkedScenes,
      totalScenes,
    },
    alignment: {
      state,
      note: noteRaw.trim(),
    },
    mode: 'read_only',
  }
}

function asVisualReference(value: unknown): VisualReferenceSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const id = asText(root.id)
  const type = asText(root.type)
  const source = asText(root.source)
  const label = asText(root.label)
  if (!id || !type || !source || !label) {
    return null
  }
  const sceneId = asText(root.scene_id)
  return {
    id,
    type,
    source,
    label,
    sceneId: sceneId ?? null,
  }
}

function asVisualReferences(value: unknown): VisualReferenceSnapshot[] | null {
  if (!Array.isArray(value)) {
    return null
  }
  const visualReferences: VisualReferenceSnapshot[] = []
  for (const item of value) {
    const parsed = asVisualReference(item)
    if (parsed) {
      visualReferences.push(parsed)
    }
  }
  return visualReferences
}

function asStringArray(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null
  }
  const values: string[] = []
  for (const item of value) {
    const parsed = asText(item)
    if (!parsed) {
      return null
    }
    values.push(parsed)
  }
  return values
}

function asVisualReferenceIndexes(value: unknown): VisualReferenceIndexesSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const byReferenceIdRoot = asRecord(root.by_reference_id)
  const bySceneIdRoot = asRecord(root.by_scene_id)
  const byTypeRoot = asRecord(root.by_type)
  if (!byReferenceIdRoot || !bySceneIdRoot || !byTypeRoot) {
    return null
  }

  const byReferenceId: Record<string, VisualReferenceSnapshot> = {}
  for (const [key, rawReference] of Object.entries(byReferenceIdRoot)) {
    const parsedReference = asVisualReference(rawReference)
    if (!parsedReference || parsedReference.id !== key) {
      return null
    }
    byReferenceId[key] = parsedReference
  }

  const bySceneId: Record<string, string[]> = {}
  for (const [key, rawIds] of Object.entries(bySceneIdRoot)) {
    const parsedIds = asStringArray(rawIds)
    if (!parsedIds) {
      return null
    }
    bySceneId[key] = parsedIds
  }

  const byType: Record<string, string[]> = {}
  for (const [key, rawIds] of Object.entries(byTypeRoot)) {
    const parsedIds = asStringArray(rawIds)
    if (!parsedIds) {
      return null
    }
    byType[key] = parsedIds
  }

  return {
    byReferenceId,
    bySceneId,
    byType,
  }
}

function asVisualReferenceSummary(value: unknown): VisualReferenceSummarySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const referenceCount = asNumber(root.reference_count)
  const linkedSceneCount = asNumber(root.linked_scene_count)
  const typeCount = asNumber(root.type_count)
  if (
    referenceCount === null ||
    linkedSceneCount === null ||
    typeCount === null ||
    referenceCount < 0 ||
    linkedSceneCount < 0 ||
    typeCount < 0
  ) {
    return null
  }
  return {
    referenceCount,
    linkedSceneCount,
    typeCount,
  }
}

function asTypeCounts(value: unknown): Record<string, number> | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const typeCounts: Record<string, number> = {}
  for (const [key, rawCount] of Object.entries(root)) {
    const parsedKey = asText(key)
    const parsedCount = asNumber(rawCount)
    if (!parsedKey || parsedCount === null || parsedCount < 0) {
      return null
    }
    typeCounts[parsedKey] = parsedCount
  }
  return typeCounts
}

function asVisualPatternSummary(value: unknown): VisualPatternSummarySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const dominantTypes = asStringArray(root.dominant_types)
  const typeCounts = asTypeCounts(root.type_counts)
  if (!dominantTypes || !typeCounts) {
    return null
  }
  return {
    dominantTypes,
    typeCounts,
  }
}

function asSceneVisualIdentity(value: unknown): SceneVisualIdentitySnapshot | null {
  return asSceneVisualLinks(value)
}

function asVisualConsistency(value: unknown): VisualConsistencySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const consistent = asBoolean(root.consistent)
  const varianceLevel = asText(root.variance_level)
  if (
    consistent === null ||
    (varianceLevel !== 'none' && varianceLevel !== 'low' && varianceLevel !== 'high')
  ) {
    return null
  }
  return {
    consistent,
    varianceLevel,
  }
}

function asVisualTension(value: unknown): VisualTensionSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const tensionScenes = asStringArray(root.tension_scenes)
  if (!tensionScenes) {
    return null
  }
  return { tensionScenes }
}

function asFrameMetadataEntry(value: unknown): FrameMetadataSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const frameId = asText(root.frame_id)
  const artifactId = asText(root.artifact_id)
  const timestamp = asNumber(root.timestamp)
  if (!frameId || !artifactId || timestamp === null || timestamp < 0) {
    return null
  }
  return {
    frameId,
    artifactId,
    timestamp,
  }
}

function asFrameMetadata(value: unknown): FrameMetadataSnapshot[] | null {
  if (!Array.isArray(value)) {
    return null
  }
  const metadata: FrameMetadataSnapshot[] = []
  for (const item of value) {
    const parsed = asFrameMetadataEntry(item)
    if (parsed) {
      metadata.push(parsed)
    }
  }
  return metadata
}

function asFrameStats(value: unknown): FrameStatsSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const frameCount = asNumber(root.frame_count)
  const artifactCount = asNumber(root.artifact_count)
  if (
    frameCount === null ||
    artifactCount === null ||
    frameCount < 0 ||
    artifactCount < 0
  ) {
    return null
  }
  return {
    frameCount,
    artifactCount,
  }
}

function asFrameAnalysisSnapshot(value: unknown): FrameAnalysisSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const frameMetadata = asFrameMetadata(root.frame_metadata)
  const frameStats = asFrameStats(root.frame_stats)
  if (!frameMetadata || !frameStats) {
    return null
  }
  return {
    frameMetadata,
    frameStats,
  }
}

function asSceneVisualLinks(value: unknown): SceneVisualLinksSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const links: SceneVisualLinksSnapshot = {}
  for (const [sceneId, rawReferenceIds] of Object.entries(root)) {
    const parsedSceneId = asText(sceneId)
    const parsedReferenceIds = asStringArray(rawReferenceIds)
    if (!parsedSceneId || !parsedReferenceIds) {
      return null
    }
    links[parsedSceneId] = parsedReferenceIds
  }
  return links
}

function asLinkCompleteness(value: unknown): LinkCompletenessSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const linkedScenes = asNumber(root.linked_scenes)
  const totalScenes = asNumber(root.total_scenes)
  if (
    linkedScenes === null ||
    totalScenes === null ||
    linkedScenes < 0 ||
    totalScenes < 0
  ) {
    return null
  }
  return {
    linkedScenes,
    totalScenes,
  }
}

function asShotCandidate(value: unknown): ShotCandidateSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const sceneId = asText(root.scene_id)
  const shotId = asText(root.shot_id)
  const sourceRefs = asStringArray(root.source_refs)
  if (!sceneId || !shotId || !sourceRefs) {
    return null
  }
  return {
    sceneId,
    shotId,
    sourceRefs,
  }
}

function asShotCandidates(value: unknown): ShotCandidateSnapshot[] | null {
  if (!Array.isArray(value)) {
    return null
  }
  const candidates: ShotCandidateSnapshot[] = []
  for (const item of value) {
    const parsed = asShotCandidate(item)
    if (parsed) {
      candidates.push(parsed)
    }
  }
  return candidates
}

function asShotCoverage(value: unknown): ShotCoverageSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const coverage: ShotCoverageSnapshot = {}
  for (const [sceneId, rawEntry] of Object.entries(root)) {
    const parsedSceneId = asText(sceneId)
    const entry = asRecord(rawEntry)
    const candidateCount = asNumber(entry?.candidate_count)
    if (!parsedSceneId || candidateCount === null || candidateCount < 0) {
      return null
    }
    coverage[parsedSceneId] = { candidateCount }
  }
  return coverage
}

function asShotPlanBundle(value: unknown): ShotPlanBundleSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const shotCandidates = asShotCandidates(root.shot_candidates)
  const shotCoverage = asShotCoverage(root.shot_coverage)
  const influenceMode = asText(root.influence_mode)
  if (!shotCandidates || !shotCoverage || !influenceMode) {
    return null
  }
  return {
    shotCandidates,
    shotCoverage,
    influenceMode,
  }
}

function asShotIntent(value: unknown): ShotIntentSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const shotIntent: ShotIntentSnapshot = {}
  for (const [shotId, rawIntent] of Object.entries(root)) {
    const parsedShotId = asText(shotId)
    const parsedIntent = asText(rawIntent)
    if (
      !parsedShotId ||
      (parsedIntent !== 'dialogue_focus' &&
        parsedIntent !== 'establishing' &&
        parsedIntent !== 'general')
    ) {
      return null
    }
    shotIntent[parsedShotId] = parsedIntent
  }
  return shotIntent
}

function asShotVariety(value: unknown): ShotVarietySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const diversity = asText(root.diversity)
  if (diversity !== 'none' && diversity !== 'low' && diversity !== 'balanced') {
    return null
  }
  return { diversity }
}

function asSceneCoverage(value: unknown): SceneCoverageSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const sceneCoverage: SceneCoverageSnapshot = {}
  for (const [sceneId, rawStatus] of Object.entries(root)) {
    const parsedSceneId = asText(sceneId)
    const parsedStatus = asText(rawStatus)
    if (!parsedSceneId || (parsedStatus !== 'covered' && parsedStatus !== 'partial')) {
      return null
    }
    sceneCoverage[parsedSceneId] = parsedStatus
  }
  return sceneCoverage
}

function asShotPlanningSummary(value: unknown): ShotPlanningSummarySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const coveredScenes = asNumber(root.covered_scenes)
  const totalScenes = asNumber(root.total_scenes)
  const variety = asText(root.variety)
  if (
    coveredScenes === null ||
    totalScenes === null ||
    coveredScenes < 0 ||
    totalScenes < 0 ||
    (variety !== 'none' && variety !== 'low' && variety !== 'balanced')
  ) {
    return null
  }
  return {
    coveredScenes,
    totalScenes,
    variety,
  }
}

function asShotAdvisoryNote(value: unknown): ShotAdvisoryNoteSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const note = root.note
  if (typeof note !== 'string') {
    return null
  }
  return { note }
}

function asSceneSequenceEntry(value: unknown): SceneSequenceSnapshot[number] | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const sceneId = asText(root.scene_id)
  const shots = asStringArray(root.shots)
  if (!sceneId || shots === null) {
    return null
  }
  return { sceneId, shots }
}

function asSceneSequence(value: unknown): SceneSequenceSnapshot | null {
  if (!Array.isArray(value)) {
    return null
  }
  const entries: SceneSequenceSnapshot = []
  for (const item of value) {
    const parsed = asSceneSequenceEntry(item)
    if (parsed) {
      entries.push(parsed)
    }
  }
  if (entries.length === 0) {
    return null
  }
  return entries
}

function asSceneAssembly(value: unknown): SceneAssemblySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const sceneCount = asNumber(root.scene_count)
  const assembled = asBoolean(root.assembled)
  const shotsAvailable = asNumber(root.shots_available)
  if (
    sceneCount === null ||
    assembled === null ||
    shotsAvailable === null ||
    sceneCount < 0 ||
    shotsAvailable < 0
  ) {
    return null
  }
  return { sceneCount, assembled, shotsAvailable }
}

function asSequenceStatus(value: unknown): SequenceStatusSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const scenes = asNumber(root.scenes)
  const shots = asNumber(root.shots)
  const assembled = asBoolean(root.assembled)
  if (
    scenes === null ||
    shots === null ||
    assembled === null ||
    scenes < 0 ||
    shots < 0
  ) {
    return null
  }
  return { scenes, shots, assembled }
}

function asSceneContinuityCheck(value: unknown): SceneContinuityCheckSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const visualConsistency = root.visual_consistency
  if (visualConsistency !== 'none' && visualConsistency !== 'low' && visualConsistency !== 'high') {
    return null
  }
  const shotVariety = root.shot_variety
  if (shotVariety !== 'none' && shotVariety !== 'low' && shotVariety !== 'balanced') {
    return null
  }
  const assembled = asBoolean(root.assembled)
  if (assembled === null) {
    return null
  }
  const status = root.status
  if (status !== 'ready' && status !== 'incomplete') {
    return null
  }
  return { visualConsistency, shotVariety, assembled, status }
}

function asScenePlaybackStatus(value: unknown): ScenePlaybackStatusSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const playbackReady = asBoolean(root.playback_ready)
  if (playbackReady === null) {
    return null
  }
  const sceneCount = asNumber(root.scene_count)
  const shotsAvailable = asNumber(root.shots_available)
  if (sceneCount === null || shotsAvailable === null || sceneCount < 0 || shotsAvailable < 0) {
    return null
  }
  const status = root.status
  if (status !== 'ready' && status !== 'incomplete') {
    return null
  }
  return { playbackReady, sceneCount, shotsAvailable, status }
}

function asCoDirectorVisualObservation(value: unknown): CoDirectorVisualObservationSnapshot | null {
  return asShotAdvisoryNote(value)
}

function asCoDirectorShotObservation(value: unknown): CoDirectorShotObservationSnapshot | null {
  return asShotAdvisoryNote(value)
}

function asCoDirectorObservationSummary(value: unknown): CoDirectorObservationSummarySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const notes = asStringArray(root.notes)
  if (!notes) {
    return null
  }
  return { notes }
}

function asCoDirectorObservationContract(value: unknown): CoDirectorObservationContractSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const mode = asText(root.mode)
  const authority = asText(root.authority)
  const influence = asText(root.influence)
  if (mode !== 'read_only' || authority !== 'none' || influence !== 'disabled') {
    return null
  }
  return { mode, authority, influence }
}

function asOutputInfluenceGuardV2(value: unknown): OutputInfluenceGuardV2Snapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const outputInfluence = asBoolean(root.output_influence)
  const reason = asText(root.reason)
  if (outputInfluence === null || !reason) {
    return null
  }
  return {
    outputInfluence,
    reason,
  }
}

function asVisualDecisionBoundary(value: unknown): VisualDecisionBoundarySnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const visualDecisionAuthority = asText(root.visual_decision_authority)
  const reason = asText(root.reason)
  if (!visualDecisionAuthority || !reason) {
    return null
  }
  return {
    visualDecisionAuthority,
    reason,
  }
}

function asShotExecutionLock(value: unknown): ShotExecutionLockSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const shotExecutionEnabled = asBoolean(root.shot_execution_enabled)
  const reason = asText(root.reason)
  if (shotExecutionEnabled === null || !reason) {
    return null
  }
  return {
    shotExecutionEnabled,
    reason,
  }
}

function asBoundaryAudit(value: unknown): BoundaryAuditSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const memorySafe = asBoolean(root.memory_safe)
  const visualSafe = asBoolean(root.visual_safe)
  const shotSafe = asBoolean(root.shot_safe)
  const renderSafe = asBoolean(root.render_safe)
  const coDirectorSafe = asBoolean(root.co_director_safe)
  const overallSafe = asBoolean(root.overall_safe)
  if (
    memorySafe === null ||
    visualSafe === null ||
    shotSafe === null ||
    renderSafe === null ||
    coDirectorSafe === null ||
    overallSafe === null
  ) {
    return null
  }
  return {
    memorySafe,
    visualSafe,
    shotSafe,
    renderSafe,
    coDirectorSafe,
    overallSafe,
  }
}

function asStudioSafetyState(value: unknown): StudioSafetyStateSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const studioState = asText(root.studio_state)
  if (studioState !== 'safe_for_control_phase' && studioState !== 'not_ready') {
    return null
  }
  return { studioState }
}

function asPromptInfluenceGateV1(value: unknown): PromptInfluenceGateV1Snapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const promptInfluenceEnabled = asBoolean(root.prompt_influence_enabled)
  const scope = asText(root.scope)
  const reason = asText(root.reason)
  if (promptInfluenceEnabled === null || scope !== 'advisory_only' || !reason) {
    return null
  }
  return {
    promptInfluenceEnabled,
    scope,
    reason,
  }
}

function asPromptEnvelope(value: unknown): PromptEnvelopeSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const baseIntentRaw = root.base_intent
  const visualTokens = asStringArray(root.visual_tokens)
  const shotTokens = asStringArray(root.shot_tokens)
  if (typeof baseIntentRaw !== 'string' || visualTokens === null || shotTokens === null) {
    return null
  }
  return {
    baseIntent: baseIntentRaw,
    visualTokens,
    shotTokens,
  }
}

function asPromptSafetyContract(value: unknown): PromptSafetyContractSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const promptOverride = asBoolean(root.prompt_override)
  const structureLocked = asBoolean(root.structure_locked)
  const tokenInjectionOnly = asBoolean(root.token_injection_only)
  const reason = asText(root.reason)
  if (
    promptOverride === null ||
    structureLocked === null ||
    tokenInjectionOnly === null ||
    !reason
  ) {
    return null
  }
  return {
    promptOverride,
    structureLocked,
    tokenInjectionOnly,
    reason,
  }
}

function asRenderActivationGateV1(value: unknown): RenderActivationGateV1Snapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const renderEnabled = asBoolean(root.render_enabled)
  const mode = asText(root.mode)
  const reason = asText(root.reason)
  if (renderEnabled === null || mode !== 'single_shot' || !reason) {
    return null
  }
  return {
    renderEnabled,
    mode: 'single_shot',
    reason,
  }
}

function asRenderRequest(value: unknown): RenderRequestSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const shotId = asText(root.shot_id)
  const sceneId = asText(root.scene_id)
  const prompt = asPromptEnvelope(root.prompt)
  if (!shotId || !sceneId || !prompt) {
    return null
  }
  return {
    shotId,
    sceneId,
    prompt,
  }
}

function asRenderOutput(value: unknown): RenderOutputSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const renderId = asText(root.render_id)
  const shotId = asText(root.shot_id)
  const status = asText(root.status)
  const promptSnapshot = asPromptEnvelope(root.prompt_snapshot)
  if (!renderId || !shotId || status !== 'pending' || !promptSnapshot) {
    return null
  }
  return {
    renderId,
    shotId,
    status: 'pending',
    promptSnapshot,
  }
}

function asOutputReview(value: unknown): OutputReviewSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const renderId = asText(root.render_id)
  const alignmentRaw = root.alignment
  const coverageRaw = root.coverage
  const status = asText(root.status)
  if (
    !renderId ||
    typeof alignmentRaw !== 'string' ||
    typeof coverageRaw !== 'string' ||
    status !== 'pending'
  ) {
    return null
  }
  return {
    renderId,
    alignment: alignmentRaw,
    coverage: coverageRaw,
    status: 'pending',
  }
}

function asOutputEvaluation(value: unknown): OutputEvaluationSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const hasOutput = asBoolean(root.has_output)
  const validStructure = asBoolean(root.valid_structure)
  const renderIdPresent = asBoolean(root.render_id_present)
  const status = asText(root.status)
  if (
    hasOutput === null ||
    validStructure === null ||
    renderIdPresent === null ||
    (status !== 'valid' && status !== 'invalid' && status !== 'none')
  ) {
    return null
  }
  return {
    hasOutput,
    validStructure,
    renderIdPresent,
    status,
  }
}

function asRetryGate(value: unknown): RetryGateSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const retryAllowed = asBoolean(root.retry_allowed)
  const reason = asText(root.reason)
  if (retryAllowed === null || !reason) {
    return null
  }
  return {
    retryAllowed,
    reason,
  }
}

function asExecutionSnapshot(value: unknown): ExecutionSnapshotSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const iteration = asNumber(root.iteration)
  const maxIterations = asNumber(root.max_iterations)
  const status = asText(root.status)
  const renderAttempted = asBoolean(root.render_attempted)
  const retryAllowed = asBoolean(root.retry_allowed)
  const finalized = asBoolean(root.finalized)
  if (
    iteration === null ||
    maxIterations === null ||
    !Number.isInteger(iteration) ||
    !Number.isInteger(maxIterations) ||
    iteration < 0 ||
    maxIterations < 0 ||
    (status !== 'idle' && status !== 'ready' && status !== 'in_progress' && status !== 'complete') ||
    renderAttempted === null ||
    retryAllowed === null ||
    finalized === null
  ) {
    return null
  }
  return {
    iteration,
    maxIterations,
    status,
    renderAttempted,
    retryAllowed,
    finalized,
  }
}

function asIterationRecord(value: unknown): IterationRecordSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const iteration = asNumber(root.iteration)
  const status = asText(root.status)
  const renderIdRaw = root.render_id
  const coverageRaw = root.coverage
  const alignmentRaw = root.alignment
  if (
    iteration === null ||
    !Number.isInteger(iteration) ||
    iteration < 0 ||
    !status ||
    !(renderIdRaw === null || typeof renderIdRaw === 'string') ||
    typeof coverageRaw !== 'string' ||
    typeof alignmentRaw !== 'string'
  ) {
    return null
  }
  return {
    iteration,
    status,
    renderId: typeof renderIdRaw === 'string' ? renderIdRaw : null,
    coverage: coverageRaw,
    alignment: alignmentRaw,
  }
}

function asTakeHistory(value: unknown): TakeHistorySnapshot | null {
  const root = asRecord(value)
  if (!root || !Array.isArray(root.takes)) {
    return null
  }
  const takes: IterationRecordSnapshot[] = []
  for (const take of root.takes) {
    const parsed = asIterationRecord(take)
    if (!parsed) {
      return null
    }
    takes.push(parsed)
  }
  return { takes }
}

function asTakeArtifacts(value: unknown): TakeArtifactSnapshot[] | null {
  if (!Array.isArray(value)) {
    return null
  }
  const artifacts: TakeArtifactSnapshot[] = []
  for (const item of value) {
    const root = asRecord(item)
    if (!root) {
      continue
    }
    const iteration = asNumber(root.iteration)
    const status = asText(root.status)
    const renderIdRaw = root.render_id
    const filePathRaw = root.file_path
    const urlRaw = root.url
    const metaRoot = asRecord(root.meta)
    const metaFilePathRaw = metaRoot?.file_path
    const metaUrlRaw = metaRoot?.url
    const resolvedFilePath =
      typeof filePathRaw === 'string'
        ? filePathRaw
        : typeof metaFilePathRaw === 'string'
          ? metaFilePathRaw
          : null
    const resolvedUrl =
      typeof urlRaw === 'string' ? urlRaw : typeof metaUrlRaw === 'string' ? metaUrlRaw : null
    if (
      iteration === null ||
      !Number.isInteger(iteration) ||
      iteration < 0 ||
      !status ||
      !(renderIdRaw === null || typeof renderIdRaw === 'string') ||
      !(resolvedFilePath === null || typeof resolvedFilePath === 'string') ||
      !(resolvedUrl === null || typeof resolvedUrl === 'string')
    ) {
      continue
    }
    artifacts.push({
      iteration,
      renderId: typeof renderIdRaw === 'string' ? renderIdRaw : null,
      status,
      ...(typeof resolvedFilePath === 'string' ? { filePath: resolvedFilePath } : {}),
      ...(typeof resolvedUrl === 'string' ? { url: resolvedUrl } : {}),
    })
  }
  return artifacts
}

function asRetrySnapshot(value: unknown): RetrySnapshotSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const allowed = asBoolean(root.allowed)
  const iteration = asNumber(root.iteration)
  const status = asText(root.status)
  if (
    allowed === null ||
    iteration === null ||
    !Number.isInteger(iteration) ||
    iteration < 0 ||
    !status
  ) {
    return null
  }
  return {
    allowed,
    iteration,
    status,
  }
}

function asTakeComparison(value: unknown): TakeComparisonSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const bestTake = root.best_take
  const comparisonReady = asBoolean(root.comparison_ready)
  if (bestTake !== null || comparisonReady === null) {
    return null
  }
  return {
    bestTake: null,
    comparisonReady,
  }
}

function asTakeComparisonV2(value: unknown): TakeComparisonV2Snapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const comparable = asBoolean(root.comparable)
  if (comparable === null || !Array.isArray(root.differences)) {
    return null
  }
  const differences = root.differences.filter((entry): entry is string => typeof entry === 'string')
  return { comparable, differences }
}

function asTakePreferenceContract(value: unknown): TakePreferenceContractSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const autoSelect = asBoolean(root.auto_select)
  const authority = asText(root.authority)
  if (autoSelect === null || authority !== 'manual_only') {
    return null
  }
  return { autoSelect, authority: 'manual_only' }
}

function asTakeAdvisoryNote(value: unknown): TakeAdvisoryNoteSnapshot | null {
  const root = asRecord(value)
  if (!root || typeof root.note !== 'string') {
    return null
  }
  return { note: root.note }
}

function asOutputReviewMatrix(value: unknown): OutputReviewMatrixRowSnapshot[] | null {
  if (!Array.isArray(value)) {
    return null
  }
  const rows: OutputReviewMatrixRowSnapshot[] = []
  for (const item of value) {
    const root = asRecord(item)
    if (!root) {
      continue
    }
    const takeId = asNumber(root.take_id)
    const alignment = asText(root.alignment)
    const coverage = asText(root.coverage)
    const validStructure = asBoolean(root.valid_structure)
    if (
      takeId === null ||
      !Number.isInteger(takeId) ||
      takeId < 0 ||
      !alignment ||
      !coverage ||
      validStructure === null
    ) {
      continue
    }
    rows.push({
      takeId,
      alignment,
      coverage,
      validStructure,
    })
  }
  return rows
}

function asLoopReadiness(value: unknown): LoopReadinessSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const ready = asBoolean(root.ready)
  const reason = asText(root.reason)
  if (ready === null || !reason) {
    return null
  }
  return { ready, reason }
}

function asNextTakePreview(value: unknown): NextTakePreviewSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const nextIteration = asNumber(root.next_iteration)
  const willRetry = asBoolean(root.will_retry)
  if (
    nextIteration === null ||
    !Number.isInteger(nextIteration) ||
    nextIteration < 0 ||
    willRetry === null
  ) {
    return null
  }
  return {
    nextIteration,
    willRetry,
  }
}

function asLoopConstraint(value: unknown): LoopConstraintSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const maxIterations = asNumber(root.max_iterations)
  const remaining = asNumber(root.remaining)
  if (
    maxIterations === null ||
    remaining === null ||
    !Number.isInteger(maxIterations) ||
    !Number.isInteger(remaining) ||
    maxIterations < 0 ||
    remaining < 0
  ) {
    return null
  }
  return {
    maxIterations,
    remaining,
  }
}

function asLoopAdvisory(value: unknown): LoopAdvisorySnapshot | null {
  const root = asRecord(value)
  if (!root || typeof root.note !== 'string') {
    return null
  }
  return { note: root.note }
}

function asLoopContract(value: unknown): LoopContractSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const autoLoop = asBoolean(root.auto_loop)
  const executionMode = asText(root.execution_mode)
  const reason = asText(root.reason)
  if (
    autoLoop === null ||
    executionMode !== 'manual_only' ||
    !reason
  ) {
    return null
  }
  return {
    autoLoop,
    executionMode: 'manual_only',
    reason,
  }
}

function asLoopExecutionPlan(value: unknown): LoopExecutionPlanSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const execute = asBoolean(root.execute)
  const nextIteration = asNumber(root.next_iteration)
  const reason = asText(root.reason)
  if (
    execute === null ||
    nextIteration === null ||
    !Number.isInteger(nextIteration) ||
    nextIteration < 0 ||
    !reason
  ) {
    return null
  }
  return {
    execute,
    nextIteration,
    reason,
  }
}

function asSimulatedIteration(value: unknown): SimulatedIterationSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const iteration = asNumber(root.iteration)
  const status = asText(root.status)
  if (
    iteration === null ||
    !Number.isInteger(iteration) ||
    iteration < 0 ||
    !status
  ) {
    return null
  }
  return {
    iteration,
    status,
  }
}

function asSimulatedOutput(value: unknown): SimulatedOutputSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const renderIdRaw = root.render_id
  const status = asText(root.status)
  if (
    !(renderIdRaw === null || typeof renderIdRaw === 'string') ||
    (status !== 'pending' && status !== 'simulated' && status !== 'none')
  ) {
    return null
  }
  return {
    renderId: typeof renderIdRaw === 'string' ? renderIdRaw : null,
    status,
  }
}

function asLoopResultSnapshot(value: unknown): LoopResultSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const iteration = asNumber(root.iteration)
  const outputStatus = asText(root.output_status)
  if (
    iteration === null ||
    !Number.isInteger(iteration) ||
    iteration < 0 ||
    (outputStatus !== 'pending' && outputStatus !== 'simulated' && outputStatus !== 'none')
  ) {
    return null
  }
  return {
    iteration,
    outputStatus,
  }
}

function asLoopExecutionContract(value: unknown): LoopExecutionContractSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const mode = asText(root.mode)
  const realExecution = asBoolean(root.real_execution)
  const reason = asText(root.reason)
  if (mode !== 'safe_simulation' || realExecution === null || !reason) {
    return null
  }
  return {
    mode: 'safe_simulation',
    realExecution,
    reason,
  }
}

function asExecutionPermission(value: unknown): ExecutionPermissionSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const allowed = asBoolean(root.allowed)
  const mode = asText(root.mode)
  const reason = asText(root.reason)
  if (
    allowed === null ||
    (mode !== 'blocked' && mode !== 'single_shot') ||
    !reason
  ) {
    return null
  }
  return {
    allowed,
    mode,
    reason,
  }
}

function asExecutionRequest(value: unknown): ExecutionRequestSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const enabled = asBoolean(root.enabled)
  const shotIdRaw = root.shot_id
  const promptRaw = root.prompt
  if (enabled === null) {
    return null
  }

  if (enabled) {
    const shotId = asText(shotIdRaw)
    const prompt = asPromptEnvelope(promptRaw)
    if (!shotId || !prompt) {
      return null
    }
    return {
      enabled: true,
      shotId,
      prompt,
    }
  }

  if (shotIdRaw !== null || promptRaw !== null) {
    return null
  }
  return {
    enabled: false,
    shotId: null,
    prompt: null,
  }
}

function asExecutionStatus(value: unknown): ExecutionStatusSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const state = asText(root.state)
  const reason = asText(root.reason)
  if ((state !== 'idle' && state !== 'ready' && state !== 'blocked') || !reason) {
    return null
  }
  return {
    state,
    reason,
  }
}

function asExecutionResult(value: unknown): ExecutionResultSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const executed = asBoolean(root.executed)
  const renderId = root.render_id
  const status = asText(root.status)
  if (executed === null || renderId !== null || status !== 'not_executed') {
    return null
  }
  return {
    executed,
    renderId: null,
    status: 'not_executed',
  }
}

function asProviderPayload(value: unknown): ProviderPayloadSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const shotIdRaw = root.shot_id
  const promptRaw = root.prompt
  const shotId = shotIdRaw === null ? null : asText(shotIdRaw)
  const prompt = promptRaw === null ? null : asPromptEnvelope(promptRaw)
  if (shotIdRaw !== null && shotId === null) {
    return null
  }
  if (promptRaw !== null && prompt === null) {
    return null
  }
  return {
    shotId,
    prompt,
  }
}

function asProviderPayloadV2(value: unknown): ProviderPayloadV2Snapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const provider = asText(root.provider)
  const shotIdRaw = root.shot_id
  const promptRaw = root.prompt
  const shotId = shotIdRaw === null ? null : asText(shotIdRaw)
  const prompt = promptRaw === null ? null : asPromptEnvelope(promptRaw)
  if (!provider) {
    return null
  }
  if (shotIdRaw !== null && shotId === null) {
    return null
  }
  if (promptRaw !== null && prompt === null) {
    return null
  }
  return {
    provider,
    shotId,
    prompt,
  }
}

function asHandoffEnvelope(value: unknown): HandoffEnvelopeSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const requestId = asText(root.request_id)
  const provider = asText(root.provider)
  const enabled = asBoolean(root.enabled)
  if (!requestId || !provider || enabled === null) {
    return null
  }
  return {
    requestId,
    provider,
    enabled,
  }
}

function asHandoffAudit(value: unknown): HandoffAuditSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const requested = asBoolean(root.requested)
  const allowed = asBoolean(root.allowed)
  const blockedReason = asText(root.blocked_reason) ?? ''
  if (requested === null || allowed === null || root.timestamp !== null) {
    return null
  }
  return {
    requested,
    allowed,
    blockedReason,
    timestamp: null,
  }
}

function asExecutionResultV2(value: unknown): ExecutionResultV2Snapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const executed = asBoolean(root.executed)
  const renderIdRaw = root.render_id
  const status = asText(root.status)
  const providerRaw = root.provider
  const metaRoot = asRecord(root.meta)
  const filePathRaw = metaRoot?.file_path
  const urlRaw = metaRoot?.url
  if (
    executed === null ||
    !(renderIdRaw === null || typeof renderIdRaw === 'string') ||
    (status !== 'success' &&
      status !== 'failed' &&
      status !== 'skipped' &&
      status !== 'not_executed') ||
    !(providerRaw === undefined || providerRaw === null || typeof providerRaw === 'string') ||
    !(
      metaRoot === null ||
      metaRoot === undefined ||
      ((filePathRaw === undefined || filePathRaw === null || typeof filePathRaw === 'string') &&
        (urlRaw === undefined || urlRaw === null || typeof urlRaw === 'string'))
    )
  ) {
    return null
  }
  return {
    executed,
    renderId: typeof renderIdRaw === 'string' ? renderIdRaw : null,
    status,
    ...(providerRaw !== undefined ? { provider: typeof providerRaw === 'string' ? providerRaw : null } : {}),
    ...(metaRoot
      ? {
          meta: {
            filePath: typeof filePathRaw === 'string' ? filePathRaw : null,
            url: typeof urlRaw === 'string' ? urlRaw : null,
          },
        }
      : {}),
  }
}

function asOutputSync(value: unknown): OutputSyncSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const synced = asBoolean(root.synced)
  const renderIdRaw = root.render_id
  if (synced === null || !(renderIdRaw === null || typeof renderIdRaw === 'string')) {
    return null
  }
  return {
    synced,
    renderId: typeof renderIdRaw === 'string' ? renderIdRaw : null,
  }
}

function asExecutionMonitor(value: unknown): ExecutionMonitorSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const state = asText(root.state)
  const result = asText(root.result)
  if (!state || !result) {
    return null
  }
  return {
    state,
    result,
  }
}

function asExecutionContract(value: unknown): ExecutionContractSnapshot | null {
  const root = asRecord(value)
  if (!root) {
    return null
  }
  const mode = asText(root.mode)
  const autoExecution = asBoolean(root.auto_execution)
  const looping = asBoolean(root.looping)
  const reason = asText(root.reason)
  if (
    mode !== 'single_shot_only' ||
    autoExecution === null ||
    looping === null ||
    !reason
  ) {
    return null
  }
  return {
    mode: 'single_shot_only',
    autoExecution,
    looping,
    reason,
  }
}

function asProviderConfigSnapshot(value: unknown): ProviderConfigSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const defaultProvider = asText(root.default_provider)
  const enabledProviders = asStringArray(root.enabled_providers)
  const qualityPriority = asText(root.quality_priority)
  const realProvidersEnabled = asBoolean(root.real_providers_enabled)
  if (!defaultProvider || enabledProviders === null || !qualityPriority || realProvidersEnabled === null) {
    return null
  }
  return {
    defaultProvider,
    enabledProviders,
    qualityPriority,
    realProvidersEnabled,
  }
}

function asProviderCredentialState(value: unknown): ProviderCredentialStateSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const provider = asText(root.provider)
  const enabled = asBoolean(root.enabled)
  const credentialPresent = asBoolean(root.credential_present)
  const credentialSource = asText(root.credential_source)
  const reason = asText(root.reason)
  if (
    !provider ||
    enabled === null ||
    credentialPresent === null ||
    !reason ||
    (credentialSource !== 'none' && credentialSource !== 'env' && credentialSource !== 'config_present')
  ) {
    return null
  }
  return {
    provider,
    enabled,
    credentialPresent,
    credentialSource,
    reason,
  }
}

function asProviderSelectionState(value: unknown): ProviderSelectionStateSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const requestedProviderRaw = root.requested_provider
  const selectedProvider = asText(root.selected_provider)
  const allowed = asBoolean(root.allowed)
  const fallbackUsed = asBoolean(root.fallback_used)
  const reason = asText(root.reason)
  if (
    !(requestedProviderRaw === null || typeof requestedProviderRaw === 'string') ||
    !selectedProvider ||
    allowed === null ||
    fallbackUsed === null ||
    !reason
  ) {
    return null
  }
  const requestedProvider = typeof requestedProviderRaw === 'string' ? requestedProviderRaw : null
  return {
    requestedProvider,
    selectedProvider,
    allowed,
    fallbackUsed,
    reason,
  }
}

function asProviderReadinessSummary(value: unknown): ProviderReadinessSummarySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const provider = asText(root.provider)
  const enabled = asBoolean(root.enabled)
  const credentialPresent = asBoolean(root.credential_present)
  const canExecute = asBoolean(root.can_execute)
  const reason = asText(root.reason)
  if (!provider || enabled === null || credentialPresent === null || canExecute === null || !reason) {
    return null
  }
  return {
    provider,
    enabled,
    credentialPresent,
    canExecute,
    reason,
  }
}

function asProviderCapability(value: unknown): ProviderCapabilitySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const provider = asText(root.provider)
  const enabled = asBoolean(root.enabled)
  const networkRequired = asBoolean(root.network_required)
  const supportsRender = asBoolean(root.supports_render)
  const supportsStreaming = asBoolean(root.supports_streaming)
  const supportsSync = asBoolean(root.supports_sync)
  const supportsMultiShot = asBoolean(root.supports_multi_shot)
  const requiresCredentials = asBoolean(root.requires_credentials)
  if (
    !provider ||
    enabled === null ||
    networkRequired === null ||
    supportsRender === null ||
    supportsStreaming === null ||
    supportsSync === null ||
    supportsMultiShot === null ||
    requiresCredentials === null
  ) {
    return null
  }
  return {
    provider,
    enabled,
    networkRequired,
    supportsRender,
    supportsStreaming,
    supportsSync,
    supportsMultiShot,
    requiresCredentials,
  }
}

function asProviderControlContract(value: unknown): ProviderControlContractSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const selectionMode = asText(root.selection_mode)
  const autoExecution = asBoolean(root.auto_execution)
  const executionOnSelect = asBoolean(root.execution_on_select)
  const reason = asText(root.reason)
  if (selectionMode !== 'manual_only' || autoExecution === null || executionOnSelect === null || !reason) {
    return null
  }
  return {
    selectionMode,
    autoExecution,
    executionOnSelect,
    reason,
  }
}

function asProviderSafetyContract(value: unknown): ProviderSafetyContractSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const realProviderExecutionEnabled = asBoolean(root.real_provider_execution_enabled)
  const reason = asText(root.reason)
  if (realProviderExecutionEnabled === null || !reason) {
    return null
  }
  return {
    realProviderExecutionEnabled,
    reason,
  }
}

function asProviderAdapterStatus(value: unknown): ProviderAdapterStatusSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const provider = asText(root.provider)
  const enabled = asBoolean(root.enabled)
  if (!provider || enabled === null) {
    return null
  }
  return { provider, enabled }
}

function asProviderAdapterReadinessGate(value: unknown): ProviderAdapterReadinessGateSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const ready = asBoolean(root.ready)
  if (ready === null) {
    return null
  }
  return { ready }
}

function asExecutionUnlockState(value: unknown): ExecutionUnlockStateSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const locked = asBoolean(root.locked)
  if (locked === null) {
    return null
  }
  return { locked }
}

function asExecutionEligibility(value: unknown): ExecutionEligibilitySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const eligible = asBoolean(root.eligible)
  if (eligible === null) {
    return null
  }
  return { eligible }
}

function asExecutionRequestEnvelope(value: unknown): ExecutionRequestEnvelopeSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const request = asText(root.request)
  if (!request) {
    return null
  }
  return { request }
}

function asRequestSchemaValidation(value: unknown): RequestSchemaValidationSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const valid = asBoolean(root.valid)
  if (valid === null) {
    return null
  }
  return { valid }
}

function asProviderValidation(value: unknown): ProviderValidationSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const valid = asBoolean(root.valid)
  if (valid === null) {
    return null
  }
  return { valid }
}

function asPayloadSanitization(value: unknown): PayloadSanitizationSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const safe = asBoolean(root.safe)
  if (safe === null) {
    return null
  }
  return { safe }
}

function asShotQueueEntry(value: unknown): ShotQueueEntrySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const shotId = asText(root.shot_id)
  const status = asText(root.status)
  const sceneIdRaw = root.scene_id
  if (!shotId || !status || !(sceneIdRaw === null || typeof sceneIdRaw === 'string')) {
    return null
  }
  return {
    shotId,
    sceneId: typeof sceneIdRaw === 'string' ? sceneIdRaw : null,
    status,
  }
}

function asShotQueue(value: unknown): ShotQueueEntrySnapshot[] | null {
  if (!Array.isArray(value)) return null
  const rows: ShotQueueEntrySnapshot[] = []
  for (const item of value) {
    const parsed = asShotQueueEntry(item)
    if (parsed) {
      rows.push(parsed)
    }
  }
  return rows
}

function asMultiShotReadiness(value: unknown): MultiShotReadinessSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const ready = asNumber(root.ready)
  if (ready === null || !Number.isInteger(ready) || ready < 0) {
    return null
  }
  return { ready }
}

function asMultiShotResult(value: unknown): MultiShotResultSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const shotId = asText(root.shot_id)
  const sceneId = asText(root.scene_id)
  const renderId = asText(root.render_id)
  const status = asText(root.status)
  const provider = asText(root.provider)
  if (!shotId || !sceneId || !renderId || !status || !provider) {
    return null
  }
  return {
    shotId,
    sceneId,
    renderId,
    status,
    provider,
  }
}

function asMultiShotResults(value: unknown): MultiShotResultSnapshot[] | null {
  if (!Array.isArray(value)) return null
  const rows: MultiShotResultSnapshot[] = []
  for (const item of value) {
    const parsed = asMultiShotResult(item)
    if (parsed) rows.push(parsed)
  }
  return rows
}

function asShotExecutionLedgerEntry(value: unknown): ShotExecutionLedgerEntrySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const shotId = asText(root.shot_id)
  const sceneId = asText(root.scene_id)
  const status = asText(root.status)
  const renderIdRaw = root.render_id
  const filePathRaw = root.file_path
  const urlRaw = root.url
  const metaRoot = asRecord(root.meta)
  const metaFilePathRaw = metaRoot?.file_path
  const metaUrlRaw = metaRoot?.url
  const resolvedFilePath =
    typeof filePathRaw === 'string'
      ? filePathRaw
      : typeof metaFilePathRaw === 'string'
        ? metaFilePathRaw
        : null
  const resolvedUrl =
    typeof urlRaw === 'string' ? urlRaw : typeof metaUrlRaw === 'string' ? metaUrlRaw : null
  if (
    !shotId ||
    !status ||
    !(renderIdRaw === null || renderIdRaw === undefined || typeof renderIdRaw === 'string') ||
    !(resolvedFilePath === null || typeof resolvedFilePath === 'string') ||
    !(resolvedUrl === null || typeof resolvedUrl === 'string')
  ) {
    return null
  }
  return {
    shotId,
    sceneId: sceneId ?? null,
    status,
    renderId: typeof renderIdRaw === 'string' ? renderIdRaw : null,
    ...(typeof resolvedFilePath === 'string' ? { filePath: resolvedFilePath } : {}),
    ...(typeof resolvedUrl === 'string' ? { url: resolvedUrl } : {}),
  }
}

function asShotExecutionLedger(value: unknown): ShotExecutionLedgerEntrySnapshot[] | null {
  if (!Array.isArray(value)) return null
  const rows: ShotExecutionLedgerEntrySnapshot[] = []
  for (const item of value) {
    const parsed = asShotExecutionLedgerEntry(item)
    if (parsed) {
      rows.push(parsed)
    }
  }
  return rows
}

function asMultiShotExecutionLedgerEntry(value: unknown): MultiShotExecutionLedgerEntrySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const shotId = asText(root.shot_id)
  const status = asText(root.status)
  const renderIdRaw = root.render_id
  if (!shotId || !status || !(renderIdRaw === null || renderIdRaw === undefined || typeof renderIdRaw === 'string')) {
    return null
  }
  return {
    shotId,
    status,
    renderId: typeof renderIdRaw === 'string' ? renderIdRaw : null,
  }
}

function asMultiShotExecutionLedger(value: unknown): MultiShotExecutionLedgerEntrySnapshot[] | null {
  if (!Array.isArray(value)) return null
  const rows: MultiShotExecutionLedgerEntrySnapshot[] = []
  for (const item of value) {
    const parsed = asMultiShotExecutionLedgerEntry(item)
    if (parsed) rows.push(parsed)
  }
  return rows
}

function asMultiShotTakeArtifact(value: unknown): MultiShotTakeArtifactSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const iteration = asNumber(root.iteration)
  const shotId = asText(root.shot_id)
  const renderId = asText(root.render_id)
  const status = asText(root.status)
  if (iteration === null || !Number.isInteger(iteration) || iteration < 1 || !shotId || !renderId || !status) {
    return null
  }
  return {
    iteration,
    shotId,
    renderId,
    status,
  }
}

function asMultiShotTakeArtifacts(value: unknown): MultiShotTakeArtifactSnapshot[] | null {
  if (!Array.isArray(value)) return null
  const rows: MultiShotTakeArtifactSnapshot[] = []
  for (const item of value) {
    const parsed = asMultiShotTakeArtifact(item)
    if (parsed) rows.push(parsed)
  }
  return rows
}

function asSceneGenerationSummary(value: unknown): SceneGenerationSummarySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const plannedShots = asNumber(root.planned_shots)
  const completedShots = asNumber(root.completed_shots)
  const provider = asText(root.provider)
  const status = asText(root.status)
  if (
    plannedShots === null ||
    !Number.isInteger(plannedShots) ||
    plannedShots < 0 ||
    completedShots === null ||
    !Number.isInteger(completedShots) ||
    completedShots < 0 ||
    !provider ||
    (status !== 'complete' && status !== 'partial' && status !== 'not_started')
  ) {
    return null
  }
  return {
    plannedShots,
    completedShots,
    provider,
    status,
  }
}

function asScenePlaybackPreview(value: unknown): ScenePlaybackPreviewSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const available = asBoolean(root.available)
  const shotCount = asNumber(root.shot_count)
  const renderIds = asStringArray(root.render_ids)
  const status = asText(root.status)
  if (
    available === null ||
    shotCount === null ||
    !Number.isInteger(shotCount) ||
    shotCount < 0 ||
    renderIds === null ||
    !status
  ) {
    return null
  }
  return {
    available,
    shotCount,
    renderIds,
    status,
  }
}

function asMultiShotExecutionContract(value: unknown): MultiShotExecutionContractSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const provider = asText(root.provider)
  const maxShotsPerRun = asNumber(root.max_shots_per_run)
  const realProvidersEnabled = asBoolean(root.real_providers_enabled)
  const retriesEnabled = asBoolean(root.retries_enabled)
  const asyncEnabled = asBoolean(root.async_enabled)
  const reason = asText(root.reason)
  if (
    provider !== 'mock_only' ||
    maxShotsPerRun === null ||
    !Number.isInteger(maxShotsPerRun) ||
    maxShotsPerRun < 0 ||
    realProvidersEnabled === null ||
    retriesEnabled === null ||
    asyncEnabled === null ||
    !reason
  ) {
    return null
  }
  return {
    provider: 'mock_only',
    maxShotsPerRun,
    realProvidersEnabled,
    retriesEnabled,
    asyncEnabled,
    reason,
  }
}

function deriveLocalRenderOutput(value: unknown): LocalRenderOutputSnapshot {
  const root = asRecord(value)
  const hasOutput = asBoolean(root?.has_output) ?? false
  const renderIdRaw = root?.render_id
  const filePathRaw = root?.file_path
  const artifactTypeRaw = root?.artifact_type
  const status = asText(root?.status) ?? 'not_executed'
  return {
    hasOutput,
    renderId: typeof renderIdRaw === 'string' ? renderIdRaw : null,
    filePath: typeof filePathRaw === 'string' ? filePathRaw : null,
    artifactType: typeof artifactTypeRaw === 'string' ? artifactTypeRaw : null,
    status,
  }
}

function deriveLocalArtifactLog(value: unknown): LocalArtifactLogSnapshot {
  const root = asRecord(value)
  const executed = asBoolean(root?.executed) ?? false
  const shotIdRaw = root?.shot_id
  const filePathRaw = root?.file_path
  return {
    executed,
    shotId: typeof shotIdRaw === 'string' ? shotIdRaw : null,
    filePath: typeof filePathRaw === 'string' ? filePathRaw : null,
    timestamp: null,
  }
}

function deriveMockRenderOutput(
  executionResultV2: ExecutionResultV2Snapshot | null,
  provider: string
): MockRenderOutputSnapshot {
  const status = executionResultV2?.status ?? 'not_executed'
  return {
    renderId: executionResultV2?.renderId ?? null,
    status,
    provider: executionResultV2?.provider ?? (provider || 'mock'),
    hasOutput: status === 'success',
  }
}

function deriveExecutionPathTrace(
  sceneIntent: SceneIntentSnapshot | null,
  requestSchemaValidation: RequestSchemaValidationSnapshot | null,
  executionEligibility: ExecutionEligibilitySnapshot | null
): ExecutionPathTraceSnapshot {
  const intentPresent = sceneIntent !== null
  const requestValid = requestSchemaValidation?.valid ?? false
  const eligible = executionEligibility?.eligible ?? false
  const blocked = !eligible
  return {
    intentPresent,
    requestValid,
    eligible,
    blocked,
  }
}

function issueCounts(issues: unknown): { issueCount: number | null; criticalIssueCount: number; warningCount: number } {
  if (!Array.isArray(issues)) {
    return { issueCount: null, criticalIssueCount: 0, warningCount: 0 }
  }
  let criticalIssueCount = 0
  let warningCount = 0
  for (const issue of issues) {
    const severity = asText(asRecord(issue)?.severity)
    if (severity === 'critical') criticalIssueCount += 1
    if (severity === 'warning') warningCount += 1
  }
  return { issueCount: issues.length, criticalIssueCount, warningCount }
}

function getValidationRoot(summary: Record<string, unknown>): Record<string, unknown> | null {
  const keys = ['validation_inspection', 'validation_report', 'render_validation_report', 'render_validation'] as const
  for (const key of keys) {
    const parsed = asRecord(summary[key])
    if (parsed) {
      return parsed
    }
  }

  if (asText(summary.advisory_disposition)) {
    return summary
  }
  return null
}

function extractValidationInspection(summary: Record<string, unknown>): ValidationInspectionSnapshot | null {
  const validation = getValidationRoot(summary)
  if (!validation) {
    return null
  }

  const counts = issueCounts(validation.issues)
  return {
    advisoryDisposition: asText(validation.advisory_disposition),
    advisoryConfidence: asNumber(validation.advisory_confidence),
    packageFidelity: asNumber(validation.package_fidelity),
    toneAlignment: asNumber(validation.tone_alignment),
    motifAlignment: asNumber(validation.motif_alignment),
    continuityAlignment: asNumber(validation.continuity_alignment),
    cinematicAlignment: asNumber(validation.cinematic_alignment),
    issueCount: counts.issueCount,
    criticalIssueCount: counts.criticalIssueCount,
    warningCount: counts.warningCount,
  }
}

function asPrevisSceneBoardEntry(value: unknown): PrevisSceneBoardEntrySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const sceneId = asText(root.scene_id)
  const shotCount = asNumber(root.shot_count)
  const linkedRefsRaw = root.linked_refs
  if (!sceneId || shotCount === null || shotCount < 0) return null
  const linkedRefs = asStringArray(linkedRefsRaw)
  if (linkedRefs === null) return null
  return { sceneId, shotCount, linkedRefs }
}

function asPrevisSceneBoard(value: unknown): PrevisSceneBoardEntrySnapshot[] | null {
  if (!Array.isArray(value)) return null
  const entries: PrevisSceneBoardEntrySnapshot[] = []
  for (const item of value) {
    const parsed = asPrevisSceneBoardEntry(item)
    if (parsed) entries.push(parsed)
  }
  return entries
}

function asPrevisBeatShotMapEntry(value: unknown): PrevisBeatShotMapEntrySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const beatId = asText(root.beat_id)
  const sceneId = asText(root.scene_id)
  const shots = asStringArray(root.shots)
  if (!beatId || !sceneId || shots === null) return null
  return { beatId, sceneId, shots }
}

function asPrevisBeatShotMap(value: unknown): PrevisBeatShotMapEntrySnapshot[] | null {
  if (!Array.isArray(value)) return null
  const entries: PrevisBeatShotMapEntrySnapshot[] = []
  for (const item of value) {
    const parsed = asPrevisBeatShotMapEntry(item)
    if (parsed) entries.push(parsed)
  }
  return entries
}

function asPrevisContinuityMapEntry(value: unknown): PrevisContinuityMapEntrySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const sceneId = asText(root.scene_id)
  const checks = asStringArray(root.checks)
  if (!sceneId || checks === null) return null
  return { sceneId, checks }
}

function asPrevisContinuityMap(value: unknown): PrevisContinuityMapEntrySnapshot[] | null {
  if (!Array.isArray(value)) return null
  const entries: PrevisContinuityMapEntrySnapshot[] = []
  for (const item of value) {
    const parsed = asPrevisContinuityMapEntry(item)
    if (parsed) entries.push(parsed)
  }
  return entries
}

function asPrevisAssetMapEntry(value: unknown): PrevisAssetMapEntrySnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const assetId = asText(root.asset_id)
  const scenes = asStringArray(root.scenes)
  if (!assetId || scenes === null) return null
  return { assetId, scenes }
}

function asPrevisAssetMap(value: unknown): PrevisAssetMapEntrySnapshot[] | null {
  if (!Array.isArray(value)) return null
  const entries: PrevisAssetMapEntrySnapshot[] = []
  for (const item of value) {
    const parsed = asPrevisAssetMapEntry(item)
    if (parsed) entries.push(parsed)
  }
  return entries
}

function asPrevisContract(value: unknown): PrevisContractSnapshot | null {
  const root = asRecord(value)
  if (!root) return null
  const mode = asText(root.mode)
  const authority = asText(root.authority)
  const executionEnabled = asBoolean(root.execution_enabled)
  if (mode !== 'read_only' || authority !== 'none' || executionEnabled === null) return null
  return { mode: 'read_only', authority: 'none', executionEnabled }
}

function getSummaryRoot(project: StudioProject | null): Record<string, unknown> | null {
  const root = asRecord(project)
  if (!root) {
    return null
  }

  const candidates: unknown[] = [
    root.execution_summary,
    asRecord(root.interactive_modules)?.execution_summary,
    asRecord(root.interactive_modules)?.render_execution_summary,
    asRecord(root.producer_dashboard)?.execution_summary,
    asRecord(root.project_dashboard)?.execution_summary,
  ]

  for (const candidate of candidates) {
    const parsed = asRecord(candidate)
    if (parsed) {
      return parsed
    }
  }

  return null
}

export function extractExecutionSummaryInspection(project: StudioProject | null): ExecutionSummaryInspectionSnapshot | null {
  const summary = getSummaryRoot(project)
  if (!summary) {
    return null
  }

  const providerName = asText(summary.provider_name) ?? 'unknown'
  const lifecycleState = asText(summary.lifecycle_state) ?? 'unknown'

  const validationInspection = extractValidationInspection(summary)
  const previsSceneBoard = asPrevisSceneBoard(summary.previs_scene_board)
  const previsBeatShotMap = asPrevisBeatShotMap(summary.previs_beat_shot_map)
  const previsContinuityMap = asPrevisContinuityMap(summary.previs_continuity_map)
  const previsAssetMap = asPrevisAssetMap(summary.previs_asset_map)
  const previsContract = asPrevisContract(summary.previs_contract)
  const visualReferences = asVisualReferences(summary.visual_references)
  const visualReferenceIndexes = asVisualReferenceIndexes(summary.visual_reference_indexes)
  const visualReferenceSummary = asVisualReferenceSummary(summary.visual_reference_summary)
  const visualPatternSummary = asVisualPatternSummary(summary.visual_pattern_summary)
  const sceneVisualIdentity = asSceneVisualIdentity(summary.scene_visual_identity)
  const visualConsistency = asVisualConsistency(summary.visual_consistency)
  const visualTension = asVisualTension(summary.visual_tension)
  const frameMetadata = asFrameMetadata(summary.frame_metadata)
  const frameStats = asFrameStats(summary.frame_stats)
  const frameAnalysisSnapshot = asFrameAnalysisSnapshot(summary.frame_analysis_snapshot)
  const sceneVisualLinks = asSceneVisualLinks(summary.scene_visual_links)
  const linkCompleteness = asLinkCompleteness(summary.link_completeness)
  const shotCandidates = asShotCandidates(summary.shot_candidates)
  const shotCoverage = asShotCoverage(summary.shot_coverage)
  const shotPlanBundle = asShotPlanBundle(summary.shot_plan_bundle)
  const shotIntent = asShotIntent(summary.shot_intent)
  const shotVariety = asShotVariety(summary.shot_variety)
  const sceneCoverage = asSceneCoverage(summary.scene_coverage)
  const shotPlanningSummary = asShotPlanningSummary(summary.shot_planning_summary)
  const shotAdvisoryNote = asShotAdvisoryNote(summary.shot_advisory_note)
  const sceneSequence = asSceneSequence(summary.scene_sequence)
  const sceneAssembly = asSceneAssembly(summary.scene_assembly)
  const sequenceStatus = asSequenceStatus(summary.sequence_status)
  const sceneContinuityCheck = asSceneContinuityCheck(summary.scene_continuity_check)
  const scenePlaybackStatus = asScenePlaybackStatus(summary.scene_playback_status)
  const coDirectorVisualObservation = asCoDirectorVisualObservation(summary.co_director_visual_observation)
  const coDirectorShotObservation = asCoDirectorShotObservation(summary.co_director_shot_observation)
  const coDirectorObservationSummary = asCoDirectorObservationSummary(summary.co_director_observation_summary)
  const coDirectorObservationContract = asCoDirectorObservationContract(summary.co_director_observation_contract)
  const outputInfluenceGuardV2 = asOutputInfluenceGuardV2(summary.output_influence_guard_v2)
  const visualDecisionBoundary = asVisualDecisionBoundary(summary.visual_decision_boundary)
  const shotExecutionLock = asShotExecutionLock(summary.shot_execution_lock)
  const boundaryAudit = asBoundaryAudit(summary.boundary_audit)
  const studioSafetyState = asStudioSafetyState(summary.studio_safety_state)
  const promptInfluenceGateV1 = asPromptInfluenceGateV1(summary.prompt_influence_gate_v1)
  const visualPromptTokens = asStringArray(summary.visual_prompt_tokens)
  const shotPromptTokens = asStringArray(summary.shot_prompt_tokens)
  const promptEnvelope = asPromptEnvelope(summary.prompt_envelope)
  const promptSafetyContract = asPromptSafetyContract(summary.prompt_safety_contract)
  const renderActivationGateV1 = asRenderActivationGateV1(summary.render_activation_gate_v1)
  const renderRequest = summary.render_request === null ? null : asRenderRequest(summary.render_request)
  const renderOutput = summary.render_output === null ? null : asRenderOutput(summary.render_output)
  const outputReview = summary.output_review === null ? null : asOutputReview(summary.output_review)
  const outputEvaluation = asOutputEvaluation(summary.output_evaluation)
  const retryGate = asRetryGate(summary.retry_gate)
  const executionSnapshot = asExecutionSnapshot(summary.execution_snapshot)
  const iterationRecord = asIterationRecord(summary.iteration_record)
  const takeHistory = asTakeHistory(summary.take_history)
  const takeArtifacts = asTakeArtifacts(summary.take_artifacts)
  const retrySnapshot = asRetrySnapshot(summary.retry_snapshot)
  const takeComparison = asTakeComparison(summary.take_comparison)
  const takeComparisonV2 = asTakeComparisonV2(summary.take_comparison_v2)
  const takePreferenceContract = asTakePreferenceContract(summary.take_preference_contract)
  const takeAdvisoryNote = asTakeAdvisoryNote(summary.take_advisory_note)
  const outputReviewMatrix = asOutputReviewMatrix(summary.output_review_matrix)
  const loopReadiness = asLoopReadiness(summary.loop_readiness)
  const nextTakePreview = asNextTakePreview(summary.next_take_preview)
  const loopConstraint = asLoopConstraint(summary.loop_constraint)
  const loopAdvisory = asLoopAdvisory(summary.loop_advisory)
  const loopContract = asLoopContract(summary.loop_contract)
  const loopExecutionPlan = asLoopExecutionPlan(summary.loop_execution_plan)
  const simulatedIteration = asSimulatedIteration(summary.simulated_iteration)
  const simulatedOutput = asSimulatedOutput(summary.simulated_output)
  const loopResultSnapshot = asLoopResultSnapshot(summary.loop_result_snapshot)
  const loopExecutionContract = asLoopExecutionContract(summary.loop_execution_contract)
  const executionPermission = asExecutionPermission(summary.execution_permission)
  const executionRequest = asExecutionRequest(summary.execution_request)
  const executionStatus = asExecutionStatus(summary.execution_status)
  const executionResult = asExecutionResult(summary.execution_result)
  const providerPayload = asProviderPayload(summary.provider_payload)
  const providerPayloadV2 = asProviderPayloadV2(summary.provider_payload_v2)
  const handoffEnvelope = asHandoffEnvelope(summary.handoff_envelope)
  const handoffAudit = asHandoffAudit(summary.handoff_audit)
  const executionResultV2 = asExecutionResultV2(summary.execution_result_v2)
  const localRenderOutput = deriveLocalRenderOutput(summary.local_render_output)
  const localArtifactLog = deriveLocalArtifactLog(summary.local_artifact_log)
  const mockRenderOutput = deriveMockRenderOutput(
    executionResultV2,
    providerName
  )
  const executionPathTrace = deriveExecutionPathTrace(
    asSceneIntent(summary.scene_intent),
    asRequestSchemaValidation(summary.request_schema_validation),
    asExecutionEligibility(summary.execution_eligibility)
  )
  const outputSync = asOutputSync(summary.output_sync)
  const executionMonitor = asExecutionMonitor(summary.execution_monitor)
  const providerConfigSnapshot = asProviderConfigSnapshot(summary.provider_config_snapshot)
  const providerCredentialState = asProviderCredentialState(summary.provider_credential_state)
  const providerSelectionState = asProviderSelectionState(summary.provider_selection_state)
  const providerReadinessSummary = asProviderReadinessSummary(summary.provider_readiness_summary)
  const providerCapability = asProviderCapability(summary.provider_capability)
  const providerControlContract = asProviderControlContract(summary.provider_control_contract)
  const providerSafetyContract = asProviderSafetyContract(summary.provider_safety_contract)
  const providerAdapterStatus = asProviderAdapterStatus(summary.provider_adapter_status)
  const providerAdapterReadinessGate = asProviderAdapterReadinessGate(summary.provider_adapter_readiness_gate)
  const executionUnlockState = asExecutionUnlockState(summary.execution_unlock_state)
  const executionEligibility = asExecutionEligibility(summary.execution_eligibility)
  const executionRequestEnvelope = asExecutionRequestEnvelope(summary.execution_request_envelope)
  const requestSchemaValidation = asRequestSchemaValidation(summary.request_schema_validation)
  const providerValidation = asProviderValidation(summary.provider_validation)
  const payloadSanitization = asPayloadSanitization(summary.payload_sanitization)
  const shotQueue = asShotQueue(summary.shot_queue)
  const multiShotReadiness = asMultiShotReadiness(summary.multi_shot_readiness)
  const multiShotResults = asMultiShotResults(summary.multi_shot_results)
  const shotExecutionLedger = asShotExecutionLedger(summary.shot_execution_ledger)
  const multiShotExecutionLedger = asMultiShotExecutionLedger(summary.multi_shot_execution_ledger)
  const multiShotTakeArtifacts = asMultiShotTakeArtifacts(summary.multi_shot_take_artifacts)
  const sceneGenerationSummary = asSceneGenerationSummary(summary.scene_generation_summary)
  const scenePlaybackPreview = asScenePlaybackPreview(summary.scene_playback_preview)
  const multiShotExecutionContract = asMultiShotExecutionContract(summary.multi_shot_execution_contract)
  const executionContract = asExecutionContract(summary.execution_contract)
  const coDirectorVisualFeed = asCoDirectorVisualFeed(summary.co_director_visual_feed)
  return {
    providerName,
    lifecycleState,
    productionSignal: asProductionSignal(summary.production_signal),
    sceneIntent: asSceneIntent(summary.scene_intent),
    intentSignal: asIntentSignal(summary.intent_signal),
    intentOutputSignal: asIntentOutputSignal(summary.intent_output_signal),
    intentOutputRelation: asIntentOutputRelation(summary.intent_output_relation),
    providerStatus: asText(summary.provider_status),
    hasOutputArtifacts: asBoolean(summary.has_output_artifacts) ?? false,
    hasError: asBoolean(summary.has_error) ?? false,
    latestUpdatedAt: asText(summary.latest_updated_at),
    renderBehavior: asRenderBehavior(summary.render_behavior),
    interventionSuggestion: asInterventionSuggestion(summary.intervention_suggestion),
    recurringPattern: asRecurringPattern(summary.recurring_pattern),
    memoryAdvisoryProjection: asMemoryAdvisoryProjection(summary.memory_advisory_projection),
    memorySnapshotSummary: asMemorySnapshotSummary(summary.memory_snapshot_summary),
    memoryStateRollup: asMemoryStateRollup(summary.memory_state_rollup),
    memoryConsistency: asMemoryConsistency(summary.memory_consistency),
    memoryCategoryPresence: asMemoryCategoryPresence(summary.memory_category_presence),
    coDirectorMemoryVisibility: asCoDirectorMemoryVisibility(summary.co_director_memory_visibility),
    coDirectorMemoryAdvisory: asCoDirectorMemoryAdvisory(summary.co_director_memory_advisory),
    coDirectorMemoryAuthorityBoundary: asCoDirectorMemoryAuthorityBoundary(
      summary.co_director_memory_authority_boundary
    ),
    ...(coDirectorVisualFeed !== null ? { coDirectorVisualFeed } : {}),
    ...(visualReferences !== null ? { visualReferences } : {}),
    ...(visualReferenceIndexes !== null ? { visualReferenceIndexes } : {}),
    ...(visualReferenceSummary !== null ? { visualReferenceSummary } : {}),
    ...(visualPatternSummary !== null ? { visualPatternSummary } : {}),
    ...(sceneVisualIdentity !== null ? { sceneVisualIdentity } : {}),
    ...(visualConsistency !== null ? { visualConsistency } : {}),
    ...(visualTension !== null ? { visualTension } : {}),
    ...(frameMetadata !== null ? { frameMetadata } : {}),
    ...(frameStats !== null ? { frameStats } : {}),
    ...(frameAnalysisSnapshot !== null ? { frameAnalysisSnapshot } : {}),
    ...(sceneVisualLinks !== null ? { sceneVisualLinks } : {}),
    ...(linkCompleteness !== null ? { linkCompleteness } : {}),
    ...(shotCandidates !== null ? { shotCandidates } : {}),
    ...(shotCoverage !== null ? { shotCoverage } : {}),
    ...(shotPlanBundle !== null ? { shotPlanBundle } : {}),
    ...(shotIntent !== null ? { shotIntent } : {}),
    ...(shotVariety !== null ? { shotVariety } : {}),
    ...(sceneCoverage !== null ? { sceneCoverage } : {}),
    ...(shotPlanningSummary !== null ? { shotPlanningSummary } : {}),
    ...(shotAdvisoryNote !== null ? { shotAdvisoryNote } : {}),
    ...(sceneSequence !== null ? { sceneSequence } : {}),
    ...(sceneAssembly !== null ? { sceneAssembly } : {}),
    ...(sequenceStatus !== null ? { sequenceStatus } : {}),
    ...(sceneContinuityCheck !== null ? { sceneContinuityCheck } : {}),
    ...(scenePlaybackStatus !== null ? { scenePlaybackStatus } : {}),
    ...(coDirectorVisualObservation !== null ? { coDirectorVisualObservation } : {}),
    ...(coDirectorShotObservation !== null ? { coDirectorShotObservation } : {}),
    ...(coDirectorObservationSummary !== null ? { coDirectorObservationSummary } : {}),
    ...(coDirectorObservationContract !== null ? { coDirectorObservationContract } : {}),
    ...(outputInfluenceGuardV2 !== null ? { outputInfluenceGuardV2 } : {}),
    ...(visualDecisionBoundary !== null ? { visualDecisionBoundary } : {}),
    ...(shotExecutionLock !== null ? { shotExecutionLock } : {}),
    ...(boundaryAudit !== null ? { boundaryAudit } : {}),
    ...(studioSafetyState !== null ? { studioSafetyState } : {}),
    ...(promptInfluenceGateV1 !== null ? { promptInfluenceGateV1 } : {}),
    ...(visualPromptTokens !== null ? { visualPromptTokens } : {}),
    ...(shotPromptTokens !== null ? { shotPromptTokens } : {}),
    ...(promptEnvelope !== null ? { promptEnvelope } : {}),
    ...(promptSafetyContract !== null ? { promptSafetyContract } : {}),
    ...(renderActivationGateV1 !== null ? { renderActivationGateV1 } : {}),
    ...(summary.render_request === null ? { renderRequest: null } : {}),
    ...(renderRequest !== null ? { renderRequest } : {}),
    ...(summary.render_output === null ? { renderOutput: null } : {}),
    ...(renderOutput !== null ? { renderOutput } : {}),
    ...(summary.output_review === null ? { outputReview: null } : {}),
    ...(outputReview !== null ? { outputReview } : {}),
    ...(outputEvaluation !== null ? { outputEvaluation } : {}),
    ...(retryGate !== null ? { retryGate } : {}),
    ...(executionSnapshot !== null ? { executionSnapshot } : {}),
    ...(iterationRecord !== null ? { iterationRecord } : {}),
    ...(takeHistory !== null ? { takeHistory } : {}),
    ...(takeArtifacts !== null ? { takeArtifacts } : {}),
    ...(retrySnapshot !== null ? { retrySnapshot } : {}),
    ...(takeComparison !== null ? { takeComparison } : {}),
    ...(takeComparisonV2 !== null ? { takeComparisonV2 } : {}),
    ...(takePreferenceContract !== null ? { takePreferenceContract } : {}),
    ...(takeAdvisoryNote !== null ? { takeAdvisoryNote } : {}),
    ...(outputReviewMatrix !== null ? { outputReviewMatrix } : {}),
    ...(loopReadiness !== null ? { loopReadiness } : {}),
    ...(nextTakePreview !== null ? { nextTakePreview } : {}),
    ...(loopConstraint !== null ? { loopConstraint } : {}),
    ...(loopAdvisory !== null ? { loopAdvisory } : {}),
    ...(loopContract !== null ? { loopContract } : {}),
    ...(loopExecutionPlan !== null ? { loopExecutionPlan } : {}),
    ...(simulatedIteration !== null ? { simulatedIteration } : {}),
    ...(simulatedOutput !== null ? { simulatedOutput } : {}),
    ...(loopResultSnapshot !== null ? { loopResultSnapshot } : {}),
    ...(loopExecutionContract !== null ? { loopExecutionContract } : {}),
    ...(executionPermission !== null ? { executionPermission } : {}),
    ...(executionRequest !== null ? { executionRequest } : {}),
    ...(executionStatus !== null ? { executionStatus } : {}),
    ...(executionResult !== null ? { executionResult } : {}),
    ...(providerPayload !== null ? { providerPayload } : {}),
    ...(providerPayloadV2 !== null ? { providerPayloadV2 } : {}),
    ...(handoffEnvelope !== null ? { handoffEnvelope } : {}),
    ...(handoffAudit !== null ? { handoffAudit } : {}),
    ...(executionResultV2 !== null ? { executionResultV2 } : {}),
    ...(
      Object.prototype.hasOwnProperty.call(summary, 'local_render_output')
        ? { localRenderOutput }
        : {}
    ),
    ...(
      Object.prototype.hasOwnProperty.call(summary, 'local_artifact_log')
        ? { localArtifactLog }
        : {}
    ),
    ...(
      Object.prototype.hasOwnProperty.call(summary, 'execution_result_v2')
        ? { mockRenderOutput }
        : {}
    ),
    ...(
      Object.prototype.hasOwnProperty.call(summary, 'request_schema_validation') ||
      Object.prototype.hasOwnProperty.call(summary, 'execution_eligibility')
        ? { executionPathTrace }
        : {}
    ),
    ...(outputSync !== null ? { outputSync } : {}),
    ...(executionMonitor !== null ? { executionMonitor } : {}),
    ...(providerConfigSnapshot !== null ? { providerConfigSnapshot } : {}),
    ...(providerCredentialState !== null ? { providerCredentialState } : {}),
    ...(providerSelectionState !== null ? { providerSelectionState } : {}),
    ...(providerReadinessSummary !== null ? { providerReadinessSummary } : {}),
    ...(providerCapability !== null ? { providerCapability } : {}),
    ...(providerControlContract !== null ? { providerControlContract } : {}),
    ...(providerSafetyContract !== null ? { providerSafetyContract } : {}),
    ...(providerAdapterStatus !== null ? { providerAdapterStatus } : {}),
    ...(providerAdapterReadinessGate !== null ? { providerAdapterReadinessGate } : {}),
    ...(executionContract !== null ? { executionContract } : {}),
    ...(executionUnlockState !== null ? { executionUnlockState } : {}),
    ...(executionEligibility !== null ? { executionEligibility } : {}),
    ...(executionRequestEnvelope !== null ? { executionRequestEnvelope } : {}),
    ...(requestSchemaValidation !== null ? { requestSchemaValidation } : {}),
    ...(providerValidation !== null ? { providerValidation } : {}),
    ...(payloadSanitization !== null ? { payloadSanitization } : {}),
    ...(shotQueue !== null ? { shotQueue } : {}),
    ...(multiShotReadiness !== null ? { multiShotReadiness } : {}),
    ...(multiShotResults !== null ? { multiShotResults } : {}),
    ...(shotExecutionLedger !== null ? { shotExecutionLedger } : {}),
    ...(multiShotExecutionLedger !== null ? { multiShotExecutionLedger } : {}),
    ...(multiShotTakeArtifacts !== null ? { multiShotTakeArtifacts } : {}),
    ...(sceneGenerationSummary !== null ? { sceneGenerationSummary } : {}),
    ...(scenePlaybackPreview !== null ? { scenePlaybackPreview } : {}),
    ...(multiShotExecutionContract !== null ? { multiShotExecutionContract } : {}),
    ...(validationInspection ? { validationInspection } : {}),
    ...(previsSceneBoard !== null ? { previsSceneBoard } : {}),
    ...(previsBeatShotMap !== null ? { previsBeatShotMap } : {}),
    ...(previsContinuityMap !== null ? { previsContinuityMap } : {}),
    ...(previsAssetMap !== null ? { previsAssetMap } : {}),
    ...(previsContract !== null ? { previsContract } : {}),
  }
}

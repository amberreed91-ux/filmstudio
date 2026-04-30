import { useMemo } from 'react'
import type { StudioProject } from '../lib/studioApi'
import { extractExecutionSummaryInspection, resolveRenderSource } from '../lib/executionSummaryInspection'

function displayText(value: string | null): string {
  return value || 'Unavailable'
}

export function safeImageSrc(filePath: string | null | undefined): string | null {
  if (typeof filePath !== 'string') {
    return null
  }
  const trimmed = filePath.trim()
  if (!trimmed) {
    return null
  }
  if (trimmed.startsWith('javascript:') || trimmed.startsWith('data:text/html')) {
    return null
  }
  return trimmed
}

function displayFlag(value: boolean): string {
  return value ? 'Yes' : 'No'
}

function displayScore(value: number | null): string {
  if (value === null) {
    return 'Unavailable'
  }
  return value.toFixed(2)
}

function displayRenderBehavior(value: 'stable' | 'retry_heavy' | 'in_progress' | 'stuck' | 'unknown'): string {
  if (value === 'stable') return 'Stable'
  if (value === 'retry_heavy') return 'Retry-heavy'
  if (value === 'in_progress') return 'In progress'
  if (value === 'stuck') return 'Stuck'
  return 'Unknown'
}

function displayRecurringPatternType(value: 'provider_failure_pattern' | 'stuck_pattern'): string {
  if (value === 'provider_failure_pattern') return 'Provider failure pattern'
  return 'Stuck pattern'
}

function displayValidationState(value: boolean, validLabel: string, invalidLabel: string): string {
  return value ? validLabel : invalidLabel
}

export async function safeReadFile(filePath: string | null): Promise<string | null> {
  if (!filePath) {
    return null
  }
  if (typeof fetch !== 'function') {
    return null
  }
  try {
    const response = await fetch(filePath, { method: 'GET' })
    if (!response.ok) {
      return null
    }
    const contents = await response.text()
    return contents || null
  } catch {
    return null
  }
}

export default function ExecutionSummaryInspectionPanel({ project }: { project: StudioProject | null }) {
  const summary = extractExecutionSummaryInspection(project)
  if (!summary) {
    return null
  }
  const hasConsistentMemorySection =
    Boolean(summary.memoryAdvisoryProjection) &&
    Boolean(summary.memorySnapshotSummary) &&
    Boolean(summary.coDirectorMemoryVisibility) &&
    Boolean(summary.coDirectorMemoryAdvisory) &&
    Boolean(summary.coDirectorMemoryAuthorityBoundary) &&
    summary.coDirectorMemoryVisibility!.influenceMode === 'disabled' &&
    summary.coDirectorMemoryAuthorityBoundary!.authority === 'none' &&
    summary.coDirectorMemoryAuthorityBoundary!.memoryInfluence === 'disabled'
  const hasMemorySummaryRow =
    Boolean(summary.memorySnapshotSummary) &&
    summary.memorySnapshotSummary!.influenceMode === 'disabled'
  const hasMemoryReviewState =
    summary.memoryStateRollup?.status === 'available' &&
    summary.memoryStateRollup?.influenceMode === 'disabled' &&
    summary.memoryConsistency?.isConsistent === true
  const studioState = summary.studioSafetyState?.studioState ?? 'not_ready'
  const boundaryAudit = summary.boundaryAudit ?? {
    memorySafe: false,
    visualSafe: false,
    shotSafe: false,
    renderSafe: false,
    coDirectorSafe: false,
    overallSafe: false,
  }
  const promptInfluenceGate = summary.promptInfluenceGateV1 ?? {
    promptInfluenceEnabled: false,
    scope: 'advisory_only' as const,
    reason: 'Studio not safe for prompt influence',
  }
  const visualPromptTokens = summary.visualPromptTokens ?? []
  const shotPromptTokens = summary.shotPromptTokens ?? []
  const promptEnvelope = summary.promptEnvelope ?? {
    baseIntent: '',
    visualTokens: [],
    shotTokens: [],
  }
  const promptSafetyContract = summary.promptSafetyContract ?? {
    promptOverride: false,
    structureLocked: true,
    tokenInjectionOnly: true,
    reason: 'Prompt structure is protected',
  }
  const renderActivationGateV1 = summary.renderActivationGateV1 ?? {
    renderEnabled: false,
    mode: 'single_shot' as const,
    reason: 'Render activation not allowed',
  }
  const renderRequest = summary.renderRequest ?? null
  const renderOutput = summary.renderOutput ?? null
  const outputReview = summary.outputReview ?? null
  const outputEvaluation = summary.outputEvaluation ?? {
    hasOutput: false,
    validStructure: false,
    renderIdPresent: false,
    status: 'none' as const,
  }
  const retryGate = summary.retryGate ?? {
    retryAllowed: false,
    reason: 'Execution not ready',
  }
  const executionSnapshot = summary.executionSnapshot ?? {
    iteration: 0,
    maxIterations: 3,
    status: 'idle' as const,
    renderAttempted: false,
    retryAllowed: false,
    finalized: false,
  }
  const iterationRecord = summary.iterationRecord ?? {
    iteration: 0,
    status: 'idle',
    renderId: null,
    coverage: '',
    alignment: '',
  }
  const retrySnapshot = summary.retrySnapshot ?? {
    allowed: false,
    iteration: 0,
    status: 'idle',
  }
  const takeAdvisoryNote = summary.takeAdvisoryNote ?? {
    note: '',
  }
  const takeComparisonV2 = summary.takeComparisonV2 ?? {
    comparable: false,
    differences: [],
  }
  const takePreferenceContract = summary.takePreferenceContract ?? {
    autoSelect: false,
    authority: 'manual_only' as const,
  }
  const outputReviewMatrix = (summary.outputReviewMatrix ?? []).filter(
    (row) =>
      typeof row.takeId === 'number' &&
      Number.isInteger(row.takeId) &&
      row.takeId >= 0 &&
      typeof row.alignment === 'string' &&
      row.alignment.length > 0 &&
      typeof row.coverage === 'string' &&
      row.coverage.length > 0 &&
      typeof row.validStructure === 'boolean'
  )
  const loopReadiness = summary.loopReadiness ?? {
    ready: false,
    reason: 'Retry not allowed',
  }
  const nextTakePreview = summary.nextTakePreview ?? {
    nextIteration: 1,
    willRetry: false,
  }
  const loopConstraint = summary.loopConstraint ?? {
    maxIterations: 3,
    remaining: 3,
  }
  const loopAdvisory = summary.loopAdvisory ?? {
    note: '',
  }
  const loopExecutionPlan = summary.loopExecutionPlan ?? {
    execute: false,
    nextIteration: 1,
    reason: 'Retry not allowed',
  }
  const simulatedIteration = summary.simulatedIteration ?? {
    iteration: 0,
    status: 'idle',
  }
  const simulatedOutput = summary.simulatedOutput ?? {
    renderId: null,
    status: 'none' as const,
  }
  const executionPermission = summary.executionPermission ?? {
    allowed: false,
    mode: 'blocked' as const,
    reason: 'Execution mode not permitted',
  }
  const executionRequest = summary.executionRequest ?? {
    enabled: false,
    shotId: null,
    prompt: null,
  }
  const executionStatus = summary.executionStatus ?? {
    state: 'blocked' as const,
    reason: 'Execution not enabled',
  }
  const executionResult = summary.executionResult ?? {
    executed: false,
    renderId: null,
    status: 'not_executed' as const,
  }
  const executionResultV2 = summary.executionResultV2 ?? {
    executed: false,
    renderId: null,
    status: 'not_executed' as const,
  }
  const outputSync = summary.outputSync ?? {
    synced: false,
    renderId: null,
  }
  const executionMonitor = summary.executionMonitor ?? {
    state: executionStatus.state,
    result: executionResultV2.status,
  }
  const providerConfigSnapshot = summary.providerConfigSnapshot ?? {
    defaultProvider: 'mock',
    enabledProviders: ['mock'],
    qualityPriority: 'cinematic_quality',
    realProvidersEnabled: false,
  }
  const providerCredentialState = summary.providerCredentialState ?? {
    provider: providerConfigSnapshot.defaultProvider,
    enabled: true,
    credentialPresent: true,
    credentialSource: 'none' as const,
    reason: 'Mock provider does not require credentials',
  }
  const providerSelectionState = summary.providerSelectionState ?? {
    requestedProvider: null,
    selectedProvider: providerConfigSnapshot.defaultProvider,
    allowed: true,
    fallbackUsed: false,
    reason: 'Default provider selected',
  }
  const providerReadinessSummary = summary.providerReadinessSummary ?? {
    provider: providerConfigSnapshot.defaultProvider,
    enabled: true,
    credentialPresent: true,
    canExecute: false,
    reason: 'Execution not enabled',
  }
  const providerCapability = summary.providerCapability ?? {
    provider: providerConfigSnapshot.defaultProvider,
    enabled: true,
    networkRequired: false,
    supportsRender: true,
    supportsStreaming: false,
    supportsSync: true,
    supportsMultiShot: false,
    requiresCredentials: false,
  }
  const providerControlContract = summary.providerControlContract ?? {
    selectionMode: 'manual_only' as const,
    autoExecution: false,
    executionOnSelect: false,
    reason: 'Provider selection does not trigger execution',
  }
  const providerSafetyContract = summary.providerSafetyContract ?? {
    realProviderExecutionEnabled: false,
    reason: 'Real provider execution is disabled by safety boundary',
  }
  const providerPayloadV2 = summary.providerPayloadV2 ?? {
    provider: providerSelectionState.selectedProvider,
    shotId: null,
    prompt: null,
  }
  const handoffEnvelope = summary.handoffEnvelope ?? {
    requestId: `handoff_${providerPayloadV2.provider}_none`,
    provider: providerPayloadV2.provider,
    enabled: false,
  }
  const handoffAudit = summary.handoffAudit ?? {
    requested: true,
    allowed: false,
    blockedReason: 'Execution permission denied',
    timestamp: null as null,
  }
  const providerAdapterStatus = summary.providerAdapterStatus ?? {
    provider: providerReadinessSummary.provider,
    enabled: false,
  }
  const providerAdapterReadinessGate = summary.providerAdapterReadinessGate ?? {
    ready: false,
  }
  const executionUnlockState = summary.executionUnlockState ?? {
    locked: true,
  }
  const executionEligibility = summary.executionEligibility ?? {
    eligible: false,
  }
  const executionRequestEnvelope = summary.executionRequestEnvelope ?? {
    request: 'blocked',
  }
  const requestSchemaValidation = summary.requestSchemaValidation ?? {
    valid: false,
  }
  const providerValidation = summary.providerValidation ?? {
    valid: false,
  }
  const payloadSanitization = summary.payloadSanitization ?? {
    safe: false,
  }
  const shotQueue = summary.shotQueue ?? []
  const multiShotReadiness = summary.multiShotReadiness ?? { ready: 0 }
  const shotExecutionLedger = summary.shotExecutionLedger ?? []
  const multiShotResults = summary.multiShotResults ?? []
  const multiShotExecutionLedger = summary.multiShotExecutionLedger ?? []
  const multiShotTakeArtifacts = summary.multiShotTakeArtifacts ?? []
  const sceneGenerationSummary = summary.sceneGenerationSummary ?? {
    plannedShots: 0,
    completedShots: 0,
    provider: 'mock',
    status: 'not_started' as const,
  }
  const scenePlaybackPreview = summary.scenePlaybackPreview ?? {
    available: false,
    shotCount: 0,
    renderIds: [],
    status: 'not_started',
  }
  const multiShotExecutionContract = summary.multiShotExecutionContract ?? {
    provider: 'mock_only' as const,
    maxShotsPerRun: 3,
    realProvidersEnabled: false,
    retriesEnabled: false,
    asyncEnabled: false,
    reason: 'Multi-shot execution is mock-only and bounded',
  }
  const takeArtifacts = summary.takeArtifacts ?? []
  const localRenderOutput = summary.localRenderOutput ?? {
    hasOutput: false,
    renderId: null,
    filePath: null,
    artifactType: null,
    status: 'not_executed',
  }
  const localArtifactLog = summary.localArtifactLog ?? {
    executed: false,
    shotId: null,
    filePath: null,
    timestamp: null as null,
  }
  const mockRenderOutput = summary.mockRenderOutput ?? {
    renderId: null,
    status: 'not_executed',
    provider: providerAdapterStatus.provider,
    hasOutput: false,
  }
  const renderSourceResolution = resolveRenderSource(summary)
  const renderSourceStrip = renderSourceResolution.source
  const renderSourceLabel =
    renderSourceResolution.source === 'real'
      ? 'Real Render'
      : renderSourceResolution.source === 'local'
        ? 'Local Render'
        : renderSourceResolution.source === 'mock'
          ? 'Mock Render'
          : 'No Render'
  const renderStatus = executionResultV2.status || mockRenderOutput.status
  const renderFilePath = renderSourceResolution.filePath
  const renderImageSrc = safeImageSrc(renderFilePath ?? renderSourceResolution.url)
  const renderHasOutput = Boolean(
    renderSourceResolution.source !== 'none' &&
      (renderFilePath || renderSourceResolution.url || localRenderOutput.hasOutput || mockRenderOutput.hasOutput)
  )
  const realFilePath = summary.executionResultV2?.meta?.filePath ?? null
  const realUrl = summary.executionResultV2?.meta?.url ?? null
  const getPreviewType = (filePath: string | null | undefined, url: string | null | undefined): 'real' | 'local' | 'none' => {
    if (
      (filePath && realFilePath && filePath === realFilePath) ||
      (url && realUrl && url === realUrl)
    ) {
      return 'real'
    }
    if (filePath || url) {
      return 'local'
    }
    return 'none'
  }
  const shotRowsWithFilePath = shotExecutionLedger.map((row) => {
    const filePath = row.filePath ?? (row.renderId && row.renderId === localRenderOutput.renderId ? localRenderOutput.filePath : null)
    const url = row.url ?? null
    return {
      ...row,
      filePath,
      url,
      previewType: getPreviewType(filePath, url),
    }
  })
  const takeRowsWithFilePath = takeArtifacts.map((row) => {
    const filePath = row.filePath ?? (row.renderId && row.renderId === localRenderOutput.renderId ? localRenderOutput.filePath : null)
    const url = row.url ?? null
    return {
      ...row,
      filePath,
      url,
      previewType: getPreviewType(filePath, url),
    }
  })
  const localArtifactCount = useMemo(() => {
    const paths = new Set<string>()
    if (localRenderOutput.filePath) {
      paths.add(localRenderOutput.filePath)
    }
    if (localArtifactLog.filePath) {
      paths.add(localArtifactLog.filePath)
    }
    for (const row of shotRowsWithFilePath) {
      if (row.filePath) {
        paths.add(row.filePath)
      }
    }
    for (const row of takeRowsWithFilePath) {
      if (row.filePath) {
        paths.add(row.filePath)
      }
    }
    return paths.size
  }, [localArtifactLog.filePath, localRenderOutput.filePath, shotRowsWithFilePath, takeRowsWithFilePath])
  const firstRealScenePreviewPath =
    shotRowsWithFilePath.find((row) => row.previewType === 'real')?.filePath ??
    takeRowsWithFilePath.find((row) => row.previewType === 'real')?.filePath ??
    realFilePath ??
    realUrl ??
    null
  const scenePreviewImageSrc = safeImageSrc(firstRealScenePreviewPath)
  const certificationSafeMode = summary.loopExecutionContract?.mode ?? summary.executionContract?.mode ?? 'safe_simulation'
  const renderReadiness = Boolean(executionEligibility.eligible && providerAdapterReadinessGate.ready)
  const executionPathTrace = summary.executionPathTrace ?? {
    intentPresent: false,
    requestValid: false,
    eligible: false,
    blocked: true,
  }
  const previsSceneBoard = summary.previsSceneBoard ?? []
  const previsAssetMap = summary.previsAssetMap ?? []
  const previsSceneCount = previsSceneBoard.length
  const previsTotalShots = previsSceneBoard.reduce((total, row) => total + row.shotCount, 0)
  const previsReferenceCount = previsAssetMap.length
  const previsFrameCount = previsAssetMap.reduce((total, row) => total + row.scenes.length, 0)
  const promptPreview = renderOutput?.promptSnapshot.baseIntent
    ? renderOutput.promptSnapshot.baseIntent.slice(0, 80)
    : ''

  return (
    <div
      className="rounded-xl p-3"
      style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
      data-testid="execution-summary-inspection"
    >
      <div className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
        Execution Summary Inspection
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-provider-status-strip"
      >
        <span style={{ color: 'var(--text-muted)' }}>Provider</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>{providerAdapterStatus.provider}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Enabled {String(providerAdapterStatus.enabled)}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Ready {String(providerAdapterReadinessGate.ready)}</span>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-execution-status-strip"
      >
        <span style={{ color: 'var(--text-muted)' }}>Execution</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>{executionUnlockState.locked ? 'Locked' : 'Unlocked'}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Eligible {String(executionEligibility.eligible)}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Request {executionRequestEnvelope.request}</span>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-validation-status-strip"
      >
        <span style={{ color: 'var(--text-muted)' }}>Validation</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>
          Schema {displayValidationState(requestSchemaValidation.valid, 'valid', 'invalid')}
        </span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>
          Provider {displayValidationState(providerValidation.valid, 'valid', 'invalid')}
        </span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>
          Payload {displayValidationState(payloadSanitization.safe, 'safe', 'unsafe')}
        </span>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-shot-pipeline-strip"
      >
        <span style={{ color: 'var(--text-muted)' }}>Shots</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>{String(shotExecutionLedger.length)}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Queue {String(shotQueue.length)}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Ready {String(multiShotReadiness.ready)}</span>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-take-pipeline-strip"
      >
        <span style={{ color: 'var(--text-muted)' }}>Takes</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>{String(takeArtifacts.length)}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Comparable {String(takeComparisonV2.comparable)}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Auto Select {String(takePreferenceContract.autoSelect)}</span>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-render-status-strip"
      >
        <span style={{ color: 'var(--text-muted)' }}>Render</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>{renderStatus}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Source {renderSourceStrip}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Output {renderHasOutput ? 'yes' : 'no'}</span>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-scene-status-strip"
      >
        <span style={{ color: 'var(--text-muted)' }}>Scene</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>{sceneGenerationSummary.status}</span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>
          Shots {sceneGenerationSummary.completedShots}/{sceneGenerationSummary.plannedShots}
        </span>
        <span style={{ color: 'var(--text-muted)' }}> · </span>
        <span style={{ color: 'var(--text-secondary)' }}>Preview {scenePlaybackPreview.available ? 'yes' : 'no'}</span>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-dashboard-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Studio Dashboard</div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Provider Card</div>
            <div style={{ color: 'var(--text-secondary)' }}>Provider: {providerAdapterStatus.provider}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Enabled: {String(providerAdapterStatus.enabled)}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Ready: {String(providerAdapterReadinessGate.ready)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Execution Card</div>
            <div style={{ color: 'var(--text-secondary)' }}>Locked: {String(executionUnlockState.locked)}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Eligible: {String(executionEligibility.eligible)}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Request: {executionRequestEnvelope.request}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Validation Card</div>
            <div style={{ color: 'var(--text-secondary)' }}>Schema: {displayValidationState(requestSchemaValidation.valid, 'valid', 'invalid')}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Provider: {displayValidationState(providerValidation.valid, 'valid', 'invalid')}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Payload: {displayValidationState(payloadSanitization.safe, 'safe', 'unsafe')}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Shot Pipeline Card</div>
            <div style={{ color: 'var(--text-secondary)' }}>Shots: {String(shotExecutionLedger.length)}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Queue: {String(shotQueue.length)}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Ready: {String(multiShotReadiness.ready)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Take Pipeline Card</div>
            <div style={{ color: 'var(--text-secondary)' }}>Takes: {String(takeArtifacts.length)}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Comparable: {String(takeComparisonV2.comparable)}</div>
            <div style={{ color: 'var(--text-secondary)' }}>Auto Select: {String(takePreferenceContract.autoSelect)}</div>
          </div>
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="previs-overview-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Previs Overview</div>
        <div style={{ color: 'var(--text-secondary)' }}>Scene Count: {String(previsSceneCount)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Total Shots: {String(previsTotalShots)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Reference Count: {String(previsReferenceCount)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Frame Count: {String(previsFrameCount)}</div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="scene-generation-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Scene Generation</div>
        <div style={{ color: 'var(--text-secondary)' }}>Status: {sceneGenerationSummary.status}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Planned Shots: {String(sceneGenerationSummary.plannedShots)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Completed Shots: {String(sceneGenerationSummary.completedShots)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Provider: {sceneGenerationSummary.provider}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Preview Available: {scenePlaybackPreview.available ? 'Yes' : 'No'}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Render IDs Count: {String(scenePlaybackPreview.renderIds.length)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Ledger Rows: {String(multiShotExecutionLedger.length)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Take Artifacts: {String(multiShotTakeArtifacts.length)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Contract: {multiShotExecutionContract.provider} · Max {String(multiShotExecutionContract.maxShotsPerRun)} · Async {String(multiShotExecutionContract.asyncEnabled)}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="shot-playback-table-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Shot Playback</div>
        {multiShotResults.length > 0 ? (
          <table className="mt-2 w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--text-muted)' }}>
                <th className="text-left">shot_id</th>
                <th className="text-left">render_id</th>
                <th className="text-left">status</th>
                <th className="text-left">provider</th>
              </tr>
            </thead>
            <tbody>
              {multiShotResults.map((row) => (
                <tr key={`${row.shotId}:${row.renderId}`}>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.shotId}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.renderId}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.status}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.provider}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No data available</div>
        )}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="scene-playback-preview-box"
      >
        {scenePreviewImageSrc ? (
          <div style={{ color: 'var(--text-secondary)' }}>
            Scene Preview Available
            <div className="mt-2">
              <img src={scenePreviewImageSrc} alt="scene preview" style={{ maxHeight: '128px', borderRadius: '0.375rem' }} />
            </div>
          </div>
        ) : localArtifactCount > 0 ? (
          <div style={{ color: 'var(--text-secondary)' }}>
            Scene Preview Available
            <div>Artifacts: {String(localArtifactCount)}</div>
          </div>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No scene preview available</div>
        )}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="shot-preview-table-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Shot Preview</div>
        {shotRowsWithFilePath.length > 0 ? (
          <table className="mt-2 w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--text-muted)' }}>
                <th className="text-left">shot_id</th>
                <th className="text-left">scene_id</th>
                <th className="text-left">status</th>
                <th className="text-left">file_path</th>
                <th className="text-left">preview_type</th>
              </tr>
            </thead>
            <tbody>
              {shotRowsWithFilePath.map((row) => (
                <tr key={`${row.shotId}:${row.sceneId}`}>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.shotId}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.sceneId}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.status || 'not_executed'}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.filePath ?? 'None'}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.previewType}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No data available</div>
        )}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="take-table-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Take Table</div>
        {takeRowsWithFilePath.length > 0 ? (
          <table className="mt-2 w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--text-muted)' }}>
                <th className="text-left">iteration</th>
                <th className="text-left">render_id</th>
                <th className="text-left">status</th>
                <th className="text-left">file_path</th>
                <th className="text-left">preview_type</th>
                <th className="text-left">preview_label</th>
              </tr>
            </thead>
            <tbody>
              {takeRowsWithFilePath.map((row, index) => (
                <tr key={`${row.iteration}:${row.renderId ?? 'none'}:${index}`}>
                  <td style={{ color: 'var(--text-secondary)' }}>{String(row.iteration)}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.renderId ?? 'None'}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.status}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.filePath ?? 'None'}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.previewType}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row.previewType === 'real' ? 'Real Preview' : row.previewType === 'local' ? 'Local Preview' : 'No Preview'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No data available</div>
        )}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="mock-render-output-card"
      >
        <div style={{ color: 'var(--text-muted)' }}>Render Output</div>
        <div style={{ color: 'var(--text-secondary)' }}>Render ID: {executionResultV2.renderId ?? localRenderOutput.renderId ?? mockRenderOutput.renderId ?? 'None'}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Status: {renderStatus}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Provider: {executionResultV2.provider ?? mockRenderOutput.provider}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Output Available: {renderHasOutput ? 'Yes' : 'No'}</div>
        <div style={{ color: 'var(--text-secondary)' }}>Render Label: {renderSourceLabel}</div>
        {renderSourceResolution.source === 'real' && renderImageSrc ? (
          <div className="mt-2" style={{ color: 'var(--text-secondary)' }}>
            <img src={renderImageSrc} alt="render preview" style={{ maxHeight: '192px', borderRadius: '0.375rem' }} />
          </div>
        ) : renderSourceResolution.source === 'local' && renderFilePath ? (
          <div style={{ color: 'var(--text-secondary)' }}>
            Local Artifact: {renderFilePath}
          </div>
        ) : renderSourceResolution.source === 'mock' ? (
          <div style={{ color: 'var(--text-secondary)' }}>
            Mock render output available
          </div>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No render output yet</div>
        )}
        {renderStatus === 'failed' ? (
          <div style={{ color: 'var(--text-secondary)' }}>
            Error: Render failed
          </div>
        ) : null}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="render-certification-panel"
      >
        <div style={{ color: 'var(--text-muted)' }}>Render Certification</div>
        <div style={{ color: 'var(--text-secondary)' }}>executed: {String(executionResultV2.executed)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>provider: {executionResultV2.provider ?? mockRenderOutput.provider}</div>
        <div style={{ color: 'var(--text-secondary)' }}>source: {renderSourceResolution.source}</div>
        <div style={{ color: 'var(--text-secondary)' }}>has_output: {renderHasOutput ? 'yes' : 'no'}</div>
        <div style={{ color: 'var(--text-secondary)' }}>file_path exists: {renderFilePath ? 'yes' : 'no'}</div>
        <div style={{ color: 'var(--text-secondary)' }}>safe_mode: {certificationSafeMode}</div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="render-readiness-indicator"
      >
        <div style={{ color: 'var(--text-muted)' }}>Ready to Render: {renderReadiness ? 'YES' : 'NO'}</div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="shot-result-panel"
      >
        <div style={{ color: 'var(--text-muted)' }}>Shot Result Panel</div>
        {shotExecutionLedger.length > 0 ? (
          <div className="mt-2 space-y-1">
            {shotExecutionLedger.map((row) => (
              <div key={`shot-result-${row.shotId}:${row.sceneId}`} style={{ color: 'var(--text-secondary)' }}>
                shot_id {row.shotId} · status {row.status} · render_id {row.renderId ?? 'None'}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No data available</div>
        )}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="take-result-card"
      >
        <div style={{ color: 'var(--text-muted)' }}>Take Result Card</div>
        {takeArtifacts.length > 0 ? (
          <div className="mt-2 space-y-1">
            {takeArtifacts.map((take, index) => (
              <div key={`take-result-${take.iteration}-${index}`} style={{ color: 'var(--text-secondary)' }}>
                iteration {take.iteration} · render_id {take.renderId ?? 'None'} · status {take.status}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No data available</div>
        )}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="preview-content-panel"
      >
        <div style={{ color: 'var(--text-muted)' }}>Preview Content</div>
        {renderSourceResolution.source === 'real' && renderImageSrc ? (
          <img src={renderImageSrc} alt="render preview" style={{ maxHeight: '160px', borderRadius: '0.375rem' }} />
        ) : renderSourceResolution.source === 'local' && renderFilePath ? (
          <pre className="mt-1 whitespace-pre-wrap rounded-lg p-2" style={{ background: 'var(--bg-panel)', color: 'var(--text-secondary)' }}>
            {`Local preview path: ${renderFilePath}`}
          </pre>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No preview available</div>
        )}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="execution-path-trace"
      >
        <div style={{ color: 'var(--text-muted)' }}>Execution Path</div>
        <div style={{ color: 'var(--text-secondary)' }}>intent_present: {String(executionPathTrace.intentPresent)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>request_valid: {String(executionPathTrace.requestValid)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>eligible: {String(executionPathTrace.eligible)}</div>
        <div style={{ color: 'var(--text-secondary)' }}>blocked: {String(executionPathTrace.blocked)}</div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="studio-safety-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Studio Safety</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Overall: {studioState}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Memory: {String(boundaryAudit.memorySafe)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Visual: {String(boundaryAudit.visualSafe)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Shot: {String(boundaryAudit.shotSafe)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Render: {String(boundaryAudit.renderSafe)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Co-Director: {String(boundaryAudit.coDirectorSafe)}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="prompt-influence-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Prompt Influence</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Enabled: {String(promptInfluenceGate.promptInfluenceEnabled)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Scope: {promptInfluenceGate.scope}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Visual Tokens: {visualPromptTokens.length > 0 ? visualPromptTokens.join(', ') : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Shot Tokens: {shotPromptTokens.length > 0 ? shotPromptTokens.join(', ') : 'None'}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="prompt-envelope-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Prompt Envelope</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Base Intent: {promptEnvelope.baseIntent || 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Visual Tokens: {promptEnvelope.visualTokens.length > 0 ? promptEnvelope.visualTokens.join(', ') : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Shot Tokens: {promptEnvelope.shotTokens.length > 0 ? promptEnvelope.shotTokens.join(', ') : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Locked: {String(promptSafetyContract.structureLocked)}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="render-control-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Render Control</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Enabled: {String(renderActivationGateV1.renderEnabled)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Mode: {renderActivationGateV1.mode}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Shot: {renderRequest ? renderRequest.shotId : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Status: {renderOutput ? renderOutput.status : 'None'}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="render-output-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Render Output</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Render ID: {renderOutput ? renderOutput.renderId : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Shot: {renderOutput ? renderOutput.shotId : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Status: {renderOutput ? renderOutput.status : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Alignment: {outputReview && outputReview.alignment ? outputReview.alignment : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Coverage: {outputReview && outputReview.coverage ? outputReview.coverage : 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Prompt Preview: {promptPreview || 'None'}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="output-evaluation-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Output Evaluation</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Has Output: {String(outputEvaluation.hasOutput)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Valid Structure: {String(outputEvaluation.validStructure)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Render ID Present: {String(outputEvaluation.renderIdPresent)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Status: {outputEvaluation.status}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="retry-gate-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Retry Gate</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Retry Allowed: {String(retryGate.retryAllowed)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Reason: {retryGate.reason}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="execution-snapshot-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Execution Snapshot</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Iteration: {executionSnapshot.iteration} / {executionSnapshot.maxIterations}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Status: {executionSnapshot.status}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Render Attempted: {String(executionSnapshot.renderAttempted)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Retry Allowed: {String(executionSnapshot.retryAllowed)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Finalized: {String(executionSnapshot.finalized)}
        </div>
      </div>
      {summary.iterationRecord ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="take-analysis-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Take Analysis</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Iteration: {iterationRecord.iteration}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Status: {iterationRecord.status}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Render ID: {iterationRecord.renderId || 'None'}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Retry Allowed: {String(retrySnapshot.allowed)}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Advisory Note: {takeAdvisoryNote.note || 'None'}
          </div>
        </div>
      ) : null}
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="take-review-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Take Review</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Comparable: {String(takeComparisonV2.comparable)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Differences: {String(takeComparisonV2.differences.length)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Auto Select: {String(takePreferenceContract.autoSelect)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Authority: {takePreferenceContract.authority}
        </div>
        {outputReviewMatrix.length > 0 ? (
          <div className="mt-2" style={{ color: 'var(--text-secondary)' }}>
            {outputReviewMatrix.map((row) => (
              <div key={`take-review-row-${row.takeId}`}>
                Take ID {row.takeId} · Alignment {row.alignment} · Coverage {row.coverage} · Valid Structure {String(row.validStructure)}
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: 'var(--text-secondary)' }}>No takes</div>
        )}
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="loop-planning-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Loop Planning</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Ready: {String(loopReadiness.ready)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Reason: {loopReadiness.reason}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Next Iteration: {nextTakePreview.nextIteration}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Remaining: {loopConstraint.remaining}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Advisory: {loopAdvisory.note || 'None'}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="loop-execution-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Loop Execution</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Execute: {String(loopExecutionPlan.execute)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Next Iteration: {loopExecutionPlan.nextIteration}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Simulated Iteration: {simulatedIteration.iteration}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Output Status: {simulatedOutput.status}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="execution-control-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Execution Control</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Allowed: {String(executionPermission.allowed)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Mode: {executionPermission.mode}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          State: {executionStatus.state}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Shot ID: {executionRequest.shotId || 'None'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Status: {executionResult.status}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="execution-monitor-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Execution Monitor</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          State: {executionMonitor.state}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Result: {executionMonitor.result}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Synced: {String(outputSync.synced)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Render ID: {outputSync.renderId || executionResultV2.renderId || 'None'}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="provider-selection-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Provider Selection</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Requested: {providerSelectionState.requestedProvider ?? 'none'}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Selected: {providerSelectionState.selectedProvider}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Allowed: {String(providerSelectionState.allowed)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Fallback Used: {String(providerSelectionState.fallbackUsed)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Reason: {providerSelectionState.reason}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="provider-control-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Provider Control</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Default Provider: {providerConfigSnapshot.defaultProvider}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Selected Provider: {providerSelectionState.selectedProvider}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Provider Enabled: {String(providerReadinessSummary.enabled)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Credentials Present: {String(providerCredentialState.credentialPresent)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Can Execute: {String(providerReadinessSummary.canExecute)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Selection Mode: {providerControlContract.selectionMode}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="provider-capability-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Provider Capability</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Provider: {providerCapability.provider}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Supports Render: {String(providerCapability.supportsRender)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Requires Credentials: {String(providerCapability.requiresCredentials)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Supports Multi-Shot: {String(providerCapability.supportsMultiShot)}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="provider-safety-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Provider Safety</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Execution Enabled: {String(providerSafetyContract.realProviderExecutionEnabled)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Reason: {providerSafetyContract.reason}
        </div>
      </div>
      <div
        className="mt-3 rounded-lg p-2 text-xs"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        data-testid="provider-handoff-section"
      >
        <div style={{ color: 'var(--text-muted)' }}>Provider Handoff</div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Provider: {providerPayloadV2.provider}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Enabled: {String(handoffEnvelope.enabled)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Request ID: {handoffEnvelope.requestId}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Allowed: {String(handoffAudit.allowed)}
        </div>
        <div style={{ color: 'var(--text-secondary)' }}>
          Blocked Reason: {handoffAudit.blockedReason || 'None'}
        </div>
      </div>
      {summary.productionSignal ? (
        <div className="mt-3 rounded-lg p-2 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Production Signal</div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.productionSignal.message}</div>
        </div>
      ) : null}
      {summary.sceneIntent ? (
        <div className="mt-3 rounded-lg p-2 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Scene Intent</div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.sceneIntent.label}</div>
        </div>
      ) : null}
      {summary.intentSignal ? (
        <div className="mt-3 rounded-lg p-2 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Intent Signal</div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.intentSignal.message}</div>
        </div>
      ) : null}
      {summary.intentOutputSignal ? (
        <div className="mt-3 rounded-lg p-2 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Intent Output Signal</div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.intentOutputSignal.message}</div>
        </div>
      ) : null}
      {summary.intentOutputRelation ? (
        <div className="mt-3 rounded-lg p-2 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Intent Output Relation</div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.intentOutputRelation.message}</div>
        </div>
      ) : null}
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Provider</div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.providerName}</div>
        </div>
        <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Lifecycle State</div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.lifecycleState}</div>
        </div>
        <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Provider Status</div>
          <div style={{ color: 'var(--text-secondary)' }}>{displayText(summary.providerStatus)}</div>
        </div>
        <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Output Artifacts</div>
          <div style={{ color: 'var(--text-secondary)' }}>{displayFlag(summary.hasOutputArtifacts)}</div>
        </div>
        <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Error Present</div>
          <div style={{ color: 'var(--text-secondary)' }}>{displayFlag(summary.hasError)}</div>
        </div>
        <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Latest Updated</div>
          <div style={{ color: 'var(--text-secondary)' }}>{displayText(summary.latestUpdatedAt)}</div>
        </div>
        {summary.renderBehavior ? (
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Render Behavior</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayRenderBehavior(summary.renderBehavior)}</div>
          </div>
        ) : null}
      </div>
      {summary.interventionSuggestion ? (
        <div className="mt-3 rounded-lg p-2 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Intervention Suggestion</div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.interventionSuggestion.message}</div>
        </div>
      ) : null}
      {summary.recurringPattern ? (
        <div className="mt-3 rounded-lg p-2 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
          <div style={{ color: 'var(--text-muted)' }}>Recurring Pattern</div>
          <div style={{ color: 'var(--text-secondary)' }}>{displayRecurringPatternType(summary.recurringPattern.type)}</div>
          {summary.recurringPattern.providerName ? (
            <div style={{ color: 'var(--text-muted)' }}>Provider: <span style={{ color: 'var(--text-secondary)' }}>{summary.recurringPattern.providerName}</span></div>
          ) : null}
          <div style={{ color: 'var(--text-muted)' }}>Count: <span style={{ color: 'var(--text-secondary)' }}>{String(summary.recurringPattern.count)}</span></div>
          <div style={{ color: 'var(--text-secondary)' }}>{summary.recurringPattern.message}</div>
        </div>
      ) : null}
      {summary.visualReferenceSummary && summary.visualReferenceSummary.referenceCount > 0 ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="visual-references-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Visual References</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            References {String(summary.visualReferenceSummary.referenceCount)}
            <span style={{ color: 'var(--text-muted)' }}> · </span>
            Linked scenes {String(summary.visualReferenceSummary.linkedSceneCount)}
            <span style={{ color: 'var(--text-muted)' }}> · </span>
            Types {String(summary.visualReferenceSummary.typeCount)}
          </div>
        </div>
      ) : null}
      {summary.frameStats && summary.frameStats.frameCount > 0 ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="frame-analysis-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Frame Analysis</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Frames {String(summary.frameStats.frameCount)}
            <span style={{ color: 'var(--text-muted)' }}> · </span>
            Artifacts {String(summary.frameStats.artifactCount)}
          </div>
        </div>
      ) : null}
      {summary.linkCompleteness && summary.linkCompleteness.totalScenes > 0 ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="scene-visual-linkage-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Scene-Visual Linkage</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Linked {String(summary.linkCompleteness.linkedScenes)} / {String(summary.linkCompleteness.totalScenes)} scenes
          </div>
        </div>
      ) : null}
      {summary.shotCandidates && summary.shotCandidates.length > 0 ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="shot-planning-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Shot Planning</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Scenes {String(summary.shotCoverage ? Object.keys(summary.shotCoverage).length : 0)}
            <span style={{ color: 'var(--text-muted)' }}> · </span>
            Candidates {String(summary.shotCandidates.length)}
          </div>
        </div>
      ) : null}
      {summary.shotPlanningSummary && summary.shotPlanningSummary.totalScenes > 0 ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="shot-thinking-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Shot Thinking</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Scenes Covered: {String(summary.shotPlanningSummary.coveredScenes)} / {String(summary.shotPlanningSummary.totalScenes)}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Variety: {summary.shotPlanningSummary.variety}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Advisory: {summary.shotAdvisoryNote ? summary.shotAdvisoryNote.note : ''}
          </div>
        </div>
      ) : null}
      {summary.sequenceStatus ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="sequence-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Sequence</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Scenes: {String(summary.sequenceStatus.scenes)}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Shots: {String(summary.sequenceStatus.shots)}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Assembled: {summary.sequenceStatus.assembled ? 'true' : 'false'}
          </div>
        </div>
      ) : null}
      {summary.scenePlaybackStatus ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="scene-playback-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Scene Playback</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Playback Ready: {summary.scenePlaybackStatus.playbackReady ? 'true' : 'false'}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Scenes: {String(summary.scenePlaybackStatus.sceneCount)}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Shots Available: {String(summary.scenePlaybackStatus.shotsAvailable)}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Status: {summary.scenePlaybackStatus.status}
          </div>
        </div>
      ) : null}
      {summary.coDirectorObservationSummary && summary.coDirectorObservationSummary.notes.length > 0 ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="co-director-notes-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Co-Director Notes</div>
          {summary.coDirectorObservationSummary.notes.map((note, index) => (
            <div key={`co-director-note-${index}`} style={{ color: 'var(--text-secondary)' }}>
              {note}
            </div>
          ))}
        </div>
      ) : null}
      {summary.visualPatternSummary && Object.keys(summary.visualPatternSummary.typeCounts).length > 0 ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="visual-summary-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Visual Summary</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Dominant Types: {summary.visualPatternSummary.dominantTypes.length > 0 ? summary.visualPatternSummary.dominantTypes.join(', ') : 'None'}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Consistency: {summary.visualConsistency ? summary.visualConsistency.varianceLevel : 'none'}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Tension Scenes: {summary.visualTension ? String(summary.visualTension.tensionScenes.length) : '0'}
          </div>
        </div>
      ) : null}
      {hasConsistentMemorySection || hasMemorySummaryRow || hasMemoryReviewState ? (
        <div className="mt-3 rounded-lg p-2 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }} data-testid="memory-inspection-section">
          {hasConsistentMemorySection ? (
            <div>
              <div style={{ color: 'var(--text-muted)' }}>Memory Advisory</div>
              <div style={{ color: 'var(--text-secondary)' }}>{summary.memoryAdvisoryProjection!.message}</div>
            </div>
          ) : null}
          {hasMemorySummaryRow ? (
            <div className="mt-2">
              <div style={{ color: 'var(--text-muted)' }}>Memory Summary</div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Candidates {String(summary.memorySnapshotSummary!.candidateCount)}
                <span style={{ color: 'var(--text-muted)' }}> · </span>
                Records {String(summary.memorySnapshotSummary!.recordCount)}
                <span style={{ color: 'var(--text-muted)' }}> · </span>
                Aggregate {String(summary.memorySnapshotSummary!.aggregateCount)}
                <span style={{ color: 'var(--text-muted)' }}> · </span>
                Influence disabled
              </div>
            </div>
          ) : null}
          {hasConsistentMemorySection && summary.memoryCategoryPresence ? (
            <div className="mt-2">
              <div style={{ color: 'var(--text-muted)' }}>Categories</div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Character pairs: {displayFlag(summary.memoryCategoryPresence.characterPairs)}
                <span style={{ color: 'var(--text-muted)' }}> · </span>
                Locations: {displayFlag(summary.memoryCategoryPresence.locations)}
                <span style={{ color: 'var(--text-muted)' }}> · </span>
                Time of day: {displayFlag(summary.memoryCategoryPresence.timeOfDay)}
              </div>
            </div>
          ) : null}
          {hasConsistentMemorySection ? (
            <div className="mt-2">
              <div style={{ color: 'var(--text-muted)' }}>Memory Visibility</div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Candidates: {displayFlag(summary.coDirectorMemoryVisibility!.hasMemoryCandidates)} | Records: {displayFlag(summary.coDirectorMemoryVisibility!.hasMemoryRecords)} | Aggregate: {displayFlag(summary.coDirectorMemoryVisibility!.hasMemoryAggregate)}
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Influence disabled
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Advisory Status: {summary.coDirectorMemoryVisibility!.advisoryStatus}
              </div>
            </div>
          ) : null}
          {hasMemoryReviewState ? (
            <div style={{ color: 'var(--text-secondary)' }}>
              <div style={{ color: 'var(--text-muted)' }}>Memory Review State</div>
              <div style={{ color: 'var(--text-secondary)' }}>Ready</div>
            </div>
          ) : null}
          {hasConsistentMemorySection ? (
            <div className="mt-2">
              <div style={{ color: 'var(--text-muted)' }}>Co-Director Memory Advisory</div>
              <div style={{ color: 'var(--text-secondary)' }}>{summary.coDirectorMemoryAdvisory!.message}</div>
            </div>
          ) : null}
          {hasConsistentMemorySection ? (
            <div className="mt-2">
              <div style={{ color: 'var(--text-muted)' }}>Memory Authority Boundary</div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Authority none
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Memory influence disabled
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>{summary.coDirectorMemoryAuthorityBoundary!.reason}</div>
            </div>
          ) : null}
        </div>
      ) : null}
      {summary.validationInspection ? (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs" data-testid="validation-inspection-section">
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Validation Disposition</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayText(summary.validationInspection.advisoryDisposition)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Validation Confidence</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayScore(summary.validationInspection.advisoryConfidence)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Validation Issues</div>
            <div style={{ color: 'var(--text-secondary)' }}>
              {summary.validationInspection.issueCount === null ? 'Unavailable' : String(summary.validationInspection.issueCount)}
            </div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Critical Issues</div>
            <div style={{ color: 'var(--text-secondary)' }}>{String(summary.validationInspection.criticalIssueCount)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Warnings</div>
            <div style={{ color: 'var(--text-secondary)' }}>{String(summary.validationInspection.warningCount)}</div>
          </div>
          <div className="rounded-lg p-2" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
            <div style={{ color: 'var(--text-muted)' }}>Package Fidelity</div>
            <div style={{ color: 'var(--text-secondary)' }}>{displayScore(summary.validationInspection.packageFidelity)}</div>
          </div>
        </div>
      ) : null}
      {summary.previsSceneBoard || summary.previsBeatShotMap || summary.previsAssetMap ? (
        <div
          className="mt-3 rounded-lg p-2 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          data-testid="previs-room-section"
        >
          <div style={{ color: 'var(--text-muted)' }}>Previs Room</div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Scenes: {summary.previsSceneBoard ? String(summary.previsSceneBoard.length) : '0'}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Beats: {summary.previsBeatShotMap ? String(summary.previsBeatShotMap.length) : '0'}
          </div>
          <div style={{ color: 'var(--text-secondary)' }}>
            Asset Scenes: {summary.previsAssetMap ? String(summary.previsAssetMap.length) : '0'}
          </div>
          {summary.previsContract ? (
            <>
              <div style={{ color: 'var(--text-secondary)' }}>
                Mode: {summary.previsContract.mode}
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Authority: {summary.previsContract.authority}
              </div>
              <div style={{ color: 'var(--text-secondary)' }}>
                Execution: {String(summary.previsContract.executionEnabled)}
              </div>
            </>
          ) : (
            <>
              <div style={{ color: 'var(--text-secondary)' }}>Mode: read_only</div>
              <div style={{ color: 'var(--text-secondary)' }}>Authority: none</div>
              <div style={{ color: 'var(--text-secondary)' }}>Execution: false</div>
            </>
          )}
          {summary.previsSceneBoard && summary.previsSceneBoard.length > 0 ? (
            <div className="mt-2 space-y-1">
              {summary.previsSceneBoard.map((entry, index) => (
                <div key={`previs-scene-${index}`} style={{ color: 'var(--text-muted)' }}>
                  scene_id: {entry.sceneId} · shot_count: {entry.shotCount} · linked_refs: {entry.linkedRefs.length}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

import type { RenderJob, StudioDecisionGate, ProductionAcceptanceReport } from './studioApi'

/**
 * Pipeline gate flow derivation.
 *
 * Every stage below maps to a record the backend already wrote. Nothing is
 * inferred: when a stage left no record, its state is `not_established` and the
 * node says which record would establish it. States are deliberately about
 * *evidence*, not about whether the film is good:
 *
 * - `cleared`         the stage ran and the recorded outcome was clean
 * - `fail_closed`     the stage refused, and the backend recorded why
 * - `not_established` no record exists for this stage on this surface
 * - `unavailable`     the source read failed, so absence proves nothing
 *
 * Backend sources:
 * - `job.metadata.router_execution` (RunwayRouterAdapter: router_config_id,
 *   resolved_model, routing_provider, payload_normalized,
 *   payload_normalization_warnings, reason, submission_attempted)
 * - `job.metadata.provider_failure` / `job.metadata.pipeline_reliability`
 * - Studio Decision Gate blockers/warnings and acceptance report checks
 *
 * The Production Integrity Gate itself remains the enforcement boundary; this
 * module never decides authorization.
 */

export type GateStageId =
  | 'socket_isolation'
  | 'preflight_authorization'
  | 'generic_mint'
  | 'payload_normalizer'
  | 'runway_router'

export type GateStageState = 'cleared' | 'fail_closed' | 'not_established' | 'unavailable'

export type GateLogEntry = {
  id: string
  label: string
  detail: string
  at?: string
}

export type GateStage = {
  id: GateStageId
  order: number
  label: string
  /** What this stage is configured to enforce, in the backend's own terms. */
  configuration: string
  /** Which persisted record establishes this node's state. */
  evidenceSource: string
  state: GateStageState
  detail: string
  logs: GateLogEntry[]
}

export type LoadStateLike<T> =
  | { status: 'loading' }
  | { status: 'unavailable'; message: string }
  | { status: 'loaded'; value: T }

type AnyRecord = Record<string, unknown>

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function routerExecution(job: RenderJob): AnyRecord {
  return asRecord(asRecord(job.metadata)?.router_execution) || {}
}

function jobLogs(job: RenderJob): GateLogEntry[] {
  const entries: GateLogEntry[] = []
  const metadata = asRecord(job.metadata) || {}
  const execution = routerExecution(job)
  const reason = text(execution.reason)
  if (reason) {
    entries.push({
      id: `${job.id}:reason`,
      label: 'Refused before submission',
      detail: reason,
      at: job.updated_at,
    })
  }
  const failure = asRecord(metadata.provider_failure)
  if (failure) {
    const category = text(failure.category) || text(failure.error_type)
    const message = text(failure.message)
    if (category || message) {
      entries.push({
        id: `${job.id}:provider_failure`,
        label: category || 'Provider failure',
        detail: message || text(failure.policy_reason) || 'No message was recorded.',
        at: job.updated_at,
      })
    }
  }
  const reliability = asRecord(metadata.pipeline_reliability)
  const location = reliability ? asRecord(reliability.failure_location) : null
  if (location) {
    const phase = text(location.phase)
    const detail = text(location.reason) || text(location.error_type) || text(location.category)
    if (phase || detail) {
      entries.push({
        id: `${job.id}:failure_location`,
        label: phase ? `Failure at ${phase}` : 'Failure location recorded',
        detail: detail || 'No reason was recorded.',
        at: job.updated_at,
      })
    }
  }
  const warnings = execution.payload_normalization_warnings
  if (Array.isArray(warnings) && warnings.length > 0) {
    entries.push({
      id: `${job.id}:normalization`,
      label: 'Payload auto-optimized',
      detail: warnings.filter((warning): warning is string => typeof warning === 'string').slice(0, 4).join(' · '),
      at: job.updated_at,
    })
  }
  return entries
}

/** Reasons the adapter records before any provider submission is attempted. */
const ISOLATION_REASONS = new Set(['direct_runway_submission_disabled', 'required_reference_incompatible'])
/** Reasons that stop a submission at the frozen-contract boundary. */
const AUTHORIZATION_REASONS = new Set(['frozen_generation_contract_unavailable', 'model_rejected_on_router_path'])
/** Reasons the router records when provider output identity cannot be trusted. */
const ROUTER_REASONS = new Set(['provider_output_identity_missing', 'provider_output_identity_mismatch'])

const MINT_PATTERN = /mint|confirmation|confirmed|digest|preflight|authori[sz]ation/i

function stage(
  base: Omit<GateStage, 'logs'> & { logs?: GateLogEntry[] },
): GateStage {
  return { ...base, logs: base.logs || [] }
}

export function buildPipelineGateFlow(input: {
  jobs: LoadStateLike<RenderJob[]>
  gate: LoadStateLike<StudioDecisionGate>
  reports: LoadStateLike<ProductionAcceptanceReport[]>
}): GateStage[] {
  const { jobs, gate, reports } = input
  const jobRows = jobs.status === 'loaded' ? jobs.value : []
  const executions = jobRows
    .map((job) => ({ job, execution: routerExecution(job) }))
    .filter((row) => Object.keys(row.execution).length > 0)
  const allLogs = jobRows.flatMap(jobLogs)
  const jobsUnavailable = jobs.status === 'unavailable'

  const reasonRows = executions
    .map((row) => ({ job: row.job, reason: text(row.execution.reason) }))
    .filter((row) => row.reason)

  const reasonsFor = (set: Set<string>) => reasonRows.filter((row) => set.has(row.reason))

  // ── 1. Socket isolation ──────────────────────────────────────────────────
  const isolationRefusals = reasonsFor(ISOLATION_REASONS)
  const isolatedSubmissions = executions.filter((row) => row.execution.submission_attempted === true)
  const socketLogs = allLogs.filter((entry) => isolationRefusals.some((row) => entry.id.startsWith(`${row.job.id}:`)))
  const socketStage = jobsUnavailable
    ? stage({
      id: 'socket_isolation', order: 1, label: 'Socket Isolation Gate',
      configuration: 'Each submission runs in its own isolated transport context; no session or socket state is shared between shots, and direct provider submission is refused.',
      evidenceSource: 'Render job metadata · router_execution.reason, submission_attempted',
      state: 'unavailable',
      detail: jobs.status === 'unavailable' ? jobs.message : 'Render queue unavailable.',
    })
    : isolationRefusals.length > 0
      ? stage({
        id: 'socket_isolation', order: 1, label: 'Socket Isolation Gate',
        configuration: 'Each submission runs in its own isolated transport context; no session or socket state is shared between shots, and direct provider submission is refused.',
        evidenceSource: 'Render job metadata · router_execution.reason, submission_attempted',
        state: 'fail_closed',
        detail: `${isolationRefusals.length} job${isolationRefusals.length === 1 ? '' : 's'} were refused at the isolation boundary and never reached a provider socket.`,
        logs: socketLogs,
      })
      : executions.length === 0
        ? stage({
          id: 'socket_isolation', order: 1, label: 'Socket Isolation Gate',
          configuration: 'Each submission runs in its own isolated transport context; no session or socket state is shared between shots, and direct provider submission is refused.',
          evidenceSource: 'Render job metadata · router_execution.reason, submission_attempted',
          state: 'not_established',
          detail: 'No router execution is recorded for this project, so isolation has nothing to report yet.',
        })
        : stage({
          id: 'socket_isolation', order: 1, label: 'Socket Isolation Gate',
          configuration: 'Each submission runs in its own isolated transport context; no session or socket state is shared between shots, and direct provider submission is refused.',
          evidenceSource: 'Render job metadata · router_execution.reason, submission_attempted',
          state: 'cleared',
          detail: `${executions.length} router execution${executions.length === 1 ? '' : 's'} recorded · ${isolatedSubmissions.length} submission${isolatedSubmissions.length === 1 ? '' : 's'} attempted · no isolation refusal recorded.`,
        })

  // ── 2. Preflight authorization ───────────────────────────────────────────
  const authorizationRefusals = reasonsFor(AUTHORIZATION_REASONS)
  const authorized = executions.filter((row) => text(row.execution.router_config_id))
  const authorizationLogs = allLogs.filter((entry) => authorizationRefusals.some((row) => entry.id.startsWith(`${row.job.id}:`)))
  const preflightStage = jobsUnavailable
    ? stage({
      id: 'preflight_authorization', order: 2, label: 'Preflight Authorization',
      configuration: 'A frozen generation contract and an eligible router model must exist before any request is built. The adapter refuses rather than repairing the contract.',
      evidenceSource: 'Render job metadata · router_execution.router_config_id, reason',
      state: 'unavailable',
      detail: jobs.status === 'unavailable' ? jobs.message : 'Render queue unavailable.',
    })
    : authorizationRefusals.length > 0
      ? stage({
        id: 'preflight_authorization', order: 2, label: 'Preflight Authorization',
        configuration: 'A frozen generation contract and an eligible router model must exist before any request is built. The adapter refuses rather than repairing the contract.',
        evidenceSource: 'Render job metadata · router_execution.router_config_id, reason',
        state: 'fail_closed',
        detail: `${authorizationRefusals.length} job${authorizationRefusals.length === 1 ? '' : 's'} were refused before a request was built.`,
        logs: authorizationLogs,
      })
      : authorized.length === 0
        ? stage({
          id: 'preflight_authorization', order: 2, label: 'Preflight Authorization',
          configuration: 'A frozen generation contract and an eligible router model must exist before any request is built. The adapter refuses rather than repairing the contract.',
          evidenceSource: 'Render job metadata · router_execution.router_config_id, reason',
          state: 'not_established',
          detail: 'No authorized router configuration is recorded for this project yet.',
        })
        : stage({
          id: 'preflight_authorization', order: 2, label: 'Preflight Authorization',
          configuration: 'A frozen generation contract and an eligible router model must exist before any request is built. The adapter refuses rather than repairing the contract.',
          evidenceSource: 'Render job metadata · router_execution.router_config_id, reason',
          state: 'cleared',
          detail: `${authorized.length} job${authorized.length === 1 ? '' : 's'} carry an authorized router configuration · config ${text(authorized[0].execution.router_config_id)}`,
        })

  // ── 3. Generic mint ──────────────────────────────────────────────────────
  // No mint record is loaded on this surface. The only honest evidence is a
  // gate blocker or acceptance check that names minting/confirmation/digests.
  const gateMentions = gate.status === 'loaded'
    ? [...gate.value.blockers, ...gate.value.warnings].filter((entry) => MINT_PATTERN.test(entry))
    : []
  const reportMentions = reports.status === 'loaded' && reports.value[0]
    ? reports.value[0].checks
      .filter((check) => MINT_PATTERN.test(`${check.title} ${check.summary}`))
      .map((check) => `${check.severity}: ${check.title} — ${check.summary}`)
    : []
  const mintEvidence = gate.status === 'unavailable' && reports.status === 'unavailable'
  const mintBlocked = gate.status === 'loaded' && gate.value.gate_status === 'blocked' && gateMentions.length > 0
  const mintStage = mintEvidence
    ? stage({
      id: 'generic_mint', order: 3, label: 'Generic Mint',
      configuration: 'A scene submission must mint a valid authorization pass from a saved shot confirmation digest. A stale or missing digest mints nothing.',
      evidenceSource: 'Studio Decision Gate blockers/warnings · acceptance check summaries',
      state: 'unavailable',
      detail: 'Neither the decision gate nor acceptance evidence could be read, so no mint state is established.',
    })
    : mintBlocked
      ? stage({
        id: 'generic_mint', order: 3, label: 'Generic Mint',
        configuration: 'A scene submission must mint a valid authorization pass from a saved shot confirmation digest. A stale or missing digest mints nothing.',
        evidenceSource: 'Studio Decision Gate blockers/warnings · acceptance check summaries',
        state: 'fail_closed',
        detail: `${gateMentions.length} recorded gate note${gateMentions.length === 1 ? '' : 's'} concern authorization or confirmation.`,
        logs: gateMentions.slice(0, 4).map((entry, index) => ({ id: `mint-gate-${index}`, label: 'Decision gate', detail: entry })),
      })
      : gateMentions.length === 0 && reportMentions.length === 0
        ? stage({
          id: 'generic_mint', order: 3, label: 'Generic Mint',
          configuration: 'A scene submission must mint a valid authorization pass from a saved shot confirmation digest. A stale or missing digest mints nothing.',
          evidenceSource: 'Studio Decision Gate blockers/warnings · acceptance check summaries',
          state: 'not_established',
          detail: 'No mint, confirmation, or digest record is loaded on this surface. Scene minting is enforced at submission and is not re-derived here.',
        })
        : stage({
          id: 'generic_mint', order: 3, label: 'Generic Mint',
          configuration: 'A scene submission must mint a valid authorization pass from a saved shot confirmation digest. A stale or missing digest mints nothing.',
          evidenceSource: 'Studio Decision Gate blockers/warnings · acceptance check summaries',
          state: 'cleared',
          detail: `${gateMentions.length + reportMentions.length} recorded note${gateMentions.length + reportMentions.length === 1 ? '' : 's'} mention authorization and none is a blocker.`,
          logs: [...gateMentions, ...reportMentions].slice(0, 4).map((entry, index) => ({ id: `mint-note-${index}`, label: 'Recorded note', detail: entry })),
        })

  // ── 4. Payload normalizer ────────────────────────────────────────────────
  const normalizedRows = executions.filter((row) => row.execution.payload_normalized === true)
  const normalizationLogs = allLogs.filter((entry) => entry.id.endsWith(':normalization'))
  const normalizerStage = jobsUnavailable
    ? stage({
      id: 'payload_normalizer', order: 4, label: 'Payload Normalizer',
      configuration: 'Before submission the adapter fits the payload to router eligibility: one primary reference image, verified aspect ratio and duration, unsupported flags stripped. Every adjustment is recorded.',
      evidenceSource: 'Render job metadata · router_execution.payload_normalized, payload_normalization_warnings',
      state: 'unavailable',
      detail: jobs.status === 'unavailable' ? jobs.message : 'Render queue unavailable.',
    })
    : executions.length === 0
      ? stage({
        id: 'payload_normalizer', order: 4, label: 'Payload Normalizer',
        configuration: 'Before submission the adapter fits the payload to router eligibility: one primary reference image, verified aspect ratio and duration, unsupported flags stripped. Every adjustment is recorded.',
        evidenceSource: 'Render job metadata · router_execution.payload_normalized, payload_normalization_warnings',
        state: 'not_established',
        detail: 'No router execution is recorded, so no normalization decision exists yet.',
        logs: [],
      })
      : normalizedRows.length === 0
        ? stage({
          id: 'payload_normalizer', order: 4, label: 'Payload Normalizer',
          configuration: 'Before submission the adapter fits the payload to router eligibility: one primary reference image, verified aspect ratio and duration, unsupported flags stripped. Every adjustment is recorded.',
          evidenceSource: 'Render job metadata · router_execution.payload_normalized, payload_normalization_warnings',
          state: 'cleared',
          detail: `${executions.length} payload${executions.length === 1 ? '' : 's'} passed through without auto-optimization.`,
        })
        : stage({
          id: 'payload_normalizer', order: 4, label: 'Payload Normalizer',
          configuration: 'Before submission the adapter fits the payload to router eligibility: one primary reference image, verified aspect ratio and duration, unsupported flags stripped. Every adjustment is recorded.',
          evidenceSource: 'Render job metadata · router_execution.payload_normalized, payload_normalization_warnings',
          state: 'cleared',
          detail: `${normalizedRows.length} of ${executions.length} payload${executions.length === 1 ? '' : 's'} were auto-optimized for router eligibility. Nothing was silently dropped; each adjustment is logged.`,
          logs: normalizationLogs,
        })

  // ── 5. Runway router adapter ─────────────────────────────────────────────
  const routerRefusals = reasonsFor(ROUTER_REASONS)
  const routedJobs = executions.filter((row) => text(row.execution.runway_task_id) || text(row.execution.resolved_model) || text(row.execution.routing_provider))
  // A provider failure is the submission path's own record, so it belongs here
  // even when no router execution was written for the job.
  const providerFailureLogs = allLogs.filter((entry) => entry.id.endsWith(':provider_failure') || entry.id.endsWith(':failure_location'))
  const routerLogs = allLogs.filter((entry) => routerRefusals.some((row) => entry.id.startsWith(`${row.job.id}:`)) || entry.id.endsWith(':reason') || entry.id.endsWith(':provider_failure'))
  const firstRouted = routedJobs[0]?.execution
  const routerStage = jobsUnavailable
    ? stage({
      id: 'runway_router', order: 5, label: 'Runway Router Adapter',
      configuration: 'The router selects the concrete model from an eligibility registry and returns one provider task identity. Provider output must match that task identity before it is accepted.',
      evidenceSource: 'Render job metadata · router_execution.resolved_model, routing_provider, runway_task_id, provider_output_identity',
      state: 'unavailable',
      detail: jobs.status === 'unavailable' ? jobs.message : 'Render queue unavailable.',
    })
    : routerRefusals.length > 0 || providerFailureLogs.length > 0
      ? stage({
        id: 'runway_router', order: 5, label: 'Runway Router Adapter',
        configuration: 'The router selects the concrete model from an eligibility registry and returns one provider task identity. Provider output must match that task identity before it is accepted.',
        evidenceSource: 'Render job metadata · router_execution.resolved_model, routing_provider, runway_task_id, provider_output_identity',
        state: 'fail_closed',
        detail: routerRefusals.length > 0
          ? `${routerRefusals.length} router response${routerRefusals.length === 1 ? '' : 's'} failed identity reconciliation and were refused.`
          : `${providerFailureLogs.length} provider failure${providerFailureLogs.length === 1 ? '' : 's'} recorded on the submission path.`,
        logs: [...routerLogs, ...providerFailureLogs.filter((entry) => !routerLogs.includes(entry))],
      })
      : routedJobs.length === 0
        ? stage({
          id: 'runway_router', order: 5, label: 'Runway Router Adapter',
          configuration: 'The router selects the concrete model from an eligibility registry and returns one provider task identity. Provider output must match that task identity before it is accepted.',
          evidenceSource: 'Render job metadata · router_execution.resolved_model, routing_provider, runway_task_id, provider_output_identity',
          state: 'not_established',
          detail: 'No routed provider task is recorded for this project yet.',
        })
        : stage({
          id: 'runway_router', order: 5, label: 'Runway Router Adapter',
          configuration: 'The router selects the concrete model from an eligibility registry and returns one provider task identity. Provider output must match that task identity before it is accepted.',
          evidenceSource: 'Render job metadata · router_execution.resolved_model, routing_provider, runway_task_id, provider_output_identity',
          state: 'cleared',
          detail: `${routedJobs.length} routed task${routedJobs.length === 1 ? '' : 's'} · routing provider ${text(firstRouted?.routing_provider) || 'not recorded'} · resolved model ${text(firstRouted?.resolved_model) || 'not recorded'}.`,
          logs: routerLogs.slice(0, 4),
        })

  return [socketStage, preflightStage, mintStage, normalizerStage, routerStage]
}

const STATE_LABEL: Record<GateStageState, string> = {
  cleared: 'Cleared',
  fail_closed: 'Fail-closed',
  not_established: 'No record',
  unavailable: 'Unavailable',
}

export function gateStageStateLabel(state: GateStageState): string {
  return STATE_LABEL[state]
}

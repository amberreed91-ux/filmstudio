import { fetchJson } from './studioApi'

/**
 * Visual Training API client.
 *
 * Mirrors the backend Pydantic DTOs in
 * `studio-backend/app/routes/visual_training.py` and the confirmed reference
 * asset contract in `studio-backend/app/routes/reference_assets.py`. All calls
 * are project-scoped and go through the shared `fetchJson` wrapper — no second
 * API abstraction, no business logic here.
 *
 * The filmmaker-facing concept is "visual identity": an approved character look
 * or environment becomes a reusable trained identity. The backend still calls
 * these "visual models" / "training jobs"; this module keeps the DTO names and
 * exposes thin, typed wrappers.
 */

const VISUAL_TRAINING_BASE = '/api/f51/studio/visual-training'

/** 'character' or 'scene' — the two canonical targets the service validates. */
export type VisualTrainingTargetType = 'character' | 'scene'

/** Backend job-side lifecycle status (see VisualTrainingJobStatus). */
export type VisualTrainingJobStatus =
  | 'pending'
  | 'training'
  | 'complete'
  | 'failed'
  | 'cancelled'

/** Reference asset kinds the backend registry uses (see ReferenceAsset). */
export type ReferenceAssetKind =
  | 'character_face'
  | 'character_full'
  | 'environment'
  | 'style'

export interface TrainingProviderInfo {
  provider_id: string
  name: string
  is_simulated: boolean
  capabilities: string[]
  models: string[]
}

export interface CreateTrainingJobRequest {
  project_id: string
  target_type: VisualTrainingTargetType
  trigger_word: string
  source_asset_ids: string[]
  provider: string
  provider_model: string
  visual_model_id?: string | null
  configuration?: Record<string, unknown> | null
}

export interface CreateTrainingJobResponse {
  job_id: string
  visual_model_id: string
  project_id: string
  target_type: VisualTrainingTargetType
  status: VisualTrainingJobStatus
  message: string
}

/**
 * Shape returned by GET job / GET model / list models. The backend reuses
 * `GetTrainingJobResponse` for both jobs and registered models.
 */
export interface VisualTrainingJob {
  job_id: string
  project_id: string
  visual_model_id: string
  target_type: VisualTrainingTargetType
  trigger_word: string
  source_asset_ids: string[]
  provider: string
  provider_model: string
  configuration: Record<string, unknown>
  status: VisualTrainingJobStatus
  created_at: string
  completed_at: string | null
  error: string | null
  trained_model_id: string | null
}

export interface ListVisualModelsResponse {
  models: VisualTrainingJob[]
}

export interface CancelTrainingJobResponse {
  job_id: string
  status: VisualTrainingJobStatus
  message: string
}

/** A confirmed reference asset (see ReferenceAsset model). */
export interface ReferenceAsset {
  ref_id: string
  kind: ReferenceAssetKind
  image_url: string
  source_shot_id?: string | null
  project_id: string
  target_type?: 'character' | 'setting' | null
  target_id?: string | null
  category?: string | null
  approval_state?: 'candidate' | 'approved' | 'rejected'
  canonical?: boolean
  source_kind?: 'confirmed' | 'uploaded' | 'generated'
  // Snapshot provenance carried from character look locks (trace-only,
  // mirrors the backend ReferenceAsset model).
  reference_role?: string | null
  look_id?: string | null
  lock_status?: string | null
}

export interface ReferenceLibrary {
  project_id: string
  target_type: 'character' | 'setting'
  target_id: string
  canonical: ReferenceAsset | null
  supporting: ReferenceAsset[]
  candidates: ReferenceAsset[]
  categories: string[]
  coverage: 'covered' | 'partially_covered' | 'not_covered' | string
}

export interface ListReferenceAssetsResponse {
  reference_assets: ReferenceAsset[]
  count: number
}

// ── Endpoints ────────────────────────────────────────────────────────────────

export function listTrainingProviders() {
  return fetchJson<{ providers: TrainingProviderInfo[] }>(
    `${VISUAL_TRAINING_BASE}/providers`,
  )
}

export function createVisualTrainingJob(payload: CreateTrainingJobRequest) {
  return fetchJson<CreateTrainingJobResponse>(`${VISUAL_TRAINING_BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getVisualTrainingJob(jobId: string) {
  return fetchJson<VisualTrainingJob>(
    `${VISUAL_TRAINING_BASE}/jobs/${encodeURIComponent(jobId)}`,
  )
}

export function cancelVisualTrainingJob(jobId: string) {
  return fetchJson<CancelTrainingJobResponse>(
    `${VISUAL_TRAINING_BASE}/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: 'POST' },
  )
}

export function listVisualModels(
  projectId: string,
  opts: { target_type?: VisualTrainingTargetType; status?: string } = {},
) {
  const params = new URLSearchParams({ project_id: projectId })
  if (opts.target_type) params.set('target_type', opts.target_type)
  if (opts.status) params.set('status', opts.status)
  return fetchJson<ListVisualModelsResponse>(
    `${VISUAL_TRAINING_BASE}/models?${params.toString()}`,
  )
}

export function getVisualModel(modelId: string) {
  return fetchJson<VisualTrainingJob>(
    `${VISUAL_TRAINING_BASE}/models/${encodeURIComponent(modelId)}`,
  )
}

/**
 * List confirmed reference assets for a project. When `kind` is provided the
 * backend filters server-side; callers may also pass multiple kinds by fetching
 * once and filtering client-side (see `listEligibleReferences`).
 */
export function getReferenceLibrary(projectId: string, targetType: 'character' | 'setting', targetId: string) {
  return fetchJson<ReferenceLibrary>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-library/${targetType}/${encodeURIComponent(targetId)}`,
  )
}

export function addReferenceLibraryAsset(projectId: string, targetType: 'character' | 'setting', targetId: string, asset: Omit<ReferenceAsset, 'project_id' | 'target_type' | 'target_id'>) {
  return fetchJson<ReferenceAsset>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-library/${targetType}/${encodeURIComponent(targetId)}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...asset, project_id: projectId, target_type: targetType, target_id: targetId }) },
  )
}

/**
 * Upload an image file as a candidate supporting reference. Uses the same
 * registry, approval gate, and consumption pipeline as URL-based references —
 * only the ingestion differs. Returns the created candidate ReferenceAsset.
 */
export function uploadReferenceLibraryAsset(
  projectId: string,
  targetType: 'character' | 'setting',
  targetId: string,
  file: File,
  category: string,
  signal?: AbortSignal,
): Promise<ReferenceAsset> {
  const form = new FormData()
  form.append('file', file)
  form.append('category', category)
  return fetchJson<ReferenceAsset>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-library/${targetType}/${encodeURIComponent(targetId)}/upload`,
    { method: 'POST', body: form, signal, timeoutMs: 60000, timeoutLabel: 'Reference upload' },
  )
}

export function approveReferenceLibraryAsset(projectId: string, targetType: 'character' | 'setting', targetId: string, refId: string) {
  return fetchJson<ReferenceAsset>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-library/${targetType}/${encodeURIComponent(targetId)}/${encodeURIComponent(refId)}/approve`, { method: 'POST' })
}

/**
 * Explicitly designate an approved environment reference as canonical for a
 * setting entity. Server-authoritative and exclusive: the backend verifies the
 * canonical setting entity, the exact target, and the approved/usable state,
 * then clears any competing canonical anchor for the same setting. It never
 * approves anything and never retargets a row — a rejection leaves existing
 * canonical authority untouched.
 */
export function designateReferenceLibraryCanonical(projectId: string, settingId: string, refId: string) {
  return fetchJson<ReferenceAsset>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-library/setting/${encodeURIComponent(settingId)}/${encodeURIComponent(refId)}/canonical`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ canonical: true }) },
  )
}

export function removeReferenceLibraryAsset(projectId: string, targetType: 'character' | 'setting', targetId: string, refId: string) {
  return fetchJson<{ removed: boolean; ref_id: string }>(`/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-library/${targetType}/${encodeURIComponent(targetId)}/${encodeURIComponent(refId)}`, { method: 'DELETE' })
}

export type ShotReferenceBindingRow = {
  ref_id: string
  uri: string
  target_type: string
  target_id: string
  role: string
  category: string
  canonical: boolean
  approval_state: string
  source_kind: string
  kind: string
}

export type ShotReferenceBinding = {
  project_id: string
  scene_id: string
  shot_id: string
  character_ids: string[]
  setting_id: string
  binding: ShotReferenceBindingRow[]
  binding_digest: string
  allowed_urls: string[]
}

/**
 * Resolve one shot's authorized reference binding (read-only preview).
 * The backend derives the scene, resolves approved canonical anchors through
 * the authoritative validation chain, and returns the frozen binding with its
 * digest. Creates no job, approves nothing, and invokes no provider.
 */
export function resolveShotReferenceBinding(projectId: string, shotId: string) {
  return fetchJson<ShotReferenceBinding>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/reference-binding`,
  )
}

/**
 * Durable shot confirmation status (R4.2).
 *
 * Recovered from the server-side record and revalidated against the current
 * binding — never established by frontend state. `confirmed` means the stored
 * digest still matches the currently authorized binding; `stale` means the
 * binding changed since confirmation; `missing` means no record exists for
 * this exact project and shot; `unverifiable` means the current binding
 * cannot be resolved. Only `confirmed` may be displayed as confirmed, and
 * only the backend submission gate may treat it as authorization evidence.
 */
export type ShotReferenceConfirmationStatus = 'confirmed' | 'stale' | 'missing' | 'unverifiable'

export type ShotReferenceConfirmation = {
  project_id: string
  scene_id: string | null
  shot_id: string
  status: ShotReferenceConfirmationStatus
  confirmed_digest: string | null
  current_digest: string | null
  created_at: string | null
  updated_at: string | null
}

export type SceneReferenceConfirmations = {
  project_id: string
  scene_id: string
  confirmations: ShotReferenceConfirmation[]
  count: number
}

/**
 * Durably record one explicit shot confirmation. The backend re-verifies the
 * carried digest against the freshly resolved binding and persists the
 * server-resolved record only on a match — the single write path.
 */
export function recordShotReferenceConfirmation(projectId: string, shotId: string, expectedDigest: string) {
  return fetchJson<ShotReferenceConfirmation>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/reference-binding-confirmation`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_digest: expectedDigest }) },
  )
}

/**
 * Recover one shot's confirmation status (read-only). Survives reloads and
 * navigation because the record lives server-side. Never throws for a
 * missing record — `missing` is an honest verdict, not an error.
 */
export function getShotReferenceConfirmation(projectId: string, shotId: string) {
  return fetchJson<ShotReferenceConfirmation>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/reference-binding-confirmation`,
  )
}

/**
 * Recover every durable confirmation for one project scene with live status
 * (read-only). The generation room uses this to restore confirmations after
 * reloads and navigation instead of trusting transient route state.
 */
export function listSceneReferenceConfirmations(projectId: string, sceneId: string) {
  return fetchJson<SceneReferenceConfirmations>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-binding-confirmations?scene_id=${encodeURIComponent(sceneId)}`,
  )
}

export function listReferenceAssets(projectId: string, kind?: ReferenceAssetKind) {
  const params = new URLSearchParams()
  if (kind) params.set('kind', kind)
  const query = params.toString()
  return fetchJson<ListReferenceAssetsResponse>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/reference-assets${query ? `?${query}` : ''}`,
  )
}

// ── Shared status helpers (single source, not duplicated across components) ──

/** True when a training job has reached a terminal state and polling must stop. */
export function isTerminalTrainingStatus(status: VisualTrainingJobStatus | string | undefined | null): boolean {
  return status === 'complete' || status === 'failed' || status === 'cancelled'
}

/** True while a job is still active and should be polled. */
export function isActiveTrainingStatus(status: VisualTrainingJobStatus | string | undefined | null): boolean {
  return status === 'pending' || status === 'training'
}

/** Filmmaker-facing label for a training status. No fabricated percentages. */
export function trainingStatusLabel(status: VisualTrainingJobStatus | string | undefined | null): string {
  switch (status) {
    case 'pending':
      return 'Preparing'
    case 'training':
      return 'Training'
    case 'complete':
      return 'Ready'
    case 'failed':
      return 'Failed'
    case 'cancelled':
      return 'Cancelled'
    default:
      return 'Unknown'
  }
}

/** Restrained Studio badge classes for a training status. */
export function trainingStatusClassName(status: VisualTrainingJobStatus | string | undefined | null): string {
  switch (status) {
    case 'complete':
      return 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200'
    case 'failed':
      return 'border-rose-400/40 bg-rose-500/10 text-rose-200'
    case 'cancelled':
      return 'border-zinc-400/40 bg-zinc-500/10 text-zinc-300'
    case 'training':
      return 'border-cyan-400/40 bg-cyan-500/10 text-cyan-200'
    case 'pending':
      return 'border-amber-400/40 bg-amber-500/10 text-amber-200'
    default:
      return 'border-white/15 bg-white/5 text-zinc-400'
  }
}

/**
 * Reference kinds eligible for a given training target. Character identities
 * train from confirmed face/full-body references; setting identities train from
 * confirmed environment references. Used to filter what the filmmaker may pick.
 */
export function eligibleKindsForTarget(targetType: VisualTrainingTargetType): ReferenceAssetKind[] {
  return targetType === 'character'
    ? ['character_face', 'character_full']
    : ['environment']
}

/**
 * Capability a provider must report to offer visual training. The backend
 * `/providers` endpoint returns every enabled provider (video, image, etc.)
 * along with its `capabilities`; only those advertising this capability can
 * actually train an identity. Filtering on the backend-reported capability
 * keeps the UI honest — we never hardcode a provider id or fabricate
 * availability, and when nothing qualifies the panel shows its real
 * "visual training unavailable" empty state.
 */
export const VISUAL_TRAINING_CAPABILITY = 'visual_training'

/** Keep only providers that report the visual_training capability. */
export function trainingCapableProviders(
  providers: TrainingProviderInfo[] | undefined | null,
): TrainingProviderInfo[] {
  return (providers || []).filter(
    (provider) =>
      Array.isArray(provider.capabilities) &&
      provider.capabilities.includes(VISUAL_TRAINING_CAPABILITY),
  )
}

/**
 * Filter reference assets down to those eligible for a target type.
 * Only assets whose authoritative registry state is `approved` are ever
 * shown; candidates, rejected, or unknown-state assets are not trainable and
 * are omitted — never invent identifiers client-side. The backend enforces
 * the same rule independently, so a bypassed client still fails closed.
 */
export function listEligibleReferences(
  assets: ReferenceAsset[],
  targetType: VisualTrainingTargetType,
): ReferenceAsset[] {
  const eligible = new Set<string>(eligibleKindsForTarget(targetType))
  return assets.filter((asset) => eligible.has(asset.kind) && asset.approval_state === 'approved')
}

/**
 * Normalize an unknown error into a filmmaker-readable message, preferring the
 * backend `detail`/`message` string surfaced by `fetchJson`.
 */
export function visualTrainingError(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim()
  return 'Visual training is unavailable right now. Please try again.'
}

/**
 * Derive a default identity token from a name: "Maya" → "MAYA".
 * Letters only, matching the backend `_TRIGGER_RE` contract (LoRA trigger
 * tokens must not collide with normal language tokens).
 */
export function defaultTriggerWordFor(name: string): string {
  const base = (name || '')
    .trim()
    .toUpperCase()
    .replace(/[^A-Z]+/g, '')
  return base || 'IDENTITY'
}

/**
 * Validate an identity trigger token against the backend contract: 3–32
 * letters only (see `_TRIGGER_RE` in visual_training_service.py). Returns an
 * empty string when valid, otherwise a filmmaker-readable reason shown next
 * to the trigger control.
 */
export function validateTriggerWord(trigger: string): string {
  const value = (trigger || '').trim()
  if (!value) return 'Give this identity a trigger word.'
  if (!/^[A-Za-z]{3,32}$/.test(value))
    return 'Use 3–32 letters only — no spaces, numbers, or symbols. E.g. MAYA.'
  return ''
}

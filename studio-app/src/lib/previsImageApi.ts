import { buildStudioApiUrl, fetchJson } from './studioApi'
import { addReferenceLibraryAsset, type ReferenceAsset } from './visualTrainingApi'

/**
 * Reference Space still generation client.
 *
 * Mirrors the backend contract in `studio-backend/app/routes/previs_image.py`:
 * one explicit creator action generates one still, which is stored under the
 * project's outputs and returned as a URL. Nothing here approves, canonicalises,
 * or binds anything — binding reuses the existing reference-library write path,
 * where a generated still always lands as a candidate.
 *
 * No business logic lives here: this module only shapes requests and responses.
 */

const PREVIS_IMAGE_BASE = '/api/f51/studio'

/** The two creative targets the generator serves. */
export type PrevisImageMode = 'character' | 'setting'

/** Session history the panel keeps: recent stills, newest first. */
export const MAX_GENERATED_STILLS = 12

/** Framings the provider is documented to support. */
export type PrevisAspectRatio = '16:9' | '1:1' | '9:16'

export const PREVIS_ASPECT_RATIOS: readonly PrevisAspectRatio[] = ['16:9', '1:1', '9:16'] as const

export interface PrevisImagePreset {
  id: string
  label: string
  prompt_fragment: string
}

export interface PrevisImagePresets {
  style_presets: PrevisImagePreset[]
  lighting_presets: PrevisImagePreset[]
  aspect_ratios: string[]
  max_prompt_chars: number
}

export interface GeneratePrevisImageRequest {
  project_id: string
  mode: PrevisImageMode
  prompt: string
  aspect_ratio: PrevisAspectRatio
  style_preset: string
  lighting_preset: string
  /** Omit to let the backend draw a seed; the drawn seed comes back. */
  seed?: number | null
}

export interface GeneratedPrevisImage {
  project_id: string
  mode: PrevisImageMode
  image_url: string
  seed: number
  aspect_ratio: string
  style_preset: string
  lighting_preset: string
  provider: string
  model: string
  prompt: string
  created_at: string
}

/** Absolute provider URLs pass through; project-relative outputs resolve against the API base. */
export function resolveAssetUrl(url: string | null | undefined): string | null {
  if (!url || !url.trim()) return null
  const trimmed = url.trim()
  return /^https?:\/\//.test(trimmed) || trimmed.startsWith('data:') ? trimmed : buildStudioApiUrl(trimmed)
}

/** Preset vocabulary the backend validates against (never duplicated here). */
export function getPrevisImagePresets() {
  return fetchJson<PrevisImagePresets>(`${PREVIS_IMAGE_BASE}/previs-image-presets`, {
    timeoutMs: 10000,
  })
}

/**
 * Generate one reference still. The provider call is bounded server-side
 * (single attempt, no retries), so this client waits longer than the default
 * request budget rather than abandoning a request the creator already paid for.
 */
export function generatePrevisImage(request: GeneratePrevisImageRequest) {
  const body: GeneratePrevisImageRequest = {
    project_id: request.project_id,
    mode: request.mode,
    prompt: request.prompt,
    aspect_ratio: request.aspect_ratio,
    style_preset: request.style_preset || 'none',
    lighting_preset: request.lighting_preset || 'none',
  }
  if (typeof request.seed === 'number' && Number.isFinite(request.seed)) body.seed = request.seed
  return fetchJson<GeneratedPrevisImage>(`${PREVIS_IMAGE_BASE}/generate-previs-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    timeoutMs: 180000,
    timeoutLabel: 'Reference generation',
  })
}

/**
 * The registry row a generated still becomes when the creator binds it.
 *
 * `source_shot_id` is carried as provenance only: it records which shot the
 * still was developed for. It is never an approval, and the backend coerces a
 * generated row to `candidate` regardless of what is sent here.
 */
export function buildBoundReferenceCandidate(
  image: GeneratedPrevisImage,
  options: { refId?: string; shotId?: string | null } = {},
): Omit<ReferenceAsset, 'project_id' | 'target_type' | 'target_id'> {
  const isCharacter = image.mode === 'character'
  const shotId = (options.shotId || '').trim()
  return {
    ref_id: options.refId || `ref_gen_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    kind: isCharacter ? 'character_full' : 'environment',
    image_url: image.image_url,
    source_shot_id: shotId || null,
    category: isCharacter ? 'full_body' : 'wide',
    approval_state: 'candidate',
    canonical: false,
    source_kind: 'generated',
    reference_role: isCharacter ? 'generated_character' : 'generated_setting',
  }
}

/**
 * Register a generated still against the active target as a candidate.
 *
 * Binding is a registry write, not an approval: the still arrives as a
 * candidate and still needs the explicit approval step before generation can
 * use it. Rejections leave the canonical reference and pipeline state untouched.
 */
export function bindGeneratedStillToShot(
  projectId: string,
  target: { kind: PrevisImageMode; targetId: string },
  image: GeneratedPrevisImage,
  shotId: string | null,
) {
  return addReferenceLibraryAsset(
    projectId,
    target.kind,
    target.targetId,
    buildBoundReferenceCandidate(image, { shotId }),
  )
}

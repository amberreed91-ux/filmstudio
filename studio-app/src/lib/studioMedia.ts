import type { RenderJob } from './studioApi'

export type StudioMediaSource =
  | 'hosted_render'
  | 'render_preview'
  | 'mock_render'
  | 'package'
  | 'review'
  | 'keyframe'
  | 'placeholder'

export type StudioMediaKind = 'video' | 'image' | 'unknown'

export type PrimaryStudioMedia = {
  url: string
  kind: StudioMediaKind
  source: StudioMediaSource
  providerMode: string
  label: string
  jobId?: string
}

type SelectPrimaryStudioMediaInput = {
  renderJobs?: RenderJob[]
  sceneId?: string
  shotId?: string
  packageUrl?: string
  reviewUrl?: string
  keyframeUrl?: string
  placeholderUrl?: string
}

type AnyRecord = Record<string, unknown>

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function isCompletedStatus(status: string): boolean {
  const value = status.trim().toLowerCase()
  return value === 'complete' || value === 'completed' || value === 'success'
}

function mediaKindFromUrl(url: string): StudioMediaKind {
  const value = url.trim().toLowerCase()
  if (!value) return 'unknown'
  if (/\.(mp4|mov|webm|m3u8)(\?|$)/.test(value)) return 'video'
  if (/\.(png|jpg|jpeg|webp|gif|avif|bmp)(\?|$)/.test(value)) return 'image'
  if (value.startsWith('data:image/')) return 'image'
  if (value.includes('cloudfront.net')) return 'video'
  return 'unknown'
}

function providerModeFromJob(job: RenderJob): string {
  const normalizedMeta = asRecord(asRecord(job.output_payload?.metadata)?.provider_response_normalized)
  const meta = asRecord(normalizedMeta?.metadata)
  return asString(meta?.provider_mode).trim().toLowerCase()
}

function jobOutputUrl(job: RenderJob): string {
  const payload = asRecord(job.output_payload) || {}
  const meta = asRecord(payload.metadata)
  const normalized = asRecord(meta?.provider_response_normalized)
  const output = asRecord(normalized?.output)
  return (
    asString(payload.asset_url).trim()
    || asString(output?.video_url).trim()
    || asString((job as unknown as AnyRecord).output_url).trim()
  )
}

function jobPreviewUrl(job: RenderJob): string {
  const payload = asRecord(job.output_payload) || {}
  const meta = asRecord(payload.metadata)
  const normalized = asRecord(meta?.provider_response_normalized)
  const output = asRecord(normalized?.output)
  return (
    asString(payload.thumbnail_url).trim()
    || asString(output?.preview_url).trim()
    || asString((job as unknown as AnyRecord).preview_url).trim()
  )
}

function jobMatchesContext(job: RenderJob, sceneId: string, shotId: string): boolean {
  if (!sceneId && !shotId) return true
  const raw = job as unknown as AnyRecord
  const payloadMeta = asRecord(job.output_payload?.metadata) || {}
  const normalizedMeta = asRecord(asRecord(payloadMeta.provider_response_normalized)?.metadata) || {}

  const jobShotId = asString(job.shot_id).trim()
  const jobSceneId =
    asString(raw.scene_id).trim()
    || asString(payloadMeta.scene_id).trim()
    || asString(normalizedMeta.scene_id).trim()

  if (shotId && jobShotId && jobShotId === shotId) return true
  if (sceneId && jobSceneId && jobSceneId === sceneId) return true
  if (sceneId && jobShotId && jobShotId.includes(sceneId)) return true
  return false
}

export function selectPrimaryStudioMedia(input: SelectPrimaryStudioMediaInput): PrimaryStudioMedia {
  const sceneId = (input.sceneId || '').trim()
  const shotId = (input.shotId || '').trim()
  const jobs = (input.renderJobs || []).filter((job) => isCompletedStatus(job.status))
  const matchingJobs = jobs.filter((job) => jobMatchesContext(job, sceneId, shotId))
  const pool = matchingJobs.length > 0 ? matchingJobs : jobs

  const hostedOutput = pool.find((job) => {
    const mode = providerModeFromJob(job)
    return mode === 'hosted_api' && Boolean(jobOutputUrl(job))
  })
  if (hostedOutput) {
    const url = jobOutputUrl(hostedOutput)
    return {
      url,
      kind: mediaKindFromUrl(url),
      source: 'hosted_render',
      providerMode: providerModeFromJob(hostedOutput),
      label: 'Hosted render output',
      jobId: hostedOutput.id,
    }
  }

  const previewJob = pool.find((job) => Boolean(jobPreviewUrl(job)))
  if (previewJob) {
    const url = jobPreviewUrl(previewJob)
    return {
      url,
      kind: mediaKindFromUrl(url),
      source: 'render_preview',
      providerMode: providerModeFromJob(previewJob),
      label: 'Render preview',
      jobId: previewJob.id,
    }
  }

  const mockOutput = pool.find((job) => {
    const mode = providerModeFromJob(job)
    return mode === 'mock_success' && Boolean(jobOutputUrl(job))
  })
  if (mockOutput) {
    const url = jobOutputUrl(mockOutput)
    return {
      url,
      kind: mediaKindFromUrl(url),
      source: 'mock_render',
      providerMode: providerModeFromJob(mockOutput),
      label: 'Mock render output',
      jobId: mockOutput.id,
    }
  }

  const packageUrl = (input.packageUrl || '').trim()
  if (packageUrl) {
    return {
      url: packageUrl,
      kind: mediaKindFromUrl(packageUrl),
      source: 'package',
      providerMode: '',
      label: 'Final package output',
    }
  }

  const reviewUrl = (input.reviewUrl || '').trim()
  if (reviewUrl) {
    return {
      url: reviewUrl,
      kind: mediaKindFromUrl(reviewUrl),
      source: 'review',
      providerMode: '',
      label: 'Review output',
    }
  }

  const keyframeUrl = (input.keyframeUrl || '').trim()
  if (keyframeUrl) {
    return {
      url: keyframeUrl,
      kind: mediaKindFromUrl(keyframeUrl),
      source: 'keyframe',
      providerMode: '',
      label: 'Keyframe fallback',
    }
  }

  return {
    url: (input.placeholderUrl || '').trim(),
    kind: mediaKindFromUrl(input.placeholderUrl || ''),
    source: 'placeholder',
    providerMode: '',
    label: 'Placeholder',
  }
}

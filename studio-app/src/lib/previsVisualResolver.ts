import type { RenderJob, VideoAsset, VideoKeyframe } from './studioApi'

type AnyRecord = Record<string, unknown>

export type VisualMatchSourceType =
  | 'runway_render'
  | 'uploaded_video_keyframe'
  | 'project_level_fallback'
  | 'none'

export type VisualMatchResult = {
  visual_url: string
  source_type: VisualMatchSourceType
  confidence: number
  match_reason: string
  job_id?: string
  asset_id?: string
  keyframe_id?: string
}

type SceneLike = Record<string, unknown>
type ShotLike = Record<string, unknown>

type KeyframeCandidate = VideoKeyframe & {
  asset_title?: string
  asset_metadata?: Record<string, unknown>
}

function asRecord(value: unknown): AnyRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as AnyRecord
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function normalizeText(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

function includesNormalized(haystack: string, needle: string): boolean {
  const nHaystack = normalizeText(haystack)
  const nNeedle = normalizeText(needle)
  if (!nHaystack || !nNeedle) return false
  return nHaystack.includes(nNeedle)
}

function sceneIdFromScene(scene: SceneLike): string {
  return asString(scene.scene_id).trim()
}

function sceneTitleFromScene(scene: SceneLike): string {
  return (
    asString(scene.scene_title).trim()
    || asString(scene.title).trim()
    || asString(scene.heading).trim()
    || asString(scene.name).trim()
  )
}

function sceneTextFromScene(scene: SceneLike): string {
  return (
    asString(scene.scene_text).trim()
    || asString(scene.script_text).trim()
    || asString(scene.description).trim()
    || asString(scene.summary).trim()
  )
}

function shotIdFromShot(shot: ShotLike): string {
  return asString(shot.shot_id).trim()
}

function shotTitleFromShot(shot: ShotLike): string {
  return asString(shot.shot_title).trim() || asString(shot.title).trim() || asString(shot.name).trim()
}

function renderJobUrl(job: RenderJob): string {
  return asString(job.output_payload?.asset_url).trim()
}

function renderJobPrompt(job: RenderJob): string {
  return asString(job.input_payload?.prompt).trim()
}

function renderJobMetadata(job: RenderJob): AnyRecord {
  const outputMeta = asRecord(job.output_payload?.metadata) || {}
  const rawMeta = asRecord((job as unknown as AnyRecord).metadata) || {}
  return { ...rawMeta, ...outputMeta }
}

function renderJobSceneId(job: RenderJob): string {
  const raw = job as unknown as AnyRecord
  const meta = renderJobMetadata(job)
  return (
    asString(raw.scene_id).trim()
    || asString(meta.scene_id).trim()
    || asString(meta.sceneId).trim()
  )
}

function renderJobShotId(job: RenderJob): string {
  const meta = renderJobMetadata(job)
  return asString(job.shot_id).trim() || asString(meta.shot_id).trim() || asString(meta.shotId).trim()
}

function renderJobSceneTitle(job: RenderJob): string {
  const raw = job as unknown as AnyRecord
  const meta = renderJobMetadata(job)
  return (
    asString(raw.scene_title).trim()
    || asString(meta.scene_title).trim()
    || asString(meta.sceneTitle).trim()
  )
}

function renderJobShotTitle(job: RenderJob): string {
  const raw = job as unknown as AnyRecord
  const meta = renderJobMetadata(job)
  return (
    asString(raw.shot_title).trim()
    || asString(meta.shot_title).trim()
    || asString(meta.shotTitle).trim()
  )
}

function isCompletedJob(job: RenderJob): boolean {
  const status = asString(job.status).trim().toLowerCase()
  return status === 'complete' || status === 'completed' || status === 'success'
}

function flattenKeyframes(videoAssets: VideoAsset[], keyframesByAsset: Record<string, VideoKeyframe[]>): KeyframeCandidate[] {
  const list: KeyframeCandidate[] = []
  for (const asset of videoAssets) {
    const keyframes = keyframesByAsset[asset.asset_id] || []
    for (const keyframe of keyframes) {
      list.push({
        ...keyframe,
        asset_title: asset.title,
        asset_metadata: asset.metadata,
      })
    }
  }
  return list
}

function keyframeMetaValue(keyframe: KeyframeCandidate, key: string): string {
  const km = asRecord(keyframe.metadata) || {}
  const am = asRecord(keyframe.asset_metadata) || {}
  return asString(km[key]).trim() || asString(am[key]).trim()
}

function matchRenderJob(
  candidates: RenderJob[],
  sceneId: string,
  shotId: string,
  sceneTitle: string,
  shotTitle: string,
  sceneText: string,
): VisualMatchResult | null {
  const withUrls = candidates.filter((job) => Boolean(renderJobUrl(job)))

  const exactShot = withUrls.find((job) => renderJobShotId(job) === shotId && shotId)
  if (exactShot) {
    return {
      visual_url: renderJobUrl(exactShot),
      source_type: 'runway_render',
      confidence: 1,
      match_reason: 'exact shot_id match',
      job_id: exactShot.id,
    }
  }

  const exactScene = withUrls.find((job) => renderJobSceneId(job) === sceneId && sceneId)
  if (exactScene) {
    return {
      visual_url: renderJobUrl(exactScene),
      source_type: 'runway_render',
      confidence: 0.95,
      match_reason: 'exact scene_id match',
      job_id: exactScene.id,
    }
  }

  const metadataScene = withUrls.find((job) => {
    const meta = renderJobMetadata(job)
    const metaScene = asString(meta.scene_id).trim() || asString(meta.sceneId).trim()
    return Boolean(sceneId && metaScene && metaScene === sceneId)
  })
  if (metadataScene) {
    return {
      visual_url: renderJobUrl(metadataScene),
      source_type: 'runway_render',
      confidence: 0.9,
      match_reason: 'metadata.scene_id match',
      job_id: metadataScene.id,
    }
  }

  const metadataShot = withUrls.find((job) => {
    const meta = renderJobMetadata(job)
    const metaShot = asString(meta.shot_id).trim() || asString(meta.shotId).trim()
    return Boolean(shotId && metaShot && metaShot === shotId)
  })
  if (metadataShot) {
    return {
      visual_url: renderJobUrl(metadataShot),
      source_type: 'runway_render',
      confidence: 0.86,
      match_reason: 'metadata.shot_id match',
      job_id: metadataShot.id,
    }
  }

  const sceneTitleMatch = withUrls.find((job) => {
    return Boolean(sceneTitle && includesNormalized(renderJobSceneTitle(job), sceneTitle))
  })
  if (sceneTitleMatch) {
    return {
      visual_url: renderJobUrl(sceneTitleMatch),
      source_type: 'runway_render',
      confidence: 0.74,
      match_reason: 'normalized scene title match',
      job_id: sceneTitleMatch.id,
    }
  }

  const shotTitleMatch = withUrls.find((job) => {
    return Boolean(shotTitle && includesNormalized(renderJobShotTitle(job), shotTitle))
  })
  if (shotTitleMatch) {
    return {
      visual_url: renderJobUrl(shotTitleMatch),
      source_type: 'runway_render',
      confidence: 0.7,
      match_reason: 'normalized shot title match',
      job_id: shotTitleMatch.id,
    }
  }

  const promptMatch = withUrls.find((job) => {
    const prompt = renderJobPrompt(job)
    if (!prompt) return false
    const sceneTitleInPrompt = sceneTitle && includesNormalized(prompt, sceneTitle)
    const sceneTextInPrompt = sceneText && includesNormalized(prompt, sceneText.slice(0, 120))
    return Boolean(sceneTitleInPrompt || sceneTextInPrompt)
  })
  if (promptMatch) {
    return {
      visual_url: renderJobUrl(promptMatch),
      source_type: 'runway_render',
      confidence: 0.62,
      match_reason: 'prompt contains scene context',
      job_id: promptMatch.id,
    }
  }

  const fallback = [...withUrls].sort((a, b) => {
    const aTime = Date.parse(a.updated_at || a.created_at || '') || 0
    const bTime = Date.parse(b.updated_at || b.created_at || '') || 0
    return bTime - aTime
  })[0]

  if (fallback) {
    return {
      visual_url: renderJobUrl(fallback),
      source_type: 'project_level_fallback',
      confidence: 0.35,
      match_reason: 'project-level fallback (most recent completed render)',
      job_id: fallback.id,
    }
  }

  return null
}

function matchKeyframe(
  candidates: KeyframeCandidate[],
  sceneId: string,
  shotId: string,
  sceneTitle: string,
  shotTitle: string,
): VisualMatchResult | null {
  const withUrl = candidates.filter((k) => Boolean(asString(k.frame_url).trim() || asString(k.frame_path).trim()))

  const exactShot = withUrl.find((k) => keyframeMetaValue(k, 'shot_id') === shotId && shotId)
  if (exactShot) {
    return {
      visual_url: asString(exactShot.frame_url).trim() || asString(exactShot.frame_path).trim(),
      source_type: 'uploaded_video_keyframe',
      confidence: 0.8,
      match_reason: 'matched uploaded video keyframe by shot_id',
      asset_id: exactShot.asset_id,
      keyframe_id: exactShot.keyframe_id,
    }
  }

  const exactScene = withUrl.find((k) => keyframeMetaValue(k, 'scene_id') === sceneId && sceneId)
  if (exactScene) {
    return {
      visual_url: asString(exactScene.frame_url).trim() || asString(exactScene.frame_path).trim(),
      source_type: 'uploaded_video_keyframe',
      confidence: 0.74,
      match_reason: 'matched uploaded video keyframe by scene_id',
      asset_id: exactScene.asset_id,
      keyframe_id: exactScene.keyframe_id,
    }
  }

  const titleMatch = withUrl.find((k) => {
    const title = asString(k.asset_title).trim()
    return (sceneTitle && includesNormalized(title, sceneTitle)) || (shotTitle && includesNormalized(title, shotTitle))
  })
  if (titleMatch) {
    return {
      visual_url: asString(titleMatch.frame_url).trim() || asString(titleMatch.frame_path).trim(),
      source_type: 'uploaded_video_keyframe',
      confidence: 0.6,
      match_reason: 'normalized scene/shot title match to uploaded asset',
      asset_id: titleMatch.asset_id,
      keyframe_id: titleMatch.keyframe_id,
    }
  }

  return null
}

export function resolveVisualForSceneAndShot(
  projectId: string,
  scene: SceneLike,
  shot: ShotLike,
  renderJobs: RenderJob[],
  videoAssets: VideoAsset[],
  keyframesByAssetId: Record<string, VideoKeyframe[]>,
): VisualMatchResult {
  const sceneId = sceneIdFromScene(scene)
  const shotId = shotIdFromShot(shot)
  const sceneTitle = sceneTitleFromScene(scene)
  const shotTitle = shotTitleFromShot(shot)
  const sceneText = sceneTextFromScene(scene)

  const projectRenderJobs = renderJobs.filter(
    (job) => asString(job.project_id).trim() === projectId && isCompletedJob(job),
  )

  const renderMatch = matchRenderJob(projectRenderJobs, sceneId, shotId, sceneTitle, shotTitle, sceneText)
  if (renderMatch) return renderMatch

  const projectAssets = videoAssets.filter((asset) => asString(asset.project_id).trim() === projectId)
  const keyframeCandidates = flattenKeyframes(projectAssets, keyframesByAssetId)
  const keyframeMatch = matchKeyframe(keyframeCandidates, sceneId, shotId, sceneTitle, shotTitle)
  if (keyframeMatch) return keyframeMatch

  return {
    visual_url: '',
    source_type: 'none',
    confidence: 0,
    match_reason: 'no visual render yet',
  }
}

export function resolveGenerateSceneShotId(params: {
  selectedShotId?: string | null
  normalizedShotId?: string | null
  completedRenderShotIds?: string[]
  selectedSceneId?: string | null
}): string {
  const selectedShotId = (params.selectedShotId || '').trim()
  if (selectedShotId) return selectedShotId

  const normalizedShotId = (params.normalizedShotId || '').trim()
  if (normalizedShotId) return normalizedShotId

  const completedShotIds = (params.completedRenderShotIds || [])
    .map((shotId) => (shotId || '').trim())
    .filter(Boolean)
  if (completedShotIds.length > 0) return completedShotIds[0]

  const selectedSceneId = (params.selectedSceneId || '').trim()
  if (selectedSceneId) return `${selectedSceneId}_shot_001`

  return ''
}

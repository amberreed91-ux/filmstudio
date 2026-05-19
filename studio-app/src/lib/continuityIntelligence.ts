import type { ContinuityIssue } from './studioApi'

export const CONTINUITY_ISSUE_TYPES: ContinuityIssue['issue_type'][] = [
  'visual_drift',
  'lighting_mismatch',
  'mood_shift',
  'composition_break',
  'palette_drift',
  'reference_mismatch',
  'continuity_strength',
]

type Severity = ContinuityIssue['severity']

const SEVERITY_ORDER: Record<Severity, number> = {
  high: 3,
  medium: 2,
  low: 1,
}

function toTime(value: string | undefined): number {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

function includesAny(haystack: string, needles: string[]): boolean {
  if (!haystack || needles.length === 0) return false
  return needles.some((needle) => Boolean(needle) && haystack.includes(needle))
}

export function continuityIssueFields(issue: ContinuityIssue): string[] {
  return [
    issue.issue_id,
    issue.source_keyframe_id || '',
    issue.compared_keyframe_id || '',
    issue.asset_id || '',
    issue.source_asset_id || '',
    issue.compared_asset_id || '',
  ]
}

/** True if the issue references this asset in any known field. */
export function continuityIssueTouchesAsset(issue: ContinuityIssue, assetId: string): boolean {
  if (!assetId) return false
  return continuityIssueFields(issue).some((field) => field === assetId)
}

export function summarizeContinuityIssues(issues: ContinuityIssue[]) {
  const severityCounts: Record<Severity, number> = { high: 0, medium: 0, low: 0 }
  const issueTypeCounts = Object.fromEntries(
    CONTINUITY_ISSUE_TYPES.map((type) => [type, 0]),
  ) as Record<ContinuityIssue['issue_type'], number>

  for (const issue of issues) {
    severityCounts[issue.severity] += 1
    issueTypeCounts[issue.issue_type] += 1
  }

  const ranked = [...issues].sort((a, b) => {
    const severityDiff = SEVERITY_ORDER[b.severity] - SEVERITY_ORDER[a.severity]
    if (severityDiff !== 0) return severityDiff
    return toTime(b.created_at) - toTime(a.created_at)
  })

  return {
    total: issues.length,
    severityCounts,
    issueTypeCounts,
    topIssue: ranked[0] || null,
  }
}

export function isInsufficientVisualData(params: {
  frameAnalysisCount: number
  embeddingCount: number
}) {
  return params.frameAnalysisCount <= 0 && params.embeddingCount <= 0
}

export function mapContinuityIssuesToScene(params: {
  issues: ContinuityIssue[]
  projectId: string
  sceneId: string
  shotIds: string[]
}) {
  const projectIssues = params.issues.filter((issue) => issue.project_id === params.projectId)
  if (!params.sceneId) {
    return { projectIssues, sceneIssues: [] as ContinuityIssue[] }
  }

  const keys = [params.sceneId, ...params.shotIds].filter(Boolean)
  const sceneIssues = projectIssues.filter((issue) =>
    continuityIssueFields(issue).some((field) => includesAny(field, keys)),
  )

  return { projectIssues, sceneIssues }
}

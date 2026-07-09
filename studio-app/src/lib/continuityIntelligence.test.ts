import { describe, expect, it } from 'vitest'
import type { ContinuityIssue } from './studioApi'
import { isInsufficientVisualData, mapContinuityIssuesToScene, summarizeContinuityIssues } from './continuityIntelligence'

function makeIssue(overrides: Partial<ContinuityIssue>): ContinuityIssue {
  return {
    issue_id: 'issue-1',
    project_id: 'project-a',
    issue_type: 'reference_mismatch',
    severity: 'high',
    confidence: 0.9,
    description: 'desc',
    evidence: 'evidence',
    recommendation: 'recommend',
    notes: '',
    metadata: {},
    created_at: '2026-05-15T01:51:59.228722+00:00',
    ...overrides,
  }
}

describe('continuityIntelligence helpers', () => {
  it('summarizes total continuity count from API issue data', () => {
    const summary = summarizeContinuityIssues([
      makeIssue({ issue_id: 'a' }),
      makeIssue({ issue_id: 'b', severity: 'medium' }),
      makeIssue({ issue_id: 'c', severity: 'low' }),
      makeIssue({ issue_id: 'd' }),
    ])
    expect(summary.total).toBe(4)
  })

  it('builds severity buckets for Crew Ops', () => {
    const summary = summarizeContinuityIssues([
      makeIssue({ issue_id: 'a', severity: 'high' }),
      makeIssue({ issue_id: 'b', severity: 'high' }),
      makeIssue({ issue_id: 'c', severity: 'medium', issue_type: 'mood_shift' }),
      makeIssue({ issue_id: 'd', severity: 'low', issue_type: 'visual_drift' }),
    ])
    expect(summary.severityCounts).toEqual({ high: 2, medium: 1, low: 1 })
    expect(summary.issueTypeCounts.reference_mismatch).toBe(2)
    expect(summary.issueTypeCounts.mood_shift).toBe(1)
    expect(summary.issueTypeCounts.visual_drift).toBe(1)
  })

  it('supports empty-state truth checks when no issues exist', () => {
    const summary = summarizeContinuityIssues([])
    expect(summary.total).toBe(0)
    expect(isInsufficientVisualData({ frameAnalysisCount: 2, embeddingCount: 1 })).toBe(false)
  })

  it('returns project-level fallback conditions when scene mapping is unavailable', () => {
    const issues = [makeIssue({ issue_id: 'a', project_id: 'project-a', source_asset_id: 'asset-only-1' })]
    const mapped = mapContinuityIssuesToScene({
      issues,
      projectId: 'project-a',
      sceneId: 'scene_001',
      shotIds: ['shot_001'],
    })
    expect(mapped.projectIssues).toHaveLength(1)
    expect(mapped.sceneIssues).toHaveLength(0)
  })

  it('prevents cross-project issue leakage', () => {
    const issues = [
      makeIssue({ issue_id: 'a', project_id: 'project-a', source_asset_id: 'scene_001::shot_001' }),
      makeIssue({ issue_id: 'b', project_id: 'project-b', source_asset_id: 'scene_001::shot_001' }),
    ]
    const mapped = mapContinuityIssuesToScene({
      issues,
      projectId: 'project-a',
      sceneId: 'scene_001',
      shotIds: ['shot_001'],
    })
    expect(mapped.projectIssues.map((issue) => issue.issue_id)).toEqual(['a'])
    expect(mapped.sceneIssues.map((issue) => issue.issue_id)).toEqual(['a'])
  })
})

import { describe, it, expect } from 'vitest'
import {
  buildAssetIntelligenceCard,
  buildPrevisIntelligenceSummary,
  buildScreeningIntelligenceSummary,
  buildCrewOpsDashboard,
  countCompleteAnalyses,
  countCompleteEmbeddingsForAsset,
  countMemoryRecordsForAsset,
  countContinuityForAsset,
  countStyleDriftForAsset,
  humanizeIntelligenceLoadError,
} from './intelligenceStatus'
import type { FrameAnalysis, ContinuityIssue, StyleDriftIssue } from './studioApi'

describe('intelligenceStatus helpers', () => {
  describe('countCompleteAnalyses', () => {
    it('counts only completed analyses', () => {
      const analyses = [
        { asset_id: 'a1', status: 'complete' } as FrameAnalysis,
        { asset_id: 'a1', status: 'in_progress' } as FrameAnalysis,
        { asset_id: 'a1', status: 'COMPLETE' } as FrameAnalysis,
      ]
      expect(countCompleteAnalyses(analyses)).toBe(2)
    })

    it('returns 0 for empty list', () => {
      expect(countCompleteAnalyses([])).toBe(0)
    })
  })

  describe('countCompleteEmbeddingsForAsset', () => {
    it('counts complete embeddings for specific asset', () => {
      const embeddings = [
        { asset_id: 'a1', status: 'complete' },
        { asset_id: 'a1', status: 'complete' },
        { asset_id: 'a2', status: 'complete' },
        { asset_id: 'a1', status: 'pending' },
      ]
      expect(countCompleteEmbeddingsForAsset(embeddings, 'a1')).toBe(2)
    })
  })

  describe('countMemoryRecordsForAsset', () => {
    it('counts memory records for specific asset', () => {
      const records = [
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { asset_id: 'a1' } as any,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { asset_id: 'a1' } as any,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { asset_id: 'a2' } as any,
      ]
      expect(countMemoryRecordsForAsset(records, 'a1')).toBe(2)
    })
  })

  describe('countContinuityForAsset', () => {
    it('counts continuity issues touching asset', () => {
      const issues: ContinuityIssue[] = [
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { issue_id: '1', issue_type: 'visual_drift', asset_id: 'a1', severity: 'high' } as any,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { issue_id: '2', issue_type: 'lighting_mismatch', source_asset_id: 'a1', severity: 'medium' } as any,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { issue_id: '3', issue_type: 'mood_shift', compared_asset_id: 'a3', severity: 'low' } as any,
      ]
      expect(countContinuityForAsset(issues, 'a1')).toBe(2)
    })
  })

  describe('countStyleDriftForAsset', () => {
    it('counts style drift issues for asset', () => {
      const issues: StyleDriftIssue[] = [
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { id: '1', asset_id: 'a1', drift_type: 'lighting' } as any,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { id: '2', asset_id: 'a1', drift_type: 'color' } as any,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { id: '3', asset_id: 'a2', drift_type: 'lighting' } as any,
      ]
      expect(countStyleDriftForAsset(issues, 'a1')).toBe(2)
    })
  })

  describe('buildAssetIntelligenceCard', () => {
    it('shows no upload state when all counts are zero', () => {
      const card = buildAssetIntelligenceCard({
        keyframeCount: 0,
        analyses: [],
        embeddingsCompleteCount: 0,
        memoryRecordCount: 0,
        continuityIssueCount: 0,
        styleDriftCount: 0,
        projectHasDirectorSignature: false,
      })
      expect(card.rows[1].state).toBe('Needs keyframes')
      expect(card.nextAction).toContain('Extract keyframes')
    })

    it('shows keyframes ready but needs analysis', () => {
      const card = buildAssetIntelligenceCard({
        keyframeCount: 5,
        analyses: [] as FrameAnalysis[],
        embeddingsCompleteCount: 0,
        memoryRecordCount: 0,
        continuityIssueCount: 0,
        styleDriftCount: 0,
        projectHasDirectorSignature: false,
      })
      expect(card.rows[1].state).toBe('Ready')
      expect(card.rows[2].state).toBe('Needs frame analysis')
      expect(card.nextAction).toContain('Run frame analysis')
    })

    it('shows analysis ready but needs embeddings', () => {
      const analyses = [{ asset_id: 'a1', status: 'complete' } as FrameAnalysis]
      const card = buildAssetIntelligenceCard({
        keyframeCount: 5,
        analyses,
        embeddingsCompleteCount: 0,
        memoryRecordCount: 0,
        continuityIssueCount: 0,
        styleDriftCount: 0,
        projectHasDirectorSignature: false,
      })
      expect(card.rows[2].state).toBe('Ready')
      expect(card.rows[3].state).toBe('Needs embeddings')
      expect(card.nextAction).toContain('Generate visual embeddings')
    })

    it('shows embeddings ready but needs memory', () => {
      const analyses = [{ asset_id: 'a1', status: 'complete' } as FrameAnalysis]
      const card = buildAssetIntelligenceCard({
        keyframeCount: 5,
        analyses,
        embeddingsCompleteCount: 3,
        memoryRecordCount: 0,
        continuityIssueCount: 0,
        styleDriftCount: 0,
        projectHasDirectorSignature: false,
      })
      expect(card.rows[3].state).toBe('Ready')
      expect(card.rows[4].state).toBe('Needs memory build')
      expect(card.nextAction).toContain('Build cinematic memory')
    })

    it('shows all ready state', () => {
      const analyses = Array.from({ length: 5 }, () =>
        ({ asset_id: 'a1', status: 'complete' } as FrameAnalysis),
      )
      const card = buildAssetIntelligenceCard({
        keyframeCount: 5,
        analyses,
        embeddingsCompleteCount: 5,
        memoryRecordCount: 5,
        continuityIssueCount: 0,
        styleDriftCount: 0,
        projectHasDirectorSignature: true,
      })
      expect(card.rows.every((r) => r.state === 'Ready')).toBe(true)
      expect(card.nextAction).toContain('ready for memory search')
    })

    it('shows style drift insufficient data with only 3 analyses', () => {
      const analyses = Array.from({ length: 3 }, () =>
        ({ asset_id: 'a1', status: 'complete' } as FrameAnalysis),
      )
      const card = buildAssetIntelligenceCard({
        keyframeCount: 3,
        analyses,
        embeddingsCompleteCount: 3,
        memoryRecordCount: 3,
        continuityIssueCount: 0,
        styleDriftCount: 0,
        projectHasDirectorSignature: true,
      })
      const styleDriftRow = card.rows.find((r) => r.label === 'Style Drift')!
      expect(styleDriftRow.state).toBe('Not enough evidence yet')
      expect(card.nextAction).toContain('Need at least 5 analyzed frames')
    })

    it('shows continuity issues count', () => {
      const card = buildAssetIntelligenceCard({
        keyframeCount: 5,
        analyses: [],
        embeddingsCompleteCount: 0,
        memoryRecordCount: 0,
        continuityIssueCount: 3,
        styleDriftCount: 0,
        projectHasDirectorSignature: false,
      })
      const continuityRow = card.rows.find((r) => r.label === 'Continuity Notes')!
      expect(continuityRow.count).toBe(3)
    })
  })

  describe('buildPrevisIntelligenceSummary', () => {
    it('shows no source when no match', () => {
      const summary = buildPrevisIntelligenceSummary({
        sceneId: 's1',
        relatedMemoryCount: 0,
        sceneContinuityIssueCount: 0,
        projectHasDirectorSignature: false,
        completeAnalysisCount: 0,
        sceneStyleDriftCount: 0,
      })
      expect(summary.matchedVisualSource).toBeNull()
      expect(summary.nextAction).toContain('Build director signature')
    })

    it('shows matched source when provided', () => {
      const summary = buildPrevisIntelligenceSummary({
        sceneId: 's1',
        matchedSourceName: 'Blade Runner 2049 - Scene 3',
        relatedMemoryCount: 1,
        sceneContinuityIssueCount: 0,
        projectHasDirectorSignature: true,
        completeAnalysisCount: 5,
        sceneStyleDriftCount: 0,
      })
      expect(summary.matchedVisualSource).toBe('Blade Runner 2049 - Scene 3')
      expect(summary.nextAction).toContain('Visual analysis ready')
    })

    it('warns about continuity and style drift', () => {
      const summary = buildPrevisIntelligenceSummary({
        sceneId: 's1',
        relatedMemoryCount: 1,
        sceneContinuityIssueCount: 2,
        projectHasDirectorSignature: true,
        completeAnalysisCount: 5,
        sceneStyleDriftCount: 1,
      })
      expect(summary.continuityWarningsCount).toBe(2)
      expect(summary.styleDriftWarningsCount).toBe(1)
      expect(summary.nextAction).toContain('Review continuity warnings')
    })

    it('shows director signature alignment status', () => {
      const aligned = buildPrevisIntelligenceSummary({
        sceneId: 's1',
        relatedMemoryCount: 0,
        sceneContinuityIssueCount: 0,
        projectHasDirectorSignature: true,
        completeAnalysisCount: 5,
        sceneStyleDriftCount: 0,
      })
      expect(aligned.directorSignatureAlignment).toBe('aligned')

      const unknown = buildPrevisIntelligenceSummary({
        sceneId: 's1',
        relatedMemoryCount: 0,
        sceneContinuityIssueCount: 0,
        projectHasDirectorSignature: false,
        completeAnalysisCount: 3,
        sceneStyleDriftCount: 0,
      })
      expect(unknown.directorSignatureAlignment).toBe('unknown')

      const needsData = buildPrevisIntelligenceSummary({
        sceneId: 's1',
        relatedMemoryCount: 0,
        sceneContinuityIssueCount: 0,
        projectHasDirectorSignature: false,
        completeAnalysisCount: 1,
        sceneStyleDriftCount: 0,
      })
      expect(needsData.directorSignatureAlignment).toBe('needs_more_data')
    })
  })

  describe('buildScreeningIntelligenceSummary', () => {
    it('shows ready state when no warnings', () => {
      const summary = buildScreeningIntelligenceSummary({
        sceneId: 's1',
        sceneContinuityIssueCount: 0,
        sceneStyleDriftCount: 0,
        relatedMemoryCount: 1,
        isPackaged: true,
      })
      expect(summary.reviewState).toBe('ready')
      expect(summary.advisories.length).toBe(0)
    })

    it('shows warnings when issues present', () => {
      const summary = buildScreeningIntelligenceSummary({
        sceneId: 's1',
        sceneContinuityIssueCount: 2,
        sceneStyleDriftCount: 1,
        relatedMemoryCount: 0,
        isPackaged: false,
      })
      expect(summary.reviewState).toBe('has_warnings')
      expect(summary.advisories.length).toBe(2)
      expect(summary.advisories[0]).toContain('2 continuity warning')
      expect(summary.advisories[1]).toContain('1 style drift warning')
      expect(summary.packageState).toBe('not_packaged')
    })
  })

  describe('buildCrewOpsDashboard', () => {
    it('shows needs_work when no data', () => {
      const dashboard = buildCrewOpsDashboard({
        assetCount: 0,
        totalKeyframes: 0,
        completedAnalysesCount: 0,
        totalEmbeddings: 0,
        memoryRecordCount: 0,
        continuityIssueCount: 0,
        styleDriftIssueCount: 0,
        hasDirectorSignature: false,
      })
      expect(dashboard.overallReadiness).toBe('needs_work')
    })

    it('shows in_progress when keyframes/analyses exist', () => {
      const dashboard = buildCrewOpsDashboard({
        assetCount: 1,
        totalKeyframes: 5,
        completedAnalysesCount: 3,
        totalEmbeddings: 0,
        memoryRecordCount: 0,
        continuityIssueCount: 0,
        styleDriftIssueCount: 0,
        hasDirectorSignature: false,
      })
      expect(dashboard.overallReadiness).toBe('in_progress')
    })

    it('shows ready when embeddings and memory exist', () => {
      const dashboard = buildCrewOpsDashboard({
        assetCount: 2,
        totalKeyframes: 10,
        completedAnalysesCount: 10,
        totalEmbeddings: 10,
        memoryRecordCount: 10,
        continuityIssueCount: 0,
        styleDriftIssueCount: 0,
        hasDirectorSignature: true,
        directorSignatureConfidence: 0.85,
      })
      expect(dashboard.overallReadiness).toBe('ready')
      expect(dashboard.directorSignatureConfidence).toBe(0.85)
    })
  })

  describe('humanizeIntelligenceLoadError', () => {
    it('converts 404 errors', () => {
      expect(humanizeIntelligenceLoadError('404 Not Found')).toContain('not available')
    })

    it('converts generic errors', () => {
      expect(humanizeIntelligenceLoadError('Connection refused')).toContain('could not be loaded')
    })
  })
})

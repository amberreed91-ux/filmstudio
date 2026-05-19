import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { buildScreeningIntelligenceSummary } from '../lib/intelligenceStatus'

type ScreeningIntelligencePanelProps = {
  sceneId: string
  sceneContinuityIssueCount: number
  sceneStyleDriftCount: number
  relatedMemoryCount: number
  isPackaged: boolean
}

export default function ScreeningIntelligencePanel({
  sceneId,
  sceneContinuityIssueCount,
  sceneStyleDriftCount,
  relatedMemoryCount,
  isPackaged,
}: ScreeningIntelligencePanelProps) {
  const summary = buildScreeningIntelligenceSummary({
    sceneId,
    sceneContinuityIssueCount,
    sceneStyleDriftCount,
    relatedMemoryCount,
    isPackaged,
  })

  return (
    <div className="bg-zinc-800/30 border border-zinc-700/50 rounded-lg p-3 space-y-2" data-testid="screening-intelligence-panel">
      {/* Status */}
      <div className="flex items-center gap-2">
        {summary.reviewState === 'ready' ? (
          <>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-semibold text-emerald-300">Ready for review</span>
          </>
        ) : (
          <>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-semibold text-amber-300">Review advisories below</span>
          </>
        )}
      </div>

      {/* Advisories */}
      {summary.advisories.length > 0 && (
        <div className="space-y-1 pt-1">
          {summary.advisories.map((advisory, idx) => (
            <div key={idx} className="flex items-start gap-2 text-xs text-amber-300">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{advisory}</span>
            </div>
          ))}
        </div>
      )}

      {/* Related Memory */}
      {summary.relatedMemoryReferencesCount > 0 && (
        <div className="flex items-center gap-2 text-xs text-blue-300 pt-1">
          <Info className="w-3 h-3 flex-shrink-0" />
          <span>{summary.relatedMemoryReferencesCount} related reference(s)</span>
        </div>
      )}

      {/* Package State */}
      {summary.packageState === 'ready' && (
        <div className="text-xs text-emerald-300 pt-1">✓ Scene packaged and ready</div>
      )}
    </div>
  )
}

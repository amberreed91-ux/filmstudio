import { AlertTriangle, CheckCircle2, Lightbulb } from 'lucide-react'
import { buildPrevisIntelligenceSummary } from '../lib/intelligenceStatus'

type PrevisIntelligencePanelProps = {
  sceneId: string
  matchedSourceName?: string
  relatedMemoryCount: number
  sceneContinuityIssueCount: number
  projectHasDirectorSignature: boolean
  completeAnalysisCount: number
  sceneStyleDriftCount: number
}

export default function PrevisIntelligencePanel({
  sceneId,
  matchedSourceName,
  relatedMemoryCount,
  sceneContinuityIssueCount,
  projectHasDirectorSignature,
  completeAnalysisCount,
  sceneStyleDriftCount,
}: PrevisIntelligencePanelProps) {
  const summary = buildPrevisIntelligenceSummary({
    sceneId,
    matchedSourceName,
    relatedMemoryCount,
    sceneContinuityIssueCount,
    projectHasDirectorSignature,
    completeAnalysisCount,
    sceneStyleDriftCount,
  })

  return (
    <div className="bg-zinc-800/30 border border-zinc-700/50 rounded-lg p-4 space-y-3" data-testid="previs-intelligence-panel">
      {/* Title */}
      <div className="flex items-center gap-2">
        <Lightbulb className="w-4 h-4 text-cyan-400" />
        <h3 className="text-sm font-semibold text-zinc-100">Visual Analysis</h3>
      </div>

      {/* Matched Source */}
      {summary.matchedVisualSource && (
        <div className="px-3 py-2 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-300">
          <div className="font-semibold">Source Material</div>
          <div className="mt-1">{summary.matchedVisualSource}</div>
        </div>
      )}

      {/* Related References */}
      {summary.relatedReferencesCount > 0 && (
        <div className="px-3 py-2 bg-blue-500/10 border border-blue-500/30 rounded text-xs text-blue-300">
          <div className="font-semibold">{summary.relatedReferencesCount} Related Reference(s)</div>
          <div className="text-xs text-blue-200 mt-1">From cinematic memory</div>
        </div>
      )}

      {/* Warnings */}
      {(summary.continuityWarningsCount > 0 || summary.styleDriftWarningsCount > 0) && (
        <div className="space-y-1">
          {summary.continuityWarningsCount > 0 && (
            <div className="flex items-start gap-2 px-3 py-2 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <div>
                <div className="font-semibold">{summary.continuityWarningsCount} Continuity Warning(s)</div>
                <div className="text-amber-200 text-xs mt-1">Review before moving forward</div>
              </div>
            </div>
          )}
          {summary.styleDriftWarningsCount > 0 && (
            <div className="flex items-start gap-2 px-3 py-2 bg-rose-500/10 border border-rose-500/30 rounded text-xs text-rose-300">
              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <div>
                <div className="font-semibold">{summary.styleDriftWarningsCount} Style Drift Warning(s)</div>
                <div className="text-rose-200 text-xs mt-1">Scene may deviate from director signature</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Director Signature Alignment */}
      <div className="px-3 py-2 bg-zinc-900/50 border border-zinc-700/30 rounded text-xs">
        <div className="flex items-center gap-2">
          {summary.directorSignatureAlignment === 'aligned' && (
            <>
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              <span className="text-emerald-300">Director signature aligned</span>
            </>
          )}
          {summary.directorSignatureAlignment === 'unknown' && (
            <>
              <AlertTriangle className="w-3 h-3 text-amber-400" />
              <span className="text-amber-300">Signature needs more data</span>
            </>
          )}
          {summary.directorSignatureAlignment === 'needs_more_data' && (
            <>
              <AlertTriangle className="w-3 h-3 text-amber-400" />
              <span className="text-amber-300">Build director signature first</span>
            </>
          )}
        </div>
      </div>

      {/* Next Action */}
      <div className="pt-2 border-t border-zinc-700/30">
        <p className="text-xs text-zinc-400 leading-relaxed">{summary.nextAction}</p>
      </div>
    </div>
  )
}

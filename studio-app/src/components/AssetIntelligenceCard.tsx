import { CheckCircle2, AlertCircle, Clock } from 'lucide-react'
import type { FrameAnalysis } from '../lib/studioApi'
import { buildAssetIntelligenceCard, type IntelligencePipelineState } from '../lib/intelligenceStatus'

type AssetIntelligenceCardProps = {
  assetId: string
  assetName: string
  keyframeCount: number
  analyses: FrameAnalysis[]
  embeddingsCompleteCount: number
  memoryRecordCount: number
  continuityIssueCount: number
  styleDriftCount: number
  projectHasDirectorSignature: boolean
  onActionClick?: (action: string) => void
}

function stateIcon(state: IntelligencePipelineState): React.ReactNode {
  if (state === 'Ready') {
    return <CheckCircle2 className="w-4 h-4 text-emerald-400" />
  }
  if (state === 'Not enough evidence yet') {
    return <Clock className="w-4 h-4 text-amber-400" />
  }
  return <AlertCircle className="w-4 h-4 text-amber-300" />
}

function stateColor(state: IntelligencePipelineState): string {
  if (state === 'Ready') return 'text-emerald-300'
  if (state === 'Not enough evidence yet') return 'text-amber-300'
  return 'text-orange-300'
}

export default function AssetIntelligenceCard({
  assetId,
  assetName,
  keyframeCount,
  analyses,
  embeddingsCompleteCount,
  memoryRecordCount,
  continuityIssueCount,
  styleDriftCount,
  projectHasDirectorSignature,
  onActionClick,
}: AssetIntelligenceCardProps) {
  const card = buildAssetIntelligenceCard({
    keyframeCount,
    analyses,
    embeddingsCompleteCount,
    memoryRecordCount,
    continuityIssueCount,
    styleDriftCount,
    projectHasDirectorSignature,
  })

  return (
    <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4 space-y-3" data-testid={`asset-intelligence-${assetId}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">{assetName}</h3>
          <p className="text-xs text-zinc-400 mt-1">Intelligence Status</p>
        </div>
      </div>

      {/* Status Rows */}
      <div className="space-y-2">
        {card.rows.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between px-2 py-1.5 bg-zinc-900/50 rounded border border-zinc-700/30"
          >
            <div className="flex items-center gap-2 flex-1 min-w-0">
              {stateIcon(row.state)}
              <span className="text-xs text-zinc-300 truncate">{row.label}</span>
            </div>
            <div className="flex items-center gap-2 ml-2">
              <span className={`text-xs font-semibold ${stateColor(row.state)}`}>{row.count}</span>
              <span className={`text-xs ${stateColor(row.state)}`}>{row.state}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Next Action */}
      <div className="pt-2 border-t border-zinc-700/30">
        <p className="text-xs text-zinc-400 leading-relaxed">{card.nextAction}</p>
      </div>

      {/* Action Button */}
      {onActionClick && (
        <button type="button"
          onClick={() => onActionClick(assetId)}
          className="w-full px-3 py-2 text-xs font-medium bg-blue-600/20 border border-blue-500/40 rounded text-blue-300 hover:bg-blue-600/30 hover:border-blue-500/60 transition-colors"
        >
          View Details
        </button>
      )}
    </div>
  )
}

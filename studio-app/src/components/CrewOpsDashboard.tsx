import { Activity, BarChart3, CheckCircle2, AlertCircle } from 'lucide-react'
import { buildCrewOpsDashboard, type CrewOpsDashboard } from '../lib/intelligenceStatus'

type CrewOpsDashboardProps = {
  assetCount: number
  totalKeyframes: number
  completedAnalysesCount: number
  totalEmbeddings: number
  memoryRecordCount: number
  continuityIssueCount: number
  styleDriftIssueCount: number
  hasDirectorSignature: boolean
  directorSignatureConfidence?: number
}

type StatItemProps = {
  label: string
  value: number | boolean | string
  unit?: string
  color?: 'emerald' | 'blue' | 'amber' | 'zinc'
}

function StatItem({ label, value, unit, color = 'zinc' }: StatItemProps) {
  const colorClasses = {
    emerald: 'text-emerald-300',
    blue: 'text-blue-300',
    amber: 'text-amber-300',
    zinc: 'text-zinc-300',
  }

  return (
    <div className="flex items-center justify-between px-3 py-2 bg-zinc-900/50 rounded border border-zinc-700/30">
      <span className="text-xs text-zinc-400">{label}</span>
      <div className={`text-sm font-semibold ${colorClasses[color]}`}>
        {typeof value === 'boolean' ? value ? '✓ Yes' : '✗ No' : `${value}${unit || ''}`}
      </div>
    </div>
  )
}

export default function CrewOpsDashboard({
  assetCount,
  totalKeyframes,
  completedAnalysesCount,
  totalEmbeddings,
  memoryRecordCount,
  continuityIssueCount,
  styleDriftIssueCount,
  hasDirectorSignature,
  directorSignatureConfidence = 0,
}: CrewOpsDashboardProps) {
  const dashboard = buildCrewOpsDashboard({
    assetCount,
    totalKeyframes,
    completedAnalysesCount,
    totalEmbeddings,
    memoryRecordCount,
    continuityIssueCount,
    styleDriftIssueCount,
    hasDirectorSignature,
    directorSignatureConfidence,
  })

  // Status color is displayed via icon, not via readinessColor variable

  return (
    <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4 space-y-4" data-testid="crew-ops-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-zinc-100">Studio Intelligence Status</h3>
        </div>
        <div className="flex items-center gap-2">
          {dashboard.overallReadiness === 'ready' && (
            <>
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold text-emerald-300">Ready</span>
            </>
          )}
          {dashboard.overallReadiness === 'in_progress' && (
            <>
              <Activity className="w-4 h-4 text-blue-400" />
              <span className="text-xs font-semibold text-blue-300">In Progress</span>
            </>
          )}
          {dashboard.overallReadiness === 'needs_work' && (
            <>
              <AlertCircle className="w-4 h-4 text-amber-400" />
              <span className="text-xs font-semibold text-amber-300">Needs Work</span>
            </>
          )}
        </div>
      </div>

      {/* Visual Evidence Section */}
      <div className="space-y-2">
        <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">Visual Evidence</div>
        <div className="space-y-2">
          <StatItem
            label="Uploaded Assets"
            value={dashboard.uploadedAssetCount}
            color={dashboard.uploadedAssetCount > 0 ? 'emerald' : 'zinc'}
          />
          <StatItem
            label="Keyframes Extracted"
            value={dashboard.totalKeyframesExtracted}
            color={dashboard.totalKeyframesExtracted > 0 ? 'emerald' : 'zinc'}
          />
          <StatItem
            label="Frame Analyses Completed"
            value={dashboard.totalAnalysesCompleted}
            color={dashboard.totalAnalysesCompleted > 0 ? 'emerald' : 'zinc'}
          />
        </div>
      </div>

      {/* Semantic Memory Section */}
      <div className="space-y-2">
        <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">Semantic Memory</div>
        <div className="space-y-2">
          <StatItem
            label="Visual Embeddings"
            value={dashboard.totalEmbeddingsGenerated}
            color={dashboard.totalEmbeddingsGenerated > 0 ? 'blue' : 'zinc'}
          />
          <StatItem
            label="Memory Records"
            value={dashboard.totalMemoryRecords}
            color={dashboard.totalMemoryRecords > 0 ? 'blue' : 'zinc'}
          />
          <StatItem
            label="Director Signature"
            value={dashboard.directorSignatureExists}
            color={dashboard.directorSignatureExists ? 'emerald' : 'zinc'}
          />
        </div>
      </div>

      {/* Quality Control Section */}
      <div className="space-y-2">
        <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">Quality Control</div>
        <div className="space-y-2">
          <StatItem
            label="Continuity Issues"
            value={dashboard.projectContinuityIssueCount}
            color={dashboard.projectContinuityIssueCount === 0 ? 'emerald' : 'amber'}
          />
          <StatItem
            label="Style Drift Issues"
            value={dashboard.projectStyleDriftIssueCount}
            color={dashboard.projectStyleDriftIssueCount === 0 ? 'emerald' : 'amber'}
          />
        </div>
      </div>

      {/* Info Text */}
      <div className="pt-2 border-t border-zinc-700/30 text-xs text-zinc-400 leading-relaxed">
        <p>
          All counts are real project data. No simulated agents or fake progress. Use the Study Room to upload assets, extract keyframes, and
          build intelligence.
        </p>
      </div>
    </div>
  )
}

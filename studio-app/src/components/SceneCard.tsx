import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { CollapsibleSection } from './StudioShell'

type SceneCardProps = {
  sceneId: string
  state: string
  blocked: boolean
  selectedCut: string
  agentOwner: string
  description: string
  location: string
  emotionalTone: string
  hasHighConflict: boolean
  hasConflict: boolean
  blockers: string[]
  reviewStatus: string
  inCut: boolean
  audioStatus: string
  editCutMode: boolean
  duration: number
  renderStatus: {
    status: string
    label: string
    canRetry: boolean
  }
  isGenerating: boolean
  isMajorPlotPoint?: boolean
  thumbnailUrl?: string
  assetUrl?: string
  onMoveUp: () => void
  onMoveDown: () => void
  onToggleCut: () => void
  onOpen: () => void
  onDebate?: () => void
  onSetDuration: (duration: number) => void
  onGenerate: () => void
  onRetry: () => void
  onSimulateAudience?: () => void
}

function toneForState(state: string, blocked: boolean): string {
  if (blocked) return 'border-rose-400/60 bg-rose-500/15 text-rose-200'
  if (state === 'locked') return 'border-emerald-400/60 bg-emerald-500/15 text-emerald-200'
  if (state === 'review') return 'border-amber-400/60 bg-amber-500/15 text-amber-200'
  if (state === 'in_progress') return 'border-cyan-400/60 bg-cyan-500/15 text-cyan-200'
  return 'border-zinc-600/70 bg-zinc-800/60 text-zinc-300'
}

function isValidAssetUrl(url: string | undefined): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    // Accept http, https, and data URLs
    return ['http:', 'https:', 'data:'].includes(parsed.protocol)
  } catch {
    return false
  }
}

export default function SceneCard(props: SceneCardProps) {
  const needsAttention = props.blocked
  const hasValidThumbnail = isValidAssetUrl(props.thumbnailUrl)
  const hasValidAsset = isValidAssetUrl(props.assetUrl)
  const [thumbnailLoading, setThumbnailLoading] = useState(true)
  const [thumbnailError, setThumbnailError] = useState(false)

  return (
    <div
      className={`rounded-xl border px-4 py-3 transition-all duration-200 hover:scale-[1.01] overflow-hidden scene-frame ${
        needsAttention ? 'border-rose-400/45 bg-rose-500/10' : 'border-white/10 bg-black/35 hover:border-white/30'
      }`}
    >
      <div className="scene-frame-corner-marker top-left" />
      <div className="scene-frame-corner-marker top-right" />
      <div className="scene-frame-corner-marker bottom-left" />
      <div className="scene-frame-corner-marker bottom-right" />
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-zinc-100">{props.sceneId}</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.12em] text-zinc-400">{props.selectedCut}</div>
          <div className="mt-1 text-[11px] text-zinc-300">agent: {props.agentOwner}</div>
        </div>
        <div className="flex items-center gap-2">
          {needsAttention && (
            <span className="rounded-full border border-rose-400/60 bg-rose-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-rose-200">
              Needs Attention
            </span>
          )}
          {props.hasHighConflict && (
            <span className="rounded-full border border-orange-400/60 bg-orange-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-orange-200">
              🔥 High Conflict
            </span>
          )}
          {!props.hasHighConflict && props.hasConflict && (
            <span className="rounded-full border border-amber-400/60 bg-amber-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-200">
              ⚠ Needs Attention
            </span>
          )}
          {props.isMajorPlotPoint && (
            <span className="rounded-full border border-indigo-400/60 bg-indigo-500/15 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-indigo-200">
              ✦ Major Plot Point
            </span>
          )}
          <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${toneForState(props.state, props.blocked)}`}>
            {props.blocked ? 'blocked' : props.state}
          </span>
        </div>
      </div>

      {/* Description */}
      {props.description && (
        <div className="mt-2 text-[13px] leading-relaxed text-zinc-400">
          {props.description.length > 120 ? `${props.description.slice(0, 120)}…` : props.description}
        </div>
      )}
      {(props.location || props.emotionalTone) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {props.location && (
            <span className="rounded border border-cyan-400/30 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-cyan-200">
              {props.location}
            </span>
          )}
          {props.emotionalTone && (
            <span className="rounded border border-purple-400/30 bg-purple-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.1em] text-purple-200">
              {props.emotionalTone}
            </span>
          )}
        </div>
      )}

      {/* Stats Grid */}
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-white/10 bg-black/35 px-2 py-1.5">
          <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">State</div>
          <div className="font-semibold text-zinc-100">{props.state}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/35 px-2 py-1.5">
          <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Issues</div>
          <div className={`font-semibold ${props.blockers.length > 0 ? 'text-rose-200' : 'text-emerald-200'}`}>
            {props.blockers.length > 0 ? `${props.blockers.length} blocker${props.blockers.length !== 1 ? 's' : ''}` : 'None'}
          </div>
        </div>
      </div>

      {/* Blockers */}
      {props.blockers.length > 0 && (
        <div className="mt-3">
          <CollapsibleSection title="Blockers" defaultOpen={false}>
            <div className="rounded-lg border border-rose-400/30 bg-rose-500/8 px-2 py-2 text-xs text-rose-100">
              {props.blockers.slice(0, 3).map((blocker, index) => (
                <div key={`${props.sceneId}-blocker-${index}`}>- {blocker}</div>
              ))}
            </div>
          </CollapsibleSection>
        </div>
      )}

      {/* Status Info */}
      <div className="mt-3 space-y-1 text-[10px] uppercase tracking-[0.12em] text-zinc-400">
        <div>{props.reviewStatus}</div>
        <div>{props.inCut ? 'in cut' : 'excluded from cut'}</div>
        <div className="text-zinc-300">
          audio readiness: <span className={props.audioStatus === 'ready' ? 'text-emerald-300' : props.audioStatus === 'needs design' ? 'text-amber-300' : 'text-cyan-300'}>{props.audioStatus}</span>
        </div>
      </div>

      {/* Thumbnail/Asset Preview */}
      {(hasValidThumbnail || hasValidAsset) && (
        <div className="mt-3 space-y-2">
          <div className="relative overflow-hidden rounded-md border border-white/10 bg-black/35">
            {/* Loading Spinner */}
            {hasValidThumbnail && thumbnailLoading && !thumbnailError && (
              <div className="absolute inset-0 flex items-center justify-center aspect-widescreen clapperboard-placeholder bg-zinc-900/50">
                <Loader2 size={20} className="animate-spin text-cyan-400" />
              </div>
            )}
            
            {hasValidThumbnail ? (
              <img
                src={props.thumbnailUrl}
                alt={`${props.sceneId} render preview`}
                className="aspect-widescreen w-full object-cover"
                loading="lazy"
                onLoad={() => setThumbnailLoading(false)}
                onError={(e) => { 
                  setThumbnailLoading(false)
                  setThumbnailError(true)
                  (e.currentTarget as HTMLImageElement).style.display = 'none'
                  console.warn(`Thumbnail failed to load for ${props.sceneId}:`, props.thumbnailUrl)
                }}
              />
            ) : hasValidAsset ? (
              <video
                src={props.assetUrl}
                className="aspect-widescreen w-full object-cover"
                controls
                preload="metadata"
                playsInline
                onError={(e) => {
                  console.warn(`Video failed to load for ${props.sceneId}:`, props.assetUrl)
                }}
              />
            ) : null}
          </div>
          {hasValidAsset && (
            <div className="text-[10px] text-zinc-400">
              <a 
                href={props.assetUrl} 
                target="_blank" 
                rel="noreferrer" 
                className="text-cyan-300 hover:text-cyan-200 break-all underline"
              >
                View full output →
              </a>
            </div>
          )}
        </div>
      )}

      {/* Edit Cut Actions */}
      {props.editCutMode && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button onClick={props.onMoveUp} className="rounded-md border border-zinc-500/45 bg-zinc-700/20 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200">
            Move Up
          </button>
          <button onClick={props.onMoveDown} className="rounded-md border border-zinc-500/45 bg-zinc-700/20 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200">
            Move Down
          </button>
          <button
            onClick={props.onToggleCut}
            className={`rounded-md border px-2 py-1 text-[10px] uppercase tracking-[0.12em] ${
              props.inCut ? 'border-rose-400/50 bg-rose-500/12 text-rose-100' : 'border-emerald-400/50 bg-emerald-500/12 text-emerald-100'
            }`}
          >
            {props.inCut ? 'Exclude' : 'Include'}
          </button>
        </div>
      )}

      {/* Open Scene Button */}
      <div className="flex gap-2">
        <button onClick={props.onOpen} className="mt-2 rounded-lg border border-cyan-300/40 bg-cyan-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-100">
          Open Scene
        </button>
        {props.onDebate && (
          <button
            onClick={props.onDebate}
            className="mt-2 rounded-lg border border-indigo-400/40 bg-indigo-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-indigo-100"
            title="Debate this decision"
          >
            Debate
          </button>
        )}
        {props.onSimulateAudience && (
          <button
            onClick={props.onSimulateAudience}
            className="mt-2 rounded-lg border border-purple-400/40 bg-purple-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-purple-100"
            title="Simulate Audience Reactions"
          >
            Simulate Audience
          </button>
        )}
      </div>

      {/* Render Controls */}
      <div className="mt-3 space-y-2">
        <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-400">Render Controls</div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:flex-wrap">
          <label className="text-[11px] text-zinc-300 sm:w-auto">Duration:</label>
          <select 
            value={props.duration} 
            onChange={(e) => props.onSetDuration(Number(e.target.value))} 
            aria-label={`Set render duration for ${props.sceneId}`}
            className="w-full sm:flex-1 sm:max-w-[120px] rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-[11px] text-zinc-100"
          >
            <option value={5}>5s</option>
            <option value={10}>10s (default)</option>
            <option value={15}>15s</option>
            <option value={20}>20s</option>
          </select>
        </div>

        {/* Status Badge */}
        {props.renderStatus.status !== 'not_started' && (
          <div
            className={`rounded-md border px-2 py-1.5 text-[11px] ${
              props.renderStatus.status === 'complete'
                ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200'
                : props.renderStatus.status === 'failed'
                  ? 'border-rose-400/40 bg-rose-500/10 text-rose-200'
                  : 'border-cyan-400/40 bg-cyan-500/10 text-cyan-200'
            }`}
          >
            {props.renderStatus.label}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {props.renderStatus.canRetry ? (
          <button onClick={props.onRetry} className="w-full sm:w-auto rounded-lg border border-amber-400/45 bg-amber-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-amber-100">
            Retry Render
          </button>
        ) : (props.renderStatus.status === 'not_started' || props.renderStatus.status === 'complete') && (
          <button
            onClick={props.onGenerate}
            disabled={props.isGenerating}
            className="w-full sm:w-auto rounded-lg border border-fuchsia-400/45 bg-fuchsia-500/12 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-fuchsia-100 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {props.isGenerating ? (
              <span className="flex items-center justify-center gap-1.5">
                <Loader2 size={11} className="animate-spin" /> 
                <span>Generating…</span>
              </span>
            ) : props.renderStatus.status === 'complete' ? 'Regenerate' : 'Generate'}
          </button>
        )}
        </div>
      </div>
    </div>
  )
}

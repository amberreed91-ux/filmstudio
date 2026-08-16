import { AlertTriangle, Eye, Layers, ScissorsLineDashed } from 'lucide-react'
import {
  buildShotSignalViews,
  shotSignalsAreQuiet,
  type ShotSignalKind,
  type ShotSignalsEnvelope,
} from '../lib/shotSignals'

/**
 * Shot Signals — what the pipeline noticed about one render.
 *
 * The backend has been recording intent fidelity, character identity, the
 * references that conditioned a render, and the exclusions sent with it. None
 * of it had a reader until now.
 *
 * Presentation follows AGENTS.md: no scores or percentages, and the panel draws
 * nothing at all when there is nothing to say. A row that always appears and
 * always reassures trains the eye to skip the panel, which is worse than an
 * empty one.
 */

type ShotSignalsPanelProps = {
  envelope: ShotSignalsEnvelope | null
}

const ICONS: Record<ShotSignalKind, typeof Eye> = {
  intent_fidelity: ScissorsLineDashed,
  character_identity: Eye,
  character_references: Layers,
  exclusions: ScissorsLineDashed,
}

export default function ShotSignalsPanel({ envelope }: ShotSignalsPanelProps) {
  if (shotSignalsAreQuiet(envelope)) return null

  const views = buildShotSignalViews(envelope)

  return (
    <div
      className="bg-zinc-800/30 border border-zinc-700/50 rounded-lg p-4 space-y-3"
      data-testid="shot-signals-panel"
    >
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-zinc-100">Shot Signals</h3>
        <span className="text-xs text-zinc-500">{envelope?.shot_id}</span>
      </div>

      {views.map((view) => {
        const Icon = ICONS[view.kind] ?? Eye
        return (
          <div
            key={view.kind}
            data-testid={`shot-signal-${view.kind}`}
            className={
              view.needsAttention
                ? 'px-3 py-2 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-200'
                : 'px-3 py-2 bg-zinc-900/40 border border-zinc-700/40 rounded text-xs text-zinc-400'
            }
          >
            <div className="flex items-center gap-2 font-semibold">
              {view.needsAttention ? (
                <AlertTriangle className="w-3.5 h-3.5" aria-hidden />
              ) : (
                <Icon className="w-3.5 h-3.5" aria-hidden />
              )}
              <span>{view.title}</span>
            </div>

            {view.note && <div className="mt-1 leading-relaxed">{view.note}</div>}

            {view.details.length > 0 && (
              <ul className="mt-2 space-y-0.5">
                {view.details.map((detail) => (
                  <li key={detail} className="text-zinc-400">
                    {/* Dropped phrases are the director's own words — quoting
                        them is what makes the note recognisable rather than
                        abstract. */}
                    {view.kind === 'intent_fidelity' ? `“${detail}”` : detail}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}

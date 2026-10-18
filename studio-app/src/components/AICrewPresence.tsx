import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, Loader2, Sparkles } from 'lucide-react'
import { useCrewPresence } from '../hooks/useCrewPresence'
import type { CrewPresenceRow } from '../lib/crewPresence'

const ROLE_TINTS: Record<string, string> = {
  director: '',
  cinematographer: 'liquid-avatar--violet',
  editor: 'liquid-avatar--cyan',
  story_analyst: 'liquid-avatar--emerald',
  continuity: 'liquid-avatar--cyan',
  archivist: 'liquid-avatar--rose',
}

function avatarClassFor(agent: CrewPresenceRow) {
  return ROLE_TINTS[agent.id] ? `liquid-avatar ${ROLE_TINTS[agent.id]}` : 'liquid-avatar'
}

export default function AICrewPresence({ compact = true, projectId }: { compact?: boolean; projectId?: string }) {
  const [expanded, setExpanded] = useState(false)
  const { agents, loading, error, refresh } = useCrewPresence(projectId)
  const activeCount = useMemo(() => agents.filter((agent) => agent.active).length, [agents])

  return (
    <aside
      aria-label="Creative crew status"
      className={`liquid-panel liquid-panel--amber relative ${compact ? 'mx-4 mb-6 mt-4 self-end' : 'mx-4 my-4'} w-80 max-w-[calc(100vw-32px)] overflow-hidden`}
    >
      <span aria-hidden="true" className="liquid-shimmer" />
      <span aria-hidden="true" className="liquid-edge" />
      <span aria-hidden="true" className="liquid-spec" />
      <span aria-hidden="true" className="liquid-glow" />

      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        aria-controls="studio-crew-members"
        className="relative z-10 flex min-h-11 w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.04]"
      >
        <span className="flex items-center gap-2.5">
          <span aria-hidden="true" className="liquid-avatar"><Sparkles size={13} /></span>
          <span className="flex flex-col">
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-200">Creative crew</span>
            <span className="mt-0.5 text-[10px] uppercase tracking-[0.1em] text-zinc-500">
              {activeCount > 0 ? `${activeCount} active · ${agents.length} total` : `${agents.length} on standby`}
            </span>
          </span>
        </span>
        <span className="flex items-center gap-2 text-zinc-500">
          <span className={`liquid-chip ${activeCount > 0 ? 'liquid-chip--amber' : ''}`}>{agents.some((agent) => agent.active) ? 'Activity' : 'Status'}</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {expanded && (
        <div id="studio-crew-members" className="relative z-10 space-y-3 border-t border-white/10 px-4 py-4">
          <p className="text-xs leading-relaxed text-zinc-400">Open the co-director whenever you want guidance. Your choices stay yours.</p>
          {loading && agents.length === 0 ? (
            <p role="status" className="flex items-center gap-2 text-xs text-zinc-400"><Loader2 size={13} className="animate-spin" />Checking crew status…</p>
          ) : error ? (
            <div role="status" className="space-y-2">
              <p className="text-xs leading-relaxed text-zinc-400">{error}</p>
              <button type="button" onClick={() => void refresh()} className="min-h-11 text-xs text-amber-200">Check again</button>
            </div>
          ) : agents.length === 0 ? (
            <p className="text-xs leading-relaxed text-zinc-500">{projectId ? 'No department activity has been reported.' : 'Open a film to see its crew status.'}</p>
          ) : (
            <ul className="space-y-2">
              {agents.map((agent) => (
                <li key={agent.id} className="liquid-crew-row">
                  <span aria-hidden="true" className={avatarClassFor(agent)}>{agent.initial}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-xs font-semibold text-zinc-200">{agent.name}</p>
                      <span className={`liquid-chip ${agent.active ? 'liquid-chip--emerald' : ''}`}>
                        <span aria-hidden="true" className={`inline-block size-1.5 rounded-full ${agent.active ? 'bg-emerald-300' : 'bg-zinc-500'}`} />
                        {agent.active ? 'Active' : 'Idle'}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-xs leading-relaxed text-zinc-400">{agent.activity}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </aside>
  )
}

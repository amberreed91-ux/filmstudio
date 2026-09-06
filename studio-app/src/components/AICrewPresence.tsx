import { useState } from 'react'
import { ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { useCrewPresence } from '../hooks/useCrewPresence'

export default function AICrewPresence({ compact = true, projectId }: { compact?: boolean; projectId?: string }) {
  const [expanded, setExpanded] = useState(false)
  const { agents, loading, error, refresh } = useCrewPresence(projectId)

  return (
    <aside aria-label="Creative crew status" className={`${compact ? 'mx-4 mb-6 mt-4 self-end' : 'mx-4 my-4'} w-72 max-w-[calc(100vw-32px)] rounded-lg border border-white/10 bg-zinc-950/60`}>
      <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} aria-controls="studio-crew-members" className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-3 text-left text-xs text-zinc-300 hover:text-zinc-100">
        <span>Creative crew</span><span className="flex items-center gap-2 text-zinc-500">{agents.some((agent) => agent.active) ? 'Activity' : 'Status'}{expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>
      </button>
      {expanded && <div id="studio-crew-members" className="space-y-3 border-t border-white/10 px-4 py-4">
        <p className="text-xs leading-relaxed text-zinc-400">Open the co-director whenever you want guidance. Your choices stay yours.</p>
        {loading && agents.length === 0 ? <p role="status" className="flex items-center gap-2 text-xs text-zinc-400"><Loader2 size={13} className="animate-spin" />Checking crew status…</p> : error ? <div role="status" className="space-y-2"><p className="text-xs leading-relaxed text-zinc-400">{error}</p><button type="button" onClick={() => void refresh()} className="min-h-11 text-xs text-amber-200">Check again</button></div> : agents.length === 0 ? <p className="text-xs leading-relaxed text-zinc-500">{projectId ? 'No department activity has been reported.' : 'Open a film to see its crew status.'}</p> : <ul className="divide-y divide-white/10">{agents.map((agent) => <li key={agent.id} className="flex items-start gap-3 py-3"><span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${agent.active ? 'bg-amber-200' : 'bg-zinc-600'}`} /><div className="min-w-0"><p className="text-xs font-medium text-zinc-200">{agent.name}</p><p className="mt-1 text-xs leading-relaxed text-zinc-400">{agent.activity}</p></div></li>)}</ul>}
      </div>}
    </aside>
  )
}

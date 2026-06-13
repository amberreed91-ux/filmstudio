import { useState } from 'react'
import { Type, Clapperboard, Camera, Film, Clipboard, MessageSquare, AlertTriangle, CheckCircle2, Save, X } from 'lucide-react'
import type { CoDirectorDebateEntry, AgentResponse } from '../types/directorMemory'
import { triggerDebate, debateAction } from '../lib/studioApi'

export interface DirectorDebatePanelProps {
  projectId: string
  debate: CoDirectorDebateEntry
  onUpdate?: (updated: CoDirectorDebateEntry) => void
  onDismiss?: () => void
}

const AGENT_ICONS: Record<string, any> = {
  'Writer Agent': Type,
  'Director Agent': Clapperboard,
  'Cinematographer Agent': Camera,
  'Editor Agent': Film,
  'Producer Agent': Clipboard,
}

export default function DirectorDebatePanel({
  projectId,
  debate: initialDebate,
  onUpdate,
  onDismiss,
}: DirectorDebatePanelProps) {
  const [debate, setDebate] = useState<CoDirectorDebateEntry>(initialDebate)
  const [loading, setLoading] = useState(false)

  const handleAction = async (action: 'dismiss' | 'save') => {
    try {
      setLoading(true)
      const { debate: updated } = await debateAction({
        project_id: projectId,
        debate_id: debate.debate_id,
        action,
      })
      setDebate(updated)
      if (onUpdate) onUpdate(updated)
      if (action === 'dismiss' && onDismiss) onDismiss()
    } catch (err) {
      console.error('Failed to perform debate action:', err)
    } finally {
      setLoading(false)
    }
  }

  if (debate.is_dismissed) return null

  return (
    <div className="director-debate-container fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-md p-6">
      <div className="relative w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col rounded-xl border border-white/10 bg-zinc-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/5 bg-zinc-950/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-400">
              <MessageSquare size={18} />
            </div>
            <div>
              <h2 className="text-sm font-bold uppercase tracking-widest text-white">Co-Director Debate</h2>
              <p className="text-xs text-zinc-400 italic">"{debate.query}"</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {!debate.is_saved && (
              <button
                onClick={() => handleAction('save')}
                disabled={loading}
                className="flex items-center gap-2 text-xs font-medium text-zinc-400 hover:text-white transition-colors"
              >
                <Save size={14} />
                Save to Notes
              </button>
            )}
            <button
              onClick={() => handleAction('dismiss')}
              className="text-zinc-500 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Agent Grid */}
        <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-white/10">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            {debate.agent_responses.map((agent) => (
              <AgentCard key={agent.agent_name} agent={agent} />
            ))}
          </div>

          {/* Summary Section */}
          <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="rounded-lg bg-emerald-500/5 border border-emerald-500/10 p-4">
              <div className="flex items-center gap-2 text-emerald-400 mb-3">
                <CheckCircle2 size={16} />
                <span className="text-xs font-bold uppercase tracking-wider">Points of Agreement</span>
              </div>
              <ul className="space-y-2">
                {debate.points_of_agreement.map((point, i) => (
                  <li key={i} className="text-sm text-zinc-300 pl-4 relative before:absolute before:left-0 before:top-2 before:h-1 before:w-1 before:rounded-full before:bg-emerald-500/40">
                    {point}
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-lg bg-amber-500/5 border border-amber-500/10 p-4">
              <div className="flex items-center gap-2 text-amber-400 mb-3">
                <AlertTriangle size={16} />
                <span className="text-xs font-bold uppercase tracking-wider">Points of Conflict</span>
              </div>
              <ul className="space-y-2">
                {debate.points_of_conflict.map((point, i) => (
                  <li key={i} className="text-sm text-zinc-300 pl-4 relative before:absolute before:left-0 before:top-2 before:h-1 before:w-1 before:rounded-full before:bg-amber-500/40">
                    {point}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Synthesis */}
          <div className="mt-8 rounded-lg bg-indigo-500/5 border border-indigo-500/10 p-6">
            <div className="flex items-center gap-2 text-indigo-400 mb-4">
              <div className="h-1 w-8 bg-indigo-500" />
              <span className="text-xs font-bold uppercase tracking-widest">Co-Director Synthesis</span>
            </div>
            <p className="text-lg font-medium leading-relaxed text-zinc-200 font-serif">
              {debate.synthesis}
            </p>
            <div className="mt-6 flex justify-end">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-indigo-400/60">
                {debate.filmmaker_prerogative}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function AgentCard({ agent }: { agent: AgentResponse }) {
  const Icon = AGENT_ICONS[agent.agent_name] || MessageSquare

  return (
    <div className="flex flex-col rounded-lg bg-zinc-800/50 border border-white/5 p-4 transition-all hover:border-white/10 hover:bg-zinc-800">
      <div className="flex items-center gap-2 mb-3">
        <div className="flex h-6 w-6 items-center justify-center rounded bg-zinc-700 text-zinc-300">
          <Icon size={14} />
        </div>
        <div>
          <h3 className="text-[10px] font-bold text-white uppercase tracking-wider">{agent.agent_name}</h3>
          <p className="text-[9px] text-zinc-500 leading-tight">{agent.perspective}</p>
        </div>
      </div>
      
      <div className="space-y-3 flex-1">
        <div>
          <div className="text-[8px] uppercase font-bold text-indigo-400/80 mb-1">Position</div>
          <p className="text-xs font-medium text-zinc-200">{agent.position}</p>
        </div>
        
        <div>
          <div className="text-[8px] uppercase font-bold text-zinc-500 mb-1">Reasoning</div>
          <p className="text-[11px] leading-relaxed text-zinc-400">{agent.reasoning}</p>
        </div>

        <div className="pt-2 mt-auto border-t border-white/5">
          <div className="text-[8px] uppercase font-bold text-emerald-500/80 mb-1">Recommendation</div>
          <p className="text-xs text-zinc-300 italic">"{agent.recommendation}"</p>
        </div>
      </div>
    </div>
  )
}

import React, { useState } from 'react'
import type { SceneAudienceSimulation } from '../types/audienceSimulator'
import { saveToDirectorsNotes } from '../lib/studioApi'
import { Loader2, Save, MessageSquare, AlertTriangle, Lightbulb } from 'lucide-react'

interface AudienceSimulatorCardProps {
  projectId: string
  simulation: SceneAudienceSimulation
  onSaveSuccess?: () => void
}

export const AudienceSimulatorCard: React.FC<AudienceSimulatorCardProps> = ({
  projectId,
  simulation,
  onSaveSuccess
}) => {
  const [isSaving, setIsSaving] = useState(false)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle')

  const handleSave = async () => {
    setIsSaving(true)
    try {
      const noteContent = `
Interpretation Variance: ${simulation.interpretation_variance}

Co-Director Note: ${simulation.co_director_note}

${simulation.audience_reactions.map(r => `[${r.audience_type}]\nReaction: ${r.likely_reaction}\nReasoning: ${r.reasoning}\nWatch out: ${r.watch_out}`).join('\n\n')}
`.trim()
      
      await saveToDirectorsNotes(projectId, `Audience Simulation: ${simulation.scene_id}`, noteContent)
      setSaveStatus('success')
      onSaveSuccess?.()
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch (err) {
      console.error('Failed to save to Director\'s Notes:', err)
      setSaveStatus('error')
    } finally {
      setIsSaving(false)
    }
  }

  const getAudienceColor = (type: string) => {
    switch (type) {
      case 'Casual audience': return 'text-cyan-400'
      case 'Cinephiles': return 'text-purple-400'
      case 'Genre fans': return 'text-amber-400'
      case 'Festival juries': return 'text-indigo-400'
      default: return 'text-zinc-400'
    }
  }

  const getAudienceIcon = (type: string) => {
    switch (type) {
      case 'Casual audience': return <MessageSquare size={14} />
      case 'Cinephiles': return <Lightbulb size={14} />
      case 'Genre fans': return <AlertTriangle size={14} />
      case 'Festival juries': return <AlertTriangle size={14} />
      default: return null
    }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-black/45 p-5 shadow-xl backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-white/5 pb-4">
        <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-100">
          Emotional Audience Simulation
        </h3>
        <button type="button"
          onClick={handleSave}
          disabled={isSaving || saveStatus === 'success'}
          aria-busy={isSaving}
          className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider transition-all ${
            saveStatus === 'success'
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-white/10'
          }`}
        >
          {isSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {saveStatus === 'success' ? 'Saved' : 'Save to Director\'s Notes'}
        </button>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        {simulation.audience_reactions.map((reaction, idx) => (
          <div key={idx} className="rounded-lg border border-white/5 bg-zinc-900/30 p-4 transition-colors hover:border-white/10">
            <div className={`flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest ${getAudienceColor(reaction.audience_type)}`}>
              {getAudienceIcon(reaction.audience_type)}
              {reaction.audience_type}
            </div>
            <p className="mt-2 text-sm font-medium text-zinc-200">"{reaction.likely_reaction}"</p>
            <p className="mt-2 text-[12px] leading-relaxed text-zinc-400">
              <span className="font-semibold text-zinc-300">Reasoning:</span> {reaction.reasoning}
            </p>
            <div className="mt-3 rounded border border-amber-900/30 bg-amber-950/20 px-2 py-2 text-xs text-amber-200/80">
              <span className="font-bold uppercase tracking-tighter">Watch out:</span> {reaction.watch_out}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 space-y-4">
        <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 p-4">
          <div className="text-[10px] font-bold uppercase tracking-widest text-indigo-400">Interpretation Variance</div>
          <p className="mt-1 text-[13px] leading-relaxed text-zinc-300 italic">
            {simulation.interpretation_variance}
          </p>
        </div>

        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4">
          <div className="text-[10px] font-bold uppercase tracking-widest text-cyan-400">Co-Director Note</div>
          <p className="mt-1 text-[13px] leading-relaxed text-zinc-200">
            {simulation.co_director_note}
          </p>
        </div>
      </div>
    </div>
  )
}

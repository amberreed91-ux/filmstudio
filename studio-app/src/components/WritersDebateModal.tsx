import { useState } from 'react'
import { Brain, ThumbsUp, X } from 'lucide-react'
import { saveDirectorMemoryEntry } from '../lib/studioApi'

export interface WritersDebateModalProps {
  projectId: string
  restraint: string
  urgency: string
  sceneId: string
  onDismiss: () => void
}

export default function WritersDebateModal({
  projectId,
  restraint,
  urgency,
  sceneId,
  onDismiss,
}: WritersDebateModalProps) {
  const [saving, setSaving] = useState<string | null>(null)
  const [agreed, setAgreed] = useState<'restraint' | 'urgency' | null>(null)

  const handleAgree = async (side: 'restraint' | 'urgency') => {
    if (saving) return
    setSaving(side)
    try {
      const label = side === 'restraint' ? 'Restraint' : 'Urgency'
      const text = side === 'restraint' ? restraint : urgency
      await saveDirectorMemoryEntry(projectId, 'notes', {
        headline: `Debate — ${label} perspective on scene ${sceneId}`,
        note: text,
        keyword: 'debate',
      })
      setAgreed(side)
    } catch (err) {
      console.error('Failed to save debate perspective:', err)
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-md p-6">
      <div className="relative w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col rounded-xl border border-white/10 bg-zinc-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/5 bg-zinc-950/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-cyan-500/20 text-cyan-400">
              <Brain size={18} />
            </div>
            <div>
              <h2 className="text-sm font-bold uppercase tracking-widest text-white">Scene Debate</h2>
              <p className="text-xs text-zinc-400">Two perspectives on the same scene</p>
            </div>
          </div>
          <button type="button"
            onClick={onDismiss}
            className="text-zinc-500 hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Side-by-side panels */}
        <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-white/10">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Restraint */}
            <div className="flex flex-col rounded-xl border border-indigo-500/20 bg-indigo-500/5">
              <div className="border-b border-indigo-500/10 px-5 py-3">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-indigo-400">
                  RESTRAINT VIEW
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">Minimalist · Contemplative</div>
              </div>
              <div className="flex-1 px-5 py-4">
                <p className="text-[13px] leading-relaxed text-zinc-300 whitespace-pre-wrap">
                  {restraint}
                </p>
              </div>
              <div className="border-t border-indigo-500/10 px-5 py-3">
                <button
                  type="button"
                  onClick={() => handleAgree('restraint')}
                  disabled={saving !== null || agreed !== null}
                  aria-busy={saving !== null}
                  className={`flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.02] disabled:opacity-50 ${
                    agreed === 'restraint'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/25'
                  }`}
                >
                  {saving === 'restraint' ? (
                    <>
                      <div className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
                      Saving...
                    </>
                  ) : agreed === 'restraint' ? (
                    <>
                      <ThumbsUp size={12} />
                      Saved to Director's Memory
                    </>
                  ) : (
                    <>
                      <ThumbsUp size={12} />
                      I agree with this approach
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Urgency */}
            <div className="flex flex-col rounded-xl border border-amber-500/20 bg-amber-500/5">
              <div className="border-b border-amber-500/10 px-5 py-3">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-400">
                  URGENCY VIEW
                </div>
                <div className="text-xs text-zinc-500 mt-0.5">Dynamic · Emotionally Direct</div>
              </div>
              <div className="flex-1 px-5 py-4">
                <p className="text-[13px] leading-relaxed text-zinc-300 whitespace-pre-wrap">
                  {urgency}
                </p>
              </div>
              <div className="border-t border-amber-500/10 px-5 py-3">
                <button
                  type="button"
                  onClick={() => handleAgree('urgency')}
                  disabled={saving !== null || agreed !== null}
                  aria-busy={saving !== null}
                  className={`flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] transition-all hover:scale-[1.02] disabled:opacity-50 ${
                    agreed === 'urgency'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-amber-500/15 text-amber-400 border border-amber-500/30 hover:bg-amber-500/25'
                  }`}
                >
                  {saving === 'urgency' ? (
                    <>
                      <div className="h-3 w-3 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
                      Saving...
                    </>
                  ) : agreed === 'urgency' ? (
                    <>
                      <ThumbsUp size={12} />
                      Saved to Director's Memory
                    </>
                  ) : (
                    <>
                      <ThumbsUp size={12} />
                      I agree with this approach
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

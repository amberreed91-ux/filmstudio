import { useEffect, useState } from 'react'

export type DossierDraft = {
  title: string
  format: string
  genre: string
  brief: string
}

type Props = {
  open: boolean
  initial: DossierDraft
  saving?: boolean
  onClose: () => void
  onSave: (draft: DossierDraft) => void
}

/**
 * DossierEditorModal — edit the Gate greenlight dossier in place.
 *
 * Obsidian glassmorphism treatment shared with the studio modal family:
 * backdrop-blur-2xl, #0B0F17/#121824 grounds, 2px #1E293B graphite border,
 * #CBD5E1 silver typography, gold #F59E0B focus rings, violet #8B5CF6
 * glowing selection borders. Presentation only: saving is delegated to the
 * parent so this modal never touches storage directly.
 */
export default function DossierEditorModal({ open, initial, saving = false, onClose, onSave }: Props) {
  const [draft, setDraft] = useState<DossierDraft>(initial)

  useEffect(() => {
    if (open) setDraft(initial)
  }, [open, initial])

  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const inputClass =
    'mt-1 block w-full rounded-lg border-2 border-[#1E293B] bg-[#121824] px-3 py-2 text-sm text-[#CBD5E1] placeholder:text-zinc-500 focus:border-[#8B5CF6] focus:outline-none focus:ring-2 focus:ring-[#F59E0B] focus:ring-offset-2 focus:ring-offset-[#0B0F17]'

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Edit project dossier"
      data-testid="dossier-editor-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border-2 border-[#1E293B] bg-[#0B0F17]/92 p-5 text-[#CBD5E1] shadow-[0_0_60px_rgba(109,40,217,0.35)] backdrop-blur-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-[#CBD5E1]">Edit project dossier</h2>
            <p className="mt-1 text-xs text-[#CBD5E1]/70">Title, format, genre, and creative brief stay editable until greenlight.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dossier editor"
            className="rounded border border-white/15 p-1.5 text-[#CBD5E1] hover:border-white/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]"
          >
            ✕
          </button>
        </div>
        <label className="mt-4 block text-[10px] uppercase tracking-[0.14em] text-[#CBD5E1]/60">
          Film title
          <input
            aria-label="Dossier title"
            value={draft.title}
            disabled={saving}
            onChange={(event) => setDraft((prev) => ({ ...prev, title: event.target.value }))}
            className={inputClass}
          />
        </label>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block text-[10px] uppercase tracking-[0.14em] text-[#CBD5E1]/60">
            Format
            <input
              aria-label="Dossier format"
              value={draft.format}
              disabled={saving}
              onChange={(event) => setDraft((prev) => ({ ...prev, format: event.target.value }))}
              className={inputClass}
            />
          </label>
          <label className="block text-[10px] uppercase tracking-[0.14em] text-[#CBD5E1]/60">
            Genre
            <input
              aria-label="Dossier genre"
              value={draft.genre}
              disabled={saving}
              onChange={(event) => setDraft((prev) => ({ ...prev, genre: event.target.value }))}
              className={inputClass}
            />
          </label>
        </div>
        <label className="mt-3 block text-[10px] uppercase tracking-[0.14em] text-[#CBD5E1]/60">
          Creative brief
          <textarea
            aria-label="Dossier brief"
            value={draft.brief}
            disabled={saving}
            onChange={(event) => setDraft((prev) => ({ ...prev, brief: event.target.value }))}
            rows={4}
            className={inputClass}
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-md border border-white/15 px-3 py-2 text-xs text-[#CBD5E1] disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onSave(draft)}
            disabled={saving || !draft.title.trim()}
            aria-label="Save dossier changes"
            className="rounded-md border-2 border-[#8B5CF6]/60 px-3 py-2 text-xs font-medium text-[#CBD5E1] shadow-[0_0_16px_rgba(139,92,246,0.35)] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0F17]"
          >
            {saving ? 'Saving…' : 'Save dossier'}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Director's Memory Panel — five-tab UI for the Director's Memory Engine.
 *
 * Co-director voice throughout; no numeric scores or percentages. All entry
 * mutations are explicit-save-only.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  DIRECTOR_MEMORY_KINDS,
  type CharacterEntry,
  type CoDirectorDebateEntry,
  type DirectorMemoryBundle,
  type DirectorMemoryEntry,
  type DirectorMemoryKind,
  type DirectorNoteEntry,
  type MotifEntry,
  type SymbolEntry,
  type ThemeEntry,
} from '../types/directorMemory'
import {
  deleteDirectorMemoryEntry,
  getDirectorMemory,
  saveDirectorMemoryEntry,
} from '../lib/studioApi'

type DraftState = Record<string, string>

const EMPTY_BUNDLE: DirectorMemoryBundle = {
  symbols: [],
  motifs: [],
  characters: [],
  themes: [],
  notes: [],
  debates: [],
}

const TAB_LABELS: Record<DirectorMemoryKind, string> = {
  symbols: 'Symbols',
  motifs: 'Motifs',
  characters: 'Characters',
  themes: 'Themes',
  notes: "Director's Notes",
  debates: 'Debates',
}

function buildEmptyDraft(kind: DirectorMemoryKind): DraftState {
  switch (kind) {
    case 'symbols':
      return { symbol: '', meaning: '', first_introduced_scene: '' }
    case 'motifs':
      return { motif: '', keyword: '', first_introduced_scene: '' }
    case 'characters':
      return { character: '', traits: '', avoids: '', motivations: '', speech_patterns: '' }
    case 'themes':
      return { theme: '', first_introduced_scene: '' }
    case 'notes':
      return { headline: '', note: '', keyword: '' }
    case 'debates':
      return { query: '', synthesis: '' }
  }
}

function normalizeDraft(kind: DirectorMemoryKind, draft: DraftState): Record<string, unknown> {
  const splitList = (raw: string): string[] =>
    raw
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean)

  if (kind === 'characters') {
    return {
      character: draft.character,
      traits: splitList(draft.traits ?? ''),
      avoids: splitList(draft.avoids ?? ''),
      motivations: draft.motivations,
      speech_patterns: draft.speech_patterns,
    }
  }
  return { ...draft }
}

function entryHeadline(entry: DirectorMemoryEntry): string {
  switch (entry.kind) {
    case 'symbols':
      return (entry as SymbolEntry).symbol
    case 'motifs':
      return (entry as MotifEntry).motif
    case 'characters':
      return (entry as CharacterEntry).character
    case 'themes':
      return (entry as ThemeEntry).theme
    case 'notes':
      return (entry as DirectorNoteEntry).headline || (entry as DirectorNoteEntry).note
    case 'debates':
      return (entry as CoDirectorDebateEntry).query
  }
}

function entryDetail(entry: DirectorMemoryEntry): string {
  switch (entry.kind) {
    case 'symbols': {
      const s = entry as SymbolEntry
      return `${s.meaning || 'meaning unset'} · first seen ${s.first_introduced_scene || 'unset'}`
    }
    case 'motifs': {
      const m = entry as MotifEntry
      return `keyword: ${m.keyword || m.motif} · last seen ${m.last_seen_scene || 'unset'}`
    }
    case 'characters': {
      const c = entry as CharacterEntry
      const parts: string[] = []
      if (c.traits.length) parts.push(`traits: ${c.traits.join(', ')}`)
      if (c.avoids.length) parts.push(`avoids: ${c.avoids.join(', ')}`)
      if (c.motivations) parts.push(`motivation: ${c.motivations}`)
      return parts.join(' · ') || 'no traits captured yet'
    }
    case 'themes': {
      const t = entry as ThemeEntry
      return `last surfaced in ${t.last_seen_scene || 'unset'}`
    }
    case 'notes': {
      const n = entry as DirectorNoteEntry
      return n.note
    }
    case 'debates': {
      const d = entry as CoDirectorDebateEntry
      return d.synthesis || d.filmmaker_prerogative || 'debate saved'
    }
  }
}

export interface DirectorMemoryPanelProps {
  projectId: string
}

export default function DirectorMemoryPanel({ projectId }: DirectorMemoryPanelProps) {
  const [activeTab, setActiveTab] = useState<DirectorMemoryKind>('symbols')
  const [bundle, setBundle] = useState<DirectorMemoryBundle>(EMPTY_BUNDLE)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<DraftState>(() => buildEmptyDraft('symbols'))
  const [submitting, setSubmitting] = useState<boolean>(false)

  const loadMemory = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setError(null)
    try {
      const response = await getDirectorMemory(projectId)
      setBundle({ ...EMPTY_BUNDLE, ...response.memory })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load director memory')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void loadMemory()
  }, [loadMemory])

  useEffect(() => {
    setDraft(buildEmptyDraft(activeTab))
  }, [activeTab])

  const entries: DirectorMemoryEntry[] = useMemo(() => {
    return bundle[activeTab] as DirectorMemoryEntry[]
  }, [bundle, activeTab])

  const handleSave = useCallback(async () => {
    setSubmitting(true)
    setError(null)
    try {
      await saveDirectorMemoryEntry(projectId, activeTab, normalizeDraft(activeTab, draft))
      setDraft(buildEmptyDraft(activeTab))
      await loadMemory()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save entry')
    } finally {
      setSubmitting(false)
    }
  }, [activeTab, draft, loadMemory, projectId])

  const handleDelete = useCallback(
    async (entryId: string) => {
      setSubmitting(true)
      setError(null)
      try {
        await deleteDirectorMemoryEntry(projectId, activeTab, entryId)
        await loadMemory()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete entry')
      } finally {
        setSubmitting(false)
      }
    },
    [activeTab, loadMemory, projectId],
  )

  return (
    <section className="director-memory-panel rounded border border-white/10 bg-black/30 p-4">
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-200">
          Director's Memory
        </h3>
        <span className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-amber-100">
          Co-director voice
        </span>
      </header>

      <nav className="mt-3 flex flex-wrap gap-1" role="tablist">
        {DIRECTOR_MEMORY_KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            role="tab"
            aria-selected={activeTab === kind}
            onClick={() => setActiveTab(kind)}
            className={`rounded px-2 py-1 text-[11px] uppercase tracking-[0.1em] ${
              activeTab === kind
                ? 'bg-white/15 text-white'
                : 'bg-black/30 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {TAB_LABELS[kind]}
          </button>
        ))}
      </nav>

      {error ? (
        <div className="mt-3 rounded border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-100">
          {error}
        </div>
      ) : null}

      <div className="mt-3">
        {loading ? (
          <div className="text-[11px] text-zinc-400">Loading memory…</div>
        ) : entries.length === 0 ? (
          <div className="rounded border border-white/10 bg-black/25 px-3 py-3 text-[11px] text-zinc-400">
            No {TAB_LABELS[activeTab].toLowerCase()} captured yet. Add one below — entries persist
            across sessions for this project.
          </div>
        ) : (
          <ul className="space-y-2">
            {entries.map((entry) => (
              <li
                key={entry.entry_id}
                className="rounded border border-white/10 bg-black/20 px-3 py-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-xs font-semibold text-zinc-100">
                      {entryHeadline(entry)}
                    </div>
                    <div className="mt-1 text-[11px] text-zinc-400">{entryDetail(entry)}</div>
                    <div className="mt-1 text-[10px] uppercase tracking-[0.1em] text-zinc-500">
                      defined {new Date(entry.saved_at).toLocaleDateString()}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDelete(entry.entry_id)}
                    disabled={submitting}
                    className="rounded border border-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-300 hover:bg-white/10 disabled:opacity-50"
                  >
                    Forget
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <DirectorMemoryDraftForm
        kind={activeTab}
        draft={draft}
        onChange={setDraft}
        onSubmit={() => void handleSave()}
        submitting={submitting}
      />
    </section>
  )
}

interface DraftFormProps {
  kind: DirectorMemoryKind
  draft: DraftState
  onChange: (next: DraftState) => void
  onSubmit: () => void
  submitting: boolean
}

function DirectorMemoryDraftForm({ kind, draft, onChange, onSubmit, submitting }: DraftFormProps) {
  const set = (field: string, value: string) => onChange({ ...draft, [field]: value })

  const fields = useMemo(() => fieldConfigForKind(kind), [kind])
  const primaryField = fields[0]?.field
  const canSubmit = Boolean(primaryField && (draft[primaryField] ?? '').trim())

  return (
    <form
      className="mt-3 border-t border-white/10 pt-3"
      onSubmit={(event) => {
        event.preventDefault()
        if (canSubmit && !submitting) onSubmit()
      }}
    >
      <div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-zinc-400">
        Add to memory (explicit save)
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {fields.map(({ field, label, placeholder, multiline }) =>
          multiline ? (
            <textarea
              key={field}
              value={draft[field] ?? ''}
              placeholder={placeholder ?? label}
              onChange={(event) => set(field, event.target.value)}
              className="col-span-full rounded border border-white/10 bg-black/40 px-2 py-1 text-[12px] text-zinc-100 placeholder:text-zinc-500"
              rows={2}
            />
          ) : (
            <input
              key={field}
              type="text"
              value={draft[field] ?? ''}
              placeholder={placeholder ?? label}
              onChange={(event) => set(field, event.target.value)}
              className="rounded border border-white/10 bg-black/40 px-2 py-1 text-[12px] text-zinc-100 placeholder:text-zinc-500"
            />
          ),
        )}
      </div>
      <div className="mt-2 flex justify-end">
        <button
          type="submit"
          disabled={!canSubmit || submitting}
          className="rounded bg-amber-500/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-black hover:bg-amber-400 disabled:opacity-50"
        >
          Save to project memory
        </button>
      </div>
    </form>
  )
}

interface FieldConfig {
  field: string
  label: string
  placeholder?: string
  multiline?: boolean
}

function fieldConfigForKind(kind: DirectorMemoryKind): FieldConfig[] {
  switch (kind) {
    case 'symbols':
      return [
        { field: 'symbol', label: 'Symbol', placeholder: 'e.g. blue' },
        { field: 'meaning', label: 'Meaning', placeholder: 'e.g. grief' },
        { field: 'first_introduced_scene', label: 'First introduced (scene id)' },
      ]
    case 'motifs':
      return [
        { field: 'motif', label: 'Motif', placeholder: 'e.g. backlit silhouettes' },
        { field: 'keyword', label: 'Detection keyword', placeholder: 'e.g. silhouette' },
        { field: 'first_introduced_scene', label: 'First seen (scene id)' },
      ]
    case 'characters':
      return [
        { field: 'character', label: 'Character', placeholder: 'e.g. Marcus' },
        { field: 'traits', label: 'Traits (comma separated)' },
        { field: 'avoids', label: 'Avoids (comma separated)', placeholder: 'e.g. confrontation' },
        { field: 'motivations', label: 'Motivations' },
        { field: 'speech_patterns', label: 'Speech patterns', multiline: true },
      ]
    case 'themes':
      return [
        { field: 'theme', label: 'Theme', placeholder: 'e.g. isolation' },
        { field: 'first_introduced_scene', label: 'First surfaced (scene id)' },
      ]
    case 'notes':
      return [
        { field: 'headline', label: 'Headline' },
        { field: 'keyword', label: 'Trigger keyword (optional)' },
        { field: 'note', label: 'Note', multiline: true },
      ]
    case 'debates':
      return [
        { field: 'query', label: 'Query' },
        { field: 'synthesis', label: 'Synthesis', multiline: true },
      ]
  }
}

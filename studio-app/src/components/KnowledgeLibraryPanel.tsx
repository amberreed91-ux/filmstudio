import { useCallback, useEffect, useMemo, useState } from 'react'
import { BookOpen, Brain, Database, GitCompare, Loader2, RefreshCw, Send } from 'lucide-react'

import {
  buildKnowledgeContext,
  listKnowledgeAtoms,
  listKnowledgeBibles,
  listKnowledgeConflicts,
  rebuildKnowledgeIndex,
  registerKnowledgeBible,
  type CanonicalConflict,
  type KnowledgeAtom,
  type KnowledgeBible,
  type KnowledgeContextPack,
} from '../lib/studioKnowledgeApi'

type KnowledgeLibraryPanelProps = {
  projectId: string
}

const SAMPLE_BIBLE = `# Tone Rules
- The film should stay patient with tension.
- Never explain a motif before the scene earns it.

# Visual Style
- Use practical light as emotional evidence, not decoration.

# Pacing
- Hold silence when a character is trying not to reveal what they know.`

function sourceLabel(sourceType: string): string {
  return sourceType.replace(/_/g, ' ')
}

export default function KnowledgeLibraryPanel({ projectId }: KnowledgeLibraryPanelProps) {
  const [bibles, setBibles] = useState<KnowledgeBible[]>([])
  const [atoms, setAtoms] = useState<KnowledgeAtom[]>([])
  const [conflicts, setConflicts] = useState<CanonicalConflict[]>([])
  const [contextPack, setContextPack] = useState<KnowledgeContextPack | null>(null)
  const [title, setTitle] = useState('Project Bible')
  const [bibleType, setBibleType] = useState('story')
  const [content, setContent] = useState(SAMPLE_BIBLE)
  const [department, setDepartment] = useState('co_director')
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState('')

  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const atom of atoms) {
      const key = atom.source_ref.source_type
      counts[key] = (counts[key] || 0) + 1
    }
    return counts
  }, [atoms])

  const refresh = useCallback(async () => {
    if (!projectId) return
    setBusy('refresh')
    try {
      const [bibleResult, atomResult, conflictResult] = await Promise.all([
        listKnowledgeBibles(projectId),
        listKnowledgeAtoms(projectId, 80),
        listKnowledgeConflicts(projectId),
      ])
      setBibles(bibleResult.bibles)
      setAtoms(atomResult.atoms)
      setConflicts(conflictResult.conflicts)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Knowledge refresh failed')
    } finally {
      setBusy(null)
    }
  }, [projectId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function handleRegisterBible() {
    if (!title.trim() || !content.trim()) {
      setMessage('Give the Bible a title and body before adding it.')
      return
    }
    setBusy('register')
    setMessage('')
    try {
      const response = await registerKnowledgeBible(projectId, {
        title,
        bible_type: bibleType,
        content,
        content_type: 'markdown',
      })
      setMessage(`Added ${response.atoms.length} source-cited knowledge item${response.atoms.length === 1 ? '' : 's'}.`)
      await refresh()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Bible registration failed')
    } finally {
      setBusy(null)
    }
  }

  async function handleRebuild() {
    setBusy('rebuild')
    setMessage('')
    try {
      const run = await rebuildKnowledgeIndex(projectId)
      setMessage(`Index rebuilt with ${run.atom_count} active item${run.atom_count === 1 ? '' : 's'}.`)
      await refresh()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Knowledge rebuild failed')
    } finally {
      setBusy(null)
    }
  }

  async function handleContext() {
    setBusy('context')
    setMessage('')
    try {
      const pack = await buildKnowledgeContext(projectId, {
        department,
        purpose: 'study_room_inspection',
        max_atoms: 10,
      })
      setContextPack(pack)
      setMessage(`Context trace ${pack.trace_id} is ready for ${sourceLabel(department)}.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Context pack failed')
    } finally {
      setBusy(null)
    }
  }

  const isBusy = busy !== null

  return (
    <section className="glass-panel rounded-xl p-4 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen size={15} style={{ color: 'var(--color-secondary)' }} />
            <span className="text-[11px] font-bold uppercase tracking-[0.18em]" style={{ color: 'var(--color-secondary)' }}>
              Canonical Knowledge
            </span>
          </div>
          <p className="mt-1 text-[11px]" style={{ color: 'var(--color-on-surface-variant)' }}>
            Shared Bible intelligence, source-cited for every department.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={isBusy}
          className="rounded-lg border border-white/10 p-2 transition-all hover:bg-white/10 disabled:opacity-50"
          title="Refresh knowledge library"
        >
          {busy === 'refresh' ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-[1fr_140px]">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="cyber-input rounded px-3 py-2 text-xs outline-none"
          style={{ color: 'var(--color-on-surface)' }}
          placeholder="Bible title"
        />
        <select
          value={bibleType}
          onChange={(event) => setBibleType(event.target.value)}
          className="cyber-input rounded px-3 py-2 text-xs outline-none"
          style={{ color: 'var(--color-on-surface)' }}
        >
          <option value="story">Story</option>
          <option value="visual">Visual</option>
          <option value="tone">Tone</option>
          <option value="character">Character</option>
          <option value="production">Production</option>
        </select>
      </div>
      <textarea
        value={content}
        onChange={(event) => setContent(event.target.value)}
        rows={7}
        className="cyber-input w-full rounded px-3 py-2 text-xs outline-none"
        style={{ color: 'var(--color-on-surface)' }}
        placeholder="Paste a filmmaking Bible, style guide, character Bible, or production rulebook..."
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleRegisterBible()}
          disabled={isBusy}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:scale-[1.01] disabled:opacity-50"
          style={{ background: 'rgba(255,209,101,0.15)', color: 'var(--color-primary)', border: '1px solid rgba(255,209,101,0.3)' }}
        >
          {busy === 'register' ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
          Add Bible
        </button>
        <button
          type="button"
          onClick={() => void handleRebuild()}
          disabled={isBusy}
          className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-all hover:bg-white/10 disabled:opacity-50"
          style={{ color: 'var(--color-on-surface)' }}
        >
          {busy === 'rebuild' ? <Loader2 size={13} className="animate-spin" /> : <Database size={13} />}
          Rebuild Index
        </button>
      </div>

      {message && <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[11px]" style={{ color: 'var(--color-on-surface)' }}>{message}</div>}

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-white/10 p-3">
          <div className="text-[9px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-on-surface-variant)' }}>Bibles</div>
          <div className="mt-1 text-2xl font-semibold" style={{ color: 'var(--color-on-surface)' }}>{bibles.length}</div>
        </div>
        <div className="rounded-lg border border-white/10 p-3">
          <div className="text-[9px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-on-surface-variant)' }}>Active Items</div>
          <div className="mt-1 text-2xl font-semibold" style={{ color: 'var(--color-on-surface)' }}>{atoms.length}</div>
        </div>
        <div className="rounded-lg border border-white/10 p-3">
          <div className="text-[9px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-on-surface-variant)' }}>Open Conflicts</div>
          <div className="mt-1 text-2xl font-semibold" style={{ color: conflicts.length ? 'var(--color-primary)' : 'var(--color-on-surface)' }}>{conflicts.length}</div>
        </div>
      </div>

      <div className="rounded-lg border border-white/10 p-3">
        <div className="mb-2 flex items-center gap-2">
          <Brain size={14} style={{ color: 'var(--color-secondary)' }} />
          <span className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-secondary)' }}>Department Context</span>
        </div>
        <div className="flex gap-2">
          <select
            value={department}
            onChange={(event) => setDepartment(event.target.value)}
            className="cyber-input flex-1 rounded px-3 py-2 text-xs outline-none"
            style={{ color: 'var(--color-on-surface)' }}
          >
            <option value="co_director">Co-Director</option>
            <option value="cinematographer">Cinematographer</option>
            <option value="production_designer">Production Designer</option>
            <option value="colorist">Colorist</option>
            <option value="performance">Performance</option>
            <option value="audio">Audio</option>
            <option value="editor">Editor</option>
            <option value="render">Render</option>
            <option value="screening">Screening</option>
          </select>
          <button
            type="button"
            onClick={() => void handleContext()}
            disabled={isBusy}
            className="rounded-lg border border-white/10 px-3 py-2 transition-all hover:bg-white/10 disabled:opacity-50"
            title="Build context pack"
          >
            {busy === 'context' ? <Loader2 size={14} className="animate-spin" /> : <GitCompare size={14} />}
          </button>
        </div>
      </div>

      {Object.keys(sourceCounts).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(sourceCounts).map(([source, count]) => (
            <span key={source} className="rounded border border-white/10 px-2 py-1 text-[9px] uppercase tracking-[0.08em]" style={{ color: 'var(--color-on-surface-variant)' }}>
              {sourceLabel(source)}: {count}
            </span>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {atoms.slice(0, 6).map((atom) => (
          <div key={atom.atom_id} className="rounded-lg border border-white/10 p-3">
            <div className="mb-1 flex flex-wrap items-center gap-1.5">
              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[8px] uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                {sourceLabel(atom.source_ref.source_type)}
              </span>
              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[8px] uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                {sourceLabel(atom.atom_type)}
              </span>
              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[8px] uppercase tracking-[0.1em]" style={{ color: 'var(--color-on-surface-variant)' }}>
                {sourceLabel(atom.authority_level)}
              </span>
            </div>
            <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-on-surface)' }}>{atom.summary || atom.canonical_text}</p>
          </div>
        ))}
      </div>

      {contextPack && (
        <div className="rounded-lg border border-secondary/30 bg-secondary/10 p-3">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-secondary)' }}>
            Context Trace {contextPack.trace_id}
          </div>
          <div className="space-y-1.5">
            {contextPack.atoms.slice(0, 5).map((atom) => (
              <p key={atom.atom_id} className="text-[11px]" style={{ color: 'var(--color-on-surface)' }}>
                {atom.summary || atom.canonical_text}
              </p>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}


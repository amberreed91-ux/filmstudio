import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, Link2, Loader2, Trash2, Upload, X } from 'lucide-react'
import { buildStudioApiUrl } from '../lib/studioApi'
import {
  addReferenceLibraryAsset,
  approveReferenceLibraryAsset,
  getReferenceLibrary,
  removeReferenceLibraryAsset,
  uploadReferenceLibraryAsset,
  type ReferenceAsset,
  type ReferenceLibrary,
} from '../lib/visualTrainingApi'

type Props = { projectId: string; targetType: 'character' | 'scene'; targetId: string }

/** Supporting reference categories per target, with an open Other option. */
const CATEGORY_OPTIONS: Record<'character' | 'setting', string[]> = {
  character: ['face', 'profile', 'full_body', 'wardrobe', 'night', 'expression'],
  setting: ['wide', 'architecture', 'day', 'night', 'detail'],
}
const OTHER_CATEGORY = 'other'

function categoryChoices(libraryTarget: 'character' | 'setting'): string[] {
  return [...CATEGORY_OPTIONS[libraryTarget], OTHER_CATEGORY]
}

function CategorySelect({ value, onChange, disabled }: { value: string; onChange: (value: string) => void; disabled?: boolean }) {
  const kind = value === 'scene' ? 'setting' : (value as 'character' | 'setting')
  const choices = CATEGORY_OPTIONS[kind] ? [...CATEGORY_OPTIONS[kind], OTHER_CATEGORY] : [OTHER_CATEGORY]
  return (
    <select
      aria-label="Reference category"
      value={choices.includes(value) ? value : OTHER_CATEGORY}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="rounded border border-white/15 bg-black/40 px-1.5 py-1 text-[10px] capitalize text-zinc-200"
    >
      {choices.map((choice) => (
        <option key={choice} value={choice}>
          {choice.replace(/_/g, ' ')}
        </option>
      ))}
    </select>
  )
}

function ImageThumb({ asset }: { asset: ReferenceAsset }) {
  return <img src={/^https?:\/\//.test(asset.image_url) ? asset.image_url : buildStudioApiUrl(asset.image_url)} alt={asset.category || asset.kind.replace(/_/g, ' ')} className="h-full w-full object-cover" />
}

export default function ReferenceLibraryPanel({ projectId, targetType, targetId }: Props) {
  const libraryTarget = targetType === 'scene' ? 'setting' : 'character'
  const [library, setLibrary] = useState<ReferenceLibrary | null>(null)
  const [loading, setLoading] = useState(true)
  const [url, setUrl] = useState('')
  const [urlCategory, setUrlCategory] = useState(categoryChoices(libraryTarget)[0])
  const [uploadCategory, setUploadCategory] = useState(categoryChoices(libraryTarget)[0])
  const [categoryEdits, setCategoryEdits] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const refresh = useCallback(async () => {
    if (!projectId || !targetId) return
    setLoading(true)
    try {
      setLibrary(await getReferenceLibrary(projectId, libraryTarget, targetId))
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reference library unavailable')
    } finally {
      setLoading(false)
    }
  }, [projectId, targetId, libraryTarget])

  useEffect(() => { void refresh() }, [refresh])

  /** URL references enter as candidates — identical lifecycle to uploads. */
  const addSupporting = async () => {
    if (!url.trim()) return
    setBusy(true)
    setError('')
    try {
      await addReferenceLibraryAsset(projectId, libraryTarget, targetId, {
        ref_id: `ref_${Date.now()}`,
        kind: libraryTarget === 'character' ? 'character_full' : 'environment',
        image_url: url.trim(),
        category: urlCategory,
        approval_state: 'candidate',
        source_kind: 'uploaded',
      })
      setUrl('')
      setNotice('Reference added as a candidate. Approve it before generation.')
      await refresh()
    } catch (err) { setError(err instanceof Error ? err.message : 'Reference could not be added') }
    finally { setBusy(false) }
  }

  const uploadFile = async (file: File) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await uploadReferenceLibraryAsset(projectId, libraryTarget, targetId, file, uploadCategory)
      setNotice('Upload registered as a candidate. Approve it before generation.')
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed — nothing was registered. You can retry.')
    }
    finally {
      if (fileInputRef.current) fileInputRef.current.value = ''
      setBusy(false)
    }
  }

  const approve = async (refId: string) => { setBusy(true); setError(''); try { await approveReferenceLibraryAsset(projectId, libraryTarget, targetId, refId); await refresh() } catch (err) { setError(err instanceof Error ? err.message : 'Reference could not be approved') } finally { setBusy(false) } }
  const remove = async (refId: string) => { setBusy(true); setError(''); try { await removeReferenceLibraryAsset(projectId, libraryTarget, targetId, refId); await refresh() } catch (err) { setError(err instanceof Error ? err.message : 'Reference could not be removed') } finally { setBusy(false) } }

  const supporting = library?.supporting || []
  const candidates = library?.candidates || []
  return <section aria-label={`${libraryTarget} visual reference library`} data-testid="reference-library" className="mt-5 border-t border-white/10 pt-5">
    <div className="flex items-baseline justify-between gap-3"><div><p className="text-[11px] font-medium uppercase tracking-[0.15em] text-amber-100/80">Visual reference library</p><h3 className="mt-1 text-sm font-medium text-zinc-100">Locked identity · supporting evidence</h3></div>{library && <span className="text-[11px] capitalize text-zinc-500">{(library.coverage || 'not_covered').replace(/_/g, ' ')}</span>}</div>
    <p className="mt-1 text-xs leading-relaxed text-zinc-500">Supporting references reinforce the canonical image. They never replace it. Uploaded and URL references both start as candidates and need explicit approval before generation.</p>
    {loading ? <p className="mt-3 flex items-center gap-2 text-xs text-zinc-400"><Loader2 size={13} className="animate-spin" />Loading library…</p> : <>
      {library?.canonical ? <div className="mt-3 flex items-center gap-3 rounded border border-amber-200/30 bg-amber-200/5 p-2"><div className="h-14 w-12 overflow-hidden rounded bg-black/40"><ImageThumb asset={library.canonical} /></div><div><p className="text-xs font-medium text-amber-100">Canonical reference · locked</p><p className="text-xs text-zinc-500">Human-controlled visual anchor</p></div></div> : <p className="mt-3 text-xs text-zinc-500">No canonical reference is registered for this target yet.</p>}
      <div className="mt-3 grid grid-cols-3 gap-2">{supporting.map((asset) => <div key={asset.ref_id} className="group relative overflow-hidden rounded border border-white/15 bg-black/30"><div className="aspect-square"><ImageThumb asset={asset} /></div><p className="truncate px-2 py-1.5 text-[10px] capitalize text-zinc-400">{asset.category || 'supporting'}{asset.source_kind === 'uploaded' ? ' · upload' : ''}</p><button type="button" aria-label={`Remove ${asset.category || 'supporting'} reference`} disabled={busy} aria-busy={busy} onClick={() => void remove(asset.ref_id)} className="absolute right-1 top-1 rounded bg-black/70 p-1 text-zinc-200 opacity-0 group-hover:opacity-100"><Trash2 size={12} /></button></div>)}</div>
      {candidates.length > 0 && <div className="mt-3 rounded border border-amber-200/20 bg-amber-200/5 p-3"><p className="text-xs text-amber-100">Candidate references awaiting approval</p>{candidates.map((asset) => (
        <div key={asset.ref_id} className="mt-2 flex items-center justify-between gap-2 text-xs text-zinc-300">
          <div className="flex min-w-0 items-center gap-2">
            <span data-testid={`candidate-source-${asset.ref_id}`} className="shrink-0 rounded border border-white/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">{asset.source_kind === 'uploaded' ? 'upload' : 'url'}</span>
            <CategorySelect value={categoryEdits[asset.ref_id] || asset.category || OTHER_CATEGORY} onChange={(value) => setCategoryEdits((prev) => ({ ...prev, [asset.ref_id]: value }))} disabled={busy} />
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button type="button" aria-label={`Approve candidate ${asset.ref_id}`} disabled={busy} aria-busy={busy} onClick={() => void approve(asset.ref_id)} className="inline-flex items-center gap-1 rounded border border-emerald-300/30 px-2 py-1 text-emerald-200"><Check size={11} />Approve</button>
            <button type="button" aria-label={`Reject candidate ${asset.ref_id}`} disabled={busy} aria-busy={busy} onClick={() => void remove(asset.ref_id)} className="rounded border border-rose-300/30 p-1 text-rose-200" title="Reject candidate"><X size={12} /></button>
          </div>
        </div>
      ))}</div>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" data-testid="reference-upload-input" onChange={(e) => { const file = e.target.files?.[0]; if (file) void uploadFile(file) }} />
        <button type="button" data-testid="reference-upload-button" disabled={busy} onClick={() => fileInputRef.current?.click()} className="inline-flex items-center gap-1 rounded border border-white/20 px-2.5 py-2 text-xs text-zinc-200 disabled:opacity-40"><Upload size={13} />Upload Reference</button>
        <CategorySelect value={uploadCategory} onChange={setUploadCategory} disabled={busy} />
      </div>
      <div className="mt-2 flex flex-wrap gap-2"><input aria-label="Supporting reference image URL" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a supporting image URL" className="min-w-0 flex-1 rounded border border-white/15 bg-black/30 px-2.5 py-2 text-xs text-zinc-200" /><CategorySelect value={urlCategory} onChange={setUrlCategory} disabled={busy} /><button type="button" aria-label="Add image URL reference" disabled={busy || !url.trim()} aria-busy={busy} onClick={() => void addSupporting()} className="inline-flex items-center gap-1 rounded border border-white/20 px-2.5 py-2 text-xs text-zinc-200 disabled:opacity-40">{busy ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}Add Image URL</button></div>
    </>}
    {notice && !error && <p role="status" className="mt-2 text-xs text-emerald-200">{notice}</p>}
    {error && <p role="alert" className="mt-2 text-xs text-rose-200">{error}</p>}
  </section>
}

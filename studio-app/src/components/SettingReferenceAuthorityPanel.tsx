import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, Loader2, Stamp, X } from 'lucide-react'
import { buildStudioApiUrl } from '../lib/studioApi'
import {
  SCENE002_PROJECT_ID,
  SCENE002_SETTING_ID,
  approveSettingReference,
  createSettingReference,
  designateSettingReferenceCanonical,
  exactSettingReferenceRows,
  rejectSettingReference,
  listSettingReferences,
  uploadSettingReference,
  type SettingReferenceAsset,
} from '../lib/settingReferenceApi'

type Props = { projectId: string }

const inputClass = 'mt-1 w-full min-w-0 rounded-md border border-white/15 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 disabled:opacity-50'
const buttonClass = 'min-h-10 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-200 disabled:opacity-40'

function lifecycleState(row: SettingReferenceAsset): 'candidate' | 'approved' | 'canonical' | 'rejected' {
  if (row.approval_state === 'rejected') return 'rejected'
  if (row.canonical) return 'canonical'
  return row.approval_state === 'approved' ? 'approved' : 'candidate'
}

const STATE_STYLE: Record<string, string> = {
  candidate: 'border-white/20 text-zinc-300',
  approved: 'border-emerald-300/40 text-emerald-200',
  canonical: 'border-amber-200/50 text-amber-100',
  rejected: 'border-red-300/40 text-red-200',
}

/**
 * Creator workflow for ONE exact entity: setting/loc-c8f88b9c in
 * project_5907c60cddbc.
 *
 * Every read goes through the sync-free scoped endpoint, so opening this panel
 * never invokes legacy creator reference sync. Every write is an explicit,
 * separate creator action — register, approve, designate canonical — with no
 * automatic selection, approval, or canonicalization anywhere. Picking the
 * reference for Scene Direction stays a separate explicit decision in the
 * Scene Direction selector.
 */
export function SettingReferenceAuthorityPanel({ projectId }: Props) {
  const [rows, setRows] = useState<SettingReferenceAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const response = await listSettingReferences(projectId)
      setRows(exactSettingReferenceRows(projectId, response?.reference_assets))
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Exact setting references could not be loaded')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  const inScope = projectId === SCENE002_PROJECT_ID

  useEffect(() => {
    if (!inScope) { setRows([]); setLoading(false); return }
    void refresh()
  }, [refresh, inScope])

  // This workflow exists for exactly one project + setting pair. Any other
  // scope renders nothing rather than a panel that could point at the wrong entity.
  if (!inScope) return null

  const registerUri = async () => {
    if (!imageUrl.trim()) return
    setBusy(true); setError(''); setNotice('')
    try {
      const { reference_asset: created } = await createSettingReference(projectId, imageUrl.trim())
      setImageUrl('')
      setNotice(`Registered ${created.ref_id} as a candidate. Approval and canonical designation are separate actions.`)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Reference could not be registered')
    } finally { setBusy(false) }
  }

  const registerUpload = async (file: File | undefined | null) => {
    if (!file) return
    setBusy(true); setError(''); setNotice('')
    try {
      const { reference_asset: created } = await uploadSettingReference(projectId, file)
      setNotice(`Registered ${created.ref_id} as a candidate. Approval and canonical designation are separate actions.`)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Upload failed — nothing was registered. You can retry.')
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = ''
      setBusy(false)
    }
  }

  const approve = async (referenceId: string) => {
    setBusy(true); setError(''); setNotice('')
    try {
      await approveSettingReference(projectId, referenceId)
      setNotice(`Approved ${referenceId}. Canonical designation is still a separate action.`)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Reference could not be approved')
    } finally { setBusy(false) }
  }

  const reject = async (referenceId: string) => {
    setBusy(true); setError(''); setNotice('')
    try {
      await rejectSettingReference(projectId, referenceId)
      setNotice(`Rejected ${referenceId}. Its record and canonical flag are preserved; selection is unchanged.`)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Reference could not be rejected')
    } finally { setBusy(false) }
  }

  const designate = async (referenceId: string) => {
    setBusy(true); setError(''); setNotice('')
    try {
      await designateSettingReferenceCanonical(projectId, referenceId)
      setNotice(`${referenceId} is now canonical for ${SCENE002_SETTING_ID}. Select it explicitly in Scene Direction.`)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Reference could not be designated canonical')
    } finally { setBusy(false) }
  }

  return (
    <section aria-label="Exact setting reference authority" data-testid="setting-reference-authority" className="mt-5 rounded-lg border border-white/15 p-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-amber-100/80">Setting authority</p>
      <h3 className="mt-1 text-sm font-medium text-zinc-100">Exact environment reference · register, approve, designate</h3>
      <p className="mt-1 text-xs leading-relaxed text-zinc-500">Canonical setting entity: <code className="text-amber-100">{SCENE002_SETTING_ID}</code>. Each registration creates a brand-new candidate reference for this exact entity — nothing is replaced or deduplicated by image URI. Nothing here selects a reference for the scene: that stays an explicit Scene Direction decision.</p>
      {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
      {notice && <p role="status" className="mt-3 text-xs text-emerald-200">{notice}</p>}
      {loading ? (
        <p className="mt-3 flex items-center gap-2 text-xs text-zinc-400"><Loader2 size={13} className="animate-spin" />Loading exact setting references…</p>
      ) : (
        <>
          {rows.length === 0 && <p className="mt-3 text-xs text-zinc-500">No references are registered for this exact setting yet.</p>}
          <ul className="mt-3 space-y-2">
            {rows.map(row => {
              const state = lifecycleState(row)
              return (
                <li key={row.ref_id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-white/10 bg-black/30 p-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="h-10 w-10 shrink-0 overflow-hidden rounded bg-zinc-900">
                      {row.image_url ? <img src={/^https?:\/\//.test(row.image_url) ? row.image_url : buildStudioApiUrl(row.image_url)} alt={`Reference ${row.ref_id}`} className="h-full w-full object-cover" /> : null}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-xs text-zinc-200"><code>{row.ref_id}</code></p>
                      <p className="text-[11px] text-zinc-500">{row.target_type}/{row.target_id} · {row.kind}</p>
                    </div>
                    <span data-testid={`state-${row.ref_id}`} className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${STATE_STYLE[state]}`}>{state}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {state === 'candidate' && <button type="button" aria-label={`Approve reference ${row.ref_id}`} disabled={busy} onClick={() => void approve(row.ref_id)} className="inline-flex items-center gap-1 rounded border border-emerald-300/30 px-2 py-1 text-xs text-emerald-200 disabled:opacity-40"><Check size={12} />Approve</button>}
                    {state === 'candidate' && <button type="button" aria-label={`Reject reference ${row.ref_id}`} disabled={busy} onClick={() => void reject(row.ref_id)} className="inline-flex items-center gap-1 rounded border border-red-300/30 px-2 py-1 text-xs text-red-200 disabled:opacity-40"><X size={12} />Reject</button>}
                    {state === 'approved' && <button type="button" aria-label={`Designate canonical reference ${row.ref_id}`} disabled={busy} onClick={() => void designate(row.ref_id)} className="inline-flex items-center gap-1 rounded border border-amber-200/40 px-2 py-1 text-xs text-amber-100 disabled:opacity-40"><Stamp size={12} />Designate canonical</button>}
                    {state === 'approved' && <button type="button" aria-label={`Reject reference ${row.ref_id}`} disabled={busy} onClick={() => void reject(row.ref_id)} className="inline-flex items-center gap-1 rounded border border-red-300/30 px-2 py-1 text-xs text-red-200 disabled:opacity-40"><X size={12} />Reject</button>}
                    {state === 'canonical' && <><span className="text-[11px] text-amber-100">canonical for this setting</span><button type="button" aria-label={`Reject reference ${row.ref_id}`} disabled={busy} onClick={() => void reject(row.ref_id)} className="inline-flex items-center gap-1 rounded border border-red-300/30 px-2 py-1 text-xs text-red-200 disabled:opacity-40"><X size={12} />Reject</button></>}
                    {state === 'rejected' && <span className="text-[11px] text-red-200">rejected · unavailable for selection</span>}
                  </div>
                </li>
              )
            })}
          </ul>
          <div className="mt-4 space-y-3 border-t border-white/10 pt-3">
            <label className="block text-xs text-zinc-300">Register an image URI as a new candidate
              <input aria-label="Reference image URI" className={inputClass} value={imageUrl} placeholder="https://… or /outputs/…" disabled={busy} onChange={event => setImageUrl(event.target.value)} />
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className={buttonClass} disabled={busy || !imageUrl.trim()} onClick={() => void registerUri()}>Register reference</button>
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-200 disabled:opacity-40">
                Upload image
                <input aria-label="Upload reference image" type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" disabled={busy} ref={fileInputRef} onChange={event => void registerUpload(event.target.files?.[0])} />
              </label>
            </div>
          </div>
        </>
      )}
    </section>
  )
}

export default SettingReferenceAuthorityPanel

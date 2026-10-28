import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, Check, Images, Loader2, RefreshCw, Stamp, Trash2, Upload, Link2, Lock, X } from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import { RoomBackdrop } from '../components/RoomCinematicChrome'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'
import ReferenceImageGenerator, { type GeneratorShot } from '../components/ReferenceImageGenerator'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import { useCharacterLooks } from '../hooks/useCharacterLooks'
import { buildStudioApiUrl, listCharacters, listRenderJobs, listScenes, type CharacterRecord, type RenderJob, type Scene } from '../lib/studioApi'
import {
  addReferenceLibraryAsset,
  approveReferenceLibraryAsset,
  designateReferenceLibraryCanonical,
  getReferenceLibrary,
  listReferenceAssets,
  removeReferenceLibraryAsset,
  uploadReferenceLibraryAsset,
  type ReferenceAsset,
  type ReferenceLibrary,
} from '../lib/visualTrainingApi'
import type { CharacterLook } from '../lib/characterLookApi'
import { referenceCapacityStatus } from '../lib/referenceCapacity'

type LoadState<T> =
  | { status: 'loading' }
  | { status: 'unavailable'; message: string }
  | { status: 'ready'; value: T }

function loadingState<T>(): LoadState<T> { return { status: 'loading' } }
function readyState<T>(value: T): LoadState<T> { return { status: 'ready', value } }
function unavailableState<T>(message: string): LoadState<T> { return { status: 'unavailable', message } }

function errMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message.trim() : fallback
}

function imageSrc(url: string | null | undefined): string | null {
  if (!url || !url.trim()) return null
  const trimmed = url.trim()
  return /^https?:\/\//.test(trimmed) || trimmed.startsWith('data:') ? trimmed : buildStudioApiUrl(trimmed)
}

type TargetKind = 'character' | 'setting'

type WorkspaceTarget = {
  kind: TargetKind
  targetId: string
  label: string
  detail: string
}

function statusLabel(asset: ReferenceAsset): string {
  if (asset.canonical) return 'Locked canonical'
  if (asset.approval_state === 'approved') return 'Approved supporting'
  if (asset.approval_state === 'rejected') return 'Rejected'
  return 'Candidate'
}

function statusTone(asset: ReferenceAsset): string {
  if (asset.canonical) return 'border-amber-200/40 bg-amber-200/5 text-amber-100'
  if (asset.approval_state === 'approved') return 'border-emerald-300/30 bg-emerald-500/10 text-emerald-200'
  if (asset.approval_state === 'rejected') return 'border-zinc-500/30 bg-zinc-500/10 text-zinc-400'
  return 'border-sky-300/30 bg-sky-500/10 text-sky-200'
}

function roleLabel(asset: ReferenceAsset): string {
  const role = (asset.reference_role || '').trim()
  if (role) return role.replace(/_/g, ' ')
  const category = (asset.category || '').trim()
  if (category) return category.replace(/_/g, ' ')
  return asset.kind.replace(/_/g, ' ')
}

function AssetThumb({ asset, size }: { asset: ReferenceAsset; size: 'sm' | 'md' | 'lg' }) {
  const src = imageSrc(asset.image_url)
  const box = size === 'lg' ? 'aspect-[4/3]' : size === 'md' ? 'aspect-square' : 'h-14 w-12'
  if (!src) {
    return (
      <div className={`${box} flex items-center justify-center overflow-hidden rounded bg-black/40 text-zinc-600`}>
        <Images size={18} />
      </div>
    )
  }
  return (
    <div className={`${box} overflow-hidden rounded bg-black/40`}>
      <img src={src} alt={roleLabel(asset)} className="h-full w-full object-cover" loading="lazy" />
    </div>
  )
}

export default function ReferenceSpace() {
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id')
  const { projectId, projectError } = useProjectRouteContext(queryProjectId)
  const query = `?project_id=${encodeURIComponent(projectId || '')}`

  const looks = useCharacterLooks(projectId || '')
  const [characters, setCharacters] = useState<LoadState<CharacterRecord[]>>(loadingState())
  const [assets, setAssets] = useState<LoadState<ReferenceAsset[]>>(loadingState())
  const [scenes, setScenes] = useState<LoadState<Scene[]>>(loadingState())
  const [jobs, setJobs] = useState<LoadState<RenderJob[]>>(loadingState())
  const [library, setLibrary] = useState<LoadState<ReferenceLibrary>>(loadingState())
  const [selected, setSelected] = useState<WorkspaceTarget | null>(null)
  const [compareId, setCompareId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [url, setUrl] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [direction, setDirection] = useState('')
  const [selectedFaceUrl, setSelectedFaceUrl] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const generation = useRef(0)

  const loadBase = useCallback(async () => {
    if (!projectId) return
    const run = ++generation.current
    setCharacters(loadingState())
    setAssets(loadingState())
    setScenes(loadingState())
    setJobs(loadingState())
    setActionError('')
    try {
      const result = await listCharacters(projectId)
      if (generation.current !== run) return
      if (result.error) setCharacters(unavailableState(result.error))
      else setCharacters(readyState(result.characters))
    } catch (error) {
      if (generation.current === run) setCharacters(unavailableState(errMessage(error, 'Character list unavailable')))
    }
    try {
      const response = await listReferenceAssets(projectId)
      if (generation.current !== run) return
      setAssets(readyState(response.reference_assets || []))
    } catch (error) {
      if (generation.current === run) setAssets(unavailableState(errMessage(error, 'Reference registry unavailable')))
    }
    try {
      const response = await listScenes(projectId)
      if (generation.current !== run) return
      setScenes(readyState(response.scenes || []))
    } catch (error) {
      if (generation.current === run) setScenes(unavailableState(errMessage(error, 'Scene list unavailable')))
    }
    try {
      // Shot ids come from recorded render jobs: they are real shots in this
      // project, so a generated still can only bind to a shot that exists.
      const response = await listRenderJobs(projectId)
      if (generation.current !== run) return
      setJobs(readyState(Array.isArray(response) ? response : []))
    } catch (error) {
      if (generation.current === run) setJobs(unavailableState(errMessage(error, 'Shot list unavailable')))
    }
  }, [projectId])

  useEffect(() => {
    generation.current += 1
    setSelected(null)
    setCompareId(null)
    setUrl('')
    setNotice('')
    setDirection('')
    setSelectedFaceUrl(null)
    if (projectId) void loadBase()
  }, [projectId, loadBase])

  const characterRows = useMemo(() => {
    const records = characters.status === 'ready' ? characters.value : []
    const lookById = new Map((looks.looks || []).map((look) => [look.character_id, look]))
    return records.map((record) => ({ record, look: lookById.get(record.id) ?? null }))
  }, [characters, looks.looks])

  const settingTargets = useMemo<WorkspaceTarget[]>(() => {
    if (assets.status !== 'ready') return []
    const seen = new Map<string, number>()
    for (const asset of assets.value) {
      if (asset.target_type !== 'setting' || !asset.target_id) continue
      seen.set(asset.target_id, (seen.get(asset.target_id) || 0) + 1)
    }
    return [...seen.entries()].map(([targetId, count]) => ({
      kind: 'setting' as const,
      targetId,
      label: targetId,
      detail: `${count} registered reference${count === 1 ? '' : 's'}`,
    }))
  }, [assets])

  const characterTargets = useMemo<WorkspaceTarget[]>(() => characterRows.map(({ record, look }) => ({
    kind: 'character' as const,
    targetId: record.id,
    label: record.name || record.id,
    detail: look ? `${look.status} · v${look.version}` : 'no look record',
  })), [characterRows])

  useEffect(() => {
    if (selected || characterTargets.length === 0) return
    setSelected(characterTargets[0])
  }, [characterTargets, selected])

  const loadLibrary = useCallback(async (target: WorkspaceTarget | null) => {
    if (!projectId || !target) return
    setLibrary(loadingState())
    setCompareId(null)
    try {
      const result = await getReferenceLibrary(projectId, target.kind, target.targetId)
      setLibrary(readyState(result))
    } catch (error) {
      setLibrary(unavailableState(errMessage(error, 'Reference library unavailable for this target')))
    }
  }, [projectId])

  useEffect(() => {
    if (selected) void loadLibrary(selected)
    else setLibrary(loadingState())
  }, [selected, loadLibrary])

  const refreshAll = useCallback(async () => {
    setRefreshing(true)
    try {
      await Promise.all([loadBase(), looks.refresh()])
    } finally {
      setRefreshing(false)
    }
    if (selected) await loadLibrary(selected)
  }, [loadBase, looks, selected, loadLibrary])

  const selectedLook: CharacterLook | null = useMemo(() => {
    if (!selected || selected.kind !== 'character') return null
    return (looks.looks || []).find((look) => look.character_id === selected.targetId) ?? null
  }, [selected, looks.looks])

  const lookCandidateSignature = selectedLook ? selectedLook.candidates.map((candidate) => candidate.image_url).join('|') : ''
  const signatureRef = useRef('')
  useEffect(() => {
    // New look candidates (uploads, finished casting portraits) become
    // registry candidates through the read-time creator sync — reload the
    // library when the set grows so review happens in one place.
    if (!selected || !lookCandidateSignature) return
    if (signatureRef.current && lookCandidateSignature.length > signatureRef.current.length && lookCandidateSignature !== signatureRef.current) {
      signatureRef.current = lookCandidateSignature
      void loadLibrary(selected)
      return
    }
    signatureRef.current = lookCandidateSignature
  }, [selected, lookCandidateSignature, loadLibrary])

  const generatorShots = useMemo<GeneratorShot[]>(() => {
    if (jobs.status !== 'ready') return []
    const sceneName = new Map<string, string>()
    if (scenes.status === 'ready') {
      for (const scene of scenes.value) sceneName.set(scene.scene_id, scene.scene_name || scene.scene_id)
    }
    const seen = new Map<string, GeneratorShot>()
    for (const job of jobs.value) {
      const shotId = (job.shot_id || '').trim()
      if (!shotId || seen.has(shotId)) continue
      const sceneId = shotId.split('_shot_')[0]
      seen.set(shotId, { shotId, sceneId, sceneName: sceneName.get(sceneId) || sceneId })
    }
    return [...seen.values()].sort((a, b) => a.sceneId.localeCompare(b.sceneId) || a.shotId.localeCompare(b.shotId))
  }, [jobs, scenes])

  const generatorTarget = selected
    ? { kind: selected.kind, targetId: selected.targetId, label: selected.label }
    : null

  const sceneNameByShot = useMemo(() => {
    const map = new Map<string, string>()
    if (scenes.status === 'ready') {
      for (const scene of scenes.value) {
        const shots = (scene as unknown as { shots?: Array<{ shot_id?: string; shot_number?: number }> }).shots || []
        for (const shot of shots) {
          if (shot.shot_id) map.set(shot.shot_id, scene.scene_name || scene.scene_id)
        }
      }
    }
    return map
  }, [scenes])

  async function runMutation(action: () => Promise<unknown>, successNotice: string) {
    if (!projectId || !selected || busy) return
    setBusy(true)
    setActionError('')
    setNotice('')
    try {
      await action()
      setNotice(successNotice)
      await loadLibrary(selected)
    } catch (error) {
      setActionError(errMessage(error, 'The reference registry rejected this change. Nothing was modified.'))
    } finally {
      setBusy(false)
    }
  }

  function handleUploadFile(file: File) {
    if (!projectId || !selected) return
    const category = selected.kind === 'character' ? 'face' : 'wide'
    void runMutation(
      () => uploadReferenceLibraryAsset(projectId, selected.kind, selected.targetId, file, category),
      'Upload registered as a candidate. It needs explicit approval before use.',
    )
  }

  function handleAddUrl() {
    if (!projectId || !selected || !url.trim()) return
    const trimmed = url.trim()
    setUrl('')
    void runMutation(
      () => addReferenceLibraryAsset(projectId, selected.kind, selected.targetId, {
        ref_id: `ref_${Date.now()}`,
        kind: selected.kind === 'character' ? 'character_full' : 'environment',
        image_url: trimmed,
        category: selected.kind === 'character' ? 'face' : 'wide',
        approval_state: 'candidate',
        source_kind: 'uploaded',
      }),
      'Reference added as a candidate. It needs explicit approval before use.',
    )
  }

  function handleApprove(refId: string) {
    if (!projectId || !selected) return
    void runMutation(
      () => approveReferenceLibraryAsset(projectId, selected.kind, selected.targetId, refId),
      'Candidate approved as supporting evidence. The canonical reference is unchanged.',
    )
  }

  function handleDesignateCanonical(refId: string) {
    if (!projectId || !selected || selected.kind !== 'setting') return
    void runMutation(
      () => designateReferenceLibraryCanonical(projectId, selected.targetId, refId),
      'Designated canonical for this setting. It is now the single canonical environment reference; a competing canonical anchor is cleared.',
    )
  }

  function handleRemove(refId: string, wasCandidate: boolean) {
    if (!projectId || !selected) return
    void runMutation(
      () => removeReferenceLibraryAsset(projectId, selected.kind, selected.targetId, refId),
      wasCandidate ? 'Candidate removed. The canonical reference is unchanged.' : 'Supporting reference removed. The canonical reference is unchanged.',
    )
  }

  function handleApproveLook(look: CharacterLook, faceUrl?: string) {
    const face = (faceUrl || look.face_image_url || '').trim()
    if (!face) {
      setActionError('This look has no saved face image, so it cannot be approved yet.')
      return
    }
    setBusy(true)
    setActionError('')
    setNotice('')
    void looks.approve(look, face, look.body_image_url).then((result) => {
      if (result) {
        setNotice(`${look.name} approved at revision ${result.profile_revision}.`)
        setSelectedFaceUrl(null)
      }      else setActionError('Look approval was rejected — the profile may have changed. Refresh the library and try again. The saved look is unchanged.')
    }).finally(() => setBusy(false))
  }

  function handleGenerateCasting(look: CharacterLook) {
    if (!projectId || busy || looks.busy) return
    setBusy(true)
    setActionError('')
    setNotice('')
    void looks.generate(look, direction.trim()).then((result) => {
      if (result) setNotice(`Casting generation started for ${look.name}. New options appear below as they finish — refresh the library to review them as candidates.`)
      else setActionError('Casting generation was rejected — the profile may have changed or no image provider is configured. The saved look is unchanged.')
    }).finally(() => setBusy(false))
  }

  function handleReviseLook(look: CharacterLook) {
    setBusy(true)
    setActionError('')
    setNotice('')
    void looks.revise(look).then((result) => {
      if (result) setNotice(`${look.name} reopened as a draft revision.`)
      else setActionError('Look revision was rejected. The saved look is unchanged.')
    }).finally(() => setBusy(false))
  }

  const libraryValue = library.status === 'ready' ? library.value : null
  const candidates = libraryValue?.candidates || []
  const supporting = libraryValue?.supporting || []
  const canonical = libraryValue?.canonical || null
  const compareAsset = compareId ? [...candidates, ...supporting].find((asset) => asset.ref_id === compareId) ?? null : null
  // Generation-forwarded references for this target: the locked canonical
  // plus approved supporting evidence. Candidates are not counted — they
  // need explicit approval before use. Descriptive only; nothing is
  // dropped, reordered, or substituted here.
  const capacityUsage = (canonical ? 1 : 0) + supporting.length
  const capacity = referenceCapacityStatus(capacityUsage)
  const totalAssets = assets.status === 'ready' ? assets.value.length : 0
  const looksLoading = looks.loading
  const baseLoading = characters.status === 'loading' || assets.status === 'loading'
  const referenceAccent = getProceduralRoomStyle('reference').tokens.accent

  return (
    <StudioShell title="Reference Space" subtitle="Visual development workshop for canonical film references.">
      <ProjectGuard>
        <RoomBackdrop roomKey="reference" testid="reference-room">
        <main className="mx-auto max-w-6xl space-y-5 px-4 pb-12 pt-4 sm:px-6">
          <header className="border-b border-white/15 pb-5" style={{ borderColor: `${referenceAccent}33` }}>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-[0.18em] text-amber-200/80">Visual development workshop</p>
                <h1 className="mt-1 text-3xl font-medium text-zinc-100">Reference Space</h1>
                <p className="mt-2 max-w-2xl text-sm text-zinc-400">
                  Develop, compare, approve, and reuse the visual references that define the film&apos;s canonical appearance.
                  Uploads and selections never become canonical on their own — approval and locking stay with their authoritative services.
                </p>
              </div>
              <button
                type="button"
                onClick={() => void refreshAll()}
                disabled={!projectId || refreshing}
                aria-busy={refreshing}
                className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-200 transition-colors hover:border-white/30 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {refreshing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                Refresh references
              </button>
            </div>
            <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <div className="border-l-2 border-white/15 pl-4" aria-label="Characters verdict">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Characters</p>
                <p className="mt-1.5 text-lg text-zinc-100">
                  {characters.status === 'ready' ? `${characters.value.length} in project` : characters.status === 'unavailable' ? 'Unavailable' : 'Loading…'}
                </p>
                <p className="mt-1 text-xs leading-snug text-zinc-500">Identity lives in character looks.</p>
              </div>
              <div className="border-l-2 border-white/15 pl-4" aria-label="Locked looks verdict">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Locked looks</p>
                <p className="mt-1.5 text-lg text-zinc-100">
                  {looksLoading ? 'Loading…' : looks.error ? 'Unavailable' : `${looks.looks.filter((look) => look.status === 'locked').length} of ${looks.looks.length} locked`}
                </p>
                <p className="mt-1 text-xs leading-snug text-zinc-500">Approval is explicit, never automatic.</p>
              </div>
              <div className="border-l-2 border-white/15 pl-4" aria-label="Registered references verdict">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Registered references</p>
                <p className="mt-1.5 text-lg text-zinc-100">
                  {assets.status === 'ready' ? `${totalAssets} confirmed` : assets.status === 'unavailable' ? 'Unavailable' : 'Loading…'}
                </p>
                <p className="mt-1 text-xs leading-snug text-zinc-500">Candidates need approval before use.</p>
              </div>
              <div className="border-l-2 border-white/15 pl-4" aria-label="Setting collections verdict">
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-500">Setting collections</p>
                <p className="mt-1.5 text-lg text-zinc-100">
                  {assets.status === 'ready' ? `${settingTargets.length} discovered` : assets.status === 'unavailable' ? 'Unavailable' : 'Loading…'}
                </p>
                <p className="mt-1 text-xs leading-snug text-zinc-500">Grouped from registered records.</p>
              </div>
            </div>
          </header>

          {projectError ? <p role="alert" className="rounded-md border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200">{projectError}</p> : null}
          {actionError ? <p role="alert" className="rounded-md border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200">{actionError}</p> : null}
          {notice && !actionError ? <p role="status" className="rounded-md border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{notice}</p> : null}

          {!projectId && !projectError ? (
            <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">Choose a project to inspect its visual references.</p>
          ) : null}

          {baseLoading ? (
            <p role="status" className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 size={16} className="animate-spin" />Reading reference records…</p>
          ) : null}

          {!projectId ? null : (
            <ReferenceImageGenerator
              projectId={projectId}
              target={generatorTarget}
              shots={generatorShots}
              hasLockedCanonical={Boolean(libraryValue?.canonical)}
              onBound={() => { if (selected) void loadLibrary(selected); void loadBase() }}
            />
          )}

          <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
            <nav aria-label="Reference targets" className="space-y-4">
              <section className="border-t border-white/10 pt-4">
                <h2 className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-200/80">Characters</h2>
                {characters.status === 'unavailable' ? (
                  <p className="mt-2 text-xs text-zinc-500">Character list unavailable: {characters.message}</p>
                ) : characterTargets.length === 0 ? (
                  <p className="mt-2 text-xs text-zinc-500">No characters are registered for this project yet.</p>
                ) : (
                  <ul className="mt-2 space-y-1">
                    {characterTargets.map((target) => (
                      <li key={`character:${target.targetId}`}>
                        <button
                          type="button"
                          onClick={() => setSelected(target)}
                          aria-current={selected?.kind === 'character' && selected.targetId === target.targetId}
                          className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm ${selected?.kind === 'character' && selected.targetId === target.targetId ? 'border-amber-200/40 bg-amber-200/5 text-zinc-100' : 'border-white/10 bg-white/[0.02] text-zinc-300 hover:border-white/25'}`}
                        >
                          <span className="min-w-0 truncate">{target.label}</span>
                          <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-500">{target.detail}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {looks.error ? <p className="mt-2 text-xs text-zinc-500">Look records unavailable: {looks.error}</p> : null}
              </section>

              <section className="border-t border-white/10 pt-4">
                <h2 className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-200/80">Settings &amp; collections</h2>
                {assets.status === 'unavailable' ? (
                  <p className="mt-2 text-xs text-zinc-500">Reference registry unavailable: {assets.message}</p>
                ) : settingTargets.length === 0 ? (
                  <p className="mt-2 text-xs text-zinc-500">No setting collections are registered yet. Uploads to a setting target will create one.</p>
                ) : (
                  <ul className="mt-2 space-y-1">
                    {settingTargets.map((target) => (
                      <li key={`setting:${target.targetId}`}>
                        <button
                          type="button"
                          onClick={() => setSelected(target)}
                          aria-current={selected?.kind === 'setting' && selected.targetId === target.targetId}
                          className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm ${selected?.kind === 'setting' && selected.targetId === target.targetId ? 'border-amber-200/40 bg-amber-200/5 text-zinc-100' : 'border-white/10 bg-white/[0.02] text-zinc-300 hover:border-white/25'}`}
                        >
                          <span className="min-w-0 truncate font-mono text-xs">{target.label}</span>
                          <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-500">{target.detail}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </nav>

            <div className="min-w-0 space-y-5">
              {!selected ? (
                <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">Select a character or setting collection to inspect its references.</p>
              ) : (
                <>
                  {selected.kind === 'character' && selectedLook ? (
                    <section aria-label="Character look record" className="border-t border-white/10 pt-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h2 className="text-sm font-semibold text-zinc-100">{selectedLook.name} · look v{selectedLook.version}</h2>
                          <p className="mt-1 text-xs text-zinc-500">
                            Status: <span className="capitalize text-zinc-300">{selectedLook.status}</span>
                            {' · '}profile revision <span className="font-mono">{selectedLook.profile_revision}</span>
                            {selectedLook.approved_at ? ` · approved ${selectedLook.approved_at}` : ''}
                          </p>
                          {selectedLook.description ? <p className="mt-2 max-w-2xl text-xs leading-relaxed text-zinc-400">{selectedLook.description}</p> : null}
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {selectedLook.status !== 'locked' ? (
                            <button
                              type="button"
                              disabled={busy || looks.busy}
                              onClick={() => handleApproveLook(selectedLook)}
                              className="inline-flex items-center gap-1.5 rounded-md border border-emerald-300/30 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-200 disabled:opacity-50"
                            >
                              <Lock size={13} />Approve look
                            </button>
                          ) : (
                            <button
                              type="button"
                              disabled={busy || looks.busy}
                              onClick={() => handleReviseLook(selectedLook)}
                              className="inline-flex items-center gap-1.5 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-200 disabled:opacity-50"
                            >
                              Reopen as draft
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        {[{ label: 'Face identity', url: selectedLook.face_image_url }, { label: 'Full appearance', url: selectedLook.body_image_url }].map((slot) => {
                          const src = imageSrc(slot.url)
                          return (
                            <div key={slot.label} className="rounded-md border border-white/10 bg-white/[0.02] p-2">
                              <p className="px-1 pb-2 text-[10px] uppercase tracking-[0.14em] text-zinc-500">{slot.label}</p>
                              {src ? <img src={src} alt={`${selectedLook.name} ${slot.label}`} className="aspect-[4/3] w-full rounded object-cover" loading="lazy" /> : <p className="px-1 py-3 text-xs text-zinc-500">No saved image for this slot.</p>}
                            </div>
                          )
                        })}
                      </div>
                      {selectedLook.status !== 'locked' ? (
                        <div className="mt-3 rounded-md border border-white/10 bg-white/[0.02] p-3">
                          <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Casting generation</p>
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <input
                              aria-label="Casting direction"
                              value={direction}
                              onChange={(e) => setDirection(e.target.value)}
                              placeholder="Optional direction, e.g. softer window light"
                              maxLength={1200}
                              disabled={busy || looks.busy}
                              className="min-w-0 flex-1 rounded border border-white/15 bg-black/30 px-2.5 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 disabled:opacity-40"
                            />
                            <button
                              type="button"
                              disabled={busy || looks.busy}
                              onClick={() => handleGenerateCasting(selectedLook)}
                              className="inline-flex items-center gap-1.5 rounded-md border border-amber-200/40 bg-amber-200/10 px-3 py-2 text-xs font-medium text-amber-100 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                              {(busy || looks.busy) ? <Loader2 size={13} className="animate-spin" /> : null}
                              Generate 3 casting options
                            </button>
                          </div>
                          {(selectedLook.casting_generations || []).filter((job) => job.status === 'queued' || job.status === 'running').length > 0 ? (
                            <p role="status" className="mt-2 flex items-center gap-1.5 text-[11px] text-zinc-400"><Loader2 size={12} className="animate-spin" />Generating casting options… they appear below as they finish.</p>
                          ) : null}
                          {(selectedLook.casting_generations || []).filter((job) => job.status === 'failed' || job.status === 'partial').slice(0, 1).map((job) => (
                            <p key={job.id} role="alert" className="mt-2 text-xs text-rose-200">{job.error || 'This casting set could not finish. Finished portraits are saved.'}</p>
                          ))}
                        </div>
                      ) : null}
                      {selectedLook.candidates.length > 0 ? (
                        <div className="mt-3">
                          <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Look candidates ({selectedLook.candidates.length})</p>
                          {selectedLook.status !== 'locked' ? (
                            <p className="mt-1 text-xs text-zinc-500">Select a candidate to approve it as this look&apos;s face identity, or approve the saved face slot.</p>
                          ) : null}
                          <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4">
                            {selectedLook.candidates.map((candidate, index) => {
                              const src = imageSrc(candidate.image_url)
                              const isFace = selectedFaceUrl === candidate.image_url
                              const selectable = selectedLook.status !== 'locked'
                              return (
                                <button
                                  key={`${candidate.image_url}-${index}`}
                                  type="button"
                                  disabled={!selectable || busy || looks.busy}
                                  onClick={() => setSelectedFaceUrl(isFace ? null : candidate.image_url)}
                                  aria-pressed={isFace}
                                  aria-label={`Select candidate ${index + 1} as face identity`}
                                  className={`overflow-hidden rounded border text-left transition-colors disabled:cursor-default ${isFace ? 'border-amber-200 bg-amber-200/10' : 'border-white/10 bg-black/30 hover:border-white/30'}`}
                                >
                                  {src ? <img src={src} alt={`${selectedLook.name} candidate ${index + 1}`} className="aspect-square w-full object-cover" loading="lazy" /> : <div className="flex aspect-square items-center justify-center text-zinc-600"><Images size={16} /></div>}
                                  <p className="truncate px-2 py-1 text-[10px] text-zinc-500">{candidate.role}{candidate.source ? ` · ${candidate.source}` : ''}{candidate.matches_current_profile === false ? ' · stale profile' : ''}</p>
                                </button>
                              )
                            })}
                          </div>
                          {selectedLook.status !== 'locked' && selectedFaceUrl ? (
                            <button
                              type="button"
                              disabled={busy || looks.busy}
                              onClick={() => handleApproveLook(selectedLook, selectedFaceUrl)}
                              className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-emerald-300/30 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-200 disabled:opacity-50"
                            >
                              <Lock size={13} />Approve look with selected face
                            </button>
                          ) : null}
                        </div>
                      ) : null}
                    </section>
                  ) : null}

                  {selected.kind === 'character' && !selectedLook && !looksLoading ? (
                    <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">This character has no look record yet. Looks are authored in the character workflow; this room organises their references once they exist.</p>
                  ) : null}

                  <section aria-label="Reference library" className="border-t border-white/10 pt-5">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <h2 className="text-sm font-semibold text-zinc-100">
                        {selected.kind === 'character' ? 'Character' : 'Setting'} reference library · <span className="font-mono text-xs">{selected.targetId}</span>
                      </h2>
                      {libraryValue ? <span className="text-xs capitalize text-zinc-500">{(libraryValue.coverage || 'not covered').replace(/_/g, ' ')}</span> : null}
                    </div>
                    {libraryValue ? (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span
                          data-testid="reference-capacity-badge"
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${capacity.state === 'over' ? 'border-amber-300/40 bg-amber-400/10 text-amber-100' : 'border-white/15 bg-white/[0.03] text-zinc-300'}`}
                        >
                          {capacity.label}
                        </span>
                        {capacity.state === 'over' ? (
                          <p data-testid="reference-capacity-warning" role="alert" className="text-[11px] leading-relaxed text-amber-200/90">
                            This target holds {capacity.overBy} more approved reference{capacity.overBy === 1 ? '' : 's'} than generation forwards per shot (max {capacity.max}). All references are kept as-is — nothing is dropped or reordered. Generation will refuse over-capacity shots before any work starts; remove or replace supporting references to fit.
                          </p>
                        ) : null}
                      </div>
                    ) : null}

                    {library.status === 'loading' ? (
                      <p role="status" className="mt-3 flex items-center gap-2 text-xs text-zinc-400"><Loader2 size={13} className="animate-spin" />Loading library…</p>
                    ) : library.status === 'unavailable' ? (
                      <p role="alert" className="mt-3 rounded-md border border-rose-400/30 bg-rose-500/10 p-3 text-xs text-rose-200">{library.message}</p>
                    ) : (
                      <>
                        {canonical ? (
                          <div className="mt-3 flex items-center gap-3 rounded border border-amber-200/30 bg-amber-200/5 p-2">
                            <div className="w-16 shrink-0"><AssetThumb asset={canonical} size="sm" /></div>
                            <div className="min-w-0">
                              <p className="text-xs font-medium text-amber-100">Canonical reference · locked</p>
                              <p className="mt-0.5 truncate font-mono text-[10px] text-zinc-500">{canonical.ref_id} · {roleLabel(canonical)}{canonical.lock_status ? ` · lock ${canonical.lock_status}` : ''}{canonical.look_id ? ` · look ${canonical.look_id}` : ''}</p>
                            </div>
                          </div>
                        ) : (
                          <p className="mt-3 text-xs text-zinc-500">No canonical reference is registered for this target yet. Candidates below need explicit approval, and canonical status changes only through an explicit designation — approving a candidate never promotes it, and uploads never become canonical on their own.</p>
                        )}

                        {supporting.length > 0 ? (
                          <div className="mt-4">
                            <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-500">Approved supporting ({supporting.length})</p>
                            <div className="mt-2 grid grid-cols-3 gap-2">
                              {supporting.map((asset) => (
                                <div key={asset.ref_id} className="group relative overflow-hidden rounded border border-white/15 bg-black/30">
                                  <div className="aspect-square"><AssetThumb asset={asset} size="md" /></div>
                                  <p className="truncate px-2 py-1.5 text-[10px] capitalize text-zinc-400">{roleLabel(asset)}{asset.source_kind === 'uploaded' ? ' · upload' : ''}</p>
                                  <button type="button" aria-label={`Remove ${roleLabel(asset)} reference`} disabled={busy} onClick={() => handleRemove(asset.ref_id, false)} className="absolute right-1 top-1 rounded bg-black/70 p-1 text-zinc-200 opacity-0 group-hover:opacity-100 disabled:opacity-40"><Trash2 size={12} /></button>
                                  {selected.kind === 'setting' ? (
                                    <button type="button" aria-label={`Designate canonical reference ${asset.ref_id}`} disabled={busy} onClick={() => handleDesignateCanonical(asset.ref_id)} className="absolute bottom-1 right-1 inline-flex items-center gap-1 rounded border border-amber-200/40 bg-black/70 px-1.5 py-0.5 text-xs text-amber-100 opacity-0 group-hover:opacity-100 disabled:opacity-40"><Stamp size={10} />Canonical</button>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}

                        {candidates.length > 0 ? (
                          <div className="mt-4 rounded border border-sky-300/20 bg-sky-500/5 p-3">
                            <p className="text-xs text-sky-100">Candidates awaiting approval ({candidates.length})</p>
                            <p className="mt-1 text-xs text-zinc-400">Approval makes a candidate supporting evidence. It never replaces the canonical reference.</p>
                            <ul className="mt-2 space-y-2">
                              {candidates.map((asset) => (
                                <li key={asset.ref_id} className="flex items-center justify-between gap-2 rounded border border-white/10 bg-black/30 p-2">
                                  <div className="flex min-w-0 items-center gap-2">
                                    <div className="w-10 shrink-0"><AssetThumb asset={asset} size="sm" /></div>
                                    <div className="min-w-0">
                                      <p className="truncate text-[11px] text-zinc-200">{roleLabel(asset)} · {asset.source_kind === 'uploaded' ? 'upload' : asset.source_kind}</p>
                                      <p className="truncate font-mono text-[10px] text-zinc-500">{asset.ref_id}</p>
                                    </div>
                                  </div>
                                  <div className="flex shrink-0 items-center gap-1">
                                    <button type="button" aria-label={`Compare candidate ${asset.ref_id}`} disabled={busy} onClick={() => setCompareId(compareId === asset.ref_id ? null : asset.ref_id)} className="rounded border border-white/20 px-2 py-1 text-xs text-zinc-200 disabled:opacity-40">Compare</button>
                                    <button type="button" aria-label={`Approve candidate ${asset.ref_id}`} disabled={busy} onClick={() => handleApprove(asset.ref_id)} className="inline-flex items-center gap-1 rounded border border-emerald-300/30 px-2 py-1 text-xs text-emerald-200 disabled:opacity-40"><Check size={11} />Approve</button>
                                    <button type="button" aria-label={`Reject candidate ${asset.ref_id}`} disabled={busy} onClick={() => handleRemove(asset.ref_id, true)} className="rounded border border-rose-300/30 p-1 text-rose-200 disabled:opacity-40" title="Reject candidate"><X size={12} /></button>
                                  </div>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : (
                          <p className="mt-3 text-xs text-zinc-500">No candidates are waiting for this target.</p>
                        )}

                        {compareAsset ? (
                          <div className="mt-4 rounded border border-white/15 bg-white/[0.02] p-3" aria-label="Reference comparison">
                            <p className="text-xs font-semibold text-zinc-200">Comparison · decision aid, not approval</p>
                            <div className="mt-2 grid gap-3 sm:grid-cols-2">
                              <div>
                                <p className="pb-2 text-[10px] uppercase tracking-[0.14em] text-zinc-500">Candidate · {roleLabel(compareAsset)}</p>
                                <AssetThumb asset={compareAsset} size="lg" />
                                <p className="mt-1 truncate font-mono text-[10px] text-zinc-500">{compareAsset.ref_id}</p>
                              </div>
                              <div>
                                <p className="pb-2 text-[10px] uppercase tracking-[0.14em] text-zinc-500">Current canonical reference</p>
                                {canonical ? (
                                  <>
                                    <AssetThumb asset={canonical} size="lg" />
                                    <p className="mt-1 truncate font-mono text-[10px] text-zinc-500">{canonical.ref_id}</p>
                                  </>
                                ) : <p className="py-3 text-xs text-zinc-500">No canonical reference exists for this target — there is nothing to compare against yet.</p>}
                              </div>
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-2">
                              <button type="button" disabled={busy} onClick={() => handleApprove(compareAsset.ref_id)} className="inline-flex items-center gap-1 rounded border border-emerald-300/30 px-2.5 py-1.5 text-xs text-emerald-200 disabled:opacity-40"><Check size={12} />Approve candidate</button>
                              <button type="button" onClick={() => setCompareId(null)} className="rounded border border-white/20 px-2.5 py-1.5 text-xs text-zinc-300">Close comparison</button>
                            </div>
                          </div>
                        ) : null}

                        <div className="mt-4 flex flex-wrap items-center gap-2">
                          <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" data-testid="reference-space-upload-input" onChange={(e) => { const file = e.target.files?.[0]; if (fileInputRef.current) fileInputRef.current.value = ''; if (file) handleUploadFile(file) }} />
                          <button type="button" data-testid="reference-space-upload-button" disabled={busy} onClick={() => fileInputRef.current?.click()} className="inline-flex items-center gap-1 rounded border border-white/20 px-2.5 py-2 text-xs text-zinc-200 disabled:opacity-40"><Upload size={13} />Upload Reference</button>
                          <input aria-label="Reference image URL" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste an image URL" className="min-w-0 flex-1 rounded border border-white/15 bg-black/30 px-2.5 py-2 text-xs text-zinc-200" />
                          <button type="button" aria-label="Add image URL reference" disabled={busy || !url.trim()} onClick={handleAddUrl} className="inline-flex items-center gap-1 rounded border border-white/20 px-2.5 py-2 text-xs text-zinc-200 disabled:opacity-40"><Link2 size={13} />Add Image URL</button>
                        </div>
                      </>
                    )}
                  </section>

                  <section aria-label="Shot provenance" className="border-t border-white/10 pt-5">
                    <h2 className="text-sm font-semibold text-zinc-100">Shot provenance</h2>
                    {library.status !== 'ready' ? (
                      <p className="mt-2 text-xs text-zinc-500">Provenance appears once the library loads.</p>
                    ) : [...(canonical ? [canonical] : []), ...supporting, ...candidates].filter((asset) => asset.source_shot_id).length === 0 ? (
                      <p className="mt-2 text-xs text-zinc-500">None of this target&apos;s references record a source shot. References without a recorded source are shown as-is — no lineage is inferred.</p>
                    ) : (
                      <ul className="mt-2 space-y-1 text-xs text-zinc-400">
                        {[...(canonical ? [canonical] : []), ...supporting, ...candidates].filter((asset) => asset.source_shot_id).map((asset) => (
                          <li key={`prov-${asset.ref_id}`} className="flex flex-wrap items-center gap-x-2">
                            <span className={`rounded border px-1.5 py-0.5 text-[10px] ${statusTone(asset)}`}>{statusLabel(asset)}</span>
                            <span className="font-mono text-[11px]">{asset.ref_id}</span>
                            <span>from shot <span className="font-mono">{asset.source_shot_id}</span>{asset.source_shot_id && sceneNameByShot.get(asset.source_shot_id) ? ` (${sceneNameByShot.get(asset.source_shot_id)})` : ''}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                </>
              )}
            </div>
          </div>

          <section aria-label="All registered references" className="border-t border-white/10 pt-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-zinc-100">All registered references</h2>
              <span className="text-xs text-zinc-500">Project-wide registry · read-only here</span>
            </div>
            {assets.status === 'loading' ? (
              <p role="status" className="mt-2 flex items-center gap-2 text-xs text-zinc-400"><Loader2 size={13} className="animate-spin" />Reading registry…</p>
            ) : assets.status === 'unavailable' ? (
              <p role="alert" className="mt-2 text-xs text-rose-200">Registry unavailable: {assets.message}</p>
            ) : assets.value.length === 0 ? (
              <p className="mt-2 text-xs text-zinc-500">No confirmed references are registered for this project yet. Add a candidate above to begin.</p>
            ) : (
              <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
                {assets.value.slice(0, 30).map((asset) => (
                  <div key={asset.ref_id} className="overflow-hidden rounded border border-white/10 bg-black/30">
                    <div className="aspect-square"><AssetThumb asset={asset} size="md" /></div>
                    <div className="px-2 py-1.5">
                      <p className={`inline-block rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${statusTone(asset)}`}>{statusLabel(asset)}</p>
                      <p className="mt-1 truncate text-[10px] capitalize text-zinc-400">{roleLabel(asset)}</p>
                      <p className="truncate font-mono text-[10px] text-zinc-600">{asset.target_type}/{asset.target_id}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {assets.status === 'ready' && assets.value.length > 30 ? <p className="mt-2 text-[11px] text-zinc-500">Showing 30 of {assets.value.length} registered references.</p> : null}
          </section>

          {selectedLook || libraryValue ? (
            <section aria-label="Version notes" className="border-t border-white/10 pt-5">
              <h2 className="text-sm font-semibold text-zinc-100">Versions &amp; approvals</h2>
              <ul className="mt-2 space-y-1 text-xs text-zinc-400">
                {selectedLook ? <li>Look record: v{selectedLook.version} · profile revision <span className="font-mono">{selectedLook.profile_revision}</span> · status <span className="capitalize">{selectedLook.status}</span>. Approval requires the saved profile revision to match — stale approvals are rejected by the server.</li> : null}
                {libraryValue ? <li>Library: {supporting.length} approved supporting · {candidates.length} awaiting approval{canonical ? ' · canonical reference locked' : ' · no canonical reference yet'}.</li> : null}
                <li>No hidden promotion exists: uploads and selections stay candidates until explicitly approved, and canonical status changes only through the lock workflow.</li>
              </ul>
            </section>
          ) : null}

          {supporting.length === 0 && candidates.length === 0 && !canonical && library.status === 'ready' ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-200/25 bg-amber-200/5 p-3 text-xs text-amber-100">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <p>This target has no references at all — an empty collection, not a failure. Upload a file or paste an image URL above to register the first candidate.</p>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-4 border-t border-white/10 pt-4">
            <Link to={`/studio/production-board${query}`} className="text-sm text-cyan-200">Open scene board</Link>
            <Link to={`/studio/screening-room${query}`} className="text-sm text-cyan-200">Open Screening Room</Link>
            <Link to={`/studio/archive${query}`} className="text-sm text-cyan-200">Open the Vault</Link>
          </div>
          <details className="text-xs text-zinc-500"><summary className="cursor-pointer">Project context</summary><ProjectContextBar roomName="reference space" /></details>
        </main>
        </RoomBackdrop>
      </ProjectGuard>
    </StudioShell>
  )
}

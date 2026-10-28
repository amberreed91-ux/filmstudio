import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowRight,
  Camera,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Film,
  Layers,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
import type { ReactNode } from 'react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import { RoomBackdrop } from '../components/RoomCinematicChrome'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'
import ShotGateChips from '../components/status/ShotGateChips'
import NextActionLine from '../components/status/NextActionLine'
import VerdictStrip from '../components/status/VerdictStrip'
import TechDetailsDrawer, { BlockerList } from '../components/status/TechDetailsDrawer'
import ShotRationaleMotifCard from '../components/status/ShotRationaleMotifCard'
import { findDeskQueueItem, toDeskQueueItems } from '../lib/deskShotInspector'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import { useStudio } from '../context/StudioContext'
import { getShotReferenceConfirmation, recordShotReferenceConfirmation, resolveShotReferenceBinding, type ShotReferenceBinding, type ShotReferenceConfirmation } from '../lib/visualTrainingApi'
import { friendlyRefusalError } from '../lib/sceneMintRefusals'
import { buildDeskConfirmedBindingState } from '../lib/confirmedBindingHandoff'
import { handoffStatusForPipeline, handoffStatusForShot, ROOM_EMPTY_STATES } from '../lib/roomHandoff'
import RoomHandoffBadge from '../components/status/RoomHandoffBadge'
import RoomEmptyState from '../components/status/RoomEmptyState'
import {
  getAssemblyStatus,
  getCurrentFilmCut,
  getLatestProductionAcceptanceSummary,
  getScreeningManifest,
  type AssemblyStatusResponse,
  type FilmCutVersion,
  type ProductionAcceptanceSummary,
  type ScreeningManifest,
} from '../lib/studioApi'

// Read-only board aggregate (one GET per load) lives in lib/deskGate so this
// page exports only its component. Next-action buttons below are plain
// navigation links.
import {
  getDeskGateSummary,
  isWaitingOnCutApproval,
  type DeskGateSummary,
} from '../lib/deskGate'

type LoadState<T> = { status: 'loading' } | { status: 'unavailable'; message: string } | { status: 'loaded'; value: T }

function empty<T>(): LoadState<T> { return { status: 'loading' } }

type DeliveryState =
  | { status: 'loading' }
  | { status: 'waiting'; message: string }
  | { status: 'unavailable'; message: string }
  | { status: 'loaded'; value: AssemblyStatusResponse }

export default function ProductionDesk() {
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const { activeProject } = useStudio()
  const { projectId, projectError } = useProjectRouteContext(queryProjectId)
  const scope = useRef(projectId)
  const [board, setBoard] = useState<LoadState<DeskGateSummary>>(empty())
  const [cut, setCut] = useState<LoadState<FilmCutVersion>>(empty())
  const [delivery, setDelivery] = useState<DeliveryState>({ status: 'loading' })
  const [screening, setScreening] = useState<LoadState<ScreeningManifest>>(empty())
  const [acceptance, setAcceptance] = useState<LoadState<ProductionAcceptanceSummary>>(empty())
  const [refreshing, setRefreshing] = useState(false)
  // Inspector selection. Null means "the first shot on the board", so the
  // side panel always has evidence to report without an extra click.
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null)

  const load = useCallback(async (showSpinner = false) => {
    if (!projectId) return
    const requestedProjectId = projectId
    scope.current = projectId
    if (showSpinner) setRefreshing(true)
    const guarded = <T,>(promise: Promise<T>, set: (state: LoadState<T>) => void, message: string): Promise<T | null> =>
      promise.then((value) => { if (scope.current === requestedProjectId) set({ status: 'loaded', value }); return value })
        .catch((error: unknown) => {
          if (scope.current === requestedProjectId) set({ status: 'unavailable', message: error instanceof Error ? error.message : message })
          return null
        })

    await guarded(
      getDeskGateSummary(projectId),
      setBoard,
      'Scene board unavailable',
    )

    await Promise.all([
      guarded(getCurrentFilmCut(projectId).then((result) => result.film_cut), setCut, 'Film Cut unavailable'),
      getAssemblyStatus(projectId).then((value) => {
        if (scope.current === requestedProjectId) setDelivery({ status: 'loaded', value })
      }).catch((error: unknown) => {
        if (scope.current !== requestedProjectId) return
        const message = error instanceof Error ? error.message : 'Delivery status unavailable'
        if (isWaitingOnCutApproval(message)) {
          setDelivery({ status: 'waiting', message: 'waiting on cut approval' })
        } else {
          setDelivery({ status: 'unavailable', message })
        }
      }),
      guarded(getScreeningManifest(projectId, false), setScreening, 'Screening registration unavailable'),
      guarded(getLatestProductionAcceptanceSummary(projectId).then((result) => result.summary), setAcceptance, 'Acceptance status unavailable'),
    ])
    if (scope.current === requestedProjectId && showSpinner) setRefreshing(false)
  }, [projectId])

  useEffect(() => {
    setBoard(empty()); setCut(empty()); setDelivery({ status: 'loading' })
    setScreening(empty()); setAcceptance(empty()); setSelectedShotId(null)
    void load()
  }, [load])

  const boardScenes = useMemo(() => board.status === 'loaded' ? board.value.scenes : [], [board])
  const readyScenes = useMemo(() => boardScenes.filter((scene) => scene.next_action === 'ready').length, [boardScenes])
  // Board cards become queue items once, so the inspector reads the same
  // rationale and motif tags the card carried instead of re-deriving them.
  const deskQueueItems = useMemo(() => toDeskQueueItems(boardScenes), [boardScenes])
  const activeDeskItem = useMemo(
    () => findDeskQueueItem(deskQueueItems, selectedShotId) ?? deskQueueItems[0] ?? null,
    [deskQueueItems, selectedShotId],
  )

  // The Desk reads the same vocabulary as the rooms that feed it. Shot state,
  // not "next action", separates a stalled render from a scene waiting on the
  // creator. An unreadable board is neutral evidence, never a failing grade.
  const deskShotStatuses = boardScenes.flatMap((scene) =>
    scene.shots.map((shot) => handoffStatusForShot({
      has_media: shot.has_media,
      latest_job_status: shot.latest_job_status,
    })),
  )
  const handoffStatus = board.status === 'unavailable'
    ? 'cant_check' as const
    : board.status === 'loading'
      ? 'making' as const
      : handoffStatusForPipeline({
        sceneCount: board.value.scene_count,
        readyCount: readyScenes,
        makingCount: deskShotStatuses.filter((status) => status === 'making').length,
        attentionCount: deskShotStatuses.filter((status) => status === 'needs_attention').length,
      })
  const accepted = acceptance.status === 'loaded' && acceptance.value.disposition === 'ready_for_creator_approval' && !acceptance.value.stale
  const hasVerifiedFinal = screening.status === 'loaded' && screening.value.current_final_output?.approved === true && acceptance.status === 'loaded' && acceptance.value.package_id === screening.value.current_final_output?.source_id && accepted
  const cutStatus = cut.status === 'loaded' ? cut.value.status : 'unavailable'

  const stages = useMemo(() => {
    const sceneState: 'verified' | 'blocked' | 'unavailable' | 'unverified' =
      board.status === 'unavailable' ? 'unavailable'
        : board.status === 'loaded' && board.value.scene_count === 0 ? 'blocked'
          : readyScenes === boardScenes.length && board.status === 'loaded' && boardScenes.length > 0 ? 'verified' : 'unverified'
    const editorialState: 'verified' | 'blocked' | 'unavailable' | 'unverified' =
      cut.status === 'unavailable' ? 'unavailable' : cutStatus === 'approved' ? 'verified' : 'blocked'
    const deliveryState: 'verified' | 'blocked' | 'stale' | 'unavailable' | 'unverified' =
      delivery.status === 'waiting' ? 'unverified'
        : delivery.status !== 'loaded' ? 'unavailable'
          : delivery.value.film_outdated ? 'stale'
            : delivery.value.film_assembled ? 'verified' : 'blocked'
    const screeningState: 'verified' | 'blocked' | 'unavailable' | 'unverified' =
      screening.status === 'unavailable' ? 'unavailable'
        : hasVerifiedFinal ? 'verified'
          : acceptance.status === 'loaded' && acceptance.value.stale ? 'blocked' : 'unverified'
    const stageDetail = (state: LoadState<unknown> | DeliveryState, loaded: string) =>
      state.status === 'loaded' ? loaded : state.status === 'waiting' ? 'waiting on cut approval' : state.status === 'loading' ? 'Loading…' : 'Unavailable'
    return [
      { key: 'scenes', label: 'Scenes', state: sceneState, detail: board.status === 'loaded' ? `${readyScenes} of ${board.value.scene_count} scenes ready` : stageDetail(board, ''), note: 'Scene cards below carry the detail' },
      { key: 'editorial', label: 'Editorial', state: editorialState, detail: stageDetail(cut, cut.status === 'loaded' ? `Cut v${cut.value.version_number} · ${cut.value.status}` : ''), note: 'Approved Film Cut governs delivery order' },
      { key: 'delivery', label: 'Delivery', state: deliveryState, detail: stageDetail(delivery, delivery.status === 'loaded' ? `${delivery.value.scenes_with_compositions} of ${delivery.value.scenes_total} scenes stitched` : ''), note: 'Scene cards feed the full-film stitch' },
      { key: 'screening', label: 'Screening', state: screeningState, detail: stageDetail(screening, hasVerifiedFinal ? 'Accepted final' : 'No accepted final'), note: 'Watching needs an accepted final' },
    ]
  }, [board, boardScenes.length, readyScenes, cut, cutStatus, delivery, screening, acceptance, hasVerifiedFinal])

  const loading = [board, cut, screening, acceptance].some((state) => state.status === 'loading') || delivery.status === 'loading'

  const [shotInput, setShotInput] = useState('')
  const [binding, setBinding] = useState<ShotReferenceBinding | null>(null)
  const [bindingError, setBindingError] = useState('')
  const [resolving, setResolving] = useState(false)
  const [confirmed, setConfirmed] = useState<{ shot_id: string; digest: string } | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState('')
  // Durable server-side confirmation record (R4.2). Recovered read-only on
  // every resolution so a confirmation survives reloads and navigation;
  // written only by the explicit Confirm action below. Null means no record
  // was recovered — never a confirmation.
  const [serverConfirmation, setServerConfirmation] = useState<ShotReferenceConfirmation | null>(null)

  useEffect(() => {
    setShotInput('')
    setBinding(null)
    setBindingError('')
    setConfirmed(null)
    setConfirmError('')
    setServerConfirmation(null)
  }, [projectId])

  async function resolveBinding() {
    const shotId = shotInput.trim()
    if (!projectId || !shotId || resolving) return
    setResolving(true)
    setBindingError('')
    setBinding(null)
    setServerConfirmation(null)
    try {
      setBinding(await resolveShotReferenceBinding(projectId, shotId))
    } catch (error: unknown) {
      setBindingError(friendlyRefusalError(error, 'Reference resolution failed.'))
    } finally {
      setResolving(false)
    }
    // Read-only recovery of the durable record for this exact project and
    // shot. A lookup failure leaves no recovered state — never a
    // confirmation — and never disturbs the fresh resolution above.
    try {
      setServerConfirmation(await getShotReferenceConfirmation(projectId, shotId))
    } catch {
      setServerConfirmation(null)
    }
  }

  async function confirmBinding() {
    if (!binding || resolving || confirming) return
    setConfirming(true)
    setConfirmError('')
    try {
      // The backend re-verifies the digest against the freshly resolved
      // binding and saves the server-resolved record only on a match.
      const recorded = await recordShotReferenceConfirmation(projectId || '', binding.shot_id, binding.binding_digest)
      setConfirmed({ shot_id: binding.shot_id, digest: binding.binding_digest })
      setServerConfirmation(recorded)
    } catch (error: unknown) {
      // Fail-closed display: a confirmation that could not be saved durably
      // is not shown as confirmed anywhere.
      setConfirmError(friendlyRefusalError(error, 'Confirmation could not be saved.'))
    } finally {
      setConfirming(false)
    }
  }

  const confirmedStale = confirmed !== null && binding !== null
    && (confirmed.shot_id !== binding.shot_id || confirmed.digest !== binding.binding_digest)
  const confirmedCurrent = confirmed !== null && binding !== null && !confirmedStale
  // Server-recovered confirmation: the durable record matches this fresh
  // resolution, so the confirmation survived a reload or navigation. Shown
  // only when the backend itself reports it — never from local memory.
  const serverConfirmedCurrent = serverConfirmation !== null && binding !== null
    && serverConfirmation.status === 'confirmed'
    && serverConfirmation.shot_id === binding.shot_id
    && (serverConfirmation.confirmed_digest || '') === binding.binding_digest
  const serverConfirmationStale = serverConfirmation !== null && binding !== null
    && serverConfirmation.shot_id === binding.shot_id
    && (serverConfirmation.status === 'stale' || serverConfirmation.status === 'unverifiable')

  // Route-state handoff into the generation room: only a confirmation that
  // matches the fresh server resolution travels. A stale or absent
  // confirmation carries nothing, so generation can never mistake it for
  // an explicit confirmation. Previs adopts this once per navigation and
  // attaches it to the real generation request; the server re-verifies.
  const previsHandoffState =
    confirmedCurrent && projectId && confirmed && binding
      ? buildDeskConfirmedBindingState({
        projectId,
        sceneId: binding.scene_id,
        shotId: confirmed.shot_id,
        digest: confirmed.digest,
      })
      : undefined

  const section = (title: string, children: ReactNode, aside?: ReactNode) => (
    <section className="border-t border-white/10 pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-200/80">{title}</h2>
        {aside}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )

  const deskAccent = getProceduralRoomStyle('desk').tokens.accent
  return <StudioShell title="Production Desk" subtitle="What the production has, what it owes, and what is waiting on you.">
    <ProjectGuard>
      <RoomBackdrop roomKey="desk" testid="desk-room">
      <main className="mx-auto max-w-6xl space-y-5 px-4 pb-12 pt-4 sm:px-6">
        <header className="border-b border-white/15 pb-5" style={{ borderColor: `${deskAccent}33` }}>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-violet-300/80">Production control</p>
              <p className="mt-2 text-xs uppercase tracking-[0.15em] text-amber-200/80">{activeProject?.title || projectId || 'No project selected'}</p>
              <h1 className="mt-1 text-3xl font-medium text-zinc-100">Production Desk</h1>
              <p className="mt-2 max-w-2xl text-sm text-zinc-400">Scene cards from the saved board state. This desk reports evidence; it does not approve or change production state.</p>
            </div>
            <button type="button" onClick={() => void load(true)} disabled={!projectId || refreshing} aria-busy={refreshing || undefined} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-200 transition-colors hover:border-white/30 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40">{refreshing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}Refresh evidence</button>
          </div>
          <VerdictStrip stages={stages} />
          <div className="mt-4"><RoomHandoffBadge room="desk" status={handoffStatus} projectId={projectId} /></div>
        </header>

        {projectError && <p role="alert" className="rounded-lg border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100">{projectError}</p>}
        {!projectId && !projectError && <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">Choose a project to inspect its production state.</p>}
        {loading && <p role="status" className="flex items-center gap-2 text-sm text-zinc-400"><Loader2 size={16} className="animate-spin" />Reading saved production state…</p>}

        {section('Scene cards', <>
          {board.status === 'unavailable' && <p role="status" className="mb-3 text-sm text-amber-100">Scene board unavailable: {board.message}</p>}
          {board.status === 'loaded' && board.value.scene_count === 0 && (
            <RoomEmptyState state={ROOM_EMPTY_STATES.desk} icon={Camera} projectId={projectId} testId="desk-empty" />
          )}
          {board.status === 'loaded' && board.value.scene_count > 0 && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
            <div className="grid gap-4 md:grid-cols-2" aria-label="Scene cards">
            {boardScenes.map((scene) => {
              const waiting = scene.next_action !== 'ready'
              return (
              <article key={scene.scene_id} data-testid={`scene-card-${scene.scene_id}`} className={`rounded-lg border border-white/10 bg-white/[0.02] p-4 ${waiting ? 'border-l-4 border-l-amber-300/70' : 'border-l-4 border-l-emerald-300/70'}`}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-sm font-semibold text-zinc-100">{scene.scene_name || scene.scene_id}</h3>
                  <span className="font-mono text-[11px] text-zinc-500">{scene.scene_id}</span>
                </div>
                <p className="mt-1 text-xs text-zinc-500">
                  {scene.board_state === 'missing_board'
                    ? 'No shot plan yet'
                    : `${scene.shot_count || scene.shots.length} shot${(scene.shot_count || scene.shots.length) === 1 ? '' : 's'}`}
                </p>
                {scene.board_state !== 'missing_board' && scene.shots.length > 0 && (
                  <ul className="mt-3 space-y-2" aria-label={`Shots in ${scene.scene_id}`}>
                    {scene.shots.map((shot) => (
                      <li key={shot.shot_id} data-testid={`shot-row-${shot.shot_id}`}>
                        <button
                          type="button"
                          onClick={() => setSelectedShotId(shot.shot_id)}
                          aria-pressed={activeDeskItem?.shotId === shot.shot_id}
                          aria-label={`Inspect ${shot.shot_id}`}
                          data-testid={`shot-select-${shot.shot_id}`}
                          className={`w-full rounded-md border p-2 text-left transition-colors ${activeDeskItem?.shotId === shot.shot_id ? 'border-amber-200/40 bg-amber-200/[0.04]' : 'border-white/10 hover:border-white/25 hover:bg-white/[0.03]'}`}
                        >
                          <span className="block font-mono text-[11px] text-zinc-300">{shot.shot_id}</span>
                          <ShotGateChips shot={shot} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <NextActionLine projectId={projectId || ''} nextAction={scene.next_action} sceneId={scene.scene_id} />
                {scene.blockers.length > 0 && (
                  <TechDetailsDrawer summary="Why is this waiting?">
                    <BlockerList items={scene.blockers} />
                  </TechDetailsDrawer>
                )}
              </article>
              )
            })}
            </div>
            <aside aria-label="Shot inspector" className="space-y-3 xl:sticky xl:top-4 xl:self-start">
              {activeDeskItem ? (
                <ShotRationaleMotifCard item={activeDeskItem} />
              ) : (
                <p className="rounded-lg border border-white/10 p-4 text-xs leading-relaxed text-zinc-500">
                  No shots on this board yet. A shot appears here once its storyboard carries one.
                </p>
              )}
            </aside>
          </div>}
          <div className="mt-4 flex flex-wrap gap-3">
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/production-board?project_id=${encodeURIComponent(projectId || '')}`}>Open scene board <ArrowRight size={14} /></Link>
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/writers-room?project_id=${encodeURIComponent(projectId || '')}`}>Open The Page <ArrowRight size={14} /></Link>
          </div>
        </>)}

        {section('Shot reference binding', <>
          <p className="max-w-2xl text-xs leading-relaxed text-zinc-500">Review the server-resolved references for one shot, in the server&apos;s canonical order, then explicitly confirm them. Resolving and confirming create no render jobs, approve nothing, and invoke no provider. Confirming saves a durable project-scoped record that survives reloads; if references change before submission, the Production Integrity Gate rejects the stale binding.</p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="min-w-0 flex-1 basis-64 text-xs text-zinc-400">Shot ID
              <input
                type="text"
                value={shotInput}
                onChange={(event) => setShotInput(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') void resolveBinding() }}
                placeholder="scene_002_shot_001"
                aria-label="Shot ID"
                className="mt-1 block w-full min-h-10 rounded-md border border-white/15 bg-black/30 px-3 font-mono text-sm text-zinc-100 placeholder:text-zinc-600"
              />
            </label>
            <button
              type="button"
              onClick={() => void resolveBinding()}
              disabled={!projectId || !shotInput.trim() || resolving}
              aria-busy={resolving || undefined}
              className="inline-flex min-h-10 items-center gap-2 rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-200 transition-colors hover:border-white/30 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >{resolving ? <Loader2 size={15} className="animate-spin" /> : null}Resolve binding</button>
          </div>
          {bindingError && <p role="alert" className="mt-3 rounded-md border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200">{bindingError}</p>}
          {binding && <div className="mt-4 rounded-md border border-white/10 bg-white/[0.02] p-3">
            <p className="text-sm text-zinc-100">Settled binding for <span className="font-mono">{binding.shot_id}</span></p>
            <p className="mt-1 font-mono text-[11px] text-zinc-500">project {binding.project_id} · scene {binding.scene_id} · {binding.binding.length} reference{binding.binding.length === 1 ? '' : 's'}</p>
            <p className="mt-1 break-all font-mono text-[11px] text-zinc-500">digest {binding.binding_digest}</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse text-left">
                <caption className="sr-only">Server-resolved references in canonical order.</caption>
                <thead>
                  <tr className="border-b border-white/15 text-[10px] uppercase tracking-[0.16em] text-zinc-500">
                    <th scope="col" className="py-1 pr-3 font-medium">Reference</th>
                    <th scope="col" className="py-1 pr-3 font-medium">Target</th>
                    <th scope="col" className="py-1 pr-3 font-medium">Role</th>
                    <th scope="col" className="py-1 font-medium">Standing</th>
                  </tr>
                </thead>
                <tbody>
                  {binding.binding.map((row) => <tr key={row.ref_id} className="border-t border-white/10 align-top text-xs">
                    <td className="py-2 pr-3 font-mono text-[11px] text-zinc-200">{row.ref_id}</td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-zinc-400">{row.target_type}/{row.target_id}</td>
                    <td className="py-2 pr-3 text-zinc-300">{row.role}{row.category && row.category !== row.role ? ` · ${row.category}` : ''}</td>
                    <td className="py-2 text-zinc-300">{row.canonical && row.approval_state === 'approved' ? 'Approved canonical' : `${row.approval_state}${row.canonical ? ' · canonical' : ''}`}</td>
                  </tr>)}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void confirmBinding()}
                disabled={resolving || confirming}
                aria-busy={confirming || undefined}
                className="inline-flex min-h-10 items-center gap-2 rounded-md border border-emerald-300/30 bg-emerald-500/10 px-4 text-sm font-semibold text-emerald-200 disabled:opacity-50"
              >{confirming ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}Confirm this binding</button>
              {confirmedCurrent && <p role="status" className="text-xs text-emerald-200">Confirmed for {confirmed?.shot_id} · digest {confirmed?.digest.slice(0, 12)}… — saved durably for this project and shot. Open Previs Bay to carry it to generation.</p>}
              {!confirmedCurrent && serverConfirmedCurrent && <p role="status" className="text-xs text-emerald-200">Confirmed for {binding.shot_id} · digest {(serverConfirmation?.confirmed_digest || '').slice(0, 12)}… — recovered from the durable record after reload. Open Previs Bay to carry it to generation.</p>}
              {confirmedStale && <p role="alert" className="text-xs text-amber-200">The confirmed binding differs from this fresh resolution. Review and confirm again before submitting.</p>}
              {!confirmedStale && serverConfirmationStale && <p role="alert" className="text-xs text-amber-200">The durable confirmation no longer matches this fresh resolution. Review and confirm again before submitting.</p>}
              {confirmError && <p role="alert" className="text-xs text-rose-200">Confirmation was not saved: {confirmError}</p>}
            </div>
          </div>}
        </>)}

        {section('Where to go next', <>
          <div className="flex flex-wrap gap-3">
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/screening-room?project_id=${encodeURIComponent(projectId || '')}`}>Open Screening Room <Film size={14} /></Link>
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/vault?project_id=${encodeURIComponent(projectId || '')}`}>Inspect the Vault <Layers size={14} /></Link>
            <Link className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200" to={`/studio/previs?project_id=${encodeURIComponent(projectId || '')}`} state={previsHandoffState}>Open Previs Bay <Camera size={14} /></Link>
          </div>
          {delivery.status === 'waiting' && <p className="mt-3 flex items-start gap-2 text-sm text-amber-100"><Clock3 size={15} className="mt-0.5 shrink-0" />Full-film stitching is waiting on cut approval. Approve the current Film Cut first.</p>}
          {acceptance.status === 'unavailable' && <p role="status" className="mt-3 flex items-center gap-2 text-sm text-amber-100"><ShieldAlert size={15} />Acceptance record unavailable: {acceptance.message}</p>}
          {screening.status === 'unavailable' && <p role="status" className="mt-3 flex items-center gap-2 text-sm text-amber-100"><ShieldAlert size={15} />Screening registration unavailable: {screening.message}</p>}
        </>)}

        <p className="flex items-start gap-2 border-t border-white/10 pt-4 text-xs leading-relaxed text-zinc-500"><CircleHelp size={14} className="mt-0.5 shrink-0" />All readiness here is informational. Approval, ownership, current-output selection, and playback are enforced by their project-scoped backend workflows.</p>
        <details className="text-xs text-zinc-500"><summary className="cursor-pointer">Project context</summary><ProjectContextBar roomName="production desk" /></details>
      </main>
      </RoomBackdrop>
    </ProjectGuard>
  </StudioShell>
}

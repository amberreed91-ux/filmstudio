import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, CircleHelp, Loader2, RefreshCw } from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import { RoomBackdrop } from '../components/RoomCinematicChrome'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'
import ShotGateChips, { type ShotGateInput } from '../components/status/ShotGateChips'
import NextActionLine from '../components/status/NextActionLine'
import VerdictStrip, { type VerdictStage } from '../components/status/VerdictStrip'
import TechDetailsDrawer, { BlockerList } from '../components/status/TechDetailsDrawer'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import { useStudio } from '../context/StudioContext'
import {
  fetchJson,
  getAssemblyStatus,
  getCurrentFilmCut,
  getScreeningManifest,
  type AssemblyStatusResponse,
  type FilmCutVersion,
  type ScreeningManifest,
} from '../lib/studioApi'
import {
  getDeskGateSummary,
  type DeskGateScene,
  type DeskGateShot,
  type DeskGateSummary,
} from './ProductionDesk'

// ── Per-shot integrity gates (one GET per shot, read-only) ──────────────────
// Shape mirrors GET /api/f51/studio/projects/{id}/shots/{shotId}/integrity-gates.
// The Engine only reads these payloads; it never prepares, submits, confirms,
// prices, or cancels anything through them.

export type IntegrityGateState = 'pass' | 'blocked' | 'cant_check' | 'not_yet'

export type IntegrityGate = {
  state: IntegrityGateState
  label: string
  detail: string
}

export type ShotIntegrityGates = {
  project_id: string
  shot_id: string
  scene_id: string
  gates: Record<string, IntegrityGate>
  spend: { estimated_credits: number | null; cost_status?: string | null }
  duplicate: { runway_task_id: string | null }
  binding_digest: string | null
  latest_job_id: string | null
  latest_job_status: string | null
  next_action: string
  blockers: string[]
}

export const INTEGRITY_GATE_ORDER = [
  'image',
  'words',
  'look',
  'settled',
  'contract',
  'preflight',
  'spend',
  'duplicate',
] as const

export async function getShotIntegrityGates(projectId: string, shotId: string): Promise<ShotIntegrityGates> {
  return fetchJson<ShotIntegrityGates>(
    `/api/f51/studio/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/integrity-gates`,
  )
}

/** Map one integrity-gates payload (+ its Desk row) onto the shared five chips. */
export function gatesToChipInput(gates: ShotIntegrityGates | null, row?: DeskGateShot): ShotGateInput {
  const stateOf = (name: string): IntegrityGateState => gates?.gates?.[name]?.state ?? 'not_yet'
  const look = stateOf('look')
  const settled = stateOf('settled')
  return {
    d4_ready: stateOf('image') === 'pass',
    d6_ready: stateOf('words') === 'pass',
    setting_anchor: look === 'pass' ? 'set' : look === 'blocked' ? 'blocked' : 'unknown',
    binding_confirmation:
      settled === 'pass' ? 'confirmed' : settled === 'blocked' ? 'stale' : 'missing',
    has_media: row?.has_media ?? false,
    latest_job_status: row?.latest_job_status ?? gates?.latest_job_status ?? null,
  }
}

type EngineGateNext = { label: string; to: string | null; plain?: string }

/** One plain next step per blocked gate. Links are navigation only. */
export function engineGateNext(
  gateName: string,
  projectId: string,
): EngineGateNext {
  const q = encodeURIComponent(projectId || '')
  const previs = `/studio/previs?project_id=${q}`
  const vault = `/studio/vault?project_id=${q}`
  const desk = `/studio/production-desk?project_id=${q}`
  const board = `/studio/production-board?project_id=${q}`
  switch (gateName) {
    case 'image':
      return { label: 'Open Previs to approve the image prompts', to: previs }
    case 'words':
      return { label: 'Open Previs to approve the send text', to: previs }
    case 'look':
      return { label: 'Open the Vault to settle the setting look', to: vault }
    case 'settled':
      return { label: 'Confirm this binding on the Desk', to: desk }
    case 'contract':
    case 'preflight':
      return { label: 'Prepare the scene in Previs', to: previs }
    case 'spend':
      return {
        label: '',
        to: null,
        plain: 'Wait for a recorded price — this view never prices a shot itself.',
      }
    case 'duplicate':
      return { label: 'Check the scene board before retrying', to: board }
    default:
      return { label: 'Check the scene board', to: board }
  }
}

function blockedGates(gates: ShotIntegrityGates | null): string[] {
  if (!gates) return []
  return INTEGRITY_GATE_ORDER.filter((name) => gates.gates?.[name]?.state === 'blocked')
}

/** A shot is ready only when every gate passes and finished media is saved. */
export function isShotReady(gates: ShotIntegrityGates | null, row?: DeskGateShot): boolean {
  if (!gates) return false
  const allPass = INTEGRITY_GATE_ORDER.every((name) => gates.gates?.[name]?.state === 'pass')
  return allPass && (row?.has_media ?? false)
}

type LoadState<T> = { status: 'loading' } | { status: 'unavailable'; message: string } | { status: 'loaded'; value: T }

function empty<T>(): LoadState<T> {
  return { status: 'loading' }
}

function HonestCostCard({ gates }: { gates: ShotIntegrityGates }) {
  const spend = gates.gates?.spend
  const price = gates.spend?.estimated_credits
  const hasUpstreamTask = Boolean(gates.duplicate?.runway_task_id)
  const jobActive = ['pending', 'queued', 'submitted', 'rendering'].includes(
    String(gates.latest_job_status || '').toLowerCase(),
  )
  if (spend?.state === 'pass' && typeof price === 'number' && price > 0) {
    return (
      <p className="mt-3 text-xs text-zinc-400">
        Runway recorded {price} credits for this shot (recorded estimate, advisory — not a Studio cap).
      </p>
    )
  }
  return (
    <div className="mt-3 rounded-lg border border-dashed border-amber-400/40 p-3 text-[13px] leading-relaxed text-zinc-300">
      <p>
        <span className="font-medium text-amber-200">Price unknown</span>
        {' '}— this shot has no Studio price before it runs.
        {(hasUpstreamTask || jobActive) &&
          ' It cannot be cancelled from Studio once started.'}{' '}
        Running it spends Runway credit.
      </p>
    </div>
  )
}

function ShotCard({
  projectId,
  scene,
  shot,
  gates,
  gatesUnavailable,
}: {
  projectId: string
  scene: DeskGateScene
  shot: DeskGateShot
  gates: ShotIntegrityGates | null
  gatesUnavailable: string | null
}) {
  const blocked = blockedGates(gates)
  const ready = isShotReady(gates, shot)
  return (
    <article
      data-testid={`engine-shot-${shot.shot_id}`}
      className={`rounded-xl border border-white/10 bg-white/[0.02] p-4 ${
        ready ? 'border-l-4 border-l-emerald-300/70' : blocked.length > 0 ? 'border-l-4 border-l-amber-300/70' : ''
      }`}
    >
      <p className="font-mono text-xs text-zinc-300">{shot.shot_id}</p>
      <p className="mt-0.5 text-[11px] text-zinc-500">{scene.scene_name || scene.scene_id}</p>
      <div className="mt-2">
        <ShotGateChips shot={gatesToChipInput(gates, shot)} />
      </div>

      {gatesUnavailable && (
        <p role="status" className="mt-3 text-sm text-zinc-400">
          Shot gates unavailable: {gatesUnavailable}
        </p>
      )}

      {gates && ready && (
        <>
          <p className="mt-3 text-sm text-zinc-100">Ready to screen. Every check passed.</p>
          <p className="mt-1 text-[13px] text-zinc-400">
            Next:{' '}
            <Link className="text-cyan-200" to={`/studio/screening-room?project_id=${encodeURIComponent(projectId || '')}`}>
              Open Screening Room
            </Link>
          </p>
        </>
      )}

      {gates && !ready && blocked.length === 0 && (
        <p className="mt-3 text-sm text-zinc-300">
          {gatesUnavailable ? 'Waiting on shot evidence.' : 'Nothing is blocked. Waiting on the remaining checks.'}
        </p>
      )}

      {gates &&
        blocked.map((name) => {
          const gate = gates.gates[name]
          const next = engineGateNext(name, projectId)
          return (
            <div key={name} className="mt-3">
              <p className="text-sm text-zinc-100">{gate.detail}</p>
              <p className="mt-1 text-[13px] text-zinc-400">
                Next:{' '}
                {next.to ? (
                  <Link className="text-cyan-200" to={next.to}>
                    {next.label}
                  </Link>
                ) : (
                  next.plain
                )}
              </p>
            </div>
          )
        })}

      {gates && <HonestCostCard gates={gates} />}

      {gates && (
        <TechDetailsDrawer summary="Why (technical details)">
          <ul className="space-y-1 text-[12px] text-zinc-400">
            <li>
              <code>image={gates.gates?.image?.state}</code> · <code>words={gates.gates?.words?.state}</code> ·{' '}
              <code>look={gates.gates?.look?.state}</code> · <code>settled={gates.gates?.settled?.state}</code>
            </li>
            <li>
              <code>contract={gates.gates?.contract?.state}</code> ·{' '}
              <code>preflight={gates.gates?.preflight?.state}</code> ·{' '}
              <code>spend={gates.gates?.spend?.state}</code> ·{' '}
              <code>duplicate={gates.gates?.duplicate?.state}</code>
            </li>
            <li>
              binding <code>digest {gates.binding_digest || 'none recorded'}</code>
            </li>
            <li>
              spend <code>cost_status {gates.spend?.cost_status || 'none recorded'}</code>
            </li>
            <li>
              upstream task <code>{gates.duplicate?.runway_task_id || 'none recorded'}</code> · latest job{' '}
              <code>{gates.latest_job_id || 'none'}</code> (<code>{gates.latest_job_status || 'no status'}</code>)
            </li>
            {gates.blockers.length > 0 && (
              <li>
                <BlockerList items={gates.blockers} />
              </li>
            )}
          </ul>
        </TechDetailsDrawer>
      )}
    </article>
  )
}

function EngineEvidence({
  projectId,
  projectTitle,
  projectError,
}: {
  projectId: string
  projectTitle: string
  projectError: string
}) {
  const scope = useRef(projectId)
  const [board, setBoard] = useState<LoadState<DeskGateSummary>>(empty())
  const [gatesByShot, setGatesByShot] = useState<Record<string, LoadState<ShotIntegrityGates>>>({})
  const [cut, setCut] = useState<LoadState<FilmCutVersion>>(empty())
  const [delivery, setDelivery] = useState<LoadState<AssemblyStatusResponse>>(empty())
  const [screening, setScreening] = useState<LoadState<ScreeningManifest>>(empty())
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    if (!projectId) return
    const requestedProjectId = projectId
    scope.current = projectId
    const guarded = <T,>(promise: Promise<T>, set: (state: LoadState<T>) => void, message: string): Promise<T | null> =>
      promise
        .then((value) => {
          if (scope.current === requestedProjectId) set({ status: 'loaded', value })
          return value
        })
        .catch((error: unknown) => {
          if (scope.current === requestedProjectId)
            set({ status: 'unavailable', message: error instanceof Error ? error.message : message })
          return null
        })

    const summary = await guarded(getDeskGateSummary(projectId), setBoard, 'Scene board unavailable')
    const shots = (summary?.scenes ?? []).flatMap((scene) => scene.shots)
    if (shots.length > 0 && scope.current === requestedProjectId) {
      setGatesByShot(Object.fromEntries(shots.map((shot) => [shot.shot_id, empty<ShotIntegrityGates>()])))
      await Promise.all(
        shots.map((shot) =>
          guarded(getShotIntegrityGates(projectId, shot.shot_id), (state) => {
            if (scope.current !== requestedProjectId) return
            setGatesByShot((prev) => ({ ...prev, [shot.shot_id]: state }))
          }, `Shot gates unavailable for ${shot.shot_id}`),
        ),
      )
    }

    await Promise.all([
      guarded(getCurrentFilmCut(projectId).then((result) => result.film_cut), setCut, 'Film Cut unavailable'),
      guarded(getAssemblyStatus(projectId), setDelivery, 'Delivery status unavailable'),
      guarded(getScreeningManifest(projectId, false), setScreening, 'Screening registration unavailable'),
    ])
  }, [projectId])

  useEffect(() => {
    setBoard(empty())
    setGatesByShot({})
    setCut(empty())
    setDelivery(empty())
    setScreening(empty())
    void load()
  }, [load])

  const scenes = board.status === 'loaded' ? board.value.scenes : []
  const allShots = scenes.flatMap((scene) => scene.shots.map((shot) => ({ scene, shot })))
  const readyCount = allShots.filter(({ shot }) => {
    const state = gatesByShot[shot.shot_id]
    return state?.status === 'loaded' && isShotReady(state.value, shot)
  }).length

  const stages: VerdictStage[] = useMemo(() => {
    const cutDetail =
      cut.status === 'loaded'
        ? `Cut v${cut.value.version_number} · ${cut.value.status}`
        : cut.status === 'unavailable'
          ? 'Unavailable'
          : 'Loading…'
    const deliveryDetail =
      delivery.status === 'loaded'
        ? delivery.value.film_assembled
          ? 'Film assembled'
          : 'No stitch yet'
        : delivery.status === 'unavailable'
          ? 'Unavailable'
          : 'Loading…'
    const screeningDetail =
      screening.status === 'loaded'
        ? screening.value.current_final_output?.approved
          ? 'Accepted final'
          : 'No accepted final'
        : screening.status === 'unavailable'
          ? 'Unavailable'
          : 'Loading…'
    return [
      {
        key: 'shots',
        label: 'Shots ready',
        state: board.status === 'loaded' ? 'unverified' : board.status === 'unavailable' ? 'unavailable' : 'unverified',
        detail: board.status === 'loaded' ? `${readyCount} of ${allShots.length} ready` : cutDetail === 'Loading…' ? 'Loading…' : 'Unavailable',
        note: 'One row per shot below carries the detail',
      },
      {
        key: 'cut',
        label: 'Cut',
        state: cut.status === 'loaded' ? (cut.value.status === 'approved' ? 'verified' : 'unverified') : cut.status === 'unavailable' ? 'unavailable' : 'unverified',
        detail: cutDetail,
        note: 'Approved Film Cut governs delivery order',
      },
      {
        key: 'delivery',
        label: 'Delivery',
        state: delivery.status === 'loaded' ? (delivery.value.film_assembled ? 'verified' : 'unverified') : delivery.status === 'unavailable' ? 'unavailable' : 'unverified',
        detail: deliveryDetail,
        note: 'Scene cards feed the full-film stitch',
      },
      {
        key: 'screening',
        label: 'Screening',
        state: screening.status === 'loaded' ? (screening.value.current_final_output?.approved ? 'verified' : 'unverified') : screening.status === 'unavailable' ? 'unavailable' : 'unverified',
        detail: screeningDetail,
        note: 'Watching needs an accepted final',
      },
    ]
  }, [board, readyCount, allShots.length, cut, delivery, screening])

  const loading = board.status === 'loading'
  const integrityAccent = getProceduralRoomStyle('integrity').tokens.accent

  return (
    <StudioShell title="Production Integrity Engine" subtitle="Can this shot move forward?">
      <ProjectGuard>
        <RoomBackdrop roomKey="integrity" testid="integrity-room">
          <main className="mx-auto max-w-6xl space-y-5 px-4 pb-12 pt-4 sm:px-6">
            <header className="border-b border-white/15 pb-5" style={{ borderColor: `${integrityAccent}33` }}>
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-violet-300/80">Verification console</p>
                  <p className="mt-2 text-xs uppercase tracking-[0.15em] text-amber-200/80">
                    {projectTitle}
                  </p>
                  <h1 className="mt-1 text-3xl font-medium text-zinc-100">Can this shot move forward?</h1>
                  <p className="mt-2 max-w-2xl text-sm text-zinc-400">
                    One row per shot. Five plain chips per shot. One reason and one next step when
                    something waits. Numbers and fingerprints live behind “Why”.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setRefreshing(true)
                    void load().finally(() => setRefreshing(false))
                  }}
                  disabled={!projectId || refreshing}
                  className="inline-flex min-h-11 items-center gap-2 rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-200 transition-colors hover:border-white/30 hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {refreshing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                  Refresh evidence
                </button>
              </div>
              <VerdictStrip stages={stages} />
            </header>

            {projectError && (
              <p role="alert" className="rounded-lg border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-100">
                {projectError}
              </p>
            )}
            {!projectId && !projectError && (
              <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">
                Choose a project to inspect its per-shot gates.
              </p>
            )}
            {loading && (
              <p role="status" className="flex items-center gap-2 text-sm text-zinc-400">
                <Loader2 size={16} className="animate-spin" />Reading saved shot gates…
              </p>
            )}

            {board.status === 'unavailable' && (
              <p role="status" className="mb-3 text-sm text-amber-100">
                Scene board unavailable: {board.message}
              </p>
            )}
            {board.status === 'loaded' && board.value.scene_count === 0 && (
              <>
                <p className="text-sm text-zinc-400">
                  No saved scenes yet. Start in The Page, then return here for per-shot gates.
                </p>
                <div className="mt-4 flex flex-wrap gap-3">
                  <Link
                    className="inline-flex min-h-10 items-center gap-1.5 text-sm text-cyan-200"
                    to={`/studio/writers-room?project_id=${encodeURIComponent(projectId || '')}`}
                  >
                    Open The Page <ArrowRight size={14} />
                  </Link>
                </div>
              </>
            )}
            {board.status === 'loaded' && board.value.scene_count > 0 && (
              <div className="grid gap-4 md:grid-cols-2" aria-label="Shot gates">
                {scenes.map((scene) =>
                  scene.board_state === 'missing_board' ? (
                    <article
                      key={scene.scene_id}
                      data-testid={`engine-scene-${scene.scene_id}`}
                      className="rounded-xl border border-white/10 bg-white/[0.02] p-4"
                    >
                      <p className="font-mono text-xs text-zinc-300">{scene.scene_id}</p>
                      <p className="mt-1 text-sm text-zinc-400">
                        No shot plan yet for {scene.scene_name || scene.scene_id}.
                      </p>
                      <NextActionLine projectId={projectId || ''} nextAction="create_board" sceneId={scene.scene_id} />
                    </article>
                  ) : (
                    scene.shots.map((shot) => {
                      const state = gatesByShot[shot.shot_id]
                      return (
                        <ShotCard
                          key={shot.shot_id}
                          projectId={projectId || ''}
                          scene={scene}
                          shot={shot}
                          gates={state?.status === 'loaded' ? state.value : null}
                          gatesUnavailable={state?.status === 'unavailable' ? state.message : null}
                        />
                      )
                    })
                  ),
                )}
              </div>
            )}

            <div className="flex flex-wrap gap-3">
              <Link
                className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200"
                to={`/studio/production-desk?project_id=${encodeURIComponent(projectId || '')}`}
              >
                Open Production Desk <ArrowRight size={14} />
              </Link>
              <Link
                className="inline-flex min-h-10 items-center gap-2 text-sm text-cyan-200"
                to={`/studio/screening-room?project_id=${encodeURIComponent(projectId || '')}`}
              >
                Open Screening Room <ArrowRight size={14} />
              </Link>
            </div>

            <p className="flex items-start gap-2 border-t border-white/10 pt-4 text-xs leading-relaxed text-zinc-500">
              <CircleHelp size={14} className="mt-0.5 shrink-0" />
              Read-only verification: this room reads saved gates and never prepares, submits, confirms,
              prices, or cancels anything.
            </p>
            <details className="text-xs text-zinc-500">
              <summary className="cursor-pointer">Project context</summary>
              <ProjectContextBar roomName="production integrity engine" />
            </details>
          </main>
        </RoomBackdrop>
      </ProjectGuard>
    </StudioShell>
  )
}

/**
 * Route entry point. The gate console is remounted per project so a project
 * switch never mixes one film's records with another's.
 */
export default function ProductionIntegrityEngine() {
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const { activeProject } = useStudio()
  const { projectId, projectError } = useProjectRouteContext(queryProjectId)
  return (
    <EngineEvidence
      key={projectId || 'no-project'}
      projectId={projectId}
      projectTitle={activeProject?.title || projectId || 'No project selected'}
      projectError={projectError}
    />
  )
}

import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import VerdictStrip, { type VerdictStage } from '../components/status/VerdictStrip'
import TechDetailsDrawer from '../components/status/TechDetailsDrawer'
import ShotGateChips from '../components/status/ShotGateChips'
import ReferenceCard from '../components/reference/ReferenceCard'
import GroupRow from '../components/reference/GroupRow'
import { listReferenceBoardAssets, type BoardAsset } from '../lib/referenceBoardApi'

type BoardState =
  | { projectId: string; status: 'needs-project' }
  | { projectId: string; status: 'loading' }
  | { projectId: string; status: 'unavailable'; message: string }
  | { projectId: string; status: 'ready'; assets: BoardAsset[] }

function distinctTargets(assets: BoardAsset[], targetType: 'character' | 'setting'): string[] {
  const seen = new Set<string>()
  for (const asset of assets) {
    if (asset.target_type === targetType && asset.target_id) seen.add(asset.target_id)
  }
  return [...seen]
}

export default function ReferenceBoard() {
  const [searchParams] = useSearchParams()
  const projectId = (searchParams.get('project_id') || '').trim()
  const [rawState, setState] = useState<BoardState>({
    projectId,
    status: projectId ? 'loading' : 'needs-project',
  })
  // Results are tagged with their project, so switching projects reads as
  // loading until the new project's board lands, with no reset effect.
  const state: BoardState = useMemo(
    () => rawState.projectId === projectId
      ? rawState
      : { projectId, status: projectId ? 'loading' : 'needs-project' },
    [rawState, projectId],
  )

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    listReferenceBoardAssets(projectId)
      .then((response) => {
        if (cancelled) return
        setState({ projectId, status: 'ready', assets: response.reference_assets || [] })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message = error instanceof Error && error.message.trim() ? error.message.trim() : 'Reference board unavailable'
        setState({ projectId, status: 'unavailable', message })
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const stages: VerdictStage[] = useMemo(() => {
    if (state.status !== 'ready') return []
    const people = distinctTargets(state.assets, 'character')
    const places = distinctTargets(state.assets, 'setting')
    const settled = state.assets.filter((asset) => asset.canonical && asset.approval_state === 'approved').length
    return [
      {
        key: 'people',
        label: 'People',
        state: people.length > 0 ? 'verified' : 'unavailable',
        detail: `${people.length} in project`,
        note: 'Identity lives in looks.',
      },
      {
        key: 'settled',
        label: 'Settled looks',
        state: settled > 0 ? 'verified' : 'unavailable',
        detail: `${settled} settled`,
        note: 'Chosen by you, locked in.',
      },
      {
        key: 'saved',
        label: 'Saved references',
        state: state.assets.length > 0 ? 'verified' : 'unavailable',
        detail: `${state.assets.length} kept`,
        note: 'Waiting ones need a yes.',
      },
      {
        key: 'places',
        label: 'Places',
        state: places.length > 0 ? 'verified' : 'unavailable',
        detail: `${places.length} found`,
        note: 'Grouped from saved work.',
      },
    ]
  }, [state])

  const people = state.status === 'ready' ? state.assets.filter((a) => a.target_type === 'character') : []
  const places = state.status === 'ready' ? state.assets.filter((a) => a.target_type === 'setting') : []
  const shots = useMemo(() => {
    if (state.status !== 'ready') return [] as Array<{ shotId: string; assets: BoardAsset[] }>
    const byShot = new Map<string, BoardAsset[]>()
    for (const asset of state.assets) {
      if (!asset.source_shot_id) continue
      const list = byShot.get(asset.source_shot_id) || []
      list.push(asset)
      byShot.set(asset.source_shot_id, list)
    }
    return [...byShot.entries()].map(([shotId, assets]) => ({ shotId, assets })).sort((a, b) => a.shotId.localeCompare(b.shotId))
  }, [state])

  return (
    <main className="mx-auto max-w-6xl space-y-4 px-4 pb-12 pt-6">
      <p className="text-[11px] uppercase tracking-[0.18em] text-amber-200/80">Visual development workshop</p>
      <h1 className="mt-1 text-3xl font-medium text-zinc-100">Reference Space</h1>
      <p className="mt-2 max-w-2xl text-sm text-zinc-400">
        Who and where the film remembers. Green means settled. Amber means needs a look. Nothing here sends anything.
      </p>

      {state.status === 'needs-project' ? (
        <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">
          Pick a project to see its references.
        </p>
      ) : null}

      {state.status === 'loading' ? (
        <p role="status" className="text-sm text-zinc-400">
          Reading saved references…
        </p>
      ) : null}

      {state.status === 'unavailable' ? (
        <p role="alert" className="rounded-md border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-200">
          {state.message}
        </p>
      ) : null}

      {state.status === 'ready' ? (
        <>
          <VerdictStrip stages={stages} />
          <TechDetailsDrawer summary="Details">
            <p>Counts: headers count saved rows; the strip counts distinct people and places.</p>
          </TechDetailsDrawer>
          <div className="rounded-lg border border-amber-400/20 bg-amber-500/5 p-3 text-[13px] leading-relaxed text-zinc-300">
            Local files stay local until upload at send time. A “local file” tag means: kept here, not ready to send — it
            must be uploaded when the shot is submitted. Runway is the only sender.
          </div>

          {state.assets.length === 0 ? (
            <p role="status" className="rounded-lg border border-white/10 p-4 text-sm text-zinc-400">
              No saved references yet for this project.
            </p>
          ) : (
            <>
              <GroupRow title="People" count={people.length}>
                {people.length === 0 ? (
                  <p className="text-sm text-zinc-500">No people references saved yet.</p>
                ) : (
                  people.map((asset) => <ReferenceCard key={asset.ref_id} asset={asset} />)
                )}
              </GroupRow>

              <GroupRow title="Places" count={places.length}>
                {places.length === 0 ? (
                  <p className="text-sm text-zinc-500">No place references saved yet.</p>
                ) : (
                  places.map((asset) => <ReferenceCard key={asset.ref_id} asset={asset} />)
                )}
              </GroupRow>

              <section aria-label="Shots" className="mt-6">
                <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200/80">
                  Shots · {shots.length}
                </h2>
                {shots.length === 0 ? (
                  <p className="mt-2 text-sm text-zinc-500">No shot links recorded yet.</p>
                ) : (
                  <div className="mt-2 grid gap-3 sm:grid-cols-2">
                    {shots.map((group) => (
                      <div key={group.shotId} className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
                        <p className="font-mono text-xs text-zinc-200">{group.shotId}</p>
                        <ShotGateChips
                          shot={{
                            d4_ready: group.assets.some((a) => a.approval_state === 'approved'),
                            d6_ready: false,
                            setting_anchor: 'unknown',
                            binding_confirmation: 'missing',
                            has_media: false,
                            latest_job_status: null,
                          }}
                        />
                        <p className="mt-2 text-[13px] text-zinc-300">
                          {group.assets.length} saved {group.assets.length === 1 ? 'reference' : 'references'} linked here.
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </>
      ) : null}
    </main>
  )
}

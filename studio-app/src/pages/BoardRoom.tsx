import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Clapperboard, Film } from 'lucide-react'
import StudioShell from '../components/StudioShell'
import {
  GlassPanel,
  PanoramicHeader,
  RoomBackdrop,
} from '../components/RoomCinematicChrome'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'
import { useStudio } from '../context/StudioContext'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import { listScenes, type Scene } from '../lib/studioApi'

export interface BoardShot {
  shotId: string
  sceneId: string
  sceneName: string
  url?: string
  status: string
}

/** Flatten scene storyboard art (backed by studio.db via the scene API) into a walkable shot wall. */
// eslint-disable-next-line react-refresh/only-export-components
export function buildShotWall(scenes: Scene[]): BoardShot[] {
  const shots: BoardShot[] = []
  for (const scene of scenes) {
    const sceneName = scene.scene_name || scene.heading || scene.scene_id
    const status = scene.status || 'written'
    const images = scene.storyboard_images ?? {}
    const ordered = Object.entries(images).sort(([left], [right]) =>
      left.localeCompare(right, undefined, { numeric: true }),
    )
    for (const [shotId, url] of ordered) {
      shots.push({ shotId, sceneId: scene.scene_id, sceneName, url, status })
    }
    if (scene.storyboard_image?.trim() && !ordered.some(([, url]) => url === scene.storyboard_image)) {
      shots.push({
        shotId: `${scene.scene_id}_board`,
        sceneId: scene.scene_id,
        sceneName,
        url: scene.storyboard_image,
        status,
      })
    }
  }
  return shots
}

export default function BoardRoom() {
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id')
  const { projectId } = useProjectRouteContext(queryProjectId)
  const { activeProject } = useStudio()
  const accent = getProceduralRoomStyle('board').tokens.accent

  const [scenes, setScenes] = useState<Scene[]>([])
  // Load state is keyed by project so switching projects reads as loading
  // without a synchronous reset inside the effect.
  const [loadedProjectId, setLoadedProjectId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<{ projectId: string; message: string } | null>(null)
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    void listScenes(projectId).then((result) => {
      if (cancelled) return
      if (result.error) {
        setLoadError({ projectId, message: result.error })
        setScenes([])
      } else {
        setScenes(result.scenes)
        setLoadError(null)
      }
      setLoadedProjectId(projectId)
    })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const loading = Boolean(projectId) && loadedProjectId !== projectId
  const errorMessage = loadError?.projectId === projectId ? loadError.message : ''

  const shots = useMemo(() => buildShotWall(scenes), [scenes])
  const selectedShot = useMemo(
    () => shots.find((shot) => shot.shotId === selectedShotId) ?? null,
    [shots, selectedShotId],
  )
  const boarded = shots.filter((shot) => shot.url?.trim()).length
  const coverage = shots.length === 0 ? 0 : Math.round((boarded / shots.length) * 100)

  return (
    <StudioShell title="Board" subtitle="Visual storyboarding — the walkable shot wall.">
      <RoomBackdrop roomKey="board" testid="board-room">
        <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 text-zinc-100 sm:px-6 lg:px-8">
          <PanoramicHeader
            eyebrow={`Fee Fee Anne Studios · Board${activeProject?.title ? ` · ${activeProject.title}` : ''}`}
            title="Shot Wall"
            lede="Walk the wall of every boarded shot. Camera metrics ride on each frame; select any shot to open the inspector."
            accent={accent}
          />

          {!projectId ? (
            <GlassPanel accent={accent} testid="board-empty">
              <p className="text-sm leading-6 text-zinc-300">
                No film is on the Board yet. File one through{' '}
                <Link to="/studio/gate" className="underline" style={{ color: accent }}>
                  Gate intake
                </Link>{' '}
                or pick a film in{' '}
                <Link to="/studio" className="underline" style={{ color: accent }}>
                  the Atrium
                </Link>
                .
              </p>
            </GlassPanel>
          ) : loading ? (
            <GlassPanel accent={accent} testid="board-loading">
              <p className="text-sm text-zinc-400">Hanging frames on the wall…</p>
            </GlassPanel>
          ) : errorMessage ? (
            <GlassPanel accent={accent} testid="board-error">
              <p className="text-sm text-rose-200">{errorMessage}</p>
            </GlassPanel>
          ) : (
            <>
              {/* Camera metric strip */}
              <section
                data-testid="board-metrics"
                aria-label="Board coverage metrics"
                className="grid grid-cols-2 gap-3 rounded-2xl border border-white/10 bg-[#0a0d18]/80 p-4 backdrop-blur-md sm:grid-cols-4 sm:p-5"
                style={{ boxShadow: `0 0 28px ${accent}18, 0 18px 55px rgba(0,0,0,0.5)` }}
              >
                {[
                  { label: 'Scenes', value: String(scenes.length) },
                  { label: 'Shots', value: String(shots.length) },
                  { label: 'Boarded frames', value: String(boarded) },
                  { label: 'Wall coverage', value: `${coverage}%` },
                ].map((metric) => (
                  <div key={metric.label} className="text-center">
                    <div
                      className="text-2xl font-bold text-zinc-50"
                      style={{ textShadow: `0 0 18px ${accent}66` }}
                    >
                      {metric.value}
                    </div>
                    <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-zinc-400">
                      {metric.label}
                    </div>
                  </div>
                ))}
              </section>

              <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
                {/* Walkable shot wall gallery */}
                <GlassPanel accent={accent} testid="board-shot-wall" className="p-4">
                  <div className="mb-3 flex items-center gap-2 px-1">
                    <Film size={15} style={{ color: accent }} />
                    <h2 className="text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-200">
                      Shot Wall · {shots.length}
                    </h2>
                  </div>
                  {shots.length === 0 ? (
                    <p className="px-1 py-6 text-center text-sm text-zinc-500">
                      No storyboard frames yet — previs art lands here as soon as shots are boarded.
                    </p>
                  ) : (
                    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {shots.map((shot, index) => {
                        const active = shot.shotId === selectedShotId
                        return (
                          <li key={shot.shotId}>
                            <button
                              type="button"
                              data-testid={`board-shot-${shot.shotId}`}
                              onClick={() => setSelectedShotId(shot.shotId)}
                              className="group w-full overflow-hidden rounded-xl border text-left transition-all duration-150 hover:scale-[1.01]"
                              style={{
                                borderColor: active ? `${accent}88` : 'rgba(255,255,255,0.1)',
                                background: 'rgba(0,0,0,0.5)',
                                boxShadow: active ? `0 0 20px ${accent}44` : 'none',
                              }}
                            >
                              {shot.url ? (
                                <img
                                  src={shot.url}
                                  alt={`Storyboard frame for ${shot.shotId}`}
                                  className="aspect-video w-full object-cover"
                                  loading="lazy"
                                />
                              ) : (
                                <div className="grid aspect-video w-full place-items-center bg-white/[0.03]">
                                  <Clapperboard size={22} className="text-zinc-600" />
                                </div>
                              )}
                              {/* Camera metric overlay */}
                              <div className="flex items-center justify-between gap-2 border-t border-white/10 px-2.5 py-2">
                                <span className="truncate font-mono text-[10px] uppercase tracking-[0.1em] text-zinc-300">
                                  {String(index + 1).padStart(2, '0')}/{String(shots.length).padStart(2, '0')} ·{' '}
                                  {shot.sceneName}
                                </span>
                                <span
                                  className="shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]"
                                  style={{ borderColor: `${accent}55`, color: accent }}
                                >
                                  {shot.status}
                                </span>
                              </div>
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </GlassPanel>

                {/* Shot inspector panel */}
                <aside
                  data-testid="board-inspector"
                  className="h-fit rounded-2xl border border-white/10 bg-[#0a0d18]/85 p-5 backdrop-blur-md"
                  style={{ boxShadow: `0 0 24px ${accent}22, 0 16px 45px rgba(0,0,0,0.5)` }}
                >
                  <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-200">
                    Shot Inspector
                  </h2>
                  {selectedShot ? (
                    <dl className="space-y-2.5 text-xs">
                      {[
                        ['Shot', selectedShot.shotId],
                        ['Scene', selectedShot.sceneName],
                        ['Status', selectedShot.status],
                        ['Frame', selectedShot.url ? 'Boarded' : 'Awaiting art'],
                      ].map(([term, value]) => (
                        <div key={term} className="flex items-start justify-between gap-3">
                          <dt className="shrink-0 uppercase tracking-[0.12em] text-zinc-500">{term}</dt>
                          <dd className="break-all text-right text-zinc-200">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="text-xs leading-5 text-zinc-500">
                      Select any frame on the wall to inspect its scene, status, and board art.
                    </p>
                  )}
                  {projectId && (
                    <Link
                      to={`/studio/previs?project_id=${encodeURIComponent(projectId)}`}
                      className="mt-4 inline-block text-[11px] font-semibold uppercase tracking-[0.14em] underline"
                      style={{ color: accent }}
                    >
                      Open in Previs →
                    </Link>
                  )}
                </aside>
              </div>
            </>
          )}
        </div>
      </RoomBackdrop>
    </StudioShell>
  )
}

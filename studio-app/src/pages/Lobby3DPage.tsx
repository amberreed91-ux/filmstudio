import { Suspense, lazy, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import StudioShell from '../components/StudioShell'
import TacticalHudHeader from '../components/TacticalHudHeader'
import TacticalSideRail from '../components/TacticalSideRail'
import { readPersistedActiveProjectId, withProjectQuery } from '../lib/projectContext'
import { LOBBY_ROOMS } from '../lib/lobbyRooms'

const Interactive3DLobby = lazy(() => import('../components/Interactive3DLobby'))

function LobbyLoading() {
  return (
    <div className="grid h-full min-h-[420px] place-items-center bg-[#040810]">
      <div className="flex flex-col items-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
        <p className="text-sm text-zinc-400">Dimming the house lights...</p>
      </div>
    </div>
  )
}

export default function Lobby3DPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // Query-first so deep links (e.g. ?project_id=proj-001) survive the spatial
  // hop; persisted active project covers arrivals from rooms that drop the
  // query. Reads no reactive context so this page never requires a provider.
  // The persisted read is guarded: sandboxed renderers may stub localStorage.
  function persistedProjectId(): string {
    try {
      return readPersistedActiveProjectId()
    } catch {
      return ''
    }
  }
  const projectId = searchParams.get('project_id')?.trim() || persistedProjectId()
  const [view, setView] = useState<'3d' | '2d'>('3d')

  const go = (to: string) => {
    navigate(withProjectQuery(to, projectId || null))
  }

  return (
    <StudioShell title="3D Studio Lobby" subtitle="An atmospheric spatial hub. Every hotspot routes into the existing 2D rooms.">
      <div className="mx-auto w-full max-w-[1600px] px-4 py-8 sm:px-6 lg:px-8">
        <section className="overflow-hidden rounded-2xl border border-purple-950/60 bg-[#05020a]">
          {/* Slim intro bar — preserves existing room routing controls */}
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-purple-950/60 bg-[#0a0518]/60 px-6 py-5">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-amber-200/90">
                Interactive 3D Lobby
              </p>
              <h1 className="mt-2 text-2xl font-bold tracking-wide text-zinc-100 sm:text-3xl">
                Walk the studio floor
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-6 text-zinc-400">
                The spatial stage is an introductory layer only — selecting a room takes you
                straight into its existing 2D page. Nothing about those rooms changes.
              </p>
              {projectId ? (
                <p data-testid="lobby-3d-project-context" className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-violet-200/80">
                  Active project {projectId} · carried into every room
                </p>
              ) : null}
            </div>
            <div className="flex items-center gap-2" role="group" aria-label="Lobby view mode">
              {view === '3d' ? (
                <button
                  type="button"
                  onClick={() => setView('2d')}
                  className="btn-ghost"
                >
                  Switch to 2D List View
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setView('3d')}
                  className="btn-primary"
                >
                  3D Studio Lobby
                </button>
              )}
              <Link to={withProjectQuery('/studio/lobby', projectId || null)} className="btn-ghost no-underline">
                Back to Home
              </Link>
            </div>
          </div>

          {view === '3d' ? (
            <div data-testid="tactical-split" className="flex min-h-[560px] flex-col bg-[#05020a]">
              <TacticalHudHeader />
              <div className="flex min-h-[560px] flex-1 flex-col overflow-hidden lg:h-[calc(100vh-240px)] lg:flex-row">
                {/* LEFT: interactive 3D soundstage canvas */}
                <div
                  id="canvas-container"
                  className="relative min-h-[560px] flex-1 overflow-hidden bg-gradient-to-b from-[#090314] via-[#05020c] to-[#030107]"
                >
                  <Suspense fallback={<LobbyLoading />}>
                    <Interactive3DLobby onNavigate={go} />
                  </Suspense>
                </div>
                {/* RIGHT: tactical telemetry side-rail */}
                <TacticalSideRail projectId={projectId} />
              </div>
            </div>
          ) : (
            <div className="p-6 sm:p-8">
              <div data-testid="lobby-2d-list" className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {LOBBY_ROOMS.map((room) => (
                  <Link
                    key={room.id}
                    to={withProjectQuery(room.to, projectId || null)}
                    data-testid={`lobby-2d-node-${room.id}`}
                    className="group rounded-xl border border-white/10 bg-black/35 p-4 no-underline transition-all duration-200 hover:border-amber-200/40 hover:bg-black/50"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ background: room.color, boxShadow: `0 0 10px ${room.color}` }}
                      />
                      <div className="text-sm font-semibold text-zinc-100">{room.label}</div>
                    </div>
                    <div className="mt-1 text-xs text-zinc-400">{room.description}</div>
                    <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-zinc-500">
                      {room.to}
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>
    </StudioShell>
  )
}

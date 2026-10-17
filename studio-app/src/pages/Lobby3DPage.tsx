import { Suspense, lazy, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import StudioShell from '../components/StudioShell'
import { LOBBY_ROOMS } from '../components/Interactive3DLobby'

const Interactive3DLobby = lazy(() => import('../components/Interactive3DLobby'))

function LobbyLoading() {
  return (
    <div className="grid h-[560px] min-h-[420px] place-items-center rounded-2xl border border-white/10 bg-[#040810]">
      <div className="flex flex-col items-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
        <p className="text-sm text-zinc-400">Dimming the house lights...</p>
      </div>
    </div>
  )
}

export default function Lobby3DPage() {
  const navigate = useNavigate()
  const [view, setView] = useState<'3d' | '2d'>('3d')

  const go = (to: string) => {
    navigate(to)
  }

  return (
    <StudioShell title="3D Studio Lobby" subtitle="An atmospheric spatial hub. Every hotspot routes into the existing 2D rooms.">
      <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <section className="cinematic-panel p-6 sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
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
              <Link to="/studio/lobby" className="btn-ghost no-underline">
                Back to Home
              </Link>
            </div>
          </div>

          <div className="mt-6">
            {view === '3d' ? (
              <Suspense fallback={<LobbyLoading />}>
                <Interactive3DLobby onNavigate={go} />
              </Suspense>
            ) : (
              <div data-testid="lobby-2d-list" className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {LOBBY_ROOMS.map((room) => (
                  <Link
                    key={room.id}
                    to={room.to}
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
            )}
          </div>
        </section>
      </div>
    </StudioShell>
  )
}

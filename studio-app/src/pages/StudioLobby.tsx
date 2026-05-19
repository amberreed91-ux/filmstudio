import StudioShell from '../components/StudioShell'
import RenderActivityPanel from '../components/RenderActivityPanel'
import OneButtonShortFilmPanel from '../components/OneButtonShortFilmPanel'
import ProductionTimeline, { type ProductionStage } from '../components/ProductionTimeline'
import { lazyLoad } from '../components/LazyLoad'
import { Link } from 'react-router-dom'
import { useMemo, useEffect, useState } from 'react'

// Lazy load AICrewPresence to improve initial load performance
const LazyAICrewPresence = lazyLoad(
  () => import('../components/AICrewPresence'),
  <div className="animate-pulse bg-zinc-800/50 h-24 rounded-lg mb-4" />
)

// Cache localStorage access to avoid repeated reads
const getLocalStorageState = () => {
  const hasScript = localStorage.getItem('studio_script_exists') === '1'
  const hasScenes = localStorage.getItem('studio_scenes_generated') === '1'
  const hasApproved = localStorage.getItem('studio_approved_scenes') === '1'
  
  let approvedSceneMap: Record<string, boolean> = {}
  try {
    const raw = localStorage.getItem('studio_approved_scene_map')
    if (raw) {
      const parsed = JSON.parse(raw)
      approvedSceneMap = parsed && typeof parsed === 'object' ? (parsed as Record<string, boolean>) : {}
    }
  } catch {
    // Use empty object on parse error
  }
  
  return { hasScript, hasScenes, hasApproved, approvedSceneMap }
}

export default function StudioLobby() {
  const [localState, setLocalState] = useState(() => getLocalStorageState())
  
  // Update local state when localStorage changes (minimal re-renders)
  useEffect(() => {
    const handleStorageChange = () => {
      setLocalState(getLocalStorageState())
    }
    
    // Listen for storage changes from other tabs
    window.addEventListener('storage', handleStorageChange)
    
    // Also check periodically for local changes (throttled)
    const interval = setInterval(handleStorageChange, 5000)
    
    return () => {
      window.removeEventListener('storage', handleStorageChange)
      clearInterval(interval)
    }
  }, [getLocalStorageState])
  
  const { hasScript, hasScenes, hasApproved, approvedSceneMap } = localState
  
  // Memoize expensive computations
  const approvedCount = useMemo(() => 
    Object.values(approvedSceneMap).filter(Boolean).length,
    [approvedSceneMap]
  )
  
  const currentCut = useMemo(() => 
    hasApproved ? 'iteration-ready' : hasScenes ? 'draft cut' : 'none',
    [hasApproved, hasScenes]
  )
  
  const archiveSnapshots = useMemo(() => 
    hasScenes ? 3 : 0,
    [hasScenes]
  )
  
  const timelineRows = useMemo(() => {
    const rows: Array<{ sceneId: string; currentStage: ProductionStage; isRendering?: boolean }> = []
    try {
      const bundleRaw = localStorage.getItem('studio:lastBundle')
      if (bundleRaw) {
        const bundle = JSON.parse(bundleRaw) as { scenes?: Array<{ scene_id?: string }> }
        const sceneIds = Array.isArray(bundle?.scenes) ? bundle.scenes.map((s) => String(s?.scene_id || '').trim()).filter(Boolean) : []
        for (const sceneId of sceneIds.slice(0, 6)) {
          const currentStage: ProductionStage = approvedSceneMap[sceneId]
            ? 'archive'
            : hasScenes
              ? 'review'
              : hasScript
                ? 'previs'
                : 'script'
          rows.push({ sceneId, currentStage, isRendering: false })
        }
      }
    } catch {
      // fallback to synthetic rows
    }
    if (rows.length > 0) return rows
    return [
      { sceneId: 'scene_001', currentStage: hasApproved ? 'archive' : hasScenes ? 'review' : hasScript ? 'previs' : 'script', isRendering: false },
      { sceneId: 'scene_002', currentStage: hasApproved ? 'edit' : hasScenes ? 'generation' : hasScript ? 'previs' : 'script', isRendering: false },
    ] as Array<{ sceneId: string; currentStage: ProductionStage; isRendering?: boolean }>
  }, [hasScript, hasScenes, hasApproved, approvedSceneMap])

  return (
    <StudioShell title="Studio Lobby" subtitle="Central room for navigating writing, previs, production, screening, and archive workflows.">
      <div className="w-full overflow-visible bg-background">
        <RenderActivityPanel roomName="Lobby" />
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-5 space-y-5 text-zinc-100">
          <section className="studio-surface studio-fade-in p-5">
            <h2 className="text-2xl font-semibold tracking-wide text-zinc-100">Studio Lobby</h2>
            <p className="mt-2 text-sm text-zinc-300">Home base for your film creation workflow from script to final cut.</p>
          </section>

          <section className="studio-surface studio-fade-in p-4">
            <div className="text-xs uppercase tracking-[0.14em] text-cyan-200">Start Here</div>
            <div className="mt-1 text-sm text-zinc-100">Begin in Writer&apos;s Room</div>
            <Link to="/studio/writers-room" className="mt-3 inline-flex rounded-lg border border-cyan-300/45 bg-cyan-500/16 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100 no-underline">
              Open Writer&apos;s Room
            </Link>
          </section>

          <OneButtonShortFilmPanel />
          <section className="studio-surface studio-fade-in p-4">
            <div className="text-xs uppercase tracking-[0.14em] text-amber-200">Current Workflow</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {[
                { label: 'Script', done: hasScript },
                { label: 'Previs', done: hasScenes },
                { label: 'Review', done: hasScenes },
                { label: 'Cut', done: hasApproved },
                { label: 'Archive', done: hasScenes },
              ].map((step) => (
                <span
                  key={step.label}
                  className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${
                    step.done ? 'border-emerald-400/55 bg-emerald-500/14 text-emerald-200' : 'border-zinc-600/60 bg-zinc-800/40 text-zinc-400'
                  }`}
                >
                  {step.label}
                </span>
              ))}
            </div>
          </section>

          <section className="studio-surface studio-fade-in p-4">
            <div className="text-xs uppercase tracking-[0.14em] text-zinc-300">Recent Studio State</div>
            <div className="mt-3 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">Scenes Generated: <span className="text-zinc-100">{hasScenes ? 'yes' : 'no'}</span></div>
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">Approved Scenes: <span className="text-zinc-100">{approvedCount}</span></div>
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">Current Cut: <span className="text-zinc-100">{currentCut}</span></div>
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">Archive Snapshots: <span className="text-zinc-100">{archiveSnapshots}</span></div>
            </div>
            {!hasScript && !hasScenes ? (
              <div className="mt-3 space-y-2">
                <div className="studio-skeleton h-2 w-full" />
                <div className="studio-skeleton h-2 w-4/5" />
              </div>
            ) : null}
          </section>

          <section className="studio-surface studio-fade-in p-4">
            <ProductionTimeline title="Lobby Pipeline Overview" scenes={timelineRows} />
          </section>

          <section className="studio-surface studio-fade-in p-4">
            <div className="text-xs uppercase tracking-[0.14em] text-zinc-300">Room Directory</div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {[
                { title: "Writer's Room", desc: 'Draft and process your script.', to: '/studio/writers-room' },
                { title: 'Previs Room', desc: 'Review scenes, visuals, and suggestions.', to: '/studio/previs' },
                { title: 'Production Board', desc: 'Track scene readiness and blockers.', to: '/studio/production-board' },
                { title: 'Screening Room', desc: 'Play and evaluate the current cut.', to: '/studio/screening-room' },
                { title: 'Archive', desc: 'Review snapshots and version history.', to: '/studio/archive' },
              ].map((room) => (
                <div key={room.title} className="studio-surface-muted p-3 transition-all duration-200 hover:border-amber-300/35 hover:bg-black/45">
                  <div className="text-sm font-semibold text-zinc-100">{room.title}</div>
                  <div className="mt-1 text-xs text-zinc-300">{room.desc}</div>
                  <Link to={room.to} className="mt-3 inline-flex rounded-md border border-amber-300/35 bg-amber-500/12 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-100 no-underline">
                    Open Room
                  </Link>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
      <LazyAICrewPresence />
    </StudioShell>
  )
}

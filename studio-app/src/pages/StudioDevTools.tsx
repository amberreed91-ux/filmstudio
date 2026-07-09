import { useEffect, useMemo, useState } from 'react'
import StudioShell from '../components/StudioShell'
import SandboxShortFilmPanel from '../components/SandboxShortFilmPanel'
import RenderActivityPanel from '../components/RenderActivityPanel'
import { lazyLoad } from '../components/LazyLoad'
import { useStudio } from '../context/StudioContext'

const LazyAICrewPresence = lazyLoad(
  () => import('../components/AICrewPresence'),
  <div className="animate-pulse bg-zinc-800/50 h-24 rounded-lg mb-4" />,
)
import { isStudioDevMode } from '../lib/devMode'
import {
  analyzeProjectContinuity,
  buildProjectStyleSignature,
  compareStyleSignatures,
  type ContinuityIssue,
  type DirectorCommentary,
  type SceneMemory,
  type ShotBoundary,
  type StyleSignature,
  type VideoAsset,
  type VideoKeyframe,
  detectVideoAssetShots,
  extractVideoAssetKeyframes,
  generateDirectorCommentary,
  ingestVideoAssetSceneMemory,
  listDirectorCommentary,
  listFinalShortFilmPackagesForProject,
  listProjectContinuityIssues,
  listProjectStyleSignatures,
  listVideoAssetKeyframes,
  listVideoAssetSceneMemory,
  listVideoAssetShots,
  listVideoAssetsForProject,
  registerFrameAnalysis,
  relatedSceneMemories,
  registerVideoAsset,
  searchScenesByMood,
  searchScenesByVisualStyle,
  searchSimilarScenes,
  searchSceneMemories,
  retrieveProjectStylePatterns,
  getRenderDiagnostics,
  type RenderDiagnostics,
  type SimilarSceneResult,
} from '../lib/studioApi'

export default function StudioDevTools() {
  const { project, loading, error, renderJobs, pollingJobs, providers, selectedRenderProvider } = useStudio()
  const [assets, setAssets] = useState<VideoAsset[]>([])
  const [assetError, setAssetError] = useState('')
  const [registerMessage, setRegisterMessage] = useState('')
  const [keyframesByAsset, setKeyframesByAsset] = useState<Record<string, VideoKeyframe[]>>({})
  const [shotsByAsset, setShotsByAsset] = useState<Record<string, ShotBoundary[]>>({})
  const [memoriesByAsset, setMemoriesByAsset] = useState<Record<string, SceneMemory[]>>({})
  const [relatedByMemory, setRelatedByMemory] = useState<Record<string, SceneMemory[]>>({})
  const [extractingAssetId, setExtractingAssetId] = useState('')
  const [detectingAssetId, setDetectingAssetId] = useState('')
  const [ingestingAssetId, setIngestingAssetId] = useState('')
  const [activeTabByAsset, setActiveTabByAsset] = useState<Record<string, 'timeline' | 'keyframes' | 'memory' | 'commentary'>>({})
  const [memoryQuery, setMemoryQuery] = useState('')
  const [memorySearchResults, setMemorySearchResults] = useState<SceneMemory[]>([])
  const [continuityIssues, setContinuityIssues] = useState<ContinuityIssue[]>([])
  const [continuityNotes, setContinuityNotes] = useState<string[]>([])
  const [continuityLoading, setContinuityLoading] = useState(false)
  const [commentaryByAsset, setCommentaryByAsset] = useState<Record<string, DirectorCommentary[]>>({})
  const [commentaryLoadingAssetId, setCommentaryLoadingAssetId] = useState('')
  const [similarResults, setSimilarResults] = useState<SimilarSceneResult[]>([])
  const [moodResults, setMoodResults] = useState<SceneMemory[]>([])
  const [styleResults, setStyleResults] = useState<SceneMemory[]>([])
  const [styleSignatures, setStyleSignatures] = useState<StyleSignature[]>([])
  const [stylePatternSummary, setStylePatternSummary] = useState<{
    project_id: string
    signature_count: number
    latest_signature: StyleSignature | null
    advisory_only: boolean
    auto_regeneration_triggered: boolean
  } | null>(null)
  const [styleComparison, setStyleComparison] = useState<{
    overall_similarity: number
    breakdown: {
      framing: number
      pacing: number
      color: number
      camera_movement: number
    }
    advisory_only: boolean
    auto_regeneration_triggered: boolean
  } | null>(null)
  const [styleLearningLoading, setStyleLearningLoading] = useState(false)
  const [diagnostics, setDiagnostics] = useState<RenderDiagnostics | null>(null)
  const [diagnosticsError, setDiagnosticsError] = useState('')
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false)
  const [debugPanelOpen, setDebugPanelOpen] = useState(true)
  const [autoRefreshDiagnostics, setAutoRefreshDiagnostics] = useState(false)
  const [showVerbosePayloads, setShowVerbosePayloads] = useState(false)
  const [lastUiError, setLastUiError] = useState('')
  const [similarMemoryId, setSimilarMemoryId] = useState('')
  const [moodQuery, setMoodQuery] = useState('')
  const [styleQuery, setStyleQuery] = useState('')
  const projectId = useMemo(() => project?.project_id || localStorage.getItem('studio:activeProjectId') || '', [project?.project_id])
  const devModeEnabled = isStudioDevMode()
  const isProduction = import.meta.env.PROD

  async function loadAssets() {
    if (!projectId) return
    setAssetError('')
    try {
      const result = await listVideoAssetsForProject(projectId)
      setAssets(result.assets || [])
    } catch (err) {
      setAssetError(err instanceof Error ? err.message : 'Failed to load video assets')
      setLastUiError(err instanceof Error ? err.message : 'Failed to load assets')
    }
  }

  async function loadDiagnostics() {
    if (!projectId) return
    setDiagnosticsLoading(true)
    setDiagnosticsError('')
    try {
      const result = await getRenderDiagnostics(projectId)
      setDiagnostics(result)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load diagnostics'
      setDiagnosticsError(message)
      setLastUiError(message)
    } finally {
      setDiagnosticsLoading(false)
    }
  }

  async function loadKeyframes(assetId: string) {
    try {
      const result = await listVideoAssetKeyframes(assetId)
      setKeyframesByAsset((prev) => ({ ...prev, [assetId]: result.keyframes || [] }))
    } catch {
      setKeyframesByAsset((prev) => ({ ...prev, [assetId]: [] }))
    }
  }

  async function loadShots(assetId: string) {
    try {
      const result = await listVideoAssetShots(assetId)
      setShotsByAsset((prev) => ({ ...prev, [assetId]: result.shots || [] }))
    } catch {
      setShotsByAsset((prev) => ({ ...prev, [assetId]: [] }))
    }
  }

  async function loadMemories(assetId: string) {
    try {
      const result = await listVideoAssetSceneMemory(assetId)
      setMemoriesByAsset((prev) => ({ ...prev, [assetId]: result.memories || [] }))
    } catch {
      setMemoriesByAsset((prev) => ({ ...prev, [assetId]: [] }))
    }
  }

  async function loadCommentary(assetId: string) {
    try {
      const result = await listDirectorCommentary(assetId)
      setCommentaryByAsset((prev) => ({ ...prev, [assetId]: result.commentary || [] }))
    } catch {
      setCommentaryByAsset((prev) => ({ ...prev, [assetId]: [] }))
    }
  }

  async function extractKeyframes(assetId: string, overwrite = false) {
    setExtractingAssetId(assetId)
    setRegisterMessage('')
    try {
      const result = await extractVideoAssetKeyframes(assetId, {
        interval_seconds: 5,
        max_frames: 20,
        overwrite,
        extraction_reason: 'interval',
      })
      setKeyframesByAsset((prev) => ({ ...prev, [assetId]: result.keyframes || [] }))
      setRegisterMessage(`Extracted ${result.keyframes?.length || 0} keyframes for ${assetId}`)
    } catch (err) {
      setRegisterMessage(err instanceof Error ? err.message : 'Failed to extract keyframes')
    } finally {
      setExtractingAssetId('')
    }
  }

  async function detectShots(assetId: string, overwrite = true) {
    setDetectingAssetId(assetId)
    setRegisterMessage('')
    try {
      const result = await detectVideoAssetShots(assetId, {
        threshold: 0.3,
        overwrite,
        generate_representative_frames: false,
      })
      setShotsByAsset((prev) => ({ ...prev, [assetId]: result.shots || [] }))
      setRegisterMessage(`Detected ${result.shots?.length || 0} shots for ${assetId}`)
    } catch (err) {
      setRegisterMessage(err instanceof Error ? err.message : 'Failed to detect shots')
    } finally {
      setDetectingAssetId('')
    }
  }

  async function ingestMemory(assetId: string) {
    setIngestingAssetId(assetId)
    setRegisterMessage('')
    try {
      const shotCount = shotsByAsset[assetId]?.length || 0
      const payload = {
        dominant_mood: shotCount > 4 ? 'dynamic' : 'contemplative',
        visual_style: 'cinematic',
        lighting_style: 'mixed contrast',
        pacing_profile: shotCount > 4 ? 'fast-cut' : 'measured',
        character_presence: ['advisory_inference'],
        composition_patterns: ['rule-of-thirds', 'shot-driven rhythm'],
        cinematic_notes: `Advisory-only scene memory generated from detected shots (${shotCount}).`,
      }
      await ingestVideoAssetSceneMemory(assetId, payload)
      await loadMemories(assetId)
      setRegisterMessage(`Scene memory ingested for ${assetId}`)
    } catch (err) {
      setRegisterMessage(err instanceof Error ? err.message : 'Failed to ingest scene memory')
    } finally {
      setIngestingAssetId('')
    }
  }

  async function runMemorySearch() {
    try {
      const result = await searchSceneMemories(memoryQuery, 20)
      setMemorySearchResults(result.memories || [])
    } catch {
      setMemorySearchResults([])
    }
  }

  async function loadRelated(memoryId: string) {
    try {
      const result = await relatedSceneMemories(memoryId, 5)
      setRelatedByMemory((prev) => ({ ...prev, [memoryId]: result.memories || [] }))
    } catch {
      setRelatedByMemory((prev) => ({ ...prev, [memoryId]: [] }))
    }
  }

  async function loadContinuityIssues() {
    if (!projectId) return
    try {
      const result = await listProjectContinuityIssues(projectId)
      setContinuityIssues(result.issues || [])
    } catch {
      setContinuityIssues([])
    }
  }

  async function loadStyleDNA() {
    if (!projectId) return
    try {
      const [signaturesResult, patternsResult] = await Promise.all([
        listProjectStyleSignatures(projectId),
        retrieveProjectStylePatterns(projectId),
      ])
      setStyleSignatures(signaturesResult.signatures || [])
      setStylePatternSummary(patternsResult)
    } catch {
      setStyleSignatures([])
      setStylePatternSummary(null)
    }
  }

  async function buildStyleSignature() {
    if (!projectId) return
    setStyleLearningLoading(true)
    setRegisterMessage('')
    try {
      const result = await buildProjectStyleSignature(projectId)
      setRegisterMessage(`Style signature built: ${result.signature.signature_id}`)
      await loadStyleDNA()
    } catch (err) {
      setRegisterMessage(err instanceof Error ? err.message : 'Failed to build style signature')
    } finally {
      setStyleLearningLoading(false)
    }
  }

  async function compareLatestSignatures() {
    if (styleSignatures.length < 2) {
      setStyleComparison(null)
      setRegisterMessage('Need at least two style signatures to compare.')
      return
    }
    try {
      const result = await compareStyleSignatures(styleSignatures[0].signature_id, styleSignatures[1].signature_id)
      setStyleComparison(result)
    } catch (err) {
      setStyleComparison(null)
      setRegisterMessage(err instanceof Error ? err.message : 'Failed to compare style signatures')
    }
  }

  async function analyzeContinuity() {
    if (!projectId) return
    setContinuityLoading(true)
    setRegisterMessage('')
    try {
      const result = await analyzeProjectContinuity(projectId, true)
      setContinuityIssues(result.issues || [])
      setContinuityNotes(result.notes || [])
      setRegisterMessage(`Continuity analysis complete: ${(result.issues || []).length} advisory issue(s).`)
    } catch (err) {
      setRegisterMessage(err instanceof Error ? err.message : 'Failed to analyze continuity')
    } finally {
      setContinuityLoading(false)
    }
  }

  async function generateCommentaryForAsset(assetId: string) {
    setCommentaryLoadingAssetId(assetId)
    setRegisterMessage('')
    try {
      const result = await generateDirectorCommentary(assetId, true)
      setCommentaryByAsset((prev) => ({ ...prev, [assetId]: result.commentary || [] }))
      setRegisterMessage(`Director commentary generated: ${(result.commentary || []).length} note(s).`)
      setActiveTabByAsset((prev) => ({ ...prev, [assetId]: 'commentary' }))
    } catch (err) {
      setRegisterMessage(err instanceof Error ? err.message : 'Failed to generate director commentary')
    } finally {
      setCommentaryLoadingAssetId('')
    }
  }

  async function registerDemoFrameAnalysis(assetId: string) {
    const frame = keyframesByAsset[assetId]?.[0]
    await registerFrameAnalysis(assetId, {
      keyframe_id: frame?.keyframe_id,
      caption: 'Framing pass with implied tension in negative space.',
      mood_tags: ['tense', 'reflective'],
      lighting_tags: ['low-key'],
      camera_tags: ['static', 'medium shot'],
      metadata: { source: 'devtools_demo' },
    })
  }

  async function findSimilarScenes() {
    if (!similarMemoryId.trim()) {
      setSimilarResults([])
      return
    }
    try {
      const result = await searchSimilarScenes(similarMemoryId.trim(), 10)
      setSimilarResults(result.results || [])
    } catch {
      setSimilarResults([])
    }
  }

  async function findByMood() {
    try {
      const result = await searchScenesByMood(moodQuery, 20)
      setMoodResults(result.memories || [])
    } catch {
      setMoodResults([])
    }
  }

  async function findByVisualStyle() {
    try {
      const result = await searchScenesByVisualStyle(styleQuery, 20)
      setStyleResults(result.memories || [])
    } catch {
      setStyleResults([])
    }
  }

  async function registerLatestFinalPackageOutput() {
    if (!projectId) return
    setRegisterMessage('')
    try {
      const packages = await listFinalShortFilmPackagesForProject(projectId)
      const latest = packages.packages?.[0]
      if (!latest?.final_output_url) {
        setRegisterMessage('No final package output URL found for this project.')
        return
      }
      const result = await registerVideoAsset(projectId, {
        source_type: 'generated_output',
        source_url: latest.final_output_url,
        title: `${latest.film_title || 'Final Output'} (Registered Asset)`,
        metadata: { package_id: latest.package_id, origin: 'devtools_register' },
      })
      setRegisterMessage(`Registered asset: ${result.asset.asset_id}`)
      await loadAssets()
    } catch (err) {
      setRegisterMessage(err instanceof Error ? err.message : 'Failed to register latest final package output')
    }
  }

  useEffect(() => {
    void loadAssets()
    void loadContinuityIssues()
    void loadStyleDNA()
    void loadDiagnostics()
  }, [projectId])

  useEffect(() => {
    assets.forEach((asset) => {
      void loadKeyframes(asset.asset_id)
      void loadShots(asset.asset_id)
      void loadMemories(asset.asset_id)
      void loadCommentary(asset.asset_id)
    })
  }, [assets])

  useEffect(() => {
    if (!autoRefreshDiagnostics) return
    const interval = window.setInterval(() => {
      void loadDiagnostics()
    }, 7000)
    return () => window.clearInterval(interval)
  }, [autoRefreshDiagnostics, projectId])

  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      if (event.message) setLastUiError(event.message)
    }
    window.addEventListener('error', onError)
    return () => window.removeEventListener('error', onError)
  }, [])

  if (isProduction && !devModeEnabled) {
    return (
      <StudioShell title="Studio Dev Tools" subtitle="Developer tools are disabled in production mode.">
        <div className="mx-auto w-full max-w-5xl px-4 py-8 text-zinc-100">
          <div className="studio-empty-state text-sm text-zinc-300">
            DevTools is hidden in production mode. Enable local dev mode to access diagnostics.
          </div>
        </div>
      </StudioShell>
    )
  }

  return (
    <StudioShell title="Studio Dev Tools" subtitle="Hidden diagnostics and sandbox tooling for local developer workflows.">
      <div className="w-full overflow-visible bg-background">
        <RenderActivityPanel roomName="Lobby" />
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6 text-zinc-100">
          <section className="rounded-2xl border border-cyan-300/25 bg-cyan-500/10 p-4 shadow-xl">
            <div className="text-xs uppercase tracking-[0.14em] text-cyan-200">Developer Tools</div>
            <p className="mt-1 text-sm text-zinc-200">Sandbox generation, recovery, diagnostics, and package/revision QA are intentionally isolated from public Studio UX.</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={registerLatestFinalPackageOutput}
                className="rounded-lg border border-cyan-300/55 bg-cyan-500/18 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100"
              >
                Register Latest Final Package Output
              </button>
              <button
                type="button"
                onClick={loadAssets}
                className="rounded-lg border border-zinc-500/55 bg-zinc-700/30 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100"
              >
                Refresh Video Assets
              </button>
            </div>
            {registerMessage ? <div className="mt-2 text-xs text-cyan-200">{registerMessage}</div> : null}
            {assetError ? <div className="mt-2 text-xs text-rose-200">{assetError}</div> : null}
          </section>

          <section className="rounded-2xl border border-amber-300/25 bg-amber-500/10 p-4 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-xs uppercase tracking-[0.14em] text-amber-200">Diagnostics Panel</div>
                <div className="mt-1 text-xs text-zinc-300">Internal-only runtime diagnostics for provider, queue, hydration, and persistence health.</div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setDebugPanelOpen((prev) => !prev)}
                  className="rounded border border-zinc-500/55 bg-zinc-700/30 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-zinc-100"
                >
                  {debugPanelOpen ? 'Hide' : 'Show'}
                </button>
                <button
                  type="button"
                  onClick={() => void loadDiagnostics()}
                  className="rounded border border-amber-300/55 bg-amber-500/18 px-2 py-1 text-[10px] uppercase tracking-[0.1em] text-amber-100"
                >
                  Refresh
                </button>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-4 text-[11px] text-zinc-200">
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={autoRefreshDiagnostics} onChange={(e) => setAutoRefreshDiagnostics(e.target.checked)} />
                auto-refresh diagnostics
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={showVerbosePayloads} onChange={(e) => setShowVerbosePayloads(e.target.checked)} />
                show verbose payloads
              </label>
            </div>
            {debugPanelOpen ? (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded border border-white/10 bg-black/30 p-2 text-[11px]">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Hydration State</div>
                  <div className="mt-1">context loading: {String(loading)}</div>
                  <div>project id: {projectId || 'none'}</div>
                  <div>in-memory jobs: {diagnostics?.hydration_state.in_memory_job_count ?? renderJobs.length}</div>
                  <div>storage initialized: {String(diagnostics?.hydration_state.storage_initialized ?? false)}</div>
                  <div>active polling loops: {pollingJobs.size}</div>
                </div>
                <div className="rounded border border-white/10 bg-black/30 p-2 text-[11px]">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Environment Visibility</div>
                  <div className="mt-1">ffmpeg: {diagnostics?.environment.ffmpeg_available ? 'available' : 'missing'}</div>
                  <div>ffprobe: {diagnostics?.environment.ffprobe_available ? 'available' : 'missing'}</div>
                  <div>storage health: {diagnostics?.persistence_health.status || 'unknown'}</div>
                  <div className="truncate">db path: {diagnostics?.persistence_health.db_path || 'n/a'}</div>
                </div>
                <div className="rounded border border-white/10 bg-black/30 p-2 text-[11px]">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Provider Status</div>
                  <div className="mt-1">selected provider: {selectedRenderProvider || 'none'}</div>
                  <div>available providers: {providers.length}</div>
                  <div className="mt-1 space-y-1">
                    {(diagnostics?.provider_status || []).map((provider) => (
                      <div key={provider.provider_id}>
                        {provider.provider_id}: {provider.status}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="rounded border border-white/10 bg-black/30 p-2 text-[11px]">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Render Queue</div>
                  <div className="mt-1">total jobs: {diagnostics?.render_queue.total ?? renderJobs.length}</div>
                  <div className="mt-1 space-y-1">
                    {Object.entries(diagnostics?.render_queue.status_counts || {}).map(([status, count]) => (
                      <div key={status}>{status}: {count}</div>
                    ))}
                  </div>
                </div>
                <div className="rounded border border-white/10 bg-black/30 p-2 text-[11px] md:col-span-2">
                  <div className="text-[10px] uppercase tracking-[0.1em] text-zinc-400">Last Errors</div>
                  <div className="mt-1">context error: {error || 'none'}</div>
                  <div>diagnostics error: {diagnosticsError || 'none'}</div>
                  <div>last ui error: {lastUiError || 'none'}</div>
                  <div>diagnostics loading: {String(diagnosticsLoading)}</div>
                </div>
                {showVerbosePayloads ? (
                  <pre className="md:col-span-2 overflow-x-auto rounded border border-white/10 bg-black/35 p-2 text-[10px] text-zinc-300">
                    {JSON.stringify(diagnostics, null, 2)}
                  </pre>
                ) : null}
              </div>
            ) : null}
          </section>
          <section className="rounded-2xl border border-white/10 bg-zinc-900/45 p-4 shadow-xl">
            <div className="text-xs uppercase tracking-[0.14em] text-zinc-300">Registered Video Assets</div>
            <div className="mt-2 text-[11px] text-zinc-400">Project: {projectId || 'none selected'}</div>
            <div className="mt-3 space-y-2">
              {assets.length === 0 ? (
                <div className="rounded-lg border border-dashed border-zinc-700 bg-black/30 px-3 py-2 text-xs text-zinc-400">
                  No registered video assets for this project.
                </div>
              ) : (
                assets.map((asset) => (
                  <div key={asset.asset_id} className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-zinc-200">
                    <div className="font-semibold text-zinc-100">{asset.title}</div>
                    <div className="mt-1">Status: {asset.status}</div>
                    <div>Source Type: {asset.source_type}</div>
                    <div className="truncate">URL: {asset.source_url || 'n/a'}</div>
                    <div className="truncate">Path: {asset.local_path || 'n/a'}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void extractKeyframes(asset.asset_id, false)}
                        disabled={extractingAssetId === asset.asset_id}
                        className="rounded border border-cyan-300/55 bg-cyan-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-cyan-100 disabled:opacity-60"
                      >
                        Extract Keyframes
                      </button>
                      <button
                        type="button"
                        onClick={() => void extractKeyframes(asset.asset_id, true)}
                        disabled={extractingAssetId === asset.asset_id}
                        className="rounded border border-zinc-400/55 bg-zinc-700/35 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-zinc-100 disabled:opacity-60"
                      >
                        Re-Extract (Overwrite)
                      </button>
                      <button
                        type="button"
                        onClick={() => void detectShots(asset.asset_id, true)}
                        disabled={detectingAssetId === asset.asset_id}
                        className="rounded border border-amber-300/55 bg-amber-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-amber-100 disabled:opacity-60"
                      >
                        Detect Shots
                      </button>
                      <button
                        type="button"
                        onClick={() => void ingestMemory(asset.asset_id)}
                        disabled={ingestingAssetId === asset.asset_id}
                        className="rounded border border-fuchsia-300/55 bg-fuchsia-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-fuchsia-100 disabled:opacity-60"
                      >
                        Ingest Scene Memory
                      </button>
                      <button
                        type="button"
                        onClick={() => void generateCommentaryForAsset(asset.asset_id)}
                        disabled={commentaryLoadingAssetId === asset.asset_id}
                        className="rounded border border-sky-300/55 bg-sky-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-sky-100 disabled:opacity-60"
                      >
                        Generate Commentary
                      </button>
                      <button
                        type="button"
                        onClick={() => void registerDemoFrameAnalysis(asset.asset_id)}
                        className="rounded border border-emerald-300/55 bg-emerald-500/18 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-emerald-100"
                      >
                        Register Frame Analysis
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTabByAsset((prev) => ({ ...prev, [asset.asset_id]: 'timeline' }))}
                        className="rounded border border-white/25 bg-white/5 px-2 py-1 text-[10px]"
                      >
                        Timeline
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTabByAsset((prev) => ({ ...prev, [asset.asset_id]: 'keyframes' }))}
                        className="rounded border border-white/25 bg-white/5 px-2 py-1 text-[10px]"
                      >
                        Keyframes
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTabByAsset((prev) => ({ ...prev, [asset.asset_id]: 'memory' }))}
                        className="rounded border border-white/25 bg-white/5 px-2 py-1 text-[10px]"
                      >
                        Scene Memory
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTabByAsset((prev) => ({ ...prev, [asset.asset_id]: 'commentary' }))}
                        className="rounded border border-white/25 bg-white/5 px-2 py-1 text-[10px]"
                      >
                        Commentary
                      </button>
                    </div>
                    {(activeTabByAsset[asset.asset_id] || 'timeline') === 'timeline' ? <div className="mt-3 rounded border border-white/10 bg-zinc-950/40 p-2">
                      <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-400">Shot Timeline</div>
                      <div className="mt-2 flex h-5 w-full overflow-hidden rounded bg-zinc-800/70">
                        {(shotsByAsset[asset.asset_id] || []).map((shot) => {
                          const width = Math.max(2, (shot.end_time - shot.start_time) * 10)
                          const color =
                            shot.transition_type === 'fade'
                              ? 'bg-violet-400/80'
                              : shot.transition_type === 'dissolve'
                                ? 'bg-amber-400/80'
                                : 'bg-emerald-400/80'
                          return <div key={shot.boundary_id} className={`${color} border-r border-black/40`} style={{ width: `${width}%` }} title={`${shot.transition_type} ${shot.start_time.toFixed(2)}-${shot.end_time.toFixed(2)}s`} />
                        })}
                      </div>
                      <div className="mt-2 space-y-1">
                        {(shotsByAsset[asset.asset_id] || []).map((shot, index) => (
                          <div key={shot.boundary_id} className="text-[10px] text-zinc-300">
                            Shot {index + 1}: {shot.start_time.toFixed(2)}s - {shot.end_time.toFixed(2)}s | {shot.transition_type} | conf {shot.confidence.toFixed(2)}
                          </div>
                        ))}
                      </div>
                    </div> : null}
                    {(activeTabByAsset[asset.asset_id] || 'timeline') === 'keyframes' ? <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                      {(keyframesByAsset[asset.asset_id] || []).map((keyframe) => (
                        <div key={keyframe.keyframe_id} className="rounded border border-white/10 bg-zinc-950/55 p-1">
                          {keyframe.frame_url ? (
                            <img src={keyframe.frame_url} alt={`Keyframe ${keyframe.frame_index}`} className="h-24 w-full rounded object-cover" />
                          ) : null}
                          <div className="mt-1 text-[10px] text-zinc-300">
                            t={keyframe.timestamp_seconds.toFixed(1)}s
                          </div>
                          <div className="text-[10px] text-zinc-400">{keyframe.extraction_reason}</div>
                        </div>
                      ))}
                    </div> : null}
                    {(activeTabByAsset[asset.asset_id] || 'timeline') === 'memory' ? (
                      <div className="mt-3 rounded border border-fuchsia-300/20 bg-fuchsia-900/10 p-2">
                        <div className="text-[10px] uppercase tracking-[0.08em] text-fuchsia-200">Scene Memory (Advisory Only)</div>
                        <div className="mt-2 space-y-2">
                          {(memoriesByAsset[asset.asset_id] || []).map((memory) => (
                            <div key={memory.memory_id} className="rounded border border-white/10 bg-black/30 p-2 text-[10px]">
                              <div className="font-semibold text-zinc-100">{memory.memory_id}</div>
                              <div>Mood: {memory.dominant_mood}</div>
                              <div>Visual: {memory.visual_style}</div>
                              <div>Lighting: {memory.lighting_style}</div>
                              <div>Pacing: {memory.pacing_profile}</div>
                              <div>Characters: {memory.character_presence.join(', ') || 'none'}</div>
                              <div>Composition: {memory.composition_patterns.join(' | ') || 'none'}</div>
                              <div className="mt-1 text-zinc-300">{memory.cinematic_notes}</div>
                              <button
                                type="button"
                                onClick={() => void loadRelated(memory.memory_id)}
                                className="mt-2 rounded border border-fuchsia-300/40 bg-fuchsia-500/15 px-2 py-1 text-[10px] text-fuchsia-100"
                              >
                                Related Memories
                              </button>
                              {(relatedByMemory[memory.memory_id] || []).length > 0 ? (
                                <div className="mt-2 text-zinc-300">
                                  Related: {(relatedByMemory[memory.memory_id] || []).map((item) => item.memory_id).join(', ')}
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {(activeTabByAsset[asset.asset_id] || 'timeline') === 'commentary' ? (
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <div className="rounded border border-white/10 bg-zinc-950/40 p-2">
                          <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-400">Playback</div>
                          {asset.source_url ? (
                            <video
                              className="mt-2 w-full rounded border border-white/10 bg-black"
                              controls
                              src={asset.source_url}
                            />
                          ) : (
                            <div className="mt-2 rounded border border-dashed border-zinc-700 px-3 py-6 text-xs text-zinc-400">
                              No playable source URL available for this asset.
                            </div>
                          )}
                        </div>
                        <div className="rounded border border-sky-300/20 bg-sky-900/10 p-2">
                          <div className="text-[10px] uppercase tracking-[0.08em] text-sky-200">Director Commentary (Grounded, Advisory)</div>
                          <div className="mt-2 space-y-2">
                            {(commentaryByAsset[asset.asset_id] || []).map((entry) => (
                              <div key={entry.commentary_id} className="rounded border border-white/10 bg-black/30 p-2 text-[10px] text-zinc-200">
                                <div className="font-semibold text-zinc-100">{entry.scene_reference}</div>
                                <div className="mt-1"><span className="text-zinc-400">Interpretation:</span> {entry.interpretation}</div>
                                <div className="mt-1"><span className="text-zinc-400">Emotional Read:</span> {entry.emotional_read}</div>
                                <div className="mt-1"><span className="text-zinc-400">Visual Language:</span> {entry.visual_language_notes}</div>
                                <div className="mt-1"><span className="text-zinc-400">Pacing:</span> {entry.pacing_notes}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
            <div className="mt-4 rounded-lg border border-fuchsia-300/20 bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-[0.1em] text-fuchsia-200">Scene Memory Search</div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                  value={memoryQuery}
                  onChange={(event) => setMemoryQuery(event.target.value)}
                  placeholder="search mood, style, notes..."
                  className="min-w-[220px] rounded border border-white/20 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
                />
                <button
                  type="button"
                  onClick={() => void runMemorySearch()}
                  className="rounded border border-fuchsia-300/40 bg-fuchsia-500/15 px-2 py-1 text-[10px] text-fuchsia-100"
                >
                  Search
                </button>
              </div>
              <div className="mt-2 space-y-1 text-[10px] text-zinc-300">
                {memorySearchResults.map((memory) => (
                  <div key={memory.memory_id}>
                    {memory.memory_id} | {memory.dominant_mood} | {memory.visual_style} | {memory.pacing_profile}
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-4 rounded-lg border border-amber-300/20 bg-amber-900/10 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[10px] uppercase tracking-[0.1em] text-amber-200">Continuity Warnings (Advisory Only)</div>
                <button
                  type="button"
                  onClick={() => void analyzeContinuity()}
                  disabled={continuityLoading}
                  className="rounded border border-amber-300/40 bg-amber-500/15 px-2 py-1 text-[10px] text-amber-100 disabled:opacity-60"
                >
                  Analyze Continuity
                </button>
              </div>
              <div className="mt-2 space-y-1 text-[10px] text-zinc-300">
                {continuityNotes.map((note, index) => (
                  <div key={`note-${index}`}>{note}</div>
                ))}
              </div>
              <div className="mt-2 space-y-2">
                {continuityIssues.map((issue) => (
                  <div key={issue.issue_id} className="rounded border border-white/10 bg-black/30 p-2 text-[10px] text-zinc-200">
                    <div className="font-semibold text-zinc-100">{issue.issue_type} · {issue.severity}</div>
                    <div>{issue.description}</div>
                    <div>confidence: {issue.confidence.toFixed(2)}</div>
                    <div className="text-zinc-400">{issue.notes}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-4 rounded-lg border border-cyan-300/20 bg-cyan-900/10 p-3">
              <div className="text-[10px] uppercase tracking-[0.1em] text-cyan-200">Find Similar Scenes</div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                  value={similarMemoryId}
                  onChange={(event) => setSimilarMemoryId(event.target.value)}
                  placeholder="memory-id"
                  className="min-w-[220px] rounded border border-white/20 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
                />
                <button
                  type="button"
                  onClick={() => void findSimilarScenes()}
                  className="rounded border border-cyan-300/40 bg-cyan-500/15 px-2 py-1 text-[10px] text-cyan-100"
                >
                  Similar
                </button>
                <input
                  value={moodQuery}
                  onChange={(event) => setMoodQuery(event.target.value)}
                  placeholder="mood"
                  className="min-w-[140px] rounded border border-white/20 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
                />
                <button
                  type="button"
                  onClick={() => void findByMood()}
                  className="rounded border border-cyan-300/40 bg-cyan-500/15 px-2 py-1 text-[10px] text-cyan-100"
                >
                  By Mood
                </button>
                <input
                  value={styleQuery}
                  onChange={(event) => setStyleQuery(event.target.value)}
                  placeholder="visual style"
                  className="min-w-[160px] rounded border border-white/20 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
                />
                <button
                  type="button"
                  onClick={() => void findByVisualStyle()}
                  className="rounded border border-cyan-300/40 bg-cyan-500/15 px-2 py-1 text-[10px] text-cyan-100"
                >
                  By Style
                </button>
              </div>
              <div className="mt-3 space-y-1 text-[10px] text-zinc-300">
                {similarResults.map((row, index) => (
                  <div key={`sim-${index}`}>
                    score {row.score.toFixed(3)} | {row.source} | {row.memory?.memory_id || row.frame_analysis?.analysis_id}
                  </div>
                ))}
              </div>
              <div className="mt-2 text-[10px] text-zinc-300">Mood matches: {moodResults.map((m) => m.memory_id).join(', ') || 'none'}</div>
              <div className="mt-1 text-[10px] text-zinc-300">Style matches: {styleResults.map((m) => m.memory_id).join(', ') || 'none'}</div>
            </div>
            <div className="mt-4 rounded-lg border border-lime-300/20 bg-lime-900/10 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[10px] uppercase tracking-[0.1em] text-lime-200">Style DNA Panel (Advisory Only)</div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void buildStyleSignature()}
                    disabled={styleLearningLoading}
                    className="rounded border border-lime-300/40 bg-lime-500/15 px-2 py-1 text-[10px] text-lime-100 disabled:opacity-60"
                  >
                    Build Signature
                  </button>
                  <button
                    type="button"
                    onClick={() => void compareLatestSignatures()}
                    className="rounded border border-lime-300/40 bg-lime-500/15 px-2 py-1 text-[10px] text-lime-100"
                  >
                    Compare Latest Two
                  </button>
                </div>
              </div>
              <div className="mt-2 text-[10px] text-zinc-300">
                Signatures: {stylePatternSummary?.signature_count ?? 0} | Advisory: yes | Auto-regeneration: no
              </div>
              {stylePatternSummary?.latest_signature ? (
                <div className="mt-2 rounded border border-white/10 bg-black/30 p-2 text-[10px] text-zinc-200">
                  <div className="font-semibold text-zinc-100">{stylePatternSummary.latest_signature.signature_id}</div>
                  <div>Framing: {stylePatternSummary.latest_signature.framing_tendencies.join(' | ') || 'none'}</div>
                  <div>Pacing: {stylePatternSummary.latest_signature.pacing_patterns.join(' | ') || 'none'}</div>
                  <div>Color Motifs: {stylePatternSummary.latest_signature.color_motifs.join(' | ') || 'none'}</div>
                  <div>Camera Movement: {stylePatternSummary.latest_signature.camera_movement_patterns.join(' | ') || 'none'}</div>
                  <div>Confidence: {stylePatternSummary.latest_signature.confidence.toFixed(2)}</div>
                </div>
              ) : (
                <div className="mt-2 rounded border border-dashed border-zinc-700 bg-black/20 px-2 py-2 text-[10px] text-zinc-400">
                  No style signatures yet. Build one from current analyzed scene memory.
                </div>
              )}
              {styleComparison ? (
                <div className="mt-2 rounded border border-white/10 bg-black/30 p-2 text-[10px] text-zinc-200">
                  <div>Similarity: {styleComparison.overall_similarity.toFixed(3)}</div>
                  <div>Framing: {styleComparison.breakdown.framing.toFixed(3)}</div>
                  <div>Pacing: {styleComparison.breakdown.pacing.toFixed(3)}</div>
                  <div>Color: {styleComparison.breakdown.color.toFixed(3)}</div>
                  <div>Camera Movement: {styleComparison.breakdown.camera_movement.toFixed(3)}</div>
                </div>
              ) : null}
            </div>
          </section>
          <SandboxShortFilmPanel />
        </div>
      </div>
      <LazyAICrewPresence />
    </StudioShell>
  )
}

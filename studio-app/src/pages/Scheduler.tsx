import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import StudioShell from '../components/StudioShell'
import CrewOpsDashboard from '../components/CrewOpsDashboard'
import { useStudio } from '../context/StudioContext'
import {
  getRenderProviders,
  getLatestDirectorSignature,
  listProjectContinuityIssues,
  listClipRevisionsForProject,
  listFinalShortFilmPackagesForProject,
  listProjectCinematicMemory,
  listProjectFrameAnalyses,
  listProjectEmbeddings,
  listProjectStyleDriftIssues,
  listRenderJobs,
  listShortFilmReviews,
  listVideoAssetsForProject,
  listVideoAssetKeyframes,
  reconcileRenderJob,
  retryRenderJobById,
  type ClipRevision,
  type FinalShortFilmPackage,
  type ProviderStatus,
  type RenderJob,
  type ShortFilmReview,
  type VideoAsset,
  type FrameAnalysis,
  type VideoKeyframe,
  type CinematicMemoryRecord,
  type VisualEmbedding,
  type ContinuityIssue,
  type DirectorSignature,
  type StyleDriftIssue,
} from '../lib/studioApi'
import { isInsufficientVisualData, summarizeContinuityIssues } from '../lib/continuityIntelligence'
import { INTELLIGENCE_LABELS, INTELLIGENCE_EMPTY } from '../lib/intelligenceStatus'
import { persistActiveProjectId, readPersistedActiveProjectId, resolveActiveProjectId, withProjectQuery } from '../lib/projectContext'

function statusPill(status: string) {
  const v = status.toLowerCase()
  if (v.includes('fail')) return 'border-rose-400/40 bg-rose-500/15 text-rose-200'
  if (v.includes('complete') || v.includes('approved') || v.includes('packaged')) return 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200'
  if (v.includes('pending') || v.includes('queued') || v.includes('submitted')) return 'border-amber-400/40 bg-amber-500/15 text-amber-200'
  return 'border-zinc-500/40 bg-zinc-500/15 text-zinc-200'
}

function outputUrl(job: RenderJob): string {
  const url = job.output_payload?.asset_url
  if (typeof url === 'string' && url.trim()) return url
  return ''
}

export default function Scheduler() {
  const { project, overview } = useStudio()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const activeProject = project || overview?.latest_project || null
  const activeProjectId = resolveActiveProjectId({
    queryProjectId,
    locationState: location.state,
    persistedProjectId: readPersistedActiveProjectId(),
    contextProjectId: activeProject?.project_id || '',
    overviewProjectId: overview?.latest_project?.project_id || '',
  })
  useEffect(() => {
    if (activeProjectId) persistActiveProjectId(activeProjectId)
  }, [activeProjectId])

  const [jobs, setJobs] = useState<RenderJob[]>([])
  const [reviews, setReviews] = useState<ShortFilmReview[]>([])
  const [revisions, setRevisions] = useState<ClipRevision[]>([])
  const [providers, setProviders] = useState<ProviderStatus[]>([])
  const [assets, setAssets] = useState<VideoAsset[]>([])
  const [frameAnalyses, setFrameAnalyses] = useState<FrameAnalysis[]>([])
  const [embeddings, setEmbeddings] = useState<VisualEmbedding[]>([])
  const [videoKeyframes, setVideoKeyframes] = useState<VideoKeyframe[]>([])
  const [cinematicMemory, setCinematicMemory] = useState<CinematicMemoryRecord[]>([])
  const [continuityIssues, setContinuityIssues] = useState<ContinuityIssue[]>([])
  const [directorSignature, setDirectorSignature] = useState<DirectorSignature | null>(null)
  const [styleDriftIssues, setStyleDriftIssues] = useState<StyleDriftIssue[]>([])
  const [packages, setPackages] = useState<FinalShortFilmPackage[]>([])
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    let controller: AbortController | null = null
    async function loadOps() {
      if (!activeProjectId) {
        setJobs([])
        setReviews([])
        setRevisions([])
        setAssets([])
        setPackages([])
        setFrameAnalyses([])
        setEmbeddings([])
        setVideoKeyframes([])
        setCinematicMemory([])
        setContinuityIssues([])
        setDirectorSignature(null)
        setStyleDriftIssues([])
      } else {
        controller?.abort()
        controller = new AbortController()
        const [
          jobsRes,
          reviewsRes,
          revisionsRes,
          assetsRes,
          packagesRes,
          analysesRes,
          embeddingsRes,
          memoryRes,
          continuityRes,
          directorSigRes,
          styleDriftRes,
        ] = await Promise.allSettled([
          listRenderJobs(activeProjectId, { signal: controller.signal }),
          listShortFilmReviews(activeProjectId),
          listClipRevisionsForProject(activeProjectId),
          listVideoAssetsForProject(activeProjectId, { signal: controller.signal }),
          listFinalShortFilmPackagesForProject(activeProjectId),
          listProjectFrameAnalyses(activeProjectId, { signal: controller.signal }),
          listProjectEmbeddings(activeProjectId, { signal: controller.signal }),
          listProjectCinematicMemory(activeProjectId, { signal: controller.signal }),
          listProjectContinuityIssues(activeProjectId, { signal: controller.signal }),
          getLatestDirectorSignature(activeProjectId, { signal: controller.signal }),
          listProjectStyleDriftIssues(activeProjectId, { signal: controller.signal }),
        ])
        if (cancelled) {
          controller.abort()
          return
        }
        setJobs(jobsRes.status === 'fulfilled' && Array.isArray(jobsRes.value) ? jobsRes.value : [])
        setReviews(reviewsRes.status === 'fulfilled' ? reviewsRes.value.reviews || [] : [])
        setRevisions(revisionsRes.status === 'fulfilled' ? revisionsRes.value.revisions || [] : [])
        setAssets(assetsRes.status === 'fulfilled' ? assetsRes.value.assets || [] : [])
        setPackages(packagesRes.status === 'fulfilled' ? packagesRes.value.packages || [] : [])
        setFrameAnalyses(analysesRes.status === 'fulfilled' ? analysesRes.value.analyses || [] : [])
        setEmbeddings(embeddingsRes.status === 'fulfilled' ? embeddingsRes.value.embeddings || [] : [])
        setVideoKeyframes([])
        setCinematicMemory(memoryRes.status === 'fulfilled' ? memoryRes.value.memory_records || [] : [])
        setContinuityIssues(continuityRes.status === 'fulfilled' ? continuityRes.value.issues || [] : [])
        setDirectorSignature(directorSigRes.status === 'fulfilled' ? directorSigRes.value.signature || null : null)
        setStyleDriftIssues(styleDriftRes.status === 'fulfilled' ? styleDriftRes.value.issues || [] : [])
      }

      const providersRes = await Promise.allSettled([getRenderProviders()])
      if (!cancelled) {
        const p = providersRes[0]
        setProviders(p.status === 'fulfilled' ? p.value : [])
      }
    }

    void loadOps()
    const timer = window.setInterval(() => {
      void loadOps()
    }, 10000)
    return () => {
      cancelled = true
      controller?.abort()
      window.clearInterval(timer)
    }
  }, [activeProjectId])

  useEffect(() => {
    if (!activeProjectId || assets.length === 0) {
      setVideoKeyframes([])
      return
    }
    let cancelled = false
    const controller = new AbortController()
    async function loadAssetKeyframes() {
      const results = await Promise.allSettled(
        assets.map((asset) => listVideoAssetKeyframes(asset.asset_id, { signal: controller.signal })),
      )
      if (cancelled) return
      const keyframes: VideoKeyframe[] = []
      results.forEach((result) => {
        if (result.status === 'fulfilled' && Array.isArray(result.value.keyframes)) {
          keyframes.push(...result.value.keyframes)
        }
      })
      setVideoKeyframes(keyframes)
    }
    void loadAssetKeyframes()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [activeProjectId, assets])

  const failedJobs = useMemo(() => jobs.filter((j) => j.status.toLowerCase() === 'failed'), [jobs])
  const pendingReviews = useMemo(
    () => reviews.filter((r) => r.decision === 'pending' || r.decision === 'needs_revision'),
    [reviews],
  )
  const pendingRevisions = useMemo(
    () => revisions.filter((r) => ['pending', 'submitted', 'failed'].includes(r.status)),
    [revisions],
  )
  const completedFrameAnalyses = useMemo(
    () => frameAnalyses.filter((a) => (a.status || '').toLowerCase() === 'complete').length,
    [frameAnalyses],
  )
  const assetsAwaitingStudy = useMemo(
    () => assets.filter((a) => ['registered', 'available', 'analysis_pending'].includes(a.status)),
    [assets],
  )
  const embeddedKeyframeCount = useMemo(
    () => embeddings.filter((e) => e.status === 'complete').length,
    [embeddings],
  )
  const continuitySummary = useMemo(() => summarizeContinuityIssues(continuityIssues), [continuityIssues])
  const continuityInsufficientData = useMemo(
    () => isInsufficientVisualData({ frameAnalysisCount: frameAnalyses.length, embeddingCount: embeddings.length }),
    [frameAnalyses.length, embeddings.length],
  )

  const pipelineCounts = useMemo(() => {
    const activeRenders = jobs.filter((j) => ['pending', 'rendering'].includes(j.status.toLowerCase())).length
    const completedRenders = jobs.filter((j) => j.status.toLowerCase() === 'complete').length
    const failedRenders = jobs.filter((j) => j.status.toLowerCase() === 'failed').length
    const packagedFilms = packages.filter((p) => ['ready_for_review', 'approved', 'packaged'].includes(p.package_status)).length
    return {
      totalProjects: overview?.projects?.length || 0,
      activeRenders,
      completedRenders,
      failedRenders,
      pendingReviews: pendingReviews.length,
      pendingRevisions: pendingRevisions.length,
      packagedFilms,
    }
  }, [jobs, overview?.projects?.length, packages, pendingReviews.length, pendingRevisions.length])

  const hasAnyOps =
    jobs.length > 0 ||
    failedJobs.length > 0 ||
    pendingReviews.length > 0 ||
    pendingRevisions.length > 0 ||
    assetsAwaitingStudy.length > 0 ||
    packages.length > 0

  return (
    <StudioShell title="Crew Ops" subtitle="Operational truth across rendering, review, revision, and package stages.">
      <div className="mx-auto w-full max-w-7xl px-4 py-6 text-zinc-100 sm:px-6 lg:px-8">
        <section className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">Production Pipeline</h2>
          <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
            <div className="rounded border border-white/10 bg-black/25 p-2 text-xs">Projects<br/><span className="text-zinc-100">{pipelineCounts.totalProjects}</span></div>
            <div className="rounded border border-white/10 bg-black/25 p-2 text-xs">Active Renders<br/><span className="text-zinc-100">{pipelineCounts.activeRenders}</span></div>
            <div className="rounded border border-white/10 bg-black/25 p-2 text-xs">Completed Renders<br/><span className="text-zinc-100">{pipelineCounts.completedRenders}</span></div>
            <div className="rounded border border-white/10 bg-black/25 p-2 text-xs">Failed Renders<br/><span className="text-zinc-100">{pipelineCounts.failedRenders}</span></div>
            <div className="rounded border border-white/10 bg-black/25 p-2 text-xs">Pending Reviews<br/><span className="text-zinc-100">{pipelineCounts.pendingReviews}</span></div>
            <div className="rounded border border-white/10 bg-black/25 p-2 text-xs">Pending Revisions<br/><span className="text-zinc-100">{pipelineCounts.pendingRevisions}</span></div>
            <div className="rounded border border-white/10 bg-black/25 p-2 text-xs">Packaged Films<br/><span className="text-zinc-100">{pipelineCounts.packagedFilms}</span></div>
          </div>
        </section>

        <section className="mt-4 rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">{INTELLIGENCE_LABELS.continuityNotes}</h2>
            <div className="flex items-center gap-3 text-xs">
              <Link to={withProjectQuery('/studio/previs', activeProjectId)} className="text-cyan-300 no-underline">Open Previs</Link>
              <Link to={withProjectQuery('/studio/screening-room', activeProjectId)} className="text-cyan-300 no-underline">Open Screening Room</Link>
            </div>
          </div>
          {continuitySummary.total > 0 ? (
            <div className="mt-3 space-y-3 text-xs">
              <div className="rounded border border-white/10 bg-black/25 p-2">
                <div className="text-zinc-300">Total Continuity Issues</div>
                <div className="text-lg font-semibold text-zinc-100">{continuitySummary.total}</div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded border border-rose-400/30 bg-rose-500/10 p-2">high<br /><span className="text-zinc-100">{continuitySummary.severityCounts.high}</span></div>
                <div className="rounded border border-amber-400/30 bg-amber-500/10 p-2">medium<br /><span className="text-zinc-100">{continuitySummary.severityCounts.medium}</span></div>
                <div className="rounded border border-sky-400/30 bg-sky-500/10 p-2">low<br /><span className="text-zinc-100">{continuitySummary.severityCounts.low}</span></div>
              </div>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {Object.entries(continuitySummary.issueTypeCounts).map(([issueType, count]) => (
                  <div key={issueType} className="rounded border border-white/10 bg-black/25 p-2">
                    {issueType}<br /><span className="text-zinc-100">{count}</span>
                  </div>
                ))}
              </div>
              {continuitySummary.topIssue ? (
                <div className="rounded border border-violet-400/30 bg-violet-500/10 p-2">
                  <div className="font-semibold text-zinc-100">Highest/Latest Issue</div>
                  <div className="text-zinc-300">{continuitySummary.topIssue.issue_type} · {continuitySummary.topIssue.severity}</div>
                  <div className="text-zinc-400">{continuitySummary.topIssue.description}</div>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="mt-3 text-sm text-zinc-300">
              {continuityInsufficientData ? INTELLIGENCE_EMPTY.continuityNeedsVisualPipeline : INTELLIGENCE_EMPTY.noContinuityIssues}
            </p>
          )}
        </section>

        <section className="mt-4 rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">{INTELLIGENCE_LABELS.directorSignature} · {INTELLIGENCE_LABELS.styleDrift}</h2>
            <Link to={withProjectQuery('/studio/study-room', activeProjectId)} className="text-xs text-cyan-300 no-underline">
              Study Room
            </Link>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
            <div className="rounded border border-fuchsia-400/30 bg-fuchsia-500/10 p-2">
              {INTELLIGENCE_LABELS.directorSignature} (confidence)
              <br />
              <span className="text-zinc-100">{directorSignature ? `${(directorSignature.confidence * 100).toFixed(0)}%` : '—'}</span>
              {directorSignature?.metadata && directorSignature.metadata.insufficient_data ? (
                <div className="text-[10px] text-amber-200">Limited evidence</div>
              ) : null}
            </div>
            <div className="rounded border border-violet-400/30 bg-violet-500/10 p-2">
              {INTELLIGENCE_LABELS.styleDrift} (all)
              <br />
              <span className="text-zinc-100">{styleDriftIssues.length}</span>
            </div>
            <div className="rounded border border-rose-400/30 bg-rose-500/10 p-2">
              High severity drift
              <br />
              <span className="text-zinc-100">{styleDriftIssues.filter((i) => i.severity === 'high').length}</span>
            </div>
            <div className="rounded border border-amber-400/30 bg-amber-500/10 p-2">
              Med / low drift
              <br />
              <span className="text-zinc-100">
                {styleDriftIssues.filter((i) => i.severity === 'medium').length} /{' '}
                {styleDriftIssues.filter((i) => i.severity === 'low').length}
              </span>
            </div>
          </div>
        </section>

        <section className="mt-4">
          <CrewOpsDashboard
            assetCount={assets.length}
            totalKeyframes={videoKeyframes.length}
            completedAnalysesCount={completedFrameAnalyses}
            totalEmbeddings={embeddedKeyframeCount}
            memoryRecordCount={cinematicMemory.length}
            continuityIssueCount={continuityIssues.length}
            styleDriftIssueCount={styleDriftIssues.length}
            hasDirectorSignature={Boolean(directorSignature)}
            directorSignatureConfidence={directorSignature?.confidence ?? 0}
          />
        </section>

        {!hasAnyOps ? (
          <section className="mt-4 rounded-2xl border border-dashed border-zinc-700 bg-zinc-950/60 p-4 text-sm text-zinc-400">
            No active crew operations yet.
          </section>
        ) : null}

        <section className="mt-4 rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">Active Render Jobs</h3>
            <Link to={withProjectQuery('/studio/production-board', activeProjectId)} className="text-xs text-cyan-300 no-underline">Open Production Board</Link>
          </div>
          <div className="mt-3 space-y-2">
            {jobs.length === 0 ? <div className="text-xs text-zinc-500">No render jobs yet.</div> : jobs.slice(0, 10).map((job) => (
              <div key={job.id} className="rounded border border-white/10 bg-black/25 p-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-zinc-100">{job.id}</span>
                  <span className={`rounded border px-1.5 py-0.5 ${statusPill(job.status)}`}>{job.status}</span>
                  <span className="text-zinc-400">provider: {job.provider}</span>
                </div>
                <div className="mt-1 text-zinc-400">project_id: {job.project_id} • shot_id: {job.shot_id} • task_id: {job.provider_job_id || 'n/a'}</div>
                <div className="mt-1 text-zinc-400">created_at: {job.created_at}</div>
                {outputUrl(job) ? <a href={outputUrl(job)} target="_blank" rel="noreferrer" className="mt-1 inline-block text-cyan-300">{outputUrl(job)}</a> : null}
              </div>
            ))}
          </div>
        </section>

        <section className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">Failed Jobs Needing Attention</h3>
            <div className="mt-3 space-y-2">
              {failedJobs.length === 0 ? <div className="text-xs text-zinc-500">No failed jobs.</div> : failedJobs.slice(0, 8).map((job) => (
                <div key={job.id} className="rounded border border-rose-400/30 bg-rose-500/10 p-2 text-xs">
                  <div className="font-semibold text-rose-100">{job.id}</div>
                  <div className="text-rose-200/90">{job.error_message || 'No error message provided.'}</div>
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await reconcileRenderJob(job.id)
                          setMessage(`Reconciled ${job.id}`)
                        } catch (err) {
                          setMessage(err instanceof Error ? err.message : `Failed to reconcile ${job.id}`)
                        }
                      }}
                      className="rounded border border-rose-300/50 bg-rose-500/20 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-rose-100"
                    >
                      Recover/Reconcile
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await retryRenderJobById(job.id)
                          setMessage(`Retried ${job.id}`)
                        } catch (err) {
                          setMessage(err instanceof Error ? err.message : `Failed to retry ${job.id}`)
                        }
                      }}
                      className="rounded border border-amber-300/50 bg-amber-500/20 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-amber-100"
                    >
                      Retry
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">Provider Status</h3>
            <div className="mt-3 space-y-2">
              {providers.length === 0 ? <div className="text-xs text-zinc-500">No provider status available.</div> : providers.map((provider) => (
                <div key={provider.provider_id} className="rounded border border-white/10 bg-black/25 p-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-zinc-100">{provider.name}</span>
                    <span className={`rounded border px-1.5 py-0.5 ${statusPill(provider.status)}`}>{provider.status}</span>
                  </div>
                  <div className="mt-1 text-zinc-400">active: {provider.active_jobs} • queued: {provider.queued_jobs}</div>
                  <div className="mt-1 text-zinc-400">{provider.provider_id === 'runway' ? 'Runway available.' : provider.is_simulated ? 'Simulated provider.' : 'Provider available.'}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">Pending Reviews</h3>
            <div className="mt-3 space-y-2">
              {pendingReviews.length === 0 ? <div className="text-xs text-zinc-500">No pending reviews.</div> : pendingReviews.map((review) => (
                <div key={review.review_id} className="rounded border border-white/10 bg-black/25 p-2 text-xs">
                  <div className="font-semibold text-zinc-100">{review.review_id}</div>
                  <div className={`mt-1 inline-flex rounded border px-1.5 py-0.5 ${statusPill(review.decision)}`}>{review.decision}</div>
                  <div className="mt-1 text-zinc-400">{review.notes || 'No notes.'}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">Pending Clip Revisions</h3>
            <div className="mt-3 space-y-2">
              {pendingRevisions.length === 0 ? <div className="text-xs text-zinc-500">No pending revisions.</div> : pendingRevisions.map((revision) => (
                <div key={revision.revision_id} className="rounded border border-white/10 bg-black/25 p-2 text-xs">
                  <div className="font-semibold text-zinc-100">{revision.revision_id}</div>
                  <div className={`mt-1 inline-flex rounded border px-1.5 py-0.5 ${statusPill(revision.status)}`}>{revision.status}</div>
                  <div className="mt-1 text-zinc-400">provider: {revision.provider} • job: {revision.original_job_id}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">Video Assets Awaiting Study</h3>
            <div className="mt-3 space-y-2">
              {assetsAwaitingStudy.length === 0 ? <div className="text-xs text-zinc-500">No assets awaiting study.</div> : assetsAwaitingStudy.slice(0, 12).map((asset) => (
                <div key={asset.asset_id} className="rounded border border-white/10 bg-black/25 p-2 text-xs">
                  <div className="font-semibold text-zinc-100">{asset.title}</div>
                  <div className="text-zinc-400">{asset.asset_id} • {asset.source_type} • {asset.status}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">Final Packages</h3>
            <div className="mt-3 space-y-2">
              {packages.length === 0 ? <div className="text-xs text-zinc-500">No final packages yet.</div> : packages.slice(0, 10).map((pkg) => (
                <div key={pkg.package_id} className="rounded border border-white/10 bg-black/25 p-2 text-xs">
                  <div className="font-semibold text-zinc-100">{pkg.film_title}</div>
                  <div className={`mt-1 inline-flex rounded border px-1.5 py-0.5 ${statusPill(pkg.package_status)}`}>{pkg.package_status}</div>
                  <div className="mt-1 text-zinc-400">{pkg.package_id}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {message ? <div className="mt-4 rounded border border-cyan-400/30 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-100">{message}</div> : null}
      </div>
    </StudioShell>
  )
}

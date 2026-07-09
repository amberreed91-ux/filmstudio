import { useCallback, useMemo, useState } from 'react'
import {
  createProject,
  createRenderJob,
  generateScenes,
  generateShortFilmWorkflow,
  getProject,
  getRenderJobOutputs,
  getRenderJobStatus,
  submitRenderJob,
  STUDIO_API_BASE,
  stitchShortFilm,
  reconcileRenderJob,
  createShortFilmReview,
  getLatestShortFilmReview,
  updateShortFilmReviewDecision,
  createClipRevision,
  listClipRevisionsForProject,
  submitClipRevisionRender,
  restitchProjectWithRevisions,
  createFinalShortFilmPackage,
  updateFinalShortFilmPackageStatus,
  type PersistedProjectState,
  type RenderJob,
  type ShortFilmStitchResult,
  type ShortFilmReview,
  type ClipRevision,
  type FinalShortFilmPackage,
} from '../lib/studioApi'
import { useStudio } from '../context/StudioContext'
import { useAsyncAction } from '../hooks/useAsyncAction'
import { useProviderStatus } from '../hooks/useProviderStatus'
import { useRenderPolling } from '../hooks/useRenderPolling'

type SandboxMode = 'one_button' | 'manual'
type SandboxState = 'idle' | 'generating' | 'rendering' | 'assembling' | 'completed' | 'failed'
type ProviderOption = 'runway' | 'simulated'
type SoundtrackType = 'generated_placeholder' | 'local_file'

type RenderRow = {
  scene_id: string
  shot_id: string
  job_id: string
  task_id?: string
  provider: string
  status: string
  output_url?: string
  preview_url?: string
  error_message?: string
}

const DEFAULT_SCRIPT = `Scene 1:
A woman named Mara walks alone through neon rain, clutching an old cassette tape. She hears her father's voice in her memory.

Scene 2:
Mara enters an empty subway station. The lights flicker. She plays the tape and realizes the message was meant for tonight.`

function asArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((v): v is Record<string, unknown> => typeof v === 'object' && v !== null) : []
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function normalizeJobToRenderRow(sceneId: string, shotId: string, job: RenderJob, outputUrl?: string, previewUrl?: string): RenderRow {
  return {
    scene_id: sceneId,
    shot_id: shotId,
    job_id: job.id,
    task_id: job.provider_job_id || '',
    provider: job.provider,
    status: job.status,
    output_url: outputUrl || job.output_payload?.asset_url || '',
    preview_url: previewUrl || job.output_payload?.thumbnail_url || '',
    error_message: job.error_message || '',
  }
}

function resolveMediaUrl(url: string): string {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  if (url.startsWith('/')) return `${STUDIO_API_BASE}${url}`
  return `${STUDIO_API_BASE}/${url}`
}

export default function SandboxShortFilmPanel() {
  const { setSelectedRenderProvider } = useStudio()
  const [mode, setMode] = useState<SandboxMode>('one_button')
  const [state, setState] = useState<SandboxState>('idle')
  const [error, setError] = useState('')
  const [blockers, setBlockers] = useState<string[]>([])

  const [projectTitle, setProjectTitle] = useState('Neon Rain Test Film')
  const [genre, setGenre] = useState('moody sci-fi drama')
  const [tone, setTone] = useState('lonely, cinematic, atmospheric')
  const [visualStyle, setVisualStyle] = useState('neon rain, reflective streets, A24-inspired realism')
  const [scriptText, setScriptText] = useState(DEFAULT_SCRIPT)
  const [provider, setProvider] = useState<ProviderOption>('runway')
  const [submitRenders, setSubmitRenders] = useState(true)
  const [assembleFinal, setAssembleFinal] = useState(false)
  const [useMockSuccess, setUseMockSuccess] = useState(false)

  const [projectId, setProjectId] = useState('')
  const [projectLookupId, setProjectLookupId] = useState('')
  const [jobLookupId, setJobLookupId] = useState('')
  const [recoveryMessage, setRecoveryMessage] = useState('')
  const [scenes, setScenes] = useState<Array<Record<string, unknown>>>([])
  const [shots, setShots] = useState<Array<Record<string, unknown>>>([])
  const [renderRows, setRenderRows] = useState<RenderRow[]>([])
  const [stitchResult, setStitchResult] = useState<ShortFilmStitchResult | null>(null)
  const [lastRequestPayload, setLastRequestPayload] = useState<Record<string, unknown> | null>(null)
  const [lastResponseSummary, setLastResponseSummary] = useState<Record<string, unknown> | null>(null)
  const [enableTitleCard, setEnableTitleCard] = useState(false)
  const [titleCardText, setTitleCardText] = useState('Neon Rain')
  const [enableEndCard, setEnableEndCard] = useState(false)
  const [endCardText, setEndCardText] = useState('THE END')
  const [enableSoundtrack, setEnableSoundtrack] = useState(false)
  const [soundtrackType, setSoundtrackType] = useState<SoundtrackType>('generated_placeholder')
  const [soundtrackAudioPath, setSoundtrackAudioPath] = useState('')
  const [soundtrackAudioUrl, setSoundtrackAudioUrl] = useState('')
  const [soundtrackVolume, setSoundtrackVolume] = useState(0.25)
  const [soundtrackFadeIn, setSoundtrackFadeIn] = useState(1)
  const [soundtrackFadeOut, setSoundtrackFadeOut] = useState(1)

  // Review state
  const [latestReview, setLatestReview] = useState<ShortFilmReview | null>(null)
  const [reviewNotes, setReviewNotes] = useState('')
  const [reviewerName, setReviewerName] = useState('')

  // Clip revision state
  const [clipRevisions, setClipRevisions] = useState<ClipRevision[]>([])
  const [selectedJobForRevision, setSelectedJobForRevision] = useState<string>('')
  const [revisionPrompt, setRevisionPrompt] = useState('')
  const [revisionReason, setRevisionReason] = useState('')
  const [revisionStatus, setRevisionStatus] = useState<'idle' | 'creating' | 'submitting' | 'completed' | 'error'>('idle')
  const [revisionError, setRevisionError] = useState('')
  const [revisedStitchResult, setRevisedStitchResult] = useState<ShortFilmStitchResult | null>(null)

  // Final short film package state
  const [latestPackage, setLatestPackage] = useState<FinalShortFilmPackage | null>(null)
  const [packageStatus, setPackageStatus] = useState<'idle' | 'creating' | 'updating' | 'completed' | 'error'>('idle')
  const [packageError, setPackageError] = useState('')
  const providerStatus = useProviderStatus(provider, useMockSuccess)
  const { pollUntilTerminal } = useRenderPolling<RenderJob>({
    isTerminal: (job) => ['complete', 'failed', 'cancelled'].includes(job.status),
    getStatus: getRenderJobStatus,
    intervalMs: 5000, // Reduced from 10s to 5s
    timeoutMs: 10 * 60 * 1000,
    adaptive: true, // Enable adaptive polling
  })

  const isLocal = import.meta.env.DEV || ['localhost', '127.0.0.1'].includes(window.location.hostname)
  const estimatedGenerations = useMemo(() => {
    const sceneMatches = scriptText.match(/^\s*Scene\s+\d+\s*:/gim)
    const sceneCount = sceneMatches?.length || 0
    const perScene = 2
    return Math.max(1, sceneCount * perScene)
  }, [scriptText])

  async function createSandboxProject() {
    const created = await createProject({ title: projectTitle || 'Sandbox Short Film' })
    if (!created.project?.project_id) {
      throw new Error(created.error || 'Unable to create sandbox project')
    }
    return created.project
  }

  function applyProjectSummary(nextProject: PersistedProjectState) {
    const summary = nextProject.execution_summary || {}
    const nextScenes = asArray(summary.scenes)
    const nextShots = asArray(summary.shot_candidates)
    setScenes(nextScenes)
    setShots(nextShots)
    const oneButtonJobs = asArray((summary as Record<string, unknown>).one_button_render_jobs).map((row) => ({
      scene_id: asString(row.scene_id),
      shot_id: asString(row.shot_id),
      job_id: asString(row.job_id),
      task_id: asString(row.task_id),
      provider: asString(row.provider),
      status: asString(row.status),
      output_url: asString(row.output_url),
      preview_url: asString(row.preview_url),
      error_message: asString(row.error_message),
    }))
    setRenderRows(oneButtonJobs)
    const assembly = (summary as Record<string, unknown>).one_button_assembly as Record<string, unknown> | undefined
    const nextBlockers = Array.isArray(assembly?.blockers) ? assembly.blockers.map((b) => String(b)) : []
    setBlockers(nextBlockers)
  }

  async function onLoadProject() {
    const lookupId = projectLookupId.trim()
    if (!lookupId) return
    setError('')
    setBlockers([])
    setState('generating')
    try {
      const result = await getProject(lookupId)
      if (!result.project) throw new Error(result.error || 'Unable to load project')
      setProjectId(result.project.project_id)
      applyProjectSummary(result.project)
      setStitchResult(null)
      setState('completed')
    } catch (err) {
      setState('failed')
      setError(err instanceof Error ? err.message : 'Failed to load project')
    }
  }

  async function onRecoverJob() {
    const lookupId = jobLookupId.trim()
    if (!lookupId) return
    setRecoveryMessage('')
    setError('')
    try {
      const reconciled = await reconcileRenderJob(lookupId)
      const outputUrl = reconciled.output_payload?.asset_url || ''
      const previewUrl = reconciled.output_payload?.thumbnail_url || ''
      setRecoveryMessage(
        `Job ${lookupId}: status=${reconciled.status}, output_url=${outputUrl || 'none'}`,
      )
      // Update row if it exists in current renderRows
      setRenderRows((prev) =>
        prev.map((row) =>
          row.job_id === lookupId
            ? { ...row, status: reconciled.status, output_url: outputUrl, preview_url: previewUrl }
            : row,
        ),
      )
    } catch (err) {
      setRecoveryMessage(`Recovery failed: ${err instanceof Error ? err.message : err}`)
    }
  }

  async function runManualRenderFlow(project: PersistedProjectState, sceneRows: Array<Record<string, unknown>>, shotRows: Array<Record<string, unknown>>) {
    if (!submitRenders) return []
    const rows: RenderRow[] = []
    setState('rendering')

    for (const shot of shotRows) {
      const shotId = asString(shot.shot_id) || `shot_${rows.length + 1}`
      const sceneId = asString(shot.scene_id) || asString(sceneRows[rows.length]?.scene_id) || 'scene_unknown'
      const prompt = asString(shot.prompt) || `Cinematic short film shot for ${sceneId}`
      const createdJob = await createRenderJob({
        project_id: project.project_id,
        shot_id: shotId,
        provider: provider === 'simulated' ? 'simulated' : 'runway',
        prompt,
        parameters: { ratio: '1280:720', duration: 5 },
      })
      let submitted = await submitRenderJob(createdJob.id)
      const polled = await pollUntilTerminal(createdJob.id)
      submitted = polled || submitted

      const outputs = await getRenderJobOutputs(createdJob.id)
      const outputUrl = outputs[0]?.url || ''
      const previewUrl = outputs[0]?.thumbnail_url || ''
      rows.push(normalizeJobToRenderRow(sceneId, shotId, submitted, outputUrl, previewUrl))
    }
    return rows
  }

  const onRun = useCallback(async () => {
    setState('generating')
    setError('')
    setBlockers([])
    setScenes([])
    setShots([])
    setRenderRows([])
    setStitchResult(null)
    setSelectedRenderProvider(providerStatus.selectedProviderKey as 'runway' | 'simulated' | 'mock_success')
    try {
      const project = await createSandboxProject()
      setProjectId(project.project_id)

      if (mode === 'one_button') {
        const manualOverrides: Record<string, unknown> = {
          genre,
          tone,
          visual_style: visualStyle,
          provider: provider === 'simulated' ? 'simulated' : 'runway',
          ratio: '1280:720',
          max_scenes: 2,
          max_shots_per_scene: 2,
          duration_per_shot_seconds: 5,
        }
        const requestPayload = {
          concept: scriptText,
          manual_overrides: {
            ...manualOverrides,
            use_mock_success: useMockSuccess,
          },
          submit_renders: submitRenders,
          assemble_final: assembleFinal,
        }
        setLastRequestPayload(requestPayload)

        const result = await generateShortFilmWorkflow(project.project_id, scriptText, requestPayload.manual_overrides as Record<string, unknown>, {
          submitRenders,
          assembleFinal,
        })
        if (!result.project) throw new Error(result.error || 'One-button generation failed')

        applyProjectSummary(result.project)
        const summary = result.project.execution_summary || {}
        const assembly = (summary as Record<string, unknown>).one_button_assembly as Record<string, unknown> | undefined
        const nextBlockers = Array.isArray(assembly?.blockers) ? assembly.blockers.map((b) => String(b)) : []
        const oneButtonJobs = asArray((summary as Record<string, unknown>).one_button_render_jobs)
        const firstJob = oneButtonJobs[0] || {}
        setLastResponseSummary({
          project_id: result.project.project_id,
          render_jobs_count: oneButtonJobs.length,
          first_job_status: asString((firstJob as Record<string, unknown>).status),
          first_output_url: asString((firstJob as Record<string, unknown>).output_url),
          blockers: nextBlockers,
        })
        if (submitRenders && assembleFinal && !nextBlockers.length) setState('assembling')
      } else {
        const generated = await generateScenes(project.project_id, scriptText)
        if (!generated.project) throw new Error(generated.error || 'Manual script ingestion failed')
        const summary = generated.project.execution_summary || {}
        const nextScenes = asArray(summary.scenes).slice(0, 2)
        const nextShots = asArray(summary.shot_candidates).slice(0, 4)
        setScenes(nextScenes)
        setShots(nextShots)
        const jobs = await runManualRenderFlow(project, nextScenes, nextShots)
        setRenderRows(jobs)
      }

      setState('completed')
    } catch (err) {
      setState('failed')
      setError(err instanceof Error ? err.message : 'Sandbox run failed')
    }
  }, [
    assembleFinal,
    genre,
    mode,
    pollUntilTerminal,
    projectTitle,
    provider,
    providerStatus.selectedProviderKey,
    scriptText,
    setSelectedRenderProvider,
    submitRenders,
    tone,
    useMockSuccess,
    visualStyle,
  ])

  const runAction = useAsyncAction(onRun, { preventConcurrent: true })

  const onStitchShortFilm = useCallback(async () => {
    if (!projectId) return
    setError('')
    setState('assembling')
    try {
      const stitched = await stitchShortFilm(
        projectId,
        false,
        {
          enabled: enableTitleCard,
          title_text: titleCardText,
          duration_seconds: 3,
          style: 'cinematic',
          background_color: 'black',
          text_color: 'white',
        },
        {
          enabled: enableEndCard,
          text: endCardText,
          duration_seconds: 3,
          style: 'cinematic',
        },
        {
          enabled: enableSoundtrack,
          audio_source_type: enableSoundtrack ? soundtrackType : 'none',
          audio_url: soundtrackAudioUrl,
          local_audio_path: soundtrackAudioPath,
          volume: soundtrackVolume,
          fade_in_seconds: soundtrackFadeIn,
          fade_out_seconds: soundtrackFadeOut,
          loop_to_duration: true,
          style_label: soundtrackType === 'generated_placeholder' ? 'placeholder' : 'local',
        },
      )
      if (!stitched.result) throw new Error(stitched.error || 'Short film stitching failed')
      setStitchResult(stitched.result)
      if (stitched.result.status === 'completed' || stitched.result.status === 'existing') {
        setState('completed')
        // Load latest review after successful stitch
        await loadLatestReview()
      } else {
        setState('failed')
      }
    } catch (err) {
      setState('failed')
      setError(err instanceof Error ? err.message : 'Stitching failed')
    }
  }, [
    enableEndCard,
    enableSoundtrack,
    enableTitleCard,
    endCardText,
    projectId,
    soundtrackAudioPath,
    soundtrackAudioUrl,
    soundtrackFadeIn,
    soundtrackFadeOut,
    soundtrackType,
    soundtrackVolume,
    titleCardText,
  ])

  const stitchAction = useAsyncAction(onStitchShortFilm, { preventConcurrent: true })

  async function loadLatestReview() {
    if (!projectId) return
    try {
      const result = await getLatestShortFilmReview(projectId)
      setLatestReview(result.review)
    } catch (err) {
      // No reviews exist yet, which is fine
      setLatestReview(null)
    }
  }

  async function onCreateReview() {
    if (!projectId || !stitchResult?.output_url) return
    try {
      const result = await createShortFilmReview(projectId, {
        output_url: stitchResult.output_url,
        reviewer: reviewerName,
        notes: reviewNotes,
      })
      setLatestReview(result.review)
      setReviewNotes('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create review')
    }
  }

  async function onUpdateReviewDecision(decision: 'approved' | 'needs_revision' | 'rejected') {
    if (!latestReview) return
    try {
      const result = await updateShortFilmReviewDecision(projectId, latestReview.review_id, {
        decision,
        reviewer: reviewerName,
        notes: reviewNotes,
      })
      setLatestReview(result.review)
      setReviewNotes('')
      
      // Load revisions when decision changes
      if (decision === 'needs_revision' || decision === 'rejected') {
        await loadClipRevisions()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update review decision')
    }
  }

  async function loadClipRevisions() {
    if (!projectId) return
    try {
      const result = await listClipRevisionsForProject(projectId)
      setClipRevisions(result.revisions)
    } catch (err) {
      console.error('Failed to load clip revisions:', err)
    }
  }

  async function onCreateClipRevision() {
    if (!projectId || !latestReview || !selectedJobForRevision || !revisionPrompt || !revisionReason) return
    
    setRevisionStatus('creating')
    setRevisionError('')
    
    try {
      const selectedRender = renderRows.find(row => row.job_id === selectedJobForRevision)
      if (!selectedRender) {
        throw new Error('Selected render job not found')
      }
      
      const result = await createClipRevision(projectId, {
        review_id: latestReview.review_id,
        original_job_id: selectedJobForRevision,
        provider: selectedRender.provider,
        revision_prompt: revisionPrompt,
        revision_reason: revisionReason,
      })
      
      setClipRevisions(prev => [result.revision, ...prev])
      setRevisionStatus('completed')
      
      // Auto-submit the revision for rendering
      await onSubmitClipRevision(result.revision.revision_id)
    } catch (err) {
      setRevisionStatus('error')
      setRevisionError(err instanceof Error ? err.message : 'Failed to create clip revision')
    }
  }

  async function onSubmitClipRevision(revisionId: string) {
    setRevisionStatus('submitting')
    setRevisionError('')
    
    try {
      const result = await submitClipRevisionRender(revisionId, {})
      setClipRevisions(prev => prev.map(r => r.revision_id === revisionId ? result.revision : r))
      setRevisionStatus('completed')
      
      // Clear form
      setSelectedJobForRevision('')
      setRevisionPrompt('')
      setRevisionReason('')
    } catch (err) {
      setRevisionStatus('error')
      setRevisionError(err instanceof Error ? err.message : 'Failed to submit clip revision')
    }
  }

  async function onRestitchWithRevisions() {
    if (!projectId) return
    
    // Get completed revisions with output URLs
    const completedRevisions = clipRevisions.filter(r => r.status === 'complete' && r.output_url)
    if (completedRevisions.length === 0) {
      setError('No completed revisions found to restitch with')
      return
    }
    
    // Build revision overrides map
    const revisionOverrides: Record<string, string> = {}
    completedRevisions.forEach(revision => {
      revisionOverrides[revision.original_job_id] = revision.output_url!
    })
    
    try {
      const result = await restitchProjectWithRevisions(projectId, {
        revision_overrides: revisionOverrides,
        overwrite: true,
        title_card: {
          enabled: enableTitleCard,
          title_text: titleCardText,
          duration_seconds: 3,
          style: 'cinematic',
          background_color: 'black',
          text_color: 'white',
        },
        end_card: {
          enabled: enableEndCard,
          text: endCardText,
          duration_seconds: 3,
          style: 'cinematic',
        },
        soundtrack: {
          enabled: enableSoundtrack,
          audio_source_type: enableSoundtrack ? soundtrackType : 'none',
          audio_url: soundtrackAudioUrl,
          local_audio_path: soundtrackAudioPath,
          volume: soundtrackVolume,
          fade_in_seconds: soundtrackFadeIn,
          fade_out_seconds: soundtrackFadeOut,
          loop_to_duration: true,
          style_label: soundtrackType === 'generated_placeholder' ? 'placeholder' : 'local',
        },
      })
      
      setRevisedStitchResult(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to restitch with revisions')
    }
  }

  
  async function onCreateFinalPackage() {
    if (!projectId) return
    
    // Use the latest stitched result or revised result as final output
    let finalOutput = stitchResult
    if (revisedStitchResult && revisedStitchResult.status === 'completed') {
      finalOutput = revisedStitchResult
    }
    
    if (!finalOutput || !finalOutput.output_url) {
      setError('No final output available. Please stitch the film first.')
      return
    }
    
    setPackageStatus('creating')
    setPackageError('')
    
    try {
      const result = await createFinalShortFilmPackage(projectId, {
        film_title: projectTitle || 'Sandbox Short Film',
        final_output_url: finalOutput.output_url,
        final_output_path: finalOutput.output_path,
        has_title_card: enableTitleCard,
        has_end_card: enableEndCard,
        has_soundtrack: enableSoundtrack,
        metadata: {
          created_by: 'sandbox',
          provider: provider,
          scene_count: renderRows.length,
          shot_count: renderRows.length,
        },
      })
      
      setLatestPackage(result.package)
      setPackageStatus('completed')
    } catch (err) {
      setPackageStatus('error')
      setPackageError(err instanceof Error ? err.message : 'Failed to create final package')
    }
  }

  async function onUpdatePackageStatus(newStatus: string) {
    if (!latestPackage) return
    
    setPackageStatus('updating')
    setPackageError('')
    
    try {
      const result = await updateFinalShortFilmPackageStatus(latestPackage.package_id, {
        package_status: newStatus,
      })
      
      setLatestPackage(result.package)
      setPackageStatus('completed')
    } catch (err) {
      setPackageStatus('error')
      setPackageError(err instanceof Error ? err.message : 'Failed to update package status')
    }
  }

  const hasCompletedRenderOutputs = renderRows.some((row) => row.status === 'complete' && Boolean(row.output_url))
  const showRevisionControls = latestReview && (latestReview.decision === 'needs_revision' || latestReview.decision === 'rejected')
  const completedRevisions = clipRevisions.filter(r => r.status === 'complete' && r.output_url)
  const canRestitch = completedRevisions.length > 0

  return (
    <section className="studio-surface studio-fade-in p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.14em] text-cyan-200">Sandbox Short Film</div>
          <p className="mt-1 text-xs text-zinc-300">Run one-button or manual sandbox generation and review outputs safely.</p>
        </div>
        <div className="rounded-full border border-white/15 bg-black/30 px-3 py-1 text-[10px] uppercase tracking-[0.12em] text-zinc-200">
          State: {state}
        </div>
      </div>
      <details className="mt-2 rounded-lg border border-zinc-700/70 bg-black/35 p-2 text-[11px] text-zinc-300">
        <summary className="cursor-pointer list-none text-[10px] uppercase tracking-[0.12em] text-zinc-400">Diagnostics</summary>
        <div className="mt-2 space-y-1">
          <div>API_BASE_URL: {STUDIO_API_BASE}</div>
          <div>selected provider: {provider}</div>
          <div>submit_renders: {String(submitRenders)}</div>
          <div>assemble_final: {String(assembleFinal)}</div>
          <div>use_mock_success: {String(useMockSuccess)}</div>
          <div>request payload: {lastRequestPayload ? JSON.stringify(lastRequestPayload) : 'n/a'}</div>
          <div>response payload summary: {lastResponseSummary ? JSON.stringify(lastResponseSummary) : 'n/a'}</div>
        </div>
      </details>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <input value={projectTitle} onChange={(e) => setProjectTitle(e.target.value)} className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100" placeholder="Project title" />
        <select value={mode} onChange={(e) => setMode(e.target.value as SandboxMode)} className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100">
          <option value="one_button">One-button mode</option>
          <option value="manual">Manual script mode</option>
        </select>
        <input value={genre} onChange={(e) => setGenre(e.target.value)} className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100" placeholder="Genre" />
        <input value={tone} onChange={(e) => setTone(e.target.value)} className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100" placeholder="Tone" />
        <input value={visualStyle} onChange={(e) => setVisualStyle(e.target.value)} className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100 md:col-span-2" placeholder="Visual style" />
        <textarea value={scriptText} onChange={(e) => setScriptText(e.target.value)} className="md:col-span-2 min-h-[120px] rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100" />
        <select value={provider} onChange={(e) => setProvider(e.target.value as ProviderOption)} className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100">
          <option value="runway">runway</option>
          {isLocal ? <option value="simulated">simulated/mock_success</option> : null}
        </select>
        <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-200">
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={submitRenders} onChange={(e) => setSubmitRenders(e.target.checked)} /> submit_renders</label>
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={assembleFinal} onChange={(e) => setAssembleFinal(e.target.checked)} /> assemble_final</label>
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={useMockSuccess} onChange={(e) => setUseMockSuccess(e.target.checked)} /> use_mock_success</label>
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-amber-300/35 bg-amber-500/10 p-2 text-xs text-amber-100">
        Estimated generations: {estimatedGenerations}. {provider === 'runway' ? 'Real Runway provider selected.' : 'Simulated/local mode selected.'}
        {provider === 'runway' ? ' Verify credits and costs before submit.' : ''}
      </div>
      {useMockSuccess ? (
        <div className="mt-2 rounded-lg border border-cyan-300/35 bg-cyan-500/10 p-2 text-xs text-cyan-100">
          Mock success requires backend env: `APP_ENV=local|test` and `RENDER_PROVIDER_TEST_MODE=mock_success`.
        </div>
      ) : null}

      <button
        type="button"
          onClick={() => void runAction.run()}
        disabled={runAction.isRunning || state === 'generating' || state === 'rendering' || state === 'assembling'}
        className="mt-3 rounded-lg border border-cyan-300/55 bg-cyan-500/18 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100 disabled:opacity-50"
      >
        Run Sandbox Flow
      </button>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          value={projectLookupId}
          onChange={(e) => setProjectLookupId(e.target.value)}
          className="w-full max-w-md rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
          placeholder="Load existing project_id for read-only playback check"
        />
        <button
          type="button"
          onClick={onLoadProject}
          disabled={state === 'generating' || state === 'rendering' || state === 'assembling'}
          className="rounded-lg border border-zinc-500/55 bg-zinc-700/30 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100 disabled:opacity-50"
        >
          Load Project
        </button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          value={jobLookupId}
          onChange={(e) => setJobLookupId(e.target.value)}
          className="w-full max-w-md rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
          placeholder="Recover a stuck job — paste job_id to reconcile and get output"
        />
        <button
          type="button"
          onClick={onRecoverJob}
          disabled={state === 'generating' || state === 'rendering' || state === 'assembling'}
          className="rounded-lg border border-cyan-500/55 bg-cyan-700/30 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-200 disabled:opacity-50"
        >
          Recover Job
        </button>
      </div>
      {recoveryMessage ? (
        <div className="mt-2 rounded-lg border border-cyan-300/35 bg-cyan-500/10 p-2 text-xs text-cyan-100">{recoveryMessage}</div>
      ) : null}
      <div className="mt-2 grid gap-2 md:grid-cols-2">
        <label className="inline-flex items-center gap-2 text-xs text-zinc-200">
          <input type="checkbox" checked={enableTitleCard} onChange={(e) => setEnableTitleCard(e.target.checked)} />
          enable title card
        </label>
        <input
          value={titleCardText}
          onChange={(e) => setTitleCardText(e.target.value)}
          className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
          placeholder="Title text"
        />
        <label className="inline-flex items-center gap-2 text-xs text-zinc-200">
          <input type="checkbox" checked={enableEndCard} onChange={(e) => setEnableEndCard(e.target.checked)} />
          enable end card
        </label>
        <input
          value={endCardText}
          onChange={(e) => setEndCardText(e.target.value)}
          className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
          placeholder="End text"
        />
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-2">
        <label className="inline-flex items-center gap-2 text-xs text-zinc-200">
          <input type="checkbox" checked={enableSoundtrack} onChange={(e) => setEnableSoundtrack(e.target.checked)} />
          enable soundtrack
        </label>
        <select
          value={soundtrackType}
          onChange={(e) => setSoundtrackType(e.target.value as SoundtrackType)}
          className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
        >
          <option value="generated_placeholder">generated placeholder</option>
          <option value="local_file">local file</option>
        </select>
        <input
          value={soundtrackAudioPath}
          onChange={(e) => setSoundtrackAudioPath(e.target.value)}
          className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
          placeholder="local audio path (optional)"
        />
        <input
          value={soundtrackAudioUrl}
          onChange={(e) => setSoundtrackAudioUrl(e.target.value)}
          className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
          placeholder="audio URL (optional)"
        />
        <label className="text-xs text-zinc-200">
          volume: {soundtrackVolume.toFixed(2)}
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={soundtrackVolume}
            onChange={(e) => setSoundtrackVolume(Number(e.target.value))}
            className="mt-1 w-full"
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <input
            type="number"
            min={0}
            step={0.5}
            value={soundtrackFadeIn}
            onChange={(e) => setSoundtrackFadeIn(Number(e.target.value))}
            className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
            placeholder="fade in (s)"
          />
          <input
            type="number"
            min={0}
            step={0.5}
            value={soundtrackFadeOut}
            onChange={(e) => setSoundtrackFadeOut(Number(e.target.value))}
            className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
            placeholder="fade out (s)"
          />
        </div>
      </div>
      {projectId ? <div className="mt-2 text-[11px] text-zinc-300">Project: {projectId}</div> : null}
      {error ? <div className="mt-2 text-xs text-rose-300">{error}</div> : null}
      {hasCompletedRenderOutputs ? (
        <button
          type="button"
          onClick={() => void stitchAction.run()}
          disabled={stitchAction.isRunning || state === 'generating' || state === 'rendering' || state === 'assembling'}
          className="mt-2 rounded-lg border border-emerald-300/55 bg-emerald-500/18 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-emerald-100 disabled:opacity-50"
        >
          Stitch Short Film
        </button>
      ) : null}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/35 p-3">
          <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-300">Scenes Generated</div>
          <div className="mt-2 text-xs text-zinc-100">{scenes.length}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/35 p-3">
          <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-300">Shot Candidates</div>
          <div className="mt-2 text-xs text-zinc-100">{shots.length}</div>
        </div>
      </div>

      {blockers.length > 0 ? (
        <div className="mt-3 rounded-lg border border-rose-300/30 bg-rose-500/10 p-3 text-xs text-rose-100">
          <div className="font-semibold uppercase tracking-[0.1em]">Blockers</div>
          {blockers.map((b) => <div key={b} className="mt-1">{b}</div>)}
        </div>
      ) : null}

      <div className="mt-4 space-y-3">
        {renderRows.map((row) => {
          async function refreshThisRow() {
            try {
              const refreshed = await reconcileRenderJob(row.job_id)
              const outputs = await getRenderJobOutputs(row.job_id)
              const outputUrl = outputs[0]?.url || ''
              const previewUrl = outputs[0]?.thumbnail_url || ''
              setRenderRows((prev) =>
                prev.map((r) =>
                  r.job_id === row.job_id
                    ? { ...r, status: refreshed.status, output_url: outputUrl, preview_url: previewUrl }
                    : r,
                ),
              )
            } catch {
              // best-effort refresh
            }
          }
          return (
            <article key={`${row.job_id}-${row.shot_id}`} className="rounded-lg border border-white/10 bg-black/35 p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="grid gap-1 text-[11px] text-zinc-200 md:grid-cols-2">
                  <div>Scene: {row.scene_id || 'n/a'}</div>
                  <div>Shot: {row.shot_id || 'n/a'}</div>
                  <div>Job: {row.job_id || 'n/a'}</div>
                  <div>Task: {row.task_id || 'n/a'}</div>
                  <div>Status: {row.status || 'n/a'}</div>
                  <div>Provider: {row.provider || 'n/a'}</div>
                </div>
                <button
                  type="button"
                  onClick={refreshThisRow}
                  className="shrink-0 rounded border border-cyan-400/40 bg-cyan-500/15 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-cyan-200 hover:bg-cyan-500/30"
                >
                  Refresh
                </button>
              </div>
              {row.error_message ? <div className="mt-2 text-xs text-rose-300">{row.error_message}</div> : null}
              <div className="mt-2 text-xs text-zinc-300 break-all">output_url: {row.output_url || 'n/a'}</div>
              <div className="mt-1 text-xs text-zinc-300 break-all">preview_url: {row.preview_url || 'n/a'}</div>
              {row.output_url ? (
                <video className="mt-2 w-full rounded border border-white/10" controls preload="metadata" src={row.output_url} />
              ) : null}
              {!row.output_url && row.preview_url ? (
                <video className="mt-2 w-full rounded border border-white/10" controls preload="metadata" src={row.preview_url} />
              ) : null}
            </article>
          )
        })}
      </div>

      {stitchResult ? (
        <article className="mt-4 rounded-lg border border-emerald-300/30 bg-emerald-500/10 p-3">
          <div className="text-[11px] uppercase tracking-[0.12em] text-emerald-100">Stitched Short Film</div>
          <div className="mt-1 text-xs text-emerald-50">status: {stitchResult.status}</div>
          <div className="mt-1 text-xs text-emerald-50">clip_count: {stitchResult.clip_count}</div>
          <div className="mt-1 text-xs text-emerald-50 break-all">output_url: {stitchResult.output_url}</div>
          {stitchResult.blocker ? <div className="mt-1 text-xs text-rose-200">blocker: {stitchResult.blocker}</div> : null}
          {(stitchResult.status === 'completed' || stitchResult.status === 'existing') && stitchResult.output_url ? (
            <video className="mt-2 w-full rounded border border-white/10" controls preload="metadata" src={resolveMediaUrl(stitchResult.output_url)} />
          ) : null}
          
          {/* Review Controls - only show when final stitched output exists */}
          {(stitchResult.status === 'completed' || stitchResult.status === 'existing') && stitchResult.output_url ? (
            <div className="mt-3 rounded-lg border border-blue-300/30 bg-blue-500/10 p-3">
              <div className="text-[11px] uppercase tracking-[0.12em] text-blue-100">Review Controls</div>
              
              {/* Latest Review Display */}
              {latestReview ? (
                <div className="mt-2 rounded border border-blue-200/20 bg-black/20 p-2">
                  <div className="text-xs text-blue-50">
                    <div className="font-semibold">Latest Review</div>
                    <div className="mt-1">Decision: <span className={`font-bold ${
                      latestReview.decision === 'approved' ? 'text-green-300' :
                      latestReview.decision === 'needs_revision' ? 'text-yellow-300' :
                      latestReview.decision === 'rejected' ? 'text-red-300' :
                      'text-gray-300'
                    }`}>{latestReview.decision}</span></div>
                    {latestReview.reviewer && <div className="mt-1">Reviewer: {latestReview.reviewer}</div>}
                    {latestReview.notes && <div className="mt-1">Notes: {latestReview.notes}</div>}
                    <div className="mt-1 text-[10px] text-gray-400">ID: {latestReview.review_id}</div>
                  </div>
                </div>
              ) : (
                <div className="mt-2 text-xs text-blue-50">No reviews yet. Create one below.</div>
              )}
              
              {/* Review Creation/Update Form */}
              <div className="mt-3 space-y-2">
                <input
                  type="text"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                  className="w-full rounded border border-blue-300/30 bg-black/40 p-2 text-xs text-blue-50 placeholder-blue-200/50"
                  placeholder="Reviewer name (optional)"
                />
                <textarea
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  className="w-full rounded border border-blue-300/30 bg-black/40 p-2 text-xs text-blue-50 placeholder-blue-200/50"
                  placeholder="Review notes (optional)"
                  rows={2}
                />
                
                {/* Action Buttons */}
                <div className="flex gap-2">
                  {!latestReview ? (
                    <button
                      type="button"
                      onClick={onCreateReview}
                      className="rounded border border-blue-300/50 bg-blue-500/20 px-3 py-1 text-xs font-semibold text-blue-100 hover:bg-blue-500/30"
                    >
                      Create Review
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => onUpdateReviewDecision('approved')}
                        className="rounded border border-green-300/50 bg-green-500/20 px-2 py-1 text-xs font-semibold text-green-100 hover:bg-green-500/30"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => onUpdateReviewDecision('needs_revision')}
                        className="rounded border border-yellow-300/50 bg-yellow-500/20 px-2 py-1 text-xs font-semibold text-yellow-100 hover:bg-yellow-500/30"
                      >
                        Needs Revision
                      </button>
                      <button
                        type="button"
                        onClick={() => onUpdateReviewDecision('rejected')}
                        className="rounded border border-red-300/50 bg-red-500/20 px-2 py-1 text-xs font-semibold text-red-100 hover:bg-red-500/30"
                      >
                        Reject
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ) : null}

          {/* Clip Revision Controls - only show when review decision is needs_revision or rejected */}
          {showRevisionControls ? (
            <div className="mt-3 rounded-lg border border-orange-300/30 bg-orange-500/10 p-3">
              <div className="text-[11px] uppercase tracking-[0.12em] text-orange-100">Clip Revisions</div>
              
              {/* Revision Creation Form */}
              <div className="mt-3 space-y-2">
                <select
                  value={selectedJobForRevision}
                  onChange={(e) => setSelectedJobForRevision(e.target.value)}
                  className="w-full rounded border border-orange-300/30 bg-black/40 p-2 text-xs text-orange-50"
                >
                  <option value="">Select a clip to revise...</option>
                  {renderRows.filter(row => row.status === 'complete' && row.output_url).map(row => (
                    <option key={row.job_id} value={row.job_id}>
                      Scene {row.scene_id} - Shot {row.shot_id} ({row.provider})
                    </option>
                  ))}
                </select>
                
                <textarea
                  value={revisionPrompt}
                  onChange={(e) => setRevisionPrompt(e.target.value)}
                  className="w-full rounded border border-orange-300/30 bg-black/40 p-2 text-xs text-orange-50 placeholder-orange-200/50"
                  placeholder="Revision prompt (describe the changes needed)..."
                  rows={3}
                />
                
                <textarea
                  value={revisionReason}
                  onChange={(e) => setRevisionReason(e.target.value)}
                  className="w-full rounded border border-orange-300/30 bg-black/40 p-2 text-xs text-orange-50 placeholder-orange-200/50"
                  placeholder="Reason for revision..."
                  rows={2}
                />
                
                <button
                  type="button"
                  onClick={onCreateClipRevision}
                  disabled={!selectedJobForRevision || !revisionPrompt || !revisionReason || revisionStatus === 'creating' || revisionStatus === 'submitting'}
                  className="rounded border border-orange-300/50 bg-orange-500/20 px-3 py-2 text-xs font-semibold text-orange-100 hover:bg-orange-500/30 disabled:opacity-50"
                >
                  {revisionStatus === 'creating' || revisionStatus === 'submitting' ? 'Submitting...' : 'Submit Clip Revision'}
                </button>
                
                {revisionError && (
                  <div className="text-xs text-rose-300">{revisionError}</div>
                )}
              </div>

              {/* Existing Revisions */}
              {clipRevisions.length > 0 ? (
                <div className="mt-3 space-y-2">
                  <div className="text-xs font-semibold text-orange-50">Existing Revisions:</div>
                  {clipRevisions.map(revision => (
                    <div key={revision.revision_id} className="rounded border border-orange-200/20 bg-black/20 p-2">
                      <div className="text-xs text-orange-50">
                        <div className="font-semibold">Revision: {revision.revision_id}</div>
                        <div className="mt-1">Original Job: {revision.original_job_id}</div>
                        <div className="mt-1">Status: <span className={`font-bold ${
                          revision.status === 'complete' ? 'text-green-300' :
                          revision.status === 'submitted' ? 'text-blue-300' :
                          revision.status === 'failed' ? 'text-red-300' :
                          revision.status === 'cancelled' ? 'text-gray-300' :
                          'text-yellow-300'
                        }`}>{revision.status}</span></div>
                        {revision.output_url && (
                          <div className="mt-1">
                            <div className="font-semibold">Output URL:</div>
                            <div className="break-all text-[10px]">{revision.output_url}</div>
                          </div>
                        )}
                        {revision.new_job_id && (
                          <div className="mt-1">New Job: {revision.new_job_id}</div>
                        )}
                        {revision.revision_prompt && (
                          <div className="mt-1">
                            <div className="font-semibold">Prompt:</div>
                            <div className="text-[10px]">{revision.revision_prompt}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}

              {/* Re-stitch Button */}
              {canRestitch ? (
                <div className="mt-3 border-t border-orange-200/20 pt-3">
                  <div className="text-xs font-semibold text-orange-50 mb-2">
                    Re-stitch with {completedRevisions.length} revised clip{completedRevisions.length > 1 ? 's' : ''}
                  </div>
                  <button
                    type="button"
                    onClick={onRestitchWithRevisions}
                    className="rounded border border-green-300/50 bg-green-500/20 px-3 py-2 text-xs font-semibold text-green-100 hover:bg-green-500/30"
                  >
                    Re-stitch With Revisions
                  </button>
                </div>
              ) : null}

              {/* Revised Stitch Result */}
              {revisedStitchResult ? (
                <div className="mt-3 rounded-lg border border-green-300/30 bg-green-500/10 p-3">
                  <div className="text-[11px] uppercase tracking-[0.12em] text-green-100">Revised Stitched Film</div>
                  <div className="mt-1 text-xs text-green-50">status: {revisedStitchResult.status}</div>
                  <div className="mt-1 text-xs text-green-50">clip_count: {revisedStitchResult.clip_count}</div>
                  <div className="mt-1 text-xs text-green-50 break-all">output_url: {revisedStitchResult.output_url}</div>
                  {(revisedStitchResult.status === 'completed' || revisedStitchResult.status === 'existing') && revisedStitchResult.output_url ? (
                    <video className="mt-2 w-full rounded border border-white/10" controls preload="metadata" src={revisedStitchResult.output_url} />
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {/* Final Short Film Package Controls */}
          {(stitchResult && (stitchResult.status === 'completed' || stitchResult.status === 'existing')) || (revisedStitchResult && (revisedStitchResult.status === 'completed' || revisedStitchResult.status === 'existing')) ? (
            <div className="mt-3 rounded-lg border border-purple-300/30 bg-purple-500/10 p-3">
              <div className="text-[11px] uppercase tracking-[0.12em] text-purple-100">Final Package</div>
              
              {/* Package Creation */}
              {!latestPackage ? (
                <div className="mt-3">
                  <button
                    type="button"
                    onClick={onCreateFinalPackage}
                    disabled={packageStatus === 'creating' || packageStatus === 'updating'}
                    className="rounded border border-purple-300/50 bg-purple-500/20 px-3 py-2 text-xs font-semibold text-purple-100 hover:bg-purple-500/30 disabled:opacity-50"
                  >
                    {packageStatus === 'creating' ? 'Creating Package...' : 'Create Final Package'}
                  </button>
                  
                  {packageError && (
                    <div className="mt-2 text-xs text-rose-300">{packageError}</div>
                  )}
                </div>
              ) : (
                <div className="mt-3 space-y-2">
                  <div className="text-xs font-semibold text-purple-50">Latest Package:</div>
                  <div className="rounded border border-purple-200/20 bg-black/20 p-2">
                    <div className="text-xs text-purple-50">
                      <div className="font-semibold">Package: {latestPackage.package_id}</div>
                      <div className="mt-1">Title: {latestPackage.film_title}</div>
                      <div className="mt-1">Status: <span className={`font-bold ${
                        latestPackage.package_status === 'approved' ? 'text-green-300' :
                        latestPackage.package_status === 'packaged' ? 'text-blue-300' :
                        latestPackage.package_status === 'archived' ? 'text-gray-300' :
                        latestPackage.package_status === 'ready_for_review' ? 'text-yellow-300' :
                        'text-orange-300'
                      }`}>{latestPackage.package_status}</span></div>
                      <div className="mt-1">Review Decision: <span className={`font-bold ${
                        latestPackage.review_decision === 'approved' ? 'text-green-300' :
                        latestPackage.review_decision === 'needs_revision' ? 'text-yellow-300' :
                        latestPackage.review_decision === 'rejected' ? 'text-red-300' :
                        'text-gray-300'
                      }`}>{latestPackage.review_decision}</span></div>
                      <div className="mt-1">Scenes: {latestPackage.scene_count}</div>
                      <div className="mt-1">Shots: {latestPackage.shot_count}</div>
                      <div className="mt-1">Title Card: {latestPackage.has_title_card ? 'Yes' : 'No'}</div>
                      <div className="mt-1">End Card: {latestPackage.has_end_card ? 'Yes' : 'No'}</div>
                      <div className="mt-1">Soundtrack: {latestPackage.has_soundtrack ? 'Yes' : 'No'}</div>
                      {latestPackage.runtime_seconds && (
                        <div className="mt-1">Runtime: {latestPackage.runtime_seconds.toFixed(1)}s</div>
                      )}
                      {latestPackage.revision_ids.length > 0 && (
                        <div className="mt-1">Revisions: {latestPackage.revision_ids.length}</div>
                      )}
                    </div>
                  </div>

                  {/* Package Actions */}
                  <div className="flex gap-2">
                    <a
                      href={latestPackage.final_output_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded border border-green-300/50 bg-green-500/20 px-2 py-1 text-xs font-semibold text-green-100 hover:bg-green-500/30"
                    >
                      Open Final Film
                    </a>
                    
                    {latestPackage.package_status !== 'archived' && (
                      <button
                        type="button"
                        onClick={() => onUpdatePackageStatus('archived')}
                        disabled={packageStatus === 'updating'}
                        className="rounded border border-gray-300/50 bg-gray-500/20 px-2 py-1 text-xs font-semibold text-gray-100 hover:bg-gray-500/30 disabled:opacity-50"
                      >
                        Archive
                      </button>
                    )}
                  </div>

                  {/* Package Video Player */}
                  {(latestPackage.package_status === 'approved' || latestPackage.package_status === 'packaged' || latestPackage.package_status === 'ready_for_review') && latestPackage.final_output_url ? (
                    <video className="mt-2 w-full rounded border border-white/10" controls preload="metadata" src={latestPackage.final_output_url} />
                  ) : null}
                </div>
              )}
            </div>
          ) : null}
        </article>
      ) : null}
    </section>
  )
}

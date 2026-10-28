import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { createProject, generateShortFilmWorkflow, type ShortFilmWorkflow } from '../lib/studioApi'
import { useStudio } from '../context/StudioContext'

const STAGE_LABELS: Record<string, string> = {
  concept: 'Concept',
  screenplay_outline: 'Screenplay Outline',
  scene_generation: 'Scene Generation',
  shot_sequencing: 'Shot Sequencing',
  render_orchestration: 'Render Orchestration',
  audio_generation: 'Audio Generation',
  film_assembly: 'Film Assembly',
  final_export: 'Final Export',
}

export default function OneButtonShortFilmPanel() {
  const [concept, setConcept] = useState('A displaced musician uncovers a citywide memory glitch one song at a time.')
  const [providerOverride, setProviderOverride] = useState('runway')
  const [useMockSuccess, setUseMockSuccess] = useState(false)
  const [toneOverride, setToneOverride] = useState('atmospheric')
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState('')
  const [workflow, setWorkflow] = useState<ShortFilmWorkflow | null>(null)
  const [lastProjectId, setLastProjectId] = useState('')
  const [latestJobs, setLatestJobs] = useState<Array<Record<string, unknown>>>([])
  const [statusMessage, setStatusMessage] = useState('')
  const { loadProject } = useStudio()

  const stageRows = useMemo(() => workflow?.stages || [], [workflow])

  const onGenerate = async () => {
    if (isRunning) return
    setIsRunning(true)
    setError('')
    setStatusMessage('Creating project...')
    try {
      const created = await createProject({ title: 'One Button Short Film' })
      const project = created.project
      if (!project?.project_id) throw new Error(created.error || 'Unable to create project')
      setLastProjectId(project.project_id)
      localStorage.setItem('studio:activeProjectId', project.project_id)
      localStorage.setItem('studio:selected-project-id', project.project_id)
      setStatusMessage('Generating scenes and render jobs...')
      const requestOptions = {
        submitRenders: true,
        assembleFinal: true,
      }
      const effectiveProvider = providerOverride.trim().toLowerCase() === 'mock_success' ? 'runway' : providerOverride
      const manualOverrides: Record<string, unknown> = {
        provider: effectiveProvider,
        tone: toneOverride,
      }
      if (useMockSuccess || providerOverride.trim().toLowerCase() === 'mock_success') {
        manualOverrides.use_mock_success = true
      }
      const result = await generateShortFilmWorkflow(project.project_id, concept, manualOverrides, requestOptions)
      const unwrappedWorkflow = (result.workflow as Record<string, unknown> | undefined)?.short_film_workflow as ShortFilmWorkflow | undefined
      const resolvedWorkflow = unwrappedWorkflow || result.workflow || null
      if (!resolvedWorkflow) throw new Error(result.error || 'Workflow generation failed')
      setWorkflow(resolvedWorkflow)
      const projectState = result.project as unknown as Record<string, unknown> | undefined
      const summary = projectState?.execution_summary as Record<string, unknown> | undefined
      const rowsFromResponse = Array.isArray(result.render_jobs) ? result.render_jobs : []
      const rowsFromSummary = Array.isArray(summary?.one_button_render_jobs) ? (summary.one_button_render_jobs as Array<Record<string, unknown>>) : []
      const rowsFromLegacyRoot = Array.isArray(projectState?.one_button_render_jobs) ? (projectState.one_button_render_jobs as Array<Record<string, unknown>>) : []
      const rowsRaw = rowsFromResponse.length > 0 ? rowsFromResponse : rowsFromSummary.length > 0 ? rowsFromSummary : rowsFromLegacyRoot
      const rows = rowsRaw.map((row) => {
        const record = row as Record<string, unknown>
        const outputPayload = (record.output_payload && typeof record.output_payload === 'object' && !Array.isArray(record.output_payload))
          ? (record.output_payload as Record<string, unknown>)
          : {}
        const outputUrl = typeof record.output_url === 'string' && record.output_url
          ? record.output_url
          : (typeof outputPayload.asset_url === 'string' ? outputPayload.asset_url : '')
        const previewUrl = typeof record.preview_url === 'string' && record.preview_url
          ? record.preview_url
          : (typeof outputPayload.thumbnail_url === 'string' ? outputPayload.thumbnail_url : '')
        return {
          ...record,
          output_url: outputUrl,
          preview_url: previewUrl,
        }
      })
      setLatestJobs(rows)
      localStorage.setItem('studio:lastShortFilmWorkflow', JSON.stringify(resolvedWorkflow))
      setStatusMessage(`Generation complete. Jobs: ${rows.length}`)
      void loadProject(project.project_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate short film')
      setStatusMessage('')
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <section className="rounded-2xl border border-fuchsia-300/25 bg-fuchsia-500/8 p-4 shadow-xl">
      <div className="text-xs uppercase tracking-[0.14em] text-fuchsia-200">One-Button Short Film</div>
      <p className="mt-2 text-xs text-zinc-300">Run full concept-to-export workflow with live stage progress and manual creative overrides.</p>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <textarea
          value={concept}
          onChange={(e) => setConcept(e.target.value)}
          className="md:col-span-3 min-h-[76px] rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
        />
        <input
          value={toneOverride}
          onChange={(e) => setToneOverride(e.target.value)}
          className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
          placeholder="Tone override"
        />
        <input
          value={providerOverride}
          onChange={(e) => setProviderOverride(e.target.value)}
          className="rounded-lg border border-zinc-700/70 bg-black/40 p-2 text-xs text-zinc-100"
          placeholder="Provider override"
        />
        <label className="flex items-center gap-2 rounded-lg border border-zinc-700/70 bg-black/30 px-2 py-2 text-[11px] text-zinc-200">
          <input
            type="checkbox"
            checked={useMockSuccess}
            onChange={(e) => setUseMockSuccess(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          use mock_success
        </label>
        <button
          type="button"
          disabled={isRunning}
          aria-busy={isRunning}
          onClick={onGenerate}
          className="rounded-lg border border-fuchsia-300/55 bg-fuchsia-500/18 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-fuchsia-100 disabled:opacity-50"
        >
          {isRunning ? 'Generating...' : 'Generate Short Film'}
        </button>
      </div>
      {statusMessage ? <div className="mt-2 text-xs text-cyan-200">{statusMessage}</div> : null}
      {error ? <div className="mt-3 text-xs text-rose-300">{error}</div> : null}
      {!isRunning && workflow?.runtime_metadata?.final_status === 'completed' ? (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-emerald-300/35 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
          <span>Workflow complete.</span>
          <div className="flex items-center gap-2">
            <Link to={lastProjectId ? `/studio/production-board?project_id=${encodeURIComponent(lastProjectId)}` : '/studio/production-board'} className="rounded-md border border-cyan-300/50 bg-cyan-500/20 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-cyan-100 no-underline">
              View in Production Board
            </Link>
            <Link to={lastProjectId ? `/studio/screening-room?project_id=${encodeURIComponent(lastProjectId)}` : '/studio/screening-room'} className="rounded-md border border-emerald-300/50 bg-emerald-500/20 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-emerald-100 no-underline">
              Open Screening Room
            </Link>
          </div>
        </div>
      ) : null}
      {latestJobs.length > 0 ? (
        <div className="mt-3 rounded-lg border border-white/15 bg-black/30 p-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-zinc-300">Latest Generated Outputs</div>
          <div className="mt-2 space-y-2">
            {latestJobs.slice(0, 5).map((job, index) => {
              const status = typeof job.status === 'string' ? job.status : 'unknown'
              const outputUrl = typeof job.output_url === 'string' ? job.output_url : ''
              const jobId = typeof job.job_id === 'string' ? job.job_id : 'n/a'
              const sceneId = typeof job.scene_id === 'string' ? job.scene_id : 'unknown_scene'
              return (
                <div key={`${jobId}-${index}`} className="rounded border border-white/10 bg-zinc-900/50 px-2 py-1.5 text-xs text-zinc-200">
                  <div>project_id: {lastProjectId || 'n/a'}</div>
                  <div>scene: {sceneId} • job_id: {jobId} • status: {status}</div>
                  {outputUrl ? (
                    <a href={outputUrl} target="_blank" rel="noreferrer" className="text-cyan-300 break-all">
                      {outputUrl}
                    </a>
                  ) : (
                    <div className="text-zinc-400">output_url not ready</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ) : null}
      <div className="mt-4 space-y-2">
        {stageRows.map((stage) => (
          <div key={stage.stage} className="rounded-lg border border-white/10 bg-black/35 p-2">
            <div className="flex items-center justify-between text-[11px] text-zinc-200">
              <span>{STAGE_LABELS[stage.stage] || stage.stage}</span>
              <span>{stage.updated_by}</span>
            </div>
            <div className="mt-1 h-1.5 w-full rounded bg-zinc-800">
              <div className="h-1.5 rounded bg-fuchsia-400 transition-all duration-500" style={{ width: `${Math.max(0, Math.min(100, stage.progress || 0))}%` }} />
            </div>
            <div className="mt-1 text-xs text-zinc-400">{stage.activity}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

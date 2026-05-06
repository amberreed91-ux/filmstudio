import { useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { FileText } from 'lucide-react'
import StudioShell, { TabGroup } from '../components/StudioShell'
import { createProject, generateScenes } from '../lib/studioApi'

type ActRow = { act: number; scene_ids: string[]; scene_count: number }
type SequenceRow = { sequence_id: string; scene_ids: string[]; length: number }

const SAMPLE_SCRIPT = `INT. APARTMENT - NIGHT
MAYA waits by the window.

EXT. STREET - DAY
Cars rush past.

INT. WAREHOUSE - NIGHT
JONAH reveals the plan.

EXT. BRIDGE - SUNSET
They split directions.`

function parseScenes(script: string): string[] {
  const lines = script.split('\n')
  const sceneIds: string[] = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (/^(INT\.|EXT\.)/i.test(trimmed)) {
      sceneIds.push(`scene_${String(sceneIds.length + 1).padStart(3, '0')}`)
    }
  }
  return sceneIds
}

function splitScenes(script: string): Array<{ heading: string; body: string[] }> {
  const lines = script.split('\n')
  const scenes: Array<{ heading: string; body: string[] }> = []
  let current: { heading: string; body: string[] } | null = null
  for (const line of lines) {
    const trimmed = line.trim()
    if (/^(INT\.|EXT\.)/i.test(trimmed)) {
      if (current) scenes.push(current)
      current = { heading: trimmed, body: [] }
      continue
    }
    if (current && trimmed) current.body.push(trimmed)
  }
  if (current) scenes.push(current)
  return scenes
}

function extractSceneTextVisuals(text: string): string[] {
  const source = text.toLowerCase()
  const tags: Array<[string, string[]]> = [
    ['chalk symbol', ['chalk', 'symbol']],
    ['farmhouse kitchen', ['farmhouse', 'kitchen']],
    ['eli drawing', ['eli', 'draw']],
    ['spoon drops', ['spoon', 'drop']],
    ['scratching inside wall', ['scratch', 'wall']],
    ['mirror fogs from inside', ['mirror', 'fog']],
    ['notebook ritual notes', ['notebook', 'ritual']],
    ['third handprint across wrists', ['third', 'handprint', 'wrist']],
  ]
  return tags.filter(([, tokens]) => tokens.every((token) => source.includes(token))).map(([label]) => label)
}

function buildBundleFromScript(script: string) {
  const split = splitScenes(script)
  const scenes = split.map((scene, index) => {
    const sceneId = `scene_${String(index + 1).padStart(3, '0')}`
    const bodyText = scene.body.join(' ')
    const headingParts = scene.heading.split(' - ')
    const location = headingParts[0]?.replace(/^INT\.|^EXT\./i, '').trim() || scene.heading
    const timeOfDay = headingParts[1]?.trim() || 'UNSPECIFIED'
    const visuals = extractSceneTextVisuals(`${scene.heading} ${bodyText}`)
    const primaryAction = scene.body[0] || 'quiet movement in frame'
    const renderId = `${sceneId}_render_a`
    const shotId = `shot_${sceneId}_001`
    const basePrompt = [
      `location ${location}`,
      `time ${timeOfDay}`,
      `characters ${bodyText.match(/\bMARA\b|\bELI\b/gi)?.join(', ') || 'none named'}`,
      `action ${primaryAction}`,
      `key objects ${(visuals.length ? visuals : ['chalk symbol']).join(', ')}`,
      `supernatural elements ${visuals.filter((v) => v.includes('mirror') || v.includes('scratch') || v.includes('handprint')).join(', ') || 'subtle unseen pressure'}`,
      `emotional tone ${index < 2 ? 'quiet supernatural unease' : 'rising supernatural tension'}`,
      `lighting ${index < 2 ? 'natural soft' : 'contrast shadow'}`,
      `camera ${index < 2 ? 'static' : 'slow push'}`,
      'cinematic dark farmhouse realism',
    ].join(', ')

    return {
      scene_id: sceneId,
      heading: scene.heading,
      location,
      time_of_day: timeOfDay,
      text: bodyText,
      scene_visual_brief: {
        scene_id: sceneId,
        location,
        time_of_day: timeOfDay,
        characters: bodyText.match(/\bMARA\b|\bELI\b/gi) || [],
        key_actions: scene.body.slice(0, 3),
        supernatural_elements: visuals.filter((v) => v.includes('mirror') || v.includes('scratch') || v.includes('handprint')),
        motifs: visuals.filter((v) => v.includes('chalk') || v.includes('symbol')),
        emotional_intent: index < 2 ? 'quiet supernatural unease' : 'rising supernatural tension',
        visual_must_haves: visuals,
      },
      scene_generation_summary: { status: 'complete' },
      scene_quality_verdict: { verdict: 'needs_revision' },
      scene_playback_preview: { available: true, render_ids: [renderId] },
      co_director_suggestions: [
        { id: `${sceneId}_s1`, type: 'tension', title: 'Increase visual tension', description: 'Raise contrast and isolate character silhouette.', confidence: 0.82 },
        { id: `${sceneId}_s2`, type: 'continuity', title: 'Fix continuity gap', description: 'Align prop placement across cuts.', confidence: 0.76 },
      ],
      director_notes: {
        what_works: ['Scene intent is visible'],
        what_breaks: ['Escalation can be clearer'],
        suggested_changes: ['Push one stronger visual beat'],
      },
      multi_shot_execution_ledger: [
        {
          shot_id: shotId,
          status: 'complete',
          render_id: renderId,
          meta: { file_path: `https://picsum.photos/seed/${sceneId}_hero/800/450` },
          shot_intent: {
            framing: index < 2 ? 'wide' : 'medium close',
            camera: index < 2 ? 'static' : 'slow push',
            lighting: index < 2 ? 'natural soft' : 'contrast shadow',
            mood: index < 2 ? 'quiet unease' : 'rising tension',
            motif_instruction: index < 2 ? 'subtle background presence' : 'visible environmental intrusion',
          },
          prompt_pack: {
            base_prompt: basePrompt,
            style_tags: ['cinematic', 'dark', 'grain', 'natural light'],
            negative_prompt: ['low quality', 'blurry', 'deformed', 'extra limbs', 'bad anatomy', 'distorted face', 'oversaturated'],
          },
        },
      ],
      scene_iterations: [],
    }
  })

  const image_render_assets = scenes.map((scene) => {
    const shot = scene.multi_shot_execution_ledger[0]
    return {
      asset_id: `image_${scene.scene_id}_${shot.shot_id}`,
      scene_id: scene.scene_id,
      shot_id: shot.shot_id,
      provider: 'local_image',
      status: 'success',
      file_path: null,
      url: shot.meta.file_path,
      preview_label: `${scene.scene_id}:${shot.shot_id}`,
      meta: {
        prompt_used: shot.prompt_pack.base_prompt,
        negative_prompt: shot.prompt_pack.negative_prompt.join(', '),
        source: 'script',
      },
    }
  })

  return {
    scenes,
    image_render_assets,
    render_asset_summary: {
      total_assets: image_render_assets.length,
      successful_assets: image_render_assets.length,
      failed_assets: 0,
      providers: ['local_image'],
    },
    screening_playlist: scenes.map((scene) => ({
      scene_id: scene.scene_id,
      cut: 'original',
      render_ids: scene.scene_playback_preview.render_ids,
      status: scene.scene_generation_summary.status,
      verdict: scene.scene_quality_verdict.verdict,
      duration_estimate: 2,
    })),
  }
}

function buildActs(sceneIds: string[]): ActRow[] {
  const total = sceneIds.length
  const act1End = Math.floor(total * 0.25)
  const act2End = Math.floor(total * 0.75)
  const a1 = sceneIds.slice(0, act1End)
  const a2 = sceneIds.slice(act1End, act2End)
  const a3 = sceneIds.slice(act2End)
  return [
    { act: 1, scene_ids: a1, scene_count: a1.length },
    { act: 2, scene_ids: a2, scene_count: a2.length },
    { act: 3, scene_ids: a3, scene_count: a3.length },
  ]
}

function buildSequences(sceneIds: string[]): SequenceRow[] {
  const out: SequenceRow[] = []
  let i = 0
  let seqId = 1
  while (i < sceneIds.length) {
    let chunk = 3
    const remaining = sceneIds.length - i
    if (remaining <= 2) chunk = remaining
    else if (remaining === 4) chunk = 4
    const rows = sceneIds.slice(i, i + chunk)
    out.push({
      sequence_id: `seq_${String(seqId).padStart(3, '0')}`,
      scene_ids: rows,
      length: rows.length,
    })
    i += chunk
    seqId += 1
  }
  return out
}

export default function WritersRoom() {
  const navigate = useNavigate()
  const location = useLocation()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [scriptInput, setScriptInput] = useState(SAMPLE_SCRIPT)
  const [processedScript, setProcessedScript] = useState(SAMPLE_SCRIPT)
  const [uploadedFileName, setUploadedFileName] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [isDragActive, setIsDragActive] = useState(false)
  const [flowMessage, setFlowMessage] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [detailsTab, setDetailsTab] = useState<'structure' | 'validation' | 'notes'>('structure')
  const routeNotice = typeof (location.state as { notice?: unknown } | null)?.notice === 'string'
    ? String((location.state as { notice?: unknown }).notice)
    : ''
  const sceneIds = useMemo(() => parseScenes(processedScript), [processedScript])
  const acts = useMemo(() => buildActs(sceneIds), [sceneIds])
  const sequences = useMemo(() => buildSequences(sceneIds), [sceneIds])
  const scriptCharCount = scriptInput.length
  const scriptLineCount = scriptInput.length > 0 ? scriptInput.split('\n').length : 0

  const allowedExtensions = ['txt', 'md', 'fountain', 'screenplay']

  const readScriptFile = (file: File) => {
    const extension = file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() || '' : ''
    if (!allowedExtensions.includes(extension)) {
      setUploadError('Unsupported file type. Use .txt, .md, .fountain, or .screenplay.')
      return
    }
    if (file.size <= 0) {
      setUploadError('File is empty. Please choose a non-empty script file.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : ''
      if (!result.trim()) {
        setUploadError('File contains no readable text.')
        return
      }
      setScriptInput(result)
      setUploadedFileName(file.name)
      setUploadError('')
    }
    reader.onerror = () => {
      setUploadError('Unable to read the file. Please try again.')
    }
    reader.readAsText(file)
  }

  const handleFileSelect = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    readScriptFile(file)
    event.target.value = ''
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragActive(false)
    const file = event.dataTransfer.files?.[0]
    if (!file) {
      setUploadError('No file detected in drop event.')
      return
    }
    readScriptFile(file)
  }

  const handleProcessScript = () => {
    setProcessedScript(scriptInput)
  }

  const handleGenerateScenes = () => {
    void (async () => {
    const trimmed = scriptInput.trim()
    if (!trimmed) {
      setUploadError('Please paste or upload a script before generating scenes.')
      return
    }
    setIsGenerating(true)
    setFlowMessage('Processing script...')
    handleProcessScript()
    const bundle = buildBundleFromScript(trimmed)
    let persistedMode = false
    let activeProjectId = localStorage.getItem('studio:activeProjectId') || ''
    if (!activeProjectId) {
      const created = await createProject({ title: 'Studio Project' })
      if (created.project?.project_id) {
        activeProjectId = created.project.project_id
        localStorage.setItem('studio:activeProjectId', activeProjectId)
      }
    }
    if (activeProjectId) {
      const generated = await generateScenes(activeProjectId, trimmed)
      if (generated.project?.execution_summary && typeof generated.project.execution_summary === 'object') {
        localStorage.setItem('studio:lastBundle', JSON.stringify(generated.project.execution_summary))
        persistedMode = true
      }
    }
    setUploadError('')
    localStorage.setItem('studio:lastScript', trimmed)
    if (!persistedMode) {
      localStorage.setItem('studio:lastBundle', JSON.stringify(bundle))
    }
    localStorage.setItem('studio:lastBundleSource', 'writers-room-local')
    localStorage.setItem('studio_script_exists', '1')
    localStorage.setItem('studio_scenes_generated', (persistedMode ? (JSON.parse(localStorage.getItem('studio:lastBundle') || '{}') as { scenes?: unknown[] }).scenes?.length : bundle.scenes.length) ? '1' : '0')
    localStorage.setItem('studio_last_script_lines', String(scriptLineCount))
    setFlowMessage(persistedMode ? 'Scenes generated and saved to project' : 'Scenes generated (local fallback mode)')
    setIsGenerating(false)
    navigate('/studio/previs', {
      state: {
        execution_summary: persistedMode ? JSON.parse(localStorage.getItem('studio:lastBundle') || '{}') : bundle,
        source: persistedMode ? 'project-persistence' : 'writers-room-local',
      },
    })
    })()
  }

  return (
    <StudioShell title="Writer's Room" subtitle="Write, upload, revise, and prepare your script.">
      <div className="w-full overflow-visible">
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6 text-zinc-100">
          {routeNotice ? (
            <section className="rounded-xl border border-amber-400/35 bg-amber-500/10 px-4 py-2 text-xs text-amber-100">
              {routeNotice}
            </section>
          ) : null}
          <section className="cinematic-panel p-6">
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">STEP 1: ADD YOUR SCRIPT</div>
            <h2 className="flex items-center gap-2 text-xl font-semibold uppercase tracking-[0.14em] text-zinc-100"><FileText size={18} />Writer&apos;s Room</h2>
            <p className="mt-2 text-sm text-zinc-300">Shape tone, rhythm, and sequence structure before production handoff.</p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="rounded-lg border border-cyan-300/50 bg-cyan-500/14 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100 transition-all duration-200 hover:scale-[1.02]"
              >
                Upload Script
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,.fountain,.screenplay"
                onChange={handleFileSelect}
                className="hidden"
              />
              <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">
                {uploadedFileName ? `Loaded: ${uploadedFileName}` : 'No file loaded'}
              </div>
            </div>
            <div
              onDragEnter={(event) => {
                event.preventDefault()
                setIsDragActive(true)
              }}
              onDragOver={(event) => {
                event.preventDefault()
                setIsDragActive(true)
              }}
              onDragLeave={(event) => {
                event.preventDefault()
                setIsDragActive(false)
              }}
              onDrop={handleDrop}
              className={`mt-3 rounded-xl border border-dashed p-4 text-center text-xs uppercase tracking-[0.12em] transition-all duration-200 ${
                isDragActive
                  ? 'dropzone-glow border-amber-300/70 bg-amber-400/10 text-amber-100'
                  : 'border-white/20 bg-black/35 text-zinc-400'
              }`}
            >
              Drag script file here
            </div>
            {uploadError ? (
              <div className="mt-2 rounded-lg border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                {uploadError}
              </div>
            ) : null}
            <textarea
              value={scriptInput}
              onChange={(e) => setScriptInput(e.target.value)}
              className="mt-4 h-56 w-full rounded-xl border border-white/15 bg-black/55 p-4 text-sm leading-relaxed tracking-[0.01em] text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="text-[11px] uppercase tracking-[0.12em] text-zinc-400">
                Dark editor mode · {scriptCharCount} chars · {scriptLineCount} lines
              </div>
              <button
                type="button"
                onClick={handleProcessScript}
                className="rounded-lg border border-amber-300/50 bg-amber-500/14 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-amber-100 transition-all duration-200 hover:scale-[1.02]"
              >
                Process Script
              </button>
            </div>
            <div className="mt-3 rounded-lg border border-cyan-400/25 bg-cyan-500/8 px-3 py-2 text-xs text-cyan-100">
              This processes your script and sends scenes to Previs.
            </div>
            <div className="mt-2 text-[10px] uppercase tracking-[0.12em] text-zinc-400">Script Processing</div>
              <button
                type="button"
                onClick={handleGenerateScenes}
                disabled={isGenerating}
                className="mt-3 w-full rounded-lg border border-cyan-300/60 bg-cyan-500/22 px-4 py-3 text-sm font-bold uppercase tracking-[0.14em] text-cyan-50 shadow-[0_0_26px_rgba(34,211,238,0.22)] transition-all duration-200 hover:scale-[1.01]"
              >
                {isGenerating ? 'Processing script...' : 'Generate Scenes'}
              </button>
            {flowMessage ? (
              <div className="mt-2 rounded-lg border border-emerald-400/35 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
                {flowMessage}
              </div>
            ) : null}
          </section>

          <section className="cinematic-panel p-4">
            <TabGroup
              className="mb-3"
              value={detailsTab}
              onChange={(next) => setDetailsTab(next)}
              options={[
                { id: 'structure', label: 'Structure' },
                { id: 'validation', label: 'Validation' },
                { id: 'notes', label: 'Notes' },
              ]}
            />

            {detailsTab === 'structure' ? (
              <div className="space-y-4">
                <div className="text-sm text-zinc-200">Total Scenes: {sceneIds.length}</div>
                <div className="space-y-2">
                  {acts.map((act) => (
                    <div key={act.act} className="rounded-xl border border-white/10 bg-black/35 p-3">
                      <div className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100">Act {act.act}</div>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.1em] text-zinc-400">Scene Count: {act.scene_count}</div>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  {sequences.map((sequence) => (
                    <div key={sequence.sequence_id} className="rounded-xl border border-white/10 bg-black/35 p-3">
                      <div className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-100">{sequence.sequence_id}</div>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.1em] text-zinc-400">Length: {sequence.length}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {detailsTab === 'validation' ? (
              <div className="space-y-2 text-xs text-zinc-300">
                <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                  {sceneIds.length > 0 ? 'Scene headings detected and grouped successfully.' : 'No scenes detected yet.'}
                </div>
                <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2">
                  {scriptInput.trim() ? 'Script ready for processing.' : 'Paste or upload a script to validate.'}
                </div>
              </div>
            ) : null}

            {detailsTab === 'notes' ? (
              <div className="rounded-lg border border-white/10 bg-black/35 px-3 py-2 text-xs text-zinc-300">
                Keep acts balanced and escalate visual pressure scene-by-scene before handing off to Previs.
              </div>
            ) : null}
          </section>
          {!scriptInput.trim() ? (
            <section className="cinematic-panel p-4">
              <div className="text-sm text-zinc-300">Paste or upload your script to begin.</div>
            </section>
          ) : null}
        </div>
      </div>
    </StudioShell>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { RadioTower } from 'lucide-react'
import { useRenderActivity } from '../context/RenderActivityContext'
import CinematicLoading from './CinematicLoading'
import CoDirectorCollaborationPanel from './CoDirectorCollaborationPanel'

type ProviderOption = {
  id: string
  label: string
}

type DirectorConsolePayload = {
  sceneGoal: string
  emotionalTone: string
  pacing: string
  cameraStyle: string
  provider: string
  collaborationMode: 'passive' | 'advisory' | 'collaborative' | 'experimental'
}

export default function DirectorConsole({
  sceneId,
  providers,
  defaultProvider,
  busy,
  onGenerate,
}: {
  sceneId: string
  providers: ProviderOption[]
  defaultProvider: string
  busy: boolean
  onGenerate: (payload: DirectorConsolePayload) => Promise<void>
}) {
  const { activity } = useRenderActivity()
  const [sceneGoal, setSceneGoal] = useState('')
  const [emotionalTone, setEmotionalTone] = useState('uneasy')
  const [pacing, setPacing] = useState('measured')
  const [cameraStyle, setCameraStyle] = useState('slow-dolly')
  const [provider, setProvider] = useState(defaultProvider || providers[0]?.id || 'mock')
  const [collaborationMode, setCollaborationMode] = useState<'passive' | 'advisory' | 'collaborative' | 'experimental'>('advisory')

  useEffect(() => {
    if (!defaultProvider) return
    setProvider((prev) => prev || defaultProvider)
  }, [defaultProvider])

  const liveStatusText = useMemo(() => {
    if (!activity) return 'Idle'
    return activity.status.toUpperCase()
  }, [activity])

  return (
    <section className="director-console-panel">
      <div className="director-console-monitor" />
      <div className="relative z-10">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200">Director Console v1.0</div>
          <div className="rounded-full border border-cyan-300/35 bg-cyan-500/10 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100">
            <RadioTower size={12} className="mr-1 inline" />
            Live: {liveStatusText}
          </div>
        </div>
        <div className="mt-2 text-[11px] uppercase tracking-[0.12em] text-zinc-400">Target Scene: {sceneId || 'scene_001'}</div>

        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <label className="director-console-control md:col-span-2">
            <span className="director-console-label">Scene Goal</span>
            <input
              value={sceneGoal}
              onChange={(event) => setSceneGoal(event.target.value)}
              placeholder="Describe the directorial objective for this pass..."
              className="director-console-input"
            />
          </label>
          <label className="director-console-control">
            <span className="director-console-label">Emotional Tone</span>
            <select value={emotionalTone} onChange={(event) => setEmotionalTone(event.target.value)} className="director-console-input">
              <option value="uneasy">Uneasy</option>
              <option value="hopeful">Hopeful</option>
              <option value="desperate">Desperate</option>
              <option value="triumphant">Triumphant</option>
            </select>
          </label>
          <label className="director-console-control">
            <span className="director-console-label">Pacing</span>
            <select value={pacing} onChange={(event) => setPacing(event.target.value)} className="director-console-input">
              <option value="measured">Measured</option>
              <option value="escalating">Escalating</option>
              <option value="staccato">Staccato</option>
              <option value="dreamlike">Dreamlike</option>
            </select>
          </label>
          <label className="director-console-control">
            <span className="director-console-label">Camera Style</span>
            <select value={cameraStyle} onChange={(event) => setCameraStyle(event.target.value)} className="director-console-input">
              <option value="slow-dolly">Slow Dolly</option>
              <option value="locked-off">Locked Off</option>
              <option value="handheld">Handheld</option>
              <option value="wide-sweep">Wide Sweep</option>
            </select>
          </label>
          <label className="director-console-control">
            <span className="director-console-label">Provider</span>
            <select value={provider} onChange={(event) => setProvider(event.target.value)} className="director-console-input">
              {providers.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </select>
          </label>
          <label className="director-console-control">
            <span className="director-console-label">Co-Director Mode</span>
            <select value={collaborationMode} onChange={(event) => setCollaborationMode(event.target.value as 'passive' | 'advisory' | 'collaborative' | 'experimental')} className="director-console-input">
              <option value="passive">Passive</option>
              <option value="advisory">Advisory</option>
              <option value="collaborative">Collaborative</option>
              <option value="experimental">Experimental</option>
            </select>
          </label>
        </div>

        <div className="mt-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => onGenerate({ sceneGoal, emotionalTone, pacing, cameraStyle, provider, collaborationMode })}
            className="director-console-generate"
          >
            {busy ? 'Generating...' : 'Generate Scene'}
          </button>
          {busy ? (
            <div className="mt-2">
              <CinematicLoading
                compact
                title="Render Job Atmosphere"
                lines={[
                  'Analyzing scene composition...',
                  'Preparing cinematic lighting...',
                  'Rendering motion frames...',
                ]}
              />
            </div>
          ) : null}
        </div>
        <div className="mt-3">
          <CoDirectorCollaborationPanel
            room="director"
            workflow={{ mode: collaborationMode, collaboration: { advisory_only: true } }}
          />
        </div>
      </div>
    </section>
  )
}

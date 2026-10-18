import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ClipboardCheck, Globe } from 'lucide-react'
import StudioShell from '../components/StudioShell'
import DossierEditorModal from '../components/DossierEditorModal'
import {
  FieldLabel,
  GlassPanel,
  PanoramicHeader,
  RoomBackdrop,
  SelectInput,
  TextArea,
  TextInput,
} from '../components/RoomCinematicChrome'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'
import { useStudio } from '../context/StudioContext'
import { createProject, listProjects, type PersistedProjectState } from '../lib/studioApi'

const FORMATS = ['Short Film', 'Feature', 'Series Pilot', 'Music Video', 'Commercial']
const GENRES = ['Drama', 'Sci-Fi', 'Thriller', 'Comedy', 'Horror', 'Documentary', 'Experimental', 'Animation']

export function dossierStorageKey(projectId: string): string {
  return `gate:dossier:${projectId}`
}

export default function GateRoom() {
  const navigate = useNavigate()
  const { setActiveProject } = useStudio()
  const gateStyle = getProceduralRoomStyle('gate')
  const accent = gateStyle.tokens.accent
  const accentDeep = gateStyle.tokens.accentDeep

  const [title, setTitle] = useState('')
  const [format, setFormat] = useState(FORMATS[0])
  const [genre, setGenre] = useState(GENRES[0])
  const [brief, setBrief] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const [bays, setBays] = useState<PersistedProjectState[]>([])
  const [loadingBays, setLoadingBays] = useState(true)
  const [dossierOpen, setDossierOpen] = useState(false)
  // Holographic vessel orientation — interactive rotation (yaw) and tilt
  // (pitch) for inspecting the globe vessel. Presentation-only local state.
  const [vesselRotation, setVesselRotation] = useState(24)
  const [vesselTilt, setVesselTilt] = useState(12)

  useEffect(() => {
    let cancelled = false
    void listProjects().then((result) => {
      if (cancelled) return
      setBays(result.projects.filter((project) => !project.project_id.includes('demo_studio_cinematic')))
      setLoadingBays(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!title.trim()) {
      setError('Give the film a title before sending it through the Gate.')
      return
    }
    setSubmitting(true)
    setError('')
    const result = await createProject({ title: title.trim() })
    if (result.error || !result.project) {
      setError(result.error || 'The Gate could not open this project. Try again.')
      setSubmitting(false)
      return
    }
    try {
      sessionStorage.setItem(
        dossierStorageKey(result.project.project_id),
        JSON.stringify({ format, genre, brief: brief.trim() }),
      )
    } catch {
      // Dossier handoff is best-effort; the project itself is already created.
    }
    await setActiveProject(result.project.project_id)
    navigate(`/studio/page?project_id=${encodeURIComponent(result.project.project_id)}`)
  }

  function handleOpenBay(projectId: string) {
    void setActiveProject(projectId).then(() => {
      navigate(`/studio/page?project_id=${encodeURIComponent(projectId)}`)
    })
  }

  return (
    <StudioShell title="Gate" subtitle="Project intake and greenlight dossier for Fee Fee Anne Studios.">
      <RoomBackdrop roomKey="gate" testid="gate-room">
        <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 text-zinc-100 sm:px-6 lg:px-8">
          <PanoramicHeader
            eyebrow="Fee Fee Anne Studios · Gate"
            title="Project Intake"
            lede="File the dossier on the left — title, format, genre, and creative brief. Active productions glow in the vessel bays on the right."
            accent={accent}
          />

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Left-hand project dossier form panel */}
            <GlassPanel accent={accent} testid="gate-dossier-panel">
              <div className="mb-5 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <ClipboardCheck size={18} style={{ color: accent }} />
                  <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-zinc-100">
                    Project Dossier
                  </h2>
                </div>
                <button
                  type="button"
                  data-testid="gate-dossier-refine"
                  onClick={() => setDossierOpen(true)}
                  className="rounded-md border border-white/15 px-2.5 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-300 hover:border-white/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F59E0B]"
                >
                  Refine dossier…
                </button>
              </div>
              <DossierEditorModal
                open={dossierOpen}
                initial={{ title, format, genre, brief }}
                onClose={() => setDossierOpen(false)}
                onSave={(draft) => { setTitle(draft.title); setFormat(draft.format); setGenre(draft.genre); setBrief(draft.brief); setDossierOpen(false) }}
              />
              <form data-testid="gate-dossier-form" onSubmit={(event) => void handleSubmit(event)} className="space-y-4">
                <div>
                  <FieldLabel>Film Title *</FieldLabel>
                  <TextInput
                    accent={accent}
                    data-testid="gate-title"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="e.g., Neon Aftertaste"
                    disabled={submitting}
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <FieldLabel>Format</FieldLabel>
                    <SelectInput
                      accent={accent}
                      data-testid="gate-format"
                      value={format}
                      onChange={(event) => setFormat(event.target.value)}
                      disabled={submitting}
                    >
                      {FORMATS.map((option) => (
                        <option key={option} value={option} className="bg-zinc-900">
                          {option}
                        </option>
                      ))}
                    </SelectInput>
                  </div>
                  <div>
                    <FieldLabel>Genre</FieldLabel>
                    <SelectInput
                      accent={accent}
                      data-testid="gate-genre"
                      value={genre}
                      onChange={(event) => setGenre(event.target.value)}
                      disabled={submitting}
                    >
                      {GENRES.map((option) => (
                        <option key={option} value={option} className="bg-zinc-900">
                          {option}
                        </option>
                      ))}
                    </SelectInput>
                  </div>
                </div>
                <div>
                  <FieldLabel>Creative Brief</FieldLabel>
                  <TextArea
                    accent={accent}
                    data-testid="gate-brief"
                    value={brief}
                    onChange={(event) => setBrief(event.target.value)}
                    placeholder="Logline, tone, and what this film must make the audience feel…"
                    disabled={submitting}
                  />
                </div>
                {error && (
                  <p data-testid="gate-error" role="alert" className="text-sm text-rose-200">
                    {error}
                  </p>
                )}
                <button
                  type="submit"
                  data-testid="gate-submit"
                  disabled={submitting}
                  className="w-full rounded-lg border-2 px-4 py-3 text-sm font-bold uppercase tracking-[0.16em] text-zinc-50 transition-all duration-200 hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50"
                  style={{
                    borderColor: `${accent}99`,
                    background: `${accentDeep}66`,
                    boxShadow: `0 0 26px ${accent}33`,
                  }}
                >
                  {submitting ? 'Opening the Gate…' : 'Greenlight → Open on the Page'}
                </button>
              </form>
            </GlassPanel>

            {/* Right-hand holographic globe vessel frame */}
            <GlassPanel accent={accent} testid="gate-vessel-panel">
              <div className="mb-5 flex items-center gap-2">
                <Globe size={18} style={{ color: accent }} />
                <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-zinc-100">
                  Vessel · Active Bays
                </h2>
              </div>
              <div
                data-testid="vessel-globe"
                aria-hidden="true"
                className="relative mx-auto mb-6 h-44 w-44"
                style={{
                  borderRadius: '9999px',
                  background: `radial-gradient(circle at 35% 30%, ${accent}55 0%, transparent 55%), radial-gradient(circle at 70% 75%, ${accentDeep}88 0%, transparent 60%), radial-gradient(circle, #0a0d1c 0%, #04060d 72%)`,
                  border: `1px solid ${accent}66`,
                  boxShadow: `0 0 44px ${accent}44, inset 0 0 34px ${accentDeep}66`,
                  transform: `perspective(700px) rotateY(${vesselRotation}deg) rotateX(${vesselTilt}deg)`,
                  transition: 'transform 120ms ease-out',
                }}
              >
                <div
                  className="absolute inset-0 animate-spin"
                  style={{
                    borderRadius: '9999px',
                    borderTop: `1px solid ${accent}cc`,
                    borderRight: '1px solid transparent',
                    animationDuration: '14s',
                  }}
                />
                <div
                  className="absolute inset-4"
                  style={{ borderRadius: '9999px', border: `1px dashed ${accent}44` }}
                />
              </div>
              <div className="mx-auto mb-6 grid max-w-xs gap-3" aria-label="Vessel orientation controls">
                <label className="block text-[10px] uppercase tracking-[0.16em] text-zinc-400">
                  Rotation · {vesselRotation}°
                  <input
                    type="range"
                    min={-180}
                    max={180}
                    value={vesselRotation}
                    onChange={(event) => setVesselRotation(Number(event.target.value))}
                    data-testid="vessel-rotation"
                    aria-label="Vessel rotation"
                    className="mt-1 w-full accent-amber-200"
                  />
                </label>
                <label className="block text-[10px] uppercase tracking-[0.16em] text-zinc-400">
                  Tilt · {vesselTilt}°
                  <input
                    type="range"
                    min={-60}
                    max={60}
                    value={vesselTilt}
                    onChange={(event) => setVesselTilt(Number(event.target.value))}
                    data-testid="vessel-tilt"
                    aria-label="Vessel tilt"
                    className="mt-1 w-full accent-amber-200"
                  />
                </label>
              </div>
              {loadingBays ? (
                <p className="text-center text-sm text-zinc-400">Illuminating bays…</p>
              ) : bays.length === 0 ? (
                <p className="text-center text-sm text-zinc-400">
                  No productions docked yet.{' '}
                  <Link to="/studio" className="underline" style={{ color: accent }}>
                    Start one in the Atrium
                  </Link>
                  .
                </p>
              ) : (
                <ul data-testid="vessel-bays" className="grid gap-2 sm:grid-cols-2">
                  {bays.map((project) => (
                    <li key={project.project_id}>
                      <button
                        type="button"
                        data-testid={`vessel-bay-${project.project_id}`}
                        onClick={() => handleOpenBay(project.project_id)}
                        className="w-full rounded-xl border bg-black/45 p-3 text-left backdrop-blur-md transition-all duration-200 hover:scale-[1.01]"
                        style={{ borderColor: `${accent}44`, boxShadow: `0 0 18px ${accent}22` }}
                      >
                        <span
                          aria-hidden="true"
                          className="mb-2 block h-1 w-10 rounded-full"
                          style={{ background: accent, boxShadow: `0 0 10px ${accent}` }}
                        />
                        <span className="block truncate text-sm font-semibold text-zinc-100">
                          {project.title || 'Untitled Film'}
                        </span>
                        <span className="mt-0.5 block text-[11px] text-zinc-500">
                          Bay {project.project_id.slice(0, 8)} · open on the Page →
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </GlassPanel>
          </div>
        </div>
      </RoomBackdrop>
    </StudioShell>
  )
}

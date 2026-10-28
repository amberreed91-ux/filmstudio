import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { BookOpen, Save, Users } from 'lucide-react'
import StudioShell from '../components/StudioShell'
import {
  FieldLabel,
  GlassPanel,
  PanoramicHeader,
  RoomBackdrop,
  TextArea,
} from '../components/RoomCinematicChrome'
import { getProceduralRoomStyle } from '../lib/proceduralBackdrops'
import { useStudio } from '../context/StudioContext'
import { useProjectRouteContext } from '../hooks/useProjectRouteContext'
import {
  listCharacters,
  listScenes,
  updateScene,
  type CharacterRecord,
  type Scene,
} from '../lib/studioApi'
import { dossierStorageKey } from '../lib/dossierStorage'

type SceneDraft = { sceneId: string; text: string }

export default function PageRoom() {
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id')
  const { projectId } = useProjectRouteContext(queryProjectId)
  const { activeProject } = useStudio()
  const accent = getProceduralRoomStyle('page').tokens.accent

  const [scenes, setScenes] = useState<Scene[]>([])
  const [characters, setCharacters] = useState<{ projectId: string; items: CharacterRecord[] }>({
    projectId: '',
    items: [],
  })
  // Load state is keyed by project so a project switch reads as loading
  // without a synchronous state reset inside the effect.
  const [loadedProjectId, setLoadedProjectId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<{ projectId: string; message: string } | null>(null)
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null)
  // Drafts and save messages are tagged with their scene, so switching scenes
  // shows that scene's text without a reset effect.
  const [draftState, setDraftState] = useState<SceneDraft | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<SceneDraft | null>(null)

  const intakeBrief = useMemo(() => {
    if (!projectId) return null
    try {
      const raw = sessionStorage.getItem(dossierStorageKey(projectId))
      return raw ? (JSON.parse(raw) as { format: string; genre: string; brief: string }) : null
    } catch {
      return null
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    void Promise.all([listScenes(projectId), listCharacters(projectId)]).then(([sceneResult, characterResult]) => {
      if (cancelled) return
      if (sceneResult.error) {
        setLoadError({ projectId, message: sceneResult.error })
        setScenes([])
      } else {
        setScenes(sceneResult.scenes)
        setLoadError(null)
      }
      if (!characterResult.error) setCharacters({ projectId, items: characterResult.characters })
      setLoadedProjectId(projectId)
    })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const loading = Boolean(projectId) && loadedProjectId !== projectId
  const errorMessage = loadError?.projectId === projectId ? loadError.message : ''
  const characterList = characters.projectId === projectId ? characters.items : []

  const selectedScene = useMemo(
    () => scenes.find((scene) => scene.scene_id === selectedSceneId) ?? scenes[0] ?? null,
    [scenes, selectedSceneId],
  )

  const sceneId = selectedScene?.scene_id ?? null
  const draft = draftState && draftState.sceneId === sceneId
    ? draftState.text
    : (selectedScene?.description || selectedScene?.text || '')
  const saveMessageText = saveMessage && saveMessage.sceneId === sceneId ? saveMessage.text : ''

  async function handleSave() {
    if (!projectId || !selectedScene) return
    setSaving(true)
    const result = await updateScene(projectId, selectedScene.scene_id, { description: draft })
    if (result.error || !result.scene) {
      setSaveMessage({ sceneId: selectedScene.scene_id, text: result.error || 'Could not save this scene.' })
    } else {
      setScenes((previous) =>
        previous.map((scene) => (scene.scene_id === result.scene!.scene_id ? result.scene! : scene)),
      )
      setDraftState(null)
      setSaveMessage({ sceneId: selectedScene.scene_id, text: 'Saved to the screenplay.' })
    }
    setSaving(false)
  }

  return (
    <StudioShell title="Page" subtitle="Script development — scenes, screenplay, and story intent.">
      <RoomBackdrop roomKey="page" testid="page-room">
        <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 text-zinc-100 sm:px-6 lg:px-8">
          <PanoramicHeader
            eyebrow={`Fee Fee Anne Studios · Page${activeProject?.title ? ` · ${activeProject.title}` : ''}`}
            title="Script Development"
            lede="Navigate scenes on the left, write in the central screenplay editor, and keep character truth and scene intent floating on the right."
            accent={accent}
          />

          {!projectId ? (
            <GlassPanel accent={accent} testid="page-empty">
              <p className="text-sm leading-6 text-zinc-300">
                No film is on the Page yet. File one through{' '}
                <Link to="/studio/gate" className="underline" style={{ color: accent }}>
                  Gate intake
                </Link>{' '}
                or pick a film in{' '}
                <Link to="/studio" className="underline" style={{ color: accent }}>
                  the Atrium
                </Link>
                .
              </p>
            </GlassPanel>
          ) : loading ? (
            <GlassPanel accent={accent} testid="page-loading">
              <p className="text-sm text-zinc-400">Unrolling the screenplay…</p>
            </GlassPanel>
          ) : errorMessage ? (
            <GlassPanel accent={accent} testid="page-error">
              <p className="text-sm text-rose-200">{errorMessage}</p>
            </GlassPanel>
          ) : (
            <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)_280px]">
              {/* Scene navigator sidebar */}
              <GlassPanel accent={accent} testid="page-navigator" className="p-4">
                <div className="mb-3 flex items-center gap-2">
                  <BookOpen size={15} style={{ color: accent }} />
                  <h2 className="text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-200">
                    Scenes · {scenes.length}
                  </h2>
                </div>
                {scenes.length === 0 ? (
                  <p className="text-xs leading-5 text-zinc-500">No scenes yet — the first blank page is waiting.</p>
                ) : (
                  <ul data-testid="page-scene-list" className="max-h-[480px] space-y-1.5 overflow-y-auto">
                    {scenes.map((scene, index) => {
                      const active = scene.scene_id === selectedScene?.scene_id
                      return (
                        <li key={scene.scene_id}>
                          <button
                            type="button"
                            data-testid={`page-scene-${scene.scene_id}`}
                            onClick={() => {
                              setSelectedSceneId(scene.scene_id)
                              setDraftState(null)
                              setSaveMessage(null)
                            }}
                            className="w-full rounded-lg border p-2.5 text-left transition-all duration-150"
                            style={{
                              borderColor: active ? `${accent}88` : 'rgba(255,255,255,0.08)',
                              background: active ? `${accent}1a` : 'rgba(0,0,0,0.35)',
                              boxShadow: active ? `0 0 16px ${accent}33` : 'none',
                            }}
                          >
                            <span className="block text-[10px] font-mono uppercase tracking-[0.14em] text-zinc-500">
                              Sc {index + 1}
                            </span>
                            <span className="mt-0.5 block truncate text-xs font-semibold text-zinc-100">
                              {scene.scene_name || scene.heading || scene.scene_id}
                            </span>
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </GlassPanel>

              {/* Central screenplay editor */}
              <GlassPanel accent={accent} testid="page-editor-panel">
                {selectedScene ? (
                  <>
                    <FieldLabel>
                      {selectedScene.scene_name || selectedScene.heading || selectedScene.scene_id}
                    </FieldLabel>
                    <TextArea
                      accent={accent}
                      data-testid="page-editor"
                      value={draft}
                      onChange={(event) =>
                        setDraftState({ sceneId: selectedScene.scene_id, text: event.target.value })
                      }
                      className="min-h-[320px] font-mono leading-7"
                      placeholder="Write the scene…"
                    />
                    <div className="mt-3 flex items-center gap-3">
                      <button
                        type="button"
                        data-testid="page-save"
                        onClick={() => void handleSave()}
                        disabled={saving}
                        aria-busy={saving || undefined}
                        className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-xs font-bold uppercase tracking-[0.14em] text-zinc-50 transition-all hover:scale-[1.02] disabled:opacity-50"
                        style={{ borderColor: `${accent}88`, background: `${accent}22` }}
                      >
                        <Save size={14} />
                        {saving ? 'Saving…' : 'Save scene'}
                      </button>
                      {saveMessageText && (
                        <span data-testid="page-save-message" role="status" className="text-xs text-zinc-300">
                          {saveMessageText}
                        </span>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-zinc-500">Select a scene to begin writing.</p>
                )}
              </GlassPanel>

              {/* Floating context inspector */}
              <aside data-testid="page-inspector" className="space-y-4">
                <div
                  className="rounded-2xl border border-white/10 bg-[#0a0d18]/85 p-4 backdrop-blur-md"
                  style={{ boxShadow: `0 0 24px ${accent}22, 0 16px 45px rgba(0,0,0,0.5)` }}
                >
                  <div className="mb-3 flex items-center gap-2">
                    <Users size={15} style={{ color: accent }} />
                    <h2 className="text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-200">
                      Characters · {characterList.length}
                    </h2>
                  </div>
                  {characterList.length === 0 ? (
                    <p className="text-xs leading-5 text-zinc-500">No character profiles filed for this film.</p>
                  ) : (
                    <ul data-testid="page-characters" className="space-y-2">
                      {characterList.map((character) => (
                        <li
                          key={character.id}
                          data-testid={`page-character-${character.id}`}
                          className="rounded-lg border border-white/10 bg-black/40 p-2.5"
                        >
                          <span className="block text-xs font-semibold text-zinc-100">{character.name}</span>
                          {character.core_desire && (
                            <span className="mt-1 block text-[11px] leading-4 text-zinc-400">
                              Wants: {character.core_desire}
                            </span>
                          )}
                          {character.energy && (
                            <span className="mt-0.5 block text-[11px] leading-4 text-zinc-500">
                              {character.energy}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div
                  data-testid="page-intent"
                  className="rounded-2xl border border-white/10 bg-[#0a0d18]/85 p-4 backdrop-blur-md"
                  style={{ boxShadow: `0 0 24px ${accent}22, 0 16px 45px rgba(0,0,0,0.5)` }}
                >
                  <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-zinc-200">
                    Scene Intent
                  </h2>
                  {selectedScene ? (
                    <dl className="space-y-2 text-xs">
                      {[
                        ['Location', selectedScene.location || '—'],
                        ['Time', selectedScene.time_of_day || '—'],
                        ['Emotional tone', selectedScene.emotional_tone || '—'],
                        [
                          'Characters',
                          selectedScene.characters?.length ? selectedScene.characters.join(', ') : '—',
                        ],
                      ].map(([term, value]) => (
                        <div key={term} className="flex items-start justify-between gap-3">
                          <dt className="shrink-0 uppercase tracking-[0.12em] text-zinc-500">{term}</dt>
                          <dd className="text-right text-zinc-200">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p className="text-xs text-zinc-500">Intent cards appear once a scene is selected.</p>
                  )}
                  {intakeBrief?.brief && (
                    <div className="mt-3 rounded-lg border border-white/10 bg-black/40 p-2.5">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-400">
                        Intake brief · {intakeBrief.format} · {intakeBrief.genre}
                      </p>
                      <p className="mt-1 text-xs leading-4 text-zinc-300">{intakeBrief.brief}</p>
                    </div>
                  )}
                </div>
              </aside>
            </div>
          )}
        </div>
      </RoomBackdrop>
    </StudioShell>
  )
}

import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Plus, Edit2, Trash2, Save, X, Upload, FileUp } from 'lucide-react'
import StudioShell from '../components/StudioShell'
import ProjectContextBar from '../components/ProjectContextBar'
import ProjectGuard from '../components/ProjectGuard'
import { useStudio } from '../context/StudioContext'
import DirectorDebatePanel from '../components/DirectorDebatePanel'
import ProactiveCoDirectorCard from '../components/ProactiveCoDirectorCard'
import { useProactiveCoDirector } from '../hooks/useProactiveCoDirector'
import { PageScene } from '../rooms/ThePage'
import {
  checkBackendHealth,
  createProject,
  createScene,
  deleteScene,
  generateScenes,
  listScenes,
  updateScene,
  triggerDebate,
  type CreateScenePayload,
  type Scene,
  type CoDirectorDebateEntry,
} from '../lib/studioApi'

export default function WritersRoom() {
  const { projectId } = useParams()
  const [searchParams] = useSearchParams()
  const queryProjectId = searchParams.get('project_id') || ''
  const navigate = useNavigate()
  const { activeProject, activeProjectId } = useStudio()
  
  // Use activeProjectId from context, not from URL or localStorage
  const effectiveProjectId = activeProjectId || projectId || queryProjectId
  
  const { check: proactiveCheck, card: proactiveCard, dismiss: proactiveDismiss, saveToNotes: proactiveSaveToNotes } = useProactiveCoDirector(effectiveProjectId)

  const [scenes, setScenes] = useState<Scene[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [activeDebate, setActiveDebate] = useState<CoDirectorDebateEntry | null>(null)
  
  // Backend health check state
  const [backendHealthy, setBackendHealthy] = useState(true)
  const [healthCheckLoading, setHealthCheckLoading] = useState(false)
  
  // Script upload state
  const [scriptText, setScriptText] = useState('')
  const [uploadingScript, setUploadingScript] = useState(false)
  const [scriptUploadError, setScriptUploadError] = useState('')
  const [scriptUploadSuccess, setScriptUploadSuccess] = useState('')
  
  // Add/Edit scene form state
  const [showForm, setShowForm] = useState(false)
  const [editingSceneId, setEditingSceneId] = useState<string | null>(null)
  const [formData, setFormData] = useState<CreateScenePayload>({
    scene_name: '',
    description: '',
    location: '',
    time_of_day: 'DAY',
    emotional_tone: 'neutral',
    characters: [],
    notes: '',
  })
  const [characterInput, setCharacterInput] = useState('')

  // Load project and scenes
  useEffect(() => {
    if (effectiveProjectId) {
      void checkHealth()
    }
  }, [effectiveProjectId])

  // Check backend health before loading scenes
  const checkHealth = async () => {
    setHealthCheckLoading(true)
    const health = await checkBackendHealth()
    setBackendHealthy(health.healthy)
    setHealthCheckLoading(false)
    
    if (health.healthy) {
      void loadScenes()
    }
  }

  const retryHealthCheck = () => {
    void checkHealth()
  }

  const loadScenes = async () => {
    if (!effectiveProjectId) return
    setLoading(true)
    setError('')
    try {
      const result = await listScenes(effectiveProjectId)
      if (result.error) {
        setError(result.error)
      } else {
        setScenes(result.scenes)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scenes')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateProject = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await createProject({ title: 'New Film Project' })
      if (result.error) {
        setError(result.error)
      } else if (result.project) {
        localStorage.setItem('studio:activeProjectId', result.project.project_id)
        navigate(`/studio/writers-room?project_id=${result.project.project_id}`)
        setSuccess('Project created successfully')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project')
    } finally {
      setLoading(false)
    }
  }

  const handleAddScene = () => {
    setEditingSceneId(null)
    setFormData({
      scene_name: '',
      description: '',
      location: '',
      time_of_day: 'DAY',
      emotional_tone: 'neutral',
      characters: [],
      notes: '',
    })
    setCharacterInput('')
    setShowForm(true)
  }

  const handleEditScene = (scene: Scene) => {
    setEditingSceneId(scene.scene_id)
    setFormData({
      scene_name: scene.scene_name,
      description: scene.description,
      location: scene.location,
      time_of_day: scene.time_of_day,
      emotional_tone: scene.emotional_tone,
      characters: scene.characters || [],
      notes: scene.notes,
      is_major_plot_point: scene.is_major_plot_point,
    })
    setCharacterInput('')
    setShowForm(true)
  }

  const handleSaveScene = async () => {
    if (!effectiveProjectId) {
      setError('No active project. Please create a project first.')
      return
    }

    if (!formData.scene_name.trim()) {
      setError('Scene name is required')
      return
    }

    setLoading(true)
    setError('')
    setSuccess('')

    try {
      if (editingSceneId) {
        // Update existing scene
        const result = await updateScene(effectiveProjectId, editingSceneId, formData)
        if (result.error) {
          setError(result.error)
        } else {
          setSuccess('Scene updated successfully')
          setShowForm(false)
          await loadScenes()

          // Proactive co-director check after scene save
          void proactiveCheck('scene_save', { sceneId: editingSceneId })

          // Trigger debate if major plot point or significant decision in description
          const isSignificant = formData.is_major_plot_point || 
            /dies|death|redemption|betrayal|act break|ending|finale|debate this/i.test(formData.description);
            
          if (isSignificant) {
            const { debate } = await triggerDebate({
              project_id: effectiveProjectId,
              scene_id: editingSceneId,
              query: formData.description || `Analyze updated major plot point: "${formData.scene_name}"`,
            })
            setActiveDebate(debate)
          }
        }
      } else {
        // Create new scene
        const result = await createScene(effectiveProjectId, formData)
        if (result.error) {
          setError(result.error)
        } else {
          setSuccess('Scene created successfully')
          setShowForm(false)
          await loadScenes()

          // Proactive co-director check after scene save
          if (result.scene) {
            void proactiveCheck('scene_save', { sceneId: result.scene.scene_id })
          }

          // Trigger debate if major plot point or significant decision in description
          const isSignificant = formData.is_major_plot_point || 
            /dies|death|redemption|betrayal|act break|ending|finale|debate this/i.test(formData.description);
            
          if (isSignificant && result.scene) {
            const { debate } = await triggerDebate({
              project_id: effectiveProjectId,
              scene_id: result.scene.scene_id,
              query: formData.description || `Analyze new major plot point: "${formData.scene_name}"`,
            })
            setActiveDebate(debate)
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save scene')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteScene = async (sceneId: string) => {
    if (!effectiveProjectId) return
    if (!confirm('Are you sure you want to delete this scene?')) return

    setLoading(true)
    setError('')
    try {
      const result = await deleteScene(effectiveProjectId, sceneId)
      if (result.error) {
        setError(result.error)
      } else {
        setSuccess('Scene deleted successfully')
        await loadScenes()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete scene')
    } finally {
      setLoading(false)
    }
  }

  const handleAddCharacter = () => {
    const char = characterInput.trim()
    if (char && !formData.characters.includes(char)) {
      setFormData({ ...formData, characters: [...formData.characters, char] })
      setCharacterInput('')
    }
  }

  const handleRemoveCharacter = (char: string) => {
    setFormData({ ...formData, characters: formData.characters.filter((c) => c !== char) })
  }

  const handleGoToStoryboard = () => {
    if (effectiveProjectId) {
      navigate(`/studio/previs?project_id=${effectiveProjectId}`)
    }
  }

  const handleScriptUpload = async () => {
    if (!effectiveProjectId) {
      setScriptUploadError('No active project. Please create a project first.')
      return
    }

    if (!scriptText.trim()) {
      setScriptUploadError('Please paste your script or upload a file')
      return
    }

    setUploadingScript(true)
    setScriptUploadError('')
    setScriptUploadSuccess('')

    try {
      const result = await generateScenes(effectiveProjectId, scriptText.trim())
      
      if (result.error) {
        setScriptUploadError(result.error)
      } else if (result.project) {
        // Count how many scenes were created
        const executionSummary = result.project.execution_summary || {}
        const scenesArray = Array.isArray(executionSummary.scenes) ? executionSummary.scenes : []
        const sceneCount = scenesArray.length
        
        setScriptUploadSuccess(`Found ${sceneCount} scene${sceneCount !== 1 ? 's' : ''} in your script!`)
        setScriptText('') // Clear the textarea
        
        // Reload scenes to show the newly created ones
        await loadScenes()
      }
    } catch (err) {
      setScriptUploadError(err instanceof Error ? err.message : 'Failed to import script')
    } finally {
      setUploadingScript(false)
    }
  }

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result
      if (typeof text === 'string') {
        setScriptText(text)
        setScriptUploadSuccess(`Loaded ${file.name}`)
        setScriptUploadError('')
      }
    }
    reader.onerror = () => {
      setScriptUploadError('Failed to read file')
    }
    reader.readAsText(file)
  }

  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh' }}>
      {/* 3D environment */}
      <div style={{ position: 'absolute', inset: 0 }}>
        <PageScene />
      </div>
      {/* UI overlay */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 10, pointerEvents: 'auto' }}>
        <StudioShell title="Writer's Room" subtitle="Create and manage your film scenes" transparent>
        <ProjectGuard>
          <ProjectContextBar roomName="writer's room" />
          <div className="w-full overflow-visible relative" style={{ background: 'var(--color-surface-0)', zIndex: 1 }}>
            <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-8">

              {/* Room Hero - "The Page" */}
              <section className="rounded-2xl border p-8" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border)' }}>
                <div className="text-[11px] uppercase tracking-[0.2em]" style={{ color: 'var(--color-accent)' }}>Writers Room</div>
                <h1 className="mt-3 text-4xl font-light tracking-tight" style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.02em' }}>
                  The Page
                </h1>
                <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  Craft your narrative. Shape your scenes. Build your story.
                </p>
              </section>

              {/* Project Header */}
              <section className="rounded-lg border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-secondary)' }}>
                      Current Project
                    </div>
                    <h2 className="mt-2 text-lg font-light" style={{ color: 'var(--color-text-primary)' }}>
                      {activeProject?.title || 'Untitled Project'}
                    </h2>
                    {effectiveProjectId && (
                      <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>Project ID: {effectiveProjectId}</p>
                    )}
                  </div>
                  {!effectiveProjectId && (
                    <button
                      type="button"
                      onClick={handleCreateProject}
                      disabled={loading}
                      className="rounded-lg border px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] transition hover:border-[#00d4aa]"
                      style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border)', color: 'var(--color-accent)' }}
                    >
                      Create New Project
                    </button>
                  )}
                </div>
              </section>

            {/* Error/Success Messages */}
            {error && (
              <div className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {error}
              </div>
            )}
            {success && (
              <div className="rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                {success}
              </div>
            )}

            {/* Backend Health Check */}
            {!backendHealthy && effectiveProjectId && (
              <div className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-4 py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-semibold text-amber-200">Studio is starting up</div>
                    <div className="mt-1 text-xs text-amber-100">
                      Please wait a moment while the backend initializes...
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={retryHealthCheck}
                    disabled={healthCheckLoading}
                    className="rounded-lg border border-amber-300/50 bg-amber-500/14 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-amber-100 transition-all duration-200 hover:scale-[1.02] disabled:opacity-50"
                  >
                    {healthCheckLoading ? 'Checking...' : 'Retry'}
                  </button>
                </div>
              </div>
            )}

            {/* Script Upload Section - Option A */}
            {effectiveProjectId && backendHealthy && (
              <section className="cinematic-panel p-6">
                <div className="mb-4">
                  <h3 className="text-lg font-semibold uppercase tracking-[0.14em] text-zinc-100">
                    Option A — Upload Script
                  </h3>
                  <p className="mt-1 text-xs text-zinc-400">
                    Have a script? Upload it and we'll break it into scenes.
                  </p>
                </div>

                {scriptUploadError && (
                  <div className="mb-4 rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                    {scriptUploadError}
                  </div>
                )}
                {scriptUploadSuccess && (
                  <div className="mb-4 rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                    {scriptUploadSuccess}
                  </div>
                )}

                <div className="space-y-4">
                  {/* File Upload Button */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                      Upload Script File
                    </label>
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-2 rounded-lg border border-cyan-300/50 bg-cyan-500/14 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100 transition-all duration-200 hover:scale-[1.02] cursor-pointer">
                        <FileUp size={16} />
                        Choose File (.txt, .pdf)
                        <input
                          type="file"
                          accept=".txt,.pdf"
                          onChange={handleFileUpload}
                          className="hidden"
                        />
                      </label>
                      <span className="text-xs text-zinc-400">or paste your script below</span>
                    </div>
                  </div>

                  {/* Script Textarea */}
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                      Paste Your Script Here
                    </label>
                    <textarea
                      value={scriptText}
                      onChange={(e) => setScriptText(e.target.value)}
                      className="w-full h-48 rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20 font-mono"
                      placeholder="Paste your script here...

Example format:

SCENE 1: INT. COFFEE SHOP - DAY
A woman sits alone at a corner table, reading a worn paperback. The café is nearly empty. Rain streaks the window behind her.

SCENE 2: EXT. STREET - NIGHT
She walks through the rain, umbrella forgotten. The city lights blur in the downpour."
                    />
                  </div>

                  {/* Import Button */}
                  <button
                    type="button"
                    onClick={handleScriptUpload}
                    disabled={uploadingScript || !scriptText.trim()}
                    className="w-full flex items-center justify-center gap-2 rounded-lg border border-emerald-300/60 bg-emerald-500/22 px-4 py-3 text-sm font-bold uppercase tracking-[0.14em] text-emerald-50 shadow-[0_0_26px_rgba(16,185,129,0.22)] transition-all duration-200 hover:scale-[1.01] disabled:opacity-50"
                  >
                    <Upload size={16} />
                    {uploadingScript ? 'Importing Script...' : 'Import Script'}
                  </button>
                </div>
              </section>
            )}

            {/* Manual Scene Entry Section - Option B */}
            {effectiveProjectId && backendHealthy && (
              <section className="cinematic-panel p-6">
                <div className="mb-4">
                  <h3 className="text-lg font-semibold uppercase tracking-[0.14em] text-zinc-100">
                    Option B — Add Scenes Manually
                  </h3>
                  <p className="mt-1 text-xs text-zinc-400">
                    Building from scratch? Add scenes one by one.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleAddScene}
                  disabled={loading}
                  className="flex items-center gap-2 rounded-lg border border-cyan-300/50 bg-cyan-500/14 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100 transition-all duration-200 hover:scale-[1.02] disabled:opacity-50"
                >
                  <Plus size={16} />
                  Add Scene
                </button>
              </section>
            )}

            {/* Scene List */}
            {effectiveProjectId && backendHealthy && (
              <section className="rounded-lg border p-5" style={{ background: 'var(--color-surface-1)', borderColor: 'var(--color-border-subtle)' }}>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-sm uppercase tracking-[0.12em]" style={{ color: 'var(--color-text-primary)' }}>
                      Your Scenes ({scenes.length})
                    </h3>
                    <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                      All scenes from script upload and manual entry
                    </p>
                  </div>
                </div>

                {loading && scenes.length === 0 ? (
                  <div className="text-center py-8" style={{ color: 'var(--color-text-secondary)' }}>Loading scenes...</div>
                ) : scenes.length === 0 ? (
                  <div className="text-center py-8" style={{ color: 'var(--color-text-secondary)' }}>
                    No scenes yet. Upload a script or add scenes manually above.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {scenes.map((scene) => (
                      <div
                        key={scene.scene_id}
                        className="rounded-lg border p-4 transition-all hover:border-[#00d4aa]"
                        style={{ background: 'var(--color-surface-2)', borderColor: 'var(--color-border-subtle)' }}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h4 className="text-sm font-light" style={{ color: 'var(--color-text-primary)' }}>{scene.scene_name}</h4>
                            <p className="mt-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{scene.description}</p>
                            <div className="mt-2 flex flex-wrap gap-2 text-xs">
                              <span className="rounded px-2 py-1" style={{ background: 'var(--color-surface-3)', color: 'var(--color-text-secondary)' }}>
                                {scene.location || 'No location'}
                              </span>
                              <span className="rounded px-2 py-1" style={{ background: 'var(--color-surface-3)', color: 'var(--color-text-secondary)' }}>
                                {scene.time_of_day}
                              </span>
                              <span className="rounded px-2 py-1" style={{ background: 'var(--color-surface-3)', color: 'var(--color-text-secondary)' }}>
                                {scene.emotional_tone}
                              </span>
                              {scene.characters && scene.characters.length > 0 && (
                                <span className="rounded px-2 py-1" style={{ background: 'var(--color-surface-3)', color: 'var(--color-text-secondary)' }}>
                                  {scene.characters.join(', ')}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex gap-2 ml-4">
                            <button
                              type="button"
                              onClick={() => handleEditScene(scene)}
                              className="rounded border border-amber-400/40 bg-amber-500/12 p-2 text-amber-100 transition-all hover:bg-amber-500/20"
                              title="Edit scene"
                            >
                              <Edit2 size={14} />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteScene(scene.scene_id)}
                              className="rounded border border-rose-400/40 bg-rose-500/12 p-2 text-rose-100 transition-all hover:bg-rose-500/20"
                              title="Delete scene"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Next Step CTA */}
                {scenes.length > 0 && (
                  <div className="mt-6 rounded-xl border border-emerald-400/35 bg-emerald-500/10 p-4">
                    <div className="text-xs uppercase tracking-[0.12em] text-emerald-200 mb-2">
                      Ready to Continue?
                    </div>
                    <button
                      type="button"
                      onClick={handleGoToStoryboard}
                      className="w-full rounded-lg border border-emerald-300/60 bg-emerald-500/22 px-4 py-3 text-sm font-bold uppercase tracking-[0.14em] text-emerald-50 shadow-[0_0_26px_rgba(16,185,129,0.22)] transition-all duration-200 hover:scale-[1.01]"
                    >
                      Next: Go to Storyboard / Scenes Room
                    </button>
                  </div>
                )}
              </section>
            )}

            {/* Proactive Co-Director Card */}
            {proactiveCard && (
              <div className="mb-2">
                <ProactiveCoDirectorCard
                  message={proactiveCard.message}
                  triggerType={proactiveCard.trigger_type}
                  saveToNotes={proactiveCard.save_to_notes}
                  onDismiss={proactiveDismiss}
                  onSaveToNotes={proactiveCard.save_to_notes ? () => proactiveSaveToNotes() : undefined}
                />
              </div>
            )}

            {/* Add/Edit Scene Form */}
            {activeDebate && (
              <div className="mb-6">
                <DirectorDebatePanel
                  projectId={effectiveProjectId}
                  debate={activeDebate}
                  onDismiss={() => setActiveDebate(null)}
                />
              </div>
            )}

            {showForm && (
              <section className="cinematic-panel p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold uppercase tracking-[0.14em] text-zinc-100">
                    {editingSceneId ? 'Edit Scene' : 'Add New Scene'}
                  </h3>
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    className="rounded border border-zinc-600 bg-zinc-800 p-2 text-zinc-300 transition-all hover:bg-zinc-700"
                    title="Close form"
                  >
                    <X size={16} />
                  </button>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                      Scene Name *
                    </label>
                    <input
                      type="text"
                      value={formData.scene_name}
                      onChange={(e) => setFormData({ ...formData, scene_name: e.target.value })}
                      className="w-full rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20"
                      placeholder="e.g., Opening Scene, The Confrontation"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                      Description
                    </label>
                    <textarea
                      value={formData.description}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      className="w-full h-24 rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20"
                      placeholder="Describe what happens in this scene..."
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                        Location
                      </label>
                      <input
                        type="text"
                        value={formData.location}
                        onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                        className="w-full rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20"
                        placeholder="e.g., INT. APARTMENT, EXT. STREET"
                      />
                    </div>

                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        id="is_major_plot_point"
                        checked={formData.is_major_plot_point}
                        onChange={(e) => setFormData({ ...formData, is_major_plot_point: e.target.checked })}
                        className="h-4 w-4 rounded border-white/15 bg-black/55 text-indigo-500 focus:ring-indigo-500/20"
                      />
                      <label htmlFor="is_major_plot_point" className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300">
                        Mark as Major Plot Point (Triggers Co-Director Debate)
                      </label>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                        Time of Day
                      </label>
                      <select
                        value={formData.time_of_day}
                        onChange={(e) => setFormData({ ...formData, time_of_day: e.target.value })}
                        className="w-full rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20"
                      >
                        <option value="DAY">Day</option>
                        <option value="NIGHT">Night</option>
                        <option value="DAWN">Dawn</option>
                        <option value="DUSK">Dusk</option>
                        <option value="MORNING">Morning</option>
                        <option value="AFTERNOON">Afternoon</option>
                        <option value="EVENING">Evening</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                      Emotional Tone
                    </label>
                    <select
                      value={formData.emotional_tone}
                      onChange={(e) => setFormData({ ...formData, emotional_tone: e.target.value })}
                      className="w-full rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20"
                    >
                      <option value="neutral">Neutral</option>
                      <option value="tense">Tense</option>
                      <option value="joyful">Joyful</option>
                      <option value="melancholic">Melancholic</option>
                      <option value="suspenseful">Suspenseful</option>
                      <option value="romantic">Romantic</option>
                      <option value="dramatic">Dramatic</option>
                      <option value="comedic">Comedic</option>
                      <option value="mysterious">Mysterious</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                      Characters
                    </label>
                    <div className="flex gap-2 mb-2">
                      <input
                        type="text"
                        value={characterInput}
                        onChange={(e) => setCharacterInput(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddCharacter())}
                        className="flex-1 rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20"
                        placeholder="Add character name and press Enter"
                      />
                      <button
                        type="button"
                        onClick={handleAddCharacter}
                        className="rounded-lg border border-cyan-300/50 bg-cyan-500/14 px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100"
                      >
                        Add
                      </button>
                    </div>
                    {formData.characters.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {formData.characters.map((char) => (
                          <span
                            key={char}
                            className="flex items-center gap-2 rounded border border-white/10 bg-black/25 px-2 py-1 text-xs text-zinc-300"
                          >
                            {char}
                            <button
                              type="button"
                              onClick={() => handleRemoveCharacter(char)}
                              className="text-rose-400 hover:text-rose-300"
                            >
                              <X size={12} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                      Notes
                    </label>
                    <textarea
                      value={formData.notes}
                      onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                      className="w-full h-20 rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20"
                      placeholder="Additional notes or ideas for this scene..."
                    />
                  </div>

                  <div className="flex gap-3 pt-4">
                    <button
                      type="button"
                      onClick={handleSaveScene}
                      disabled={loading || !formData.scene_name.trim()}
                      className="flex-1 flex items-center justify-center gap-2 rounded-lg border border-emerald-300/60 bg-emerald-500/22 px-4 py-3 text-sm font-bold uppercase tracking-[0.14em] text-emerald-50 shadow-[0_0_26px_rgba(16,185,129,0.22)] transition-all duration-200 hover:scale-[1.01] disabled:opacity-50"
                    >
                      <Save size={16} />
                      {loading ? 'Saving...' : editingSceneId ? 'Update Scene' : 'Create Scene'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowForm(false)}
                      className="rounded-lg border border-zinc-600 bg-zinc-800 px-4 py-3 text-sm font-semibold uppercase tracking-[0.12em] text-zinc-300 transition-all hover:bg-zinc-700"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </section>
            )}
          </div>
          </div>
        </ProjectGuard>
        </StudioShell>
      </div>
    </div>
  )
}
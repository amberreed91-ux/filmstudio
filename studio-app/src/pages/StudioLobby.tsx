import StudioShell from '../components/StudioShell'
import { lazyLoad } from '../components/LazyLoad'
import { Link, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Plus, Film, Trash2, X, Box } from 'lucide-react'
import { useStudio } from '../context/StudioContext'
import { createProject, deleteProject, listProjects, type PersistedProjectState } from '../lib/studioApi'

// Lazy load AICrewPresence to improve initial load performance
const LazyAICrewPresence = lazyLoad(
  () => import('../components/AICrewPresence'),
  <div className="animate-pulse bg-zinc-800/50 h-24 rounded-lg mb-4" />
)

export default function StudioLobby() {
  const navigate = useNavigate()
  const { setActiveProject } = useStudio()
  
  // Project list state
  const [projects, setProjects] = useState<PersistedProjectState[]>([])
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [projectsError, setProjectsError] = useState('')
  
  // New project modal state
  const [showNewProjectModal, setShowNewProjectModal] = useState(false)
  const [newProjectTitle, setNewProjectTitle] = useState('')
  const [newProjectDescription, setNewProjectDescription] = useState('')
  const [creatingProject, setCreatingProject] = useState(false)
  const [createError, setCreateError] = useState('')
  
  // Delete confirmation state
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null)
  
  // Load projects on mount
  useEffect(() => {
    void loadProjectList()
  }, [])
  
  async function loadProjectList() {
    setLoadingProjects(true)
    setProjectsError('')
    try {
      const result = await listProjects()
      if (result.error) {
        setProjectsError(result.error)
      } else {
        // Filter out demo projects
        const nonDemoProjects = result.projects.filter(
          (p) => !p.project_id.includes('demo_studio_cinematic')
        )
        setProjects(nonDemoProjects)
      }
    } catch (err) {
      setProjectsError(err instanceof Error ? err.message : 'Failed to load projects')
    } finally {
      setLoadingProjects(false)
    }
  }
  
  async function handleCreateNewProject() {
    if (!newProjectTitle.trim()) {
      setCreateError('Film title is required')
      return
    }
    
    setCreatingProject(true)
    setCreateError('')
    
    try {
      const result = await createProject({
        title: newProjectTitle.trim(),
      })
      
      if (result.error) {
        setCreateError(result.error)
      } else if (result.project) {
        // Set as active project using sessionStorage
        await setActiveProject(result.project.project_id)
        
        // Navigate to Writer's Room
        navigate(`/studio/writers-room?project_id=${result.project.project_id}`)
      }
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create project')
    } finally {
      setCreatingProject(false)
    }
  }
  
  async function handleSelectProject(projectId: string) {
    // Set as active project using sessionStorage
    await setActiveProject(projectId)
    
    // Navigate to Overview
    navigate(`/studio/overview?project_id=${projectId}`)
  }
  
  function handleDeleteProject(projectId: string) {
    setDeletingProjectId(projectId)
  }
  
  async function confirmDeleteProject() {
    if (!deletingProjectId) return
    
    // Call the delete API endpoint
    const result = await deleteProject(deletingProjectId)
    
    if (result.error) {
      setProjectsError(`Failed to delete project: ${result.error}`)
      setDeletingProjectId(null)
      return
    }
    
    // Clear from sessionStorage if it's the active project
    const activeProjectId = sessionStorage.getItem('studio:active-project-id')
    if (activeProjectId === deletingProjectId) {
      sessionStorage.removeItem('studio:active-project-id')
      setActiveProject(null)
    }
    
    setDeletingProjectId(null)
    void loadProjectList()
  }
  
  function getSceneCount(project: PersistedProjectState): number {
    try {
      const summary = project.execution_summary
      if (summary && typeof summary === 'object' && 'scenes' in summary) {
        const scenes = summary.scenes
        return Array.isArray(scenes) ? scenes.length : 0
      }
    } catch {
      return 0
    }
    return 0
  }
  
  function getProjectStatus(project: PersistedProjectState): string {
    const sceneCount = getSceneCount(project)
    if (sceneCount === 0) return 'Just started'
    if (sceneCount < 3) return 'In progress'
    return 'In progress'
  }
  
  function formatDate(dateString: string): string {
    try {
      const date = new Date(dateString)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
      
      if (diffDays === 0) return 'Today'
      if (diffDays === 1) return 'Yesterday'
      if (diffDays < 7) return `${diffDays} days ago`
      if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
      return date.toLocaleDateString()
    } catch {
      return 'Unknown'
    }
  }

  return (
    <StudioShell title="Studio Home" subtitle="Start a new film or continue working on an existing project.">
      <div className="w-full overflow-visible bg-background">
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-8 text-zinc-100">
          
          {/* Hero Section - Start a New Film */}
          <section className="cinematic-panel p-8 text-center">
            <h1 className="text-3xl font-bold tracking-wide text-zinc-100 mb-3">
              Welcome to Studio
            </h1>
            <p className="text-lg text-zinc-300 mb-6">
              Create cinematic short films from script to screen
            </p>
            
            <button
              type="button"
              onClick={() => setShowNewProjectModal(true)}
              className="inline-flex items-center gap-3 rounded-lg border-2 border-emerald-400/60 bg-emerald-500/20 px-8 py-4 text-lg font-bold uppercase tracking-[0.14em] text-emerald-50 shadow-[0_0_30px_rgba(16,185,129,0.25)] transition-all duration-200 hover:scale-[1.02] hover:shadow-[0_0_40px_rgba(16,185,129,0.35)]"
            >
              <Plus size={24} />
              Start a New Film
            </button>
            
            <p className="mt-3 text-sm text-zinc-400">
              Create a new project from scratch
            </p>
          </section>

          {/* Existing Projects */}
          {loadingProjects ? (
            <section className="cinematic-panel p-6">
              <div className="text-center py-8 text-zinc-400">Loading your films...</div>
            </section>
          ) : projectsError ? (
            <section className="cinematic-panel p-6">
              <div className="text-center py-8 text-rose-200">{projectsError}</div>
            </section>
          ) : projects.length > 0 ? (
            <section className="cinematic-panel p-6">
              <h2 className="text-xl font-semibold uppercase tracking-[0.14em] text-zinc-100 mb-4">
                Continue a Film
              </h2>
              <p className="text-sm text-zinc-400 mb-6">
                Pick up where you left off
              </p>
              
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {projects.map((project) => (
                  <div
                    key={project.project_id}
                    className="group relative rounded-xl border border-white/10 bg-black/35 p-5 transition-all duration-200 hover:border-cyan-400/50 hover:bg-black/50 cursor-pointer"
                    onClick={() => handleSelectProject(project.project_id)}
                  >
                    {/* Delete Button */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeleteProject(project.project_id)
                      }}
                      className="absolute top-3 right-3 rounded border border-rose-400/40 bg-rose-500/12 p-1.5 text-rose-200 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-rose-500/20"
                      title="Delete film"
                    >
                      <Trash2 size={14} />
                    </button>
                    
                    {/* Film Icon */}
                    <div className="mb-3 flex items-center gap-2">
                      <div className="rounded-lg border border-cyan-400/40 bg-cyan-500/10 p-2">
                        <Film size={20} className="text-cyan-300" />
                      </div>
                    </div>
                    
                    {/* Film Title */}
                    <h3 className="text-lg font-semibold text-zinc-100 mb-2 line-clamp-2">
                      {project.title || 'Untitled Film'}
                    </h3>
                    
                    {/* Film Stats */}
                    <div className="space-y-1.5 text-xs text-zinc-400">
                      <div className="flex items-center justify-between">
                        <span>Scenes:</span>
                        <span className="text-zinc-200">{getSceneCount(project)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span>Last edited:</span>
                        <span className="text-zinc-200">{formatDate(project.updated_at)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span>Status:</span>
                        <span className="rounded border border-emerald-400/40 bg-emerald-500/10 px-2 py-0.5 text-emerald-200">
                          {getProjectStatus(project)}
                        </span>
                      </div>
                    </div>
                    
                    {/* Hover Indicator */}
                    <div className="mt-4 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-300 opacity-0 transition-opacity group-hover:opacity-100">
                      Click to open →
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : (
            <section className="cinematic-panel p-6">
              <div className="text-center py-8">
                <p className="text-zinc-400 mb-4">No films yet. Start your first project above!</p>
              </div>
            </section>
          )}

          {/* Room Directory */}
          <section className="cinematic-panel p-6">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold uppercase tracking-[0.14em] text-zinc-100">
                  Room Directory
                </h2>
                <p className="mt-1 text-sm text-zinc-400">
                  Navigate to different areas of the studio
                </p>
              </div>
              <Link
                to="/studio/lobby-3d"
                data-testid="enter-3d-lobby"
                className="inline-flex items-center gap-2 rounded-full border border-amber-200/30 bg-amber-400/10 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-100 no-underline shadow-[0_0_18px_rgba(214,169,92,0.18)] backdrop-blur-md transition-all duration-200 hover:border-amber-200/60 hover:bg-amber-400/20 hover:shadow-[0_0_26px_rgba(214,169,92,0.32)]"
              >
                <Box size={14} />
                3D Studio Lobby
              </Link>
            </div>
            <div className="mb-6" />
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {[
                { title: "Writer's Room", desc: 'Draft and manage your script', to: '/studio/writers-room', color: 'cyan' },
                { title: 'Storyboard', desc: 'Review scenes and visuals', to: '/studio/previs', color: 'amber' },
                { title: 'Scenes', desc: 'Track scene production', to: '/studio/production-board', color: 'purple' },
                { title: 'Watch', desc: 'Screen your film', to: '/studio/screening-room', color: 'emerald' },
                { title: 'Study Room', desc: 'Analyze story structure', to: '/studio/study-room', color: 'blue' },
                { title: 'Archive', desc: 'Review version history', to: '/studio/archive', color: 'zinc' },
              ].map((room) => (
                <Link
                  key={room.title}
                  to={room.to}
                  className="group rounded-xl border border-white/10 bg-black/35 p-4 transition-all duration-200 hover:border-white/30 hover:bg-black/50 no-underline"
                >
                  <div className="text-sm font-semibold text-zinc-100 mb-1">{room.title}</div>
                  <div className="text-xs text-zinc-400">{room.desc}</div>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>

      {/* New Project Modal */}
      {showNewProjectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className="relative w-full max-w-lg rounded-xl border border-white/20 bg-zinc-900 p-6 shadow-2xl">
            {/* Close Button */}
            <button
              type="button"
              onClick={() => {
                setShowNewProjectModal(false)
                setNewProjectTitle('')
                setNewProjectDescription('')
                setCreateError('')
              }}
              className="absolute top-4 right-4 rounded border border-zinc-600 bg-zinc-800 p-1.5 text-zinc-300 transition-all hover:bg-zinc-700"
            >
              <X size={16} />
            </button>

            {/* Modal Header */}
            <h2 className="text-2xl font-bold text-zinc-100 mb-2">Start a New Film</h2>
            <p className="text-sm text-zinc-400 mb-6">Create a new project and begin your filmmaking journey</p>

            {/* Error Message */}
            {createError && (
              <div className="mb-4 rounded-lg border border-rose-400/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {createError}
              </div>
            )}

            {/* Form */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                  What's your film called? *
                </label>
                <input
                  type="text"
                  value={newProjectTitle}
                  onChange={(e) => setNewProjectTitle(e.target.value)}
                  placeholder="e.g., Neon Aftertaste, The Last Frame"
                  className="w-full rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-emerald-300/60 focus:ring-2 focus:ring-emerald-300/20"
                  disabled={creatingProject}
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm font-semibold uppercase tracking-[0.12em] text-zinc-300 mb-2">
                  What kind of film is it? (optional)
                </label>
                <input
                  type="text"
                  value={newProjectDescription}
                  onChange={(e) => setNewProjectDescription(e.target.value)}
                  placeholder="e.g., Sci-fi thriller, Drama, Experimental"
                  className="w-full rounded-lg border border-white/15 bg-black/55 p-3 text-sm text-zinc-100 outline-none transition-all duration-200 focus:border-emerald-300/60 focus:ring-2 focus:ring-emerald-300/20"
                  disabled={creatingProject}
                />
              </div>

              {/* Action Buttons */}
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => void handleCreateNewProject()}
                  disabled={creatingProject || !newProjectTitle.trim()}
                  className="flex-1 rounded-lg border border-emerald-300/60 bg-emerald-500/22 px-4 py-3 text-sm font-bold uppercase tracking-[0.14em] text-emerald-50 shadow-[0_0_26px_rgba(16,185,129,0.22)] transition-all duration-200 hover:scale-[1.01] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {creatingProject ? 'Creating Film...' : 'Create Film'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowNewProjectModal(false)
                    setNewProjectTitle('')
                    setNewProjectDescription('')
                    setCreateError('')
                  }}
                  disabled={creatingProject}
                  className="rounded-lg border border-zinc-600 bg-zinc-800 px-4 py-3 text-sm font-semibold uppercase tracking-[0.12em] text-zinc-300 transition-all hover:bg-zinc-700 disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingProjectId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className="relative w-full max-w-md rounded-xl border border-rose-400/40 bg-zinc-900 p-6 shadow-2xl">
            <h2 className="text-xl font-bold text-rose-200 mb-2">Delete this film?</h2>
            <p className="text-sm text-zinc-300 mb-6">
              This action cannot be undone. All scenes, renders, and project data will be permanently deleted.
            </p>

            <div className="flex gap-3">
              <button
                type="button"
                onClick={confirmDeleteProject}
                className="flex-1 rounded-lg border border-rose-400/60 bg-rose-500/20 px-4 py-3 text-sm font-bold uppercase tracking-[0.14em] text-rose-100 transition-all duration-200 hover:bg-rose-500/30"
              >
                Delete Film
              </button>
              <button
                type="button"
                onClick={() => setDeletingProjectId(null)}
                className="rounded-lg border border-zinc-600 bg-zinc-800 px-4 py-3 text-sm font-semibold uppercase tracking-[0.12em] text-zinc-300 transition-all hover:bg-zinc-700"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <LazyAICrewPresence />
    </StudioShell>
  )
}

import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Eye, Film, Clapperboard, Users, ArrowLeft, Loader2, MessageSquare } from 'lucide-react'
import { getSharedProject, listScenes, type StudioProject, type Scene } from '../lib/studioApi'
import { ProviderModelLabel } from '../components/ProviderPicker'
import CollaboratorRoleBadge from '../components/CollaboratorRoleBadge'
import CommentSection from '../components/CommentSection'

export default function ShareProject() {
  const { shareToken } = useParams<{ shareToken: string }>()
  const [project, setProject] = useState<StudioProject | null>(null)
  const [scenes, setScenes] = useState<Scene[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadSharedProject() {
      if (!shareToken) return

      try {
        setLoading(true)
        setError(null)
        
        // Fetch the shared project
        const sharedProject = await getSharedProject(shareToken)
        setProject(sharedProject)
        
        // Fetch scenes for this project
        const { scenes: scenesData } = await listScenes(sharedProject.project_id)
        setScenes(scenesData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load shared project')
      } finally {
        setLoading(false)
      }
    }

    void loadSharedProject()
  }, [shareToken])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: 'var(--bg-deep)' }}>
        <div className="flex items-center gap-2 text-zinc-400">
          <Loader2 size={24} className="animate-spin" />
          <span>Loading shared project...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6" style={{ background: 'var(--bg-deep)' }}>
        <div
          className="max-w-xl w-full rounded-2xl p-8 text-center"
          style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)' }}
        >
          <div className="mx-auto mb-4 w-12 h-12 rounded-full flex items-center justify-center" style={{ background: 'rgba(249,115,22,0.12)' }}>
            <AlertTriangle size={22} style={{ color: 'var(--accent-orange)' }} />
          </div>
          <h1 className="text-2xl font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
            Shared Project Not Found
          </h1>
          <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
            {error}
          </p>
          <Link to="/studio" className="btn-primary no-underline">
            Go to Studio Home
          </Link>
        </div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: 'var(--bg-deep)' }}>
        <p className="text-zinc-400">Project not found</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-deep)' }}>
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-white/10" style={{ background: 'var(--bg-panel)' }}>
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/studio" className="flex items-center gap-2 text-zinc-300 hover:text-zinc-100 transition-colors">
              <ArrowLeft size={18} />
              <span className="text-sm">Back to Studio</span>
            </Link>
          </div>
          <div className="flex items-center gap-2">
            <Eye size={16} className="text-zinc-400" />
            <span className="text-sm text-zinc-400">Read-only view</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Project Header */}
        <div className="mb-8">
          <div className="flex items-start gap-4">
            <Film size={28} className="text-zinc-400 flex-shrink-0 mt-1" />
            <div className="flex-1">
              <h1 className="text-3xl font-bold text-zinc-100 mb-1">
                {project.title || 'Untitled Project'}
              </h1>
              <p className="text-sm text-zinc-400">
                Shared via read-only link
              </p>
            </div>
          </div>
        </div>

        {/* Project Stats */}
        {project.source_stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div className="rounded-lg border border-white/10 bg-black/20 p-4">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Scenes</div>
              <div className="text-2xl font-bold text-zinc-100">{project.source_stats.scene_count || 0}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-4">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Shots</div>
              <div className="text-2xl font-bold text-zinc-100">{project.source_stats.shot_count || 0}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-4">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Characters</div>
              <div className="text-2xl font-bold text-zinc-100">{project.source_stats.character_count || 0}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-4">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Runtime</div>
              <div className="text-2xl font-bold text-zinc-100">
                {project.source_stats.target_runtime_minutes || '?'}m
              </div>
            </div>
          </div>
        )}

        {/* Creative Intent */}
        {project.production_bible?.creative_intent && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-zinc-300 mb-3">Creative Intent</h2>
            <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-zinc-300">
              {project.production_bible.creative_intent}
            </div>
          </div>
        )}

        {/* Scene List */}
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-zinc-300 mb-3 flex items-center gap-2">
            <Clapperboard size={18} />
            Scenes
          </h2>
          {scenes.length > 0 ? (
            <div className="space-y-3">
              {scenes.map((scene) => (
                <div
                  key={scene.scene_id}
                  className="rounded-lg border border-white/10 bg-black/20 p-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-medium text-zinc-100">{scene.scene_name}</h3>
                    <span className="text-xs text-zinc-500 uppercase tracking-wider">
                      {scene.time_of_day}
                    </span>
                  </div>
                  <p className="text-sm text-zinc-400 mb-2">{scene.description}</p>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className="text-zinc-500">
                      Tone: {scene.emotional_tone}
                    </span>
                    <span className="text-zinc-500">
                      Location: {scene.location}
                    </span>
                    {scene.characters.length > 0 && (
                      <span className="text-zinc-500">
                        Characters: {scene.characters.join(', ')}
                      </span>
                    )}
                  </div>
                  
                  {/* Sound Advisory */}
                  {scene.sound_advisory && (
                    <div className="mt-3 pt-3 border-t border-white/5">
                      <h4 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Sound Advisory</h4>
                      <div className="text-sm text-zinc-400">
                        <p><strong className="text-zinc-300">Mood:</strong> {scene.sound_advisory.mood}</p>
                        <p><strong className="text-zinc-300">Score:</strong> {scene.sound_advisory.score_notes}</p>
                        <p><strong className="text-zinc-300">Ambient:</strong> {scene.sound_advisory.ambient_notes}</p>
                        {scene.sound_advisory.silence_flag && (
                          <p className="text-amber-400 text-xs mt-1">Silence flagged for intentional use</p>
                        )}
                      </div>
                    </div>
                  )}
                  
                  {/* Transition Advisory */}
                  {scene.transition_advisory && (
                    <div className="mt-3 pt-3 border-t border-white/5">
                      <h4 className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Transition Advisory</h4>
                      <div className="text-sm text-zinc-400">
                        <p><strong className="text-zinc-300">Type:</strong> {scene.transition_advisory.transition_type}</p>
                        <p><strong className="text-zinc-300">Rationale:</strong> {scene.transition_advisory.transition_rationale}</p>
                        <p><strong className="text-zinc-300">Continuity:</strong> {scene.transition_advisory.continuity_notes}</p>
                      </div>
                    </div>
                  )}

                  {/* Comments Section */}
                  {scene.comments && scene.comments.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-white/5">
                      <CommentSection
                        scene={scene}
                        currentUserRole="viewer"
                        currentUserEmail=""
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-zinc-500">No scenes available</p>
          )}
        </div>

        {/* Render Queue Preview */}
        {project.render_queue && project.render_queue.length > 0 && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-zinc-300 mb-3 flex items-center gap-2">
              <Users size={18} />
              Render Queue
            </h2>
            <div className="space-y-3">
              {(project.render_queue as Array<Record<string, unknown>>).map((queueItem, index) => {
                const item = queueItem as Record<string, unknown>
                return (
                  <div
                    key={item.id as string || index}
                    className="rounded-lg border border-white/10 bg-black/20 p-4"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-zinc-100">
                        {item.shot_id as string || item.scene_id as string || 'Unknown'}
                      </span>
                      <span className="text-xs text-zinc-500 uppercase tracking-wider">
                        {item.status as string || 'pending'}
                      </span>
                    </div>
                    <div className="text-sm text-zinc-400">
                      {item.provider && (
                        <ProviderModelLabel
                          provider={item.provider as string}
                          model={item.model as string | undefined}
                          showBadge
                        />
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Collaborators */}
        {project.shared_collaborators && project.shared_collaborators.length > 0 && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-zinc-300 mb-3 flex items-center gap-2">
              <Users size={18} />
              Shared With
            </h2>
            <div className="flex flex-wrap gap-2">
              {project.shared_collaborators.map((collab, index) => (
                <span
                  key={collab.email || index}
                  className="flex items-center gap-2 rounded-md border border-white/15 bg-black/30 px-3 py-1 text-sm text-zinc-300"
                >
                  {collab.email}
                  {collab.role && <CollaboratorRoleBadge role={collab.role} />}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="pt-8 border-t border-white/10 mt-8">
          <p className="text-xs text-zinc-600 text-center">
            This is a read-only view. No edits or render submissions are available.
          </p>
        </div>
      </main>
    </div>
  )
}

// Temporary import for error state
import { AlertTriangle } from 'lucide-react'

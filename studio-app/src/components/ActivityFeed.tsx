import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Clock, Film, MessageSquare, Users, CheckCircle, X } from 'lucide-react'
import { getProjectActivity, type ActivityEntry } from '../lib/studioApi'

type ActivityFeedProps = {
  projectId: string
  className?: string
}

function getActivityIcon(type: string) {
  switch (type) {
    case 'scene_edited':
      return <Film size={14} className="text-amber-400" />
    case 'render_submitted':
      return <Activity size={14} className="text-cyan-400" />
    case 'comment_added':
      return <MessageSquare size={14} className="text-blue-400" />
    case 'collaborator_joined':
      return <Users size={14} className="text-emerald-400" />
    case 'scene_approved':
      return <CheckCircle size={14} className="text-emerald-400" />
    default:
      return <Activity size={14} className="text-zinc-400" />
  }
}

function formatActivityTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffInMinutes = (now.getTime() - date.getTime()) / (1000 * 60)

  if (diffInMinutes < 1) {
    return 'Just now'
  }
  if (diffInMinutes < 60) {
    return `${Math.floor(diffInMinutes)}m ago`
  }
  if (diffInMinutes < 24 * 60) {
    return `${Math.floor(diffInMinutes / 60)}h ago`
  }
  if (diffInMinutes < 7 * 24 * 60) {
    return `${Math.floor(diffInMinutes / (60 * 24))}d ago`
  }
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function getActivitySceneLink(entry: ActivityEntry, projectId: string) {
  if (entry.scene_id) {
    return `/studio/production-board?project_id=${projectId}&scene_id=${entry.scene_id}`
  }
  return null
}

// Mock activity data for when API is not available
const MOCK_ACTIVITY: ActivityEntry[] = [
  {
    id: 'act_1',
    type: 'collaborator_joined',
    action: 'joined the project',
    author: 'Alice Chen',
    timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(), // 5 minutes ago
  },
  {
    id: 'act_2',
    type: 'scene_edited',
    action: 'updated scene description',
    author: 'Bob Wilson',
    timestamp: new Date(Date.now() - 15 * 60 * 1000).toISOString(), // 15 minutes ago
    scene_id: 'scene_1',
    scene_name: 'Opening Scene',
  },
  {
    id: 'act_3',
    type: 'comment_added',
    action: 'left a comment',
    author: 'Carol Martinez',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
    scene_id: 'scene_1',
    scene_name: 'Opening Scene',
  },
  {
    id: 'act_4',
    type: 'render_submitted',
    action: 'submitted render job',
    author: 'David Kim',
    timestamp: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(), // 6 hours ago
    scene_id: 'scene_2',
    scene_name: 'Dialogue Scene',
    metadata: { provider: 'Runway', status: 'completed' },
  },
  {
    id: 'act_5',
    type: 'scene_approved',
    action: 'approved scene',
    author: 'Alice Chen',
    timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // 24 hours ago
    scene_id: 'scene_3',
    scene_name: 'Climax Scene',
  },
]

const ACTIVITY_ACTION_LABELS: Record<string, string> = {
  scene_edited: 'updated',
  render_submitted: 'submitted',
  comment_added: 'commented',
  collaborator_joined: 'joined',
  scene_approved: 'approved',
}

export default function ActivityFeed({ projectId, className = '' }: ActivityFeedProps) {
  const [activities, setActivities] = useState<ActivityEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    async function loadActivities() {
      if (!projectId) {
        setActivities([])
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        // Try to fetch from API, fall back to mock data
        try {
          const data = await getProjectActivity(projectId)
          setActivities(data)
        } catch {
          // Use mock data as fallback
          setActivities(MOCK_ACTIVITY)
        }
      } catch {
        setActivities(MOCK_ACTIVITY)
      } finally {
        setLoading(false)
      }
    }

    void loadActivities()
  }, [projectId])

  const displayActivities = showAll ? activities : activities.slice(0, 5)

  if (loading) {
    return (
      <div className={`border border-white/10 rounded-lg bg-zinc-900/50 p-4 ${className}`}>
        <p className="text-sm text-zinc-500">Loading activity...</p>
      </div>
    )
  }

  if (activities.length === 0) {
    return (
      <div className={`border border-white/10 rounded-lg bg-zinc-900/50 p-4 ${className}`}>
        <p className="text-sm text-zinc-500">No activity yet</p>
      </div>
    )
  }

  return (
    <div className={`border border-white/10 rounded-lg bg-zinc-900/50 ${className}`}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10">
        <h3 className="text-sm font-medium text-zinc-200 flex items-center gap-2">
          <Activity size={16} />
          Activity Feed
        </h3>
      </div>

      {/* Activity List */}
      <div className="p-2">
        {displayActivities.map((activity, index) => (
          <ActivityItem
            key={activity.id || index}
            activity={activity}
            projectId={projectId}
            isLast={index === displayActivities.length - 1}
          />
        ))}

        {/* Show All Button */}
        {activities.length > 5 && !showAll && (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="w-full py-2 text-xs text-zinc-400 hover:text-zinc-200 transition-colors flex items-center justify-center gap-1"
          >
            <Clock size={12} />
            Show all {activities.length} activities
          </button>
        )}

        {showAll && activities.length > 5 && (
          <button
            type="button"
            onClick={() => setShowAll(false)}
            className="w-full py-2 text-xs text-zinc-400 hover:text-zinc-200 transition-colors flex items-center justify-center gap-1"
          >
            <X size={12} />
            Show less
          </button>
        )}
      </div>
    </div>
  )
}

type ActivityItemProps = {
  activity: ActivityEntry
  projectId: string
  isLast?: boolean
}

function ActivityItem({ activity, projectId, isLast = false }: ActivityItemProps) {
  const actionLabel = ACTIVITY_ACTION_LABELS[activity.type] || 'did'
  const sceneLink = getActivitySceneLink(activity, projectId)

  return (
    <div
      className={`py-2 px-3 rounded hover:bg-zinc-800/50 transition-colors ${!isLast ? 'border-b border-white/5' : ''}`}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className="flex-shrink-0 mt-0.5">{getActivityIcon(activity.type)}</div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-zinc-300">{activity.author}</span>
            <span className="text-[10px] text-zinc-500">{formatActivityTime(activity.timestamp)}</span>
          </div>
          <p className="text-sm text-zinc-400 mt-0.5">
            {actionLabel} {activity.action}
            {activity.scene_name && (
              <> on <span className="text-zinc-300">{activity.scene_name}</span></>
            )}
          </p>
        </div>

        {/* Scene Link */}
        {sceneLink && (
          <Link
            to={sceneLink}
            className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors whitespace-nowrap"
          >
            View
          </Link>
        )}
      </div>
    </div>
  )
}

// Export mock data for testing
// eslint-disable-next-line react-refresh/only-export-components
export { formatActivityTime, getActivityIcon }

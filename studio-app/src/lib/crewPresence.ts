import type { CrewIntelligenceOverview } from './studioApi'

export type CrewPresenceRow = { id: string; name: string; initial: string; activity: string; active: boolean }

/** Present the server's department state without inventing background work. */
export function crewPresenceRows(overview: CrewIntelligenceOverview | undefined, projectId?: string): CrewPresenceRow[] {
  if (!overview || overview.project_id !== projectId) return []
  return [...overview.departments]
    .sort((left, right) => Number(right.state !== 'idle') - Number(left.state !== 'idle'))
    .slice(0, 5)
    .map((department) => ({
      id: department.agent_role,
      name: department.department_name,
      initial: department.department_name.charAt(0).toUpperCase(),
      active: department.state === 'working',
      activity: department.state === 'working'
        ? department.current_activity || 'Work in progress.'
        : department.state === 'needs_creator' ? 'Waiting for your review.'
          : department.state === 'waiting' ? 'Waiting for a department handoff.'
            : department.state === 'idle' ? 'Standing by.' : 'Status not available.',
    }))
}

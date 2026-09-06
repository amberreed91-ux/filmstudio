import { describe, expect, it } from 'vitest'
import { crewPresenceRows } from './crewPresence'
import type { CrewDepartmentStatus, CrewIntelligenceOverview } from './studioApi'

function overview(...departments: Partial<CrewDepartmentStatus>[]): CrewIntelligenceOverview {
  return { project_id: 'film-a', departments: departments as CrewDepartmentStatus[] } as CrewIntelligenceOverview
}

describe('truthful crew presence', () => {
  it('has no invented working crew while data is missing or belongs to another film', () => {
    expect(crewPresenceRows(undefined, 'film-a')).toEqual([])
    expect(crewPresenceRows(overview({ agent_role: 'director', department_name: 'Director', state: 'working' }), 'film-b')).toEqual([])
  })

  it('does not present a past activity as current work when the department is idle', () => {
    expect(crewPresenceRows(overview({ agent_role: 'director', department_name: 'Director', state: 'idle', current_activity: 'Adjusting pacing…' }), 'film-a')[0])
      .toMatchObject({ active: false, activity: 'Standing by.' })
  })

  it('distinguishes actual work from waiting for the creator or a handoff', () => {
    const rows = crewPresenceRows(overview(
      { agent_role: 'director', department_name: 'Director', state: 'working', current_activity: 'Reviewing the saved shot plan.' },
      { agent_role: 'script_analyst', department_name: 'Writer', state: 'needs_creator' },
      { agent_role: 'memory_archivist', department_name: 'Memory', state: 'waiting' },
    ), 'film-a')
    expect(rows.map(({ active }) => active)).toEqual([true, false, false])
    expect(rows.map(({ activity }) => activity)).toEqual(['Reviewing the saved shot plan.', 'Waiting for your review.', 'Waiting for a department handoff.'])
  })
})

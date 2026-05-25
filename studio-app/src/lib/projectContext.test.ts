import { describe, expect, it } from 'vitest'
import {
  projectIdFromLocationState,
  resolveActiveProjectId,
  withProjectQuery,
} from './projectContext'

describe('resolveActiveProjectId', () => {
  it('prefers query param over everything', () => {
    expect(
      resolveActiveProjectId({
        queryProjectId: 'query-proj',
        routeProjectId: 'route-proj',
        persistedProjectId: 'persisted-proj',
        contextProjectId: 'context-proj',
      }),
    ).toBe('query-proj')
  })

  it('prefers route param over location state and persisted', () => {
    expect(
      resolveActiveProjectId({
        queryProjectId: '',
        routeProjectId: 'route-proj',
        locationState: { project_id: 'state-proj' },
        persistedProjectId: 'persisted-proj',
        contextProjectId: 'context-proj',
      }),
    ).toBe('route-proj')
  })

  it('falls back to location state project_id when no query or route', () => {
    expect(
      resolveActiveProjectId({
        queryProjectId: '',
        routeProjectId: '',
        locationState: { project_id: 'state-proj' },
        persistedProjectId: 'persisted-proj',
        contextProjectId: 'context-proj',
      }),
    ).toBe('state-proj')
  })

  it('falls back to persisted id when no query, route, or state', () => {
    expect(
      resolveActiveProjectId({
        queryProjectId: '',
        routeProjectId: '',
        locationState: null,
        persistedProjectId: 'persisted-proj',
        contextProjectId: 'context-proj',
      }),
    ).toBe('persisted-proj')
  })

  it('falls back to context project id last', () => {
    expect(
      resolveActiveProjectId({
        queryProjectId: '',
        routeProjectId: '',
        locationState: null,
        persistedProjectId: '',
        contextProjectId: 'context-proj',
      }),
    ).toBe('context-proj')
  })

  it('does NOT fall back to demo_studio_cinematic_001 — returns empty string when nothing is set', () => {
    const result = resolveActiveProjectId({
      queryProjectId: '',
      routeProjectId: '',
      locationState: null,
      persistedProjectId: '',
      contextProjectId: '',
    })
    expect(result).toBe('')
    expect(result).not.toBe('demo_studio_cinematic_001')
  })

  it('real project route param is used even when persisted is demo id', () => {
    const result = resolveActiveProjectId({
      queryProjectId: '',
      routeProjectId: 'real-user-project-abc123',
      locationState: null,
      persistedProjectId: 'demo_studio_cinematic_001',
      contextProjectId: 'demo_studio_cinematic_001',
    })
    expect(result).toBe('real-user-project-abc123')
    expect(result).not.toBe('demo_studio_cinematic_001')
  })

  it('real project query param is used even when context is demo id', () => {
    const result = resolveActiveProjectId({
      queryProjectId: 'real-user-project-xyz',
      routeProjectId: '',
      locationState: null,
      persistedProjectId: 'demo_studio_cinematic_001',
      contextProjectId: 'demo_studio_cinematic_001',
    })
    expect(result).toBe('real-user-project-xyz')
    expect(result).not.toBe('demo_studio_cinematic_001')
  })

  it('trims whitespace from all inputs', () => {
    expect(
      resolveActiveProjectId({
        queryProjectId: '  proj-1  ',
        routeProjectId: '',
        persistedProjectId: '',
        contextProjectId: '',
      }),
    ).toBe('proj-1')
  })
})

describe('projectIdFromLocationState', () => {
  it('reads project_id from state root', () => {
    expect(projectIdFromLocationState({ project_id: 'state-proj' })).toBe('state-proj')
  })

  it('reads projectId from state root', () => {
    expect(projectIdFromLocationState({ projectId: 'state-proj-2' })).toBe('state-proj-2')
  })

  it('reads project_id from nested project object', () => {
    expect(projectIdFromLocationState({ project: { project_id: 'nested-proj' } })).toBe('nested-proj')
  })

  it('returns empty string for null state', () => {
    expect(projectIdFromLocationState(null)).toBe('')
  })

  it('returns empty string for missing project_id', () => {
    expect(projectIdFromLocationState({ other: 'value' })).toBe('')
  })
})

describe('withProjectQuery', () => {
  it('appends project_id to path', () => {
    expect(withProjectQuery('/studio/previs', 'proj-1')).toBe('/studio/previs?project_id=proj-1')
  })

  it('returns path unchanged when projectId is empty', () => {
    expect(withProjectQuery('/studio/previs', '')).toBe('/studio/previs')
  })

  it('encodes special characters in project id', () => {
    const result = withProjectQuery('/studio/previs', 'proj/with spaces')
    expect(result).toContain('project_id=proj%2Fwith+spaces')
  })
})

import { describe, expect, it } from 'vitest'
import type { StudioProject } from './studioApi'
import { extractCoDirectorInspection } from './coDirectorInspection'

describe('extractCoDirectorInspection', () => {
  it('returns null when project is missing', () => {
    expect(extractCoDirectorInspection(null)).toBeNull()
  })

  it('returns null when co-director payload is missing', () => {
    const project = {
      project_id: 'p-1',
      title: 'No Co-Director',
    } satisfies StudioProject

    expect(extractCoDirectorInspection(project)).toBeNull()
  })

  it('extracts expected fields from interactive module workflow payload', () => {
    const project = {
      project_id: 'p-2',
      interactive_modules: {
        co_director_workflow: {
          mode: 'advisory',
          workflow_active: true,
          critique: { title: 'Dominant critique title' },
          proposal: { category: 'director_rejection_recovery' },
          comparison: 'Aligned comparison note',
          intensity_profile: { level: 'medium' },
        },
      },
    } satisfies StudioProject

    expect(extractCoDirectorInspection(project)).toEqual({
      mode: 'advisory',
      workflowActive: true,
      critique: 'Dominant critique title',
      proposal: 'director_rejection_recovery',
      comparison: 'Aligned comparison note',
      intensity: 'medium',
    })
  })

  it('handles malformed payload safely and keeps workflow inactive', () => {
    const project = {
      project_id: 'p-3',
      interactive_modules: {
        co_director_workflow: {
          mode: 123,
          workflow_active: 'yes',
          critique: 42,
          proposal: null,
          comparison: ['bad'],
          intensity: { random: true },
        },
      },
    } as unknown as StudioProject

    expect(extractCoDirectorInspection(project)).toEqual({
      mode: 'unknown',
      workflowActive: false,
      critique: null,
      proposal: null,
      comparison: null,
      intensity: null,
    })
  })
})

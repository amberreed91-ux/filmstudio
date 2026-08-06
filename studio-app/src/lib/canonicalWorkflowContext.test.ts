import { describe, expect, it } from 'vitest'

import {
  extractCanonicalSceneContext,
  isCanonicalPollingStatus,
  nextCanonicalWorkflowAction,
} from './canonicalWorkflowContext'
import type { CanonicalWorkflowRun } from './canonicalWorkflowApi'

function run(status: CanonicalWorkflowRun['status'], revisionStatus = ''): CanonicalWorkflowRun {
  return {
    run_id: 'run-1',
    project_id: 'project-1',
    script_id: 'script-1',
    scene_id: 'scene-1',
    blueprint_id: 'blueprint-1',
    blueprint_version_id: 'version-1',
    status,
    context_hash: 'hash-1',
    data: {
      identifiers: {},
      creative_context: {},
      continuity_context: {},
      artifacts: revisionStatus ? { revision: { status: revisionStatus } } : {},
      approvals: {},
      failures: [],
    },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('canonical workflow context', () => {
  it('extracts identifiers from only the selected scene and preserves beat order', () => {
    const context = extractCanonicalSceneContext({
      execution_summary: {
        script_id: 'script-1',
        scenes: [
          { scene_id: 'scene-a', sequence_id: 'sequence-a', beats: [{ beat_id: 'a-1' }] },
          { scene_id: 'scene-b', sequence_id: 'sequence-b', beats: [{ beat_id: 'b-1' }, { beat_id: 'b-2' }] },
        ],
      },
    }, 'scene-b')

    expect(context).toEqual({
      scriptId: 'script-1',
      sequenceId: 'sequence-b',
      beatIds: ['b-1', 'b-2'],
    })
  })

  it('does not leak a different scene when the requested scene is absent', () => {
    const context = extractCanonicalSceneContext({
      execution_summary: {
        script_id: 'script-1',
        scenes: [{ scene_id: 'scene-a', sequence_id: 'sequence-a', beats: [{ beat_id: 'a-1' }] }],
      },
    }, 'scene-missing')

    expect(context).toEqual({ scriptId: 'script-1', sequenceId: '', beatIds: [] })
  })

  it('keeps room-specific approvals in Screening while Previs becomes read-only', () => {
    expect(nextCanonicalWorkflowAction('screening_ready', 'previs')).toBe('complete')
    expect(nextCanonicalWorkflowAction('screening_ready', 'screening')).toBe('approve_screening')
    expect(nextCanonicalWorkflowAction('cut_approved', 'screening')).toBe('create_revision')
  })

  it('polls only queued work and submitted revisions', () => {
    expect(isCanonicalPollingStatus(run('render_queued'))).toBe(true)
    expect(isCanonicalPollingStatus(run('revision_pending', 'draft'))).toBe(false)
    expect(isCanonicalPollingStatus(run('revision_pending', 'submitted'))).toBe(true)
    expect(isCanonicalPollingStatus(run('render_completed'))).toBe(false)
  })
})

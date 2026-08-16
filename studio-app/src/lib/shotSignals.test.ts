import { describe, expect, it } from 'vitest'
import {
  buildShotSignalViews,
  shotSignalsAreQuiet,
  type ShotSignalsEnvelope,
} from './shotSignals'

function envelope(overrides: Partial<ShotSignalsEnvelope> = {}): ShotSignalsEnvelope {
  return {
    job_id: 'job-1',
    shot_id: 'scene_001_shot_002',
    project_id: 'proj-1',
    status: 'settled',
    signals: [],
    quiet_signals: [],
    ...overrides,
  }
}

describe('shotSignalsAreQuiet', () => {
  it('treats a missing envelope as quiet', () => {
    expect(shotSignalsAreQuiet(null)).toBe(true)
  })

  it('treats an envelope with no signals as quiet', () => {
    expect(shotSignalsAreQuiet(envelope())).toBe(true)
  })

  it('is not quiet once there is something to say', () => {
    expect(
      shotSignalsAreQuiet(
        envelope({
          signals: [{ kind: 'exclusions', status: 'settled', note: 'x', terms: ['watermark'] }],
        }),
      ),
    ).toBe(false)
  })
})

describe('buildShotSignalViews', () => {
  it('returns nothing for a null envelope', () => {
    expect(buildShotSignalViews(null)).toEqual([])
  })

  it('puts signals needing attention before background context', () => {
    const views = buildShotSignalViews(
      envelope({
        status: 'attention',
        signals: [
          { kind: 'exclusions', status: 'settled', note: 'sent', terms: ['watermark'] },
          {
            kind: 'character_identity',
            status: 'attention',
            note: 'MAYA may not read as the same character here.',
            characters: [{ character_name: 'MAYA', reading: 'drifted', drifted: true }],
          },
        ],
      }),
    )

    expect(views[0].kind).toBe('character_identity')
    expect(views[0].needsAttention).toBe(true)
    expect(views[1].kind).toBe('exclusions')
  })

  it('surfaces dropped phrases as details so they are recognisable', () => {
    const views = buildShotSignalViews(
      envelope({
        signals: [
          {
            kind: 'intent_fidelity',
            status: 'attention',
            note: 'The prompt no longer carries "never stops moving".',
            dropped_phrases: ['never stops moving', 'boots caked in dry mud'],
          },
        ],
      }),
    )

    expect(views[0].details).toContain('never stops moving')
    expect(views[0].details).toContain('boots caked in dry mud')
  })

  it('names each character alongside its reading', () => {
    const views = buildShotSignalViews(
      envelope({
        signals: [
          {
            kind: 'character_identity',
            status: 'settled',
            note: 'Reads as the same person.',
            characters: [
              { character_name: 'MAYA', reading: 'Reads as the same person.', drifted: false },
            ],
          },
        ],
      }),
    )

    expect(views[0].details[0]).toContain('MAYA')
  })

  it('describes reference roles in plain language', () => {
    const views = buildShotSignalViews(
      envelope({
        signals: [
          {
            kind: 'character_references',
            status: 'settled',
            note: '2 locked references conditioned this render.',
            references: [
              { ref_id: 'charlock:c1:general', role: 'general', image_url: '/a.jpg' },
              { ref_id: 'charlock:c1:alternate_angle', role: 'alternate_angle', image_url: '/b.jpg' },
            ],
          },
        ],
      }),
    )

    expect(views[0].details).toEqual(['primary reference', 'alternate angle'])
  })

  it('never renders a score or percentage', () => {
    // AGENTS.md: no scores, ratings, or percentages in director-facing output.
    const views = buildShotSignalViews(
      envelope({
        signals: [
          {
            kind: 'character_identity',
            status: 'attention',
            note: 'MAYA may not read as the same character here.',
            characters: [{ character_name: 'MAYA', reading: 'may not read as the same', drifted: true }],
          },
        ],
      }),
    )

    const rendered = JSON.stringify(views)
    expect(rendered).not.toContain('%')
    expect(rendered.toLowerCase()).not.toContain('score')
  })

  it('falls back to the raw kind when a title is unknown', () => {
    const views = buildShotSignalViews(
      envelope({
        // @ts-expect-error deliberately unknown kind from a newer backend
        signals: [{ kind: 'future_signal', status: 'settled', note: 'n' }],
      }),
    )
    expect(views[0].title).toBe('future_signal')
  })
})

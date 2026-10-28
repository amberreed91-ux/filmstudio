import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ShotRationaleMotifCard from './ShotRationaleMotifCard'
import type { DeskQueueItem } from '../../lib/deskShotInspector'

function item(over: Partial<DeskQueueItem> = {}): DeskQueueItem {
  return {
    shotId: 'scene_001_shot_001',
    sceneId: 'scene_001',
    sceneName: 'Held breath',
    shotNumber: 1,
    intent: 'Carries the brass key into the light.',
    motifs: ['brass key', 'rain'],
    hasMedia: true,
    ...over,
  }
}

describe('ShotRationaleMotifCard', () => {
  it('reports the primary purpose and every motif the shot carries', () => {
    const html = renderToStaticMarkup(<ShotRationaleMotifCard item={item()} />)
    expect(html).toContain('Shot Rationale &amp; Motif')
    expect(html).toContain('Carries the brass key into the light.')
    expect(html).toContain('Held breath · shot 1')
    expect(html).toContain('brass key')
    expect(html.match(/data-testid="shot-motif-chip"/g)).toHaveLength(2)
  })

  it('says plainly when no rationale or motif has been carried yet', () => {
    const html = renderToStaticMarkup(<ShotRationaleMotifCard item={item({ intent: '', motifs: [] })} />)
    expect(html).toContain('data-testid="shot-rationale-empty"')
    expect(html).toContain('No shot rationale has been carried from the board yet.')
    expect(html).toContain('No motif is tagged to this shot.')
    expect(html).not.toContain('data-testid="shot-motif-chip"')
  })

  it('keeps the copy free of scores, ratings, and percentages', () => {
    const copy = renderToStaticMarkup(<ShotRationaleMotifCard item={item()} />).replace(/<[^>]+>/g, ' ')
    expect(copy).not.toMatch(/\d+\s*%|\bscore\b|\brating\b|\b\d+(\.\d+)?\/10\b/i)
  })
})

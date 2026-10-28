import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ShotIntentBadge from './ShotIntentBadge'

describe('ShotIntentBadge', () => {
  it('names the shot intent carried by the card', () => {
    const html = renderToStaticMarkup(<ShotIntentBadge intent="Holds on the empty chair." testId="board-shot-intent-scene_001" />)
    expect(html).toContain('Intent · Holds on the empty chair.')
    expect(html).toContain('data-testid="board-shot-intent-scene_001"')
  })

  it('renders nothing for a card with no intent', () => {
    expect(renderToStaticMarkup(<ShotIntentBadge intent="" />)).toBe('')
    expect(renderToStaticMarkup(<ShotIntentBadge intent="   " />)).toBe('')
  })

  it('keeps the full rationale available on hover without a grade', () => {
    const html = renderToStaticMarkup(<ShotIntentBadge intent="Withholds the reveal until the door closes." />)
    expect(html).toContain('title="Withholds the reveal until the door closes."')
    expect(html).not.toMatch(/\d+\s*%|\bscore\b|\brating\b/i)
  })
})

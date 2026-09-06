import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(resolve(__dirname, 'ScreeningRoom.tsx'), 'utf8')

describe('Screening Room external emotion analysis wiring', () => {
  it('keeps the only Qwen call inside the explicit active-scene handler', () => {
    expect(source.match(/analyzeSceneEmotion\(/g)).toHaveLength(1)

    const handlerStart = source.indexOf('const handleAnalyzeActiveScene')
    const handlerEnd = source.indexOf('// ── Request co-director notes', handlerStart)
    const handler = source.slice(handlerStart, handlerEnd)

    expect(handler).toContain('analyzeSceneEmotion(effectiveProjectId, sceneId)')
    expect(handler).toContain('if (!effectiveProjectId || !sceneId || emotionAnalysisLoading) return')
  })

  it('uses cache-only reads on scene changes and keeps local simulation provider-free', () => {
    const cacheEffectStart = source.indexOf('// Load a previously cached result')
    const cacheEffectEnd = source.indexOf('// ── Video event handlers', cacheEffectStart)
    expect(source.slice(cacheEffectStart, cacheEffectEnd)).toContain('getCachedSceneEmotion(')
    expect(source.slice(cacheEffectStart, cacheEffectEnd)).not.toContain('analyzeSceneEmotion(')

    const simulateStart = source.indexOf('const handleSimulate')
    const simulateEnd = source.indexOf('const handleAnalyzeActiveScene', simulateStart)
    expect(source.slice(simulateStart, simulateEnd)).not.toContain('analyzeSceneEmotion(')
  })

  it('discloses the external provider action in the button label', () => {
    expect(source).toContain('ANALYZE ACTIVE SCENE · QWEN')
    expect(source).toContain('External AI call. Results are cached')
  })
})

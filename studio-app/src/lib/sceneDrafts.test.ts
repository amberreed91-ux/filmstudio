import { describe, expect, it, vi } from 'vitest'
import { createSceneDraftBuffer } from './sceneDrafts'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((done) => { resolve = done })
  return { promise, resolve }
}

describe('scene editor draft preservation', () => {
  it('serializes saves and retains edits made while an earlier version is saving', async () => {
    const first = deferred()
    const persist = vi.fn().mockImplementationOnce(() => first.promise).mockResolvedValue(undefined)
    const buffer = createSceneDraftBuffer(persist)
    buffer.write('film', 'scene', 'first')
    const saving = buffer.save('film', 'scene', 'first')
    buffer.write('film', 'scene', 'newer')
    const next = buffer.save('film', 'scene', 'newer')
    await Promise.resolve()
    expect(persist).toHaveBeenCalledTimes(1)
    expect(buffer.read('film', 'scene')).toBe('newer')
    first.resolve()
    await saving
    await next
    expect(persist.mock.calls.map((call) => call[2])).toEqual(['first', 'newer'])
    expect(buffer.read('film', 'scene')).toBeUndefined()
  })

  it('keeps a failed save recoverable on returning to the editor and allows retry', async () => {
    const persist = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
    const buffer = createSceneDraftBuffer(persist)
    buffer.write('film', 'scene', 'unsaved')
    await expect(buffer.save('film', 'scene', 'unsaved')).rejects.toThrow('offline')
    expect(buffer.read('film', 'scene')).toBe('unsaved')
    await buffer.save('film', 'scene', 'unsaved')
    expect(buffer.read('film', 'scene')).toBeUndefined()
  })

  it('isolates identical scene IDs in different films and deduplicates a pending flush', async () => {
    const first = deferred()
    const persist = vi.fn(() => first.promise)
    const buffer = createSceneDraftBuffer(persist)
    buffer.write('film-a', 'scene_001', 'A')
    buffer.write('film-b', 'scene_001', 'B')
    const saving = buffer.save('film-a', 'scene_001', 'A')
    expect(buffer.save('film-a', 'scene_001', 'A')).toBe(saving)
    first.resolve()
    await saving
    expect(buffer.read('film-b', 'scene_001')).toBe('B')
    expect(persist).toHaveBeenCalledTimes(1)
  })
})

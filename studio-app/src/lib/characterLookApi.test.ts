import { afterEach, describe, expect, it, vi } from 'vitest'
import { approveCharacterLook, generateCharacterCasting, characterLookError, listCharacterLooks, reviseCharacterLook, uploadCharacterLookReference } from './characterLookApi'

afterEach(() => vi.unstubAllGlobals())

describe('character look API contract', () => {
  it('reads the server approvals for the explicit film', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ looks: [] })))
    vi.stubGlobal('fetch', request)
    await expect(listCharacterLooks('film / one')).resolves.toEqual({ looks: [] })
    expect(request.mock.calls[0][0]).toContain('/projects/film%20%2F%20one/character-looks')
    expect(request.mock.calls[0][1].method).toBeUndefined()
  })

  it('locks the exact profile revision and selected references only on an explicit approval call', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'locked', version: 1 })))
    vi.stubGlobal('fetch', request)
    const payload = { expected_profile_revision: 'revision-2', face_image_url: '/outputs/portrait.png', body_image_url: null }
    await approveCharacterLook('film', 'character / one', payload)
    expect(request.mock.calls[0][0]).toContain('/characters/character%20%2F%20one/look/approve')
    expect(request.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual(payload)
  })

  it('uploads a candidate as multipart without implying approval', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ image_url: '/outputs/candidate.png' })))
    vi.stubGlobal('fetch', request)
    const file = new File(['fixture'], 'portrait.png', { type: 'image/png' })
    await uploadCharacterLookReference('film', 'character', file)
    expect(request).toHaveBeenCalledTimes(1)
    expect(request.mock.calls[0][0]).toContain('/look/reference')
    expect(request.mock.calls[0][1].body.get('file')).toBe(file)
    expect(request.mock.calls[0][1].headers['Content-Type']).toBeUndefined()
  })

  it('requires the current saved revision when reopening a look', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'draft', version: 1 })))
    vi.stubGlobal('fetch', request)
    await reviseCharacterLook('film', 'character', 'current-revision')
    expect(request.mock.calls[0][0]).toContain('/look/revise')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ expected_profile_revision: 'current-revision' })
  })

  it('shows the backend reason when a stale approval is refused', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { error_type: 'state_error', message: 'This profile changed. Reload the saved look before approval.', stage: 'character_look_approve', metadata: {} } }), { status: 409 })))
    try {
      await approveCharacterLook('film', 'character', { expected_profile_revision: 'old', face_image_url: '/outputs/portrait.png' })
      throw new Error('Expected approval to fail')
    } catch (error) {
      expect(characterLookError(error)).toBe('This profile changed. Reload the saved look before approval.')
    }
  })
})


describe('casting generation requests', () => {
  it('submits one idempotent set using the saved revision without selecting or approving a face', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'draft', casting_generations: [{ status: 'queued' }] })))
    vi.stubGlobal('fetch', request)
    const payload = { request_id: '3b3a930e-424f-4bdf-a55d-b32de85a5522', expected_profile_revision: 'saved-revision', direction: 'Natural daylight' }
    await generateCharacterCasting('film / one', 'chr / one', payload)
    expect(request).toHaveBeenCalledTimes(1)
    expect(request.mock.calls[0][0]).toContain('/projects/film%20%2F%20one/characters/chr%20%2F%20one/look/casting')
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual(payload)
  })
})

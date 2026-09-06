import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { buildCoDirectorChatPayload, type CoDirectorContext, type CoDirectorSceneSummary, type CoDirectorSpecialist } from '../lib/coDirectorDrawerContext'
import { fetchJson } from '../lib/studioApi'

type Message = { role: 'user' | 'agent'; text: string; specialist: CoDirectorSpecialist; timestamp: number }
type MemoryBundle = Partial<Record<'symbols' | 'motifs' | 'characters' | 'themes' | 'notes' | 'debates', unknown[]>>
type ChatResponse = { reply: string; memory_entries_used?: number }
type Conversation = { scope: string; messages: Message[]; loading: boolean; supplied: number | null }

export function useCoDirectorConversation(args: {
  projectId?: string; activeSceneId?: string; specialist: CoDirectorSpecialist;
  context: CoDirectorContext; systemPrompt: string; enabled: boolean;
}) {
  const { projectId, activeSceneId, specialist, context, systemPrompt, enabled } = args
  const base = `/api/f51/studio/projects/${encodeURIComponent(projectId || '')}`
  const memory = useQuery({
    queryKey: ['director-memory', projectId], enabled: Boolean(projectId) && enabled,
    queryFn: ({ signal }) => fetchJson<{ memory: MemoryBundle }>(`${base}/director-memory`, { signal }),
    staleTime: 60_000, retry: 1,
  })
  const scenes = useQuery({
    queryKey: ['project-scenes-light', projectId], enabled: Boolean(projectId) && enabled,
    queryFn: ({ signal }) => fetchJson<{ scenes: CoDirectorSceneSummary[] }>(`${base}/scenes`, { signal }),
    staleTime: 60_000, retry: 0,
  })
  const scope = JSON.stringify([projectId, activeSceneId, specialist, context])
  const [conversation, setConversation] = useState<Conversation>({ scope, messages: [], loading: false, supplied: null })
  const lifecycle = useRef({ scope, live: true, request: null as AbortController | null })

  useEffect(() => {
    const current = { scope, live: true, request: null as AbortController | null }
    lifecycle.current = current
    setConversation({ scope, messages: [], loading: false, supplied: null })
    return () => { current.live = false; current.request?.abort() }
  }, [scope])

  const send = useCallback(async (message: string): Promise<void> => {
    const text = message.trim()
    const current = lifecycle.current
    if (!text || !projectId || !enabled || !current.live || current.scope !== scope || current.request) return
    const controller = new AbortController()
    current.request = controller
    setConversation((previous) => ({ scope, loading: true, supplied: previous.scope === scope ? previous.supplied : null, messages: [
      ...(previous.scope === scope ? previous.messages : []),
      { role: 'user', text, specialist, timestamp: Date.now() },
    ] }))
    try {
      const payload = buildCoDirectorChatPayload({ specialist, message: text, context, projectId, systemPrompt, scenes: scenes.data?.scenes, activeSceneId })
      const result = await fetchJson<ChatResponse>(`${base}/co-director/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: controller.signal,
      })
      if (!result.reply?.trim()) throw new Error('The Co-Director returned an empty response.')
      if (!current.live || lifecycle.current !== current) return
      setConversation((previous) => ({ ...previous, loading: false, supplied: typeof result.memory_entries_used === 'number' ? result.memory_entries_used : null,
        messages: [...previous.messages, { role: 'agent', text: result.reply, specialist, timestamp: Date.now() }],
      }))
    } catch (error) {
      if (!current.live || lifecycle.current !== current || controller.signal.aborted) return
      console.error('Co-director request failed', { projectId, sceneId: activeSceneId, specialist, error: error instanceof Error ? error.message : 'Request failed' })
      setConversation((previous) => ({ ...previous, loading: false, messages: [...previous.messages, {
        role: 'agent', text: 'The Co-Director could not respond just now. Please retry when the service is available.', specialist, timestamp: Date.now(),
      }] }))
    } finally {
      if (current.request === controller) current.request = null
    }
  }, [activeSceneId, base, context, enabled, projectId, scenes.data?.scenes, scope, specialist, systemPrompt])

  const visible = conversation.scope === scope ? conversation : { messages: [], loading: false, supplied: null }
  const memoryEntries = Object.values(memory.data?.memory || {}).reduce((count, items) => count + (Array.isArray(items) ? items.length : 0), 0)
  return { messages: visible.messages, loading: visible.loading, lastMemoryEntriesSupplied: visible.supplied, memoryEntries, scenes: scenes.data?.scenes, send }
}

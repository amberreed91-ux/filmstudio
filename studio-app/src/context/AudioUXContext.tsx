import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

export type AudioUXEvent = 'render_started' | 'render_completed' | 'render_failed' | 'room_transition'

type AudioUXValue = {
  muted: boolean
  toggleMuted: () => void
  emitAudioEvent: (event: AudioUXEvent, payload?: Record<string, unknown>) => void
}

const AudioUXContext = createContext<AudioUXValue>({
  muted: true,
  toggleMuted: () => undefined,
  emitAudioEvent: () => undefined,
})

export function AudioUXProvider({ children }: { children: ReactNode }) {
  const [muted, setMuted] = useState(true)

  const value = useMemo<AudioUXValue>(() => ({
    muted,
    toggleMuted: () => setMuted((prev) => !prev),
    emitAudioEvent: (event, payload) => {
      if (muted) return
      if (import.meta.env.DEV) {
        console.info('[AudioUX]', event, payload || {})
      }
    },
  }), [muted])

  return <AudioUXContext.Provider value={value}>{children}</AudioUXContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAudioUX() {
  return useContext(AudioUXContext)
}

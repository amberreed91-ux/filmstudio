import { create } from 'zustand'

type TransitionState = 'idle' | 'cutting' | 'entering'

interface TransitionStore {
  state: TransitionState
  fromRoom: string | null
  toRoom: string | null
  cut: (to: string) => void
  complete: () => void
}

export const useTransition = create<TransitionStore>((set) => ({
  state: 'idle',
  fromRoom: null,
  toRoom: null,
  cut: (to) => set((s) => ({
    state: 'cutting',
    fromRoom: s.toRoom,
    toRoom: to,
  })),
  complete: () => set({ state: 'idle' }),
}))
import { create } from 'zustand'

export type RenderStatus = 'idle' | 'running' | 'complete' | 'failed'

export interface RenderStatusState {
  status: RenderStatus
  jobId: string | null
  setStatus: (status: RenderStatus, jobId?: string | null) => void
}

export const useRenderStatusStore = create<RenderStatusState>((set) => ({
  status: 'idle',
  jobId: null,
  setStatus: (status, jobId = null) => set({ status, jobId }),
}))
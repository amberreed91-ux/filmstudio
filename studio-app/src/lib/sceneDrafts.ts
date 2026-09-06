/** Unsaved editor buffers live only in this tab; the backend remains the saved source. */
export function createSceneDraftBuffer(
  persist: (projectId: string, sceneId: string, text: string) => Promise<void>,
) {
  const drafts = new Map<string, string>()
  const requests = new Map<string, { text: string; promise: Promise<void> }>()
  const keyFor = (projectId: string, sceneId: string) => JSON.stringify([projectId, sceneId])
  return {
    read(projectId: string, sceneId: string) {
      return drafts.get(keyFor(projectId, sceneId))
    },
    write(projectId: string, sceneId: string, text: string) {
      drafts.set(keyFor(projectId, sceneId), text)
    },
    save(projectId: string, sceneId: string, text: string): Promise<void> {
      const key = keyFor(projectId, sceneId)
      const prior = requests.get(key)
      if (prior?.text === text) return prior.promise
      // Serialize writes for one scene so a slower old save cannot replace a newer edit.
      const promise = (prior?.promise.catch(() => {}) ?? Promise.resolve())
        .then(() => persist(projectId, sceneId, text))
        .then(() => {
          if (drafts.get(key) === text) drafts.delete(key)
        })
        .finally(() => {
          if (requests.get(key)?.promise === promise) requests.delete(key)
        })
      requests.set(key, { text, promise })
      return promise
    },
  }
}

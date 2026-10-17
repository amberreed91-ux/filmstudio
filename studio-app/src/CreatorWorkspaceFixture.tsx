import { useCallback, useEffect, useState } from 'react'
import { CreatorDecisionWorkspace } from './components/CreatorDecisionWorkspace'
import { getSceneDirection } from './lib/sceneDirectionApi'
import {
  SCENE002_FIXTURE_PROJECT_ID,
  SCENE002_FIXTURE_SCENE_ID,
  SCENE002_FIXTURE_VERSION_ID,
} from './components/__fixtures__/sceneDirectionFixture'

export default function CreatorWorkspaceFixture() {
  const [versionId, setVersionId] = useState(SCENE002_FIXTURE_VERSION_ID)

  const refreshVersion = useCallback(() => {
    void getSceneDirection(SCENE002_FIXTURE_PROJECT_ID, SCENE002_FIXTURE_SCENE_ID)
      .then(direction => setVersionId(direction.version_id))
      .catch(() => undefined)
  }, [])

  useEffect(() => { refreshVersion() }, [refreshVersion])

  return (
    <main className="mx-auto min-h-screen w-full max-w-6xl space-y-5 px-4 py-6 text-zinc-100 sm:px-8">
      <header className="space-y-2 rounded-lg border border-amber-300/60 bg-amber-950/50 p-4">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-amber-200">Synthetic fixture only · not authenticated project access</p>
        <h1 className="text-xl font-semibold">Creator Decision Workspace verification</h1>
        <p className="text-sm leading-relaxed text-amber-50/90">
          This isolated preview uses invented source/dialogue text and process-local memory. It does not read or save the real Scene 002 project, authenticate a user, or contact the normal Studio backend. Refreshing or stopping the fixture discards its decisions.
        </p>
        <dl className="grid gap-2 text-xs sm:grid-cols-4">
          <div><dt className="text-amber-200">Fixture project / scene</dt><dd><code>{SCENE002_FIXTURE_PROJECT_ID} / {SCENE002_FIXTURE_SCENE_ID}</code></dd></div>
          <div><dt className="text-amber-200">Approved source version</dt><dd><code>{SCENE002_FIXTURE_VERSION_ID}</code></dd></div>
          <div><dt className="text-amber-200">Current version</dt><dd><code>{versionId}</code></dd></div>
          <div><dt className="text-amber-200">Successor version</dt><dd><code>{versionId === SCENE002_FIXTURE_VERSION_ID ? 'Not created yet' : versionId}</code></dd></div>
        </dl>
        <p className="text-xs text-amber-100/80">To exercise the disposable Setting Authority lifecycle, register only a <code>fixture://name</code> identifier. Uploads and external media URLs are disabled.</p>
      </header>

      <CreatorDecisionWorkspace
        projectId={SCENE002_FIXTURE_PROJECT_ID}
        sceneId={SCENE002_FIXTURE_SCENE_ID}
        versionId={versionId}
        activeShotNumber={1}
        onSaved={refreshVersion}
      />
    </main>
  )
}

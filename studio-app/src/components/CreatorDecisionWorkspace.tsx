import { SceneDirectionPanel } from './SceneDirectionPanel'
import { SettingReferenceAuthorityPanel } from './SettingReferenceAuthorityPanel'
import { useSceneDirection } from '../hooks/useSceneDirection'

type Props = {
  projectId: string
  sceneId?: string | null
  versionId?: string | null
  activeShotNumber: number
  onSaved: () => void
}

/**
 * Setting authority scoped to the open scene's canonical setting entity.
 * Reads the same sync-free scene-direction endpoint the Scene Direction panel
 * reads, so the entity named here always matches the entity the selector
 * below will filter on. While the entity is still resolving, a status line
 * holds the space instead of a panel that could point at the wrong entity.
 * When the scene has no canonical entity (or the read fails), this falls back
 * to the default authority scope — the Scene Direction panel names the block.
 */
function ScopedSettingAuthority({ projectId, sceneId, versionId }: { projectId: string; sceneId: string; versionId: string }) {
  const { data, error } = useSceneDirection(projectId, sceneId, versionId)
  if (!data && !error) {
    return <p role="status" className="mt-5 text-xs text-zinc-500">Resolving the scene&apos;s setting entity…</p>
  }
  return <SettingReferenceAuthorityPanel projectId={projectId} settingId={data?.canonical_setting_id || undefined} />
}

export function CreatorDecisionWorkspace({ projectId, sceneId, versionId, activeShotNumber, onSaved }: Props) {
  return (
    <div className="space-y-2">
      {sceneId && versionId ? (
        <ScopedSettingAuthority projectId={projectId} sceneId={sceneId} versionId={versionId} />
      ) : (
        <SettingReferenceAuthorityPanel projectId={projectId} />
      )}
      {sceneId && versionId ? (
        <SceneDirectionPanel
          projectId={projectId}
          sceneId={sceneId}
          versionId={versionId}
          activeShotNumber={activeShotNumber}
          onSaved={onSaved}
        />
      ) : (
        <p className="text-xs text-zinc-500">Open a scene to capture Scene Direction and coverage decisions.</p>
      )}
    </div>
  )
}

export default CreatorDecisionWorkspace

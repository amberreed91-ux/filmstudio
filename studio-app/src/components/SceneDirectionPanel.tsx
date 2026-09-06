import { useSceneDirection } from '../hooks/useSceneDirection'

const inputClass = 'mt-1 w-full min-w-0 rounded-md border border-white/15 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 disabled:opacity-50'
const buttonClass = 'min-h-10 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-200 disabled:opacity-40'

type Props = { projectId: string; sceneId: string; versionId: string; activeShotNumber: number; onSaved: () => void }

export function SceneDirectionPanel({ projectId, sceneId, versionId, activeShotNumber, onSaved }: Props) {
  const editor = useSceneDirection(projectId, sceneId, versionId)
  const data = editor.data
  const currentIndex = data?.shots.findIndex(shot => shot.shot_number === activeShotNumber) ?? -1
  const shot = data?.shots[currentIndex]
  const previous = currentIndex > 0 ? data?.shots[currentIndex - 1] : null
  const unassigned = data?.dialogue.filter(line => !line.shot_id).length ?? 0
  return <details className="rounded-lg border border-white/15 p-3">
    <summary className="cursor-pointer text-sm font-medium text-zinc-200">Dialogue &amp; shot handoffs</summary>
    <div className="mt-4 space-y-5">
      <p className="text-xs leading-relaxed text-zinc-400">Place dialogue and describe what changes on screen. Save creates a new storyboard draft for review; existing takes stay as they are.</p>
      {editor.error && <p role="alert" className="text-sm text-red-300">{editor.error}</p>}
      {!data && editor.busy && <p role="status" className="text-sm text-zinc-400">Loading scene direction…</p>}
      {data && <form className="space-y-5" onSubmit={async event => { event.preventDefault(); if (await editor.save()) onSaved() }}>
        <fieldset disabled={editor.busy} className="min-w-0 space-y-4">
          <legend className="text-sm font-medium text-zinc-100">Dialogue for this scene</legend>
          <p role="status" className="text-xs text-amber-200">{unassigned ? `${unassigned} dialogue ${unassigned === 1 ? 'line is' : 'lines are'} unassigned.` : data.dialogue.length ? 'Every dialogue line has a shot.' : 'No dialogue lines saved for this scene.'}</p>
          {!data.saved && data.dialogue.length > 0 && <p className="text-xs text-zinc-400">These lines came from the project. Check the words and speaker before saving.</p>}
          {data.dialogue.map((line, index) => <fieldset key={line.line_id} disabled={data.shots.some(item => item.shot_id === line.shot_id && item.locked)} className="min-w-0 space-y-2 rounded-md border border-white/10 p-3">
            <legend className="px-1 text-xs text-zinc-400">Line {index + 1}{!line.shot_id ? ' · Unassigned' : ''}</legend>
            <label className="block text-xs text-zinc-300">Speaker {index + 1}<input aria-label={`Speaker ${index + 1}`} required maxLength={150} className={inputClass} value={line.character} onChange={event => editor.editLine(line.line_id, { character: event.target.value, character_id: '', voice_style_hint: '' })} /></label>
            <label className="block text-xs text-zinc-300">Dialogue {index + 1}<textarea aria-label={`Dialogue ${index + 1}`} required maxLength={4000} rows={2} className={inputClass} value={line.text} onChange={event => editor.editLine(line.line_id, { text: event.target.value })} /></label>
            <label className="block text-xs text-zinc-300">Shot for line {index + 1}<select aria-label={`Shot for line ${index + 1}`} className={inputClass} value={line.shot_id || ''} onChange={event => editor.editLine(line.line_id, { shot_id: event.target.value || null })}><option value="">Unassigned</option>{data.shots.map(item => <option key={item.shot_id} value={item.shot_id} disabled={item.locked}>Shot {item.shot_number}{item.locked ? ' · locked' : ''}</option>)}</select></label>
            <button type="button" className={buttonClass} onClick={() => editor.removeLine(line.line_id)}>Remove line {index + 1}</button>
          </fieldset>)}
          <button type="button" className={buttonClass} onClick={editor.addLine}>Add dialogue line</button>
        </fieldset>
        {shot && <fieldset disabled={editor.busy || shot.locked} className="min-w-0 space-y-3 border-t border-white/10 pt-3">
          <legend className="text-sm font-medium text-zinc-100">Shot {shot.shot_number} handoff{shot.locked ? ' · locked' : ''}</legend>
          {shot.frame_url && <figure><img src={shot.frame_url} alt={`Storyboard reference for shot ${shot.shot_number}`} className="max-h-40 w-full rounded-md object-contain" /><figcaption className="mt-1 text-xs text-zinc-400">Reference frame · {data.version_status === 'approved' ? 'approved storyboard' : 'review with this draft'}</figcaption></figure>}
          {shot.frame_changed && <p className="text-xs text-amber-200">The reference frame changed since this handoff was saved. Check that the opening state still fits.</p>}
          {previous && <p className="rounded-md bg-white/5 p-3 text-xs leading-relaxed text-zinc-300">Previous shot ends: {previous.ending_state || 'No ending state recorded yet.'}</p>}
          <label className="block text-xs text-zinc-300">Opening state<textarea aria-label="Opening state" maxLength={1500} rows={2} placeholder="Maya holds the key in her right hand; Jules stands by the doorway." className={inputClass} value={shot.opening_state} onChange={event => editor.editHandoff(shot.shot_id, { opening_state: event.target.value })} /></label>
          <label className="block text-xs text-zinc-300">Action and change<textarea aria-label="Action and change" maxLength={1500} rows={2} placeholder="Maya places the key in Jules’s left palm." className={inputClass} value={shot.action_change} onChange={event => editor.editHandoff(shot.shot_id, { action_change: event.target.value })} /></label>
          <label className="block text-xs text-zinc-300">Ending state<textarea aria-label="Ending state" maxLength={1500} rows={2} placeholder="Jules holds the key; Maya’s hands are empty." className={inputClass} value={shot.ending_state} onChange={event => editor.editHandoff(shot.shot_id, { ending_state: event.target.value })} /></label>
        </fieldset>}
        <p className="text-xs leading-relaxed text-zinc-400">Unassigned lines stay out of shot audio. These intentions guide future takes; check the rendered action against the frame and handoff.</p>
        <div className="flex flex-wrap gap-2"><button type="submit" disabled={editor.busy || !editor.dirty} className="min-h-11 rounded-md bg-amber-200 px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40">{editor.busy ? 'Saving…' : 'Save scene direction'}</button><button type="button" disabled={editor.busy} onClick={editor.reload} className={buttonClass}>{editor.dirty ? 'Discard edits and reload' : 'Reload saved direction'}</button></div>
      </form>}
      {!data && !editor.busy && <button type="button" className={buttonClass} onClick={editor.reload}>Retry loading direction</button>}
    </div>
  </details>
}

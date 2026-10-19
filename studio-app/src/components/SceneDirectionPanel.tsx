import { useState } from 'react'
import { useSceneDirection } from '../hooks/useSceneDirection'
import type { CoverageDecision, SceneDirection } from '../lib/sceneDirectionApi'
import { LEGACY_SCENE002_REFERENCE_ID } from '../lib/settingReferenceApi'

const inputClass = 'mt-1 w-full min-w-0 rounded-md border border-white/15 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 disabled:opacity-50'
const buttonClass = 'min-h-10 rounded-md border border-white/20 px-3 py-2 text-xs text-zinc-200 disabled:opacity-40'
const cardClass = 'space-y-2 rounded-md border border-white/10 p-3'

type Props = { projectId: string; sceneId: string; versionId: string; activeShotNumber: number; onSaved: () => void }

type ObligationType = CoverageDecision['obligation_type']

const decisionFor = (data: SceneDirection, type: ObligationType, id: string): CoverageDecision | undefined =>
  data.coverage_decisions.find(row => row.obligation_type === type && row.obligation_id === id)

const ownsAssignment = (data: SceneDirection, type: 'content' | 'dialogue', shotId: string): boolean =>
  data.coverage_decisions.some(row => row.obligation_type === type && row.status === 'ASSIGNED' && row.shot_id === shotId)

/**
 * An obligation counts as resolved only through a creator decision: either its
 * own explicit disposition, or — for shot-level rows — the creator's explicit
 * assignment of content/dialogue to that shot. Nothing resolves because the
 * shot exists, because a reference is canonical, or because the page opened.
 */
const isResolved = (data: SceneDirection, row: CoverageDecision): boolean => {
  if (row.status !== 'UNASSIGNED') return true
  if (row.obligation_type === 'shot_dialogue') return ownsAssignment(data, 'dialogue', row.obligation_id)
  if (row.obligation_type === 'shot_content') return ownsAssignment(data, 'content', row.obligation_id)
  return false
}

const SILENCE_ELIGIBLE_KINDS = ['establishing', 'establishing_shot', 'transition', 'transition_shot']

const isSilenceEligibleKind = (kind: string): boolean =>
  SILENCE_ELIGIBLE_KINDS.includes(kind.trim().toLowerCase())

const shotKindLabel = (kind: string): string => (kind.trim() ? kind : 'kind not recorded')

const contentOwnedByShot = (data: SceneDirection, shotId: string): CoverageDecision[] =>
  data.coverage_decisions.filter(row => row.obligation_type === 'content' && row.status === 'ASSIGNED' && row.shot_id === shotId)

type ShotBoardState = 'covered' | 'needs-line' | 'silence-allowed'

const shotBoardState = (data: SceneDirection, shotId: string, eligible: boolean): ShotBoardState =>
  contentOwnedByShot(data, shotId).length > 0 ? 'covered' : eligible ? 'silence-allowed' : 'needs-line'

const shotBoardStateLabel = (state: ShotBoardState): string =>
  state === 'covered' ? 'covered' : state === 'silence-allowed' ? 'silence allowed' : 'needs a line'

const shotBoardChipClass = (state: ShotBoardState): string =>
  state === 'covered'
    ? 'border-emerald-300/40 text-emerald-200'
    : state === 'silence-allowed'
      ? 'border-amber-200/40 text-amber-100'
      : 'border-rose-300/50 text-rose-200'

const shotNumberOf = (data: SceneDirection, shotId: string | null): number | null =>
  data.shots.find(item => item.shot_id === shotId)?.shot_number ?? null

const VO_CUE_PATTERN = /\(V\.O\.\)/i

const scrollToShotCard = (shotId: string): void => {
  document.getElementById(`shot-board-card-${shotId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/**
 * "Move a line here" for one shot card. Presentation only: a move is a single
 * content reassignment through the existing editCoverage('content', ...)
 * path, committed by the existing save flow. A donor left with no lines is
 * blocked with the reason, and another line is suggested.
 */
function MoveLineControl({ data, targetShotId, targetShotNumber, onMove }: {
  data: SceneDirection
  targetShotId: string
  targetShotNumber: number
  onMove: (lineId: string) => void
}) {
  const [selected, setSelected] = useState('')
  const candidates = data.coverage_decisions.filter(row =>
    row.obligation_type === 'content' && row.status === 'ASSIGNED' && row.shot_id && row.shot_id !== targetShotId)
  const donorKeeps = (donorId: string | null): number =>
    donorId ? contentOwnedByShot(data, donorId).length - 1 : 0
  const movable = candidates.filter(row => donorKeeps(row.shot_id) >= 1)
  const targetOwns = contentOwnedByShot(data, targetShotId).length
  if (candidates.length === 0) {
    return <p className="text-xs text-zinc-400">No lines are owned by other shots yet — assign a line to a shot in section A first, then move it here.</p>
  }
  if (movable.length === 0) {
    const only = candidates[0]
    const donorNumber = shotNumberOf(data, only.shot_id)
    return <p role="status" className="text-xs leading-relaxed text-amber-200">Moving {only.obligation_id} would leave Shot {donorNumber ?? only.shot_id} with no lines, so it stays put. Assign another line to Shot {targetShotNumber} in section A first.</p>
  }
  const chosen = candidates.find(row => row.obligation_id === selected)
  const chosenDonorNumber = chosen ? shotNumberOf(data, chosen.shot_id) : null
  const chosenBlocked = chosen ? donorKeeps(chosen.shot_id) < 1 : false
  const suggestion = movable.find(row => row.obligation_id !== selected)
  return (
    <div className="space-y-2">
      <label className="block text-xs text-zinc-300">Move a line here<select aria-label={`Move a line to shot ${targetShotNumber}`} className={inputClass} value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">Choose a line from another shot</option>
        {candidates.map(row => {
          const donorNumber = shotNumberOf(data, row.shot_id)
          const empties = donorKeeps(row.shot_id) < 1
          return <option key={row.obligation_id} value={row.obligation_id} disabled={empties}>{row.obligation_id} · from Shot {donorNumber ?? row.shot_id}{empties ? ' · would leave that shot empty' : ''}</option>
        })}
      </select></label>
      {chosen && !chosenBlocked && <p role="status" className="text-xs text-zinc-300">Shot {chosenDonorNumber ?? chosen.shot_id} keeps {donorKeeps(chosen.shot_id)} {donorKeeps(chosen.shot_id) === 1 ? 'line' : 'lines'}. Shot {targetShotNumber} gets {targetOwns + 1}.</p>}
      {chosen && chosenBlocked && <p role="status" className="text-xs leading-relaxed text-amber-200">Cannot move {chosen.obligation_id} — Shot {chosenDonorNumber ?? chosen.shot_id} would be left with no lines.{suggestion ? ` Try ${suggestion.obligation_id} from Shot ${shotNumberOf(data, suggestion.shot_id) ?? suggestion.shot_id} instead.` : ' Assign another line in section A first.'}</p>}
      <button type="button" disabled={!chosen || chosenBlocked} onClick={() => { if (chosen && !chosenBlocked) { onMove(chosen.obligation_id); setSelected('') } }} className={buttonClass}>Move line to Shot {targetShotNumber}</button>
    </div>
  )
}

/**
 * V.O. group: the cue is a content line, the spoken words are dialogue. Each
 * stays separately assignable in sections A and B; the spoken lines are
 * labeled as one unit that stays together on one shot.
 */
function VoGroupBox({ data }: { data: SceneDirection }) {
  const cueUnits = data.coverage_obligations.filter(row => row.obligation_type === 'content' && VO_CUE_PATTERN.test(row.source_text))
  if (data.dialogue.length === 0 && cueUnits.length === 0) return null
  const spokenOwners = data.dialogue.map(line => {
    const decision = decisionFor(data, 'dialogue', line.line_id)
    return { line, shotId: decision && decision.status === 'ASSIGNED' ? decision.shot_id : null }
  })
  const assignedShots = [...new Set(spokenOwners.map(row => row.shotId).filter((id): id is string => id !== null))]
  const togetherShot = assignedShots.length === 1 ? shotNumberOf(data, assignedShots[0]) : null
  return (
    <div data-testid="vo-group" className="space-y-2 rounded-md border border-white/10 bg-black/20 p-3">
      <h5 className="text-xs font-medium text-zinc-100">V.O. group — cue plus spoken lines</h5>
      <p className="text-xs leading-relaxed text-zinc-400">The cue (for example “MAYA (V.O.)”) is a content line; the spoken words are dialogue. The cue and each spoken line are assigned separately in sections A and B, and the spoken lines below stay together as one unit on one shot.</p>
      {cueUnits.map(unit => {
        const decision = decisionFor(data, 'content', unit.obligation_id)
        const owner = decision && decision.status === 'ASSIGNED' ? shotNumberOf(data, decision.shot_id) : null
        return <p key={unit.obligation_id} className="text-xs text-zinc-300">Cue {unit.obligation_id} (“{unit.source_text.slice(0, 60)}”) · {owner ? `Shot ${owner}` : 'no shot yet — assign it in section A'}</p>
      })}
      <p className="text-xs text-zinc-300">Spoken-dialogue block · one unit that stays together · {togetherShot ? `together on Shot ${togetherShot}` : assignedShots.length === 0 ? 'no shot yet — assign every spoken line to the same shot in section B' : 'split across shots — bring every spoken line onto one shot in section B'}</p>
      <ul className="space-y-1">
        {spokenOwners.map(({ line, shotId }) => <li key={line.line_id} className="text-[11px] text-zinc-400">{line.line_id} · {line.character} · {shotId ? `Shot ${shotNumberOf(data, shotId) ?? shotId}` : 'no shot yet'}</li>)}
      </ul>
    </div>
  )
}

/** Visible decision label: UNRESOLVED, or the chosen decision state. */
const badgeLabel = (data: SceneDirection, row: CoverageDecision): string => {
  if (row.status !== 'UNASSIGNED') return row.status
  if (isResolved(data, row)) return 'ASSIGNED'
  return 'UNRESOLVED'
}

function StatusBadge({ label }: { label: string }) {
  const unresolved = label === 'UNRESOLVED'
  return (
    <span
      data-testid="decision-badge"
      data-state={unresolved ? 'unresolved' : 'resolved'}
      className={`inline-block shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${unresolved ? 'border-rose-300/50 text-rose-200' : 'border-emerald-300/40 text-emerald-200'}`}
    >
      {label}
    </span>
  )
}

/**
 * Scene Direction creator capture.
 *
 * Three decisions stay distinct: the Scene Direction reference selection,
 * the coverage decisions below, and (in the Setting Reference Authority
 * panel) setting authority itself. Opening this panel performs no mutation,
 * selects nothing, and resolves nothing — every one of the 60 obligations
 * stays UNRESOLVED until the creator decides it explicitly. Saving is always
 * an explicit, reviewed commit that produces a new DRAFT successor; it never
 * marks the scene READY.
 */
export function SceneDirectionPanel({ projectId, sceneId, versionId, activeShotNumber, onSaved }: Props) {
  const editor = useSceneDirection(projectId, sceneId, versionId)
  const data = editor.data
  // The review is bound to the version it was opened for: when the data
  // reloads or a save produces a successor version, any open review closes.
  const [reviewVersion, setReviewVersion] = useState<string | null>(null)
  const reviewing = reviewVersion !== null && reviewVersion === data?.version_id
  const [savedVersion, setSavedVersion] = useState<string | null>(null)
  const showSavedVersion = savedVersion !== null && savedVersion === data?.version_id

  const currentIndex = data?.shots.findIndex(shot => shot.shot_number === activeShotNumber) ?? -1
  const shot = data?.shots[currentIndex]
  const previous = currentIndex > 0 ? data?.shots[currentIndex - 1] : null

  // Only exact-target options for this scene's canonical setting entity are
  // offerable. The legacy scene-targeted reference ID and any option aimed at a
  // different target are never presented, and nothing is ever pre-selected.
  const eligibleOptions = (data?.setting_reference_options ?? []).filter(option =>
    Boolean(data?.canonical_setting_id)
    && option.target_type === 'setting'
    && option.target_id === data?.canonical_setting_id
    && option.kind === 'environment'
    && option.approval_state === 'approved'
    && option.canonical === true
    && option.ref_id !== LEGACY_SCENE002_REFERENCE_ID,
  )
  const eligibleReferenceIds = new Set(eligibleOptions.map(option => option.ref_id))

  const contentRows = data?.coverage_obligations.filter(row => row.obligation_type === 'content') ?? []
  const dialogueRows = data?.coverage_decisions.filter(row => row.obligation_type === 'dialogue') ?? []
  const shotContentRows = data?.coverage_decisions.filter(row => row.obligation_type === 'shot_content') ?? []
  const shotDialogueRows = data?.coverage_decisions.filter(row => row.obligation_type === 'shot_dialogue') ?? []

  const totalCount = data?.coverage_decisions.length ?? 0
  const resolvedCount = data ? data.coverage_decisions.filter(row => isResolved(data, row)).length : 0
  const unresolvedCount = totalCount - resolvedCount
  const unassigned = dialogueRows.filter(row => row.status === 'UNASSIGNED').length

  const sectionCounts = [
    { key: 'content', label: 'A · CONTENT', count: contentRows.length, resolved: contentRows.filter(row => { const decision = decisionFor(data!, 'content', row.obligation_id); return decision ? isResolved(data!, decision) : false }).length },
    { key: 'dialogue', label: 'B · DIALOGUE', count: dialogueRows.length, resolved: dialogueRows.filter(row => isResolved(data!, row)).length },
    { key: 'shot_content', label: 'C · SHOT CONTENT', count: shotContentRows.length, resolved: shotContentRows.filter(row => isResolved(data!, row)).length },
    { key: 'shot_dialogue', label: 'D · SHOT DIALOGUE', count: shotDialogueRows.length, resolved: shotDialogueRows.filter(row => isResolved(data!, row)).length },
  ]

  const coveredShotCount = data ? data.shots.filter(item => contentOwnedByShot(data, item.shot_id).length > 0).length : 0
  const unassignedContent = data ? data.coverage_decisions.filter(row => row.obligation_type === 'content' && row.status === 'UNASSIGNED') : []
  const blockingSummary = !data ? '' : !data.coverage_blocked
    ? 'Nothing on this board is blocking render.'
    : data.coverage_blockers.length > 0
      ? `What is blocking render: ${data.coverage_blockers[0]}${data.coverage_blockers.length > 1 ? ` (+${data.coverage_blockers.length - 1} more)` : ''}`
      : 'What is blocking render: coverage is blocked — work each card below.'

  const confirmSave = async () => {
    const result = await editor.save()
    // The save response model (SceneDirection) returns the new draft
    // version_id but no image-prompt carry-forward fields, so the success
    // note below stays static about prompts and names the draft version.
    if (result) { setReviewVersion(null); setSavedVersion(result.version_id); onSaved() }
  }

  return (
    <details open className="rounded-lg border border-white/15 p-3">
      <summary className="cursor-pointer text-sm font-medium text-zinc-200">Scene Direction &amp; coverage decisions · creator capture</summary>
      <div className="mt-4 space-y-5">
        <p className="text-xs leading-relaxed text-zinc-400">This surface captures creator decisions only: the Scene Direction reference selection and all coverage obligations. Save commits your explicit decisions as a new draft; existing takes stay as they are. Nothing here runs preflight, contacts a provider, or marks the scene READY.</p>
        {editor.error && <p role="alert" className="text-sm text-red-300">{editor.error}</p>}
        {!data && editor.busy && <p role="status" className="text-sm text-zinc-400">Loading scene direction…</p>}
        {data && <form className="space-y-5" onSubmit={event => { event.preventDefault(); if (editor.dirty && data) setReviewVersion(data.version_id) }}>
          <fieldset disabled={editor.busy} className="min-w-0 space-y-4">
            <section className="space-y-3 rounded-md border border-amber-200/20 bg-amber-200/[0.03] p-3">
              <h3 className="text-sm font-medium text-zinc-100">Scene Direction · exact setting reference selection</h3>
              {data.canonical_setting_id ? <p className="text-xs text-zinc-300">Canonical setting entity: <code className="text-amber-100">{data.canonical_setting_id}</code></p> : <p role="alert" className="text-xs text-amber-200">No canonical setting entity is resolved for this scene. Reference authority stays blocked.</p>}
              <p className="text-xs text-zinc-400">Creator selection is required. Scene ID and storyboard imagery do not identify a setting reference. Reference approval and canonical designation are separate creator actions performed in Setting authority above.</p>
              <label className="block text-xs text-zinc-300">Explicit creator-selected reference<select aria-label="Canonical setting reference" className={inputClass} value={data.setting_reference_decision?.reference_id || ''} onChange={event => { const referenceId = event.target.value; if (!referenceId) { editor.editSettingReference(null); return } if (!data.canonical_setting_id || !eligibleReferenceIds.has(referenceId)) return; editor.editSettingReference({ canonical_setting_id: data.canonical_setting_id, reference_id: referenceId }) }}>
                <option value="">Choose a reference</option>
                {eligibleOptions.map(option => <option key={option.ref_id} value={option.ref_id}>{option.ref_id} · {option.target_type}/{option.target_id} · {option.kind} · {option.approval_state}{option.canonical ? ' · canonical' : ''}</option>)}
              </select></label>
              {eligibleOptions.length === 0 && data.canonical_setting_id && <p role="status" className="text-xs text-amber-200">No approved references are registered for {data.canonical_setting_id} yet, so there is nothing to choose. In Setting authority above, register the image as a candidate for that exact setting, then approve it and designate it canonical — it will appear here as a choice. References approved for a different setting never appear here.</p>}
              {data.setting_reference_decision && <p className="text-[11px] text-zinc-400">Selected exact reference ID: <code>{data.setting_reference_decision.reference_id}</code></p>}
            </section>

            <section className="space-y-2 rounded-md border border-white/10 p-3">
              <h3 className="text-sm font-medium text-zinc-100">Approved shots in this scene</h3>
              <p className="text-xs text-zinc-400">Shot identity is read-only here. A shot existing never resolves an obligation.</p>
              <ul className="flex flex-wrap gap-2">
                {data.shots.map(item => <li key={item.shot_id} className="rounded border border-white/10 bg-black/30 px-2 py-1 text-[11px] text-zinc-300"><code>{item.shot_id}</code> · Shot {item.shot_number}{item.locked ? ' · locked' : ''}</li>)}
              </ul>
            </section>

            <section aria-label="Coverage decisions" data-testid="coverage-workspace" className="space-y-4 rounded-md border border-white/15 p-3">
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-zinc-100">Coverage decisions · {totalCount} obligations</h3>
                <div data-testid="coverage-progress" role="status" className="space-y-1">
                  <p className="text-sm font-medium text-amber-100"><span data-testid="coverage-resolved-count">{`${resolvedCount} / ${totalCount} resolved`}</span></p>
                  <p className="text-xs text-rose-200">{unresolvedCount} UNRESOLVED</p>
                  <div className="h-1.5 w-full overflow-hidden rounded bg-white/10"><div className="h-1.5 rounded bg-amber-200 transition-all" style={{ width: `${totalCount ? Math.round((resolvedCount / totalCount) * 100) : 0}%` }} /></div>
                </div>
                <nav aria-label="Coverage sections" className="flex flex-wrap gap-2">
                  {sectionCounts.map(section => <span key={section.key} data-testid={`coverage-tab-${section.key}`} className="rounded border border-white/15 px-2 py-1 text-[11px] text-zinc-300">{section.label} · {section.count} obligations · {section.resolved} resolved</span>)}
                </nav>
                <p className="text-xs text-zinc-400">Every obligation stays UNRESOLVED until you choose a decision yourself. Opening this page, saving a reference, or a shot merely existing never resolves anything.</p>
                {unassigned > 0 && <p role="status" className="text-xs text-amber-200">{unassigned} dialogue {unassigned === 1 ? 'line is' : 'lines are'} unresolved.</p>}
                {data.coverage_blocked && <p role="status" className="text-xs text-amber-200">Coverage remains blocked until every required obligation has an explicit supported decision.</p>}
              </div>

              <section aria-label="Content coverage" data-testid="coverage-section-content" className="space-y-3 border-t border-white/10 pt-3">
                <h4 className="text-sm font-medium text-zinc-100">A · CONTENT — {contentRows.length} obligations</h4>
                <p className="text-xs text-zinc-400">Every source unit stays independently visible. Assignment is never inferred from order, prompt, or narrative meaning. Allowed decisions: ASSIGNED (with an explicit shot) or EXPLICITLY_OMITTED (with your reason).</p>
                {contentRows.map((unit, index) => { const decision = decisionFor(data, 'content', unit.obligation_id); return decision && <article key={unit.obligation_id} className={cardClass}>
                  <div className="flex flex-wrap items-center gap-2"><StatusBadge label={badgeLabel(data, decision)} /><span className="text-[11px] text-zinc-500">{unit.obligation_id} · source {unit.source_start ?? '—'}–{unit.source_end ?? '—'}</span></div>
                  <p className="whitespace-pre-wrap text-sm text-zinc-100">{unit.source_text}</p>
                  <p className="text-xs text-zinc-300">Current status: {decision.status === 'ASSIGNED' ? `Assigned · Shot ${data.shots.find(item => item.shot_id === decision.shot_id)?.shot_number ?? decision.shot_id}` : decision.status === 'EXPLICITLY_OMITTED' ? 'Explicitly omitted' : 'Unresolved — your decision required'}</p>
                  <label className="block text-xs text-zinc-300">Content decision {index + 1}<select aria-label={`Coverage decision for content ${index + 1}`} className={inputClass} value={decision.status} onChange={event => { const status = event.target.value as CoverageDecision['status']; editor.editCoverage('content', unit.obligation_id, { status, shot_id: status === 'ASSIGNED' ? decision.shot_id : null, reason: status === 'EXPLICITLY_OMITTED' ? decision.reason : '' }) }}><option value="UNASSIGNED">UNASSIGNED</option><option value="ASSIGNED">Assigned to one approved shot</option><option value="EXPLICITLY_OMITTED">Explicitly omitted</option></select></label>
                  {decision.status === 'ASSIGNED' && <label className="block text-xs text-zinc-300">Owning shot<select aria-label={`Owning shot for content ${index + 1}`} required className={inputClass} value={decision.shot_id || ''} onChange={event => editor.editCoverage('content', unit.obligation_id, { shot_id: event.target.value || null })}><option value="">Choose a shot</option>{data.shots.map(item => <option key={item.shot_id} value={item.shot_id}>Shot {item.shot_number}{item.locked ? ' · locked' : ''}</option>)}</select></label>}
                  {decision.status === 'EXPLICITLY_OMITTED' && <label className="block text-xs text-zinc-300">Creator reason (required)<textarea aria-label={`Omission reason for content ${index + 1}`} required maxLength={2000} rows={2} className={inputClass} value={decision.reason} onChange={event => editor.editCoverage('content', unit.obligation_id, { reason: event.target.value })} /></label>}
                </article> })}
              </section>

              <section aria-label="Dialogue coverage" data-testid="coverage-section-dialogue" className="space-y-3 border-t border-white/10 pt-3">
                <h4 className="text-sm font-medium text-zinc-100">B · DIALOGUE — {dialogueRows.length} obligations</h4>
                <p className="text-xs text-zinc-400">Canonical screenplay wording is read-only. Allowed decisions: ASSIGNED (with an explicit shot) or EXPLICITLY_OMITTED (with your reason). Intentional silence is not a valid decision for a spoken line.</p>
                {!data.saved && data.dialogue.length > 0 && <p className="text-xs text-zinc-400">Canonical screenplay wording is read-only here. Make no choice until you explicitly assign or omit it.</p>}
                {data.dialogue.map((line, index) => { const decision = decisionFor(data, 'dialogue', line.line_id); return decision && <fieldset key={line.line_id} disabled={data.shots.some(item => item.shot_id === decision.shot_id && item.locked)} className="min-w-0 space-y-2 rounded-md border border-white/10 p-3">
                  <legend className="px-1 text-xs text-zinc-400">Line {index + 1}</legend>
                  <div className="flex flex-wrap items-center gap-2"><StatusBadge label={badgeLabel(data, decision)} /><span className="text-[11px] text-zinc-500">{line.line_id}</span></div>
                  <p className="whitespace-pre-wrap text-sm text-zinc-100">{line.text}</p>
                  <p className="text-xs text-zinc-400">{line.character} · canonical source wording</p>
                  <p className="text-xs text-zinc-300">Current status: {decision.status === 'ASSIGNED' ? `Assigned · Shot ${data.shots.find(item => item.shot_id === decision.shot_id)?.shot_number ?? decision.shot_id}` : decision.status === 'EXPLICITLY_OMITTED' ? 'Explicitly omitted' : 'Unassigned'}</p>
                  <label className="block text-xs text-zinc-300">Coverage decision {index + 1}<select aria-label={`Coverage decision for dialogue ${index + 1}`} className={inputClass} value={decision.status} onChange={event => { const status = event.target.value as CoverageDecision['status']; editor.editCoverage('dialogue', line.line_id, { status, shot_id: status === 'ASSIGNED' ? decision.shot_id : null, reason: status === 'EXPLICITLY_OMITTED' ? decision.reason : '' }); editor.editLine(line.line_id, { shot_id: status === 'ASSIGNED' ? decision.shot_id : null }) }}><option value="UNASSIGNED">UNASSIGNED</option><option value="ASSIGNED">Assigned to one approved shot</option><option value="EXPLICITLY_OMITTED">Explicitly omitted</option></select></label>
                  {decision.status === 'ASSIGNED' && <label className="block text-xs text-zinc-300">Owning shot<select aria-label={`Owning shot for dialogue ${index + 1}`} required className={inputClass} value={decision.shot_id || ''} onChange={event => { editor.editCoverage('dialogue', line.line_id, { shot_id: event.target.value || null }); editor.editLine(line.line_id, { shot_id: event.target.value || null }) }}><option value="">Choose a shot</option>{data.shots.map(item => <option key={item.shot_id} value={item.shot_id}>Shot {item.shot_number}{item.locked ? ' · locked' : ''}</option>)}</select></label>}
                  {decision.status === 'EXPLICITLY_OMITTED' && <label className="block text-xs text-zinc-300">Creator reason (required)<textarea aria-label={`Omission reason for dialogue ${index + 1}`} required maxLength={2000} rows={2} className={inputClass} value={decision.reason} onChange={event => editor.editCoverage('dialogue', line.line_id, { reason: event.target.value })} /></label>}
                </fieldset> })}
              </section>

              <section aria-label="Shot board" data-testid="coverage-section-shot-content" className="space-y-3 border-t border-white/10 pt-3">
                <h4 className="text-sm font-medium text-zinc-100">C · SHOT BOARD — {data.shots.length} shots</h4>
                <p className="text-xs text-zinc-400">One card per approved shot, read from the live board. A shot is covered when a content line is assigned to it in section A; an eligible establishing or transition shot may instead record intentional silence with a reason. This board only explains the rules — it never changes them.</p>
                <p data-testid="shot-board-progress" role="status" className="text-xs font-medium text-amber-100">{coveredShotCount} of {data.shots.length} shots covered</p>
                <nav aria-label="Shot chips" className="flex flex-wrap gap-2">
                  {data.shots.map(item => {
                    const chipState = shotBoardState(data, item.shot_id, isSilenceEligibleKind(item.shot_kind))
                    return <button key={item.shot_id} type="button" aria-label={`Go to Shot ${item.shot_number} card · ${shotBoardStateLabel(chipState)}`} onClick={() => scrollToShotCard(item.shot_id)} className={`rounded border px-2 py-1 text-[11px] ${shotBoardChipClass(chipState)}`}>Shot {item.shot_number} · {shotBoardStateLabel(chipState)}</button>
                  })}
                </nav>
                <p role="status" className="text-xs leading-relaxed text-zinc-300">{blockingSummary}</p>
                <VoGroupBox data={data} />
                <div data-testid="shot-board-tray" className="rounded-md border border-white/10 bg-black/20 p-3">
                  <h5 className="text-xs font-medium text-zinc-100">Lines with no shot · {unassignedContent.length}</h5>
                  {unassignedContent.length === 0
                    ? <p className="mt-1 text-xs text-zinc-400">Every content line currently names a shot.</p>
                    : <ul className="mt-1 space-y-1">{unassignedContent.map(row => <li key={row.obligation_id} className="text-[11px] text-zinc-400">{row.obligation_id} — assign it in section A above, or bring it onto a card with “Move a line here”.</li>)}</ul>}
                </div>
                {data.shots.map(item => {
                  const decision = decisionFor(data, 'shot_content', item.shot_id)
                  if (!decision) return null
                  const silenceEligible = isSilenceEligibleKind(item.shot_kind)
                  const owned = contentOwnedByShot(data, item.shot_id)
                  const boardState = shotBoardState(data, item.shot_id, silenceEligible)
                  return <article key={item.shot_id} id={`shot-board-card-${item.shot_id}`} data-testid={`shot-board-card-${item.shot_number}`} className={cardClass}>
                    <div className="flex flex-wrap items-center gap-2"><StatusBadge label={badgeLabel(data, decision)} /><span className="text-xs text-zinc-200">Shot {item.shot_number} · <code>{item.shot_id}</code> · {shotKindLabel(item.shot_kind)}</span><span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${shotBoardChipClass(boardState)}`}>{shotBoardStateLabel(boardState)}</span></div>
                    {boardState === 'covered' && <p className="text-xs text-zinc-300">Covered — {owned.length} {owned.length === 1 ? 'line' : 'lines'} explicitly assigned to this shot.</p>}
                    {owned.length > 0 && <ul className="space-y-1">{owned.map(row => {
                      const unit = data.coverage_obligations.find(candidate => candidate.obligation_type === 'content' && candidate.obligation_id === row.obligation_id)
                      const isVoCue = unit ? VO_CUE_PATTERN.test(unit.source_text) : false
                      return <li key={row.obligation_id} className="text-[11px] text-zinc-400">{row.obligation_id}{unit ? ` — “${unit.source_text.slice(0, 80)}”` : ''}{isVoCue ? ' · V.O. cue' : ''}</li>
                    })}</ul>}
                    {boardState === 'needs-line' && <p role="status" className="text-xs leading-relaxed text-rose-200">Needs a line — this {shotKindLabel(item.shot_kind)} cannot be silent, so intentional silence is not offered here. Assign a line in section A above, or move a line here.</p>}
                    {boardState === 'silence-allowed' && <>
                      <p className="text-xs leading-relaxed text-zinc-300">Silence allowed — this establishing or transition shot may record intentional silence with your reason, or take a line instead.</p>
                      <label className="block text-xs text-zinc-300">Disposition<select aria-label={`Content disposition for shot ${item.shot_number}`} className={inputClass} value={decision.status} onChange={event => { const status = event.target.value as CoverageDecision['status']; editor.editCoverage('shot_content', item.shot_id, { status, reason: status === 'UNASSIGNED' ? '' : decision.reason }) }}><option value="UNASSIGNED">UNASSIGNED · decision required</option><option value="INTENTIONAL_SILENCE">Intentional establishing shot</option></select></label>
                      {decision.status === 'INTENTIONAL_SILENCE' && <label className="block text-xs text-zinc-300">Creator reason (required)<textarea aria-label={`Content disposition reason for shot ${item.shot_number}`} required maxLength={2000} rows={2} className={inputClass} value={decision.reason} onChange={event => editor.editCoverage('shot_content', item.shot_id, { reason: event.target.value })} /></label>}
                    </>}
                    <MoveLineControl data={data} targetShotId={item.shot_id} targetShotNumber={item.shot_number} onMove={lineId => editor.editCoverage('content', lineId, { shot_id: item.shot_id })} />
                  </article>
                })}
                <p className="text-xs leading-relaxed text-zinc-400">What saving does: saving mints a new DRAFT successor version and leaves the approved version untouched. Approved image prompts move across where the shot text did not change. Nothing is marked READY.</p>
                {showSavedVersion && <p data-testid="save-success" role="status" className="text-xs text-emerald-200">Saved as new draft {savedVersion}. The approved source version is untouched; approved image prompts moved across where the shot text did not change.</p>}
              </section>

              <section aria-label="Shot dialogue coverage" data-testid="coverage-section-shot-dialogue" className="space-y-3 border-t border-white/10 pt-3">
                <h4 className="text-sm font-medium text-zinc-100">D · SHOT DIALOGUE — {shotDialogueRows.length} obligations</h4>
                <p className="text-xs text-zinc-400">Allowed decisions: EXPLICITLY_OMITTED or INTENTIONAL_SILENCE, each with your reason. A shot that owns assigned dialogue cannot also be omitted or marked silent.</p>
                {shotDialogueRows.map(row => { const decision = decisionFor(data, 'shot_dialogue', row.obligation_id); const item = data.shots.find(candidate => candidate.shot_id === row.obligation_id); const assigned = ownsAssignment(data, 'dialogue', row.obligation_id); if (!decision || !item) return null; return <div key={row.obligation_id} className={cardClass}>
                  <div className="flex flex-wrap items-center gap-2"><StatusBadge label={badgeLabel(data, decision)} /><span className="text-xs text-zinc-200">Shot {item.shot_number} · <code>{item.shot_id}</code></span></div>
                  <p className="text-xs text-zinc-400">{assigned ? 'dialogue explicitly assigned above' : 'no dialogue assigned · disposition required'}</p>
                  {assigned ? <p className="text-xs text-zinc-300">Current status: Assigned dialogue</p> : <>
                    <label className="block text-xs text-zinc-300">Shot dialogue disposition<select aria-label={`Dialogue disposition for shot ${item.shot_number}`} className={inputClass} value={decision.status} onChange={event => { const status = event.target.value as CoverageDecision['status']; editor.editCoverage('shot_dialogue', item.shot_id, { status, reason: status === 'UNASSIGNED' ? '' : decision.reason }) }}><option value="UNASSIGNED">UNASSIGNED · decision required</option><option value="INTENTIONAL_SILENCE">Intentional silence</option><option value="EXPLICITLY_OMITTED">Dialogue omitted</option></select></label>
                    {decision.status !== 'UNASSIGNED' && <label className="block text-xs text-zinc-300">Creator reason (required)<textarea aria-label={`Dialogue disposition reason for shot ${item.shot_number}`} required maxLength={2000} rows={2} className={inputClass} value={decision.reason} onChange={event => editor.editCoverage('shot_dialogue', item.shot_id, { reason: event.target.value })} /></label>}
                  </>}
                </div> })}
              </section>
            </section>
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

          <p className="text-xs leading-relaxed text-zinc-400">UNASSIGNED obligations remain unresolved and block coverage. Saving records creator decisions only; it does not run preflight, create a generation contract, contact a provider, or mark Scene 002 READY.</p>

          {reviewing && <section aria-label="Review decisions before saving" data-testid="save-review" className="space-y-3 rounded-md border border-amber-200/40 bg-amber-200/[0.05] p-3">
            <h4 className="text-sm font-medium text-amber-100">Review before commit</h4>
            <p className="text-xs leading-relaxed text-zinc-300">Saving writes {resolvedCount} resolved and {unresolvedCount} UNRESOLVED decisions as a new DRAFT successor of <code>{data.version_id}</code>. The approved source version is not modified and this does not mark the scene READY. Unresolved obligations stay unresolved.</p>
            <p className="text-xs text-zinc-300">Scene Direction reference: {data.setting_reference_decision ? <code>{data.setting_reference_decision.reference_id}</code> : 'no reference selected'} · Shot handoffs: {data.shots.length} shot(s)</p>
            <ul className="max-h-64 space-y-1 overflow-y-auto rounded border border-white/10 bg-black/30 p-2 text-[11px] text-zinc-300">
              {data.coverage_decisions.map(row => <li key={`${row.obligation_type}:${row.obligation_id}`}><span className="text-zinc-500">{row.obligation_type}</span> · {row.obligation_id} → <strong className={badgeLabel(data, row) === 'UNRESOLVED' ? 'text-rose-200' : 'text-emerald-200'}>{badgeLabel(data, row)}</strong>{row.shot_id ? ` · ${row.shot_id}` : ''}{row.reason ? ` · reason: ${row.reason}` : ''}</li>)}
            </ul>
            {editor.error && <p role="alert" className="text-xs text-red-300">{editor.error}</p>}
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={editor.busy} onClick={() => void confirmSave()} className="min-h-11 rounded-md bg-amber-200 px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40">{editor.busy ? 'Saving…' : 'Confirm & save decisions'}</button>
              <button type="button" disabled={editor.busy} onClick={() => setReviewVersion(null)} className={buttonClass}>Keep editing</button>
            </div>
          </section>}

          {!reviewing && <div className="flex flex-wrap gap-2"><button type="submit" disabled={editor.busy || !editor.dirty} className="min-h-11 rounded-md bg-amber-200 px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40">{editor.busy ? 'Saving…' : 'Review & save decisions'}</button><button type="button" disabled={editor.busy} onClick={editor.reload} className={buttonClass}>{editor.dirty ? 'Discard edits and reload' : 'Reload saved direction'}</button></div>}
        </form>}
        {!data && !editor.busy && <button type="button" className={buttonClass} onClick={editor.reload}>Retry loading direction</button>}
      </div>
    </details>
  )
}

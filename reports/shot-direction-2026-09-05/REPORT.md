# Dialogue assignment and continuity handoffs — September 5, 2026

Both features are implemented in Previs → Approve the storyboard → Dialogue & shot handoffs. Build a storyboard blueprint first if the scene does not have one.

## Creator workflow

Review the imported dialogue text and speaker, add/edit/remove lines, and choose a shot for each line. The editor visibly lists unassigned lines. Previewing, typing, and reading perform no save. Explicit empty assignments stay empty; unassigned lines are excluded from the new storyboard's shot audio rather than falling back to scene-wide dialogue. Existing voice-direction fields are preserved, and changing a speaker clears the old speaker's ID/voice hint.

For each shot, record its opening state, action/change, and ending state alongside the reference frame. The previous shot's ending is shown for comparison. Saving records the frame URL with the handoff; a subsequent frame change is flagged for review. These are creator intentions, not claims that the generated footage follows them.

Save scene direction creates a new storyboard draft in one transaction. The prior approved version and footage remain intact. Review continuity and approve the new draft before rendering it. The draft, assignments, unassigned lines, and handoffs persist after reopening storage. Locked shots cannot be changed through this editor. A stale version save is rejected without replacing the current version, and the UI keeps the unsaved text available for recovery.

## Production integration

- Provider-neutral storyboard inputs carry the saved opening/action/ending state and reference-frame metadata.
- Previs retains these notes even when the creator overrides the camera/action prompt. Duplicate handoff text is not appended twice.
- Explicit per-shot dialogue travels with the render parameters into scene audio production and scene assembly; empty lists prevent unintended scene-text fallback.
- Ordinary storyboard revisions retain explicit dialogue assignments. Lines whose shots were removed remain visible as unassigned. Existing per-shot dialogue and locked-shot inputs are preserved.
- New typed GET/PUT contracts are service-mediated. Storage uses the existing version-bundle transaction with an expected-version comparison. No schema migration, infrastructure rewrite, or paid integration was added.

## Verification

- 50 affected backend tests passed in a disposable backend copy: DTO/route validation, ownership, explicit persistence, reopen, retained approval, draft gate, prompt override, correct per-shot audio inputs, stale saves, atomic version comparison, failed persistence, frame changes, explicit clearing, revision carry-forward, deleted shots, locked shots, and existing voice direction.
- All 712 frontend tests passed; production TypeScript/Vite build passed.
- Browser checks passed for explicit saving, no write while typing, unassigned lines, previous-shot context, opening/action/ending persistence, reload, stale-save recovery, discard, desktop/mobile layout, and no page errors. Test writes were intercepted; the live editor check is read-only.
- React review and lint: no new warnings/errors. One existing Previs effect-dependency warning remains outside this change.
- Verified application source matches the isolated tested copy. Local backend activation checks readiness, the existing take/delivery contracts, and the new direction endpoint. Schema remains v62.

A focused run initially hit the environment's shared-memory restriction; it was rerun outside the sandbox using fake providers. No paid generation was performed. Existing project direction, approvals, and exports were not changed during verification.

These features guide future takes and sound production; they do not retrofit performances into already-rendered footage or guarantee a provider will preserve every prop handoff. No creative memory is saved by passive observation.

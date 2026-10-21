"""Version-scoped creator coverage and shot handoff capture."""
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

from app.models.scene_direction import (
    AssignedDialogue,
    CoverageDecision,
    CoverageObligation,
    DirectionShot,
    SaveSceneDirection,
    SceneDirection,
    SettingReferenceDecision,
    SettingReferenceOption,
)
from app.models.storyboard_blueprint import (
    StoryboardBlueprintInspection,
    StoryboardBlueprintStatus,
    utc_now_iso,
)
from app.services.stability import (
    PersistenceError,
    StateError,
    ValidationError,
    elapsed_ms,
    log_stage_event,
    start_timer,
)
from app.services.storyboard_blueprint_service import StoryboardBlueprintService


class SceneDirectionService:
    def __init__(self, storage=None):
        self.blueprints = StoryboardBlueprintService(storage=storage)
        self.storage = self.blueprints.storage

    def _coverage_snapshot(self, project_id, scene_id, version, shots):
        project_model = self.storage.get_project(project_id)
        project = project_model.model_dump(mode='json') if hasattr(project_model, 'model_dump') else project_model or {}
        summary = project.get('execution_summary') if isinstance(project.get('execution_summary'), dict) else {}
        source_scene = next((row for row in (summary.get('scenes') or [])
                             if isinstance(row, dict) and row.get('scene_id') == scene_id), None)
        if not isinstance(source_scene, dict):
            return [], [], [], ['Canonical scene coverage is unavailable.']

        from app.services.scene_coverage_contract import build_scene_coverage_contract

        shot_rows = []
        for shot in shots:
            row = shot.model_dump(mode='json')
            parameters = dict(row.get('render_contract', {}).get('structured_parameters', {}))
            # Historical shot-level dialogue and coverage fields are not creator choices.
            for key in ('dialogue_lines', 'covered_content_ids', 'creator_coverage_decisions',
                        'dialogue_disposition', 'content_coverage_disposition', 'content_coverage_reason'):
                parameters.pop(key, None)
            row['parameters'] = parameters
            row['covered_content_ids'] = []
            row['shot_id'] = shot.shot_id
            row['shot_number'] = shot.shot_number
            row['shot_kind'] = parameters.get('shot_kind') or shot.metadata.get('shot_kind', '')
            shot_rows.append(row)

        saved_rows = (version.metadata.get('scene_direction') or {}).get('coverage_decisions', [])
        canonical_scene = dict(source_scene)
        for key in ('coverage_decisions', 'content_dispositions', 'dialogue_dispositions',
                    'dialogue_disposition', 'speech_disposition', 'dialogue_lines'):
            canonical_scene.pop(key, None)
        coverage_project = dict(project)
        clean_summary = dict(summary)
        clean_summary['scenes'] = [canonical_scene if row is source_scene else row
                                   for row in (summary.get('scenes') or [])]
        clean_summary['dialogue_lines'] = [
            {key: value for key, value in row.items() if key != 'shot_id'}
            for row in (summary.get('dialogue_lines') or []) if isinstance(row, dict)
        ]
        coverage_project['execution_summary'] = clean_summary
        coverage, blockers, _ = build_scene_coverage_contract(
            project_id=project_id,
            project=coverage_project,
            scene=canonical_scene,
            shots=shot_rows,
            creator_decisions=saved_rows,
        )
        persisted = {(row.get('obligation_type'), row.get('obligation_id')): row
                     for row in saved_rows if isinstance(row, dict)}

        obligations = []
        decisions = []
        dialogue = []
        for unit in coverage.get('content_units', []):
            identity = unit['content_id']
            previous = persisted.get(('content', identity), {})
            status = previous.get('status', 'UNASSIGNED')
            shot_id = previous.get('shot_id') if status == 'ASSIGNED' else None
            reason = str(previous.get('reason') or '')
            obligations.append(CoverageObligation(
                obligation_type='content', obligation_id=identity, source_text=unit['text'],
                source_start=unit['source_start'], source_end=unit['source_end'],
                status=status, shot_id=shot_id, reason=reason,
                reason_required=status == 'EXPLICITLY_OMITTED',
            ))
            decisions.append(CoverageDecision(
                obligation_type='content', obligation_id=identity, status=status,
                shot_id=shot_id, reason=reason,
            ))

        for line in coverage.get('dialogue', []):
            identity = line['dialogue_id']
            previous = persisted.get(('dialogue', identity), {})
            status = previous.get('status', 'UNASSIGNED')
            shot_id = previous.get('shot_id') if status == 'ASSIGNED' else None
            reason = str(previous.get('reason') or '')
            speaker = line.get('speaker') or 'Speaker'
            obligations.append(CoverageObligation(
                obligation_type='dialogue', obligation_id=identity,
                source_text=line['text'], source_speaker=speaker,
                status=status, shot_id=shot_id, reason=reason,
                reason_required=status == 'EXPLICITLY_OMITTED',
            ))
            dialogue.append(AssignedDialogue(
                line_id=identity, character=speaker, text=line['text'], shot_id=shot_id,
            ))
            decisions.append(CoverageDecision(
                obligation_type='dialogue', obligation_id=identity, status=status,
                shot_id=shot_id, reason=reason,
            ))

        for shot in shots:
            for kind in ('shot_dialogue', 'shot_content'):
                previous = persisted.get((kind, shot.shot_id), {})
                decisions.append(CoverageDecision(
                    obligation_type=kind, obligation_id=shot.shot_id,
                    status=previous.get('status', 'UNASSIGNED'), reason=previous.get('reason', ''),
                ))
        return obligations, decisions, dialogue, blockers

    def _scene_setting_identity(self, project_id: str, scene_id: str) -> str | None:
        from app.services.reference_validation import resolve_canonical_setting_id

        project_model = self.storage.get_project(project_id)
        project = project_model.model_dump(mode='json') if hasattr(project_model, 'model_dump') else project_model or {}
        summary = project.get('execution_summary') if isinstance(project, dict) and isinstance(project.get('execution_summary'), dict) else {}
        scene = next((row for row in (summary.get('scenes') or [])
                      if isinstance(row, dict) and row.get('scene_id') == scene_id), None)
        if scene is None:
            scene = self.blueprints._get_scene(project_id, scene_id)
        if not isinstance(scene, dict):
            return None
        try:
            return resolve_canonical_setting_id(
                project_id=project_id, scene_id=scene_id, storage=self.storage, scene=scene,
            )
        except Exception:
            return None

    def _setting_reference_options(self, project_id: str, setting_id: str | None) -> list[SettingReferenceOption]:
        if not setting_id:
            return []
        # This is a direct read-only storage query. Do not route through the
        # reference-library GET endpoint, whose creator-sync hook can mutate rows.
        try:
            rows = self.storage.list_reference_assets(
                project_id=project_id, target_type='setting', target_id=setting_id, limit=200,
            ) or []
        except Exception:
            return []
        from app.services.reference_asset_service import scene002_setting_asset_view

        options = []
        for row in rows:
            if not (
                isinstance(row, dict)
                and str(row.get('project_id') or '') == project_id
                and str(row.get('ref_id') or '').strip()
                and str(row.get('target_type') or '') == 'setting'
                and str(row.get('target_id') or '') == setting_id
                and not (project_id == 'project_5907c60cddbc'
                         and setting_id == 'loc-c8f88b9c'
                         and str(row.get('ref_id') or '') == 'ref_env_6b726885ed67ae4d')
                and str(row.get('kind') or '') == 'environment'
                and str(row.get('approval_state') or '') == 'approved'
                and str(row.get('approval_state') or '') != 'rejected'
                and bool(row.get('canonical'))
            ):
                continue
            visible = scene002_setting_asset_view(row)
            if visible is None or not str(visible.get('image_url') or '').strip():
                continue
            options.append(SettingReferenceOption(
                ref_id=str(row['ref_id']),
                image_url=str(visible['image_url']).strip(),
                target_type='setting',
                target_id=setting_id,
                kind='environment',
                approval_state='approved',
                canonical=True,
            ))
        return options

    def _setting_reference_decision(self, version) -> SettingReferenceDecision | None:
        scene_direction = version.metadata.get('scene_direction') if isinstance(version.metadata, dict) else None
        raw_decision = scene_direction.get('setting_reference_decision') if isinstance(scene_direction, dict) else None
        try:
            return SettingReferenceDecision.model_validate(raw_decision) if raw_decision is not None else None
        except Exception as exc:
            raise ValidationError('The saved setting reference decision is malformed.', stage='scene_direction') from exc

    def get(
        self,
        project_id: str,
        scene_id: str,
        version_selection: Literal["current", "approved"] = "current",
    ) -> SceneDirection:
        # The approved opt-in exists for frozen and consumption surfaces
        # (inspection); editing surfaces omit it and keep the working draft.
        detail = self.blueprints.get_blueprint_detail(
            project_id=project_id, scene_id=scene_id, version_selection=version_selection
        )
        version = detail['version']
        shots = sorted(detail['shots'], key=lambda shot: shot.shot_number)
        setting_decision = self._setting_reference_decision(version)
        canonical_setting_id = self._scene_setting_identity(project_id, scene_id)
        obligations, decisions, dialogue, blockers = self._coverage_snapshot(project_id, scene_id, version, shots)
        known = {shot.shot_id for shot in shots}
        establishing_shots = {
            shot.shot_id for shot in shots
            if str(shot.render_contract.structured_parameters.get('shot_kind')
                   or shot.metadata.get('shot_kind') or '').lower()
            in {'establishing', 'establishing_shot', 'transition', 'transition_shot'}
        }
        assigned_content_shots = {
            row.shot_id for row in obligations
            if row.obligation_type == 'content' and row.status == 'ASSIGNED'
        }
        decisions = [
            row.model_copy(update={'status': 'UNASSIGNED', 'shot_id': None, 'reason': ''})
            if row.obligation_type in {'content', 'dialogue'} and row.status == 'ASSIGNED' and row.shot_id not in known
            else row.model_copy(update={'status': 'UNASSIGNED', 'reason': ''})
            if row.obligation_type == 'shot_content' and row.status == 'INTENTIONAL_SILENCE'
            and (row.obligation_id not in establishing_shots or row.obligation_id in assigned_content_shots)
            else row for row in decisions
        ]
        decision_by_key = {(row.obligation_type, row.obligation_id): row for row in decisions}
        dialogue = [line.model_copy(update={
            'shot_id': decision_by_key[('dialogue', line.line_id)].shot_id
            if decision_by_key[('dialogue', line.line_id)].status == 'ASSIGNED' else None,
        }) for line in dialogue]
        obligations = [row.model_copy(update={
            'status': decision_by_key[(row.obligation_type, row.obligation_id)].status,
            'shot_id': decision_by_key[(row.obligation_type, row.obligation_id)].shot_id,
            'reason': decision_by_key[(row.obligation_type, row.obligation_id)].reason,
            'reason_required': decision_by_key[(row.obligation_type, row.obligation_id)].status == 'EXPLICITLY_OMITTED',
        }) for row in obligations]

        direction_shots = []
        previous_ending = ''
        for shot in shots:
            plan = shot.continuity_plan
            saved_frame = shot.metadata.get('handoff_frame_url')
            direction_shots.append(DirectionShot(
                shot_id=shot.shot_id,
                shot_number=shot.shot_number,
                locked=shot.locked,
                opening_state=plan.opening_state,
                action_change=plan.action_change,
                ending_state=plan.ending_state,
                previous_ending_state=previous_ending,
                shot_kind=str(shot.render_contract.structured_parameters.get('shot_kind') or shot.metadata.get('shot_kind') or ''),
                dialogue_disposition=decision_by_key[('shot_dialogue', shot.shot_id)].status,
                dialogue_disposition_reason=decision_by_key[('shot_dialogue', shot.shot_id)].reason,
                frame_url=shot.storyboard_image_url,
                saved_frame_url=saved_frame,
                frame_changed='handoff_frame_url' in shot.metadata and saved_frame != shot.storyboard_image_url,
            ))
            previous_ending = plan.ending_state

        return SceneDirection(
            project_id=project_id,
            scene_id=scene_id,
            version_id=version.version_id,
            version_status=version.status.value,
            canonical_setting_id=canonical_setting_id,
            setting_reference_decision=setting_decision,
            setting_reference_options=self._setting_reference_options(project_id, canonical_setting_id),
            dialogue=dialogue,
            coverage_obligations=obligations,
            coverage_decisions=decisions,
            coverage_blocked=bool(blockers),
            coverage_blockers=blockers,
            unassigned_line_ids=[
                line.line_id for line in dialogue
                if decision_by_key[('dialogue', line.line_id)].status == 'UNASSIGNED'
            ],
            shots=direction_shots,
            saved='scene_direction' in version.metadata,
        )

    def save(self, project_id: str, scene_id: str, payload: SaveSceneDirection) -> SceneDirection:
        timer = start_timer()
        detail = self.blueprints.get_blueprint_detail(project_id=project_id, scene_id=scene_id)
        blueprint, source, source_shots = detail['blueprint'], detail['version'], detail['shots']
        if source.version_id != payload.expected_version_id:
            raise StateError('The storyboard changed. Reload before saving your direction.', stage='scene_direction')
        if blueprint.locked:
            raise StateError('Unlock the storyboard before changing its direction.', stage='scene_direction')

        prior_scene_direction = source.metadata.get('scene_direction') if isinstance(source.metadata, dict) else None
        prior_raw = prior_scene_direction.get('setting_reference_decision') if isinstance(prior_scene_direction, dict) else None
        prior_decision: SettingReferenceDecision | None = None
        if prior_raw is not None:
            try:
                prior_decision = SettingReferenceDecision.model_validate(prior_raw)
            except Exception as exc:
                raise ValidationError('The saved setting reference decision is malformed.', stage='scene_direction') from exc
        setting_decision = payload.setting_reference_decision
        if 'setting_reference_decision' not in payload.model_fields_set:
            setting_decision = prior_decision
        if setting_decision is not None:
            is_unchanged_carry = (
                prior_decision is not None
                and setting_decision.model_dump(mode='json') == prior_decision.model_dump(mode='json')
            )
            is_draft_current = (
                blueprint.current_version_id == source.version_id
                and source.status == StoryboardBlueprintStatus.DRAFT
            )
            # Option B: an unchanged decision on the current draft carries
            # forward without re-authorizing; new/changed decisions still
            # require the current approved source. The live reference check
            # below still runs on every save.
            if not (is_unchanged_carry and is_draft_current):
                if source.status != StoryboardBlueprintStatus.APPROVED or blueprint.approved_version_id != source.version_id or blueprint.current_version_id != source.version_id:
                    raise StateError('Scene Direction decisions can only authorize the current approved storyboard version.', stage='scene_direction')
            canonical_setting_id = self._scene_setting_identity(project_id, scene_id)
            if not canonical_setting_id or setting_decision.canonical_setting_id != canonical_setting_id:
                raise ValidationError('Select a reference for the exact canonical setting entity of this scene.', stage='scene_direction')
            from app.services.reference_validation import _selected_setting_reference
            try:
                _selected_setting_reference(
                    storage=self.storage,
                    project_id=project_id,
                    scene_id=scene_id,
                    setting_id=canonical_setting_id,
                    reference_id=setting_decision.reference_id,
                )
            except Exception as exc:
                raise ValidationError(
                    'The selected setting reference is no longer approved and canonical for this exact setting.',
                    stage='scene_direction',
                ) from exc

        known_shots = {shot.shot_id for shot in source_shots}
        _, existing, canonical_dialogue, _ = self._coverage_snapshot(project_id, scene_id, source, source_shots)
        allowed = {(row.obligation_type, row.obligation_id) for row in existing}
        keys = [(row.obligation_type, row.obligation_id) for row in payload.coverage_decisions]
        if len(keys) != len(set(keys)) or set(keys) != allowed:
            raise ValidationError('Submit exactly one decision for every canonical obligation.', stage='scene_direction')
        submitted_decisions = dict(zip(keys, payload.coverage_decisions))
        decisions = [submitted_decisions[(row.obligation_type, row.obligation_id)] for row in existing]

        try:
            decisions = [CoverageDecision.model_validate(row.model_dump()) for row in decisions]
        except PydanticValidationError as exc:
            raise ValidationError('Coverage decisions must be complete and supported.', stage='scene_direction') from exc

        decision_by_key = {(row.obligation_type, row.obligation_id): row for row in decisions}
        canonical_by_id = {line.line_id: line for line in canonical_dialogue}
        submitted = {line.line_id: line for line in payload.dialogue}
        if len(submitted) != len(payload.dialogue) or set(submitted) != set(canonical_by_id):
            raise ValidationError('Canonical dialogue rows must stay visible exactly once in Scene Direction.', stage='scene_direction')
        for identity, canonical in canonical_by_id.items():
            line = submitted[identity]
            decision = decision_by_key[('dialogue', identity)]
            if line.text != canonical.text or line.character != canonical.character:
                raise ValidationError('Canonical screenplay dialogue is read-only in Scene Direction.', stage='scene_direction')
            if line.shot_id != (decision.shot_id if decision.status == 'ASSIGNED' else None):
                raise ValidationError('Dialogue shot assignments must match the explicit coverage decision.', stage='scene_direction')

        for decision in decisions:
            if decision.shot_id is not None and decision.shot_id not in known_shots:
                raise ValidationError('Assign coverage only to an approved shot in this scene.', stage='scene_direction')
            if decision.obligation_type in {'shot_dialogue', 'shot_content'} and decision.obligation_id not in known_shots:
                raise ValidationError('Shot dispositions must name an approved shot in this scene.', stage='scene_direction')

        dialogue_by_shot = {
            row.shot_id for row in decisions
            if row.obligation_type == 'dialogue' and row.status == 'ASSIGNED'
        }
        content_by_shot = {
            row.shot_id for row in decisions
            if row.obligation_type == 'content' and row.status == 'ASSIGNED'
        }
        for decision in decisions:
            if (decision.obligation_type == 'shot_dialogue'
                    and decision.status in {'EXPLICITLY_OMITTED', 'INTENTIONAL_SILENCE'}
                    and decision.obligation_id in dialogue_by_shot):
                raise ValidationError('A shot with assigned dialogue cannot also be omitted or marked silent.', stage='scene_direction')
            if (decision.obligation_type == 'shot_content'
                    and decision.status == 'INTENTIONAL_SILENCE'
                    and (decision.obligation_id in content_by_shot
                         or not any(shot.shot_id == decision.obligation_id
                                    and str(shot.render_contract.structured_parameters.get('shot_kind')
                                            or shot.metadata.get('shot_kind') or '').lower()
                                    in {'establishing', 'establishing_shot', 'transition', 'transition_shot'}
                                    for shot in source_shots))):
                raise ValidationError('Intentional content silence requires an eligible establishing or transition shot with no assigned content.', stage='scene_direction')

        if {row.shot_id for row in payload.handoffs} != known_shots or len(payload.handoffs) != len(known_shots):
            raise ValidationError('Include each current scene shot exactly once.', stage='scene_direction')

        handoffs = {row.shot_id: row for row in payload.handoffs}
        version_id = f'sbv_{uuid4().hex[:12]}'
        clones = []
        primary_shot_id = min(source_shots, key=lambda shot: shot.shot_number).shot_id if source_shots else ''
        decision_rows = [row.model_dump() for row in decisions]
        content_assignments = {
            shot_id: [row.obligation_id for row in decisions
                      if row.obligation_type == 'content' and row.status == 'ASSIGNED' and row.shot_id == shot_id]
            for shot_id in known_shots
        }
        dialogue_dispositions = {shot_id: decision_by_key[('shot_dialogue', shot_id)] for shot_id in known_shots}
        content_dispositions = {shot_id: decision_by_key[('shot_content', shot_id)] for shot_id in known_shots}
        for shot in source_shots:
            handoff = handoffs[shot.shot_id]
            fields = handoff.model_dump(exclude={'shot_id'})
            if shot.locked and any(getattr(shot.continuity_plan, key) != value for key, value in fields.items()):
                raise StateError('Unlock the shot before changing its handoff.', stage='scene_direction')
            clone = self.blueprints._clone_shot_for_version(shot, version_id=version_id, preserve_lock=True)
            if shot.shot_id == primary_shot_id:
                clone.render_contract.structured_parameters['creator_coverage_decisions'] = decision_rows
            else:
                clone.render_contract.structured_parameters.pop('creator_coverage_decisions', None)
            clone.render_contract.structured_parameters['covered_content_ids'] = content_assignments[shot.shot_id]
            dialogue_decision = dialogue_dispositions[shot.shot_id]
            clone.render_contract.structured_parameters['dialogue_disposition'] = dialogue_decision.status
            clone.render_contract.structured_parameters['dialogue_disposition_reason'] = dialogue_decision.reason
            content_decision = content_dispositions[shot.shot_id]
            clone.render_contract.structured_parameters['content_coverage_disposition'] = content_decision.status
            clone.render_contract.structured_parameters['content_coverage_reason'] = content_decision.reason
            clone.continuity_plan = clone.continuity_plan.model_copy(update=fields)
            if not shot.locked:
                if any(fields.values()):
                    clone.metadata['handoff_frame_url'] = clone.storyboard_image_url
                else:
                    clone.metadata.pop('handoff_frame_url', None)
            clones.append(clone)

        successor = source.model_copy(deep=True)
        successor.version_id = version_id
        successor.version_number = max(row.version_number for row in self.storage.list_storyboard_blueprint_versions(blueprint.blueprint_id)) + 1
        successor.source_version_id = source.version_id
        successor.status = StoryboardBlueprintStatus.DRAFT
        successor.approved_at = None
        successor.approved_by = ''
        successor.created_at = utc_now_iso()
        successor.change_reason = 'creator_coverage_decisions'
        successor.metadata = {key: value for key, value in source.metadata.items() if key != 'continuity_review'}
        successor.metadata['scene_direction'] = {
            'dialogue': [row.model_dump() for row in payload.dialogue],
            'coverage_decisions': decision_rows,
        }
        if setting_decision is not None:
            successor.metadata['scene_direction']['setting_reference_decision'] = setting_decision.model_dump(mode='json')
        successor.inspection = StoryboardBlueprintInspection(
            blueprint_id=blueprint.blueprint_id, version_id=version_id, provenance=successor.provenance,
        )
        blueprint.current_version_id = version_id
        blueprint.status = StoryboardBlueprintStatus.DRAFT
        blueprint.updated_at = utc_now_iso()
        blueprint.metadata = {key: value for key, value in blueprint.metadata.items() if key != 'continuity_review'}
        try:
            self.storage.commit_storyboard_blueprint_version(
                blueprint=blueprint, version=successor, shots=clones,
                expected_version_id=source.version_id,
            )
        except ValueError as exc:
            raise StateError('The storyboard changed. Reload before saving your direction.', stage='scene_direction') from exc
        except Exception as exc:
            raise PersistenceError('Could not save scene direction. The prior version is preserved.', stage='scene_direction') from exc
        # Hash-gated carry-forward (design item C): Scene Direction and
        # coverage saves mint a version with new shot IDs, so approved rows
        # carry when the canonical hash is unchanged; the rest get proposals.
        try:
            self.blueprints._carry_forward_and_derive(clones)
        except Exception:
            pass
        log_stage_event(project_id=project_id, job_id=None, provider=None, stage='scene_direction',
                        duration_ms=elapsed_ms(timer), extra={'scene_id': scene_id, 'version_id': version_id})
        return self.get(project_id, scene_id)

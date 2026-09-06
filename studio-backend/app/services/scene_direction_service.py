"""Explicit, versioned dialogue placement and shot opening/ending intentions."""
from uuid import uuid4

from app.models.scene_direction import AssignedDialogue, DirectionShot, SaveSceneDirection, SceneDirection
from app.models.storyboard_blueprint import StoryboardBlueprintStatus, StoryboardBlueprintInspection, utc_now_iso
from app.services.storyboard_blueprint_service import StoryboardBlueprintService
from app.services.stability import PersistenceError, StateError, ValidationError, log_stage_event, start_timer, elapsed_ms
from app.utils.helpers import derive_scene_id_from_shot_id, derive_shot_number_from_shot_id


class SceneDirectionService:
    def __init__(self, storage=None):
        self.blueprints = StoryboardBlueprintService(storage=storage)
        self.storage = self.blueprints.storage

    @staticmethod
    def _voice_fields(row):
        return {key: str(row[key]) for key in ('character_id', 'emotional_subtext', 'pacing_tag', 'voice_style_hint') if row.get(key) is not None}

    def _dialogue(self, project_id, scene_id, version, shots):
        saved = version.metadata.get('scene_direction')
        if saved is not None:
            return [AssignedDialogue.model_validate(row) for row in saved['dialogue']]
        project = self.storage.get_project(project_id)
        project = project.model_dump() if hasattr(project, 'model_dump') else project or {}
        lines = (project.get('execution_summary') or {}).get('dialogue_lines') or []
        shot_ids = {shot.shot_id for shot in shots}
        result = []
        used = set()
        for index, line in enumerate(lines):
            if not isinstance(line, dict) or line.get('scene_id') != scene_id or not str(line.get('text') or '').strip():
                continue
            line_id = str(line.get('line_id') or f'{scene_id}_line_{index + 1}')
            if line_id in used:
                line_id = f'{line_id}_{index + 1}'
            used.add(line_id)
            requested = str(line.get('shot_id') or '')
            assigned = requested if requested in shot_ids else next((shot.shot_id for shot in shots if requested and derive_scene_id_from_shot_id(requested) == scene_id and derive_shot_number_from_shot_id(requested) == shot.shot_number), None)
            result.append(AssignedDialogue(line_id=line_id, character=str(line.get('character') or line.get('character_name') or line.get('character_id') or 'Speaker'), text=str(line['text']), shot_id=assigned, **self._voice_fields(line)))
        # Import existing per-shot dialogue too, so saving handoffs cannot erase
        # an earlier explicit audio assignment stored on the render contract.
        for shot in shots:
            explicit = shot.render_contract.structured_parameters.get('dialogue_lines')
            if not isinstance(explicit, list):
                continue
            for line in result:
                if line.shot_id == shot.shot_id:
                    line.shot_id = None
            for index, row in enumerate(explicit):
                if not isinstance(row, dict) or not str(row.get('text') or '').strip():
                    continue
                character = str(row.get('character') or row.get('character_name') or row.get('character_id') or 'Speaker')
                match = next((line for line in result if (row.get('line_id') and row['line_id'] == line.line_id) or (not row.get('line_id') and line.shot_id in {None, shot.shot_id} and line.character == character and line.text == str(row['text']))), None)
                if match:
                    match.shot_id = shot.shot_id
                    for key, value in self._voice_fields(row).items():
                        setattr(match, key, value)
                else:
                    line_id = str(row.get('line_id') or f'{shot.shot_id}_dialogue_{index + 1}')
                    if line_id in used:
                        line_id = f'{shot.shot_id}_dialogue_{index + 1}'
                    used.add(line_id)
                    result.append(AssignedDialogue(line_id=line_id, character=character, text=str(row['text']), shot_id=shot.shot_id, **self._voice_fields(row)))
        return result

    def get(self, project_id: str, scene_id: str) -> SceneDirection:
        detail = self.blueprints.get_blueprint_detail(project_id=project_id, scene_id=scene_id)
        version = detail['version']
        shots = sorted(detail['shots'], key=lambda shot: shot.shot_number)
        dialogue = self._dialogue(project_id, scene_id, version, shots)
        known = {shot.shot_id for shot in shots}
        # Deleted shots leave their lines visibly unassigned; never silently drop text.
        dialogue = [line.model_copy(update={'shot_id': line.shot_id if line.shot_id in known else None}) for line in dialogue]
        result = []
        previous = ''
        for shot in shots:
            plan = shot.continuity_plan
            saved_frame = shot.metadata.get('handoff_frame_url')
            result.append(DirectionShot(shot_id=shot.shot_id, shot_number=shot.shot_number, locked=shot.locked,
                opening_state=plan.opening_state, action_change=plan.action_change, ending_state=plan.ending_state,
                frame_url=shot.storyboard_image_url, saved_frame_url=saved_frame,
                frame_changed='handoff_frame_url' in shot.metadata and saved_frame != shot.storyboard_image_url,
                previous_ending_state=previous))
            previous = plan.ending_state
        return SceneDirection(project_id=project_id, scene_id=scene_id, version_id=version.version_id,
            version_status=version.status.value, dialogue=dialogue,
            unassigned_line_ids=[line.line_id for line in dialogue if line.shot_id is None],
            shots=result, saved='scene_direction' in version.metadata)

    def save(self, project_id: str, scene_id: str, payload: SaveSceneDirection) -> SceneDirection:
        timer = start_timer()
        detail = self.blueprints.get_blueprint_detail(project_id=project_id, scene_id=scene_id)
        blueprint, source, source_shots = detail['blueprint'], detail['version'], detail['shots']
        if source.version_id != payload.expected_version_id:
            raise StateError('The storyboard changed. Reload before saving your direction.', stage='scene_direction')
        if blueprint.locked:
            raise StateError('Unlock the storyboard before changing its direction.', stage='scene_direction')
        known = {shot.shot_id for shot in source_shots}
        if len({line.line_id for line in payload.dialogue}) != len(payload.dialogue):
            raise ValidationError('Each dialogue line needs a distinct ID.', stage='scene_direction')
        if any(line.shot_id is not None and line.shot_id not in known for line in payload.dialogue):
            raise ValidationError('Assign dialogue only to a shot in this scene.', stage='scene_direction')
        if {row.shot_id for row in payload.handoffs} != known or len(payload.handoffs) != len(known):
            raise ValidationError('Include each current scene shot exactly once.', stage='scene_direction')
        handoffs = {row.shot_id: row for row in payload.handoffs}
        original_dialogue = self._dialogue(project_id, scene_id, source, source_shots)
        version_id = f'sbv_{uuid4().hex[:12]}'
        clones = []
        for shot in source_shots:
            handoff = handoffs[shot.shot_id]
            lines = [line.model_dump() for line in payload.dialogue if line.shot_id == shot.shot_id]
            fields = handoff.model_dump(exclude={'shot_id'})
            if shot.locked and (any(getattr(shot.continuity_plan, key) != value for key, value in fields.items()) or lines != [line.model_dump() for line in original_dialogue if line.shot_id == shot.shot_id]):
                raise StateError('Unlock the shot before changing its dialogue or handoff.', stage='scene_direction')
            clone = self.blueprints._clone_shot_for_version(shot, version_id=version_id, preserve_lock=True)
            clone.continuity_plan = clone.continuity_plan.model_copy(update=fields)
            if not shot.locked:
                if any(fields.values()):
                    clone.metadata['handoff_frame_url'] = clone.storyboard_image_url
                else:
                    clone.metadata.pop('handoff_frame_url', None)
                clone.render_contract.structured_parameters['dialogue_lines'] = lines
            clones.append(clone)
        version = source.model_copy(deep=True)
        version.version_id = version_id
        version.version_number = max(v.version_number for v in self.storage.list_storyboard_blueprint_versions(blueprint.blueprint_id)) + 1
        version.source_version_id = source.version_id
        version.status = StoryboardBlueprintStatus.DRAFT
        version.approved_at = None
        version.approved_by = ''
        version.created_at = utc_now_iso()
        version.change_reason = 'creator_dialogue_and_handoff'
        version.metadata = {key: value for key, value in source.metadata.items() if key != 'continuity_review'}
        version.metadata['scene_direction'] = {'dialogue': [line.model_dump() for line in payload.dialogue]}
        version.inspection = StoryboardBlueprintInspection(blueprint_id=blueprint.blueprint_id, version_id=version_id, provenance=version.provenance)
        blueprint.current_version_id = version_id
        blueprint.status = StoryboardBlueprintStatus.DRAFT
        blueprint.updated_at = utc_now_iso()
        blueprint.metadata = {key: value for key, value in blueprint.metadata.items() if key != 'continuity_review'}
        try:
            self.storage.commit_storyboard_blueprint_version(blueprint=blueprint, version=version, shots=clones, expected_version_id=source.version_id)
        except ValueError as exc:
            raise StateError('The storyboard changed. Reload before saving your direction.', stage='scene_direction') from exc
        except Exception as exc:
            raise PersistenceError('Could not save scene direction. The prior version is preserved.', stage='scene_direction') from exc
        log_stage_event(project_id=project_id, job_id=None, provider=None, stage='scene_direction', duration_ms=elapsed_ms(timer), extra={'scene_id':scene_id,'version_id':version_id})
        return self.get(project_id, scene_id)

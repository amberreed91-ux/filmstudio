"""Read existing pixel evidence against the exact take's immutable camera plan."""
import re
from app.data.storage import get_storage
from app.models.take_camera_review import TakeCameraReview, CameraCorrectionDraft
from app.services.stability import ValidationError, StateError, PersistenceError, log_stage_event, start_timer, elapsed_ms
from app.utils.helpers import derive_scene_id_from_shot_id, derive_shot_number_from_shot_id


def clean(value):
    text = str(value or '').strip()
    # Legacy scorer prose may contain ratings. It must not leak into advisory UI.
    if re.search(r'\b(score|rating|objectively)\b|\d\s*%|\d\s*/\s*10', text, re.I):
        return ''
    return text[:4000]


class TakeCameraReviewService:
    def __init__(self, storage=None):
        self.storage = storage or get_storage('sqlite')

    def _job(self, project_id, job_id):
        job = self.storage.get_job(job_id)
        if job is None or job.project_id != project_id:
            raise ValidationError('Take not found in this project', stage='take_camera_review')
        if job.status != 'complete' or not str(getattr(job.output_payload, 'asset_url', '') or '').strip():
            raise StateError('This take has no completed video', stage='take_camera_review')
        return job

    def review(self, project_id: str, job_id: str) -> TakeCameraReview:
        timer = start_timer()
        job = self._job(project_id, job_id)
        params = job.input_payload.parameters or {}
        shot = self.storage.get_storyboard_shot(params.get('storyboard_shot_id')) if params.get('storyboard_shot_id') else None
        if shot and (shot.project_id != project_id or shot.scene_id != derive_scene_id_from_shot_id(job.shot_id) or shot.shot_number != derive_shot_number_from_shot_id(job.shot_id)):
            shot = None
        expected = clean((params.get('creator_shot_planning') or {}).get('camera') or (params.get('camera_plan') or {}).get('camera') or (params.get('shot_planning') or {}).get('camera') or (shot.visual_plan.camera_movement if shot else ''))
        result = TakeCameraReview(job_id=job.id, scene_id=derive_scene_id_from_shot_id(job.shot_id), shot_number=derive_shot_number_from_shot_id(job.shot_id), frame_url=shot.storyboard_image_url if shot else None, expected_camera=expected, correction=expected)
        try:
            attempts = self.storage.list_render_attempts(project_id=project_id, shot_id=job.shot_id, limit=-1)
        except Exception as exc:
            raise PersistenceError('Could not load the visual review', stage='take_camera_review') from exc
        attempt = next((a for a in attempts if a.get('job_id') == job_id), None)
        score = (attempt or {}).get('score_json') or {}
        if not isinstance(score, dict):
            score = {}
        camera = (score.get('dimensions') or {}).get('camera') or {}
        # An analysis of another prompt, unsupported fallback, or a single frame
        # cannot establish a camera mismatch for this take.
        normalize = lambda value: ' '.join(str(value or '').lower().split())
        valid = (expected and normalize(camera.get('expected')) == normalize(expected)
                 and score.get('scored_by_provider') and score.get('scored_by_model')
                 and len(score.get('frames_scored') or []) >= 3
                 and 'camera' not in (score.get('unscored_dimensions') or [])
                 and clean(camera.get('observed')) and clean(camera.get('evidence')))
        if valid:
            result.observed = clean(camera.get('observed'))
            result.evidence = clean(camera.get('evidence'))
            if 'camera' in (score.get('failed_slots') or []):
                result.status = 'possible_mismatch'
                result.message = 'The sampled frames suggest a camera mismatch. Watch the full take before deciding.'
            else:
                result.status = 'no_mismatch_reported'
                result.message = 'The sampled frames did not flag a camera mismatch. They cannot confirm the full movement.'
        log_stage_event(project_id=project_id, job_id=job_id, provider=None, stage='take_camera_review', duration_ms=elapsed_ms(timer))
        return result

    def correction(self, project_id: str, job_id: str, correction: str) -> CameraCorrectionDraft:
        job = self._job(project_id, job_id)
        correction = correction.strip()
        if not correction or len(correction) > 4000:
            raise ValidationError('Enter the camera correction', stage='take_camera_correction')
        original = str(job.input_payload.prompt or '').strip()
        if not original:
            raise StateError('The source take has no saved prompt', stage='take_camera_correction')
        log_stage_event(project_id=project_id, job_id=job_id, provider=None, stage='take_camera_correction', duration_ms=0)
        return CameraCorrectionDraft(job_id=job_id, prompt=original + '\n\n[Camera revision for the next take]\n' + correction + '\nPreserve the other scene, character, action, and lighting directions above.')

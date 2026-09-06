from __future__ import annotations

from app.data.storage import get_storage
from app.models.take_selection import SceneTakeChoices, TakeChoice
from app.services.stability import StateError, ValidationError, PersistenceError, log_stage_event, start_timer, elapsed_ms
from app.utils.helpers import derive_scene_id_from_shot_id, derive_shot_number_from_shot_id


class TakeSelectionService:
    def __init__(self, storage=None):
        self._storage = storage

    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    def choices(self, project_id: str, scene_id: str) -> SceneTakeChoices:
        return SceneTakeChoices(project_id=project_id, scene_id=scene_id, choices=[
            TakeChoice(shot_number=row["shot_number"], job_id=row["job_id"])
            for row in self.storage.list_take_choices(project_id, scene_id)
        ])

    def choose(self, project_id: str, scene_id: str, shot_number: int, job_id: str | None) -> SceneTakeChoices:
        timer = start_timer()
        if shot_number < 1:
            raise ValidationError("Shot number must be positive", stage="take_selection")
        if job_id is not None:
            self._validate(self.storage.get_job(job_id), project_id, scene_id, shot_number)
        try:
            self.storage.save_take_choice(project_id, scene_id, shot_number, job_id)
        except Exception as exc:
            raise PersistenceError("Could not save the take choice", stage="take_selection") from exc
        log_stage_event(project_id=project_id, job_id=job_id, provider=None, stage="take_selection", duration_ms=elapsed_ms(timer), extra={"scene_id": scene_id, "shot_number": shot_number})
        return self.choices(project_id, scene_id)

    @staticmethod
    def _validate(job, project_id, scene_id, shot_number):
        if (job is None or job.project_id != project_id
                or derive_scene_id_from_shot_id(job.shot_id) != scene_id
                or derive_shot_number_from_shot_id(job.shot_id) != shot_number):
            raise ValidationError("This take does not belong to this project and shot", stage="take_selection")
        if job.status != "complete" or not str(getattr(job.output_payload, "asset_url", "") or "").strip():
            raise StateError("The chosen take has no completed video. Choose an available take.", stage="take_selection")

    def resolve(self, project_id: str, scene_id: str):
        # Unchosen shots preserve legacy latest-take behavior. An explicit choice
        # is loaded by ID, independently of render recency. Delivery examines the complete project
        # job history rather than silently dropping shots beyond a UI page.
        latest = {}
        expected = set()
        for job in self.storage.list_jobs(project_id=project_id, limit=-1):
            number = derive_shot_number_from_shot_id(job.shot_id)
            if job.project_id != project_id or derive_scene_id_from_shot_id(job.shot_id) != scene_id or number < 1:
                continue
            expected.add(number)
            if job.status != "complete" or not str(getattr(job.output_payload, "asset_url", "") or "").strip():
                continue
            if number not in latest or (str(job.created_at), job.id) > (str(latest[number].created_at), latest[number].id):
                latest[number] = job
        for choice in self.choices(project_id, scene_id).choices:
            if choice.job_id is not None:
                job = self.storage.get_job(choice.job_id)
                self._validate(job, project_id, scene_id, choice.shot_number)
                latest[choice.shot_number] = job
        missing = sorted(expected - latest.keys())
        if missing:
            raise StateError("Some shots have no completed take. Finish or remove those shots before assembly.", stage="take_selection", metadata={"scene_id": scene_id, "shot_numbers": missing})
        return sorted(latest.items())

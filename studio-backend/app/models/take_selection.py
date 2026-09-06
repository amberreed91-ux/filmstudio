from pydantic import BaseModel, Field


class TakeChoiceRequest(BaseModel):
    job_id: str | None = Field(default=None, min_length=1)


class TakeChoice(BaseModel):
    shot_number: int
    job_id: str | None


class SceneTakeChoices(BaseModel):
    project_id: str
    scene_id: str
    choices: list[TakeChoice]

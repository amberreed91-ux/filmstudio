from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TakeCameraReview(BaseModel):
    job_id: str
    scene_id: str
    shot_number: int
    frame_url: str | None = None
    expected_camera: str = ''
    status: Literal['needs_judgment', 'possible_mismatch', 'no_mismatch_reported'] = 'needs_judgment'
    observed: str = ''
    evidence: str = ''
    correction: str = ''
    message: str = 'Review the camera movement yourself; there is not enough visual evidence for a note.'


class CameraCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    correction: str = Field(min_length=1, max_length=4000)


class CameraCorrectionDraft(BaseModel):
    job_id: str
    prompt: str

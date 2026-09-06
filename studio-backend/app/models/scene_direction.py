from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssignedDialogue(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_id: str = Field(min_length=1, max_length=150)
    character: str = Field(min_length=1, max_length=150)
    text: str = Field(min_length=1, max_length=4000)
    shot_id: str | None = None
    character_id: str = Field(default='', max_length=150)
    emotional_subtext: str = Field(default='', max_length=1500)
    pacing_tag: str = Field(default='', max_length=150)
    voice_style_hint: str = Field(default='', max_length=1500)

    @field_validator('line_id', 'character', 'text')
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Enter a non-empty value')
        return value.strip()


class ShotHandoff(BaseModel):
    model_config = ConfigDict(extra='forbid')
    shot_id: str
    opening_state: str = Field(default='', max_length=1500)
    action_change: str = Field(default='', max_length=1500)
    ending_state: str = Field(default='', max_length=1500)


class SaveSceneDirection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version_id: str
    dialogue: list[AssignedDialogue] = Field(max_length=300)
    handoffs: list[ShotHandoff] = Field(max_length=100)


class DirectionShot(ShotHandoff):
    shot_number: int
    locked: bool
    frame_url: str | None = None
    saved_frame_url: str | None = None
    frame_changed: bool = False
    previous_ending_state: str = ''


class SceneDirection(BaseModel):
    project_id: str
    scene_id: str
    version_id: str
    version_status: str
    dialogue: list[AssignedDialogue]
    unassigned_line_ids: list[str]
    shots: list[DirectionShot]
    saved: bool

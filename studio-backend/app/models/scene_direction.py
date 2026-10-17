from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CoverageStatus = Literal['UNASSIGNED', 'ASSIGNED', 'EXPLICITLY_OMITTED', 'INTENTIONAL_SILENCE']


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


class CoverageDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    obligation_type: Literal['content', 'dialogue', 'shot_dialogue', 'shot_content']
    obligation_id: str = Field(min_length=1, max_length=200)
    status: CoverageStatus
    shot_id: str | None = None
    reason: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def validate_decision(self):
        if self.obligation_type in {'content', 'dialogue'} and self.status == 'INTENTIONAL_SILENCE':
            raise ValueError('Canonical content and spoken dialogue cannot be marked as intentional silence')
        if self.obligation_type == 'shot_content' and self.status not in {'UNASSIGNED', 'INTENTIONAL_SILENCE'}:
            raise ValueError('A shot content disposition must be unassigned or an explicit establishing-shot silence')
        if self.obligation_type == 'shot_dialogue' and self.status not in {'UNASSIGNED', 'EXPLICITLY_OMITTED', 'INTENTIONAL_SILENCE'}:
            raise ValueError('A shot dialogue disposition must be unassigned, omitted, or intentional silence')
        if self.status == 'ASSIGNED' and self.obligation_type != 'shot_dialogue' and not self.shot_id:
            raise ValueError('A shot assignment requires one approved shot')
        if self.status != 'ASSIGNED' and self.shot_id is not None:
            raise ValueError('Only an assigned decision may name a shot')
        if self.status in {'EXPLICITLY_OMITTED', 'INTENTIONAL_SILENCE'} and not self.reason.strip():
            raise ValueError('An explicit omission or silence decision requires a creator reason')
        if self.obligation_type in {'shot_dialogue', 'shot_content'} and self.shot_id is not None:
            raise ValueError('A shot disposition is scoped by its obligation ID')
        return self


class CoverageObligation(BaseModel):
    obligation_type: Literal['content', 'dialogue']
    obligation_id: str
    source_text: str
    source_speaker: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    status: CoverageStatus
    shot_id: str | None = None
    reason: str = ''
    reason_required: bool = False

    @model_validator(mode='after')
    def validate_obligation_decision(self):
        if self.status == 'INTENTIONAL_SILENCE':
            raise ValueError('Canonical content and dialogue obligations cannot be marked as intentional silence')
        if self.status == 'ASSIGNED' and not self.shot_id:
            raise ValueError('An assigned canonical obligation requires one approved shot')
        if self.status != 'ASSIGNED' and self.shot_id is not None:
            raise ValueError('Only an assigned canonical obligation may name a shot')
        if self.status == 'EXPLICITLY_OMITTED' and (not self.reason.strip() or not self.reason_required):
            raise ValueError('An omitted canonical obligation requires a creator reason')
        return self


class ShotHandoff(BaseModel):
    model_config = ConfigDict(extra='forbid')
    shot_id: str
    opening_state: str = Field(default='', max_length=1500)
    action_change: str = Field(default='', max_length=1500)
    ending_state: str = Field(default='', max_length=1500)


class SettingReferenceDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    canonical_setting_id: str = Field(min_length=1, max_length=256, strict=True)
    reference_id: str = Field(min_length=1, max_length=256, strict=True)

    @field_validator('canonical_setting_id', 'reference_id')
    @classmethod
    def non_blank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('An explicit non-empty identity is required')
        return value.strip()


class SettingReferenceOption(BaseModel):
    ref_id: str
    image_url: str
    target_type: str
    target_id: str
    kind: str
    approval_state: str
    canonical: bool


class SaveSceneDirection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version_id: str = Field(min_length=1, strict=True)
    dialogue: list[AssignedDialogue]
    handoffs: list[ShotHandoff] = Field(max_length=100)
    coverage_decisions: list[CoverageDecision] = Field(max_length=1000)
    setting_reference_decision: SettingReferenceDecision | None = None

    @field_validator('expected_version_id')
    @classmethod
    def non_blank_expected_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('expected_version_id is required')
        return value.strip()


class DirectionShot(ShotHandoff):
    shot_number: int
    locked: bool
    frame_url: str | None = None
    saved_frame_url: str | None = None
    frame_changed: bool = False
    previous_ending_state: str = ''
    shot_kind: str = ''
    dialogue_disposition: CoverageStatus = 'UNASSIGNED'
    dialogue_disposition_reason: str = ''


class SceneDirection(BaseModel):
    project_id: str
    scene_id: str
    version_id: str
    version_status: str
    canonical_setting_id: str | None = None
    setting_reference_decision: SettingReferenceDecision | None = None
    setting_reference_options: list[SettingReferenceOption] = Field(default_factory=list)
    dialogue: list[AssignedDialogue]
    coverage_obligations: list[CoverageObligation] = Field(default_factory=list)
    coverage_decisions: list[CoverageDecision] = Field(default_factory=list)
    coverage_blocked: bool = True
    coverage_blockers: list[str] = Field(default_factory=list)
    unassigned_line_ids: list[str]
    shots: list[DirectionShot]
    saved: bool

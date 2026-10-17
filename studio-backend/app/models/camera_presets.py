"""Provider-neutral camera planning catalog contracts."""
from pydantic import BaseModel, Field


class CameraPreset(BaseModel):
    id: str
    label: str
    category: str
    description: str
    camera: str
    framing: str = ''


class CameraView(BaseModel):
    id: str
    label: str
    camera: str


class CameraFraming(BaseModel):
    id: str
    label: str
    framing: str


class CameraLens(BaseModel):
    """A named lens personality the creator can attach to a shot."""
    id: str
    label: str
    category: str
    description: str
    lens_language: str


class CameraFocalLength(BaseModel):
    """A specific focal length available for the chosen lens."""
    id: str
    label: str
    mm: int
    framing_hint: str


class CameraAperture(BaseModel):
    """An f-stop selection that controls depth of field."""
    id: str
    label: str
    f_stop: str
    depth_hint: str


class CameraPresetCatalog(BaseModel):
    presets: list[CameraPreset] = Field(default_factory=list)
    views: list[CameraView] = Field(default_factory=list)
    framings: list[CameraFraming] = Field(default_factory=list)
    lenses: list[CameraLens] = Field(default_factory=list)
    focal_lengths: list[CameraFocalLength] = Field(default_factory=list)
    apertures: list[CameraAperture] = Field(default_factory=list)


class StoryboardCameraPlan(BaseModel):
    """Explicit camera edits submitted with a new storyboard frame."""
    model_config = {'extra': 'forbid'}
    camera: str | None = Field(default=None, max_length=4000)
    framing: str | None = Field(default=None, max_length=4000)
    lens: str | None = Field(default=None, max_length=200)
    focal_length: str | None = Field(default=None, max_length=20)
    aperture: str | None = Field(default=None, max_length=20)


class CameraShotRecommendationRequest(BaseModel):
    """Scene context for a shot-aware camera suggestion."""

    model_config = {'extra': 'ignore'}
    scene: dict = Field(default_factory=dict)
    shot_number: int = Field(default=1, ge=1)
    total_shots: int | None = Field(default=None, ge=1)


class CameraSceneRecommendationsRequest(BaseModel):
    """Scene context for suggesting a camera package per shot."""

    model_config = {'extra': 'ignore'}
    scene: dict = Field(default_factory=dict)
    total_shots: int = Field(default=3, ge=1, le=12)


class CameraShotRecommendation(BaseModel):
    """One advisory camera package. Suggestion only — never auto-applied."""

    preset_id: str
    preset_label: str
    view_id: str
    framing_id: str
    lens_id: str
    focal_length_id: str
    aperture_id: str
    camera: str
    framing: str
    lens_language: str
    focal_length: str
    aperture: str
    shot_label: str
    why: str


class CameraSceneRecommendations(BaseModel):
    """Advisory packages for every shot. Suggestions only — never applied."""

    total_shots: int
    recommendations: list[CameraShotRecommendation]

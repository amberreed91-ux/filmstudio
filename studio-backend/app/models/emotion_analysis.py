from pydantic import BaseModel


class AudienceMetricGroup(BaseModel):
    engagement: int
    tension: int
    emotional_impact: int


class EmotionAnalysisResponse(BaseModel):
    scene_id: str
    general: AudienceMetricGroup
    cinephile: AudienceMetricGroup
    genre_fan: AudienceMetricGroup


class EmotionAnalysisRequest(BaseModel):
    confirmed: bool = False
    force: bool = False


class EmotionAnalysisEnvelope(BaseModel):
    analysis_id: str
    project_id: str
    scene_id: str
    context_hash: str
    provider: str
    model: str
    cached: bool
    provider_call: bool
    created_at: str
    updated_at: str
    analysis: EmotionAnalysisResponse

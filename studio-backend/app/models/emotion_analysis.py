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

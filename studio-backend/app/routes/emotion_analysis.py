from fastapi import APIRouter, Depends, HTTPException

from app.models.emotion_analysis import EmotionAnalysisEnvelope, EmotionAnalysisRequest
from app.services.emotion_analysis_service import EmotionAnalysisService, emotion_analysis_service
from app.services.stability import PersistenceError, ProviderError, StabilityError, StateError, ValidationError

router = APIRouter(prefix="/api/f51/studio/emotion-analysis", tags=["emotion-analysis"])


def get_emotion_analysis_service() -> EmotionAnalysisService:
    return emotion_analysis_service


def _http_error(exc: StabilityError) -> HTTPException:
    if isinstance(exc, ValidationError):
        status = 422
    elif isinstance(exc, StateError):
        status = 404
    elif isinstance(exc, ProviderError):
        status = 502
    elif isinstance(exc, PersistenceError):
        status = 503
    else:
        status = 500
    return HTTPException(status_code=status, detail=exc.to_dict())


@router.get(
    "/projects/{project_id}/scenes/{scene_id}",
    response_model=EmotionAnalysisEnvelope,
)
async def get_cached_scene_emotion(
    project_id: str,
    scene_id: str,
    service: EmotionAnalysisService = Depends(get_emotion_analysis_service),
):
    """Return the current cached result without invoking an external provider."""
    try:
        return service.get_cached_scene(project_id, scene_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/projects/{project_id}/scenes/{scene_id}/analyze",
    response_model=EmotionAnalysisEnvelope,
)
async def analyze_scene_emotion(
    project_id: str,
    scene_id: str,
    request: EmotionAnalysisRequest,
    service: EmotionAnalysisService = Depends(get_emotion_analysis_service),
):
    """Run creator-confirmed analysis for one scene, reusing a current cached result."""
    try:
        return await service.analyze_scene(
            project_id,
            scene_id,
            confirmed=request.confirmed,
            force=request.force,
        )
    except StabilityError as exc:
        raise _http_error(exc) from exc

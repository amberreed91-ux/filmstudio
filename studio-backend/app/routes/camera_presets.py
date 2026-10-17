from fastapi import APIRouter, Depends
from app.models.camera_presets import (
    CameraPresetCatalog,
    CameraSceneRecommendations,
    CameraSceneRecommendationsRequest,
    CameraShotRecommendation,
    CameraShotRecommendationRequest,
)
from app.services.camera_preset_service import CameraPresetService


router = APIRouter(prefix='/api/camera-presets', tags=['camera-planning'])


def get_service() -> CameraPresetService:
    return CameraPresetService()


@router.get('', response_model=CameraPresetCatalog)
async def get_camera_presets(service: CameraPresetService = Depends(get_service)):
    return service.catalog()


@router.post('/recommend', response_model=CameraShotRecommendation)
async def recommend_camera_for_shot(
    request: CameraShotRecommendationRequest,
    service: CameraPresetService = Depends(get_service),
):
    """Advisory camera package for one shot. Suggestion only — never applied."""
    return service.recommend_for_shot(
        request.scene,
        request.shot_number,
        request.total_shots,
    )


@router.post('/recommend-all', response_model=CameraSceneRecommendations)
async def recommend_cameras_for_scene(
    request: CameraSceneRecommendationsRequest,
    service: CameraPresetService = Depends(get_service),
):
    """Advisory package per shot. Suggestions only — never applied."""
    return service.recommend_for_scene(request.scene, request.total_shots)

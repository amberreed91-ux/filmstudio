from fastapi import APIRouter, Depends, HTTPException
from app.models.take_camera_review import TakeCameraReview, CameraCorrectionRequest, CameraCorrectionDraft
from app.services.take_camera_review_service import TakeCameraReviewService
from app.services.stability import StabilityError

router = APIRouter(prefix='/api/f51/studio/projects', tags=['take-camera-review'])


def get_service():
    return TakeCameraReviewService()


def error(exc):
    return HTTPException(status_code=422 if exc.error_type == 'validation_error' else 409 if exc.error_type == 'state_error' else 503, detail=exc.to_dict())


@router.get('/{project_id}/takes/{job_id}/camera-review', response_model=TakeCameraReview)
async def review(project_id: str, job_id: str, service=Depends(get_service)):
    try:
        return service.review(project_id, job_id)
    except StabilityError as exc:
        raise error(exc) from exc


@router.post('/{project_id}/takes/{job_id}/camera-correction', response_model=CameraCorrectionDraft)
async def correction(project_id: str, job_id: str, payload: CameraCorrectionRequest, service=Depends(get_service)):
    try:
        return service.correction(project_id, job_id, payload.correction)
    except StabilityError as exc:
        raise error(exc) from exc

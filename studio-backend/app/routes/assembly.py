"""Film delivery HTTP contracts. Assembly and persistence belong to services."""
from fastapi import APIRouter, Depends, HTTPException

from app.models.film_delivery import AssemblyStatusResponse, AssembleFilmResponse
from app.services.film_delivery_service import FilmDeliveryService
from app.services.stability import StabilityError

router = APIRouter(prefix="/api/f51/studio/projects")


def get_film_delivery_service() -> FilmDeliveryService:
    return FilmDeliveryService()


def _http_error(exc: StabilityError) -> HTTPException:
    return HTTPException(status_code=409 if exc.error_type == "state_error" else 500, detail=exc.to_dict())


@router.post("/{project_id}/assemble-film", response_model=AssembleFilmResponse)
async def assemble_film_endpoint(project_id: str, service: FilmDeliveryService = Depends(get_film_delivery_service)):
    try:
        return await service.assemble(project_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc


@router.get("/{project_id}/assembly-status", response_model=AssemblyStatusResponse)
async def get_assembly_status(project_id: str, service: FilmDeliveryService = Depends(get_film_delivery_service)):
    try:
        return service.status(project_id)
    except StabilityError as exc:
        raise _http_error(exc) from exc

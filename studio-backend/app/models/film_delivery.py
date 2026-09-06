from typing import Literal

from pydantic import BaseModel


class AssemblyStatusResponse(BaseModel):
    scenes_with_compositions: int
    scenes_total: int
    film_assembled: bool
    film_url: str | None
    has_audio: bool
    film_outdated: bool = False
    scenes_needing_assembly: list[str] = []


class AssembleFilmResponse(BaseModel):
    film_url: str
    scene_count: int
    total_duration_seconds: float | None
    has_audio: bool


class CutFreshness(BaseModel):
    status: Literal["current", "outdated", "unverified"]
    reason: str

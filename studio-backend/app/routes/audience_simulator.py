from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from app.models.audience_simulator import SceneAudienceSimulation, ProjectAudienceSimulation
from app.services.audience_simulator_service import audience_simulator_service

router = APIRouter(prefix="/api/f51/studio/audience-simulator", tags=["audience-simulator"])

@router.post("/projects/{project_id}/scenes/{scene_id}/simulate", response_model=SceneAudienceSimulation)
async def simulate_scene_audience(project_id: str, scene_id: str):
    """Simulate audience reactions for a single scene."""
    try:
        return await audience_simulator_service.simulate_scene(project_id, scene_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")

@router.post("/projects/{project_id}/simulate", response_model=ProjectAudienceSimulation)
async def simulate_project_audience(project_id: str):
    """Simulate audience reactions for the entire project sequence."""
    try:
        return await audience_simulator_service.simulate_project(project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")

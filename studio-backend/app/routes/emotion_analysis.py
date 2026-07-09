from fastapi import APIRouter, HTTPException

from app.models.emotion_analysis import EmotionAnalysisResponse
from app.services.emotion_analysis_service import emotion_analysis_service
from app.services.project_store import project_store

router = APIRouter(prefix="/api/f51/studio/emotion-analysis", tags=["emotion-analysis"])


@router.post(
    "/projects/{project_id}/scenes/{scene_id}/analyze",
    response_model=EmotionAnalysisResponse,
)
async def analyze_scene_emotion(project_id: str, scene_id: str):
    """Analyze a scene's emotional impact on different audience types via Groq."""
    try:
        project = project_store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        summary = project.get("execution_summary") or {}
        scenes = summary.get("scenes") or []
        total = len(scenes)
        scene_index = 1
        for i, s in enumerate(scenes):
            if str(s.get("scene_id")) == scene_id:
                scene_index = i + 1
                break

        result = await emotion_analysis_service.analyze_scene(
            project_id, scene_id, scene_index, total
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

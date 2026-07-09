from fastapi import APIRouter, HTTPException
from datetime import datetime

router = APIRouter()

PROJECTS = {
    "proj-001": {
        "project_id": "proj-001",
        "title": "AI Film Project",
        "updated_at": datetime.now().isoformat(),
        "source_stats": {"images": 10, "documents": 3, "assets": 5},
        "render_provider": "sora",
        "production_bible": {},
        "render_provider_integrations": [],
        "crew_agents": [],
        "shot_approval_gates": [],
        "storyboard_wall": [],
        "render_queue": [],
        "rights_safety_clearance_board": [],
        "reference_study_library": [],
        "interactive_modules": [],
        "producer_dashboard": {},
        "project_dashboard": {},
        "agent_activity_timeline": [],
        "continuity_register": [],
        "risk_register": [],
        "next_actions": []
    }
}

@router.get("/projects/{project_id}")
def get_project(project_id: str):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")

    return PROJECTS[project_id]

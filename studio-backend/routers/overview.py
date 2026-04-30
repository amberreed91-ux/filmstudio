from fastapi import APIRouter
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

@router.get("/overview")
def get_overview():
    projects_list = list(PROJECTS.values())

    return {
        "build": {
            "name": "studio-backend",
            "version": "1.0.0",
            "status": "healthy"
        },
        "projects": projects_list,
        "latest_project": projects_list[0] if projects_list else None
    }

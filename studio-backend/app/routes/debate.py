from fastapi import APIRouter, HTTPException
from app.models.debate import CoDirectorDebate, DebateRoundRequest, DebateActionRequest
from app.services.debate_service import debate_service
from app.services.director_memory_service import director_memory_service

router = APIRouter(prefix="/api/f51/studio/debate", tags=["debate"])

@router.post("/trigger")
def trigger_debate(request: DebateRoundRequest):
    """Trigger a new debate round based on a filmmaker's decision."""
    try:
        debate = debate_service.generate_debate(request)
        return {"debate": debate}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/action")
def debate_action(request: DebateActionRequest):
    """Dismiss or save a debate."""
    updates = {}
    if request.action == "dismiss":
        updates["is_dismissed"] = True
    elif request.action == "save":
        updates["is_saved"] = True
        
        # Also save to Director's Notes as requested
        debate = director_memory_service.get_memory(request.project_id).get("debates", [])
        debate_entry = next((d for d in debate if d.get("debate_id") == request.debate_id), None)
        if debate_entry:
            director_memory_service.save_entry(
                request.project_id,
                "notes",
                {
                    "headline": f"Co-Director Debate: {debate_entry.get('query')}",
                    "note": f"Synthesis: {debate_entry.get('synthesis')}\n\nAgreements: {', '.join(debate_entry.get('points_of_agreement', []))}\nConflicts: {', '.join(debate_entry.get('points_of_conflict', []))}",
                    "keyword": "debate"
                }
            )
    
    updated = director_memory_service.update_entry(
        request.project_id, 
        "debates", 
        request.debate_id, 
        updates
    )
    
    if updated is None:
        raise HTTPException(status_code=404, detail="Debate not found")
        
    return {"debate": updated}

@router.get("/{project_id}")
def list_debates(project_id: str):
    """List all debates for a project."""
    debates = director_memory_service.list_entries(project_id, "debates")
    return {"debates": debates}

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class AgentResponse(BaseModel):
    agent_name: str
    perspective: str
    position: str
    reasoning: str
    recommendation: str

class CoDirectorDebate(BaseModel):
    debate_id: str
    project_id: str
    scene_id: Optional[str] = None
    act_number: Optional[int] = None
    is_full_project: bool = False
    query: str
    agent_responses: List[AgentResponse]
    points_of_agreement: List[str]
    points_of_conflict: List[str]
    synthesis: str
    filmmaker_prerogative: str
    is_dismissed: bool = False
    is_saved: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

class DebateRoundRequest(BaseModel):
    project_id: str
    scene_id: Optional[str] = None
    act_number: Optional[int] = None
    is_full_project: bool = False
    query: str

class DebateActionRequest(BaseModel):
    project_id: str
    debate_id: str
    action: str  # dismiss, save

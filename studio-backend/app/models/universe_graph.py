from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class UniverseNode(BaseModel):
    node_id: str
    project_id: str
    node_type: str  # character, location, object, lore
    name: str
    description: str = ""
    first_scene: Optional[str] = None
    last_scene: Optional[str] = None
    universe_tags: List[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    connected_nodes: List[str] = [] # Transient, populated during retrieval

class UniverseRelationship(BaseModel):
    relationship_id: str
    project_id: str
    from_node: str
    to_node: str
    relationship_type: str
    description: str = ""
    created_at: Optional[str] = None

class UniverseGraph(BaseModel):
    project_id: str
    nodes: List[UniverseNode]
    relationships: List[UniverseRelationship]

class AbsenceReport(BaseModel):
    project_id: str
    absences: List[Dict[str, Any]] # {node_id, name, type, last_seen_scene, advisory}

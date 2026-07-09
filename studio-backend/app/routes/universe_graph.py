from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
from app.models.universe_graph import UniverseNode, UniverseRelationship, UniverseGraph, AbsenceReport
from app.services.universe_graph_service import universe_graph_service

router = APIRouter(prefix="/projects/{project_id}/universe-graph", tags=["Universe Graph"])

@router.get("", response_model=UniverseGraph)
async def get_universe_graph(project_id: str):
    return await universe_graph_service.get_graph(project_id)

@router.post("/nodes", response_model=bool)
async def save_node(project_id: str, node: UniverseNode):
    return universe_graph_service.save_node(project_id, node)

@router.delete("/nodes/{node_id}", response_model=bool)
async def delete_node(project_id: str, node_id: str):
    return universe_graph_service.delete_node(node_id)

@router.post("/relationships", response_model=bool)
async def save_relationship(project_id: str, rel: UniverseRelationship):
    return universe_graph_service.save_relationship(project_id, rel)

@router.delete("/relationships/{relationship_id}", response_model=bool)
async def delete_relationship(project_id: str, relationship_id: str):
    return universe_graph_service.delete_relationship(relationship_id)

@router.get("/absences", response_model=AbsenceReport)
async def get_absences(project_id: str):
    return await universe_graph_service.detect_absences(project_id)

@router.get("/export", response_model=str)
async def export_universe_bible(project_id: str):
    return await universe_graph_service.export_bible(project_id)

@router.post("/auto-populate", response_model=UniverseGraph)
async def force_auto_populate(project_id: str):
    return await universe_graph_service.auto_populate(project_id)

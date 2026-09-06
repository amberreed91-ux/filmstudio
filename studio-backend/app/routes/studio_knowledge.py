from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.models.studio_knowledge import (
    KnowledgeBibleCreateRequest,
    KnowledgeBibleResponse,
    KnowledgeConflictAcknowledgeRequest,
    KnowledgeContextPack,
    KnowledgeContextRequest,
    KnowledgeRebuildRequest,
    KnowledgeRebuildRun,
)
from app.services.stability import PersistenceError, StateError, ValidationError
from app.services.studio_knowledge_service import studio_knowledge_service


router = APIRouter(prefix="/api/projects", tags=["studio-knowledge"])


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=exc.message)
    if isinstance(exc, StateError):
        status = 404 if "not found" in exc.message.lower() else 409
        return HTTPException(status_code=status, detail=exc.message)
    if isinstance(exc, PersistenceError):
        return HTTPException(status_code=500, detail=exc.message)
    return HTTPException(status_code=500, detail="Internal server error")


@router.post("/{project_id}/knowledge/bibles", response_model=KnowledgeBibleResponse)
def register_knowledge_bible(project_id: str, request: KnowledgeBibleCreateRequest):
    try:
        return studio_knowledge_service.register_bible(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/knowledge/bibles/upload", response_model=KnowledgeBibleResponse)
async def upload_knowledge_bible(
    project_id: str,
    file: UploadFile = File(...),
    title: str = Form(""),
    bible_type: str = Form("general"),
):
    filename = (file.filename or "").strip()
    lower_filename = filename.lower()
    if not lower_filename.endswith((".md", ".markdown")):
        raise HTTPException(status_code=400, detail="Only .md or .markdown Bible files are accepted")

    try:
        raw_content = await file.read()
        content = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Bible file must be UTF-8 encoded Markdown") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read Bible file: {exc}") from exc

    display_title = (title or "").strip() or filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
    request = KnowledgeBibleCreateRequest(
        title=display_title or "Uploaded Bible",
        bible_type=(bible_type or "general").strip() or "general",
        content=content,
        content_type="markdown",
        source_filename=filename,
        metadata={"ingest_mode": "markdown_upload"},
    )
    try:
        return studio_knowledge_service.register_bible(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/knowledge/bibles")
def list_knowledge_bibles(
    project_id: str,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    bibles = studio_knowledge_service.list_bibles(project_id, status=status, limit=limit)
    return {"bibles": [bible.model_dump(mode="json") for bible in bibles]}


@router.get("/{project_id}/knowledge/bibles/{bible_id}", response_model=KnowledgeBibleResponse)
def get_knowledge_bible(project_id: str, bible_id: str):
    try:
        return studio_knowledge_service.get_bible_response(project_id, bible_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/knowledge/bibles/{bible_id}/parse", response_model=KnowledgeBibleResponse)
def parse_knowledge_bible(project_id: str, bible_id: str):
    try:
        studio_knowledge_service.parse_bible_sections(bible_id)
        studio_knowledge_service.atomize_bible(bible_id)
        return studio_knowledge_service.get_bible_response(project_id, bible_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{project_id}/knowledge/rebuild", response_model=KnowledgeRebuildRun)
def rebuild_knowledge_index(project_id: str, request: KnowledgeRebuildRequest):
    try:
        return studio_knowledge_service.build_index(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/knowledge/rebuilds")
def list_knowledge_rebuilds(project_id: str, limit: int = Query(25, ge=1, le=100)):
    runs = studio_knowledge_service.list_rebuild_runs(project_id, limit=limit)
    return {"rebuilds": [run.model_dump(mode="json") for run in runs]}


@router.get("/{project_id}/knowledge/rebuilds/{run_id}")
def get_knowledge_rebuild(project_id: str, run_id: str):
    try:
        run = studio_knowledge_service.get_rebuild_run(project_id, run_id)
        return {"rebuild": run.model_dump(mode="json")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/knowledge/atoms")
def list_knowledge_atoms(
    project_id: str,
    source_type: str | None = None,
    atom_type: str | None = None,
    authority_level: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    department: str | None = None,
    status: str | None = "active",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    atoms = studio_knowledge_service.list_atoms(
        project_id,
        filters={
            "source_type": source_type,
            "atom_type": atom_type,
            "authority_level": authority_level,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "department": department,
            "status": status,
        },
        limit=limit,
        offset=offset,
    )
    return {"atoms": [atom.model_dump(mode="json") for atom in atoms]}


@router.post("/{project_id}/knowledge/context", response_model=KnowledgeContextPack)
def build_knowledge_context_pack(project_id: str, request: KnowledgeContextRequest):
    try:
        return studio_knowledge_service.get_context_pack(project_id, request)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/knowledge/conflicts")
def list_knowledge_conflicts(
    project_id: str,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    conflicts = studio_knowledge_service.list_conflicts(project_id, status=status, limit=limit)
    return {"conflicts": [conflict.model_dump(mode="json") for conflict in conflicts]}


@router.post("/{project_id}/knowledge/conflicts/{conflict_id}/acknowledge")
def acknowledge_knowledge_conflict(project_id: str, conflict_id: str, request: KnowledgeConflictAcknowledgeRequest):
    try:
        conflict = studio_knowledge_service.acknowledge_conflict(project_id, conflict_id, request)
        return {"conflict": conflict.model_dump(mode="json")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/knowledge/traces")
def list_knowledge_traces(
    project_id: str,
    department: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    traces = studio_knowledge_service.list_traces(project_id, department=department, limit=limit)
    return {"traces": [trace.model_dump(mode="json") for trace in traces]}


@router.get("/{project_id}/knowledge/traces/{trace_id}")
def get_knowledge_trace(project_id: str, trace_id: str):
    try:
        trace = studio_knowledge_service.get_trace(project_id, trace_id)
        return {"trace": trace.model_dump(mode="json")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{project_id}/knowledge/sources")
def get_knowledge_sources(project_id: str):
    return studio_knowledge_service.source_status(project_id)

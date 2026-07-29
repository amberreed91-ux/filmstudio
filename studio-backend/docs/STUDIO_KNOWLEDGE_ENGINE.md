# Studio Knowledge Engine

Sprint 19 adds the canonical knowledge-consumption layer for AI Film Studio. It turns filmmaking Bibles, Study memory, project memory, cinematic memory, semantic memory, director memory, explicit creative memory, continuity graphs, and crew reasoning into source-cited knowledge atoms that departments can consume consistently.

## Ownership Boundary

`StudioKnowledgeService` is a derived resolver. It does not replace the systems that own truth:

- `MemoryService` owns project, scene, character, style, and review memory.
- `StudyMemoryService` owns Study room Active Memory.
- `CinematicMemoryService` owns cinematic keyframe memory.
- `SemanticMemoryService` owns video scene memory.
- `ProjectStoreService` owns explicit creative memory and director memory.
- `CreativeSpine` remains governance, not memory.
- `ContinuityIntelligenceService` owns continuity graph analysis.
- Department services own their own plans, observations, assessments, and decisions.

Knowledge atoms are rebuildable projections with provenance. They must not be treated as a new source of truth.

## Core Backend Files

- `app/models/studio_knowledge.py`
- `app/services/studio_knowledge_service.py`
- `app/routes/studio_knowledge.py`
- `app/data/storage.py` migration 51 and `knowledge_*` helper methods

Routes are mounted at:

- `POST /api/projects/{project_id}/knowledge/bibles`
- `GET /api/projects/{project_id}/knowledge/bibles`
- `POST /api/projects/{project_id}/knowledge/rebuild`
- `GET /api/projects/{project_id}/knowledge/atoms`
- `POST /api/projects/{project_id}/knowledge/context`
- `GET /api/projects/{project_id}/knowledge/conflicts`
- `GET /api/projects/{project_id}/knowledge/traces`
- `GET /api/projects/{project_id}/knowledge/sources`

## Department Consumption

Departments should call:

```python
from app.models.studio_knowledge import KnowledgeContextRequest
from app.services.studio_knowledge_service import studio_knowledge_service

pack = studio_knowledge_service.get_context_pack(
    project_id,
    KnowledgeContextRequest(
        department="co_director",
        purpose="scene_guidance",
        scene_id=scene_id,
        max_atoms=18,
    ),
)
```

Use `pack.atoms` for compact, source-cited context and `pack.trace_id` for audit. Do not parse Bible text inside department services.

## Explicit Memory Rule

The Knowledge Engine never saves permanent creative memory from inference. It can read explicit creative memory and project it as `creator_approved` atoms. New permanent memory must still go through existing explicit save gates.

## Frontend Surface

Study Room includes `KnowledgeLibraryPanel`, backed by `studio-app/src/lib/studioKnowledgeApi.ts`. The panel can register Bibles, rebuild the index, inspect active atoms, review source counts, and request department context packs.

## Verification

Focused checks:

```bash
.venv/bin/python -m pytest studio-backend/app/services/test_studio_knowledge_service.py studio-backend/app/routes/test_studio_knowledge_routes.py studio-backend/app/services/test_studio_brain_service.py
npm test -- --run src/components/KnowledgeLibraryPanel.test.tsx
npm run build
```

Expected behavior:

- Bible ingestion creates sections and atoms.
- Rebuild projects existing source systems into active atoms.
- Context packs include source counts, warnings, selected atoms, conflicts, and a trace ID.
- Studio Brain can include Studio Knowledge as read-only context.
- No automatic creative memory writes occur.


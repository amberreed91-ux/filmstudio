import secrets
import logging
import json
import time
import os
import subprocess
import sqlite3
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Ensure .env values are available before importing modules that construct runtime singletons.
load_dotenv(Path(__file__).resolve().parent / ".env")

# Raise the soft file-descriptor ceiling before application modules construct
# their SQLite connection pools. Server processes on macOS can inherit a
# 256-fd soft limit; once pooled SQLite connections consume it, uvicorn's
# accept() fails with EMFILE and every incoming request is reset before it
# can reach ASGI (surfacing to clients as proxy 502 / ECONNRESET).
try:
    import resource

    _soft_fd_limit, _hard_fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    _target_fd_limit = (
        4096
        if _hard_fd_limit == resource.RLIM_INFINITY
        else min(4096, _hard_fd_limit)
    )
    if _soft_fd_limit < _target_fd_limit:
        resource.setrlimit(resource.RLIMIT_NOFILE, (_target_fd_limit, _hard_fd_limit))
        print(
            f"[FD_LIMIT] soft file-descriptor limit raised {_soft_fd_limit} -> {_target_fd_limit}",
            flush=True,
        )
except Exception:  # noqa: BLE001 — a limit raise must never block startup
    pass

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from typing import Dict, Set
import asyncio

from app.routes import overview_router, projects_router, exports_router
from app.routes import auth_router
from app.routes.render import router as render_router
from app.routes.character_looks import router as character_looks_router
from app.routes.agents import router as agents_router
from app.routes.crew import router as crew_router
from app.routes.memory import router as memory_router
from app.routes.scene_intelligence import router as scene_intelligence_router
from app.routes.projects import router as projects_persistence_router
from app.routes.video_assets import router as video_assets_router
from app.routes.workflows import router as workflows_router
from app.routes.production_recovery import router as production_recovery_router
from app.routes.scene_continuity_intelligence import router as scene_continuity_intelligence_router
from app.routes.film_dna import router as film_dna_router
from app.routes.director_intent import router as director_intent_router
from app.routes.session_debrief import router as session_debrief_router
from app.routes.export_package import router as export_package_router, presets_router as festival_presets_router
from app.routes.pitch_deck import router as pitch_deck_router
from app.routes.previs_routes import router as previs_router
from app.routes.script_intelligence import router as script_intelligence_router
from app.routes.audience_simulator import router as audience_simulator_router
from app.routes.debate import router as debate_router
from app.routes.universe_graph import router as universe_graph_router
from app.routes.production_scan import router as production_scan_router
from app.routes.production_acceptance import router as production_acceptance_router
from app.routes.audio import router as audio_router
from app.routes.stitching import router as stitching_router
from app.routes.export import router as final_export_router
from app.routes.proactive import router as proactive_router
from app.routes.visual_training import router as visual_training_router
from app.routes.compose import router as compose_router
from app.routes.assembly import router as assembly_router
from app.routes.emotion_analysis import router as emotion_analysis_router
from app.routes.writers_intelligence import router as writers_intelligence_router
from app.routes.admin import router as admin_router
from app.routes.standing_corrections import router as standing_corrections_router
from app.routes.storyboard_blueprints import router as storyboard_blueprints_router
from app.routes.editorial_intelligence import router as editorial_intelligence_router
from app.routes.production_queue import router as production_queue_router
from app.routes.studio_workflow import router as studio_workflow_router
from app.routes.errors import router as errors_router
from app.routes.performance_intelligence import router as performance_intelligence_router
from app.routes.cinematography import router as cinematography_router
from app.routes.performance_audio_intelligence import router as performance_audio_intelligence_router
from app.routes.production_design_intelligence import router as production_design_intelligence_router
from app.routes.colorist import router as colorist_router
from app.routes.casting_intelligence import router as casting_intelligence_router
from app.routes.studio_knowledge import router as studio_knowledge_router
from app.routes.studio_brain import router as studio_brain_router
from app.routes.reference_assets import router as reference_assets_router
from app.routes.previs_image import router as previs_image_router
from app.routes.screening_room import router as screening_room_router
from app.routes.canonical_workflow import router as canonical_workflow_router
from app.services.render import set_job_update_callback, set_storage
from app.data.storage import get_storage
from app.auth import AuthService, demo_login, auth_service
from app.config import settings, get_settings
from app.middleware.request_id import RequestIDMiddleware, request_id_var
from app.middleware.structured_logging import StructuredLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.background_task_registry import BackgroundTaskRegistry
from app.services.database_backup import init_database_backup

# Configure logging
_log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
if settings.log_format == "json":
    _log_format = "%(message)s"
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format=_log_format,
)
logger = logging.getLogger("studio-api")


def _resolve_git_commit() -> str | None:
    """Return the checked-out git commit for build/runtime diagnostics."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    commit = result.stdout.strip()
    return commit or None


BUILD_COMMIT = _resolve_git_commit()
_start_time = time.time()

# Storage instance
storage = get_storage("sqlite")

# Auth service instance
auth_service.storage = storage

# Background task registry
task_registry = BackgroundTaskRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting Studio API")
    logger.info("Studio API build commit: %s", BUILD_COMMIT or "unknown")
    runway_key = os.getenv("RUNWAYML_API_SECRET", "").strip() or os.getenv("RUNWAY_API_KEY", "").strip()
    logger.info("Runway API configured: %s", bool(runway_key))

    # Initialize storage
    set_storage(storage)

    # Initialize database backup
    db_path = str(storage.db_path)
    backup = init_database_backup(
        db_path,
        backup_dir=settings.backup_dir,
        max_backups=settings.backup_max_count,
    )
    logger.info("Database backup initialized: %s", backup.get_status())

    # Schedule daily backup
    if settings.backup_enabled:
        task_registry.register("daily-backup", backup.schedule_daily(settings.backup_interval_hours))

    # Recovery lineage guard (added after the 2026-09-27 hard-reset incident):
    # 1) before ANY startup that follows a detected replace/restore event, pin an
    #    immutable snapshot of the outgoing database trio;
    # 2) register the database identity renders will later be verified against.
    try:
        from app.services.recovery_lineage_guard import (
            capture_recovery_snapshot,
            write_lineage_registration,
        )

        _db_file = Path(str(storage.db_path))
        _prev = _db_file.parent / "database_lineage.json"
        if _prev.exists():
            try:
                _prev_reg = json.loads(_prev.read_text())
                _prev_size = _prev_reg.get("bytes")
                _prev_hash = _prev_reg.get("sha256_first1m", "")
                import hashlib as _hashlib

                _h = _hashlib.sha256()
                with open(_db_file, "rb") as _f:
                    _h.update(_f.read(1 << 20))
                _changed = (
                    _prev_size != _db_file.stat().st_size
                    or (_prev_hash and _h.hexdigest()[:16] != _prev_hash)
                )
                if _changed:
                    capture_recovery_snapshot(
                        _db_file,
                        reason="startup-database-changed-since-registration",
                    )
                    logger.warning(
                        "Database changed since last registration — pre-change "
                        "snapshot captured before serving traffic"
                    )
            except Exception:  # noqa: BLE001 — snapshot failure is logged, not fatal at startup
                logger.exception("Recovery snapshot capture failed at startup")
        write_lineage_registration(_db_file)
        logger.info("Recovery lineage guard: database identity registered")
    except Exception:  # noqa: BLE001 — guard failure must never block startup
        logger.exception("Recovery lineage guard initialization failed")

    # Initialize render service with storage
    from app.services.render import render_service

    # Load existing jobs from canonical render_jobs storage
    try:
        from app.services.render_job_backfill import hydrate_render_service_from_storage

        loaded_count = hydrate_render_service_from_storage(
            render_service,
            storage,
            limit=max(1, min(int(settings.render_recovery_hydration_limit or 1000), 5000)),
        )
        logger.info("Loaded %d jobs from database", loaded_count)
        recovery = await render_service.recover_jobs_after_restart()
        logger.info("Render recovery summary: %s", recovery)
    except Exception as e:
        logger.warning("Could not load jobs from database: %s", e)

    # Initialize memory service with storage for persistence
    from app.services.memory import memory_service
    memory_service.storage = storage
    from app.services.studio_knowledge_service import studio_knowledge_service
    studio_knowledge_service.storage = storage
    from app.services.studio_brain_executive_service import studio_brain_executive_service
    studio_brain_executive_service._storage = storage
    studio_brain_executive_service._knowledge_service = studio_knowledge_service
    from app.services.video_asset_service import video_asset_service
    from app.services.keyframe_extraction_service import keyframe_extraction_service
    from app.services.shot_detection_service import shot_detection_service
    from app.services.semantic_memory_service import semantic_memory_service
    from app.services.continuity_intelligence_service import continuity_intelligence_service
    from app.services.director_commentary_service import director_commentary_service
    from app.services.semantic_search_service import semantic_search_service
    video_asset_service._storage = storage
    keyframe_extraction_service._storage = storage
    keyframe_extraction_service._video_asset_service = video_asset_service
    shot_detection_service._storage = storage
    shot_detection_service._video_asset_service = video_asset_service
    shot_detection_service._keyframe_service = keyframe_extraction_service
    semantic_memory_service._storage = storage
    semantic_memory_service._video_asset_service = video_asset_service
    semantic_memory_service._shot_detection_service = shot_detection_service
    continuity_intelligence_service._storage = storage
    continuity_intelligence_service._video_asset_service = video_asset_service
    continuity_intelligence_service._semantic_memory_service = semantic_memory_service
    director_commentary_service._storage = storage
    director_commentary_service._video_asset_service = video_asset_service
    director_commentary_service._keyframe_service = keyframe_extraction_service
    director_commentary_service._shot_detection_service = shot_detection_service
    director_commentary_service._semantic_memory_service = semantic_memory_service
    semantic_search_service._storage = storage
    semantic_search_service._semantic_memory_service = semantic_memory_service

    # Initialize visual training service with storage and the shared provider
    # configurations. Training adapters opt in via the VisualTrainingAdapter
    # boundary; non-training providers fail closed at get_training_adapter.
    from app.services.visual_training_service import visual_training_service
    visual_training_service._storage = storage
    for _provider_config in render_service._provider_configs.values():
        visual_training_service.register_provider_config(_provider_config)
    # Local visual-model training is available as its own provider so the
    # workflow can run end-to-end on this machine without a hosted trainer.
    from app.adapters.local_visual_training import build_default_config
    visual_training_service.register_provider_config(build_default_config())
    # Real Phosphene trainer: submits to the running Phosphene service's
    # training API (/train/upload → /train/start → /status → /characters).
    from app.adapters.phosphene_training import build_default_config as build_phosphene_training_config
    visual_training_service.register_provider_config(build_phosphene_training_config())
    # Restart recovery: re-poll any training job that was queued/training when
    # the backend last stopped. No background loop — one honest sweep here,
    # further refreshes ride the existing status mechanism (API reads).
    try:
        recovered = await visual_training_service.refresh_running_training_jobs()
        if recovered:
            logger.info(
                "Visual training restart recovery refreshed %d job(s)",
                len(recovered),
            )
    except Exception:  # noqa: BLE001 — recovery must never block startup
        logger.exception("Visual training restart recovery failed")
    logger.info("Visual training service initialized with storage and provider configs")

    # Initialize render retry / adherence quality loop with runtime services.
    from app.services.render_retry_service import render_retry_service
    from app.services.adherence_service import adherence_service
    render_retry_service.set_storage(storage)
    render_retry_service._adherence_service = adherence_service
    render_retry_service._keyframe_service = keyframe_extraction_service
    render_retry_service._video_asset_service = video_asset_service
    adherence_service._storage = storage
    logger.info("Render retry/adherence service initialized with storage and media services")

    # Initialize StudyMemoryService with storage
    from app.services.study_memory_service import get_study_memory_service
    _study_svc = get_study_memory_service()
    _study_svc.storage = storage
    logger.info("Study memory service initialized with storage")

    # Initialize short film review service with storage
    from app.services.short_film_review_service import short_film_review_service
    short_film_review_service._storage = storage
    logger.info("Short film review service initialized with storage")

    # Initialize clip revision service with storage and render service
    from app.services.clip_revision_service import clip_revision_service
    clip_revision_service._storage = storage
    clip_revision_service._render_service = render_service
    logger.info("Clip revision service initialized with storage and render service")

    # Initialize final short film package service with storage and other services
    from app.services.final_short_film_package_service import final_short_film_package_service
    final_short_film_package_service._storage = storage
    final_short_film_package_service._render_service = render_service
    final_short_film_package_service._review_service = short_film_review_service
    final_short_film_package_service._revision_service = clip_revision_service
    final_short_film_package_service._video_asset_service = video_asset_service
    video_asset_service._storage = storage
    logger.info("Final short film package service initialized with storage and other services")

    # Initialize standing corrections service with storage
    from app.services.standing_corrections_service import standing_corrections_service
    from app.services.performance_intelligence_service import performance_intelligence_service
    from app.services.cinematographer_intelligence_service import cinematographer_intelligence_service
    from app.services.production_design_intelligence_service import production_design_intelligence_service
    from app.services.casting_intelligence_service import casting_intelligence_service
    standing_corrections_service._storage = storage
    performance_intelligence_service._storage = storage
    cinematographer_intelligence_service._storage = storage
    production_design_intelligence_service._storage = storage
    casting_intelligence_service._storage = storage
    logger.info("Standing corrections service initialized with storage")

    # Initialize durable production queue service with storage and render dispatch.
    from app.services.production_queue_service import production_queue_service
    production_queue_service.set_storage(storage)
    production_queue_service.set_render_service(render_service)
    queue_recovery = production_queue_service.recover_expired_leases()
    logger.info("Production queue initialized: %s", queue_recovery)
    if settings.production_queue_enabled and settings.production_queue_worker_enabled:
        task_registry.register("queue-worker", production_queue_service.worker_loop())
        logger.info("Started production queue worker task")

    # Start background polling task for active Runway jobs
    task_registry.register("render-polling", render_service.poll_active_runway_jobs())
    logger.info("Started background Runway job polling task")

    # Recovery lineage guard: verify the restored/registered database still
    # holds the creative estate it held before any prior destructive operation.
    try:
        from app.services.recovery_lineage_guard import verify_restore_invariants

        _baseline_path = Path(str(storage.db_path)).parent / "recovery-snapshots" / "baseline-creative-counts.json"
        if _baseline_path.exists():
            _baseline = json.loads(_baseline_path.read_text())
            _report = verify_restore_invariants(str(storage.db_path), _baseline)
            if _report["ok"]:
                logger.info("Restore invariant verification passed (%d projects)", len(_baseline))
            else:  # fail closed: surface loudly, do not heal silently
                logger.error(
                    "RESTORE INVARIANT FAILURE — creative estate regressed: %s",
                    _report["failures"][:10],
                )
    except Exception:  # noqa: BLE001
        logger.exception("Restore invariant verification failed to run")

    yield

    # --- Graceful Shutdown ---
    logger.info("Shutting down Studio API")

    # 1. Cancel all tracked background tasks
    await task_registry.cancel_all(timeout=10.0)

    # 2. Stop production queue worker
    try:
        await production_queue_service.stop_background_worker()
    except Exception as e:
        logger.warning("Error stopping queue worker: %s", e)

    # 3. Cleanup expired sessions before draining the connection pool.
    try:
        storage.cleanup_expired_sessions()
    except Exception as e:
        logger.warning("Error cleaning up sessions: %s", e)

    # 4. Drain connection pool
    storage.close()

    logger.info("Studio API shutdown complete")


app = FastAPI(
    title="Studio API",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.disable_rate_limit_for_testclient = True

# --- Middleware Stack (order matters: outermost runs first) ---

# 1. Request ID (outermost — every request gets a correlation ID)
app.add_middleware(RequestIDMiddleware)

# 2. Structured logging (emits JSON log per request)
if settings.log_format == "json":
    app.add_middleware(StructuredLoggingMiddleware)

# 3. Rate limiting
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute, read_requests_per_minute=max(600, settings.rate_limit_per_minute))

from app.middleware.project_access import ProjectAccessMiddleware
app.add_middleware(ProjectAccessMiddleware, storage=storage, schema=app.openapi)

# 4. CORS — configurable origins
if settings.cors_origins:
    _cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
else:
    _cors_origins = [o.strip() for o in settings.cors_origins_dev.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=bool(_cors_origins),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Admin-Token", "X-Session-Token"],
)

# 5. Security headers
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Routers
app.include_router(overview_router, prefix="/api/f51/studio")
app.include_router(final_export_router)
app.include_router(projects_router, prefix="/api/f51/studio")
app.include_router(projects_persistence_router)
app.include_router(video_assets_router)
app.include_router(exports_router)
app.include_router(render_router, prefix="/api/f51/studio/render")
app.include_router(auth_router, prefix="/api/f51/studio/auth")
app.include_router(agents_router)
app.include_router(crew_router)
app.include_router(memory_router)
app.include_router(scene_intelligence_router)
app.include_router(workflows_router)
app.include_router(production_recovery_router)
app.include_router(scene_continuity_intelligence_router)
app.include_router(film_dna_router)
app.include_router(director_intent_router)
app.include_router(session_debrief_router)
app.include_router(export_package_router)
app.include_router(festival_presets_router)
app.include_router(pitch_deck_router)
app.include_router(previs_router, prefix="/api/f51/studio")
app.include_router(script_intelligence_router)
app.include_router(audience_simulator_router)
app.include_router(debate_router)
app.include_router(universe_graph_router)
app.include_router(production_scan_router)
app.include_router(production_acceptance_router)
app.include_router(audio_router)
app.include_router(stitching_router)
app.include_router(proactive_router)
app.include_router(compose_router)
app.include_router(visual_training_router, prefix="/api/f51/studio/visual-training")
app.include_router(assembly_router)
from app.routes.take_selection import router as take_selection_router
app.include_router(take_selection_router)
from app.routes.scene_direction import router as scene_direction_router
app.include_router(scene_direction_router)
from app.routes.camera_presets import router as camera_presets_router
app.include_router(camera_presets_router)
from app.routes.take_camera_review import router as take_camera_review_router
app.include_router(take_camera_review_router)
app.include_router(emotion_analysis_router)
app.include_router(writers_intelligence_router)
app.include_router(admin_router)
app.include_router(standing_corrections_router)
app.include_router(storyboard_blueprints_router)
app.include_router(editorial_intelligence_router)
app.include_router(production_queue_router)
app.include_router(studio_workflow_router)
app.include_router(errors_router)
app.include_router(performance_intelligence_router)
app.include_router(cinematography_router)
app.include_router(performance_audio_intelligence_router)
app.include_router(production_design_intelligence_router)
app.include_router(colorist_router)
app.include_router(casting_intelligence_router)
app.include_router(studio_knowledge_router)
app.include_router(studio_brain_router)
app.include_router(reference_assets_router)
app.include_router(previs_image_router)
app.include_router(screening_room_router)
app.include_router(canonical_workflow_router)
app.include_router(character_looks_router)

OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Create previs output directory
PREVIS_DIR = OUTPUTS_DIR / "previs"
PREVIS_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files for previs images
app.mount("/previs-assets", StaticFiles(directory=str(PREVIS_DIR)), name="previs-assets")


@app.get("/outputs/mock-video/sample.mp4")
def mock_video_sample():
    sample_path = OUTPUTS_DIR / "mock-video" / "sample.mp4"
    if sample_path.exists():
        return PlainTextResponse(
            "mock video placeholder unavailable",
            media_type="text/plain",
            headers={"X-Mock-Video-Blocker": "non_video_placeholder"},
        ) if sample_path.stat().st_size < 32 else Response(
            content=sample_path.read_bytes(),
            media_type="video/mp4",
            headers={"Cache-Control": "no-store"},
        )
    return PlainTextResponse(
        "mock video placeholder unavailable",
        media_type="text/plain",
        headers={"X-Mock-Video-Blocker": "missing_sample"},
    )


app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

# Mount static files for composed scene videos
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/build-info")
def build_info():
    return {
        "app": "studio-api",
        "version": app.version,
        "commit": BUILD_COMMIT,
        "commit_source": "git_rev_parse_head" if BUILD_COMMIT else "unavailable",
    }

# WebSocket Connection Manager
class ConnectionManager:
    """WebSocket connection manager for real-time job updates"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, job_id: str = "global"):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
        logger.debug("WebSocket connected: %s, total: %d", job_id, len(self.active_connections[job_id]))
    
    def disconnect(self, websocket: WebSocket, job_id: str = "global"):
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
            logger.debug("WebSocket disconnected: %s", job_id)
    
    async def broadcast(self, message: dict, job_id: str = "global"):
        if job_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.add(connection)
            for conn in disconnected:
                self.disconnect(conn, job_id)
    
    async def broadcast_all(self, message: dict):
        all_connections = set()
        for connections in self.active_connections.values():
            all_connections.update(connections)
        
        disconnected = set()
        for connection in all_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        
        for conn in disconnected:
            for job_id in list(self.active_connections.keys()):
                self.disconnect(conn, job_id)

manager = ConnectionManager()

async def notify_job_update(job_id: str, job_data: dict):
    """Broadcast job update to all subscribers"""
    await manager.broadcast({"type": "job_update", "job_id": job_id, "data": job_data}, job_id)
    await manager.broadcast({"type": "job_update", "job_id": job_id, "data": job_data}, "global")

# Register the callback with render service
set_job_update_callback(notify_job_update)

# WebSocket endpoints
@app.websocket("/ws/jobs")
async def websocket_jobs_endpoint(websocket: WebSocket):
    """WebSocket endpoint for all job updates"""
    await manager.connect(websocket, "global")
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "global")

@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_updates(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for specific job updates"""
    await manager.connect(websocket, job_id)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)


# --- Health & Readiness Endpoints ---

@app.get("/health")
def health_check():
    """Comprehensive health check across all subsystems."""
    try:
        import psutil
        _psutil_available = True
    except ImportError:
        _psutil_available = False

    # Database
    db_status = "ok"
    db_error = None
    db_latency_ms = None
    try:
        import sqlite3 as _sq3
        _start = time.perf_counter()
        conn = _sq3.connect(str(storage.db_path), timeout=5.0)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        db_latency_ms = round((time.perf_counter() - _start) * 1000, 2)
    except Exception as e:
        db_status = "error"
        db_error = str(e)

    # Render service
    render_status = "ok"
    job_count = 0
    providers_available = []
    try:
        from app.services.render import render_service
        job_count = len(render_service._jobs)
        providers_available = list(getattr(render_service, '_available_providers', []))
    except Exception as e:
        render_status = "error"

    # Production queue
    queue_status = "ok"
    queue_summary = {}
    try:
        from app.services.production_queue_service import production_queue_service
        summary = production_queue_service.summarize()
        queue_summary = {
            "counts_by_status": summary.counts_by_status,
            "stale_leases": summary.stale_leases,
            "worker": production_queue_service.worker_status().model_dump(),
        }
    except Exception as e:
        queue_status = "error"
        queue_summary = {"error": str(e)}

    # Circuit breakers
    from app.circuit_breaker import circuit_breaker
    circuit_status = {}
    for provider in ["simulated", "higgsfield", "generic"]:
        try:
            circuit_status[provider] = circuit_breaker.get_status(provider)
        except Exception:
            circuit_status[provider] = {"state": "unknown"}

    # Background tasks
    bg_tasks = task_registry.status()

    # System metrics
    system_metrics = {"status": "unavailable"}
    if _psutil_available:
        try:
            system_metrics = {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
            }
        except Exception:
            system_metrics = {"status": "error"}

    # Overall status
    if db_status != "ok":
        overall_status = "unhealthy"
    elif render_status != "ok" or queue_status != "ok":
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "version": app.version,
        "git_commit": BUILD_COMMIT,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "timestamp": time.time(),
        "components": {
            "database": {"status": db_status, "error": db_error, "latency_ms": db_latency_ms},
            "render_service": {"status": render_status, "active_jobs": job_count, "providers_available": providers_available},
            "production_queue": {"status": queue_status, **queue_summary},
            "circuit_breakers": circuit_status,
            "background_tasks": bg_tasks,
            "system": system_metrics,
        },
    }


@app.get("/ready")
async def readiness_check():
    """Readiness probe — returns 200 only when fully initialized."""
    checks = {}
    all_ready = True

    # Database
    try:
        import sqlite3 as _sq3
        conn = _sq3.connect(str(storage.db_path), timeout=5.0)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        checks["database"] = "ready"
    except Exception as e:
        checks["database"] = f"not_ready: {e}"
        all_ready = False

    # Schema
    try:
        import sqlite3 as _sq3
        conn = _sq3.connect(str(storage.db_path), timeout=5.0)
        try:
            cursor = conn.execute("SELECT MAX(version) FROM schema_migrations")
            row = cursor.fetchone()
            checks["schema"] = f"ready (v{row[0]})" if row and row[0] else "not_ready: no migrations"
        finally:
            conn.close()
    except Exception as e:
        checks["schema"] = f"not_ready: {e}"
        all_ready = False

    # Background tasks
    bg_status = task_registry.status()
    if bg_status:
        checks["background_tasks"] = f"ready ({len(bg_status)} active)"
    else:
        checks["background_tasks"] = "ready (no active tasks)"

    status_code = 200 if all_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "ready": all_ready,
            "components": checks,
            "timestamp": time.time(),
        },
    )


@app.get("/")
def root():
    return {"message": "Studio API running", "version": "1.0.0"}

@app.get("/api/approval")
def approval_snapshot():
    """Deterministic, provider-independent approval snapshot for frontend fallback-safe loading."""
    return {
        "approvals": [
            {
                "scene_id": "scene_001",
                "status": "pending",
                "notes": "Needs pacing adjustment",
                "verdict": "needs_review"
            }
        ],
        "summary": {
            "total": 1,
            "pending": 1,
            "approved": 0,
            "rejected": 0
        }
    }

# Temporary, observational instrumentation for one authentication session route.
_STUDIO_SESSION_DIAGNOSTIC_PATH = "/api/f51/studio/auth/session"
_STUDIO_SESSION_DIAGNOSTIC_PREFIX = "[STUDIO_SESSION_ASGI_DIAGNOSTIC]"
_STUDIO_SESSION_DIAGNOSTIC_STAGES = frozenset({
    "asgi_entry",
    "handler_entry",
    "response_start",
    "handler_exception",
})


def _emit_studio_session_diagnostic(
    stage: str,
    *,
    status: int | None = None,
    error: str | None = None,
) -> None:
    """Emit fixed, allowlisted fields; diagnostics must never affect requests."""
    try:
        if stage not in _STUDIO_SESSION_DIAGNOSTIC_STAGES:
            return
        record = [
            f"utc={datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
            f"stage={stage}",
        ]
        if stage == "response_start" and isinstance(status, int) and not isinstance(status, bool):
            record.append(f"status={status}")
        if stage == "handler_exception" and error in {
            "HTTP_EXCEPTION",
            "VALIDATION_ERROR",
            "STORAGE_ERROR",
            "UNKNOWN_EXCEPTION",
        }:
            record.append(f"error={error}")
        sys.stdout.write(f"{_STUDIO_SESSION_DIAGNOSTIC_PREFIX} {' '.join(record)}\n")
        sys.stdout.flush()
    except BaseException:
        # Diagnostic failures must not alter request processing.
        pass


def _studio_session_exception_category(error: Exception) -> str:
    if isinstance(error, HTTPException):
        return "HTTP_EXCEPTION"
    if isinstance(error, (RequestValidationError, ValidationError)):
        return "VALIDATION_ERROR"
    if isinstance(error, sqlite3.Error):
        return "STORAGE_ERROR"
    return "UNKNOWN_EXCEPTION"


class _StudioSessionASGIDiagnosticMiddleware:
    """Observe only the exact session request before existing middleware."""

    def __init__(self, wrapped_app):
        self.wrapped_app = wrapped_app

    async def __call__(self, scope, receive, send):
        if not (
            scope.get("type") == "http"
            and scope.get("method") == "GET"
            and scope.get("path") == _STUDIO_SESSION_DIAGNOSTIC_PATH
        ):
            await self.wrapped_app(scope, receive, send)
            return

        _emit_studio_session_diagnostic("asgi_entry")

        async def observed_send(message):
            if message.get("type") == "http.response.start":
                _emit_studio_session_diagnostic(
                    "response_start",
                    status=message.get("status"),
                )
            await send(message)

        await self.wrapped_app(scope, receive, observed_send)


def _install_studio_session_diagnostics() -> None:
    """Add a transparent outer observer and wrap only the exact APIRoute."""
    for route in app.router.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == _STUDIO_SESSION_DIAGNOSTIC_PATH
            and "GET" in (route.methods or set())
        ):
            original_handler = route.dependant.call
            if original_handler is None:
                continue

            async def observed_handler(*args, _original=original_handler, **kwargs):
                _emit_studio_session_diagnostic("handler_entry")
                try:
                    return await _original(*args, **kwargs)
                except Exception as error:
                    try:
                        _emit_studio_session_diagnostic(
                            "handler_exception",
                            error=_studio_session_exception_category(error),
                        )
                    except BaseException:
                        pass
                    raise

            route.dependant.call = observed_handler
            break

    # Wrap the already-built stack so its existing middleware ordering is intact.
    app.middleware_stack = _StudioSessionASGIDiagnosticMiddleware(
        app.build_middleware_stack()
    )


_install_studio_session_diagnostics()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8010,
        log_level="info"
    )

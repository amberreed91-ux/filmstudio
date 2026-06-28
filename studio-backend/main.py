import secrets
import logging
import time
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Ensure .env values are available before importing modules that construct runtime singletons.
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from typing import Dict, Set
import asyncio

from app.routes import overview_router, projects_router, exports_router
from app.routes import auth_router
from app.routes.render import router as render_router
from app.routes.agents import router as agents_router
from app.routes.crew import router as crew_router
from app.routes.memory import router as memory_router
from app.routes.scene_intelligence import router as scene_intelligence_router
from app.routes.projects import router as projects_persistence_router
from app.routes.video_assets import router as video_assets_router
from app.routes.video_analysis import router as video_analysis_router
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
from app.routes.audio import router as audio_router
from app.routes.stitching import router as stitching_router
from app.routes.export import router as final_export_router
from app.routes.proactive import router as proactive_router
from app.routes.co_director_chat import router as co_director_chat_router
from app.routes.compose import router as compose_router
from app.routes.emotion_analysis import router as emotion_analysis_router
from app.routes.writers_intelligence import router as writers_intelligence_router
from app.services.render import set_job_update_callback, set_storage
from app.data.storage import get_storage
from app.auth import AuthService, demo_login

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("studio-api")

# Storage instance
storage = get_storage("sqlite")

# Auth service instance
auth_service = AuthService(storage)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting Studio API")
    runway_key = os.getenv("RUNWAYML_API_SECRET", "").strip() or os.getenv("RUNWAY_API_KEY", "").strip()
    logger.info("Runway API configured: %s", bool(runway_key))
    
    # Initialize storage
    set_storage(storage)
    
    # Initialize render service with storage
    from app.services.render import render_service
    
    # Load existing jobs from canonical render_jobs storage
    try:
        from app.services.render_job_backfill import hydrate_render_service_from_storage

        loaded_count = hydrate_render_service_from_storage(render_service, storage)
        logger.info(f"Loaded {loaded_count} jobs from database")
        recovery = await render_service.recover_jobs_after_restart()
        logger.info("Render recovery summary: %s", recovery)
    except Exception as e:
        logger.warning(f"Could not load jobs from database: {e}")
    
    # Initialize memory service with storage for persistence
    from app.services.memory import memory_service
    memory_service.storage = storage
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
    from app.services.short_film_review_service import short_film_review_service
    from app.services.video_asset_service import video_asset_service
    final_short_film_package_service._storage = storage
    final_short_film_package_service._render_service = render_service
    final_short_film_package_service._review_service = short_film_review_service
    final_short_film_package_service._revision_service = clip_revision_service
    final_short_film_package_service._video_asset_service = video_asset_service
    video_asset_service._storage = storage
    logger.info("Final short film package service initialized with storage and other services")
    
    # Start background polling task for active Runway jobs
    asyncio.create_task(render_service.poll_active_runway_jobs())
    logger.info("Started background Runway job polling task")
    
    yield
    
    logger.info("Shutting down Studio API")
    # Cleanup
    storage.cleanup_expired_sessions()

app = FastAPI(
    title="Studio API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS - configured for local frontend dev origins
CORS_ORIGINS = [
    "http://127.0.0.1:5001",
    "http://localhost:5001",
    "http://127.0.0.1:5000",
    "http://localhost:5000",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://127.0.0.1:4174",
    "http://localhost:4174",
    "http://127.0.0.1:8010",
    "http://localhost:8010",
    "http://127.0.0.1:8012",
    "http://localhost:8012",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        logger.info(f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s")
        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"{request.method} {request.url.path} - Error: {e} - {duration:.3f}s")
        raise

# Routers
app.include_router(overview_router, prefix="/api/f51/studio")
app.include_router(projects_router, prefix="/api/f51/studio")
app.include_router(projects_persistence_router)
app.include_router(video_assets_router)
app.include_router(video_analysis_router)
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
app.include_router(audio_router)
app.include_router(stitching_router)
app.include_router(final_export_router)
app.include_router(proactive_router)
app.include_router(co_director_chat_router)
app.include_router(compose_router)
app.include_router(emotion_analysis_router)
app.include_router(writers_intelligence_router)

OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Create previs output directory
PREVIS_DIR = OUTPUTS_DIR / "previs"
PREVIS_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files for previs images
from fastapi.staticfiles import StaticFiles
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
        logger.debug(f"WebSocket connected: {job_id}, total: {len(self.active_connections[job_id])}")
    
    def disconnect(self, websocket: WebSocket, job_id: str = "global"):
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
            logger.debug(f"WebSocket disconnected: {job_id}")
    
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

# Health check endpoint with detailed status
@app.get("/health")
def health_check():
    """Health check endpoint with detailed status"""
    import psutil
    
    # Check database
    db_status = "ok"
    db_error = None
    try:
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as e:
        db_status = "error"
        db_error = str(e)
    
    # Check render service
    render_status = "ok"
    try:
        from app.services.render import render_service
        job_count = len(render_service._jobs)
    except Exception as e:
        render_status = "error"
        job_count = 0
    
    # Check circuit breakers
    from app.circuit_breaker import circuit_breaker
    circuit_status = {}
    for provider in ["simulated", "higgsfield", "generic"]:
        try:
            circuit_status[provider] = circuit_breaker.get_status(provider)
        except:
            circuit_status[provider] = {"state": "unknown"}
    
    overall_status = "healthy" if db_status == "ok" else "degraded"
    
    return {
        "status": overall_status,
        "version": "1.0.0",
        "timestamp": time.time(),
        "components": {
            "database": {"status": db_status, "error": db_error},
            "render_service": {"status": render_status, "active_jobs": job_count},
            "circuit_breakers": circuit_status,
            "system": {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent
            }
        }
    }

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8010,
        log_level="info"
    )

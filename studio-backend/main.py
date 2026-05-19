import secrets
import logging
import time
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    
    # Initialize storage
    set_storage(storage)
    
    # Initialize render service with storage
    from app.services.render import render_service
    
    # Load existing jobs from database
    try:
        existing_jobs = storage.list_jobs(limit=1000)
        for job in existing_jobs:
            render_service._jobs[job.id] = job
        logger.info(f"Loaded {len(existing_jobs)} jobs from database")
    except Exception as e:
        logger.warning(f"Could not load jobs from database: {e}")
    
    # Initialize memory service with storage for persistence
    from app.services.memory import memory_service
    memory_service.storage = storage
    logger.info("Memory service initialized with storage")
    
    yield
    
    logger.info("Shutting down Studio API")
    # Cleanup
    storage.cleanup_expired_sessions()

app = FastAPI(
    title="Studio API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS - configured for production (includes localhost + 127.0.0.1 dev origins)
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    ",".join(
        [
            "http://localhost:5004",
            "http://localhost:5003",
            "http://localhost:5002",
            "http://localhost:5001",
            "http://localhost:5000",
            "http://127.0.0.1:5004",
            "http://127.0.0.1:5003",
            "http://127.0.0.1:5002",
            "http://127.0.0.1:5001",
            "http://127.0.0.1:5000",
            "http://localhost:8010",
            "http://127.0.0.1:8010",
        ]
    ),
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-Token", "X-Request-ID"],
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
app.include_router(exports_router)
app.include_router(render_router, prefix="/api/f51/studio/render")
app.include_router(auth_router, prefix="/api/f51/studio/auth")
app.include_router(agents_router)
app.include_router(crew_router)
app.include_router(memory_router)
app.include_router(scene_intelligence_router)

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

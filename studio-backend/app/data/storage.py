import json
import sqlite3
import os
import logging
from pathlib import Path
from typing import Optional, Any, List, Dict
from datetime import datetime
from contextlib import contextmanager
from queue import Queue
import threading

from app.models import StudioProject, StudioOverview, BuildInfo, RenderJobModel

logger = logging.getLogger("studio-storage")


class StorageInterface:
    """Abstract storage interface - can be replaced with SQLite/Postgres"""

    def get_all_projects(self) -> dict[str, Any]:
        raise NotImplementedError

    def get_project(self, project_id: str) -> Optional[Any]:
        raise NotImplementedError

    def save_project(self, project: Any) -> Any:
        raise NotImplementedError

    def delete_project(self, project_id: str) -> bool:
        raise NotImplementedError

    def list_project_ids(self) -> list[str]:
        raise NotImplementedError


class DatabaseStorage:
    """SQLite storage with database-ready abstraction layer and connection pooling"""

    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "studio.db"
        self._connection_pool: Queue = Queue(maxsize=10)
        self._pool_size = 10
        self._lock = threading.Lock()
        self._init_schema()
        self._ensure_initial_data()

    def _create_connection(self):
        """Create a new database connection"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _get_connection(self):
        """Get connection - thread-safe implementation"""
        conn = None
        try:
            conn = self._create_connection()
            yield conn
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def _init_schema(self):
        """Initialize database schema with constraints and integrity"""
        conn = self._create_connection()
        cursor = conn.cursor()

        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT
            )
        """)

        migrations = [
            (1, "Initial schema with constraints", """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    CHECK (project_id != '')
                );
                
                CREATE TABLE IF NOT EXISTS render_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_job_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending' 
                        CHECK (status IN ('pending', 'rendering', 'complete', 'failed', 'cancelled')),
                    progress INTEGER NOT NULL DEFAULT 0 
                        CHECK (progress >= 0 AND progress <= 100),
                    input_payload TEXT,
                    output_payload TEXT,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0 
                        CHECK (retry_count >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    CHECK (id != ''),
                    CHECK (project_id != ''),
                    CHECK (shot_id != ''),
                    CHECK (provider != '')
                );
                
                CREATE INDEX IF NOT EXISTS idx_render_jobs_project ON render_jobs(project_id);
                CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON render_jobs(status);
                CREATE INDEX IF NOT EXISTS idx_render_jobs_created ON render_jobs(created_at);
                CREATE INDEX IF NOT EXISTS idx_render_jobs_provider ON render_jobs(provider);
            """),
            (2, "Add provider_configs table", """
                CREATE TABLE IF NOT EXISTS provider_configs (
                    provider_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                    is_simulated INTEGER NOT NULL DEFAULT 0 CHECK (is_simulated IN (0, 1)),
                    api_key TEXT,
                    api_endpoint TEXT,
                    requires TEXT,
                    capabilities TEXT,
                    config_data TEXT
                );
            """),
            (3, "Add sessions with constraints", """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    CHECK (session_id != ''),
                    CHECK (user_id != ''),
                    CHECK (expires_at > created_at)
                );
                
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
            """),
            (4, "Add audit_log table", """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    user_id TEXT,
                    action TEXT NOT NULL,
                    resource_type TEXT,
                    resource_id TEXT,
                    details TEXT,
                    ip_address TEXT
                );
                
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
            """),
            (5, "Add persistent project memory tables", """
                CREATE TABLE IF NOT EXISTS project_memories (
                    project_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    summary TEXT,
                    scope TEXT NOT NULL DEFAULT 'global',
                    scene_id TEXT,
                    character_id TEXT,
                    created_by_agent TEXT,
                    source_task_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    contradicted INTEGER NOT NULL DEFAULT 0,
                    contradiction_notes TEXT,
                    entry_id TEXT NOT NULL,
                    PRIMARY KEY (entry_id, version),
                    CHECK (project_id != ''),
                    CHECK (memory_type != '')
                );
                
                CREATE TABLE IF NOT EXISTS memory_versions (
                    entry_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    modified_by TEXT,
                    modified_at TEXT NOT NULL,
                    change_summary TEXT,
                    PRIMARY KEY (entry_id, version),
                    CHECK (version >= 1)
                );
                
                CREATE TABLE IF NOT EXISTS scene_memories (
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    scene_number INTEGER DEFAULT 0,
                    location_name TEXT,
                    time_of_day TEXT,
                    weather TEXT,
                    camera_choices TEXT,
                    lighting_notes TEXT,
                    color_palette TEXT,
                    props_in_scene TEXT,
                    character_positions TEXT,
                    generated_shots TEXT,
                    approved_shots TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, scene_id),
                    CHECK (project_id != ''),
                    CHECK (scene_id != '')
                );
                
                CREATE TABLE IF NOT EXISTS character_memories (
                    project_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    character_name TEXT,
                    appearance_traits TEXT,
                    personality_traits TEXT,
                    speech_patterns TEXT,
                    mannerisms TEXT,
                    physical_quirks TEXT,
                    wardrobe TEXT,
                    backstory_notes TEXT,
                    relationships TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, character_id),
                    CHECK (project_id != ''),
                    CHECK (character_id != '')
                );
                
                CREATE TABLE IF NOT EXISTS style_memories (
                    project_id TEXT NOT NULL,
                    camera_language TEXT,
                    lighting_approach TEXT,
                    color_palette TEXT,
                    pacing_notes TEXT,
                    frame_composition TEXT,
                    movement_style TEXT,
                    lens_preferences TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id),
                    CHECK (project_id != '')
                );
                
                CREATE TABLE IF NOT EXISTS review_memories (
                    project_id TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    feedback_type TEXT NOT NULL,
                    feedback_source TEXT NOT NULL,
                    feedback_text TEXT,
                    quality_score INTEGER,
                    issues TEXT,
                    recommendations TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, scene_id, shot_id, feedback_type),
                    CHECK (project_id != ''),
                    CHECK (feedback_type != ''),
                    CHECK (feedback_source != '')
                );
                
                CREATE INDEX IF NOT EXISTS idx_project_memories_project ON project_memories(project_id);
                CREATE INDEX IF NOT EXISTS idx_project_memories_type ON project_memories(project_id, memory_type);
                CREATE INDEX IF NOT EXISTS idx_project_memories_scene ON project_memories(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_project_memories_character ON project_memories(project_id, character_id);
                CREATE INDEX IF NOT EXISTS idx_scene_memories_project ON scene_memories(project_id);
                CREATE INDEX IF NOT EXISTS idx_character_memories_project ON character_memories(project_id);
                CREATE INDEX IF NOT EXISTS idx_review_memories_project ON review_memories(project_id);
            """),
            (6, "Add crew_tasks and task_log tables", """
                CREATE TABLE IF NOT EXISTS crew_tasks (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    agent_role TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    title TEXT,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'created'
                        CHECK (status IN ('created', 'pending_input', 'assigned', 'in_progress', 'completed', 'failed', 'blocked', 'cancelled')),
                    priority INTEGER NOT NULL DEFAULT 5 CHECK (priority >= 0 AND priority <= 10),
                    depends_on TEXT,
                    input_data TEXT,
                    output_data TEXT,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    progress INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    created_by TEXT DEFAULT 'system',
                    CHECK (task_id != ''),
                    CHECK (project_id != ''),
                    CHECK (agent_role != ''),
                    CHECK (task_type != '')
                );
                
                CREATE TABLE IF NOT EXISTS crew_task_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    agent_role TEXT,
                    details TEXT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (task_id) REFERENCES crew_tasks(task_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_crew_tasks_project ON crew_tasks(project_id);
                CREATE INDEX IF NOT EXISTS idx_crew_tasks_status ON crew_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_crew_tasks_role ON crew_tasks(agent_role);
                CREATE INDEX IF NOT EXISTS idx_crew_tasks_created ON crew_tasks(created_at);
                CREATE INDEX IF NOT EXISTS idx_task_log_task ON crew_task_log(task_id);
                CREATE INDEX IF NOT EXISTS idx_task_log_project ON crew_task_log(project_id);
            """),
        ]

        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        current_version = cursor.fetchone()[0] or 0

        for version, description, sql in migrations:
            if version > current_version:
                cursor.execute("BEGIN TRANSACTION")
                try:
                    for statement in sql.split(';'):
                        statement = statement.strip()
                        if statement:
                            cursor.execute(statement)
                    cursor.execute(
                        "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                        (version, datetime.now().isoformat(), description)
                    )
                    cursor.execute("COMMIT")
                    logger.info(f"Applied migration {version}: {description}")
                except Exception as e:
                    cursor.execute("ROLLBACK")
                    logger.error(f"Migration {version} failed: {e}")
                    raise

        conn.commit()
        conn.close()

    def _ensure_initial_data(self):
        """Ensure initial demo project exists"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM projects")
            if cursor.fetchone()[0] == 0:
                self._create_demo_project()

    def _create_demo_project(self):
        """Create demo project in database"""
        project_data = {
            "project_id": "proj-001",
            "title": "Neon Dreams",
            "updated_at": datetime.now().isoformat(),
            "source_stats": {"scene_count": 12, "shot_count": 48, "render_count": 18, "character_count": 7, "word_count": 4200, "target_runtime_minutes": 94},
            "render_provider": {"provider_name": "Simulated Provider", "provider_model": "GPU Cluster", "status": "running", "mode": "batch", "live_mode": False},
            "production_bible": {"creative_intent": "Neo-noir thriller exploring surveillance capitalism through the lens of a jaded detective in a rain-soaked megacity. Tone: cinematic, morally ambiguous, visually lush."},
            "render_provider_integrations": [
                {"provider": "Simulated", "selected": True, "status": "active", "live_generation": "enabled", "requires": []},
            ],
            "crew_agents": [
                {"agent_id": "director", "name": "Director Agent", "task": "Guard tone and character arc", "status": "active", "color": "#f59e0b", "department": "Directing"},
                {"agent_id": "cinematographer", "name": "Cinematographer Agent", "task": "Own blocking and lensing", "status": "active", "color": "#3b82f6", "department": "Camera"},
                {"agent_id": "editor", "name": "Editor Agent", "task": "Shape pacing and rhythm", "status": "active", "color": "#8b5cf6", "department": "Post"},
            ],
            "shot_approval_gates": [
                {"id": "creative", "label": "Creative Approval", "status": "passed", "sub": "Director approved", "detail": "All creative gates passed", "shot_id": "shot_001"},
                {"id": "technical", "label": "Technical Review", "status": "pending", "sub": "Awaiting QC", "detail": "Render quality check", "shot_id": "shot_001"},
            ],
            "storyboard_wall": [
                {"shot_id": "shot_001", "scene": "Scene 1", "description": "Establishing shot of city", "status": "approved"},
                {"shot_id": "shot_002", "scene": "Scene 2", "description": "Detective enters office", "status": "pending"},
            ],
            "render_queue": [
                {"render_id": "render_001", "shot_id": "shot_001", "status": "complete", "progress": 100, "eta": "Ready", "cost_per_minute": "$0.42", "priority": True, "provider": "Simulated", "selected": True, "score": 92, "qc_note": ""},
                {"render_id": "render_002", "shot_id": "shot_002", "status": "rendering", "progress": 67, "eta": "2m 30s", "cost_per_minute": "$0.42", "priority": False, "provider": "Simulated", "selected": False, "score": 0, "qc_note": ""},
            ],
            "rights_safety_clearance_board": {"overall_status": "cleared", "music": {"status": "cleared", "notes": "All tracks licensed"}, "talent": {"status": "cleared", "notes": "All releases signed"}, "locations": {"status": "pending", "notes": "Awaiting location permits"}},
            "reference_study_library": {"studies": []},
            "interactive_modules": {"automated_dailies_selects": {"items": []}, "provider_execution": {"status": "planning_only", "live_mode": False}},
            "producer_dashboard": {"last_updated": "", "dailies_count": 3, "screening_status": "pending", "priority_focus": ["Scene 3 pacing", "Dialogue clarity"], "blockers": ["Awaiting dailies from render farm"]},
            "project_dashboard": {"cards": [
                {"id": "development", "label": "Development", "status": "complete", "progress": 100, "detail": "Script locked"},
                {"id": "preproduction", "label": "Pre-Production", "status": "active", "progress": 75, "detail": "Casting complete"},
                {"id": "production", "label": "Production", "status": "active", "progress": 40, "detail": "Day 12 of shooting"},
                {"id": "postproduction", "label": "Post-Production", "status": "pending", "progress": 0, "detail": "Editorial begins May 1"},
            ]},
            "agent_activity_timeline": [
                {"agent_id": "director", "event": "Approved Scene 1-3 dailies", "timestamp": ""},
                {"agent_id": "cinematographer", "event": "Generated coverage options for Scene 5", "timestamp": ""},
            ],
            "continuity_register": {"last_checked": "", "open_issues": 2, "issues": [
                {"id": "c001", "scene": "Scene 3", "type": "prop", "description": "Coffee mug position changed between shots"},
                {"id": "c002", "scene": "Scene 7", "type": "lighting", "description": "Exterior daylight shift not matched"},
            ]},
            "risk_register": ["Render farm capacity at 85%", "Actor availability conflict in Week 3"],
            "next_actions": ["Approve Scene 4 dailies", "Review continuity report", "Confirm VFX vendor"]
        }
        
        project = StudioProject(**project_data)
        self.save_project(project)

    def get_all_projects(self) -> dict[str, StudioProject]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT project_id, data FROM projects ORDER BY updated_at DESC")
            return {row["project_id"]: StudioProject(**json.loads(row["data"])) for row in cursor.fetchall()}

    def get_project(self, project_id: str) -> Optional[StudioProject]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM projects WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            if row:
                return StudioProject(**json.loads(row["data"]))
            return None

    def save_project(self, project: StudioProject) -> StudioProject:
        project.updated_at = datetime.now().isoformat()
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO projects (project_id, data, created_at, updated_at) 
                   VALUES (?, ?, COALESCE((SELECT created_at FROM projects WHERE project_id = ?), ?), ?)""",
                (project.project_id, json.dumps(project.model_dump(mode='json')), project.project_id, now, project.updated_at)
            )
            conn.commit()
        return project

    def delete_project(self, project_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_project_ids(self) -> list[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT project_id FROM projects ORDER BY updated_at DESC")
            return [row["project_id"] for row in cursor.fetchall()]

    # Render Job Persistence
    def save_job(self, job: RenderJobModel) -> RenderJobModel:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO render_jobs 
                   (id, project_id, shot_id, provider, provider_job_id, status, progress,
                    input_payload, output_payload, error_message, retry_count,
                    created_at, updated_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.id, job.project_id, job.shot_id, job.provider, job.provider_job_id,
                    job.status, job.progress,
                    json.dumps(job.input_payload.model_dump()) if job.input_payload else None,
                    json.dumps(job.output_payload.model_dump()) if job.output_payload else None,
                    job.error_message, job.retry_count,
                    job.created_at, job.updated_at, job.completed_at
                )
            )
            conn.commit()
        return job

    def get_job(self, job_id: str) -> Optional[RenderJobModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM render_jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_job(row)
            return None

    def list_jobs(self, project_id: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> List[RenderJobModel]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM render_jobs"
            params = []
            conditions = []
            if project_id:
                conditions.append("project_id = ?")
                params.append(project_id)
            if status:
                conditions.append("status = ?")
                params.append(status)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            return [self._row_to_job(row) for row in cursor.fetchall()]

    def delete_job(self, job_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM render_jobs WHERE id = ?", (job_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_job(self, row: sqlite3.Row) -> RenderJobModel:
        from app.models import RenderJobInput, RenderJobOutput
        input_payload = None
        output_payload = None
        if row["input_payload"]:
            input_payload = RenderJobInput(**json.loads(row["input_payload"]))
        if row["output_payload"]:
            output_payload = RenderJobOutput(**json.loads(row["output_payload"]))
        return RenderJobModel(
            id=row["id"],
            project_id=row["project_id"],
            shot_id=row["shot_id"],
            provider=row["provider"],
            provider_job_id=row["provider_job_id"],
            status=row["status"],
            progress=row["progress"],
            input_payload=input_payload,
            output_payload=output_payload,
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"]
        )

    # Session management
    def create_session(self, session_id: str, user_id: str, ttl_seconds: int = 86400) -> bool:
        now = datetime.now()
        expires = datetime.fromtimestamp(now.timestamp() + ttl_seconds)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO sessions (session_id, user_id, created_at, expires_at, last_active_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, user_id, now.isoformat(), expires.isoformat(), now.isoformat())
            )
            conn.commit()
        return True

    def get_session(self, session_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE session_id = ? AND expires_at > ?",
                (session_id, datetime.now().isoformat())
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def delete_session(self, session_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0

    def cleanup_expired_sessions(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.now().isoformat(),))
            conn.commit()
            return cursor.rowcount

    # ========================================================================
    # MEMORY PERSISTENCE
    # ========================================================================

    def save_memory_entry(self, entry: Dict) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Get current version
            cursor.execute(
                "SELECT MAX(version) FROM project_memories WHERE entry_id = ?",
                (entry.get("entry_id"),)
            )
            current_version = cursor.fetchone()[0] or 0
            
            new_version = current_version + 1
            
            # Insert new version
            cursor.execute("""
                INSERT INTO project_memories (
                    project_id, memory_type, key, value, summary, scope, scene_id, character_id,
                    created_by_agent, source_task_id, created_at, updated_at, version,
                    confidence, contradicted, contradiction_notes, entry_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.get("project_id"),
                entry.get("memory_type"),
                entry.get("key"),
                entry.get("value"),
                entry.get("summary"),
                entry.get("scope", "global"),
                entry.get("scene_id"),
                entry.get("character_id"),
                entry.get("created_by_agent"),
                entry.get("source_task_id"),
                entry.get("created_at", now),
                now,
                new_version,
                entry.get("confidence", 1.0),
                entry.get("contradicted", 0),
                entry.get("contradiction_notes"),
                entry.get("entry_id")
            ))
            
            # Store version history
            cursor.execute("""
                INSERT INTO memory_versions (
                    entry_id, version, project_id, memory_type, key, value,
                    modified_by, modified_at, change_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.get("entry_id"),
                new_version,
                entry.get("project_id"),
                entry.get("memory_type"),
                entry.get("key"),
                entry.get("value"),
                entry.get("created_by_agent"),
                now,
                entry.get("change_summary", f"Version {new_version}")
            ))
            
            conn.commit()
            return True

    def get_memory_entries(
        self,
        project_id: str,
        memory_type: Optional[str] = None,
        scene_id: Optional[str] = None,
        character_id: Optional[str] = None
    ) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM project_memories WHERE project_id = ?"
            params = [project_id]
            
            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            if scene_id:
                query += " AND scene_id = ?"
                params.append(scene_id)
            if character_id:
                query += " AND character_id = ?"
                params.append(character_id)
            
            query += " ORDER BY version DESC"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_memory_entry(self, entry_id: str, version: Optional[int] = None) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if version:
                cursor.execute(
                    "SELECT * FROM project_memories WHERE entry_id = ? AND version = ?",
                    (entry_id, version)
                )
            else:
                cursor.execute(
                    "SELECT * FROM project_memories WHERE entry_id = ? ORDER BY version DESC LIMIT 1",
                    (entry_id,)
                )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_memory_versions(self, entry_id: str) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM memory_versions WHERE entry_id = ? ORDER BY version ASC",
                (entry_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    # Scene Memory
    def save_scene_memory(self, scene_memory: Dict) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO scene_memories (
                    project_id, scene_id, location_name, time_of_day, weather,
                    camera_choices, lighting_notes, color_palette, props_in_scene,
                    character_positions, generated_shots, approved_shots, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scene_memory.get("project_id"),
                scene_memory.get("scene_id") or scene_memory.get("scene_id", ""),
                scene_memory.get("location_name", ""),
                scene_memory.get("time_of_day", ""),
                scene_memory.get("weather"),
                json.dumps(scene_memory.get("camera_choices", [])),
                json.dumps(scene_memory.get("lighting_notes", [])),
                json.dumps(scene_memory.get("color_palette", [])),
                json.dumps(scene_memory.get("props_in_scene", [])),
                json.dumps(scene_memory.get("character_positions", {})),
                json.dumps(scene_memory.get("generated_shots", [])),
                json.dumps(scene_memory.get("approved_shots", [])),
                now
            ))
            conn.commit()
            return True

    def get_scene_memory(self, project_id: str, scene_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM scene_memories WHERE project_id = ? AND scene_id = ?",
                (project_id, scene_id)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                # Parse JSON fields
                for field in ["camera_choices", "lighting_notes", "color_palette", "props_in_scene", "character_positions", "generated_shots", "approved_shots"]:
                    if result.get(field):
                        result[field] = json.loads(result[field])
                return result
            return None

    def get_all_scene_memories(self, project_id: str) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM scene_memories WHERE project_id = ? ORDER BY scene_id",
                (project_id,)
            )
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                for field in ["camera_choices", "lighting_notes", "color_palette", "props_in_scene", "character_positions", "generated_shots", "approved_shots"]:
                    if result.get(field):
                        result[field] = json.loads(result[field])
                results.append(result)
            return results

    # Character Memory
    def save_character_memory(self, char_memory: Dict) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO character_memories (
                    project_id, character_id, character_name, appearance_traits,
                    personality_traits, speech_patterns, mannerisms, physical_quirks,
                    wardrobe, backstory_notes, relationships, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                char_memory.get("project_id"),
                char_memory.get("character_id"),
                char_memory.get("character_name"),
                json.dumps(char_memory.get("appearance_traits", [])),
                json.dumps(char_memory.get("personality_traits", [])),
                json.dumps(char_memory.get("speech_patterns", [])),
                json.dumps(char_memory.get("mannerisms", [])),
                json.dumps(char_memory.get("physical_quirks", [])),
                json.dumps(char_memory.get("wardrobe", [])),
                json.dumps(char_memory.get("backstory_notes", [])),
                json.dumps(char_memory.get("relationships", {})),
                now
            ))
            conn.commit()
            return True

    def get_character_memory(self, project_id: str, character_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM character_memories WHERE project_id = ? AND character_id = ?",
                (project_id, character_id)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                for field in ["appearance_traits", "personality_traits", "speech_patterns", "mannerisms", "physical_quirks", "wardrobe", "backstory_notes", "relationships"]:
                    if result.get(field):
                        result[field] = json.loads(result[field])
                return result
            return None

    def get_all_character_memories(self, project_id: str) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM character_memories WHERE project_id = ? ORDER BY character_id",
                (project_id,)
            )
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                for field in ["appearance_traits", "personality_traits", "speech_patterns", "mannerisms", "physical_quirks", "wardrobe", "backstory_notes", "relationships"]:
                    if result.get(field):
                        result[field] = json.loads(result[field])
                results.append(result)
            return results

    # Style Memory
    def save_style_memory(self, style_memory: Dict) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO style_memories (
                    project_id, camera_language, lighting_approach, color_palette,
                    pacing_notes, frame_composition, movement_style, lens_preferences, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                style_memory.get("project_id"),
                style_memory.get("camera_language"),
                style_memory.get("lighting_approach"),
                style_memory.get("color_palette"),
                style_memory.get("pacing_notes"),
                style_memory.get("frame_composition"),
                style_memory.get("movement_style"),
                style_memory.get("lens_preferences"),
                now
            ))
            conn.commit()
            return True

    def get_style_memory(self, project_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM style_memories WHERE project_id = ?",
                (project_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    # Review Memory
    def save_review_memory(self, review_memory: Dict) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO review_memories (
                    project_id, scene_id, shot_id, feedback_type, feedback_source,
                    feedback_text, quality_score, issues, recommendations, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                review_memory.get("project_id"),
                review_memory.get("scene_id"),
                review_memory.get("shot_id"),
                review_memory.get("feedback_type"),
                review_memory.get("feedback_source"),
                review_memory.get("feedback_text"),
                review_memory.get("quality_score"),
                json.dumps(review_memory.get("issues", [])),
                json.dumps(review_memory.get("recommendations", [])),
                now
            ))
            conn.commit()
            return True

    def get_review_memories(
        self,
        project_id: str,
        scene_id: Optional[str] = None,
        shot_id: Optional[str] = None
    ) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM review_memories WHERE project_id = ?"
            params = [project_id]
            
            if scene_id:
                query += " AND scene_id = ?"
                params.append(scene_id)
            if shot_id:
                query += " AND shot_id = ?"
                params.append(shot_id)
            
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get("issues"):
                    result["issues"] = json.loads(result["issues"])
                if result.get("recommendations"):
                    result["recommendations"] = json.loads(result["recommendations"])
                results.append(result)
            return results

    # =========================================================================
    # CREW TASK PERSISTENCE (for Orchestrator)
    # =========================================================================

    def create_crew_task(self, task_data: Dict) -> Dict:
        """
        Create a new crew task in the database.
        
        Args:
            task_data: Dict with task fields
            
        Returns:
            Created task with task_id
        """
        task_id = task_data.get("task_id", f"task-{uuid4().hex[:12]}")
        now = datetime.now().isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO crew_tasks (
                    task_id, project_id, agent_role, task_type, title, description,
                    status, priority, depends_on, input_data, output_data,
                    error_message, retry_count, progress, created_at, updated_at,
                    started_at, completed_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id,
                task_data.get("project_id"),
                task_data.get("agent_role"),
                task_data.get("task_type"),
                task_data.get("title"),
                task_data.get("description"),
                task_data.get("status", "created"),
                task_data.get("priority", 5),
                json.dumps(task_data.get("depends_on", [])),
                json.dumps(task_data.get("input_data", {})),
                json.dumps(task_data.get("output_data", {})),
                task_data.get("error_message"),
                task_data.get("retry_count", 0),
                task_data.get("progress", 0),
                now,
                now,
                task_data.get("started_at"),
                task_data.get("completed_at"),
                task_data.get("created_by", "system"),
            ))
            conn.commit()
        
        # Log task creation
        self._log_crew_task_action(task_id, task_data.get("project_id"), "created", task_data.get("agent_role"))
        
        return self.get_crew_task(task_id)

    def get_crew_task(self, task_id: str) -> Optional[Dict]:
        """Get a single crew task by ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crew_tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_crew_task(row)
            return None

    def get_crew_tasks(self, project_id: str, status: Optional[str] = None) -> List[Dict]:
        """
        Get all crew tasks for a project.
        
        Args:
            project_id: Project ID
            status: Optional filter by status
            
        Returns:
            List of crew tasks
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM crew_tasks WHERE project_id = ? AND status = ? ORDER BY priority DESC, created_at ASC",
                    (project_id, status)
                )
            else:
                cursor.execute(
                    "SELECT * FROM crew_tasks WHERE project_id = ? ORDER BY priority DESC, created_at ASC",
                    (project_id,)
                )
            
            return [self._row_to_crew_task(row) for row in cursor.fetchall()]

    def update_crew_task_status(
        self,
        task_id: str,
        status: str,
        output_data: Optional[Dict] = None,
        error: Optional[str] = None,
        retry_count: Optional[int] = None
    ) -> bool:
        """
        Update task status and optionally set output or error.
        
        Args:
            task_id: Task ID
            status: New status
            output_data: Optional output data (for completed tasks)
            error: Optional error message
            retry_count: Optional retry count
            
        Returns:
            True if updated
        """
        now = datetime.now().isoformat()
        
        # Get current task for logging
        task = self.get_crew_task(task_id)
        if not task:
            return False
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Build update query dynamically
            updates = ["status = ?", "updated_at = ?"]
            params = [status, now]
            
            if status == "in_progress" and not task.get("started_at"):
                updates.append("started_at = ?")
                params.append(now)
            
            if status == "completed":
                updates.append("completed_at = ?")
                params.append(now)
            
            if output_data is not None:
                updates.append("output_data = ?")
                params.append(json.dumps(output_data))
            
            if error is not None:
                updates.append("error_message = ?")
                params.append(error)
            
            if retry_count is not None:
                updates.append("retry_count = ?")
                params.append(retry_count)
            
            params.append(task_id)
            
            cursor.execute(
                f"UPDATE crew_tasks SET {', '.join(updates)} WHERE task_id = ?",
                params
            )
            conn.commit()
        
        # Log status change
        self._log_crew_task_action(task_id, task.get("project_id"), f"status:{status}", task.get("agent_role"))
        
        return True

    def update_crew_task(self, task_id: str, updates: Dict) -> bool:
        """Update arbitrary fields on a task"""
        now = datetime.now().isoformat()
        
        # Get current task
        task = self.get_crew_task(task_id)
        if not task:
            return False
        
        set_clauses = ["updated_at = ?"]
        params = [now]
        
        for key, value in updates.items():
            if key in ["title", "description", "priority", "agent_role", "task_type"]:
                set_clauses.append(f"{key} = ?")
                params.append(value)
            elif key == "depends_on":
                set_clauses.append("depends_on = ?")
                params.append(json.dumps(value))
            elif key == "input_data":
                set_clauses.append("input_data = ?")
                params.append(json.dumps(value))
        
        params.append(task_id)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE crew_tasks SET {', '.join(set_clauses)} WHERE task_id = ?",
                params
            )
            conn.commit()
        
        return True

    def delete_crew_task(self, task_id: str) -> bool:
        """Delete a crew task"""
        task = self.get_crew_task(task_id)
        if not task:
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM crew_tasks WHERE task_id = ?", (task_id,))
            conn.commit()
        
        self._log_crew_task_action(task_id, task.get("project_id"), "deleted", task.get("agent_role"))
        return True

    def get_crew_task_log(self, project_id: str, limit: int = 100) -> List[Dict]:
        """Get execution log for a project"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM crew_task_log 
                WHERE project_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (project_id, limit))
            
            return [dict(row) for row in cursor.fetchall()]

    def _row_to_crew_task(self, row: sqlite3.Row) -> Dict:
        """Convert a database row to a crew task dict"""
        result = dict(row)
        
        # Parse JSON fields
        if result.get("depends_on"):
            result["depends_on"] = json.loads(result["depends_on"])
        else:
            result["depends_on"] = []
        
        if result.get("input_data"):
            result["input_data"] = json.loads(result["input_data"])
        else:
            result["input_data"] = {}
        
        if result.get("output_data"):
            result["output_data"] = json.loads(result["output_data"])
        else:
            result["output_data"] = {}
        
        return result

    def _log_crew_task_action(self, task_id: str, project_id: str, action: str, agent_role: str = None):
        """Log a crew task action"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO crew_task_log (task_id, project_id, action, agent_role, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (task_id, project_id, action, agent_role, datetime.now().isoformat()))
            conn.commit()


class JsonFileStorage:
    """Legacy file-based JSON storage - kept for backwards compatibility only"""

    def __init__(self, storage_path: str):
        import warnings
        warnings.warn("JsonFileStorage is deprecated for production use", DeprecationWarning)
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.projects_file = self.storage_path / "projects.json"
        self._ensure_initial_data()

    def _ensure_initial_data(self):
        if not self.projects_file.exists():
            default_data = {
                "proj-001": {
                    "project_id": "proj-001",
                    "title": "Neon Dreams",
                    "updated_at": "",
                    "source_stats": {"scene_count": 12, "shot_count": 48, "render_count": 18, "character_count": 7, "word_count": 4200, "target_runtime_minutes": 94},
                    "render_provider": {"provider_name": "Simulated Provider", "provider_model": "GPU Cluster", "status": "running", "mode": "batch", "live_mode": False},
                    "production_bible": {"creative_intent": "Neo-noir thriller"},
                    "render_provider_integrations": [{"provider": "Simulated", "selected": True, "status": "active", "live_generation": "enabled", "requires": []}],
                    "crew_agents": [],
                    "shot_approval_gates": [],
                    "storyboard_wall": [],
                    "render_queue": [],
                    "rights_safety_clearance_board": {"overall_status": "pending"},
                    "reference_study_library": {"studies": []},
                    "interactive_modules": None,
                    "producer_dashboard": None,
                    "project_dashboard": None,
                    "agent_activity_timeline": [],
                    "continuity_register": None,
                    "risk_register": [],
                    "next_actions": []
                }
            }
            self._save_data(default_data)

    def _load_data(self) -> dict:
        if self.projects_file.exists():
            with open(self.projects_file) as f:
                return json.load(f)
        return {}

    def _save_data(self, data: dict):
        with open(self.projects_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_all_projects(self) -> dict[str, StudioProject]:
        data = self._load_data()
        return {k: StudioProject(**v) for k, v in data.items()}

    def get_project(self, project_id: str) -> Optional[StudioProject]:
        data = self._load_data()
        if project_id in data:
            return StudioProject(**data[project_id])
        return None

    def save_project(self, project: StudioProject) -> StudioProject:
        data = self._load_data()
        data[project.project_id] = project.model_dump(mode='json')
        self._save_data(data)
        return project

    def delete_project(self, project_id: str) -> bool:
        data = self._load_data()
        if project_id in data:
            del data[project_id]
            self._save_data(data)
            return True
        return False

    def list_project_ids(self) -> list[str]:
        data = self._load_data()
        return list(data.keys())


def get_storage(storage_type: str = "sqlite", **kwargs) -> Any:
    """Factory function to get storage implementation
    
    Args:
        storage_type: One of 'sqlite', 'json', 'postgres'
        **kwargs: Additional options (storage_path, connection_string)
    
    Returns:
        Storage implementation matching StorageInterface
    
    Note:
        - SQLite is recommended for development and single-server deployment
        - PostgreSQL requires SQLAlchemy setup (see docs for migration)
        - JSON storage is deprecated and only for backwards compatibility
    """
    if storage_type == "sqlite":
        return DatabaseStorage(kwargs.get("storage_path", "/Users/amberreed/Enhanced_adaptive_strategy_python/studio-backend/data"))
    elif storage_type == "json":
        return JsonFileStorage(kwargs.get("storage_path", "/Users/amberreed/Enhanced_adaptive_strategy_python/studio-backend/data"))
    elif storage_type == "postgres":
        raise NotImplementedError(
            "PostgreSQL storage requires SQLAlchemy setup. "
            "Use DatabaseStorage (SQLite) for development, "
            "or configure SQLAlchemy with asyncpg for production."
        )
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")


class DatabaseStoragePostgres:
    """PostgreSQL storage - scaffold for production deployment (not implemented)"""
    
    def __init__(self, connection_string: str):
        raise NotImplementedError(
            "PostgreSQL storage requires SQLAlchemy setup. "
            "Use DatabaseStorage (SQLite) for development."
        )
    
    def get_all_projects(self) -> dict[str, StudioProject]:
        raise NotImplementedError

    def get_project(self, project_id: str) -> Optional[StudioProject]:
        raise NotImplementedError

    def save_project(self, project: StudioProject) -> StudioProject:
        raise NotImplementedError

    def delete_project(self, project_id: str) -> bool:
        raise NotImplementedError

    def list_project_ids(self) -> list[str]:
        raise NotImplementedError
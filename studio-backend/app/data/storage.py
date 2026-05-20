import json
import sqlite3
import os
import sys
import logging
from pathlib import Path
from typing import Optional, Any, List, Dict
from datetime import datetime
from contextlib import contextmanager
from queue import Queue
import threading
import time

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
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _execute_write_with_retry(self, operation_name: str, operation):
        """Execute a write operation with retry on transient sqlite lock errors."""
        max_attempts = 3
        backoff_seconds = 0.05
        for attempt in range(1, max_attempts + 1):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                lock_error = "database is locked" in message or "database table is locked" in message
                if not lock_error or attempt >= max_attempts:
                    raise
                logger.warning(
                    "SQLite lock during %s (attempt %s/%s); retrying",
                    operation_name,
                    attempt,
                    max_attempts,
                )
                time.sleep(backoff_seconds * attempt)

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
            (7, "Add visual embeddings and cinematic memory tables", """
                CREATE TABLE IF NOT EXISTS visual_embeddings (
                    embedding_id TEXT PRIMARY KEY,
                    keyframe_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'unavailable',
                    model TEXT NOT NULL DEFAULT 'unconfigured',
                    vector_dimension INTEGER NOT NULL DEFAULT 0,
                    embedding_vector TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'unavailable',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (embedding_id != ''),
                    CHECK (keyframe_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_visual_embeddings_keyframe ON visual_embeddings(keyframe_id);
                CREATE INDEX IF NOT EXISTS idx_visual_embeddings_asset ON visual_embeddings(asset_id);
                CREATE INDEX IF NOT EXISTS idx_visual_embeddings_project ON visual_embeddings(project_id);
                CREATE INDEX IF NOT EXISTS idx_visual_embeddings_status ON visual_embeddings(status);

                CREATE TABLE IF NOT EXISTS cinematic_memory_records (
                    memory_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    keyframe_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL DEFAULT '',
                    embedding_id TEXT NOT NULL DEFAULT '',
                    memory_type TEXT NOT NULL DEFAULT 'keyframe_memory',
                    summary TEXT NOT NULL DEFAULT '',
                    visual_tags TEXT NOT NULL DEFAULT '[]',
                    emotional_tags TEXT NOT NULL DEFAULT '[]',
                    composition_tags TEXT NOT NULL DEFAULT '[]',
                    lighting_tags TEXT NOT NULL DEFAULT '[]',
                    searchable_text TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (memory_id != ''),
                    CHECK (project_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (keyframe_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_cinematic_memory_project ON cinematic_memory_records(project_id);
                CREATE INDEX IF NOT EXISTS idx_cinematic_memory_asset ON cinematic_memory_records(asset_id);
                CREATE INDEX IF NOT EXISTS idx_cinematic_memory_keyframe ON cinematic_memory_records(keyframe_id);
            """),
            (8, "Add continuity/style/director/shot-boundary persistence tables", """
                CREATE TABLE IF NOT EXISTS continuity_issues (
                    issue_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_keyframe_id TEXT,
                    compared_keyframe_id TEXT,
                    asset_id TEXT,
                    source_asset_id TEXT,
                    compared_asset_id TEXT,
                    issue_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    description TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    recommendation TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (issue_id != ''),
                    CHECK (project_id != ''),
                    CHECK (issue_type != '')
                );

                CREATE INDEX IF NOT EXISTS idx_continuity_issues_project ON continuity_issues(project_id);
                CREATE INDEX IF NOT EXISTS idx_continuity_issues_type ON continuity_issues(project_id, issue_type);

                CREATE TABLE IF NOT EXISTS style_signatures (
                    signature_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    framing_tendencies TEXT NOT NULL DEFAULT '[]',
                    pacing_patterns TEXT NOT NULL DEFAULT '[]',
                    color_motifs TEXT NOT NULL DEFAULT '[]',
                    camera_movement_patterns TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (signature_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_style_signatures_project ON style_signatures(project_id);

                CREATE TABLE IF NOT EXISTS director_signatures (
                    signature_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    dominant_mood_tags TEXT NOT NULL DEFAULT '[]',
                    dominant_lighting_tags TEXT NOT NULL DEFAULT '[]',
                    dominant_composition_tags TEXT NOT NULL DEFAULT '[]',
                    dominant_palette TEXT NOT NULL DEFAULT '[]',
                    pacing_notes TEXT NOT NULL DEFAULT '',
                    visual_language_summary TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    evidence_keyframe_ids TEXT NOT NULL DEFAULT '[]',
                    evidence_memory_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (signature_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_director_signatures_project ON director_signatures(project_id);

                CREATE TABLE IF NOT EXISTS style_drift_issues (
                    drift_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    keyframe_id TEXT NOT NULL DEFAULT '',
                    asset_id TEXT NOT NULL DEFAULT '',
                    drift_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    description TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    recommendation TEXT NOT NULL DEFAULT '',
                    compared_against_signature_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (drift_id != ''),
                    CHECK (project_id != ''),
                    CHECK (drift_type != '')
                );

                CREATE INDEX IF NOT EXISTS idx_style_drift_project ON style_drift_issues(project_id);
                CREATE INDEX IF NOT EXISTS idx_style_drift_type ON style_drift_issues(project_id, drift_type);

                CREATE TABLE IF NOT EXISTS director_commentary_records (
                    commentary_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    scene_reference TEXT NOT NULL DEFAULT '',
                    interpretation TEXT NOT NULL DEFAULT '',
                    emotional_read TEXT NOT NULL DEFAULT '',
                    visual_language_notes TEXT NOT NULL DEFAULT '',
                    pacing_notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (commentary_id != ''),
                    CHECK (asset_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_director_commentary_asset ON director_commentary_records(asset_id);

                CREATE TABLE IF NOT EXISTS shot_boundaries (
                    boundary_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    start_time REAL NOT NULL DEFAULT 0.0,
                    end_time REAL NOT NULL DEFAULT 0.0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    transition_type TEXT NOT NULL DEFAULT 'hard_cut',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (boundary_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (end_time >= start_time)
                );

                CREATE INDEX IF NOT EXISTS idx_shot_boundaries_asset ON shot_boundaries(asset_id);
            """),
            (9, "Add semantic video scene memory table", """
                CREATE TABLE IF NOT EXISTS video_scene_memories (
                    memory_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    dominant_mood TEXT NOT NULL DEFAULT 'neutral',
                    visual_style TEXT NOT NULL DEFAULT 'observational',
                    lighting_style TEXT NOT NULL DEFAULT 'naturalistic',
                    pacing_profile TEXT NOT NULL DEFAULT 'moderate',
                    character_presence TEXT NOT NULL DEFAULT '[]',
                    composition_patterns TEXT NOT NULL DEFAULT '[]',
                    cinematic_notes TEXT NOT NULL DEFAULT '',
                    embeddings TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    CHECK (memory_id != ''),
                    CHECK (asset_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_video_scene_memories_asset ON video_scene_memories(asset_id);
                CREATE INDEX IF NOT EXISTS idx_video_scene_memories_created ON video_scene_memories(created_at);
            """),
            (10, "Add review/revision/package/workflow/keyframe-analysis persistence tables", """
                CREATE TABLE IF NOT EXISTS short_film_reviews (
                    review_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    output_url TEXT NOT NULL,
                    decision TEXT NOT NULL DEFAULT 'pending',
                    reviewer TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (review_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_short_film_reviews_project ON short_film_reviews(project_id);
                CREATE INDEX IF NOT EXISTS idx_short_film_reviews_created ON short_film_reviews(created_at);

                CREATE TABLE IF NOT EXISTS clip_revisions (
                    revision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    review_id TEXT NOT NULL,
                    original_job_id TEXT NOT NULL,
                    new_job_id TEXT,
                    provider TEXT NOT NULL,
                    revision_prompt TEXT NOT NULL DEFAULT '',
                    revision_reason TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    output_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (revision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (review_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_clip_revisions_project ON clip_revisions(project_id);
                CREATE INDEX IF NOT EXISTS idx_clip_revisions_review ON clip_revisions(review_id);
                CREATE INDEX IF NOT EXISTS idx_clip_revisions_created ON clip_revisions(created_at);

                CREATE TABLE IF NOT EXISTS final_short_film_packages (
                    package_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    film_title TEXT NOT NULL,
                    final_output_url TEXT NOT NULL,
                    final_output_path TEXT,
                    review_id TEXT,
                    review_decision TEXT NOT NULL DEFAULT 'pending',
                    runtime_seconds REAL,
                    scene_count INTEGER NOT NULL DEFAULT 0,
                    shot_count INTEGER NOT NULL DEFAULT 0,
                    render_job_ids TEXT NOT NULL DEFAULT '[]',
                    revision_ids TEXT NOT NULL DEFAULT '[]',
                    has_title_card INTEGER NOT NULL DEFAULT 0 CHECK (has_title_card IN (0, 1)),
                    has_end_card INTEGER NOT NULL DEFAULT 0 CHECK (has_end_card IN (0, 1)),
                    has_soundtrack INTEGER NOT NULL DEFAULT 0 CHECK (has_soundtrack IN (0, 1)),
                    package_status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (package_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_final_short_film_packages_project ON final_short_film_packages(project_id);
                CREATE INDEX IF NOT EXISTS idx_final_short_film_packages_created ON final_short_film_packages(created_at);

                CREATE TABLE IF NOT EXISTS workflow_executions (
                    execution_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    started_at TEXT,
                    completed_at TEXT,
                    current_step TEXT,
                    completed_steps TEXT NOT NULL DEFAULT '[]',
                    failed_steps TEXT NOT NULL DEFAULT '[]',
                    step_results TEXT NOT NULL DEFAULT '{}',
                    inputs TEXT NOT NULL DEFAULT '{}',
                    outputs TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT,
                    progress_percentage REAL NOT NULL DEFAULT 0.0,
                    CHECK (execution_id != ''),
                    CHECK (workflow_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_executions_project ON workflow_executions(project_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_executions_workflow ON workflow_executions(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status);

                CREATE TABLE IF NOT EXISTS video_keyframes (
                    keyframe_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'unknown',
                    timestamp_seconds REAL NOT NULL DEFAULT 0.0,
                    image_path TEXT NOT NULL DEFAULT '',
                    image_url TEXT,
                    frame_index INTEGER NOT NULL DEFAULT 0,
                    width INTEGER,
                    height INTEGER,
                    extraction_method TEXT NOT NULL DEFAULT 'interval',
                    frame_path TEXT,
                    frame_url TEXT,
                    extraction_reason TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (keyframe_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_video_keyframes_asset ON video_keyframes(asset_id);
                CREATE INDEX IF NOT EXISTS idx_video_keyframes_project ON video_keyframes(project_id);
                CREATE INDEX IF NOT EXISTS idx_video_keyframes_timestamp ON video_keyframes(asset_id, timestamp_seconds);

                CREATE TABLE IF NOT EXISTS video_frame_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    keyframe_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    caption TEXT NOT NULL DEFAULT '',
                    visual_summary TEXT NOT NULL DEFAULT '',
                    mood_tags TEXT NOT NULL DEFAULT '[]',
                    lighting_tags TEXT NOT NULL DEFAULT '[]',
                    composition_tags TEXT NOT NULL DEFAULT '[]',
                    color_palette TEXT NOT NULL DEFAULT '[]',
                    detected_subjects TEXT NOT NULL DEFAULT '[]',
                    camera_notes TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    provider TEXT NOT NULL DEFAULT 'unavailable',
                    model TEXT NOT NULL DEFAULT 'unconfigured',
                    status TEXT NOT NULL DEFAULT 'unavailable',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    camera_tags TEXT NOT NULL DEFAULT '[]',
                    embeddings TEXT,
                    CHECK (analysis_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_video_frame_analyses_asset ON video_frame_analyses(asset_id);
                CREATE INDEX IF NOT EXISTS idx_video_frame_analyses_project ON video_frame_analyses(project_id);
                CREATE INDEX IF NOT EXISTS idx_video_frame_analyses_keyframe ON video_frame_analyses(keyframe_id);
            """),
            (11, "Add video asset persistence table", """
                CREATE TABLE IF NOT EXISTS video_assets (
                    asset_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    local_path TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    duration_seconds REAL,
                    file_size_bytes INTEGER,
                    status TEXT NOT NULL DEFAULT 'registered',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (asset_id != ''),
                    CHECK (project_id != ''),
                    CHECK (source_type != '')
                );

                CREATE INDEX IF NOT EXISTS idx_video_assets_project ON video_assets(project_id);
                CREATE INDEX IF NOT EXISTS idx_video_assets_source_type ON video_assets(source_type);
                CREATE INDEX IF NOT EXISTS idx_video_assets_updated ON video_assets(updated_at);
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
        payload = json.dumps(project.model_dump(mode='json'))

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                columns = [row["name"] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()]
                has_created_at = "created_at" in columns
                has_updated_at = "updated_at" in columns

                if has_created_at and has_updated_at:
                    cursor.execute(
                        """INSERT OR REPLACE INTO projects (project_id, data, created_at, updated_at)
                           VALUES (?, ?, COALESCE((SELECT created_at FROM projects WHERE project_id = ?), ?), ?)""",
                        (project.project_id, payload, project.project_id, now, project.updated_at),
                    )
                elif has_updated_at:
                    cursor.execute(
                        "INSERT OR REPLACE INTO projects (project_id, data, updated_at) VALUES (?, ?, ?)",
                        (project.project_id, payload, project.updated_at),
                    )
                else:
                    cursor.execute(
                        "INSERT OR REPLACE INTO projects (project_id, data) VALUES (?, ?)",
                        (project.project_id, payload),
                    )
                conn.commit()

        self._execute_write_with_retry("save_project", _write)
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

    # =========================================================================
    # VISUAL EMBEDDINGS + CINEMATIC MEMORY PERSISTENCE
    # =========================================================================

    def save_visual_embedding(self, embedding) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO visual_embeddings (
                    embedding_id, keyframe_id, asset_id, project_id, provider, model,
                    vector_dimension, embedding_vector, status, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    embedding.embedding_id,
                    embedding.keyframe_id,
                    embedding.asset_id,
                    embedding.project_id,
                    embedding.provider,
                    embedding.model,
                    embedding.vector_dimension,
                    json.dumps(embedding.embedding_vector or []),
                    embedding.status,
                    embedding.created_at,
                    json.dumps(embedding.metadata or {}),
                ),
            )
            conn.commit()
        return embedding

    def _row_to_visual_embedding(self, row: sqlite3.Row):
        from app.models import VisualEmbedding

        return VisualEmbedding(
            embedding_id=row["embedding_id"],
            keyframe_id=row["keyframe_id"],
            asset_id=row["asset_id"],
            project_id=row["project_id"],
            provider=row["provider"] or "unavailable",
            model=row["model"] or "unconfigured",
            vector_dimension=int(row["vector_dimension"] or 0),
            embedding_vector=json.loads(row["embedding_vector"] or "[]"),
            status=row["status"] or "unavailable",
            created_at=row["created_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def get_visual_embedding(self, embedding_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM visual_embeddings WHERE embedding_id = ?", (embedding_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_visual_embedding(row)
            return None

    def get_visual_embedding_for_keyframe(self, keyframe_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM visual_embeddings
                WHERE keyframe_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (keyframe_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_visual_embedding(row)
            return None

    def list_visual_embeddings_for_asset(self, asset_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM visual_embeddings WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_visual_embedding(row) for row in cursor.fetchall()]

    def list_visual_embeddings_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM visual_embeddings WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_visual_embedding(row) for row in cursor.fetchall()]

    def list_visual_embeddings(self, limit: int = 5000) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM visual_embeddings ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            )
            return [self._row_to_visual_embedding(row) for row in cursor.fetchall()]

    def delete_visual_embeddings_for_asset(self, asset_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM visual_embeddings WHERE asset_id = ?", (asset_id,))
            conn.commit()
            return cursor.rowcount

    def save_cinematic_memory_record(self, record):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO cinematic_memory_records (
                    memory_id, project_id, asset_id, keyframe_id, analysis_id, embedding_id,
                    memory_type, summary, visual_tags, emotional_tags, composition_tags,
                    lighting_tags, searchable_text, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.memory_id,
                    record.project_id,
                    record.asset_id,
                    record.keyframe_id,
                    record.analysis_id or "",
                    record.embedding_id or "",
                    record.memory_type or "keyframe_memory",
                    record.summary or "",
                    json.dumps(record.visual_tags or []),
                    json.dumps(record.emotional_tags or []),
                    json.dumps(record.composition_tags or []),
                    json.dumps(record.lighting_tags or []),
                    record.searchable_text or "",
                    record.created_at,
                    json.dumps(record.metadata or {}),
                ),
            )
            conn.commit()
        return record

    def _row_to_cinematic_memory_record(self, row: sqlite3.Row):
        from app.models import CinematicMemoryRecord

        return CinematicMemoryRecord(
            memory_id=row["memory_id"],
            project_id=row["project_id"],
            asset_id=row["asset_id"],
            keyframe_id=row["keyframe_id"],
            analysis_id=row["analysis_id"] or "",
            embedding_id=row["embedding_id"] or "",
            memory_type=row["memory_type"] or "keyframe_memory",
            summary=row["summary"] or "",
            visual_tags=json.loads(row["visual_tags"] or "[]"),
            emotional_tags=json.loads(row["emotional_tags"] or "[]"),
            composition_tags=json.loads(row["composition_tags"] or "[]"),
            lighting_tags=json.loads(row["lighting_tags"] or "[]"),
            searchable_text=row["searchable_text"] or "",
            created_at=row["created_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def get_cinematic_memory_record(self, memory_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cinematic_memory_records WHERE memory_id = ?", (memory_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_cinematic_memory_record(row)
            return None

    def list_cinematic_memory_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cinematic_memory_records WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_cinematic_memory_record(row) for row in cursor.fetchall()]

    def list_cinematic_memory_records_for_project(self, project_id: str) -> List[Any]:
        return self.list_cinematic_memory_for_project(project_id)

    def list_cinematic_memory_records_for_asset(self, asset_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cinematic_memory_records WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_cinematic_memory_record(row) for row in cursor.fetchall()]

    def list_cinematic_memory_records(self, limit: int = 5000) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cinematic_memory_records ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            )
            return [self._row_to_cinematic_memory_record(row) for row in cursor.fetchall()]

    def delete_cinematic_memory_records_for_project(self, project_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cinematic_memory_records WHERE project_id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount

    def save_continuity_issue(self, issue):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO continuity_issues (
                    issue_id, project_id, source_keyframe_id, compared_keyframe_id, asset_id,
                    source_asset_id, compared_asset_id, issue_type, severity, confidence,
                    description, evidence, recommendation, notes, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issue.issue_id,
                    issue.project_id,
                    issue.source_keyframe_id,
                    issue.compared_keyframe_id,
                    issue.asset_id,
                    issue.source_asset_id,
                    issue.compared_asset_id,
                    issue.issue_type,
                    issue.severity,
                    issue.confidence,
                    issue.description,
                    issue.evidence,
                    issue.recommendation,
                    issue.notes,
                    json.dumps(issue.metadata or {}),
                    issue.created_at,
                ),
            )
            conn.commit()
        return issue

    def _row_to_continuity_issue(self, row: sqlite3.Row):
        from app.models import ContinuityIssue

        return ContinuityIssue(
            issue_id=row["issue_id"],
            project_id=row["project_id"],
            source_keyframe_id=row["source_keyframe_id"],
            compared_keyframe_id=row["compared_keyframe_id"],
            asset_id=row["asset_id"],
            source_asset_id=row["source_asset_id"],
            compared_asset_id=row["compared_asset_id"],
            issue_type=row["issue_type"],
            severity=row["severity"] or "medium",
            confidence=float(row["confidence"] or 0.0),
            description=row["description"] or "",
            evidence=row["evidence"] or "",
            recommendation=row["recommendation"] or "",
            notes=row["notes"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"] or "",
        )

    def list_continuity_issues_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM continuity_issues WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_continuity_issue(row) for row in cursor.fetchall()]

    def delete_continuity_issues_for_project(self, project_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM continuity_issues WHERE project_id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount

    def save_style_signature(self, signature):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO style_signatures (
                    signature_id, project_id, framing_tendencies, pacing_patterns, color_motifs,
                    camera_movement_patterns, confidence, advisory_only, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signature.signature_id,
                    signature.project_id,
                    json.dumps(signature.framing_tendencies or []),
                    json.dumps(signature.pacing_patterns or []),
                    json.dumps(signature.color_motifs or []),
                    json.dumps(signature.camera_movement_patterns or []),
                    signature.confidence,
                    1 if signature.advisory_only else 0,
                    json.dumps(signature.metadata or {}),
                    signature.created_at,
                ),
            )
            conn.commit()
        return signature

    def _row_to_style_signature(self, row: sqlite3.Row):
        from app.models import StyleSignature

        return StyleSignature(
            signature_id=row["signature_id"],
            project_id=row["project_id"],
            framing_tendencies=json.loads(row["framing_tendencies"] or "[]"),
            pacing_patterns=json.loads(row["pacing_patterns"] or "[]"),
            color_motifs=json.loads(row["color_motifs"] or "[]"),
            camera_movement_patterns=json.loads(row["camera_movement_patterns"] or "[]"),
            confidence=float(row["confidence"] or 0.0),
            advisory_only=bool(row["advisory_only"]),
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"] or "",
        )

    def list_style_signatures_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM style_signatures WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_style_signature(row) for row in cursor.fetchall()]

    def get_style_signature(self, signature_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM style_signatures WHERE signature_id = ?", (signature_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_style_signature(row)
            return None

    def get_latest_style_signature(self, project_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM style_signatures WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_style_signature(row)
            return None

    def save_director_signature(self, signature):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO director_signatures (
                    signature_id, project_id, dominant_mood_tags, dominant_lighting_tags,
                    dominant_composition_tags, dominant_palette, pacing_notes, visual_language_summary,
                    confidence, evidence_keyframe_ids, evidence_memory_ids, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signature.signature_id,
                    signature.project_id,
                    json.dumps(signature.dominant_mood_tags or []),
                    json.dumps(signature.dominant_lighting_tags or []),
                    json.dumps(signature.dominant_composition_tags or []),
                    json.dumps(signature.dominant_palette or []),
                    signature.pacing_notes or "",
                    signature.visual_language_summary or "",
                    signature.confidence,
                    json.dumps(signature.evidence_keyframe_ids or []),
                    json.dumps(signature.evidence_memory_ids or []),
                    signature.created_at,
                    json.dumps(signature.metadata or {}),
                ),
            )
            conn.commit()
        return signature

    def _row_to_director_signature(self, row: sqlite3.Row):
        from app.models import DirectorSignature

        return DirectorSignature(
            signature_id=row["signature_id"],
            project_id=row["project_id"],
            dominant_mood_tags=json.loads(row["dominant_mood_tags"] or "[]"),
            dominant_lighting_tags=json.loads(row["dominant_lighting_tags"] or "[]"),
            dominant_composition_tags=json.loads(row["dominant_composition_tags"] or "[]"),
            dominant_palette=json.loads(row["dominant_palette"] or "[]"),
            pacing_notes=row["pacing_notes"] or "",
            visual_language_summary=row["visual_language_summary"] or "",
            confidence=float(row["confidence"] or 0.0),
            evidence_keyframe_ids=json.loads(row["evidence_keyframe_ids"] or "[]"),
            evidence_memory_ids=json.loads(row["evidence_memory_ids"] or "[]"),
            created_at=row["created_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def list_director_signatures_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM director_signatures WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_director_signature(row) for row in cursor.fetchall()]

    def get_latest_director_signature(self, project_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM director_signatures WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_director_signature(row)
            return None

    def save_style_drift_issue(self, issue):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO style_drift_issues (
                    drift_id, project_id, keyframe_id, asset_id, drift_type, severity,
                    confidence, description, evidence, recommendation, compared_against_signature_id,
                    created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issue.drift_id,
                    issue.project_id,
                    issue.keyframe_id or "",
                    issue.asset_id or "",
                    issue.drift_type,
                    issue.severity,
                    issue.confidence,
                    issue.description or "",
                    issue.evidence or "",
                    issue.recommendation or "",
                    issue.compared_against_signature_id or "",
                    issue.created_at,
                    json.dumps(issue.metadata or {}),
                ),
            )
            conn.commit()
        return issue

    def _row_to_style_drift_issue(self, row: sqlite3.Row):
        from app.models import StyleDriftIssue

        return StyleDriftIssue(
            drift_id=row["drift_id"],
            project_id=row["project_id"],
            keyframe_id=row["keyframe_id"] or "",
            asset_id=row["asset_id"] or "",
            drift_type=row["drift_type"],
            severity=row["severity"] or "medium",
            confidence=float(row["confidence"] or 0.0),
            description=row["description"] or "",
            evidence=row["evidence"] or "",
            recommendation=row["recommendation"] or "",
            compared_against_signature_id=row["compared_against_signature_id"] or "",
            created_at=row["created_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def list_style_drift_issues_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM style_drift_issues WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_style_drift_issue(row) for row in cursor.fetchall()]

    def delete_style_drift_issues_for_project(self, project_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM style_drift_issues WHERE project_id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount

    def save_director_commentary(self, commentary):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO director_commentary_records (
                    commentary_id, asset_id, scene_reference, interpretation, emotional_read,
                    visual_language_notes, pacing_notes, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commentary.commentary_id,
                    commentary.asset_id,
                    commentary.scene_reference or "",
                    commentary.interpretation or "",
                    commentary.emotional_read or "",
                    commentary.visual_language_notes or "",
                    commentary.pacing_notes or "",
                    commentary.created_at,
                    json.dumps(commentary.metadata or {}),
                ),
            )
            conn.commit()
        return commentary

    def _row_to_director_commentary(self, row: sqlite3.Row):
        from app.models import DirectorCommentary

        return DirectorCommentary(
            commentary_id=row["commentary_id"],
            asset_id=row["asset_id"],
            scene_reference=row["scene_reference"] or "",
            interpretation=row["interpretation"] or "",
            emotional_read=row["emotional_read"] or "",
            visual_language_notes=row["visual_language_notes"] or "",
            pacing_notes=row["pacing_notes"] or "",
            created_at=row["created_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def list_director_commentary_for_asset(self, asset_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM director_commentary_records WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_director_commentary(row) for row in cursor.fetchall()]

    def delete_director_commentary_for_asset(self, asset_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM director_commentary_records WHERE asset_id = ?", (asset_id,))
            conn.commit()
            return cursor.rowcount

    def save_shot_boundary(self, boundary):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO shot_boundaries (
                    boundary_id, asset_id, start_time, end_time, confidence, transition_type, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    boundary.boundary_id,
                    boundary.asset_id,
                    boundary.start_time,
                    boundary.end_time,
                    boundary.confidence,
                    boundary.transition_type,
                    json.dumps(boundary.metadata or {}),
                ),
            )
            conn.commit()
        return boundary

    def _row_to_shot_boundary(self, row: sqlite3.Row):
        from app.models import ShotBoundary

        return ShotBoundary(
            boundary_id=row["boundary_id"],
            asset_id=row["asset_id"],
            start_time=float(row["start_time"] or 0.0),
            end_time=float(row["end_time"] or 0.0),
            confidence=float(row["confidence"] or 0.0),
            transition_type=row["transition_type"] or "hard_cut",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def list_shot_boundaries_for_asset(self, asset_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM shot_boundaries WHERE asset_id = ? ORDER BY start_time ASC",
                (asset_id,),
            )
            return [self._row_to_shot_boundary(row) for row in cursor.fetchall()]

    def delete_shot_boundaries_for_asset(self, asset_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM shot_boundaries WHERE asset_id = ?", (asset_id,))
            conn.commit()
            return cursor.rowcount

    def save_video_scene_memory(self, memory):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO video_scene_memories (
                    memory_id, asset_id, dominant_mood, visual_style, lighting_style,
                    pacing_profile, character_presence, composition_patterns,
                    cinematic_notes, embeddings, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.memory_id,
                    memory.asset_id,
                    memory.dominant_mood,
                    memory.visual_style,
                    memory.lighting_style,
                    memory.pacing_profile,
                    json.dumps(memory.character_presence or []),
                    json.dumps(memory.composition_patterns or []),
                    memory.cinematic_notes or "",
                    json.dumps(memory.embeddings or []),
                    memory.created_at,
                ),
            )
            conn.commit()
        return memory

    def _row_to_video_scene_memory(self, row: sqlite3.Row):
        from app.models import SceneMemoryRecord

        return SceneMemoryRecord(
            memory_id=row["memory_id"],
            asset_id=row["asset_id"],
            dominant_mood=row["dominant_mood"] or "neutral",
            visual_style=row["visual_style"] or "observational",
            lighting_style=row["lighting_style"] or "naturalistic",
            pacing_profile=row["pacing_profile"] or "moderate",
            character_presence=json.loads(row["character_presence"] or "[]"),
            composition_patterns=json.loads(row["composition_patterns"] or "[]"),
            cinematic_notes=row["cinematic_notes"] or "",
            embeddings=json.loads(row["embeddings"] or "[]"),
            created_at=row["created_at"] or "",
        )

    def get_video_scene_memory(self, memory_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_scene_memories WHERE memory_id = ?", (memory_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_video_scene_memory(row)
            return None

    def list_video_scene_memories_for_asset(self, asset_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_scene_memories WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_video_scene_memory(row) for row in cursor.fetchall()]

    def list_video_scene_memories(self, limit: int = 100) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_scene_memories ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            )
            return [self._row_to_video_scene_memory(row) for row in cursor.fetchall()]

    # =========================================================================
    # REVIEW / REVISION / PACKAGE / WORKFLOW + VIDEO UNDERSTANDING COMPAT
    # =========================================================================

    def save_review(self, review) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO short_film_reviews (
                    review_id, project_id, output_url, decision, reviewer, notes,
                    created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.project_id,
                    review.output_url,
                    review.decision,
                    review.reviewer or "",
                    review.notes or "",
                    review.created_at,
                    review.updated_at,
                    json.dumps(review.metadata or {}),
                ),
            )
            conn.commit()
        return review

    def _row_to_short_film_review(self, row: sqlite3.Row):
        from app.models import ShortFilmReview

        return ShortFilmReview(
            review_id=row["review_id"],
            project_id=row["project_id"],
            output_url=row["output_url"],
            decision=row["decision"] or "pending",
            reviewer=row["reviewer"] or "",
            notes=row["notes"] or "",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def get_review(self, review_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM short_film_reviews WHERE review_id = ?", (review_id,))
            row = cursor.fetchone()
            return self._row_to_short_film_review(row) if row else None

    def list_reviews_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM short_film_reviews WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            )
            return [self._row_to_short_film_review(row) for row in cursor.fetchall()]

    def update_review(self, review) -> Any:
        return self.save_review(review)

    def save_clip_revision(self, revision) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO clip_revisions (
                    revision_id, project_id, review_id, original_job_id, new_job_id, provider,
                    revision_prompt, revision_reason, status, output_url, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision.revision_id,
                    revision.project_id,
                    revision.review_id,
                    revision.original_job_id,
                    revision.new_job_id,
                    revision.provider,
                    revision.revision_prompt,
                    revision.revision_reason,
                    revision.status,
                    revision.output_url,
                    revision.created_at,
                    revision.updated_at,
                    json.dumps(revision.metadata or {}),
                ),
            )
            conn.commit()
        return revision

    def _row_to_clip_revision(self, row: sqlite3.Row):
        from app.models import ClipRevision

        return ClipRevision(
            revision_id=row["revision_id"],
            project_id=row["project_id"],
            review_id=row["review_id"],
            original_job_id=row["original_job_id"],
            new_job_id=row["new_job_id"],
            provider=row["provider"],
            revision_prompt=row["revision_prompt"] or "",
            revision_reason=row["revision_reason"] or "",
            status=row["status"] or "pending",
            output_url=row["output_url"],
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def get_clip_revision(self, revision_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clip_revisions WHERE revision_id = ?", (revision_id,))
            row = cursor.fetchone()
            return self._row_to_clip_revision(row) if row else None

    def list_clip_revisions_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM clip_revisions WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            )
            return [self._row_to_clip_revision(row) for row in cursor.fetchall()]

    def list_clip_revisions_for_review(self, review_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM clip_revisions WHERE review_id = ? ORDER BY created_at ASC",
                (review_id,),
            )
            return [self._row_to_clip_revision(row) for row in cursor.fetchall()]

    def update_clip_revision(self, revision) -> Any:
        return self.save_clip_revision(revision)

    def save_final_short_film_package(self, package) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO final_short_film_packages (
                    package_id, project_id, film_title, final_output_url, final_output_path,
                    review_id, review_decision, runtime_seconds, scene_count, shot_count,
                    render_job_ids, revision_ids, has_title_card, has_end_card, has_soundtrack,
                    package_status, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    package.package_id,
                    package.project_id,
                    package.film_title,
                    package.final_output_url,
                    package.final_output_path,
                    package.review_id,
                    package.review_decision,
                    package.runtime_seconds,
                    int(package.scene_count or 0),
                    int(package.shot_count or 0),
                    json.dumps(package.render_job_ids or []),
                    json.dumps(package.revision_ids or []),
                    1 if package.has_title_card else 0,
                    1 if package.has_end_card else 0,
                    1 if package.has_soundtrack else 0,
                    package.package_status,
                    package.created_at,
                    package.updated_at,
                    json.dumps(package.metadata or {}),
                ),
            )
            conn.commit()
        return package

    def _row_to_final_short_film_package(self, row: sqlite3.Row):
        from app.models import FinalShortFilmPackage

        return FinalShortFilmPackage(
            package_id=row["package_id"],
            project_id=row["project_id"],
            film_title=row["film_title"] or "",
            final_output_url=row["final_output_url"] or "",
            final_output_path=row["final_output_path"],
            review_id=row["review_id"],
            review_decision=row["review_decision"] or "pending",
            runtime_seconds=row["runtime_seconds"],
            scene_count=int(row["scene_count"] or 0),
            shot_count=int(row["shot_count"] or 0),
            render_job_ids=json.loads(row["render_job_ids"] or "[]"),
            revision_ids=json.loads(row["revision_ids"] or "[]"),
            has_title_card=bool(row["has_title_card"]),
            has_end_card=bool(row["has_end_card"]),
            has_soundtrack=bool(row["has_soundtrack"]),
            package_status=row["package_status"] or "draft",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def get_final_short_film_package(self, package_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM final_short_film_packages WHERE package_id = ?", (package_id,))
            row = cursor.fetchone()
            return self._row_to_final_short_film_package(row) if row else None

    def list_final_short_film_packages_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM final_short_film_packages WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            )
            return [self._row_to_final_short_film_package(row) for row in cursor.fetchall()]

    def update_final_short_film_package(self, package) -> Any:
        return self.save_final_short_film_package(package)

    def save_workflow_execution(self, execution) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO workflow_executions (
                    execution_id, workflow_id, project_id, status, started_at, completed_at,
                    current_step, completed_steps, failed_steps, step_results, inputs, outputs,
                    error_message, progress_percentage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.execution_id,
                    execution.workflow_id,
                    execution.project_id,
                    execution.status,
                    execution.started_at,
                    execution.completed_at,
                    execution.current_step,
                    json.dumps(execution.completed_steps or []),
                    json.dumps(execution.failed_steps or []),
                    json.dumps(execution.step_results or {}, default=str),
                    json.dumps(execution.inputs or {}, default=str),
                    json.dumps(execution.outputs or {}, default=str),
                    execution.error_message,
                    float(execution.progress_percentage or 0.0),
                ),
            )
            conn.commit()
        return execution

    def _row_to_workflow_execution(self, row: sqlite3.Row):
        from app.models import WorkflowExecution

        return WorkflowExecution(
            execution_id=row["execution_id"],
            workflow_id=row["workflow_id"],
            project_id=row["project_id"],
            status=row["status"] or "pending",
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            current_step=row["current_step"],
            completed_steps=json.loads(row["completed_steps"] or "[]"),
            failed_steps=json.loads(row["failed_steps"] or "[]"),
            step_results=json.loads(row["step_results"] or "{}"),
            inputs=json.loads(row["inputs"] or "{}"),
            outputs=json.loads(row["outputs"] or "{}"),
            error_message=row["error_message"],
            progress_percentage=float(row["progress_percentage"] or 0.0),
        )

    def get_workflow_execution(self, execution_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflow_executions WHERE execution_id = ?", (execution_id,))
            row = cursor.fetchone()
            return self._row_to_workflow_execution(row) if row else None

    def list_workflow_executions(self, project_id: Optional[str] = None) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute(
                    "SELECT * FROM workflow_executions WHERE project_id = ? ORDER BY started_at DESC",
                    (project_id,),
                )
            else:
                cursor.execute("SELECT * FROM workflow_executions ORDER BY started_at DESC")
            return [self._row_to_workflow_execution(row) for row in cursor.fetchall()]

    def save_video_keyframe(self, keyframe) -> Any:
        params = (
            keyframe.keyframe_id,
            keyframe.asset_id,
            keyframe.project_id,
            keyframe.source_type or "unknown",
            float(keyframe.timestamp_seconds or 0.0),
            keyframe.image_path or keyframe.frame_path or "",
            keyframe.image_url or keyframe.frame_url,
            int(keyframe.frame_index or 0),
            keyframe.width,
            keyframe.height,
            keyframe.extraction_method or keyframe.extraction_reason or "interval",
            keyframe.frame_path or keyframe.image_path,
            keyframe.frame_url or keyframe.image_url,
            keyframe.extraction_reason or keyframe.extraction_method or "interval",
            keyframe.created_at,
            json.dumps(keyframe.metadata or {}),
        )
        for attempt in range(4):
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO video_keyframes (
                            keyframe_id, asset_id, project_id, source_type, timestamp_seconds,
                            image_path, image_url, frame_index, width, height, extraction_method,
                            frame_path, frame_url, extraction_reason, created_at, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        params,
                    )
                    conn.commit()
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == 3:
                    raise
                time.sleep(0.05 * (attempt + 1))
        return keyframe

    def save_video_asset(self, asset) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO video_assets (
                    asset_id, project_id, source_type, source_url, local_path, title, description,
                    duration_seconds, file_size_bytes, status, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.asset_id,
                    asset.project_id,
                    asset.source_type,
                    asset.source_url,
                    asset.local_path,
                    asset.title,
                    asset.description,
                    asset.duration_seconds,
                    asset.file_size_bytes,
                    asset.status,
                    asset.created_at,
                    asset.updated_at,
                    json.dumps(asset.metadata or {}),
                ),
            )
            conn.commit()
        return asset

    def update_video_asset(self, asset) -> Any:
        return self.save_video_asset(asset)

    def _row_to_video_asset(self, row: sqlite3.Row):
        from app.models.video_assets import VideoAsset

        return VideoAsset(
            asset_id=row["asset_id"],
            project_id=row["project_id"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            local_path=row["local_path"],
            title=row["title"] or "",
            description=row["description"],
            duration_seconds=float(row["duration_seconds"]) if row["duration_seconds"] is not None else None,
            file_size_bytes=int(row["file_size_bytes"]) if row["file_size_bytes"] is not None else None,
            status=row["status"] or "registered",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def get_video_asset(self, asset_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_assets WHERE asset_id = ?", (asset_id,))
            row = cursor.fetchone()
            return self._row_to_video_asset(row) if row else None

    def list_video_assets_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_assets WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            )
            return [self._row_to_video_asset(row) for row in cursor.fetchall()]

    def list_video_assets(self, source_type: Optional[str] = None, limit: int = 5000) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if source_type:
                cursor.execute(
                    "SELECT * FROM video_assets WHERE source_type = ? ORDER BY updated_at DESC LIMIT ?",
                    (source_type, max(1, int(limit))),
                )
            else:
                cursor.execute(
                    "SELECT * FROM video_assets ORDER BY updated_at DESC LIMIT ?",
                    (max(1, int(limit)),),
                )
            return [self._row_to_video_asset(row) for row in cursor.fetchall()]

    def _row_to_video_keyframe(self, row: sqlite3.Row):
        from app.models import VideoKeyframe

        return VideoKeyframe(
            keyframe_id=row["keyframe_id"],
            asset_id=row["asset_id"],
            project_id=row["project_id"],
            source_type=row["source_type"] or "unknown",
            timestamp_seconds=float(row["timestamp_seconds"] or 0.0),
            image_path=row["image_path"] or "",
            image_url=row["image_url"],
            frame_index=int(row["frame_index"] or 0),
            width=row["width"],
            height=row["height"],
            extraction_method=row["extraction_method"] or "interval",
            frame_path=row["frame_path"] or row["image_path"] or "",
            frame_url=row["frame_url"] or row["image_url"],
            extraction_reason=row["extraction_reason"] or row["extraction_method"] or "interval",
            created_at=row["created_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def get_video_keyframe(self, keyframe_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_keyframes WHERE keyframe_id = ?", (keyframe_id,))
            row = cursor.fetchone()
            return self._row_to_video_keyframe(row) if row else None

    def list_video_keyframes_for_asset(self, asset_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_keyframes WHERE asset_id = ? ORDER BY timestamp_seconds ASC",
                (asset_id,),
            )
            return [self._row_to_video_keyframe(row) for row in cursor.fetchall()]

    def list_video_keyframes_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_keyframes WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_video_keyframe(row) for row in cursor.fetchall()]

    def delete_video_keyframes_for_asset(self, asset_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM video_keyframes WHERE asset_id = ?", (asset_id,))
            conn.commit()
            return cursor.rowcount

    def save_video_frame_analysis(self, analysis) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO video_frame_analyses (
                    analysis_id, keyframe_id, asset_id, project_id, caption, visual_summary,
                    mood_tags, lighting_tags, composition_tags, color_palette, detected_subjects,
                    camera_notes, confidence, provider, model, status, created_at, metadata,
                    camera_tags, embeddings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.analysis_id,
                    analysis.keyframe_id,
                    analysis.asset_id,
                    analysis.project_id,
                    analysis.caption or "",
                    analysis.visual_summary or "",
                    json.dumps(analysis.mood_tags or []),
                    json.dumps(analysis.lighting_tags or []),
                    json.dumps(analysis.composition_tags or []),
                    json.dumps(analysis.color_palette or []),
                    json.dumps(analysis.detected_subjects or []),
                    analysis.camera_notes or "",
                    float(analysis.confidence or 0.0),
                    analysis.provider or "unavailable",
                    analysis.model or "unconfigured",
                    analysis.status or "unavailable",
                    analysis.created_at,
                    json.dumps(analysis.metadata or {}),
                    json.dumps(analysis.camera_tags or []),
                    json.dumps(analysis.embeddings) if analysis.embeddings is not None else None,
                ),
            )
            conn.commit()
        return analysis

    def save_frame_analysis(self, analysis) -> Any:
        return self.save_video_frame_analysis(analysis)

    def _row_to_frame_analysis_record(self, row: sqlite3.Row):
        from app.models import FrameAnalysisRecord

        embeddings_raw = row["embeddings"]
        return FrameAnalysisRecord(
            analysis_id=row["analysis_id"],
            keyframe_id=row["keyframe_id"],
            asset_id=row["asset_id"],
            project_id=row["project_id"],
            caption=row["caption"] or "",
            visual_summary=row["visual_summary"] or "",
            mood_tags=json.loads(row["mood_tags"] or "[]"),
            lighting_tags=json.loads(row["lighting_tags"] or "[]"),
            composition_tags=json.loads(row["composition_tags"] or "[]"),
            color_palette=json.loads(row["color_palette"] or "[]"),
            detected_subjects=json.loads(row["detected_subjects"] or "[]"),
            camera_notes=row["camera_notes"] or "",
            confidence=float(row["confidence"] or 0.0),
            provider=row["provider"] or "unavailable",
            model=row["model"] or "unconfigured",
            status=row["status"] or "unavailable",
            created_at=row["created_at"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
            camera_tags=json.loads(row["camera_tags"] or "[]"),
            embeddings=json.loads(embeddings_raw) if embeddings_raw else None,
        )

    def get_frame_analysis(self, analysis_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_frame_analyses WHERE analysis_id = ?", (analysis_id,))
            row = cursor.fetchone()
            return self._row_to_frame_analysis_record(row) if row else None

    def list_frame_analyses_for_asset(self, asset_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_frame_analyses WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_frame_analysis_record(row) for row in cursor.fetchall()]

    def list_video_frame_analyses_for_asset(self, asset_id: str) -> List[Any]:
        return self.list_frame_analyses_for_asset(asset_id)

    def list_frame_analyses_for_project(self, project_id: str) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_frame_analyses WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_frame_analysis_record(row) for row in cursor.fetchall()]

    def list_video_frame_analyses(self, limit: int = 5000) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_frame_analyses ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            )
            return [self._row_to_frame_analysis_record(row) for row in cursor.fetchall()]


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
    default_storage_path = os.getenv("STUDIO_STORAGE_PATH")
    if not default_storage_path:
        if os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
            default_storage_path = str(Path("/tmp") / f"studio-backend-pytest-{os.getpid()}")
        else:
            default_storage_path = str(Path(__file__).resolve().parents[2] / "data")
    if storage_type == "sqlite":
        return DatabaseStorage(kwargs.get("storage_path", default_storage_path))
    elif storage_type == "json":
        return JsonFileStorage(kwargs.get("storage_path", default_storage_path))
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

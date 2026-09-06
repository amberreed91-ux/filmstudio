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
from uuid import uuid4

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

    def save_error_report(self, report: dict[str, Any]) -> None:
        raise NotImplementedError

    # Universe Knowledge Graph
    def get_universe_nodes(self, project_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def save_universe_node(self, node: Dict[str, Any]) -> bool:
        raise NotImplementedError

    def delete_universe_node(self, node_id: str) -> bool:
        raise NotImplementedError

    def get_universe_relationships(self, project_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def save_universe_relationship(self, rel: Dict[str, Any]) -> bool:
        raise NotImplementedError

    def delete_universe_relationship(self, relationship_id: str) -> bool:
        raise NotImplementedError

    def delete_universe_project_data(self, project_id: str) -> bool:
        raise NotImplementedError

    def list_universe_project_ids(self) -> List[str]:
        raise NotImplementedError


class DatabaseStorage:
    """SQLite storage with connection pooling and WAL mode."""

    def __init__(self, storage_path: str, pool_size: int = 10):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "studio.db"
        self._pool_size = pool_size
        self._pool: list[sqlite3.Connection] = []
        self._pool_lock = threading.Lock()
        self._closed = False
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
        """Get a connection from the pool, or create a new one."""
        conn = None
        from_pool = False
        try:
            with self._pool_lock:
                if self._pool:
                    conn = self._pool.pop()
                    from_pool = True
                    # Validate connection is still alive
                    try:
                        conn.execute("SELECT 1")
                    except Exception:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = None
                        from_pool = False

            if conn is None and not self._closed:
                conn = self._create_connection()

            yield conn
        finally:
            # A failed write (or an early return) must not leave a transaction
            # holding SQLite's writer lock inside the idle connection pool.
            if conn and conn.in_transaction:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    logger.exception("Discarding connection after transaction cleanup failed")
                    conn.close()
                    conn = None
            if conn and not self._closed:
                try:
                    with self._pool_lock:
                        if len(self._pool) < self._pool_size:
                            self._pool.append(conn)
                            conn = None  # Prevent close below
                        else:
                            pass  # Pool full, close below
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def close(self):
        """Drain the connection pool on shutdown."""
        self._closed = True
        with self._pool_lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()

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
            (12, "Add continuity graph persistence tables", """
                CREATE TABLE IF NOT EXISTS continuity_graphs (
                    film_id TEXT PRIMARY KEY,
                    graph_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    CHECK (film_id != '')
                );

                CREATE TABLE IF NOT EXISTS continuity_graph_versions (
                    version_id TEXT PRIMARY KEY,
                    film_id TEXT NOT NULL,
                    graph_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (version_id != ''),
                    CHECK (film_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_continuity_graph_versions_film ON continuity_graph_versions(film_id);
                CREATE INDEX IF NOT EXISTS idx_continuity_graph_versions_created ON continuity_graph_versions(film_id, created_at);
            """),
            (13, "Add film DNA persistence table", """
                CREATE TABLE IF NOT EXISTS film_dna (
                    film_id TEXT PRIMARY KEY,
                    dna_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    CHECK (film_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_film_dna_updated ON film_dna(updated_at);
            """),
            (14, "Add session debriefs persistence table", """
                CREATE TABLE IF NOT EXISTS session_debriefs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    session_start TEXT NOT NULL,
                    session_end TEXT NOT NULL,
                    debrief_json TEXT NOT NULL DEFAULT '{}',
                    generated_at TEXT NOT NULL,
                    CHECK (id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_session_debriefs_project ON session_debriefs(project_id);
                CREATE INDEX IF NOT EXISTS idx_session_debriefs_generated ON session_debriefs(generated_at);
            """),
            (15, "Add export packages persistence table", """
                CREATE TABLE IF NOT EXISTS export_packages (
                    package_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    package_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (package_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_export_packages_project ON export_packages(project_id);
                CREATE INDEX IF NOT EXISTS idx_export_packages_created ON export_packages(created_at);
            """),
            (16, "Add pitch decks persistence table", """
                CREATE TABLE IF NOT EXISTS pitch_decks (
                    deck_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    deck_json TEXT NOT NULL DEFAULT '{}',
                    target_audience TEXT NOT NULL DEFAULT 'general',
                    created_at TEXT NOT NULL,
                    CHECK (deck_id != ''),
                    CHECK (project_id != ''),
                    CHECK (target_audience IN ('festival', 'investor', 'general'))
                );

                CREATE INDEX IF NOT EXISTS idx_pitch_decks_project ON pitch_decks(project_id);
                CREATE INDEX IF NOT EXISTS idx_pitch_decks_created ON pitch_decks(created_at);
                CREATE INDEX IF NOT EXISTS idx_pitch_decks_audience ON pitch_decks(target_audience);
            """),
            (17, "Add previs_images and surfaced_disagreements tables", """
                CREATE TABLE IF NOT EXISTS previs_images (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    shot_id TEXT,
                    image_path TEXT,
                    job_id TEXT,
                    status TEXT DEFAULT 'pending',
                    prompt_used TEXT,
                    fallback INTEGER DEFAULT 0,
                    created_at TEXT,
                    CHECK (id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_previs_images_project ON previs_images(project_id);
                CREATE INDEX IF NOT EXISTS idx_previs_images_scene ON previs_images(scene_id);
                CREATE INDEX IF NOT EXISTS idx_previs_images_status ON previs_images(status);
                CREATE INDEX IF NOT EXISTS idx_previs_images_job ON previs_images(job_id);

                CREATE TABLE IF NOT EXISTS surfaced_disagreements (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    disagreement_id TEXT NOT NULL,
                    decision_type TEXT,
                    surfaced_at TEXT,
                    dismissed_at TEXT,
                    CHECK (id != ''),
                    CHECK (project_id != ''),
                    CHECK (disagreement_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_surfaced_disagreements_project ON surfaced_disagreements(project_id);
                CREATE INDEX IF NOT EXISTS idx_surfaced_disagreements_type ON surfaced_disagreements(decision_type);
                CREATE INDEX IF NOT EXISTS idx_surfaced_disagreements_surfaced ON surfaced_disagreements(surfaced_at);
            """),
            (18, "Add Universe Knowledge Graph tables", """
                CREATE TABLE IF NOT EXISTS universe_nodes (
                    node_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    first_scene TEXT,
                    last_scene TEXT,
                    universe_tags TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (node_id != ''),
                    CHECK (project_id != ''),
                    CHECK (node_type IN ('character', 'location', 'object', 'lore'))
                );

                CREATE INDEX IF NOT EXISTS idx_universe_nodes_project ON universe_nodes(project_id);
                CREATE INDEX IF NOT EXISTS idx_universe_nodes_type ON universe_nodes(node_type);

                CREATE TABLE IF NOT EXISTS universe_relationships (
                    relationship_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    from_node TEXT NOT NULL,
                    to_node TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    CHECK (relationship_id != ''),
                    CHECK (project_id != ''),
                    CHECK (from_node != ''),
                    CHECK (to_node != ''),
                    FOREIGN KEY (from_node) REFERENCES universe_nodes(node_id) ON DELETE CASCADE,
                    FOREIGN KEY (to_node) REFERENCES universe_nodes(node_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_universe_rels_project ON universe_relationships(project_id);
                CREATE INDEX IF NOT EXISTS idx_universe_rels_from ON universe_relationships(from_node);
                CREATE INDEX IF NOT EXISTS idx_universe_rels_to ON universe_relationships(to_node);
            """),
            (19, "Add study_memories table for persisted Study room Active Memory", """
                CREATE TABLE IF NOT EXISTS study_memories (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_reference TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (project_id != ''),
                    CHECK (category IN ('learned_style', 'tone_rules', 'pacing'))
                );

                CREATE INDEX IF NOT EXISTS idx_study_memories_project ON study_memories(project_id);
                CREATE INDEX IF NOT EXISTS idx_study_memories_category ON study_memories(project_id, category);
            """),
            (20, "Add characters table for persistent character descriptions", """
                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    age TEXT,
                    look TEXT,
                    energy TEXT,
                    core_wound TEXT,
                    core_desire TEXT,
                    relationship_notes TEXT,
                    visual_prompt_summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (project_id != ''),
                    CHECK (name != '')
                );

                CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id);
                CREATE INDEX IF NOT EXISTS idx_characters_project_name ON characters(project_id, name);
            """),
            (21, "Add scene_compositions table for composed scene videos", """
                CREATE TABLE IF NOT EXISTS scene_compositions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    composed_url TEXT NOT NULL,
                    shot_count INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (composed_url != '')
                );

                CREATE INDEX IF NOT EXISTS idx_scene_compositions_project ON scene_compositions(project_id);
                CREATE INDEX IF NOT EXISTS idx_scene_compositions_scene ON scene_compositions(scene_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_scene_compositions_project_scene ON scene_compositions(project_id, scene_id);
            """),
            (22, "Add films table for assembled full films", """
                CREATE TABLE IF NOT EXISTS films (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    film_url TEXT NOT NULL,
                    scene_count INTEGER NOT NULL DEFAULT 0,
                    total_duration_seconds REAL,
                    has_audio INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (project_id != ''),
                    CHECK (film_url != '')
                );

                CREATE INDEX IF NOT EXISTS idx_films_project ON films(project_id);
                CREATE INDEX IF NOT EXISTS idx_films_created ON films(created_at);
            """),
            (23, "Add shots table for render seed locking", """
                CREATE TABLE IF NOT EXISTS shots (
                    project_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    seed INTEGER,
                    seed_locked INTEGER NOT NULL DEFAULT 0 CHECK (seed_locked IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, shot_id),
                    CHECK (project_id != ''),
                    CHECK (shot_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_shots_project ON shots(project_id);
            """),
            (24, "Add seed locking to previs_images table", """
                ALTER TABLE previs_images ADD COLUMN previs_seed INTEGER;
                ALTER TABLE previs_images ADD COLUMN seed_locked INTEGER NOT NULL DEFAULT 0 CHECK (seed_locked IN (0, 1));
                CREATE INDEX IF NOT EXISTS idx_previs_images_seed_locked ON previs_images(seed_locked);
            """),
            (25, "Add updated_at column to previs_images", """
                ALTER TABLE previs_images ADD COLUMN updated_at TEXT DEFAULT (datetime('now'));
            """),
            (26, "Add render_attempts table for prompt-adherence tracking", """
                CREATE TABLE IF NOT EXISTS render_attempts (
                    shot_id TEXT NOT NULL,
                    attempt_n INTEGER NOT NULL,
                    prompt_text TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    adherence_score REAL,
                    score_json TEXT,
                    diff_json TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (shot_id, attempt_n),
                    CHECK (shot_id != ''),
                    CHECK (provider != ''),
                    CHECK (attempt_n >= 1)
                );

                CREATE INDEX IF NOT EXISTS idx_render_attempts_shot ON render_attempts(shot_id);
                CREATE INDEX IF NOT EXISTS idx_render_attempts_created ON render_attempts(created_at);
            """),
            (28, "Add standing_corrections table for slot-level auto-correction rules", """
                CREATE TABLE IF NOT EXISTS standing_corrections (
                    correction_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    trigger_json TEXT NOT NULL DEFAULT '{}',
                    injection_text TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5
                        CHECK (confidence >= 0.0 AND confidence <= 1.0),
                    hits INTEGER NOT NULL DEFAULT 0
                        CHECK (hits >= 0),
                    misses INTEGER NOT NULL DEFAULT 0
                        CHECK (misses >= 0),
                    last_applied TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'probation', 'retired')),
                    CHECK (project_id != ''),
                    CHECK (slot != ''),
                    CHECK (injection_text != '')
                );

                CREATE INDEX IF NOT EXISTS idx_standing_corrections_project
                    ON standing_corrections(project_id);
                CREATE INDEX IF NOT EXISTS idx_standing_corrections_slot
                    ON standing_corrections(project_id, slot);
                CREATE INDEX IF NOT EXISTS idx_standing_corrections_status
                    ON standing_corrections(status);
            """),
            (29, "Add superseded_by column to standing_corrections for merge traceability", """
                ALTER TABLE standing_corrections
                ADD COLUMN superseded_by TEXT;
            """),
            (30, "Add reference_assets table for confirmed reference-asset persistence", """
                CREATE TABLE IF NOT EXISTS reference_assets (
                    ref_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL
                        CHECK (kind IN ('character_face', 'character_full', 'environment', 'style')),
                    image_url TEXT NOT NULL,
                    embedding TEXT,
                    source_shot_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    CHECK (project_id != ''),
                    CHECK (image_url != '')
                );

                CREATE INDEX IF NOT EXISTS idx_reference_assets_project
                    ON reference_assets(project_id);
                CREATE INDEX IF NOT EXISTS idx_reference_assets_source_shot
                    ON reference_assets(project_id, source_shot_id);
            """),
            (27, "Add appearance_core/notes/description_status to characters and character_stagings table", """
                ALTER TABLE characters ADD COLUMN appearance_core TEXT;
                ALTER TABLE characters ADD COLUMN appearance_notes TEXT;
                ALTER TABLE characters ADD COLUMN description_status TEXT NOT NULL DEFAULT 'legacy'
                    CHECK (description_status IN ('legacy','migrated','verified'));

                CREATE TABLE IF NOT EXISTS character_stagings (
                    id TEXT PRIMARY KEY,
                    character_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    shot_id TEXT,
                    staging_prompt TEXT NOT NULL,
                    appearance_override TEXT,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                    UNIQUE (character_id, scene_id, shot_id),
                    CHECK (character_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (staging_prompt != '')
                );

                CREATE INDEX IF NOT EXISTS idx_character_stagings_lookup
                    ON character_stagings(character_id, scene_id, shot_id);
            """),
            (31, "Add elevenlabs_voice_id and elevenlabs_voice_name to characters", """
                ALTER TABLE characters ADD COLUMN elevenlabs_voice_id TEXT;
                ALTER TABLE characters ADD COLUMN elevenlabs_voice_name TEXT;
            """),
            (32, "Add provider-aware voice casting columns to characters", """
                ALTER TABLE characters ADD COLUMN voice_provider TEXT;
                ALTER TABLE characters ADD COLUMN voice_id TEXT;
                ALTER TABLE characters ADD COLUMN voice_name TEXT;
                ALTER TABLE characters ADD COLUMN voice_source_type TEXT;
                ALTER TABLE characters ADD COLUMN voice_style_prompt TEXT;
            """),
            (33, "Add adherence review history columns to render_attempts", """
                ALTER TABLE render_attempts ADD COLUMN mismatch_description TEXT;
                ALTER TABLE render_attempts ADD COLUMN retry_number INTEGER DEFAULT 0;
                ALTER TABLE render_attempts ADD COLUMN outcome TEXT;
                ALTER TABLE render_attempts ADD COLUMN advisory_note TEXT;
            """),
            (34, "Add character reference locks table", """
                CREATE TABLE IF NOT EXISTS character_reference_locks (
                    lock_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    character_name TEXT,
                    source_shot_id TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    lock_status TEXT NOT NULL DEFAULT 'locked'
                        CHECK (lock_status IN ('provisional', 'locked', 'disabled', 'superseded')),
                    provider TEXT,
                    capture_method TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (project_id != ''),
                    CHECK (character_id != ''),
                    CHECK (source_shot_id != ''),
                    CHECK (image_url != '')
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_character_reference_locks_active
                    ON character_reference_locks(project_id, character_id)
                    WHERE lock_status = 'locked';
                CREATE INDEX IF NOT EXISTS idx_character_reference_locks_project
                    ON character_reference_locks(project_id);
                CREATE INDEX IF NOT EXISTS idx_character_reference_locks_source_shot
                    ON character_reference_locks(project_id, source_shot_id);
            """),
            (35, "Allow provisional character reference locks", """
                CREATE TABLE IF NOT EXISTS character_reference_locks_v2 (
                    lock_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    character_name TEXT,
                    source_shot_id TEXT NOT NULL,
                    image_url TEXT NOT NULL,
                    lock_status TEXT NOT NULL DEFAULT 'locked'
                        CHECK (lock_status IN ('provisional', 'locked', 'disabled', 'superseded')),
                    provider TEXT,
                    capture_method TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (project_id != ''),
                    CHECK (character_id != ''),
                    CHECK (source_shot_id != ''),
                    CHECK (image_url != '')
                );
                INSERT OR IGNORE INTO character_reference_locks_v2
                    SELECT lock_id, project_id, character_id, character_name,
                           source_shot_id, image_url, lock_status, provider,
                           capture_method, created_at, updated_at
                    FROM character_reference_locks;
                DROP TABLE character_reference_locks;
                ALTER TABLE character_reference_locks_v2 RENAME TO character_reference_locks;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_character_reference_locks_active
                    ON character_reference_locks(project_id, character_id)
                    WHERE lock_status = 'locked';
                CREATE INDEX IF NOT EXISTS idx_character_reference_locks_project
                    ON character_reference_locks(project_id);
                CREATE INDEX IF NOT EXISTS idx_character_reference_locks_source_shot
                    ON character_reference_locks(project_id, source_shot_id);
            """),
            (36, "Add canonical character identity continuity fields", """
                ALTER TABLE characters ADD COLUMN identity_core_json TEXT;
                ALTER TABLE characters ADD COLUMN default_appearance_json TEXT;
                ALTER TABLE characters ADD COLUMN continuity_state_json TEXT;
                ALTER TABLE characters ADD COLUMN appearance_version_history_json TEXT;
                ALTER TABLE character_reference_locks ADD COLUMN reference_role TEXT DEFAULT 'general';
                ALTER TABLE character_reference_locks ADD COLUMN reliability TEXT DEFAULT 'medium';
                ALTER TABLE character_reference_locks ADD COLUMN source_job_id TEXT;
                ALTER TABLE character_reference_locks ADD COLUMN source_status TEXT DEFAULT 'provisional';
                ALTER TABLE character_reference_locks ADD COLUMN review_status TEXT DEFAULT 'unreviewed';
                ALTER TABLE character_reference_locks ADD COLUMN trace_notes TEXT;
            """),
            (37, "Add canonical storyboard blueprint tables", """
                CREATE TABLE IF NOT EXISTS storyboard_blueprints (
                    blueprint_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    current_version_id TEXT,
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','needs_review','approved','locked','superseded','archived')),
                    approved_version_id TEXT,
                    locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (blueprint_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_storyboard_blueprints_project
                    ON storyboard_blueprints(project_id);
                CREATE INDEX IF NOT EXISTS idx_storyboard_blueprints_scene
                    ON storyboard_blueprints(project_id, scene_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_storyboard_blueprints_project_scene_unique
                    ON storyboard_blueprints(project_id, scene_id);

                CREATE TABLE IF NOT EXISTS storyboard_blueprint_versions (
                    version_id TEXT PRIMARY KEY,
                    blueprint_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','needs_review','approved','locked','superseded','archived')),
                    change_reason TEXT,
                    source_version_id TEXT,
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    inspection_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    approved_by TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (version_id != ''),
                    CHECK (blueprint_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (version_number >= 1)
                );
                CREATE INDEX IF NOT EXISTS idx_storyboard_versions_blueprint
                    ON storyboard_blueprint_versions(blueprint_id);
                CREATE INDEX IF NOT EXISTS idx_storyboard_versions_project_scene
                    ON storyboard_blueprint_versions(project_id, scene_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_storyboard_versions_blueprint_number
                    ON storyboard_blueprint_versions(blueprint_id, version_number);

                CREATE TABLE IF NOT EXISTS storyboard_shots (
                    storyboard_shot_id TEXT PRIMARY KEY,
                    blueprint_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    shot_number INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','ready','approved','locked','rendering','rendered','needs_revision','superseded')),
                    intent_json TEXT NOT NULL DEFAULT '{}',
                    visual_plan_json TEXT NOT NULL DEFAULT '{}',
                    continuity_plan_json TEXT NOT NULL DEFAULT '{}',
                    render_contract_json TEXT NOT NULL DEFAULT '{}',
                    department_notes_json TEXT NOT NULL DEFAULT '[]',
                    storyboard_image_url TEXT,
                    previs_image_id TEXT,
                    rationale TEXT,
                    locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (storyboard_shot_id != ''),
                    CHECK (blueprint_id != ''),
                    CHECK (version_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (shot_id != ''),
                    CHECK (shot_number >= 1)
                );
                CREATE INDEX IF NOT EXISTS idx_storyboard_shots_blueprint
                    ON storyboard_shots(blueprint_id);
                CREATE INDEX IF NOT EXISTS idx_storyboard_shots_version
                    ON storyboard_shots(version_id);
                CREATE INDEX IF NOT EXISTS idx_storyboard_shots_project_scene
                    ON storyboard_shots(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_storyboard_shots_shot_id
                    ON storyboard_shots(project_id, shot_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_storyboard_shots_version_shot
                    ON storyboard_shots(version_id, shot_id);

                CREATE TABLE IF NOT EXISTS storyboard_render_links (
                    link_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    storyboard_shot_id TEXT NOT NULL,
                    blueprint_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    render_job_id TEXT NOT NULL,
                    link_type TEXT NOT NULL DEFAULT 'initial_render',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (link_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (shot_id != ''),
                    CHECK (storyboard_shot_id != ''),
                    CHECK (blueprint_id != ''),
                    CHECK (version_id != ''),
                    CHECK (render_job_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_storyboard_render_links_job
                    ON storyboard_render_links(render_job_id);
                CREATE INDEX IF NOT EXISTS idx_storyboard_render_links_shot
                    ON storyboard_render_links(project_id, shot_id);
                CREATE INDEX IF NOT EXISTS idx_storyboard_render_links_version
                    ON storyboard_render_links(version_id);

                CREATE TABLE IF NOT EXISTS storyboard_revision_links (
                    link_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    original_version_id TEXT NOT NULL,
                    proposed_version_id TEXT,
                    change_scope_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (link_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (shot_id != ''),
                    CHECK (revision_id != ''),
                    CHECK (original_version_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_storyboard_revision_links_revision
                    ON storyboard_revision_links(revision_id);
                CREATE INDEX IF NOT EXISTS idx_storyboard_revision_links_shot
                    ON storyboard_revision_links(project_id, shot_id);
            """),
            (38, "Add production acceptance report persistence", """
                CREATE TABLE IF NOT EXISTS production_acceptance_reports (
                    acceptance_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    package_id TEXT NOT NULL DEFAULT '',
                    disposition TEXT NOT NULL,
                    stale INTEGER NOT NULL DEFAULT 0,
                    blocker_count INTEGER NOT NULL DEFAULT 0,
                    warning_count INTEGER NOT NULL DEFAULT 0,
                    final_output_url TEXT NOT NULL DEFAULT '',
                    acceptance_input_hash TEXT NOT NULL DEFAULT '',
                    report_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    CHECK (acceptance_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_acceptance_project
                    ON production_acceptance_reports(project_id);
                CREATE INDEX IF NOT EXISTS idx_production_acceptance_package
                    ON production_acceptance_reports(package_id);
                CREATE INDEX IF NOT EXISTS idx_production_acceptance_generated
                    ON production_acceptance_reports(generated_at);
            """),
            (39, "Add editorial intelligence analysis and application persistence", """
                CREATE TABLE IF NOT EXISTS editorial_analysis_records (
                    analysis_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_cut_id TEXT NOT NULL,
                    source_package_id TEXT NOT NULL DEFAULT '',
                    context_hash TEXT NOT NULL,
                    analysis_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    CHECK (analysis_id != ''),
                    CHECK (project_id != ''),
                    CHECK (source_cut_id != ''),
                    CHECK (context_hash != '')
                );
                CREATE INDEX IF NOT EXISTS idx_editorial_analysis_project
                    ON editorial_analysis_records(project_id);
                CREATE INDEX IF NOT EXISTS idx_editorial_analysis_created
                    ON editorial_analysis_records(created_at);
                CREATE INDEX IF NOT EXISTS idx_editorial_analysis_project_context
                    ON editorial_analysis_records(project_id, context_hash);

                CREATE TABLE IF NOT EXISTS editorial_decision_applications (
                    application_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    analysis_id TEXT NOT NULL,
                    decision_ids_json TEXT NOT NULL,
                    source_cut_id TEXT NOT NULL,
                    result_cut_id TEXT NOT NULL DEFAULT '',
                    application_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    CHECK (application_id != ''),
                    CHECK (project_id != ''),
                    CHECK (analysis_id != ''),
                    CHECK (source_cut_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_editorial_applications_project
                    ON editorial_decision_applications(project_id);
                CREATE INDEX IF NOT EXISTS idx_editorial_applications_analysis
                    ON editorial_decision_applications(analysis_id);
                CREATE INDEX IF NOT EXISTS idx_editorial_applications_created
                    ON editorial_decision_applications(created_at);
            """),
            (40, "Add production queue persistence", """
                CREATE TABLE IF NOT EXISTS production_queue_items (
                    queue_item_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    work_type TEXT NOT NULL,
                    canonical_type TEXT NOT NULL,
                    canonical_id TEXT,
                    provider TEXT,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 50 CHECK (priority >= 0 AND priority <= 100),
                    idempotency_key TEXT NOT NULL,
                    dependency_policy TEXT NOT NULL DEFAULT 'all_complete',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    failure_json TEXT NOT NULL DEFAULT '{}',
                    reason TEXT NOT NULL DEFAULT '',
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts >= 0),
                    lease_owner TEXT,
                    lease_acquired_at TEXT,
                    lease_expires_at TEXT,
                    next_run_at TEXT,
                    next_poll_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    CHECK (queue_item_id != ''),
                    CHECK (project_id != ''),
                    CHECK (work_type != ''),
                    CHECK (canonical_type != ''),
                    UNIQUE (project_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_production_queue_project_status
                    ON production_queue_items(project_id, status, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_production_queue_ready
                    ON production_queue_items(status, next_run_at, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_production_queue_provider_status
                    ON production_queue_items(provider, status, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_production_queue_lease
                    ON production_queue_items(lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_production_queue_canonical
                    ON production_queue_items(canonical_type, canonical_id);
                CREATE INDEX IF NOT EXISTS idx_production_queue_scene
                    ON production_queue_items(scene_id);
                CREATE INDEX IF NOT EXISTS idx_production_queue_shot
                    ON production_queue_items(shot_id);

                CREATE TABLE IF NOT EXISTS production_queue_dependencies (
                    dependency_id TEXT PRIMARY KEY,
                    queue_item_id TEXT NOT NULL,
                    depends_on_type TEXT NOT NULL,
                    depends_on_id TEXT NOT NULL,
                    required_status TEXT NOT NULL DEFAULT 'complete',
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (dependency_id != ''),
                    CHECK (queue_item_id != ''),
                    CHECK (depends_on_type != ''),
                    CHECK (depends_on_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_queue_dependencies_item
                    ON production_queue_dependencies(queue_item_id);
                CREATE INDEX IF NOT EXISTS idx_production_queue_dependencies_target
                    ON production_queue_dependencies(depends_on_type, depends_on_id);
                CREATE INDEX IF NOT EXISTS idx_production_queue_dependencies_status
                    ON production_queue_dependencies(status);

                CREATE TABLE IF NOT EXISTS production_queue_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    queue_item_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    lease_owner TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_ms INTEGER,
                    error_type TEXT,
                    error_message TEXT,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (attempt_id != ''),
                    CHECK (queue_item_id != ''),
                    CHECK (attempt_number >= 0),
                    CHECK (lease_owner != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_queue_attempts_item
                    ON production_queue_attempts(queue_item_id, attempt_number);
                CREATE INDEX IF NOT EXISTS idx_production_queue_attempts_status
                    ON production_queue_attempts(status);
                CREATE INDEX IF NOT EXISTS idx_production_queue_attempts_started
                    ON production_queue_attempts(started_at);

                CREATE TABLE IF NOT EXISTS production_queue_events (
                    event_id TEXT PRIMARY KEY,
                    queue_item_id TEXT,
                    project_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (event_id != ''),
                    CHECK (project_id != ''),
                    CHECK (event_type != ''),
                    CHECK (stage != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_queue_events_project
                    ON production_queue_events(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_production_queue_events_item
                    ON production_queue_events(queue_item_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_production_queue_events_type
                    ON production_queue_events(event_type, created_at);

                CREATE TABLE IF NOT EXISTS production_queue_policies (
                    policy_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    scope_id TEXT NOT NULL DEFAULT '',
                    max_concurrent_items INTEGER NOT NULL DEFAULT 4,
                    max_concurrent_render_jobs INTEGER NOT NULL DEFAULT 2,
                    provider_limits_json TEXT NOT NULL DEFAULT '{}',
                    polling_policy_json TEXT NOT NULL DEFAULT '{}',
                    retry_policy_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (policy_id != ''),
                    CHECK (scope != '')
                );
            """),
            (41, "Add professional studio workflow persistence", """
                CREATE TABLE IF NOT EXISTS studio_workflow_project_states (
                    project_id TEXT PRIMARY KEY,
                    current_phase TEXT NOT NULL DEFAULT 'intake',
                    workflow_status TEXT NOT NULL DEFAULT 'active',
                    active_version_id TEXT NOT NULL DEFAULT '',
                    active_gate_id TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (project_id != '')
                );

                CREATE TABLE IF NOT EXISTS studio_collaborators (
                    collaborator_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL,
                    permission_scope TEXT NOT NULL DEFAULT 'project',
                    status TEXT NOT NULL DEFAULT 'active',
                    last_seen_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (collaborator_id != ''),
                    CHECK (project_id != ''),
                    CHECK (actor_id != ''),
                    UNIQUE (project_id, actor_id)
                );
                CREATE INDEX IF NOT EXISTS idx_studio_collaborators_project
                    ON studio_collaborators(project_id, role, status);

                CREATE TABLE IF NOT EXISTS studio_artifact_versions (
                    version_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL CHECK (version_number >= 1),
                    status TEXT NOT NULL DEFAULT 'draft',
                    title TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    source_version_id TEXT,
                    canonical_ref_type TEXT NOT NULL DEFAULT '',
                    canonical_ref_id TEXT NOT NULL DEFAULT '',
                    snapshot_json TEXT NOT NULL DEFAULT '{}',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL DEFAULT '',
                    approved_by TEXT NOT NULL DEFAULT '',
                    approved_at TEXT,
                    locked_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (version_id != ''),
                    CHECK (project_id != ''),
                    CHECK (artifact_type != ''),
                    CHECK (artifact_id != ''),
                    UNIQUE (project_id, artifact_type, artifact_id, version_number)
                );
                CREATE INDEX IF NOT EXISTS idx_studio_versions_project_target
                    ON studio_artifact_versions(project_id, artifact_type, artifact_id, version_number);
                CREATE INDEX IF NOT EXISTS idx_studio_versions_status
                    ON studio_artifact_versions(project_id, status, updated_at);

                CREATE TABLE IF NOT EXISTS studio_version_lineage (
                    lineage_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    parent_version_id TEXT NOT NULL,
                    child_version_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    change_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    CHECK (lineage_id != ''),
                    CHECK (project_id != ''),
                    CHECK (parent_version_id != ''),
                    CHECK (child_version_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_lineage_parent
                    ON studio_version_lineage(parent_version_id);
                CREATE INDEX IF NOT EXISTS idx_studio_lineage_child
                    ON studio_version_lineage(child_version_id);

                CREATE TABLE IF NOT EXISTS studio_approval_gates (
                    gate_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    gate_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    version_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    required_role TEXT NOT NULL DEFAULT 'producer',
                    required_decision TEXT NOT NULL DEFAULT 'approve',
                    queue_item_id TEXT,
                    manual_dependency_id TEXT,
                    evidence_policy_json TEXT NOT NULL DEFAULT '{}',
                    latest_evaluation_json TEXT NOT NULL DEFAULT '{}',
                    opened_by TEXT NOT NULL DEFAULT '',
                    closed_by TEXT NOT NULL DEFAULT '',
                    closed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (gate_id != ''),
                    CHECK (project_id != ''),
                    CHECK (gate_type != ''),
                    CHECK (target_type != ''),
                    CHECK (target_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_gates_project_status
                    ON studio_approval_gates(project_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_studio_gates_target
                    ON studio_approval_gates(project_id, target_type, target_id);
                CREATE INDEX IF NOT EXISTS idx_studio_gates_version
                    ON studio_approval_gates(version_id);

                CREATE TABLE IF NOT EXISTS studio_approval_decisions (
                    decision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    gate_id TEXT NOT NULL,
                    version_id TEXT,
                    actor_id TEXT NOT NULL,
                    actor_role TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    rationale TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    CHECK (decision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (gate_id != ''),
                    CHECK (actor_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_decisions_gate
                    ON studio_approval_decisions(gate_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_studio_decisions_project
                    ON studio_approval_decisions(project_id, created_at);

                CREATE TABLE IF NOT EXISTS studio_workflow_comments (
                    comment_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    version_id TEXT,
                    parent_comment_id TEXT,
                    actor_id TEXT NOT NULL,
                    actor_role TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    resolved_by TEXT,
                    resolved_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (comment_id != ''),
                    CHECK (project_id != ''),
                    CHECK (target_type != ''),
                    CHECK (target_id != ''),
                    CHECK (actor_id != ''),
                    CHECK (body != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_comments_target
                    ON studio_workflow_comments(project_id, target_type, target_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_studio_comments_version
                    ON studio_workflow_comments(version_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_studio_comments_status
                    ON studio_workflow_comments(project_id, status, created_at);

                CREATE TABLE IF NOT EXISTS studio_workflow_tasks (
                    workflow_task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    target_type TEXT NOT NULL DEFAULT '',
                    target_id TEXT NOT NULL DEFAULT '',
                    version_id TEXT,
                    assignee_actor_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    queue_item_id TEXT,
                    due_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (workflow_task_id != ''),
                    CHECK (project_id != ''),
                    CHECK (title != ''),
                    CHECK (task_type != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_tasks_project_status
                    ON studio_workflow_tasks(project_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_studio_tasks_target
                    ON studio_workflow_tasks(project_id, target_type, target_id);

                CREATE TABLE IF NOT EXISTS studio_workflow_events (
                    event_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL DEFAULT '',
                    target_type TEXT NOT NULL DEFAULT '',
                    target_id TEXT NOT NULL DEFAULT '',
                    version_id TEXT,
                    gate_id TEXT,
                    decision_id TEXT,
                    message TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (event_id != ''),
                    CHECK (project_id != ''),
                    CHECK (event_type != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_events_project
                    ON studio_workflow_events(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_studio_events_gate
                    ON studio_workflow_events(gate_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_studio_events_version
                    ON studio_workflow_events(version_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_studio_events_target
                    ON studio_workflow_events(project_id, target_type, target_id, created_at);
            """),
            (42, "Add advanced crew intelligence persistence", """
                CREATE TABLE IF NOT EXISTS crew_reasoning_records (
                    reasoning_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT,
                    workflow_execution_id TEXT,
                    agent_role TEXT NOT NULL,
                    department_name TEXT NOT NULL,
                    reasoning_type TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    asset_id TEXT,
                    render_job_id TEXT,
                    package_id TEXT,
                    observation TEXT NOT NULL DEFAULT '',
                    context_used TEXT NOT NULL DEFAULT '[]',
                    inference TEXT NOT NULL DEFAULT '',
                    recommendation_summary TEXT NOT NULL DEFAULT '',
                    creator_note TEXT NOT NULL DEFAULT '',
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    memory_refs TEXT NOT NULL DEFAULT '[]',
                    spine_refs TEXT NOT NULL DEFAULT '[]',
                    risks TEXT NOT NULL DEFAULT '[]',
                    recommendations TEXT NOT NULL DEFAULT '[]',
                    downstream_departments TEXT NOT NULL DEFAULT '[]',
                    requires_creator_decision INTEGER NOT NULL DEFAULT 0 CHECK (requires_creator_decision IN (0, 1)),
                    escalation_reason TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    confidence_label TEXT NOT NULL DEFAULT 'emerging',
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    trace_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (reasoning_id != ''),
                    CHECK (project_id != ''),
                    CHECK (agent_role != ''),
                    CHECK (reasoning_type != '')
                );
                CREATE INDEX IF NOT EXISTS idx_crew_reasoning_project
                    ON crew_reasoning_records(project_id);
                CREATE INDEX IF NOT EXISTS idx_crew_reasoning_task
                    ON crew_reasoning_records(task_id);
                CREATE INDEX IF NOT EXISTS idx_crew_reasoning_role
                    ON crew_reasoning_records(project_id, agent_role);
                CREATE INDEX IF NOT EXISTS idx_crew_reasoning_scene
                    ON crew_reasoning_records(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_crew_reasoning_attention
                    ON crew_reasoning_records(project_id, requires_creator_decision);
                CREATE INDEX IF NOT EXISTS idx_crew_reasoning_created
                    ON crew_reasoning_records(project_id, created_at);

                CREATE TABLE IF NOT EXISTS crew_handoff_packets (
                    handoff_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_role TEXT NOT NULL,
                    target_role TEXT NOT NULL,
                    source_task_id TEXT,
                    target_task_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    asset_id TEXT,
                    context_summary TEXT NOT NULL DEFAULT '',
                    requirements TEXT NOT NULL DEFAULT '[]',
                    open_questions TEXT NOT NULL DEFAULT '[]',
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    memory_refs TEXT NOT NULL DEFAULT '[]',
                    spine_refs TEXT NOT NULL DEFAULT '[]',
                    risks TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'created',
                    acknowledged_by TEXT,
                    acknowledged_at TEXT,
                    completed_at TEXT,
                    failed_reason TEXT,
                    trace_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (handoff_id != ''),
                    CHECK (project_id != ''),
                    CHECK (source_role != ''),
                    CHECK (target_role != '')
                );
                CREATE INDEX IF NOT EXISTS idx_crew_handoffs_project
                    ON crew_handoff_packets(project_id);
                CREATE INDEX IF NOT EXISTS idx_crew_handoffs_source
                    ON crew_handoff_packets(project_id, source_role);
                CREATE INDEX IF NOT EXISTS idx_crew_handoffs_target
                    ON crew_handoff_packets(project_id, target_role);
                CREATE INDEX IF NOT EXISTS idx_crew_handoffs_status
                    ON crew_handoff_packets(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_crew_handoffs_scene
                    ON crew_handoff_packets(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_crew_handoffs_created
                    ON crew_handoff_packets(project_id, created_at);

                CREATE TABLE IF NOT EXISTS crew_deliberation_records (
                    deliberation_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    conflict_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    asset_id TEXT,
                    participating_roles TEXT NOT NULL DEFAULT '[]',
                    triggering_reasoning_ids TEXT NOT NULL DEFAULT '[]',
                    triggering_task_ids TEXT NOT NULL DEFAULT '[]',
                    issue_summary TEXT NOT NULL DEFAULT '',
                    points_of_agreement TEXT NOT NULL DEFAULT '[]',
                    points_of_tension TEXT NOT NULL DEFAULT '[]',
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    risks TEXT NOT NULL DEFAULT '[]',
                    recommended_resolution TEXT NOT NULL DEFAULT '',
                    requires_creator_decision INTEGER NOT NULL DEFAULT 0 CHECK (requires_creator_decision IN (0, 1)),
                    creator_question TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    resolution_summary TEXT,
                    resolved_by TEXT,
                    resolved_at TEXT,
                    trace_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (deliberation_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_crew_deliberations_project
                    ON crew_deliberation_records(project_id);
                CREATE INDEX IF NOT EXISTS idx_crew_deliberations_status
                    ON crew_deliberation_records(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_crew_deliberations_attention
                    ON crew_deliberation_records(project_id, requires_creator_decision);
                CREATE INDEX IF NOT EXISTS idx_crew_deliberations_scene
                    ON crew_deliberation_records(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_crew_deliberations_created
                    ON crew_deliberation_records(project_id, created_at);

                CREATE TABLE IF NOT EXISTS crew_department_status_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    agent_role TEXT NOT NULL,
                    department_name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    current_task_id TEXT,
                    current_activity TEXT NOT NULL DEFAULT '',
                    last_reasoning_id TEXT,
                    active_handoff_count INTEGER NOT NULL DEFAULT 0,
                    unresolved_risk_count INTEGER NOT NULL DEFAULT 0,
                    needs_creator_attention INTEGER NOT NULL DEFAULT 0 CHECK (needs_creator_attention IN (0, 1)),
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (snapshot_id != ''),
                    CHECK (project_id != ''),
                    CHECK (agent_role != '')
                );
                CREATE INDEX IF NOT EXISTS idx_crew_department_snapshots_project
                    ON crew_department_status_snapshots(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_crew_department_snapshots_role
                    ON crew_department_status_snapshots(project_id, agent_role, created_at);
            """),
            (43, "Add frontend error telemetry storage", """
                CREATE TABLE IF NOT EXISTS error_reports (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    level TEXT NOT NULL CHECK (level IN ('fatal', 'error', 'warning')),
                    message TEXT NOT NULL,
                    stack TEXT,
                    component_stack TEXT,
                    url TEXT,
                    user_agent TEXT,
                    build_version TEXT,
                    context_json TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_error_reports_timestamp ON error_reports(timestamp);
                CREATE INDEX IF NOT EXISTS idx_error_reports_level ON error_reports(level);
                CREATE INDEX IF NOT EXISTS idx_error_reports_build_version ON error_reports(build_version);
            """),
            (44, "Add performance intelligence persistence", """
                CREATE TABLE IF NOT EXISTS performance_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT,
                    analysis_scope TEXT NOT NULL,
                    status TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_signature TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    reasoning_trace_json TEXT NOT NULL DEFAULT '[]',
                    guardrail_report_json TEXT NOT NULL DEFAULT '{}',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (analysis_id != ''),
                    CHECK (project_id != ''),
                    CHECK (analysis_scope != '')
                );
                CREATE INDEX IF NOT EXISTS idx_performance_analyses_project_scene
                    ON performance_analyses(project_id, scene_id, generated_at);
                CREATE INDEX IF NOT EXISTS idx_performance_analyses_signature
                    ON performance_analyses(project_id, source_signature);

                CREATE TABLE IF NOT EXISTS performance_briefs (
                    brief_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    character_name TEXT NOT NULL,
                    objective TEXT NOT NULL DEFAULT '',
                    obstacle TEXT NOT NULL DEFAULT '',
                    tactic TEXT NOT NULL DEFAULT '',
                    emotional_start TEXT NOT NULL DEFAULT '',
                    emotional_end TEXT NOT NULL DEFAULT '',
                    mask TEXT NOT NULL DEFAULT '',
                    reveal TEXT NOT NULL DEFAULT '',
                    subtext_summary TEXT NOT NULL DEFAULT '',
                    continuity_note TEXT NOT NULL DEFAULT '',
                    uncertainty_label TEXT NOT NULL DEFAULT 'emerging',
                    uncertainty_reason TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (brief_id != ''),
                    CHECK (analysis_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (character_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_performance_briefs_project_scene
                    ON performance_briefs(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_performance_briefs_project_character
                    ON performance_briefs(project_id, character_id, created_at);

                CREATE TABLE IF NOT EXISTS performance_beats (
                    beat_id TEXT PRIMARY KEY,
                    brief_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    beat_index INTEGER NOT NULL,
                    beat_label TEXT NOT NULL DEFAULT '',
                    visible_action TEXT NOT NULL DEFAULT '',
                    internal_action TEXT NOT NULL DEFAULT '',
                    dialogue_subtext TEXT NOT NULL DEFAULT '',
                    physical_direction TEXT NOT NULL DEFAULT '',
                    voice_direction TEXT NOT NULL DEFAULT '',
                    camera_relevance TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (beat_id != ''),
                    CHECK (brief_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (character_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_performance_beats_brief
                    ON performance_beats(brief_id, beat_index);

                CREATE TABLE IF NOT EXISTS performance_relationship_reads (
                    relationship_read_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    character_a TEXT NOT NULL,
                    character_b TEXT NOT NULL,
                    relationship_state TEXT NOT NULL DEFAULT '',
                    pressure TEXT NOT NULL DEFAULT '',
                    power_shift TEXT NOT NULL DEFAULT '',
                    trust_state TEXT NOT NULL DEFAULT '',
                    conflict_residue TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    uncertainty_label TEXT NOT NULL DEFAULT 'emerging',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (relationship_read_id != ''),
                    CHECK (analysis_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (character_a != ''),
                    CHECK (character_b != '')
                );
                CREATE INDEX IF NOT EXISTS idx_performance_relationships_scene
                    ON performance_relationship_reads(project_id, scene_id);

                CREATE TABLE IF NOT EXISTS performance_evidence_refs (
                    evidence_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    brief_id TEXT,
                    beat_id TEXT,
                    project_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    scene_id TEXT,
                    character_id TEXT,
                    field_path TEXT NOT NULL DEFAULT '',
                    excerpt TEXT NOT NULL DEFAULT '',
                    relevance TEXT NOT NULL DEFAULT '',
                    reliability_label TEXT NOT NULL DEFAULT 'emerging',
                    created_at TEXT NOT NULL,
                    CHECK (evidence_id != ''),
                    CHECK (analysis_id != ''),
                    CHECK (project_id != ''),
                    CHECK (source_type != ''),
                    CHECK (source_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_performance_evidence_analysis
                    ON performance_evidence_refs(analysis_id);
                CREATE INDEX IF NOT EXISTS idx_performance_evidence_source
                    ON performance_evidence_refs(source_type, source_id);

                CREATE TABLE IF NOT EXISTS performance_decisions (
                    decision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT,
                    character_id TEXT,
                    source_brief_id TEXT,
                    decision_text TEXT NOT NULL,
                    inferred_tradeoff TEXT NOT NULL DEFAULT '',
                    saved_by TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    memory_entry_id TEXT,
                    editable INTEGER NOT NULL DEFAULT 1 CHECK (editable IN (0, 1)),
                    forgotten_at TEXT,
                    CHECK (decision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (decision_text != ''),
                    CHECK (saved_by != '')
                );
                CREATE INDEX IF NOT EXISTS idx_performance_decisions_project_character
                    ON performance_decisions(project_id, character_id, saved_at);
            """),
            (45, "Add cinematographer intelligence camera grammar persistence", """
                CREATE TABLE IF NOT EXISTS camera_grammar_plans (
                    plan_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    take_id TEXT,
                    render_job_id TEXT,
                    plan_scope TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    source_summary TEXT NOT NULL DEFAULT '',
                    grammar_axes TEXT NOT NULL DEFAULT '[]',
                    composition_intent TEXT NOT NULL DEFAULT 'neutral',
                    lens_intent TEXT NOT NULL DEFAULT 'unspecified',
                    movement_intent TEXT NOT NULL DEFAULT 'none',
                    lighting_intent TEXT NOT NULL DEFAULT 'unspecified',
                    framing_intent TEXT NOT NULL DEFAULT 'medium',
                    depth_strategy TEXT NOT NULL DEFAULT '',
                    blocking_strategy TEXT NOT NULL DEFAULT '',
                    screen_direction_strategy TEXT NOT NULL DEFAULT '',
                    visual_storytelling_rationale TEXT NOT NULL DEFAULT '',
                    render_slot_suggestions TEXT NOT NULL DEFAULT '[]',
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    memory_refs TEXT NOT NULL DEFAULT '[]',
                    spine_refs TEXT NOT NULL DEFAULT '[]',
                    confidence_label TEXT NOT NULL DEFAULT 'emerging',
                    creator_note TEXT NOT NULL DEFAULT '',
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (plan_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_plans_project
                    ON camera_grammar_plans(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_plans_scene
                    ON camera_grammar_plans(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_plans_shot
                    ON camera_grammar_plans(project_id, shot_id);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_plans_render_job
                    ON camera_grammar_plans(render_job_id);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_plans_status
                    ON camera_grammar_plans(project_id, status);

                CREATE TABLE IF NOT EXISTS camera_grammar_observations (
                    observation_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT,
                    asset_id TEXT,
                    render_job_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    observation_scope TEXT NOT NULL DEFAULT 'asset',
                    observed_composition TEXT NOT NULL DEFAULT '',
                    observed_lighting TEXT NOT NULL DEFAULT '',
                    observed_camera_notes TEXT NOT NULL DEFAULT '',
                    observed_framing_tags TEXT NOT NULL DEFAULT '[]',
                    observed_lighting_tags TEXT NOT NULL DEFAULT '[]',
                    observed_movement_evidence TEXT NOT NULL DEFAULT '',
                    keyframe_ids TEXT NOT NULL DEFAULT '[]',
                    analysis_ids TEXT NOT NULL DEFAULT '[]',
                    cinematic_memory_ids TEXT NOT NULL DEFAULT '[]',
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    confidence_label TEXT NOT NULL DEFAULT 'low_data',
                    limitations TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (observation_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_observations_project
                    ON camera_grammar_observations(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_observations_asset
                    ON camera_grammar_observations(asset_id);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_observations_render_job
                    ON camera_grammar_observations(render_job_id);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_observations_plan
                    ON camera_grammar_observations(plan_id);

                CREATE TABLE IF NOT EXISTS camera_grammar_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    asset_id TEXT,
                    render_job_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    alignment_summary TEXT NOT NULL DEFAULT '',
                    matched_axes TEXT NOT NULL DEFAULT '[]',
                    drift_axes TEXT NOT NULL DEFAULT '[]',
                    risks TEXT NOT NULL DEFAULT '[]',
                    revision_suggestions TEXT NOT NULL DEFAULT '[]',
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    memory_refs TEXT NOT NULL DEFAULT '[]',
                    spine_refs TEXT NOT NULL DEFAULT '[]',
                    crew_reasoning_id TEXT,
                    requires_creator_attention INTEGER NOT NULL DEFAULT 0 CHECK (requires_creator_attention IN (0, 1)),
                    confidence_label TEXT NOT NULL DEFAULT 'emerging',
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    CHECK (assessment_id != ''),
                    CHECK (project_id != ''),
                    CHECK (plan_id != ''),
                    CHECK (observation_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_assessments_project
                    ON camera_grammar_assessments(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_assessments_plan
                    ON camera_grammar_assessments(plan_id);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_assessments_observation
                    ON camera_grammar_assessments(observation_id);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_assessments_asset
                    ON camera_grammar_assessments(asset_id);
                CREATE INDEX IF NOT EXISTS idx_camera_grammar_assessments_render_job
                    ON camera_grammar_assessments(render_job_id);
            """),
            (46, "Add performance audio intelligence persistence", """
                CREATE TABLE IF NOT EXISTS performance_audio_plans (
                    plan_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'scene',
                    scene_id TEXT,
                    shot_id TEXT,
                    asset_id TEXT,
                    status TEXT NOT NULL DEFAULT 'ready',
                    generated_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    model_version TEXT NOT NULL DEFAULT 'performance-audio-v1',
                    source_signature TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    voice_profiles_json TEXT NOT NULL DEFAULT '[]',
                    dialogue_cues_json TEXT NOT NULL DEFAULT '[]',
                    soundscape_layers_json TEXT NOT NULL DEFAULT '[]',
                    mix_requirements_json TEXT NOT NULL DEFAULT '{}',
                    provider_requirements_json TEXT NOT NULL DEFAULT '[]',
                    reasoning_trace_json TEXT NOT NULL DEFAULT '[]',
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    memory_refs_json TEXT NOT NULL DEFAULT '[]',
                    spine_refs_json TEXT NOT NULL DEFAULT '[]',
                    crew_reasoning_id TEXT,
                    readiness_label TEXT NOT NULL DEFAULT 'needs_review',
                    blockers_json TEXT NOT NULL DEFAULT '[]',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    stale_reason TEXT NOT NULL DEFAULT '',
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    CHECK (plan_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_performance_audio_plans_project
                    ON performance_audio_plans(project_id, generated_at);
                CREATE INDEX IF NOT EXISTS idx_performance_audio_plans_scene
                    ON performance_audio_plans(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_performance_audio_plans_shot
                    ON performance_audio_plans(project_id, shot_id);
                CREATE INDEX IF NOT EXISTS idx_performance_audio_plans_status
                    ON performance_audio_plans(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_performance_audio_plans_stale
                    ON performance_audio_plans(project_id, stale);

                CREATE TABLE IF NOT EXISTS character_voice_profiles (
                    profile_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    character_name TEXT NOT NULL,
                    source_signature TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ready',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (profile_id != ''),
                    CHECK (project_id != ''),
                    CHECK (character_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_character_voice_profiles_project_character
                    ON character_voice_profiles(project_id, character_id);
                CREATE INDEX IF NOT EXISTS idx_character_voice_profiles_stale
                    ON character_voice_profiles(project_id, stale);

                CREATE TABLE IF NOT EXISTS audio_intelligence_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    asset_id TEXT,
                    render_job_id TEXT,
                    generated_at TEXT NOT NULL,
                    source_signature TEXT NOT NULL DEFAULT '',
                    observed_audio_stream INTEGER NOT NULL DEFAULT 0 CHECK (observed_audio_stream IN (0, 1)),
                    readiness_label TEXT NOT NULL DEFAULT 'needs_review',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (assessment_id != ''),
                    CHECK (project_id != ''),
                    CHECK (plan_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_audio_assessments_project
                    ON audio_intelligence_assessments(project_id, generated_at);
                CREATE INDEX IF NOT EXISTS idx_audio_assessments_plan
                    ON audio_intelligence_assessments(plan_id);
                CREATE INDEX IF NOT EXISTS idx_audio_assessments_asset
                    ON audio_intelligence_assessments(asset_id);
                CREATE INDEX IF NOT EXISTS idx_audio_assessments_render_job
                    ON audio_intelligence_assessments(render_job_id);

                CREATE TABLE IF NOT EXISTS dialogue_performance_cues (
                    cue_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    shot_id TEXT,
                    line_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    character_name TEXT NOT NULL,
                    uncertainty_label TEXT NOT NULL DEFAULT 'emerging',
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (cue_id != ''),
                    CHECK (project_id != ''),
                    CHECK (plan_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (line_id != ''),
                    CHECK (character_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_dialogue_performance_cues_plan
                    ON dialogue_performance_cues(plan_id);
                CREATE INDEX IF NOT EXISTS idx_dialogue_performance_cues_scene
                    ON dialogue_performance_cues(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_dialogue_performance_cues_character
                    ON dialogue_performance_cues(project_id, character_id);

                CREATE TABLE IF NOT EXISTS soundscape_layer_plans (
                    layer_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    track_type TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (layer_id != ''),
                    CHECK (project_id != ''),
                    CHECK (plan_id != ''),
                    CHECK (track_type != '')
                );
                CREATE INDEX IF NOT EXISTS idx_soundscape_layer_plans_plan
                    ON soundscape_layer_plans(plan_id);
                CREATE INDEX IF NOT EXISTS idx_soundscape_layer_plans_scene
                    ON soundscape_layer_plans(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_soundscape_layer_plans_track
                    ON soundscape_layer_plans(project_id, track_type);

                CREATE TABLE IF NOT EXISTS audio_decision_memory_projections (
                    decision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    decision_text TEXT NOT NULL,
                    inferred_tradeoff TEXT NOT NULL DEFAULT '',
                    scene_id TEXT,
                    character_id TEXT,
                    plan_id TEXT,
                    cue_id TEXT,
                    layer_id TEXT,
                    profile_id TEXT,
                    assessment_id TEXT,
                    saved_by TEXT NOT NULL DEFAULT 'creator',
                    saved_at TEXT NOT NULL,
                    memory_entry_id TEXT,
                    editable INTEGER NOT NULL DEFAULT 1 CHECK (editable IN (0, 1)),
                    forgotten_at TEXT,
                    CHECK (decision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (decision_text != '')
                );
                CREATE INDEX IF NOT EXISTS idx_audio_decisions_project
                    ON audio_decision_memory_projections(project_id, saved_at);
                CREATE INDEX IF NOT EXISTS idx_audio_decisions_plan
                    ON audio_decision_memory_projections(plan_id);
            """),
            (47, "Ensure first-class performance audio cue and layer tables", """
                CREATE TABLE IF NOT EXISTS dialogue_performance_cues (
                    cue_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    shot_id TEXT,
                    line_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    character_name TEXT NOT NULL,
                    uncertainty_label TEXT NOT NULL DEFAULT 'emerging',
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (cue_id != ''),
                    CHECK (project_id != ''),
                    CHECK (plan_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (line_id != ''),
                    CHECK (character_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_dialogue_performance_cues_plan
                    ON dialogue_performance_cues(plan_id);
                CREATE INDEX IF NOT EXISTS idx_dialogue_performance_cues_scene
                    ON dialogue_performance_cues(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_dialogue_performance_cues_character
                    ON dialogue_performance_cues(project_id, character_id);

                CREATE TABLE IF NOT EXISTS soundscape_layer_plans (
                    layer_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    track_type TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (layer_id != ''),
                    CHECK (project_id != ''),
                    CHECK (plan_id != ''),
                    CHECK (track_type != '')
                );
                CREATE INDEX IF NOT EXISTS idx_soundscape_layer_plans_plan
                    ON soundscape_layer_plans(plan_id);
                CREATE INDEX IF NOT EXISTS idx_soundscape_layer_plans_scene
                    ON soundscape_layer_plans(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_soundscape_layer_plans_track
                    ON soundscape_layer_plans(project_id, track_type);
            """),
            (48, "Add production design intelligence persistence", """
                CREATE TABLE IF NOT EXISTS production_design_plans (
                    plan_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'scene',
                    scene_id TEXT,
                    shot_id TEXT,
                    asset_id TEXT,
                    render_job_id TEXT,
                    status TEXT NOT NULL DEFAULT 'ready',
                    generated_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_signature TEXT NOT NULL DEFAULT '',
                    readiness_label TEXT NOT NULL DEFAULT 'needs_review',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (plan_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_design_plans_project
                    ON production_design_plans(project_id, generated_at);
                CREATE INDEX IF NOT EXISTS idx_production_design_plans_scene
                    ON production_design_plans(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_plans_shot
                    ON production_design_plans(project_id, shot_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_plans_asset
                    ON production_design_plans(asset_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_plans_render_job
                    ON production_design_plans(render_job_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_plans_status
                    ON production_design_plans(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_production_design_plans_stale
                    ON production_design_plans(project_id, stale);

                CREATE TABLE IF NOT EXISTS production_design_environment_profiles (
                    profile_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    location_id TEXT,
                    location_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (profile_id != ''),
                    CHECK (project_id != ''),
                    CHECK (location_name != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_design_env_project_location
                    ON production_design_environment_profiles(project_id, location_name);
                CREATE INDEX IF NOT EXISTS idx_production_design_env_location_id
                    ON production_design_environment_profiles(project_id, location_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_env_stale
                    ON production_design_environment_profiles(project_id, stale);

                CREATE TABLE IF NOT EXISTS production_design_prop_records (
                    prop_record_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    prop_id TEXT NOT NULL,
                    prop_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (prop_record_id != ''),
                    CHECK (project_id != ''),
                    CHECK (prop_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_design_props_project_prop
                    ON production_design_prop_records(project_id, prop_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_props_name
                    ON production_design_prop_records(project_id, prop_name);
                CREATE INDEX IF NOT EXISTS idx_production_design_props_stale
                    ON production_design_prop_records(project_id, stale);

                CREATE TABLE IF NOT EXISTS production_design_costume_records (
                    costume_record_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    status TEXT NOT NULL DEFAULT 'ready',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (costume_record_id != ''),
                    CHECK (project_id != ''),
                    CHECK (character_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_design_costumes_character
                    ON production_design_costume_records(project_id, character_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_costumes_scene
                    ON production_design_costume_records(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_costumes_stale
                    ON production_design_costume_records(project_id, stale);

                CREATE TABLE IF NOT EXISTS production_design_observations (
                    observation_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT,
                    asset_id TEXT,
                    render_job_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL,
                    confidence_label TEXT NOT NULL DEFAULT 'low_data',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (observation_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_design_obs_project
                    ON production_design_observations(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_production_design_obs_plan
                    ON production_design_observations(plan_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_obs_asset
                    ON production_design_observations(asset_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_obs_render_job
                    ON production_design_observations(render_job_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_obs_scene
                    ON production_design_observations(project_id, scene_id);

                CREATE TABLE IF NOT EXISTS production_design_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    asset_id TEXT,
                    render_job_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    status TEXT NOT NULL DEFAULT 'ready',
                    generated_at TEXT NOT NULL,
                    requires_creator_attention INTEGER NOT NULL DEFAULT 0 CHECK (requires_creator_attention IN (0, 1)),
                    confidence_label TEXT NOT NULL DEFAULT 'emerging',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (assessment_id != ''),
                    CHECK (project_id != ''),
                    CHECK (plan_id != ''),
                    CHECK (observation_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_design_assess_project
                    ON production_design_assessments(project_id, generated_at);
                CREATE INDEX IF NOT EXISTS idx_production_design_assess_plan
                    ON production_design_assessments(plan_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_assess_observation
                    ON production_design_assessments(observation_id);
                CREATE INDEX IF NOT EXISTS idx_production_design_assess_attention
                    ON production_design_assessments(project_id, requires_creator_attention);

                CREATE TABLE IF NOT EXISTS production_design_decision_memory_projections (
                    decision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    decision_text TEXT NOT NULL,
                    inferred_tradeoff TEXT NOT NULL DEFAULT '',
                    scene_id TEXT,
                    character_id TEXT,
                    plan_id TEXT,
                    prop_record_id TEXT,
                    costume_record_id TEXT,
                    environment_profile_id TEXT,
                    assessment_id TEXT,
                    saved_by TEXT NOT NULL DEFAULT 'creator',
                    saved_at TEXT NOT NULL,
                    memory_entry_id TEXT,
                    editable INTEGER NOT NULL DEFAULT 1 CHECK (editable IN (0, 1)),
                    forgotten_at TEXT,
                    CHECK (decision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (decision_text != '')
                );
                CREATE INDEX IF NOT EXISTS idx_production_design_decisions_project
                    ON production_design_decision_memory_projections(project_id, saved_at);
                CREATE INDEX IF NOT EXISTS idx_production_design_decisions_plan
                    ON production_design_decision_memory_projections(plan_id);
            """),
            (49, "Add colorist intelligence persistence", """
                CREATE TABLE IF NOT EXISTS color_look_bibles (
                    look_bible_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'project',
                    act_id TEXT,
                    sequence_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    look_fingerprint TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (look_bible_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_color_look_bibles_project
                    ON color_look_bibles(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_color_look_bibles_scope
                    ON color_look_bibles(project_id, scope);
                CREATE INDEX IF NOT EXISTS idx_color_look_bibles_sequence
                    ON color_look_bibles(project_id, sequence_id);
                CREATE INDEX IF NOT EXISTS idx_color_look_bibles_status
                    ON color_look_bibles(project_id, status);

                CREATE TABLE IF NOT EXISTS colorist_look_plans (
                    plan_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    look_bible_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    take_id TEXT,
                    asset_id TEXT,
                    render_job_id TEXT,
                    scope TEXT NOT NULL DEFAULT 'scene',
                    status TEXT NOT NULL DEFAULT 'active',
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    look_fingerprint TEXT NOT NULL DEFAULT '',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (plan_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_colorist_plans_project
                    ON colorist_look_plans(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_colorist_plans_scene
                    ON colorist_look_plans(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_colorist_plans_shot
                    ON colorist_look_plans(project_id, shot_id);
                CREATE INDEX IF NOT EXISTS idx_colorist_plans_asset
                    ON colorist_look_plans(asset_id);
                CREATE INDEX IF NOT EXISTS idx_colorist_plans_render_job
                    ON colorist_look_plans(render_job_id);
                CREATE INDEX IF NOT EXISTS idx_colorist_plans_status
                    ON colorist_look_plans(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_colorist_plans_stale
                    ON colorist_look_plans(project_id, stale);

                CREATE TABLE IF NOT EXISTS color_palette_continuity_records (
                    palette_record_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'project',
                    scene_id TEXT,
                    sequence_id TEXT,
                    character_id TEXT,
                    location_id TEXT,
                    prop_id TEXT,
                    motif_id TEXT,
                    source_type TEXT NOT NULL DEFAULT 'project',
                    source_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (palette_record_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_color_palette_records_project
                    ON color_palette_continuity_records(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_color_palette_records_scene
                    ON color_palette_continuity_records(project_id, scene_id);
                CREATE INDEX IF NOT EXISTS idx_color_palette_records_sequence
                    ON color_palette_continuity_records(project_id, sequence_id);
                CREATE INDEX IF NOT EXISTS idx_color_palette_records_motif
                    ON color_palette_continuity_records(project_id, motif_id);

                CREATE TABLE IF NOT EXISTS color_story_arcs (
                    color_arc_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    look_bible_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (color_arc_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_color_story_arcs_project
                    ON color_story_arcs(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_color_story_arcs_look_bible
                    ON color_story_arcs(look_bible_id);

                CREATE TABLE IF NOT EXISTS color_grade_observations (
                    observation_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT,
                    look_bible_id TEXT,
                    asset_id TEXT,
                    render_job_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    scope TEXT NOT NULL DEFAULT 'asset',
                    status TEXT NOT NULL DEFAULT 'active',
                    confidence_label TEXT NOT NULL DEFAULT 'low_data',
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (observation_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_color_observations_project
                    ON color_grade_observations(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_color_observations_plan
                    ON color_grade_observations(plan_id);
                CREATE INDEX IF NOT EXISTS idx_color_observations_asset
                    ON color_grade_observations(asset_id);
                CREATE INDEX IF NOT EXISTS idx_color_observations_render_job
                    ON color_grade_observations(render_job_id);
                CREATE INDEX IF NOT EXISTS idx_color_observations_scene
                    ON color_grade_observations(project_id, scene_id);

                CREATE TABLE IF NOT EXISTS color_match_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    look_bible_id TEXT,
                    asset_id TEXT,
                    render_job_id TEXT,
                    scene_id TEXT,
                    shot_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    requires_creator_attention INTEGER NOT NULL DEFAULT 0 CHECK (requires_creator_attention IN (0, 1)),
                    confidence_label TEXT NOT NULL DEFAULT 'emerging',
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (assessment_id != ''),
                    CHECK (project_id != ''),
                    CHECK (plan_id != ''),
                    CHECK (observation_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_color_assessments_project
                    ON color_match_assessments(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_color_assessments_plan
                    ON color_match_assessments(plan_id);
                CREATE INDEX IF NOT EXISTS idx_color_assessments_observation
                    ON color_match_assessments(observation_id);
                CREATE INDEX IF NOT EXISTS idx_color_assessments_asset
                    ON color_match_assessments(asset_id);
                CREATE INDEX IF NOT EXISTS idx_color_assessments_render_job
                    ON color_match_assessments(render_job_id);
                CREATE INDEX IF NOT EXISTS idx_color_assessments_attention
                    ON color_match_assessments(project_id, requires_creator_attention);

                CREATE TABLE IF NOT EXISTS color_final_verifications (
                    verification_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    package_id TEXT,
                    asset_id TEXT,
                    look_bible_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    confidence_label TEXT NOT NULL DEFAULT 'emerging',
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (verification_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_color_final_verifications_project
                    ON color_final_verifications(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_color_final_verifications_package
                    ON color_final_verifications(package_id);
                CREATE INDEX IF NOT EXISTS idx_color_final_verifications_asset
                    ON color_final_verifications(asset_id);

                CREATE TABLE IF NOT EXISTS colorist_decision_projections (
                    decision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    decision_text TEXT NOT NULL,
                    scene_id TEXT,
                    plan_id TEXT,
                    assessment_id TEXT,
                    look_bible_id TEXT,
                    saved_by TEXT NOT NULL DEFAULT 'creator',
                    saved_at TEXT NOT NULL,
                    memory_entry_id TEXT,
                    editable INTEGER NOT NULL DEFAULT 1 CHECK (editable IN (0, 1)),
                    forgotten_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (decision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (decision_text != '')
                );
                CREATE INDEX IF NOT EXISTS idx_colorist_decisions_project
                    ON colorist_decision_projections(project_id, saved_at);
                CREATE INDEX IF NOT EXISTS idx_colorist_decisions_plan
                    ON colorist_decision_projections(plan_id);
            """),
            (50, "Add casting intelligence and talent management persistence", """
                CREATE TABLE IF NOT EXISTS casting_role_breakdowns (
                    role_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    character_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    readiness_label TEXT NOT NULL DEFAULT 'needs_review',
                    source_signature TEXT NOT NULL DEFAULT '',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (role_id != ''),
                    CHECK (project_id != ''),
                    CHECK (character_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_casting_roles_project
                    ON casting_role_breakdowns(project_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_casting_roles_character
                    ON casting_role_breakdowns(project_id, character_id);
                CREATE INDEX IF NOT EXISTS idx_casting_roles_status
                    ON casting_role_breakdowns(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_casting_roles_stale
                    ON casting_role_breakdowns(project_id, stale);

                CREATE TABLE IF NOT EXISTS talent_profiles (
                    talent_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    modality TEXT NOT NULL DEFAULT 'human',
                    availability_label TEXT NOT NULL DEFAULT 'unknown',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (talent_id != ''),
                    CHECK (project_id != ''),
                    CHECK (display_name != '')
                );
                CREATE INDEX IF NOT EXISTS idx_talent_profiles_project
                    ON talent_profiles(project_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_talent_profiles_modality
                    ON talent_profiles(project_id, modality);
                CREATE INDEX IF NOT EXISTS idx_talent_profiles_stale
                    ON talent_profiles(project_id, stale);

                CREATE TABLE IF NOT EXISTS talent_consent_records (
                    consent_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    talent_id TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (consent_id != ''),
                    CHECK (project_id != ''),
                    CHECK (talent_id != ''),
                    CHECK (modality != '')
                );
                CREATE INDEX IF NOT EXISTS idx_talent_consent_talent
                    ON talent_consent_records(project_id, talent_id);
                CREATE INDEX IF NOT EXISTS idx_talent_consent_status
                    ON talent_consent_records(project_id, status);

                CREATE TABLE IF NOT EXISTS audition_packages (
                    package_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (package_id != ''),
                    CHECK (project_id != ''),
                    CHECK (role_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_audition_packages_role
                    ON audition_packages(project_id, role_id);
                CREATE INDEX IF NOT EXISTS idx_audition_packages_status
                    ON audition_packages(project_id, status);

                CREATE TABLE IF NOT EXISTS audition_submissions (
                    audition_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    talent_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    submitted_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (audition_id != ''),
                    CHECK (project_id != ''),
                    CHECK (package_id != ''),
                    CHECK (role_id != ''),
                    CHECK (talent_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_audition_submissions_role
                    ON audition_submissions(project_id, role_id, submitted_at);
                CREATE INDEX IF NOT EXISTS idx_audition_submissions_talent
                    ON audition_submissions(project_id, talent_id);
                CREATE INDEX IF NOT EXISTS idx_audition_submissions_package
                    ON audition_submissions(package_id);

                CREATE TABLE IF NOT EXISTS audition_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    audition_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    talent_id TEXT NOT NULL,
                    uncertainty_label TEXT NOT NULL DEFAULT 'emerging',
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (evaluation_id != ''),
                    CHECK (project_id != ''),
                    CHECK (audition_id != ''),
                    CHECK (role_id != ''),
                    CHECK (talent_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_audition_evaluations_audition
                    ON audition_evaluations(audition_id);
                CREATE INDEX IF NOT EXISTS idx_audition_evaluations_role
                    ON audition_evaluations(project_id, role_id, created_at);

                CREATE TABLE IF NOT EXISTS casting_recommendations (
                    recommendation_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    talent_id TEXT NOT NULL,
                    audition_id TEXT,
                    evaluation_id TEXT,
                    readiness_label TEXT NOT NULL DEFAULT 'needs_review',
                    source_signature TEXT NOT NULL DEFAULT '',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (recommendation_id != ''),
                    CHECK (project_id != ''),
                    CHECK (role_id != ''),
                    CHECK (talent_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_casting_recommendations_role
                    ON casting_recommendations(project_id, role_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_casting_recommendations_talent
                    ON casting_recommendations(project_id, talent_id);
                CREATE INDEX IF NOT EXISTS idx_casting_recommendations_stale
                    ON casting_recommendations(project_id, stale);

                CREATE TABLE IF NOT EXISTS casting_decisions (
                    decision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    character_id TEXT NOT NULL,
                    talent_id TEXT NOT NULL,
                    recommendation_id TEXT,
                    audition_id TEXT,
                    evaluation_id TEXT,
                    status TEXT NOT NULL DEFAULT 'approved',
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    approved_at TEXT NOT NULL,
                    readiness_label TEXT NOT NULL DEFAULT 'needs_review',
                    stale INTEGER NOT NULL DEFAULT 0 CHECK (stale IN (0, 1)),
                    supersedes_decision_id TEXT,
                    superseded_by_decision_id TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (decision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (role_id != ''),
                    CHECK (character_id != ''),
                    CHECK (talent_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_casting_decisions_project
                    ON casting_decisions(project_id, approved_at);
                CREATE INDEX IF NOT EXISTS idx_casting_decisions_role
                    ON casting_decisions(project_id, role_id);
                CREATE INDEX IF NOT EXISTS idx_casting_decisions_character
                    ON casting_decisions(project_id, character_id);
                CREATE INDEX IF NOT EXISTS idx_casting_decisions_active
                    ON casting_decisions(project_id, active);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_casting_decisions_active_role
                    ON casting_decisions(project_id, role_id) WHERE active = 1;

                CREATE TABLE IF NOT EXISTS casting_readiness_reports (
                    report_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'project',
                    role_id TEXT,
                    readiness_label TEXT NOT NULL DEFAULT 'needs_review',
                    generated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (report_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_casting_readiness_project
                    ON casting_readiness_reports(project_id, generated_at);
                CREATE INDEX IF NOT EXISTS idx_casting_readiness_role
                    ON casting_readiness_reports(project_id, role_id);

                CREATE TABLE IF NOT EXISTS casting_decision_memory_projections (
                    decision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    role_id TEXT,
                    character_id TEXT,
                    talent_id TEXT,
                    casting_decision_id TEXT,
                    decision_text TEXT NOT NULL,
                    inferred_tradeoff TEXT NOT NULL DEFAULT '',
                    saved_by TEXT NOT NULL DEFAULT 'creator',
                    saved_at TEXT NOT NULL,
                    memory_entry_id TEXT,
                    editable INTEGER NOT NULL DEFAULT 1 CHECK (editable IN (0, 1)),
                    forgotten_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (decision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (decision_text != '')
                );
                CREATE INDEX IF NOT EXISTS idx_casting_memory_decisions_project
                    ON casting_decision_memory_projections(project_id, saved_at);
                CREATE INDEX IF NOT EXISTS idx_casting_memory_decisions_role
                    ON casting_decision_memory_projections(project_id, role_id);
            """),
            (51, "Add studio knowledge canonical intelligence persistence", """
                CREATE TABLE IF NOT EXISTS knowledge_bibles (
                    bible_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    bible_type TEXT NOT NULL DEFAULT 'general',
                    content_type TEXT NOT NULL DEFAULT 'markdown',
                    source_filename TEXT NOT NULL DEFAULT '',
                    source_uri TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'registered',
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    section_count INTEGER NOT NULL DEFAULT 0,
                    atom_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (bible_id != ''),
                    CHECK (project_id != ''),
                    CHECK (title != '')
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_bibles_project
                    ON knowledge_bibles(project_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_knowledge_bibles_status
                    ON knowledge_bibles(project_id, status);

                CREATE TABLE IF NOT EXISTS knowledge_bible_sections (
                    section_id TEXT PRIMARY KEY,
                    bible_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    heading TEXT NOT NULL DEFAULT '',
                    section_index INTEGER NOT NULL DEFAULT 0,
                    content TEXT NOT NULL DEFAULT '',
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (section_id != ''),
                    CHECK (bible_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_sections_bible
                    ON knowledge_bible_sections(bible_id, section_index);
                CREATE INDEX IF NOT EXISTS idx_knowledge_sections_project
                    ON knowledge_bible_sections(project_id, bible_id);

                CREATE TABLE IF NOT EXISTS knowledge_atoms (
                    atom_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_ref_json TEXT NOT NULL DEFAULT '{}',
                    atom_type TEXT NOT NULL,
                    authority_level TEXT NOT NULL,
                    scope_type TEXT NOT NULL DEFAULT 'project',
                    scope_id TEXT NOT NULL DEFAULT '',
                    department TEXT NOT NULL DEFAULT '',
                    canonical_text TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    confidence_label TEXT NOT NULL DEFAULT 'emerging',
                    extraction_method TEXT NOT NULL DEFAULT 'deterministic',
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at TEXT,
                    supersedes_atom_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (atom_id != ''),
                    CHECK (project_id != ''),
                    CHECK (source_type != ''),
                    CHECK (source_id != ''),
                    CHECK (canonical_text != '')
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_atoms_source_fingerprint
                    ON knowledge_atoms(project_id, source_type, source_id, source_fingerprint);
                CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_type
                    ON knowledge_atoms(project_id, atom_type);
                CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_authority
                    ON knowledge_atoms(project_id, authority_level);
                CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_scope
                    ON knowledge_atoms(project_id, scope_type, scope_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_source
                    ON knowledge_atoms(project_id, source_type, source_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_status
                    ON knowledge_atoms(project_id, status);

                CREATE TABLE IF NOT EXISTS knowledge_context_pack_snapshots (
                    pack_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    purpose TEXT NOT NULL DEFAULT 'planning',
                    scene_id TEXT,
                    shot_id TEXT,
                    asset_id TEXT,
                    trace_id TEXT NOT NULL DEFAULT '',
                    atom_ids_json TEXT NOT NULL DEFAULT '[]',
                    conflict_ids_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (pack_id != ''),
                    CHECK (project_id != ''),
                    CHECK (department != '')
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_packs_project
                    ON knowledge_context_pack_snapshots(project_id, department, created_at);
                CREATE INDEX IF NOT EXISTS idx_knowledge_packs_scene
                    ON knowledge_context_pack_snapshots(project_id, scene_id);

                CREATE TABLE IF NOT EXISTS knowledge_reasoning_traces (
                    trace_id TEXT PRIMARY KEY,
                    pack_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    department TEXT NOT NULL,
                    purpose TEXT NOT NULL DEFAULT 'planning',
                    consumer_id TEXT NOT NULL DEFAULT '',
                    selected_atom_ids_json TEXT NOT NULL DEFAULT '[]',
                    excluded_atom_ids_json TEXT NOT NULL DEFAULT '[]',
                    conflict_ids_json TEXT NOT NULL DEFAULT '[]',
                    source_counts_json TEXT NOT NULL DEFAULT '{}',
                    selection_notes_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (trace_id != ''),
                    CHECK (pack_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_traces_project
                    ON knowledge_reasoning_traces(project_id, department, created_at);

                CREATE TABLE IF NOT EXISTS knowledge_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    conflict_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'advisory',
                    status TEXT NOT NULL DEFAULT 'open',
                    primary_atom_id TEXT NOT NULL,
                    conflicting_atom_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    resolution_guidance TEXT NOT NULL DEFAULT '',
                    scope_type TEXT NOT NULL DEFAULT 'project',
                    scope_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    acknowledged_by TEXT NOT NULL DEFAULT '',
                    acknowledged_at TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (conflict_id != ''),
                    CHECK (project_id != ''),
                    CHECK (primary_atom_id != ''),
                    CHECK (conflicting_atom_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_conflicts_project
                    ON knowledge_conflicts(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_knowledge_conflicts_scope
                    ON knowledge_conflicts(project_id, scope_type, scope_id);

                CREATE TABLE IF NOT EXISTS knowledge_rebuild_runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'complete',
                    source_types_json TEXT NOT NULL DEFAULT '[]',
                    source_count INTEGER NOT NULL DEFAULT 0,
                    atom_count INTEGER NOT NULL DEFAULT 0,
                    conflict_count INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (run_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_rebuilds_project
                    ON knowledge_rebuild_runs(project_id, started_at);
            """),
            (52, "Add Studio Brain 2.0 executive orchestration persistence", """
                CREATE TABLE IF NOT EXISTS studio_brain_sessions (
                    session_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    active_plan_id TEXT NOT NULL DEFAULT '',
                    latest_readiness_snapshot_id TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    closed_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (session_id != ''),
                    CHECK (project_id != ''),
                    CHECK (purpose != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_brain_sessions_project_created
                    ON studio_brain_sessions(project_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_studio_brain_sessions_project_status
                    ON studio_brain_sessions(project_id, status);

                CREATE TABLE IF NOT EXISTS studio_brain_department_signals (
                    signal_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    agent_role TEXT NOT NULL,
                    department_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'standby',
                    purpose TEXT NOT NULL DEFAULT 'project_overview',
                    requires_creator_decision INTEGER NOT NULL DEFAULT 0 CHECK (requires_creator_decision IN (0, 1)),
                    generated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (signal_id != ''),
                    CHECK (session_id != ''),
                    CHECK (project_id != ''),
                    CHECK (agent_role != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_brain_signals_session_role
                    ON studio_brain_department_signals(session_id, agent_role);
                CREATE INDEX IF NOT EXISTS idx_studio_brain_signals_project
                    ON studio_brain_department_signals(project_id, generated_at);

                CREATE TABLE IF NOT EXISTS studio_brain_production_plans (
                    plan_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    phase TEXT NOT NULL DEFAULT '',
                    readiness_snapshot_id TEXT NOT NULL DEFAULT '',
                    reasoning_trace_id TEXT NOT NULL DEFAULT '',
                    supersedes_plan_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (plan_id != ''),
                    CHECK (session_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_brain_plans_session_status
                    ON studio_brain_production_plans(session_id, status);
                CREATE INDEX IF NOT EXISTS idx_studio_brain_plans_project
                    ON studio_brain_production_plans(project_id, created_at);

                CREATE TABLE IF NOT EXISTS studio_brain_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    conflict_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'advisory',
                    status TEXT NOT NULL DEFAULT 'open',
                    requires_creator_decision INTEGER NOT NULL DEFAULT 0 CHECK (requires_creator_decision IN (0, 1)),
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (conflict_id != ''),
                    CHECK (session_id != ''),
                    CHECK (project_id != ''),
                    CHECK (conflict_type != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_brain_conflicts_session_status
                    ON studio_brain_conflicts(session_id, status);
                CREATE INDEX IF NOT EXISTS idx_studio_brain_conflicts_project_severity
                    ON studio_brain_conflicts(project_id, severity);

                CREATE TABLE IF NOT EXISTS studio_brain_resolution_decisions (
                    resolution_id TEXT PRIMARY KEY,
                    conflict_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    resolved_by TEXT NOT NULL DEFAULT 'studio_brain',
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (resolution_id != ''),
                    CHECK (conflict_id != ''),
                    CHECK (session_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_brain_resolutions_conflict
                    ON studio_brain_resolution_decisions(conflict_id, created_at);

                CREATE TABLE IF NOT EXISTS studio_brain_execution_directives (
                    directive_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    directive_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    target_service TEXT NOT NULL DEFAULT '',
                    target_method TEXT NOT NULL DEFAULT '',
                    idempotency_key TEXT NOT NULL,
                    source_plan_id TEXT NOT NULL DEFAULT '',
                    source_conflict_id TEXT NOT NULL DEFAULT '',
                    requires_creator_approval INTEGER NOT NULL DEFAULT 0 CHECK (requires_creator_approval IN (0, 1)),
                    approval_gate_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    dispatched_at TEXT,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (directive_id != ''),
                    CHECK (session_id != ''),
                    CHECK (project_id != ''),
                    CHECK (directive_type != ''),
                    CHECK (idempotency_key != '')
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_studio_brain_directives_idempotency
                    ON studio_brain_execution_directives(project_id, idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_studio_brain_directives_session_status
                    ON studio_brain_execution_directives(session_id, status);

                CREATE TABLE IF NOT EXISTS studio_brain_readiness_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    phase TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'insufficient_evidence',
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (snapshot_id != ''),
                    CHECK (session_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_brain_readiness_session
                    ON studio_brain_readiness_snapshots(session_id, created_at);

                CREATE TABLE IF NOT EXISTS studio_brain_reasoning_traces (
                    trace_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    trace_type TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (trace_id != ''),
                    CHECK (session_id != ''),
                    CHECK (project_id != ''),
                    CHECK (operation != '')
                );
                CREATE INDEX IF NOT EXISTS idx_studio_brain_traces_session_created
                    ON studio_brain_reasoning_traces(session_id, created_at);
            """),
            (53, "Add durable Previs lifecycle and production package provenance", """
                ALTER TABLE previs_images ADD COLUMN blueprint_id TEXT;
                ALTER TABLE previs_images ADD COLUMN blueprint_version_id TEXT;
                ALTER TABLE previs_images ADD COLUMN storyboard_shot_id TEXT;
                ALTER TABLE previs_images ADD COLUMN approved INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1));
                ALTER TABLE previs_images ADD COLUMN approved_at TEXT;
                ALTER TABLE previs_images ADD COLUMN approved_by TEXT;
                ALTER TABLE previs_images ADD COLUMN failure_reason TEXT;
                ALTER TABLE previs_images ADD COLUMN source_previs_image_id TEXT;
                ALTER TABLE previs_images ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1;
                ALTER TABLE previs_images ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}';
                CREATE INDEX IF NOT EXISTS idx_previs_images_provenance
                    ON previs_images(project_id, scene_id, storyboard_shot_id, blueprint_version_id);
                CREATE INDEX IF NOT EXISTS idx_previs_images_approved
                    ON previs_images(project_id, scene_id, approved);

                CREATE TABLE IF NOT EXISTS previs_production_packages (
                    package_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    blueprint_id TEXT NOT NULL,
                    blueprint_version_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (package_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (blueprint_id != ''),
                    CHECK (blueprint_version_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_previs_packages_project_scene
                    ON previs_production_packages(project_id, scene_id, created_at);
            """),
            (54, "Add canonical Screening Room output registry and approval state", """
                CREATE TABLE IF NOT EXISTS screening_outputs (
                    screening_output_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT,
                    shot_id TEXT,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    output_type TEXT NOT NULL,
                    original_url TEXT NOT NULL,
                    playback_url TEXT NOT NULL,
                    mime_type TEXT NOT NULL DEFAULT 'video/mp4',
                    media_status TEXT NOT NULL DEFAULT 'available',
                    approved INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1)),
                    approved_at TEXT,
                    approved_by TEXT,
                    supersedes_output_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (screening_output_id != ''),
                    CHECK (project_id != ''),
                    CHECK (source_type != ''),
                    CHECK (source_id != ''),
                    CHECK (original_url != ''),
                    CHECK (playback_url != '')
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_screening_outputs_source
                    ON screening_outputs(project_id, source_type, source_id, original_url);
                CREATE INDEX IF NOT EXISTS idx_screening_outputs_project_scene
                    ON screening_outputs(project_id, scene_id, output_type, created_at);
                CREATE INDEX IF NOT EXISTS idx_screening_outputs_approved
                    ON screening_outputs(project_id, output_type, approved, approved_at);

                CREATE TABLE IF NOT EXISTS screening_project_state (
                    project_id TEXT PRIMARY KEY,
                    current_final_output_id TEXT,
                    completion_status TEXT NOT NULL DEFAULT 'in_progress',
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (project_id != '')
                );
            """),
            (55, "Add versioned Film Cut and timeline persistence", """
                CREATE TABLE IF NOT EXISTS film_cut_versions (
                    cut_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    source_cut_id TEXT,
                    source_analysis_id TEXT,
                    source_application_id TEXT,
                    scene_order_json TEXT NOT NULL DEFAULT '[]',
                    timeline_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT,
                    approved_by TEXT,
                    CHECK (cut_id != ''),
                    CHECK (project_id != ''),
                    CHECK (version_number > 0)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_film_cut_project_version
                    ON film_cut_versions(project_id, version_number);
                CREATE INDEX IF NOT EXISTS idx_film_cut_project_created
                    ON film_cut_versions(project_id, created_at);

                CREATE TABLE IF NOT EXISTS film_cut_state (
                    project_id TEXT PRIMARY KEY,
                    current_cut_id TEXT NOT NULL,
                    approved_cut_id TEXT,
                    updated_at TEXT NOT NULL,
                    CHECK (project_id != ''),
                    CHECK (current_cut_id != '')
                );
            """),
            (56, "Add canonical production workflow runs and transition ledger", """
                CREATE TABLE IF NOT EXISTS canonical_workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    script_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    blueprint_id TEXT NOT NULL,
                    blueprint_version_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (run_id != ''),
                    CHECK (project_id != ''),
                    CHECK (script_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (blueprint_id != ''),
                    CHECK (blueprint_version_id != ''),
                    CHECK (status != ''),
                    CHECK (context_hash != '')
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_canonical_workflow_source
                    ON canonical_workflow_runs(project_id, scene_id, blueprint_version_id);
                CREATE INDEX IF NOT EXISTS idx_canonical_workflow_project_status
                    ON canonical_workflow_runs(project_id, status, updated_at);

                CREATE TABLE IF NOT EXISTS canonical_workflow_transitions (
                    transition_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    CHECK (transition_id != ''),
                    CHECK (run_id != ''),
                    CHECK (idempotency_key != ''),
                    CHECK (from_status != ''),
                    CHECK (to_status != ''),
                    CHECK (event_type != '')
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_canonical_workflow_transition_idempotency
                    ON canonical_workflow_transitions(run_id, idempotency_key);
                CREATE INDEX IF NOT EXISTS idx_canonical_workflow_transition_order
                    ON canonical_workflow_transitions(run_id, created_at, transition_id);
            """),
            (57, "Add cached creator-confirmed emotion analysis results", """
                CREATE TABLE IF NOT EXISTS emotion_analysis_results (
                    analysis_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (analysis_id != ''),
                    CHECK (project_id != ''),
                    CHECK (scene_id != ''),
                    CHECK (context_hash != ''),
                    CHECK (provider != ''),
                    CHECK (model != '')
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_emotion_analysis_context
                    ON emotion_analysis_results(project_id, scene_id, context_hash);
                CREATE INDEX IF NOT EXISTS idx_emotion_analysis_scene_updated
                    ON emotion_analysis_results(project_id, scene_id, updated_at);
            """),
            (58, "Allow multiple locked character references per role", """
                DROP INDEX IF EXISTS idx_character_reference_locks_active;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_character_reference_locks_active_role
                    ON character_reference_locks(project_id, character_id, reference_role)
                    WHERE lock_status = 'locked';
                CREATE INDEX IF NOT EXISTS idx_character_reference_locks_character_status
                    ON character_reference_locks(project_id, character_id, lock_status);
            """),
            (59, "Scope character reference locks by look", """
                ALTER TABLE character_reference_locks ADD COLUMN look_id TEXT NOT NULL DEFAULT 'default';
                ALTER TABLE character_reference_locks ADD COLUMN frame_score REAL NOT NULL DEFAULT 0.0;
                DROP INDEX IF EXISTS idx_character_reference_locks_active_role;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_character_reference_locks_active_look
                    ON character_reference_locks(project_id, character_id, look_id, reference_role)
                    WHERE lock_status = 'locked';
                CREATE INDEX IF NOT EXISTS idx_character_reference_locks_look
                    ON character_reference_locks(project_id, character_id, look_id);
            """),
            (60, "Add durable authentication and project ownership", """
                CREATE TABLE IF NOT EXISTS access_users (
                    username TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_owners (
                    project_id TEXT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES access_users(user_id),
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_project_owners_user ON project_owners(user_id);
            """),
            (61, "Persist review-blocked jobs and generation evidence", """
                CREATE TABLE render_jobs_review (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    shot_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_job_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'rendering', 'complete', 'failed', 'cancelled', 'needs_review', 'skipped')),
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
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (id != ''),
                    CHECK (project_id != ''),
                    CHECK (shot_id != ''),
                    CHECK (provider != '')
                );
                INSERT INTO render_jobs_review (id, project_id, shot_id, provider, provider_job_id, status, progress, input_payload, output_payload, error_message, retry_count, created_at, updated_at, completed_at) SELECT id, project_id, shot_id, provider, provider_job_id, status, progress, input_payload, output_payload, error_message, retry_count, created_at, updated_at, completed_at FROM render_jobs;
                DROP TABLE render_jobs;
                ALTER TABLE render_jobs_review RENAME TO render_jobs;
                CREATE INDEX idx_render_jobs_project ON render_jobs(project_id);
                CREATE INDEX idx_render_jobs_status ON render_jobs(status);
                CREATE INDEX idx_render_jobs_created ON render_jobs(created_at);
                CREATE INDEX idx_render_jobs_provider ON render_jobs(provider);
            """),
            (62, "Persist creator take choices and delivery provenance", """
                CREATE TABLE IF NOT EXISTS scene_take_choices (
                    project_id TEXT NOT NULL, scene_id TEXT NOT NULL,
                    shot_number INTEGER NOT NULL, job_id TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, scene_id, shot_number)
                );
                CREATE TABLE IF NOT EXISTS delivery_manifests (
                    project_id TEXT NOT NULL, scope TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (project_id, scope)
                );
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
            out: dict[str, StudioProject] = {}
            for row in cursor.fetchall():
                raw = row["data"]
                if not raw:
                    continue
                try:
                    out[row["project_id"]] = StudioProject(**json.loads(raw))
                except Exception:
                    continue
            return out

    def get_project(self, project_id: str) -> Optional[StudioProject]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM projects WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            if not row or not row["data"]:
                return None
            try:
                return StudioProject(**json.loads(row["data"]))
            except Exception:
                return None

    def save_project(self, project: StudioProject) -> StudioProject:
        project.updated_at = datetime.now().isoformat()
        now = datetime.now().isoformat()

        # Merge with existing data to preserve any fields not in the model
        new_data = project.model_dump(mode='json')

        def _smart_merge(existing: dict, new: dict) -> dict:
            """Merge new data into existing, preserving non-empty existing values
            when the new value is empty/default. This prevents model defaults
            from overwriting real data that was set by other code paths."""
            merged = dict(existing)
            for key, new_val in new.items():
                existing_val = existing.get(key)
                # Always overwrite if existing is missing or None
                if key not in existing or existing_val is None:
                    merged[key] = new_val
                    continue
                # For strings: only overwrite if new value is non-empty
                if isinstance(new_val, str) and not new_val and isinstance(existing_val, str) and existing_val:
                    continue  # preserve existing non-empty string
                # For lists: only overwrite if new value is non-empty
                if isinstance(new_val, list) and len(new_val) == 0 and isinstance(existing_val, list) and len(existing_val) > 0:
                    continue  # preserve existing non-empty list
                # For dicts: only overwrite if new value is non-empty
                if isinstance(new_val, dict) and len(new_val) == 0 and isinstance(existing_val, dict) and len(existing_val) > 0:
                    continue  # preserve existing non-empty dict
                # For all other cases, overwrite with new value
                merged[key] = new_val
            return merged

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Load existing data and merge
                cursor.execute("SELECT data FROM projects WHERE project_id = ?", (project.project_id,))
                row = cursor.fetchone()
                if row and row["data"]:
                    try:
                        existing_data = json.loads(row["data"])
                        # Smart merge: preserve existing non-empty values
                        merged_data = _smart_merge(existing_data, new_data)
                    except (json.JSONDecodeError, TypeError):
                        merged_data = new_data
                else:
                    merged_data = new_data

                payload = json.dumps(merged_data)

                columns = [row["name"] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()]
                has_created_at = "created_at" in columns
                has_updated_at = "updated_at" in columns

                # REPLACE deletes the parent row first, cascading into ownership
                # and storyboard records. A project save must retain its identity.
                if row is not None:
                    if has_updated_at:
                        cursor.execute("UPDATE projects SET data = ?, updated_at = ? WHERE project_id = ?", (payload, project.updated_at, project.project_id))
                    else:
                        cursor.execute("UPDATE projects SET data = ? WHERE project_id = ?", (payload, project.project_id))
                elif has_created_at and has_updated_at:
                    cursor.execute(
                        """INSERT INTO projects (project_id, data, created_at, updated_at)
                           VALUES (?, ?, COALESCE((SELECT created_at FROM projects WHERE project_id = ?), ?), ?)""",
                        (project.project_id, payload, project.project_id, now, project.updated_at),
                    )
                elif has_updated_at:
                    cursor.execute(
                        "INSERT INTO projects (project_id, data, updated_at) VALUES (?, ?, ?)",
                        (project.project_id, payload, project.updated_at),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO projects (project_id, data) VALUES (?, ?)",
                        (project.project_id, payload),
                    )
                conn.commit()

        self._execute_write_with_retry("save_project", _write)
        return project

    def save_error_report(self, report: dict[str, Any]) -> None:
        """Persist one frontend error report behind the storage boundary."""
        context = report.get("context")

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO error_reports
                       (id, timestamp, level, message, stack, component_stack,
                        url, user_agent, build_version, context_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report["error_id"],
                        report["timestamp"],
                        report.get("level", "error"),
                        report["message"],
                        report.get("stack"),
                        report.get("component_stack"),
                        report.get("url"),
                        report.get("user_agent"),
                        report.get("build_version"),
                        json.dumps(context) if context else None,
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_error_report", _write)

    def cascade_delete_project(self, project_id: str) -> bool:
        """Delete a project and ALL child records in correct order.
        Wraps the entire delete in a transaction for atomicity."""
        child_tables = [
            "scene_take_choices",
            "delivery_manifests",
            "crew_department_status_snapshots",
            "crew_deliberation_records",
            "crew_handoff_packets",
            "crew_reasoning_records",
            "production_queue_events",
            "production_queue_items",
            "editorial_decision_applications",
            "editorial_analysis_records",
            "storyboard_revision_links",
            "storyboard_render_links",
            "storyboard_shots",
            "storyboard_blueprint_versions",
            "storyboard_blueprints",
            "surfaced_disagreements",
            "previs_images",
            "pitch_decks",
            "export_packages",
            "session_debriefs",
            "video_frame_analyses",
            "video_keyframes",
            "workflow_executions",
            "production_acceptance_reports",
            "final_short_film_packages",
            "clip_revisions",
            "short_film_reviews",
            "style_drift_issues",
            "director_signatures",
            "style_signatures",
            "continuity_issues",
            "cinematic_memory_records",
            "visual_embeddings",
            "crew_task_log",
            "crew_tasks",
            "review_memories",
            "style_memories",
            "character_memories",
            "scene_memories",
            "memory_versions",
            "project_memories",
            "performance_decisions",
            "performance_evidence_refs",
            "performance_relationship_reads",
            "performance_beats",
            "performance_briefs",
            "performance_analyses",
            "camera_grammar_assessments",
            "camera_grammar_observations",
            "camera_grammar_plans",
            "production_design_assessments",
            "production_design_observations",
            "production_design_costume_records",
            "production_design_prop_records",
            "production_design_environment_profiles",
            "production_design_plans",
            "colorist_decision_projections",
            "color_final_verifications",
            "color_match_assessments",
            "color_grade_observations",
            "color_story_arcs",
            "color_palette_continuity_records",
            "colorist_look_plans",
            "color_look_bibles",
            "universe_relationships",
            "universe_nodes",
            "study_memories",
            "scene_compositions",
            "films",
            "render_jobs",
        ]
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN")
                cursor.execute(
                    """DELETE FROM production_queue_attempts
                       WHERE queue_item_id IN (
                           SELECT queue_item_id FROM production_queue_items WHERE project_id = ?
                       )""",
                    (project_id,),
                )
                cursor.execute(
                    """DELETE FROM production_queue_dependencies
                       WHERE queue_item_id IN (
                           SELECT queue_item_id FROM production_queue_items WHERE project_id = ?
                       )""",
                    (project_id,),
                )
                for table in child_tables:
                    cursor.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
                cursor.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
                conn.commit()
                return True
        except Exception:
            return False

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

    # ------------------------------------------------------------------ #
    # Performance Intelligence
    # ------------------------------------------------------------------ #

    def _row_to_camera_grammar_plan(self, row: sqlite3.Row):
        from app.models.cinematography import (
            CameraGrammarAxis,
            CameraGrammarEvidenceRef,
            CameraGrammarMemoryRef,
            CameraGrammarPlan,
            CameraGrammarRenderSlotSuggestion,
            CameraGrammarSpineRef,
        )

        return CameraGrammarPlan(
            plan_id=row["plan_id"],
            project_id=row["project_id"],
            scene_id=row["scene_id"],
            shot_id=row["shot_id"],
            take_id=row["take_id"],
            render_job_id=row["render_job_id"],
            plan_scope=row["plan_scope"],
            status=row["status"],
            source_fingerprint=row["source_fingerprint"],
            source_summary=row["source_summary"],
            grammar_axes=[CameraGrammarAxis(**item) for item in self._json_loads(row["grammar_axes"], [])],
            composition_intent=row["composition_intent"],
            lens_intent=row["lens_intent"],
            movement_intent=row["movement_intent"],
            lighting_intent=row["lighting_intent"],
            framing_intent=row["framing_intent"],
            depth_strategy=row["depth_strategy"],
            blocking_strategy=row["blocking_strategy"],
            screen_direction_strategy=row["screen_direction_strategy"],
            visual_storytelling_rationale=row["visual_storytelling_rationale"],
            render_slot_suggestions=[
                CameraGrammarRenderSlotSuggestion(**item)
                for item in self._json_loads(row["render_slot_suggestions"], [])
            ],
            evidence_refs=[CameraGrammarEvidenceRef(**item) for item in self._json_loads(row["evidence_refs"], [])],
            memory_refs=[CameraGrammarMemoryRef(**item) for item in self._json_loads(row["memory_refs"], [])],
            spine_refs=[CameraGrammarSpineRef(**item) for item in self._json_loads(row["spine_refs"], [])],
            confidence_label=row["confidence_label"],
            creator_note=row["creator_note"],
            advisory_only=bool(row["advisory_only"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=self._json_loads(row["metadata"], {}),
        )

    def save_camera_grammar_plan(self, plan: Any) -> Any:
        data = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else dict(plan)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO camera_grammar_plans (
                        plan_id, project_id, scene_id, shot_id, take_id, render_job_id,
                        plan_scope, status, source_fingerprint, source_summary,
                        grammar_axes, composition_intent, lens_intent, movement_intent,
                        lighting_intent, framing_intent, depth_strategy, blocking_strategy,
                        screen_direction_strategy, visual_storytelling_rationale,
                        render_slot_suggestions, evidence_refs, memory_refs, spine_refs,
                        confidence_label, creator_note, advisory_only, created_at, updated_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["plan_id"],
                        data["project_id"],
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("take_id"),
                        data.get("render_job_id"),
                        data.get("plan_scope") or "scene",
                        data.get("status") or "active",
                        data.get("source_fingerprint") or "",
                        data.get("source_summary") or "",
                        self._json_dumps(data.get("grammar_axes", [])),
                        data.get("composition_intent") or "neutral",
                        data.get("lens_intent") or "unspecified",
                        data.get("movement_intent") or "none",
                        data.get("lighting_intent") or "unspecified",
                        data.get("framing_intent") or "medium",
                        data.get("depth_strategy") or "",
                        data.get("blocking_strategy") or "",
                        data.get("screen_direction_strategy") or "",
                        data.get("visual_storytelling_rationale") or "",
                        self._json_dumps(data.get("render_slot_suggestions", [])),
                        self._json_dumps(data.get("evidence_refs", [])),
                        self._json_dumps(data.get("memory_refs", [])),
                        self._json_dumps(data.get("spine_refs", [])),
                        data.get("confidence_label") or "emerging",
                        data.get("creator_note") or "",
                        1 if data.get("advisory_only", True) else 0,
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data.get("metadata", {})),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_camera_grammar_plan", _write)
        return plan

    def get_camera_grammar_plan(self, plan_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM camera_grammar_plans WHERE plan_id = ?", (plan_id,))
            row = cursor.fetchone()
            return self._row_to_camera_grammar_plan(row) if row else None

    def list_camera_grammar_plans(
        self,
        project_id: str,
        scene_id: str | None = None,
        shot_id: str | None = None,
        render_job_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM camera_grammar_plans WHERE project_id = ?"
            params: list[Any] = [project_id]
            if scene_id:
                query += " AND scene_id = ?"
                params.append(scene_id)
            if shot_id:
                query += " AND shot_id = ?"
                params.append(shot_id)
            if render_job_id:
                query += " AND render_job_id = ?"
                params.append(render_job_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [self._row_to_camera_grammar_plan(row) for row in cursor.fetchall()]

    def mark_camera_grammar_plan_stale(self, plan_id: str) -> bool:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE camera_grammar_plans SET status = ?, updated_at = ? WHERE plan_id = ?",
                    ("stale", datetime.utcnow().isoformat() + "Z", plan_id),
                )
                conn.commit()
                return cursor.rowcount > 0

        return bool(self._execute_write_with_retry("mark_camera_grammar_plan_stale", _write))

    def _row_to_camera_grammar_observation(self, row: sqlite3.Row):
        from app.models.cinematography import CameraGrammarEvidenceRef, CameraGrammarObservation

        return CameraGrammarObservation(
            observation_id=row["observation_id"],
            project_id=row["project_id"],
            plan_id=row["plan_id"],
            asset_id=row["asset_id"],
            render_job_id=row["render_job_id"],
            scene_id=row["scene_id"],
            shot_id=row["shot_id"],
            status=row["status"],
            observation_scope=row["observation_scope"],
            observed_composition=row["observed_composition"],
            observed_lighting=row["observed_lighting"],
            observed_camera_notes=row["observed_camera_notes"],
            observed_framing_tags=self._json_loads(row["observed_framing_tags"], []),
            observed_lighting_tags=self._json_loads(row["observed_lighting_tags"], []),
            observed_movement_evidence=row["observed_movement_evidence"],
            keyframe_ids=self._json_loads(row["keyframe_ids"], []),
            analysis_ids=self._json_loads(row["analysis_ids"], []),
            cinematic_memory_ids=self._json_loads(row["cinematic_memory_ids"], []),
            evidence_refs=[CameraGrammarEvidenceRef(**item) for item in self._json_loads(row["evidence_refs"], [])],
            confidence_label=row["confidence_label"],
            limitations=self._json_loads(row["limitations"], []),
            created_at=row["created_at"],
            metadata=self._json_loads(row["metadata"], {}),
        )

    def save_camera_grammar_observation(self, observation: Any) -> Any:
        data = observation.model_dump(mode="json") if hasattr(observation, "model_dump") else dict(observation)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO camera_grammar_observations (
                        observation_id, project_id, plan_id, asset_id, render_job_id, scene_id, shot_id,
                        status, observation_scope, observed_composition, observed_lighting,
                        observed_camera_notes, observed_framing_tags, observed_lighting_tags,
                        observed_movement_evidence, keyframe_ids, analysis_ids, cinematic_memory_ids,
                        evidence_refs, confidence_label, limitations, created_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["observation_id"],
                        data["project_id"],
                        data.get("plan_id"),
                        data.get("asset_id"),
                        data.get("render_job_id"),
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("status") or "active",
                        data.get("observation_scope") or "asset",
                        data.get("observed_composition") or "",
                        data.get("observed_lighting") or "",
                        data.get("observed_camera_notes") or "",
                        self._json_dumps(data.get("observed_framing_tags", [])),
                        self._json_dumps(data.get("observed_lighting_tags", [])),
                        data.get("observed_movement_evidence") or "",
                        self._json_dumps(data.get("keyframe_ids", [])),
                        self._json_dumps(data.get("analysis_ids", [])),
                        self._json_dumps(data.get("cinematic_memory_ids", [])),
                        self._json_dumps(data.get("evidence_refs", [])),
                        data.get("confidence_label") or "low_data",
                        self._json_dumps(data.get("limitations", [])),
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data.get("metadata", {})),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_camera_grammar_observation", _write)
        return observation

    def get_camera_grammar_observation(self, observation_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM camera_grammar_observations WHERE observation_id = ?", (observation_id,))
            row = cursor.fetchone()
            return self._row_to_camera_grammar_observation(row) if row else None

    def list_camera_grammar_observations(
        self,
        project_id: str,
        plan_id: str | None = None,
        asset_id: str | None = None,
        render_job_id: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM camera_grammar_observations WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {
                "plan_id": plan_id,
                "asset_id": asset_id,
                "render_job_id": render_job_id,
                "scene_id": scene_id,
                "shot_id": shot_id,
            }
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [self._row_to_camera_grammar_observation(row) for row in cursor.fetchall()]

    def _row_to_camera_grammar_assessment(self, row: sqlite3.Row):
        from app.models.cinematography import (
            CameraGrammarAssessment,
            CameraGrammarEvidenceRef,
            CameraGrammarMemoryRef,
            CameraGrammarRevisionSuggestion,
            CameraGrammarRisk,
            CameraGrammarSpineRef,
        )

        return CameraGrammarAssessment(
            assessment_id=row["assessment_id"],
            project_id=row["project_id"],
            plan_id=row["plan_id"],
            observation_id=row["observation_id"],
            asset_id=row["asset_id"],
            render_job_id=row["render_job_id"],
            scene_id=row["scene_id"],
            shot_id=row["shot_id"],
            status=row["status"],
            alignment_summary=row["alignment_summary"],
            matched_axes=self._json_loads(row["matched_axes"], []),
            drift_axes=self._json_loads(row["drift_axes"], []),
            risks=[CameraGrammarRisk(**item) for item in self._json_loads(row["risks"], [])],
            revision_suggestions=[
                CameraGrammarRevisionSuggestion(**item)
                for item in self._json_loads(row["revision_suggestions"], [])
            ],
            evidence_refs=[CameraGrammarEvidenceRef(**item) for item in self._json_loads(row["evidence_refs"], [])],
            memory_refs=[CameraGrammarMemoryRef(**item) for item in self._json_loads(row["memory_refs"], [])],
            spine_refs=[CameraGrammarSpineRef(**item) for item in self._json_loads(row["spine_refs"], [])],
            crew_reasoning_id=row["crew_reasoning_id"],
            requires_creator_attention=bool(row["requires_creator_attention"]),
            confidence_label=row["confidence_label"],
            advisory_only=bool(row["advisory_only"]),
            created_at=row["created_at"],
            metadata=self._json_loads(row["metadata"], {}),
        )

    def save_camera_grammar_assessment(self, assessment: Any) -> Any:
        data = assessment.model_dump(mode="json") if hasattr(assessment, "model_dump") else dict(assessment)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO camera_grammar_assessments (
                        assessment_id, project_id, plan_id, observation_id, asset_id, render_job_id,
                        scene_id, shot_id, status, alignment_summary, matched_axes, drift_axes,
                        risks, revision_suggestions, evidence_refs, memory_refs, spine_refs,
                        crew_reasoning_id, requires_creator_attention, confidence_label,
                        advisory_only, created_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["assessment_id"],
                        data["project_id"],
                        data["plan_id"],
                        data["observation_id"],
                        data.get("asset_id"),
                        data.get("render_job_id"),
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("status") or "active",
                        data.get("alignment_summary") or "",
                        self._json_dumps(data.get("matched_axes", [])),
                        self._json_dumps(data.get("drift_axes", [])),
                        self._json_dumps(data.get("risks", [])),
                        self._json_dumps(data.get("revision_suggestions", [])),
                        self._json_dumps(data.get("evidence_refs", [])),
                        self._json_dumps(data.get("memory_refs", [])),
                        self._json_dumps(data.get("spine_refs", [])),
                        data.get("crew_reasoning_id"),
                        1 if data.get("requires_creator_attention", False) else 0,
                        data.get("confidence_label") or "emerging",
                        1 if data.get("advisory_only", True) else 0,
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data.get("metadata", {})),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_camera_grammar_assessment", _write)
        return assessment

    def get_camera_grammar_assessment(self, assessment_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM camera_grammar_assessments WHERE assessment_id = ?", (assessment_id,))
            row = cursor.fetchone()
            return self._row_to_camera_grammar_assessment(row) if row else None

    def list_camera_grammar_assessments(
        self,
        project_id: str,
        plan_id: str | None = None,
        observation_id: str | None = None,
        asset_id: str | None = None,
        render_job_id: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM camera_grammar_assessments WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {
                "plan_id": plan_id,
                "observation_id": observation_id,
                "asset_id": asset_id,
                "render_job_id": render_job_id,
                "scene_id": scene_id,
                "shot_id": shot_id,
            }
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [self._row_to_camera_grammar_assessment(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    # Performance Audio Intelligence
    # ------------------------------------------------------------------ #

    def _row_to_performance_audio_plan(self, row: sqlite3.Row):
        from app.models.performance_audio import (
            AudioEvidenceRef,
            AudioMemoryRef,
            AudioMixRequirement,
            AudioSpineRef,
            CharacterVoiceProfile,
            DialoguePerformanceCue,
            PerformanceAudioPlan,
            SoundscapeLayerPlan,
        )

        return PerformanceAudioPlan(
            plan_id=row["plan_id"],
            project_id=row["project_id"],
            scope=row["scope"],
            scene_id=row["scene_id"],
            shot_id=row["shot_id"],
            asset_id=row["asset_id"],
            status=row["status"],
            generated_at=row["generated_at"],
            updated_at=row["updated_at"],
            model_version=row["model_version"],
            source_signature=row["source_signature"],
            summary=row["summary"],
            voice_profiles=[
                CharacterVoiceProfile(**item)
                for item in self._json_loads(row["voice_profiles_json"], [])
            ],
            dialogue_cues=[
                DialoguePerformanceCue(**item)
                for item in self._json_loads(row["dialogue_cues_json"], [])
            ],
            soundscape_layers=[
                SoundscapeLayerPlan(**item)
                for item in self._json_loads(row["soundscape_layers_json"], [])
            ],
            mix_requirements=AudioMixRequirement(**self._json_loads(row["mix_requirements_json"], {})),
            provider_requirements=self._json_loads(row["provider_requirements_json"], []),
            reasoning_trace=self._json_loads(row["reasoning_trace_json"], []),
            evidence_refs=[AudioEvidenceRef(**item) for item in self._json_loads(row["evidence_refs_json"], [])],
            memory_refs=[AudioMemoryRef(**item) for item in self._json_loads(row["memory_refs_json"], [])],
            spine_refs=[AudioSpineRef(**item) for item in self._json_loads(row["spine_refs_json"], [])],
            crew_reasoning_id=row["crew_reasoning_id"],
            readiness_label=row["readiness_label"],
            blockers=self._json_loads(row["blockers_json"], []),
            stale=bool(row["stale"]),
            stale_reason=row["stale_reason"],
            advisory_only=bool(row["advisory_only"]),
        )

    def save_performance_audio_plan(self, plan: Any) -> Any:
        data = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else dict(plan)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO performance_audio_plans (
                        plan_id, project_id, scope, scene_id, shot_id, asset_id, status,
                        generated_at, updated_at, model_version, source_signature, summary,
                        voice_profiles_json, dialogue_cues_json, soundscape_layers_json,
                        mix_requirements_json, provider_requirements_json, reasoning_trace_json,
                        evidence_refs_json, memory_refs_json, spine_refs_json, crew_reasoning_id,
                        readiness_label, blockers_json, stale, stale_reason, advisory_only
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["plan_id"],
                        data["project_id"],
                        data.get("scope") or "scene",
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("asset_id"),
                        data.get("status") or "ready",
                        data.get("generated_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("model_version") or "performance-audio-v1",
                        data.get("source_signature") or "",
                        data.get("summary") or "",
                        self._json_dumps(data.get("voice_profiles", [])),
                        self._json_dumps(data.get("dialogue_cues", [])),
                        self._json_dumps(data.get("soundscape_layers", [])),
                        self._json_dumps(data.get("mix_requirements", {})),
                        self._json_dumps(data.get("provider_requirements", [])),
                        self._json_dumps(data.get("reasoning_trace", [])),
                        self._json_dumps(data.get("evidence_refs", [])),
                        self._json_dumps(data.get("memory_refs", [])),
                        self._json_dumps(data.get("spine_refs", [])),
                        data.get("crew_reasoning_id"),
                        data.get("readiness_label") or "needs_review",
                        self._json_dumps(data.get("blockers", [])),
                        1 if data.get("stale", False) else 0,
                        data.get("stale_reason") or "",
                        1 if data.get("advisory_only", True) else 0,
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_performance_audio_plan", _write)
        for profile in data.get("voice_profiles", []) or []:
            self.save_character_voice_profile(profile)
        for cue in data.get("dialogue_cues", []) or []:
            self.save_dialogue_performance_cue(cue)
        for layer in data.get("soundscape_layers", []) or []:
            self.save_soundscape_layer_plan(layer)
        return plan

    def get_performance_audio_plan(self, plan_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM performance_audio_plans WHERE plan_id = ?", (plan_id,))
            row = cursor.fetchone()
            return self._row_to_performance_audio_plan(row) if row else None

    def list_performance_audio_plans(
        self,
        project_id: str,
        scene_id: str | None = None,
        shot_id: str | None = None,
        status: str | None = None,
        stale: bool | None = None,
        limit: int = 50,
    ) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM performance_audio_plans WHERE project_id = ?"
            params: list[Any] = [project_id]
            if scene_id:
                query += " AND scene_id = ?"
                params.append(scene_id)
            if shot_id:
                query += " AND shot_id = ?"
                params.append(shot_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            if stale is not None:
                query += " AND stale = ?"
                params.append(1 if stale else 0)
            query += " ORDER BY generated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [self._row_to_performance_audio_plan(row) for row in cursor.fetchall()]

    def mark_performance_audio_plan_stale(self, plan_id: str, reason: str = "") -> bool:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE performance_audio_plans
                    SET status = ?, stale = 1, stale_reason = ?, updated_at = ?
                    WHERE plan_id = ?
                    """,
                    ("stale", reason or "Source inputs changed.", datetime.utcnow().isoformat() + "Z", plan_id),
                )
                conn.commit()
                return cursor.rowcount > 0

        return bool(self._execute_write_with_retry("mark_performance_audio_plan_stale", _write))

    def save_character_voice_profile(self, profile: Any) -> Any:
        data = profile.model_dump(mode="json") if hasattr(profile, "model_dump") else dict(profile)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO character_voice_profiles (
                        profile_id, project_id, character_id, character_name, source_signature,
                        status, stale, created_at, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["profile_id"],
                        data["project_id"],
                        data["character_id"],
                        data.get("character_name") or data["character_id"],
                        data.get("source_signature") or "",
                        data.get("status") or "ready",
                        1 if data.get("stale", False) else 0,
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_character_voice_profile", _write)
        return profile

    def get_character_voice_profile(self, profile_id: str) -> Any | None:
        from app.models.performance_audio import CharacterVoiceProfile

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload_json FROM character_voice_profiles WHERE profile_id = ?", (profile_id,))
            row = cursor.fetchone()
            return CharacterVoiceProfile(**self._json_loads(row["payload_json"], {})) if row else None

    def list_character_voice_profiles(
        self,
        project_id: str,
        character_id: str | None = None,
        stale: bool | None = None,
        limit: int = 50,
    ) -> list[Any]:
        from app.models.performance_audio import CharacterVoiceProfile

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM character_voice_profiles WHERE project_id = ?"
            params: list[Any] = [project_id]
            if character_id:
                query += " AND character_id = ?"
                params.append(character_id)
            if stale is not None:
                query += " AND stale = ?"
                params.append(1 if stale else 0)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [CharacterVoiceProfile(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_dialogue_performance_cue(self, cue: Any) -> Any:
        data = cue.model_dump(mode="json") if hasattr(cue, "model_dump") else dict(cue)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO dialogue_performance_cues (
                        cue_id, project_id, plan_id, scene_id, shot_id, line_id,
                        character_id, character_name, uncertainty_label, advisory_only, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["cue_id"],
                        data["project_id"],
                        data["plan_id"],
                        data["scene_id"],
                        data.get("shot_id"),
                        data["line_id"],
                        data["character_id"],
                        data.get("character_name") or data["character_id"],
                        data.get("uncertainty_label") or "emerging",
                        1 if data.get("advisory_only", True) else 0,
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_dialogue_performance_cue", _write)
        return cue

    def list_dialogue_performance_cues(
        self,
        project_id: str,
        plan_id: str | None = None,
        scene_id: str | None = None,
        character_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from app.models.performance_audio import DialoguePerformanceCue

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM dialogue_performance_cues WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {"plan_id": plan_id, "scene_id": scene_id, "character_id": character_id}
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            query += " ORDER BY line_id ASC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [DialoguePerformanceCue(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_soundscape_layer_plan(self, layer: Any) -> Any:
        data = layer.model_dump(mode="json") if hasattr(layer, "model_dump") else dict(layer)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO soundscape_layer_plans (
                        layer_id, project_id, plan_id, scene_id, shot_id, track_type,
                        label, advisory_only, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["layer_id"],
                        data["project_id"],
                        data["plan_id"],
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data["track_type"],
                        data.get("label") or "",
                        1 if data.get("advisory_only", True) else 0,
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_soundscape_layer_plan", _write)
        return layer

    def list_soundscape_layer_plans(
        self,
        project_id: str,
        plan_id: str | None = None,
        scene_id: str | None = None,
        track_type: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from app.models.performance_audio import SoundscapeLayerPlan

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM soundscape_layer_plans WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {"plan_id": plan_id, "scene_id": scene_id, "track_type": track_type}
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            query += " ORDER BY track_type ASC, layer_id ASC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [SoundscapeLayerPlan(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_audio_intelligence_assessment(self, assessment: Any) -> Any:
        data = assessment.model_dump(mode="json") if hasattr(assessment, "model_dump") else dict(assessment)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO audio_intelligence_assessments (
                        assessment_id, project_id, plan_id, scene_id, shot_id, asset_id, render_job_id,
                        generated_at, source_signature, observed_audio_stream, readiness_label, stale, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["assessment_id"],
                        data["project_id"],
                        data["plan_id"],
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("asset_id"),
                        data.get("render_job_id"),
                        data.get("generated_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("source_signature") or "",
                        1 if data.get("observed_audio_stream", False) else 0,
                        data.get("readiness_label") or "needs_review",
                        1 if data.get("stale", False) else 0,
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_audio_intelligence_assessment", _write)
        return assessment

    def get_audio_intelligence_assessment(self, assessment_id: str) -> Any | None:
        from app.models.performance_audio import AudioIntelligenceAssessment

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload_json FROM audio_intelligence_assessments WHERE assessment_id = ?", (assessment_id,))
            row = cursor.fetchone()
            return AudioIntelligenceAssessment(**self._json_loads(row["payload_json"], {})) if row else None

    def list_audio_intelligence_assessments(
        self,
        project_id: str,
        plan_id: str | None = None,
        asset_id: str | None = None,
        render_job_id: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        readiness_label: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        from app.models.performance_audio import AudioIntelligenceAssessment

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM audio_intelligence_assessments WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {
                "plan_id": plan_id,
                "asset_id": asset_id,
                "render_job_id": render_job_id,
                "scene_id": scene_id,
                "shot_id": shot_id,
                "readiness_label": readiness_label,
            }
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            query += " ORDER BY generated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [
                AudioIntelligenceAssessment(**self._json_loads(row["payload_json"], {}))
                for row in cursor.fetchall()
            ]

    def save_audio_decision_memory_projection(self, decision: Any) -> Any:
        data = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO audio_decision_memory_projections (
                        decision_id, project_id, decision_text, inferred_tradeoff, scene_id,
                        character_id, plan_id, cue_id, layer_id, profile_id, assessment_id,
                        saved_by, saved_at, memory_entry_id, editable, forgotten_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["decision_id"],
                        data["project_id"],
                        data["decision_text"],
                        data.get("inferred_tradeoff") or "",
                        data.get("scene_id"),
                        data.get("character_id"),
                        data.get("plan_id"),
                        data.get("cue_id"),
                        data.get("layer_id"),
                        data.get("profile_id"),
                        data.get("assessment_id"),
                        data.get("saved_by") or "creator",
                        data.get("saved_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("memory_entry_id"),
                        1 if data.get("editable", True) else 0,
                        data.get("forgotten_at"),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_audio_decision_memory_projection", _write)
        return decision

    def get_audio_decision_memory_projection(self, decision_id: str) -> Any | None:
        from app.models.performance_audio import PerformanceAudioDecisionProjection

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audio_decision_memory_projections WHERE decision_id = ?", (decision_id,))
            row = cursor.fetchone()
            return PerformanceAudioDecisionProjection(**dict(row)) if row else None

    def list_audio_decision_memory_projections(self, project_id: str, limit: int = 50) -> list[Any]:
        from app.models.performance_audio import PerformanceAudioDecisionProjection

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM audio_decision_memory_projections
                WHERE project_id = ?
                ORDER BY saved_at DESC
                LIMIT ?
                """,
                (project_id, max(1, min(int(limit), 500))),
            )
            return [PerformanceAudioDecisionProjection(**dict(row)) for row in cursor.fetchall()]

    def update_audio_decision_memory_projection(
        self,
        decision_id: str,
        *,
        decision_text: str | None = None,
        inferred_tradeoff: str | None = None,
        forgotten_at: str | None = None,
    ) -> Any | None:
        current = self.get_audio_decision_memory_projection(decision_id)
        if current is None:
            return None
        data = current.model_dump(mode="json")
        if decision_text is not None:
            data["decision_text"] = decision_text
        if inferred_tradeoff is not None:
            data["inferred_tradeoff"] = inferred_tradeoff
        if forgotten_at is not None:
            data["forgotten_at"] = forgotten_at
        from app.models.performance_audio import PerformanceAudioDecisionProjection

        updated = PerformanceAudioDecisionProjection(**data)
        self.save_audio_decision_memory_projection(updated)
        return updated

    # ------------------------------------------------------------------ #
    # Production Design Intelligence
    # ------------------------------------------------------------------ #

    def save_production_design_plan(self, plan: Any) -> Any:
        data = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else dict(plan)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO production_design_plans (
                        plan_id, project_id, scope, scene_id, shot_id, asset_id, render_job_id,
                        status, generated_at, updated_at, source_signature, readiness_label,
                        stale, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["plan_id"],
                        data["project_id"],
                        data.get("scope") or "scene",
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("asset_id"),
                        data.get("render_job_id"),
                        data.get("status") or "ready",
                        data.get("generated_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("source_signature") or "",
                        data.get("readiness_label") or "needs_review",
                        1 if data.get("stale", False) else 0,
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_production_design_plan", _write)
        if data.get("environment_profile"):
            self.save_production_design_environment_profile(data["environment_profile"])
        for record in data.get("prop_records", []) or []:
            self.save_production_design_prop_record(record)
        for record in data.get("costume_records", []) or []:
            self.save_production_design_costume_record(record)
        return plan

    def get_production_design_plan(self, plan_id: str) -> Any | None:
        from app.models.production_design import ProductionDesignPlan

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload_json FROM production_design_plans WHERE plan_id = ?", (plan_id,))
            row = cursor.fetchone()
            return ProductionDesignPlan(**self._json_loads(row["payload_json"], {})) if row else None

    def list_production_design_plans(
        self,
        project_id: str,
        scene_id: str | None = None,
        shot_id: str | None = None,
        asset_id: str | None = None,
        render_job_id: str | None = None,
        status: str | None = None,
        stale: bool | None = None,
        limit: int = 50,
    ) -> list[Any]:
        from app.models.production_design import ProductionDesignPlan

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM production_design_plans WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {
                "scene_id": scene_id,
                "shot_id": shot_id,
                "asset_id": asset_id,
                "render_job_id": render_job_id,
                "status": status,
            }
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            if stale is not None:
                query += " AND stale = ?"
                params.append(1 if stale else 0)
            query += " ORDER BY generated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [ProductionDesignPlan(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def mark_production_design_plan_stale(self, plan_id: str, reason: str = "") -> bool:
        current = self.get_production_design_plan(plan_id)
        if current is None:
            return False
        data = current.model_dump(mode="json")
        data["status"] = "stale"
        data["stale"] = True
        data["stale_reason"] = reason or "Source inputs changed."
        data["updated_at"] = datetime.utcnow().isoformat() + "Z"
        from app.models.production_design import ProductionDesignPlan

        self.save_production_design_plan(ProductionDesignPlan(**data))
        return True

    def save_production_design_environment_profile(self, profile: Any) -> Any:
        data = profile.model_dump(mode="json") if hasattr(profile, "model_dump") else dict(profile)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO production_design_environment_profiles (
                        profile_id, project_id, location_id, location_name, status, stale, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["profile_id"],
                        data["project_id"],
                        data.get("location_id"),
                        data.get("location_name") or "unspecified location",
                        data.get("status") or "ready",
                        1 if data.get("stale", False) else 0,
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_production_design_environment_profile", _write)
        return profile

    def list_production_design_environment_profiles(
        self,
        project_id: str,
        location_name: str | None = None,
        location_id: str | None = None,
        stale: bool | None = None,
        limit: int = 50,
    ) -> list[Any]:
        from app.models.production_design import EnvironmentDesignProfile

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM production_design_environment_profiles WHERE project_id = ?"
            params: list[Any] = [project_id]
            if location_name:
                query += " AND location_name = ?"
                params.append(location_name)
            if location_id:
                query += " AND location_id = ?"
                params.append(location_id)
            if stale is not None:
                query += " AND stale = ?"
                params.append(1 if stale else 0)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [EnvironmentDesignProfile(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_production_design_prop_record(self, record: Any) -> Any:
        data = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO production_design_prop_records (
                        prop_record_id, project_id, prop_id, prop_name, status, stale, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["prop_record_id"],
                        data["project_id"],
                        data["prop_id"],
                        data.get("prop_name") or data["prop_id"],
                        data.get("status") or "ready",
                        1 if data.get("stale", False) else 0,
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_production_design_prop_record", _write)
        return record

    def list_production_design_prop_records(
        self,
        project_id: str,
        prop_id: str | None = None,
        prop_name: str | None = None,
        stale: bool | None = None,
        limit: int = 50,
    ) -> list[Any]:
        from app.models.production_design import PropContinuityRecord

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM production_design_prop_records WHERE project_id = ?"
            params: list[Any] = [project_id]
            if prop_id:
                query += " AND prop_id = ?"
                params.append(prop_id)
            if prop_name:
                query += " AND prop_name = ?"
                params.append(prop_name)
            if stale is not None:
                query += " AND stale = ?"
                params.append(1 if stale else 0)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [PropContinuityRecord(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_production_design_costume_record(self, record: Any) -> Any:
        data = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO production_design_costume_records (
                        costume_record_id, project_id, character_id, scene_id, shot_id,
                        status, stale, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["costume_record_id"],
                        data["project_id"],
                        data["character_id"],
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("status") or "ready",
                        1 if data.get("stale", False) else 0,
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_production_design_costume_record", _write)
        return record

    def list_production_design_costume_records(
        self,
        project_id: str,
        character_id: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        stale: bool | None = None,
        limit: int = 50,
    ) -> list[Any]:
        from app.models.production_design import CostumeContinuityRecord

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM production_design_costume_records WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {"character_id": character_id, "scene_id": scene_id, "shot_id": shot_id}
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            if stale is not None:
                query += " AND stale = ?"
                params.append(1 if stale else 0)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [CostumeContinuityRecord(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_production_design_observation(self, observation: Any) -> Any:
        data = observation.model_dump(mode="json") if hasattr(observation, "model_dump") else dict(observation)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO production_design_observations (
                        observation_id, project_id, plan_id, asset_id, render_job_id,
                        scene_id, shot_id, status, created_at, confidence_label, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["observation_id"],
                        data["project_id"],
                        data.get("plan_id"),
                        data.get("asset_id"),
                        data.get("render_job_id"),
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("status") or "ready",
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("confidence_label") or "low_data",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_production_design_observation", _write)
        return observation

    def get_production_design_observation(self, observation_id: str) -> Any | None:
        from app.models.production_design import ProductionDesignObservation

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload_json FROM production_design_observations WHERE observation_id = ?", (observation_id,))
            row = cursor.fetchone()
            return ProductionDesignObservation(**self._json_loads(row["payload_json"], {})) if row else None

    def list_production_design_observations(
        self,
        project_id: str,
        plan_id: str | None = None,
        asset_id: str | None = None,
        render_job_id: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        from app.models.production_design import ProductionDesignObservation

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM production_design_observations WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {"plan_id": plan_id, "asset_id": asset_id, "render_job_id": render_job_id, "scene_id": scene_id, "shot_id": shot_id}
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [ProductionDesignObservation(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_production_design_assessment(self, assessment: Any) -> Any:
        data = assessment.model_dump(mode="json") if hasattr(assessment, "model_dump") else dict(assessment)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO production_design_assessments (
                        assessment_id, project_id, plan_id, observation_id, asset_id, render_job_id,
                        scene_id, shot_id, status, generated_at, requires_creator_attention,
                        confidence_label, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["assessment_id"],
                        data["project_id"],
                        data["plan_id"],
                        data["observation_id"],
                        data.get("asset_id"),
                        data.get("render_job_id"),
                        data.get("scene_id"),
                        data.get("shot_id"),
                        data.get("status") or "ready",
                        data.get("generated_at") or datetime.utcnow().isoformat() + "Z",
                        1 if data.get("requires_creator_attention", False) else 0,
                        data.get("confidence_label") or "emerging",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_production_design_assessment", _write)
        return assessment

    def get_production_design_assessment(self, assessment_id: str) -> Any | None:
        from app.models.production_design import ProductionDesignAssessment

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT payload_json FROM production_design_assessments WHERE assessment_id = ?", (assessment_id,))
            row = cursor.fetchone()
            return ProductionDesignAssessment(**self._json_loads(row["payload_json"], {})) if row else None

    def list_production_design_assessments(
        self,
        project_id: str,
        plan_id: str | None = None,
        observation_id: str | None = None,
        asset_id: str | None = None,
        render_job_id: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        from app.models.production_design import ProductionDesignAssessment

        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT payload_json FROM production_design_assessments WHERE project_id = ?"
            params: list[Any] = [project_id]
            filters = {
                "plan_id": plan_id,
                "observation_id": observation_id,
                "asset_id": asset_id,
                "render_job_id": render_job_id,
                "scene_id": scene_id,
                "shot_id": shot_id,
                "status": status,
            }
            for column, value in filters.items():
                if value:
                    query += f" AND {column} = ?"
                    params.append(value)
            query += " ORDER BY generated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [ProductionDesignAssessment(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_production_design_decision_memory_projection(self, decision: Any) -> Any:
        data = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO production_design_decision_memory_projections (
                        decision_id, project_id, decision_text, inferred_tradeoff, scene_id,
                        character_id, plan_id, prop_record_id, costume_record_id,
                        environment_profile_id, assessment_id, saved_by, saved_at,
                        memory_entry_id, editable, forgotten_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["decision_id"],
                        data["project_id"],
                        data["decision_text"],
                        data.get("inferred_tradeoff") or "",
                        data.get("scene_id"),
                        data.get("character_id"),
                        data.get("plan_id"),
                        data.get("prop_record_id"),
                        data.get("costume_record_id"),
                        data.get("environment_profile_id"),
                        data.get("assessment_id"),
                        data.get("saved_by") or "creator",
                        data.get("saved_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("memory_entry_id"),
                        1 if data.get("editable", True) else 0,
                        data.get("forgotten_at"),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_production_design_decision_memory_projection", _write)
        return decision

    def list_production_design_decision_memory_projections(self, project_id: str, limit: int = 50) -> list[Any]:
        from app.models.production_design import ProductionDesignDecisionProjection

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM production_design_decision_memory_projections
                WHERE project_id = ?
                ORDER BY saved_at DESC
                LIMIT ?
                """,
                (project_id, max(1, min(int(limit), 500))),
            )
            return [ProductionDesignDecisionProjection(**dict(row)) for row in cursor.fetchall()]

    def get_production_design_decision_memory_projection(self, decision_id: str) -> Any | None:
        from app.models.production_design import ProductionDesignDecisionProjection

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM production_design_decision_memory_projections WHERE decision_id = ?", (decision_id,))
            row = cursor.fetchone()
            return ProductionDesignDecisionProjection(**dict(row)) if row else None

    def update_production_design_decision_memory_projection(
        self,
        decision_id: str,
        *,
        decision_text: str | None = None,
        inferred_tradeoff: str | None = None,
        forgotten_at: str | None = None,
    ) -> Any | None:
        current = self.get_production_design_decision_memory_projection(decision_id)
        if current is None:
            return None
        data = current.model_dump(mode="json")
        if decision_text is not None:
            data["decision_text"] = decision_text
        if inferred_tradeoff is not None:
            data["inferred_tradeoff"] = inferred_tradeoff
        if forgotten_at is not None:
            data["forgotten_at"] = forgotten_at
        from app.models.production_design import ProductionDesignDecisionProjection

        updated = ProductionDesignDecisionProjection(**data)
        self.save_production_design_decision_memory_projection(updated)
        return updated

    def save_performance_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(analysis or {})
        now = datetime.now().isoformat()
        payload.setdefault("generated_at", now)
        payload.setdefault("updated_at", now)
        payload.setdefault("model_version", "performance-intelligence-v1")
        payload.setdefault("summary", "")
        payload.setdefault("reasoning_trace", [])
        payload.setdefault("guardrail_report", {})

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_analyses (
                        analysis_id, project_id, scene_id, analysis_scope, status,
                        generated_at, updated_at, source_signature, model_version,
                        summary_json, reasoning_trace_json, guardrail_report_json, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["analysis_id"],
                        payload["project_id"],
                        payload.get("scene_id"),
                        payload.get("analysis_scope", "scene"),
                        payload.get("status", "complete"),
                        payload["generated_at"],
                        payload["updated_at"],
                        payload.get("source_signature", ""),
                        payload["model_version"],
                        json.dumps({"summary": payload.get("summary", "")}, ensure_ascii=True, sort_keys=True),
                        json.dumps(payload.get("reasoning_trace", []), ensure_ascii=True, sort_keys=True),
                        json.dumps(payload.get("guardrail_report", {}), ensure_ascii=True, sort_keys=True),
                        json.dumps(payload, ensure_ascii=True, sort_keys=True),
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_analysis", operation)

    def get_latest_performance_analysis(self, project_id: str, scene_id: str | None = None) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            if scene_id:
                row = conn.execute(
                    "SELECT payload_json FROM performance_analyses WHERE project_id = ? AND scene_id = ? ORDER BY generated_at DESC LIMIT 1",
                    (project_id, scene_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT payload_json FROM performance_analyses WHERE project_id = ? ORDER BY generated_at DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
        if not row:
            return None
        try:
            parsed = json.loads(row["payload_json"] or "{}")
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def list_performance_analyses(
        self,
        project_id: str,
        *,
        scene_id: str | None = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 500))
        with self._get_connection() as conn:
            if scene_id:
                rows = conn.execute(
                    "SELECT payload_json FROM performance_analyses WHERE project_id = ? AND scene_id = ? ORDER BY generated_at DESC LIMIT ?",
                    (project_id, scene_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload_json FROM performance_analyses WHERE project_id = ? ORDER BY generated_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                parsed = json.loads(row["payload_json"] or "{}")
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                out.append(parsed)
        return out

    def save_performance_brief(self, brief: Dict[str, Any], *, analysis_id: str, project_id: str) -> Dict[str, Any]:
        payload = dict(brief or {})
        now = datetime.now().isoformat()
        payload.setdefault("created_at", now)
        payload.setdefault("updated_at", now)
        uncertainty = payload.get("uncertainty") if isinstance(payload.get("uncertainty"), dict) else {}

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_briefs (
                        brief_id, analysis_id, project_id, scene_id, character_id, character_name,
                        objective, obstacle, tactic, emotional_start, emotional_end, mask, reveal,
                        subtext_summary, continuity_note, uncertainty_label, uncertainty_reason,
                        payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["brief_id"],
                        analysis_id,
                        project_id,
                        payload.get("scene_id", ""),
                        payload.get("character_id", ""),
                        payload.get("character_name", ""),
                        payload.get("objective", ""),
                        payload.get("obstacle", ""),
                        payload.get("tactic", ""),
                        payload.get("emotional_start", ""),
                        payload.get("emotional_end", ""),
                        payload.get("mask", ""),
                        payload.get("reveal", ""),
                        payload.get("subtext_summary", ""),
                        payload.get("continuity_note", ""),
                        uncertainty.get("label", "emerging"),
                        uncertainty.get("reason", ""),
                        json.dumps(payload, ensure_ascii=True, sort_keys=True),
                        payload["created_at"],
                        payload["updated_at"],
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_brief", operation)

    def list_performance_briefs_for_scene(self, project_id: str, scene_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM performance_briefs WHERE project_id = ? AND scene_id = ? ORDER BY created_at DESC",
                (project_id, scene_id),
            ).fetchall()
        return [json.loads(row["payload_json"] or "{}") for row in rows]

    def list_performance_briefs_for_character(self, project_id: str, character_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 500))
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM performance_briefs WHERE project_id = ? AND character_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, character_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"] or "{}") for row in rows]

    def save_performance_beat(self, beat: Dict[str, Any], *, brief_id: str, project_id: str, scene_id: str, character_id: str) -> Dict[str, Any]:
        payload = dict(beat or {})
        payload.setdefault("created_at", datetime.now().isoformat())

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_beats (
                        beat_id, brief_id, project_id, scene_id, character_id, beat_index,
                        beat_label, visible_action, internal_action, dialogue_subtext,
                        physical_direction, voice_direction, camera_relevance,
                        evidence_json, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["beat_id"],
                        brief_id,
                        project_id,
                        scene_id,
                        character_id,
                        int(payload.get("beat_index", 0)),
                        payload.get("beat_label", ""),
                        payload.get("visible_action", ""),
                        payload.get("internal_action", ""),
                        payload.get("dialogue_subtext", ""),
                        payload.get("physical_direction", ""),
                        payload.get("voice_direction", ""),
                        payload.get("camera_relevance", ""),
                        json.dumps(payload.get("evidence_refs", []), ensure_ascii=True, sort_keys=True),
                        json.dumps(payload, ensure_ascii=True, sort_keys=True),
                        payload["created_at"],
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_beat", operation)

    def save_performance_relationship_read(self, relationship: Dict[str, Any], *, analysis_id: str, project_id: str) -> Dict[str, Any]:
        payload = dict(relationship or {})
        payload.setdefault("created_at", datetime.now().isoformat())
        uncertainty = payload.get("uncertainty") if isinstance(payload.get("uncertainty"), dict) else {}

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_relationship_reads (
                        relationship_read_id, analysis_id, project_id, scene_id,
                        character_a, character_b, relationship_state, pressure, power_shift,
                        trust_state, conflict_residue, evidence_json, uncertainty_label,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["relationship_read_id"],
                        analysis_id,
                        project_id,
                        payload.get("scene_id", ""),
                        payload.get("character_a", ""),
                        payload.get("character_b", ""),
                        payload.get("relationship_state", ""),
                        payload.get("pressure", ""),
                        payload.get("power_shift", ""),
                        payload.get("trust_state", ""),
                        payload.get("conflict_residue", ""),
                        json.dumps(payload.get("evidence_refs", []), ensure_ascii=True, sort_keys=True),
                        uncertainty.get("label", "emerging"),
                        json.dumps(payload, ensure_ascii=True, sort_keys=True),
                        payload["created_at"],
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_relationship_read", operation)

    def save_performance_evidence_refs(
        self,
        refs: List[Dict[str, Any]],
        *,
        analysis_id: str,
        project_id: str,
        brief_id: str | None = None,
        beat_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        rows = [dict(ref or {}) for ref in refs or []]
        now = datetime.now().isoformat()

        def operation():
            with self._get_connection() as conn:
                for payload in rows:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO performance_evidence_refs (
                            evidence_id, analysis_id, brief_id, beat_id, project_id,
                            source_type, source_id, scene_id, character_id, field_path,
                            excerpt, relevance, reliability_label, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            payload["evidence_id"],
                            analysis_id,
                            brief_id,
                            beat_id,
                            project_id,
                            payload.get("source_type", ""),
                            payload.get("source_id", ""),
                            payload.get("scene_id"),
                            payload.get("character_id"),
                            payload.get("field_path", ""),
                            payload.get("excerpt", ""),
                            payload.get("relevance", ""),
                            payload.get("reliability_label", "emerging"),
                            payload.get("created_at", now),
                        ),
                    )
                conn.commit()
            return rows

        return self._execute_write_with_retry("save_performance_evidence_refs", operation)

    def save_performance_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(decision or {})
        payload.setdefault("saved_at", datetime.now().isoformat())
        payload.setdefault("editable", True)

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_decisions (
                        decision_id, project_id, scene_id, character_id, source_brief_id,
                        decision_text, inferred_tradeoff, saved_by, saved_at,
                        memory_entry_id, editable, forgotten_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["decision_id"],
                        payload["project_id"],
                        payload.get("scene_id"),
                        payload.get("character_id"),
                        payload.get("source_brief_id"),
                        payload.get("decision_text", ""),
                        payload.get("inferred_tradeoff", ""),
                        payload.get("saved_by", "creator"),
                        payload["saved_at"],
                        payload.get("memory_entry_id"),
                        1 if payload.get("editable", True) else 0,
                        payload.get("forgotten_at"),
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_decision", operation)

    def list_performance_decisions(
        self,
        project_id: str,
        *,
        character_id: str | None = None,
        include_forgotten: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 500))
        clauses = ["project_id = ?"]
        params: List[Any] = [project_id]
        if character_id:
            clauses.append("character_id = ?")
            params.append(character_id)
        if not include_forgotten:
            clauses.append("forgotten_at IS NULL")
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM performance_decisions WHERE {' AND '.join(clauses)} ORDER BY saved_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [
            {
                "decision_id": row["decision_id"],
                "project_id": row["project_id"],
                "scene_id": row["scene_id"],
                "character_id": row["character_id"],
                "source_brief_id": row["source_brief_id"],
                "decision_text": row["decision_text"],
                "inferred_tradeoff": row["inferred_tradeoff"],
                "saved_by": row["saved_by"],
                "saved_at": row["saved_at"],
                "memory_entry_id": row["memory_entry_id"],
                "editable": bool(row["editable"]),
                "forgotten_at": row["forgotten_at"],
            }
            for row in rows
        ]

    def update_performance_decision(self, project_id: str, decision_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current_rows = self.list_performance_decisions(project_id, include_forgotten=True, limit=500)
        current = next((row for row in current_rows if row.get("decision_id") == decision_id), None)
        if not current:
            return None
        payload = {**current}
        if "decision_text" in updates and str(updates.get("decision_text") or "").strip():
            payload["decision_text"] = str(updates["decision_text"]).strip()
        if "inferred_tradeoff" in updates:
            payload["inferred_tradeoff"] = str(updates.get("inferred_tradeoff") or "").strip()
        return self.save_performance_decision(payload)

    def forget_performance_decision(self, project_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
        current_rows = self.list_performance_decisions(project_id, include_forgotten=True, limit=500)
        current = next((row for row in current_rows if row.get("decision_id") == decision_id), None)
        if not current:
            return None
        current["forgotten_at"] = datetime.now().isoformat()
        return self.save_performance_decision(current)

    def set_project_poster_url(self, project_id: str, poster_url: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(projects)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "poster_url" not in columns:
                cursor.execute("ALTER TABLE projects ADD COLUMN poster_url TEXT")
            cursor.execute(
                "UPDATE projects SET poster_url = ?, updated_at = ? WHERE project_id = ?",
                (poster_url, datetime.now().isoformat(), project_id),
            )
            conn.commit()

    def get_project_poster_url(self, project_id: str) -> str | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(projects)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "poster_url" not in columns:
                return None
            cursor.execute("SELECT poster_url FROM projects WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            if row and row["poster_url"]:
                return row["poster_url"]
            return None

    # Universe Knowledge Graph
    def get_universe_nodes(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM universe_nodes WHERE project_id = ? ORDER BY created_at ASC", (project_id,))
            return [dict(row) for row in cursor.fetchall()]

    def save_universe_node(self, node: Dict[str, Any]) -> bool:
        now = datetime.now().isoformat()
        node_id = node["node_id"]
        project_id = node["project_id"]
        node_type = node["node_type"]
        name = node["name"]
        description = node.get("description", "")
        first_scene = node.get("first_scene", "")
        last_scene = node.get("last_scene", "")
        universe_tags = json.dumps(node.get("universe_tags", []))

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO universe_nodes
                       (node_id, project_id, node_type, name, description, first_scene, last_scene, universe_tags, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM universe_nodes WHERE node_id = ?), ?), ?)""",
                    (node_id, project_id, node_type, name, description, first_scene, last_scene, universe_tags, node_id, now, now),
                )
                conn.commit()

        self._execute_write_with_retry("save_universe_node", _write)
        return True

    def delete_universe_node(self, node_id: str) -> bool:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM universe_nodes WHERE node_id = ?", (node_id,))
                conn.commit()

        self._execute_write_with_retry("delete_universe_node", _write)
        return True

    def get_universe_relationships(self, project_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM universe_relationships WHERE project_id = ?", (project_id,))
            return [dict(row) for row in cursor.fetchall()]

    def save_universe_relationship(self, rel: Dict[str, Any]) -> bool:
        now = datetime.now().isoformat()
        relationship_id = rel["relationship_id"]
        project_id = rel["project_id"]
        from_node = rel["from_node"]
        to_node = rel["to_node"]
        relationship_type = rel["relationship_type"]
        description = rel.get("description", "")

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO universe_relationships
                       (relationship_id, project_id, from_node, to_node, relationship_type, description, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM universe_relationships WHERE relationship_id = ?), ?))""",
                    (relationship_id, project_id, from_node, to_node, relationship_type, description, relationship_id, now),
                )
                conn.commit()

        self._execute_write_with_retry("save_universe_relationship", _write)
        return True

    def delete_universe_relationship(self, relationship_id: str) -> bool:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM universe_relationships WHERE relationship_id = ?", (relationship_id,))
                conn.commit()

        self._execute_write_with_retry("delete_universe_relationship", _write)
        return True

    def delete_universe_project_data(self, project_id: str) -> bool:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM universe_relationships WHERE project_id = ?", (project_id,))
                cursor.execute("DELETE FROM universe_nodes WHERE project_id = ?", (project_id,))
                conn.commit()

        self._execute_write_with_retry("delete_universe_project_data", _write)
        return True

    def list_universe_project_ids(self) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT project_id FROM universe_nodes")
            return [row["project_id"] for row in cursor.fetchall()]

    # Render Job Persistence
    def save_job(self, job: RenderJobModel) -> RenderJobModel:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            columns = ['id', 'project_id', 'shot_id', 'provider', 'provider_job_id', 'status', 'progress',
                       'input_payload', 'output_payload', 'error_message', 'retry_count', 'created_at', 'updated_at', 'completed_at']
            values = [job.id, job.project_id, job.shot_id, job.provider, job.provider_job_id, job.status, job.progress,
                      json.dumps(job.input_payload.model_dump()) if job.input_payload else None,
                      json.dumps(job.output_payload.model_dump()) if job.output_payload else None,
                      job.error_message, job.retry_count, job.created_at, job.updated_at, job.completed_at]
            # Extensions may supply a stricter legacy table. Preserve its native
            # constraints instead of masking them with an unknown-column error.
            if 'metadata_json' in {row[1] for row in cursor.execute('PRAGMA table_info(render_jobs)')}:
                columns.append('metadata_json')
                values.append(json.dumps(job.metadata or {}))
            cursor.execute(
                f"INSERT OR REPLACE INTO render_jobs ({', '.join(columns)}) VALUES ({', '.join('?' for _ in values)})",
                values,
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

    def list_jobs_page(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 50), 200))
        cursor_created_at = None
        cursor_id = None
        if cursor:
            if "|" in cursor:
                cursor_created_at, cursor_id = cursor.split("|", 1)
            else:
                cursor_created_at = cursor
        with self._get_connection() as conn:
            db_cursor = conn.cursor()
            query = "SELECT * FROM render_jobs"
            params: list[Any] = []
            conditions: list[str] = []
            if project_id:
                conditions.append("project_id = ?")
                params.append(project_id)
            if status:
                conditions.append("status = ?")
                params.append(status)
            if cursor_created_at and cursor_id:
                conditions.append("(created_at < ? OR (created_at = ? AND id < ?))")
                params.extend([cursor_created_at, cursor_created_at, cursor_id])
            elif cursor_created_at:
                conditions.append("created_at < ?")
                params.append(cursor_created_at)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC, id DESC LIMIT ?"
            params.append(safe_limit + 1)
            rows = db_cursor.execute(query, params).fetchall()
        jobs = [self._row_to_job(row) for row in rows[:safe_limit]]
        has_more = len(rows) > safe_limit
        return {
            "items": jobs,
            "next_cursor": f"{jobs[-1].created_at}|{jobs[-1].id}" if has_more and jobs else None,
            "total_visible": len(jobs),
            "has_more": has_more,
            "filters": {
                "project_id": project_id or "",
                "status": status or "",
            },
        }

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
            metadata=json.loads(row["metadata_json"] or "{}") if "metadata_json" in row.keys() else None,
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

    # Production Queue Persistence
    def _json_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _row_to_queue_item(self, row: sqlite3.Row):
        from app.models.production_queue import ProductionQueueItem

        return ProductionQueueItem(
            queue_item_id=row["queue_item_id"],
            project_id=row["project_id"],
            scene_id=row["scene_id"],
            shot_id=row["shot_id"],
            work_type=row["work_type"],
            canonical_type=row["canonical_type"],
            canonical_id=row["canonical_id"],
            provider=row["provider"],
            status=row["status"],
            priority=row["priority"],
            idempotency_key=row["idempotency_key"],
            dependency_policy=row["dependency_policy"],
            payload=self._json_dict(row["payload_json"]),
            result=self._json_dict(row["result_json"]),
            failure=self._json_dict(row["failure_json"]),
            reason=row["reason"] or "",
            attempt_count=row["attempt_count"] or 0,
            max_attempts=row["max_attempts"] or 0,
            lease_owner=row["lease_owner"],
            lease_acquired_at=row["lease_acquired_at"],
            lease_expires_at=row["lease_expires_at"],
            next_run_at=row["next_run_at"],
            next_poll_at=row["next_poll_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def _row_to_queue_dependency(self, row: sqlite3.Row):
        from app.models.production_queue import ProductionQueueDependency

        return ProductionQueueDependency(
            dependency_id=row["dependency_id"],
            queue_item_id=row["queue_item_id"],
            depends_on_type=row["depends_on_type"],
            depends_on_id=row["depends_on_id"],
            required_status=row["required_status"],
            status=row["status"],
            reason=row["reason"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_queue_event(self, row: sqlite3.Row):
        from app.models.production_queue import ProductionQueueEvent

        return ProductionQueueEvent(
            event_id=row["event_id"],
            queue_item_id=row["queue_item_id"],
            project_id=row["project_id"],
            event_type=row["event_type"],
            stage=row["stage"],
            message=row["message"] or "",
            details=self._json_dict(row["details_json"]),
            created_at=row["created_at"],
        )

    def create_queue_item(self, item):
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO production_queue_items (
                        queue_item_id, project_id, scene_id, shot_id, work_type,
                        canonical_type, canonical_id, provider, status, priority,
                        idempotency_key, dependency_policy, payload_json, result_json,
                        failure_json, reason, attempt_count, max_attempts, lease_owner,
                        lease_acquired_at, lease_expires_at, next_run_at, next_poll_at,
                        created_at, updated_at, started_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.queue_item_id,
                        item.project_id,
                        item.scene_id,
                        item.shot_id,
                        item.work_type.value if hasattr(item.work_type, "value") else item.work_type,
                        item.canonical_type,
                        item.canonical_id,
                        item.provider,
                        item.status.value if hasattr(item.status, "value") else item.status,
                        item.priority,
                        item.idempotency_key,
                        item.dependency_policy,
                        json.dumps(item.payload or {}),
                        json.dumps(item.result or {}),
                        json.dumps(item.failure or {}),
                        item.reason or "",
                        item.attempt_count,
                        item.max_attempts,
                        item.lease_owner,
                        item.lease_acquired_at,
                        item.lease_expires_at,
                        item.next_run_at,
                        item.next_poll_at,
                        item.created_at,
                        item.updated_at,
                        item.started_at,
                        item.completed_at,
                    ),
                )
                conn.commit()
        self._execute_write_with_retry("create_queue_item", _write)
        return item

    def get_queue_item(self, queue_item_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM production_queue_items WHERE queue_item_id = ?",
                (queue_item_id,),
            )
            row = cursor.fetchone()
            return self._row_to_queue_item(row) if row else None

    def find_queue_item_by_idempotency_key(self, project_id: str, idempotency_key: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM production_queue_items
                   WHERE project_id = ? AND idempotency_key = ?""",
                (project_id, idempotency_key),
            )
            row = cursor.fetchone()
            return self._row_to_queue_item(row) if row else None

    def list_queue_items(
        self,
        project_id: str | None = None,
        status: str | None = None,
        work_type: str | None = None,
        provider: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ):
        from app.models.production_queue import ProductionQueuePage

        safe_limit = max(1, min(int(limit or 50), 200))
        cursor_created_at = None
        cursor_item_id = None
        if cursor:
            if "|" in cursor:
                cursor_created_at, cursor_item_id = cursor.split("|", 1)
            else:
                cursor_created_at = cursor
        query = "SELECT * FROM production_queue_items"
        conditions: list[str] = []
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if work_type:
            conditions.append("work_type = ?")
            params.append(work_type)
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        if cursor_created_at and cursor_item_id:
            conditions.append("(created_at < ? OR (created_at = ? AND queue_item_id < ?))")
            params.extend([cursor_created_at, cursor_created_at, cursor_item_id])
        elif cursor_created_at:
            conditions.append("created_at < ?")
            params.append(cursor_created_at)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC, queue_item_id DESC LIMIT ?"
        params.append(safe_limit + 1)
        with self._get_connection() as conn:
            rows = conn.cursor().execute(query, params).fetchall()
        items = [self._row_to_queue_item(row) for row in rows[:safe_limit]]
        has_more = len(rows) > safe_limit
        next_cursor = f"{items[-1].created_at}|{items[-1].queue_item_id}" if has_more and items else None
        return ProductionQueuePage(
            items=items,
            next_cursor=next_cursor,
            total_visible=len(items),
            has_more=has_more,
            filters={
                "project_id": project_id or "",
                "status": status or "",
                "work_type": work_type or "",
                "provider": provider or "",
            },
        )

    def list_queue_candidates(self, now: str, limit: int = 50):
        safe_limit = max(1, min(int(limit or 50), 200))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(
                """SELECT * FROM production_queue_items
                   WHERE status IN ('queued', 'waiting_provider')
                     AND (next_run_at IS NULL OR next_run_at <= ?)
                     AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                   ORDER BY priority DESC, created_at ASC, queue_item_id ASC
                   LIMIT ?""",
                (now, now, safe_limit),
            ).fetchall()
        return [self._row_to_queue_item(row) for row in rows]

    def update_queue_item(self, item):
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE production_queue_items
                       SET scene_id = ?, shot_id = ?, canonical_id = ?, provider = ?,
                           status = ?, priority = ?, dependency_policy = ?,
                           payload_json = ?, result_json = ?, failure_json = ?,
                           reason = ?, attempt_count = ?, max_attempts = ?,
                           lease_owner = ?, lease_acquired_at = ?, lease_expires_at = ?,
                           next_run_at = ?, next_poll_at = ?, updated_at = ?,
                           started_at = ?, completed_at = ?
                       WHERE queue_item_id = ?""",
                    (
                        item.scene_id,
                        item.shot_id,
                        item.canonical_id,
                        item.provider,
                        item.status.value if hasattr(item.status, "value") else item.status,
                        item.priority,
                        item.dependency_policy,
                        json.dumps(item.payload or {}),
                        json.dumps(item.result or {}),
                        json.dumps(item.failure or {}),
                        item.reason or "",
                        item.attempt_count,
                        item.max_attempts,
                        item.lease_owner,
                        item.lease_acquired_at,
                        item.lease_expires_at,
                        item.next_run_at,
                        item.next_poll_at,
                        item.updated_at,
                        item.started_at,
                        item.completed_at,
                        item.queue_item_id,
                    ),
                )
                conn.commit()
        self._execute_write_with_retry("update_queue_item", _write)
        return item

    def update_queue_item_status(
        self,
        queue_item_id: str,
        status: str,
        reason: str = "",
        result: dict[str, Any] | None = None,
        failure: dict[str, Any] | None = None,
    ):
        item = self.get_queue_item(queue_item_id)
        if item is None:
            return None
        item.status = status
        item.reason = reason or item.reason
        item.updated_at = datetime.now().isoformat()
        if result is not None:
            item.result = result
        if failure is not None:
            item.failure = failure
        if status in {"complete", "failed", "cancelled", "dead_lettered"}:
            item.completed_at = item.completed_at or item.updated_at
            item.lease_owner = None
            item.lease_acquired_at = None
            item.lease_expires_at = None
        return self.update_queue_item(item)

    def save_queue_dependency(self, dependency):
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO production_queue_dependencies (
                        dependency_id, queue_item_id, depends_on_type, depends_on_id,
                        required_status, status, reason, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        dependency.dependency_id,
                        dependency.queue_item_id,
                        dependency.depends_on_type.value if hasattr(dependency.depends_on_type, "value") else dependency.depends_on_type,
                        dependency.depends_on_id,
                        dependency.required_status,
                        dependency.status,
                        dependency.reason or "",
                        dependency.created_at,
                        dependency.updated_at,
                    ),
                )
                conn.commit()
        self._execute_write_with_retry("save_queue_dependency", _write)
        return dependency

    def list_queue_dependencies(self, queue_item_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM production_queue_dependencies
                   WHERE queue_item_id = ?
                   ORDER BY created_at ASC""",
                (queue_item_id,),
            )
            return [self._row_to_queue_dependency(row) for row in cursor.fetchall()]

    def count_active_queue_items(
        self,
        project_id: str | None = None,
        provider: str | None = None,
        work_type: str | None = None,
    ) -> int:
        conditions = ["status IN ('leased', 'running')"]
        params: list[Any] = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        if work_type:
            conditions.append("work_type = ?")
            params.append(work_type)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                f"SELECT COUNT(*) AS count FROM production_queue_items WHERE {' AND '.join(conditions)}",
                params,
            ).fetchone()
        return int(row["count"] or 0) if row else 0

    def acquire_queue_lease_for_item(
        self,
        queue_item_id: str,
        owner_id: str,
        now: str,
        lease_expires_at: str,
    ):
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE production_queue_items
                       SET status = 'leased',
                           lease_owner = ?,
                           lease_acquired_at = ?,
                           lease_expires_at = ?,
                           attempt_count = attempt_count + 1,
                           updated_at = ?,
                           started_at = COALESCE(started_at, ?)
                       WHERE queue_item_id = ?
                         AND status IN ('queued', 'waiting_provider')
                         AND (next_run_at IS NULL OR next_run_at <= ?)
                         AND (lease_expires_at IS NULL OR lease_expires_at <= ?)""",
                    (owner_id, now, lease_expires_at, now, now, queue_item_id, now, now),
                )
                changed = cursor.rowcount == 1
                conn.commit()
                return changed
        if self._execute_write_with_retry("acquire_queue_lease_for_item", _write):
            return self.get_queue_item(queue_item_id)
        return None

    def acquire_queue_lease(self, owner_id: str, now: str, lease_expires_at: str):
        candidate_statuses = ("queued", "waiting_provider")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute(
                """SELECT * FROM production_queue_items
                   WHERE status IN (?, ?)
                     AND (next_run_at IS NULL OR next_run_at <= ?)
                     AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                   ORDER BY priority DESC, created_at ASC
                   LIMIT 20""",
                (candidate_statuses[0], candidate_statuses[1], now, now),
            ).fetchall()
            for row in rows:
                queue_item_id = row["queue_item_id"]
                cursor.execute(
                    """UPDATE production_queue_items
                       SET status = 'leased',
                           lease_owner = ?,
                           lease_acquired_at = ?,
                           lease_expires_at = ?,
                           attempt_count = attempt_count + 1,
                           updated_at = ?,
                           started_at = COALESCE(started_at, ?)
                       WHERE queue_item_id = ?
                         AND status IN ('queued', 'waiting_provider')
                         AND (lease_expires_at IS NULL OR lease_expires_at <= ?)""",
                    (owner_id, now, lease_expires_at, now, now, queue_item_id, now),
                )
                if cursor.rowcount == 1:
                    conn.commit()
                    return self.get_queue_item(queue_item_id)
            conn.commit()
        return None

    def renew_queue_lease(self, queue_item_id: str, owner_id: str, lease_expires_at: str) -> bool:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE production_queue_items
                       SET lease_expires_at = ?, updated_at = ?
                       WHERE queue_item_id = ? AND lease_owner = ?""",
                    (lease_expires_at, datetime.now().isoformat(), queue_item_id, owner_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        return bool(self._execute_write_with_retry("renew_queue_lease", _write))

    def expire_stale_queue_leases(self, now: str) -> int:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE production_queue_items
                       SET status = CASE
                           WHEN attempt_count >= max_attempts THEN 'dead_lettered'
                           ELSE 'queued'
                       END,
                           reason = CASE
                               WHEN attempt_count >= max_attempts THEN 'Lease expired after max attempts'
                               ELSE 'Lease expired and was returned to queue'
                           END,
                           lease_owner = NULL,
                           lease_acquired_at = NULL,
                           lease_expires_at = NULL,
                           updated_at = ?
                       WHERE status IN ('leased', 'running')
                         AND lease_expires_at IS NOT NULL
                         AND lease_expires_at <= ?""",
                    (now, now),
                )
                count = cursor.rowcount
                conn.commit()
                return count
        return int(self._execute_write_with_retry("expire_stale_queue_leases", _write) or 0)

    def save_queue_attempt(self, attempt):
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO production_queue_attempts (
                        attempt_id, queue_item_id, attempt_number, lease_owner, status,
                        started_at, completed_at, duration_ms, error_type, error_message,
                        result_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        attempt.attempt_id,
                        attempt.queue_item_id,
                        attempt.attempt_number,
                        attempt.lease_owner,
                        attempt.status,
                        attempt.started_at,
                        attempt.completed_at,
                        attempt.duration_ms,
                        attempt.error_type,
                        attempt.error_message,
                        json.dumps(attempt.result or {}),
                        json.dumps(attempt.metadata or {}),
                    ),
                )
                conn.commit()
        self._execute_write_with_retry("save_queue_attempt", _write)
        return attempt

    def save_queue_event(self, event):
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO production_queue_events (
                        event_id, queue_item_id, project_id, event_type, stage,
                        message, details_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.event_id,
                        event.queue_item_id,
                        event.project_id,
                        event.event_type,
                        event.stage,
                        event.message or "",
                        json.dumps(event.details or {}),
                        event.created_at,
                    ),
                )
                conn.commit()
        self._execute_write_with_retry("save_queue_event", _write)
        return event

    def list_queue_events(self, queue_item_id: str, limit: int = 100):
        safe_limit = max(1, min(int(limit or 100), 500))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM production_queue_events
                   WHERE queue_item_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (queue_item_id, safe_limit),
            )
            return [self._row_to_queue_event(row) for row in cursor.fetchall()]

    def get_queue_summary(self, project_id: str | None = None):
        from app.models.production_queue import (
            ProductionProviderPressure,
            ProductionProjectThroughput,
            ProductionQueueSummary,
        )

        params: list[Any] = []
        where = ""
        if project_id:
            where = " WHERE project_id = ?"
            params.append(project_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            status_rows = cursor.execute(
                f"SELECT status, COUNT(*) AS count FROM production_queue_items{where} GROUP BY status",
                params,
            ).fetchall()
            work_rows = cursor.execute(
                f"SELECT work_type, COUNT(*) AS count FROM production_queue_items{where} GROUP BY work_type",
                params,
            ).fetchall()
            provider_rows = cursor.execute(
                f"""SELECT COALESCE(provider, 'unassigned') AS provider,
                          SUM(CASE WHEN status IN ('leased','running') THEN 1 ELSE 0 END) AS active,
                          SUM(CASE WHEN status IN ('queued','waiting_provider') THEN 1 ELSE 0 END) AS queued
                   FROM production_queue_items{where}
                   GROUP BY COALESCE(provider, 'unassigned')""",
                params,
            ).fetchall()
            project_rows = cursor.execute(
                """SELECT project_id,
                          SUM(CASE WHEN status IN ('leased','running') THEN 1 ELSE 0 END) AS active,
                          SUM(CASE WHEN status IN ('queued','waiting_provider') THEN 1 ELSE 0 END) AS queued,
                          SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) AS completed,
                          SUM(CASE WHEN status IN ('failed','dead_lettered') THEN 1 ELSE 0 END) AS failed
                   FROM production_queue_items
                   GROUP BY project_id
                   ORDER BY queued DESC, active DESC
                   LIMIT 20"""
                if not project_id
                else """SELECT project_id,
                          SUM(CASE WHEN status IN ('leased','running') THEN 1 ELSE 0 END) AS active,
                          SUM(CASE WHEN status IN ('queued','waiting_provider') THEN 1 ELSE 0 END) AS queued,
                          SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) AS completed,
                          SUM(CASE WHEN status IN ('failed','dead_lettered') THEN 1 ELSE 0 END) AS failed
                   FROM production_queue_items
                   WHERE project_id = ?
                   GROUP BY project_id""",
                params if project_id else [],
            ).fetchall()
            oldest_row = cursor.execute(
                f"""SELECT * FROM production_queue_items{where}
                    {"AND" if where else "WHERE"} status IN ('queued','waiting_provider','waiting_dependency','blocked')
                    ORDER BY created_at ASC LIMIT 1""",
                params,
            ).fetchone()
            stale_rows = cursor.execute(
                f"""SELECT COUNT(*) AS count FROM production_queue_items{where}
                    {"AND" if where else "WHERE"} status IN ('leased','running')
                    AND lease_expires_at IS NOT NULL
                    AND lease_expires_at <= ?""",
                [*params, datetime.now().isoformat()],
            ).fetchone()
            failure_rows = cursor.execute(
                f"""SELECT * FROM production_queue_items{where}
                    {"AND" if where else "WHERE"} status IN ('failed','dead_lettered')
                    ORDER BY updated_at DESC LIMIT 5""",
                params,
            ).fetchall()
            blocked_rows = cursor.execute(
                f"""SELECT reason FROM production_queue_items{where}
                    {"AND" if where else "WHERE"} status IN ('blocked','waiting_dependency','waiting_creator')
                    AND reason != ''
                    ORDER BY updated_at DESC LIMIT 10""",
                params,
            ).fetchall()

        provider_pressure = [
            ProductionProviderPressure(
                provider=row["provider"],
                active=int(row["active"] or 0),
                queued=int(row["queued"] or 0),
                limit=0,
                status="at_capacity" if int(row["active"] or 0) > 0 and int(row["queued"] or 0) > 0 else "available",
            )
            for row in provider_rows
        ]
        return ProductionQueueSummary(
            project_id=project_id,
            counts_by_status={row["status"]: int(row["count"] or 0) for row in status_rows},
            counts_by_work_type={row["work_type"]: int(row["count"] or 0) for row in work_rows},
            provider_pressure=provider_pressure,
            project_throughput=[
                ProductionProjectThroughput(
                    project_id=row["project_id"],
                    active=int(row["active"] or 0),
                    queued=int(row["queued"] or 0),
                    completed=int(row["completed"] or 0),
                    failed=int(row["failed"] or 0),
                )
                for row in project_rows
            ],
            oldest_waiting_item=self._row_to_queue_item(oldest_row) if oldest_row else None,
            blocked_reasons=[row["reason"] for row in blocked_rows if row["reason"]],
            stale_leases=int(stale_rows["count"] or 0) if stale_rows else 0,
            recent_failures=[self._row_to_queue_item(row) for row in failure_rows],
        )

    def list_take_choices(self, project_id: str, scene_id: str) -> list[dict]:
        with self._get_connection() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM scene_take_choices WHERE project_id=? AND scene_id=? ORDER BY shot_number",
                (project_id, scene_id),
            ).fetchall()]

    def save_take_choice(self, project_id: str, scene_id: str, shot_number: int, job_id: str | None) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO scene_take_choices VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id, scene_id, shot_number) DO UPDATE SET job_id=excluded.job_id, updated_at=excluded.updated_at",
                (project_id, scene_id, shot_number, job_id, datetime.now().isoformat()),
            )
            conn.commit()

    def get_delivery_manifest(self, project_id: str, scope: str) -> dict | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT payload_json FROM delivery_manifests WHERE project_id=? AND scope=?", (project_id, scope)).fetchone()
            return json.loads(row[0]) if row else None

    def save_delivery_manifest(self, project_id: str, scope: str, payload: dict) -> None:
        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO delivery_manifests VALUES (?, ?, ?)", (project_id, scope, json.dumps(payload)))
            conn.commit()

    # Scene Composition Persistence
    def save_scene_composition(self, project_id: str, scene_id: str, composed_url: str, shot_count: int, duration_seconds: float | None = None) -> dict:
        from datetime import datetime
        now = datetime.now().isoformat()
        comp_id = f"{project_id}_{scene_id}_composed"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO scene_compositions
                   (id, project_id, scene_id, composed_url, shot_count, duration_seconds, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?,
                           COALESCE((SELECT created_at FROM scene_compositions WHERE id = ?), ?),
                           ?)""",
                (comp_id, project_id, scene_id, composed_url, shot_count, duration_seconds,
                 comp_id, now, now)
            )
            conn.commit()
        return {
            "id": comp_id,
            "project_id": project_id,
            "scene_id": scene_id,
            "composed_url": composed_url,
            "shot_count": shot_count,
            "duration_seconds": duration_seconds,
            "created_at": now,
            "updated_at": now,
        }

    def get_scene_composition(self, project_id: str, scene_id: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM scene_compositions
                   WHERE project_id = ? AND scene_id = ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (project_id, scene_id)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def list_scene_compositions_for_project(self, project_id: str) -> list[dict]:
        """List all scene compositions for a project, ordered by scene_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM scene_compositions
                   WHERE project_id = ?
                   ORDER BY scene_id ASC""",
                (project_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    # ── Films (assembled full films) ───────────────────────────────────────

    def save_film(self, project_id: str, film_url: str, scene_count: int,
                  total_duration_seconds: float | None = None,
                  has_audio: bool = False) -> dict:
        from datetime import datetime
        now = datetime.now().isoformat()
        film_id = f"film_{project_id}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO films
                   (id, project_id, film_url, scene_count, total_duration_seconds, has_audio, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?,
                           COALESCE((SELECT created_at FROM films WHERE id = ?), ?),
                           ?)""",
                (film_id, project_id, film_url, scene_count, total_duration_seconds,
                 1 if has_audio else 0,
                 film_id, now, now)
            )
            conn.commit()
        return {
            "id": film_id,
            "project_id": project_id,
            "film_url": film_url,
            "scene_count": scene_count,
            "total_duration_seconds": total_duration_seconds,
            "has_audio": has_audio,
            "created_at": now,
            "updated_at": now,
        }

    def get_film(self, project_id: str) -> dict | None:
        """Get the assembled film for a project, if one exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM films
                   WHERE project_id = ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (project_id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result["has_audio"] = bool(result.get("has_audio", 0))
                return result
            return None

    # Session management
    def access_get_user(self, *, username=None, user_id=None):
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM access_users WHERE username = ? OR user_id = ?",
                (username, user_id),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def access_save_user(self, user, *, create=False):
        with self._get_connection() as conn:
            if create:
                conn.execute("INSERT INTO access_users VALUES (?, ?, ?)",
                             (user["username"], user["user_id"], json.dumps(user)))
            else:
                conn.execute("UPDATE access_users SET payload_json = ? WHERE user_id = ?",
                             (json.dumps(user), user["user_id"]))
            conn.commit()

    def access_claim_project(self, project_id, user_id):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO project_owners VALUES (?, ?, ?)",
                         (project_id, user_id, datetime.now().isoformat()))
            conn.commit()

    def access_owned_projects(self, user_id):
        with self._get_connection() as conn:
            return {row[0] for row in conn.execute(
                "SELECT project_id FROM project_owners WHERE user_id = ?", (user_id,))}

    def access_resource_projects(self, identifier):
        """Resolve opaque identifiers through schema-owned columns, never URL guesses.

        SQL identifiers come exclusively from SQLite metadata. Values are bound.
        Unresolved resources are denied by the access service.
        """
        projects = set()
        with self._get_connection() as conn:
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                columns = [row[1] for row in conn.execute(f"PRAGMA table_info({quoted})")]
                if "project_id" not in columns:
                    continue
                ids = [c for c in columns if c == "id" or c.endswith("_id")]
                clauses = ' OR '.join('"' + c.replace('"', '""') + '" = ?' for c in ids)
                projects.update(row[0] for row in conn.execute(
                    f"SELECT project_id FROM {quoted} WHERE {clauses}", [identifier] * len(ids)) if row[0])
        return projects

    def access_media_projects(self, path):
        """Exact registered URL matching; URL path text is not ownership proof."""
        from urllib.parse import urlsplit
        projects = set()
        def contains(value):
            if isinstance(value, dict):
                return any(contains(v) for v in value.values())
            if isinstance(value, list):
                return any(contains(v) for v in value)
            if isinstance(value, str):
                if value.startswith(("/", "http://", "https://")) and urlsplit(value).path == path:
                    return True
                try:
                    decoded = json.loads(value)
                except (ValueError, TypeError):
                    return False
                return contains(decoded) if isinstance(decoded, (dict, list)) else False
            return False
        with self._get_connection() as conn:
            for table in ("render_jobs", "video_assets", "previs_images", "screening_outputs", "characters", "character_reference_locks", "reference_assets"):
                columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
                if "project_id" not in columns:
                    continue
                for row in conn.execute(f'SELECT * FROM "{table}"'):
                    if contains(dict(row)):
                        projects.add(row["project_id"])
        return projects

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
    # Shot Seed Persistence
    # ========================================================================

    def get_shot_seed(self, project_id: str, shot_id: str) -> Optional[dict]:
        """Get the seed record for a shot, if one exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT project_id, shot_id, seed, seed_locked, created_at, updated_at
                   FROM shots WHERE project_id = ? AND shot_id = ?""",
                (project_id, shot_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_shot_seed(self, project_id: str, shot_id: str, seed: int, seed_locked: bool = False) -> dict:
        """Upsert a seed record for a shot."""
        now = datetime.now().isoformat()
        lock_val = 1 if seed_locked else 0

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO shots
                       (project_id, shot_id, seed, seed_locked, created_at, updated_at)
                       VALUES (?, ?, ?, ?,
                               COALESCE((SELECT created_at FROM shots WHERE project_id = ? AND shot_id = ?), ?),
                               ?)""",
                    (project_id, shot_id, seed, lock_val, project_id, shot_id, now, now),
                )
                conn.commit()

        self._execute_write_with_retry("save_shot_seed", _write)
        return {"project_id": project_id, "shot_id": shot_id, "seed": seed, "seed_locked": lock_val}

    def update_shot_seed_lock(self, project_id: str, shot_id: str, seed: Optional[int] = None, seed_locked: Optional[bool] = None) -> bool:
        """Update seed and/or lock status for a shot record."""
        now = datetime.now().isoformat()
        updates = ["updated_at = ?"]
        params = [now]
        if seed is not None:
            updates.append("seed = ?")
            params.append(seed)
        if seed_locked is not None:
            updates.append("seed_locked = ?")
            params.append(1 if seed_locked else 0)
        params.extend([project_id, shot_id])

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE shots SET {', '.join(updates)} WHERE project_id = ? AND shot_id = ?",
                    params,
                )
                conn.commit()

        self._execute_write_with_retry("update_shot_seed_lock", _write)
        return True

    # ========================================================================
    # Director Intent Persistence
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
                    project_id, scene_id, scene_number, location_name, time_of_day, weather,
                    camera_choices, lighting_notes, color_palette, props_in_scene,
                    character_positions, generated_shots, approved_shots, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scene_memory.get("project_id"),
                scene_memory.get("scene_id") or scene_memory.get("scene_id", ""),
                scene_memory.get("scene_number", 0),
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    # =========================================================================
    # ADVANCED CREW INTELLIGENCE PERSISTENCE
    # =========================================================================

    def _crew_json_list(self, value: Any) -> list:
        parsed = self._json_loads(value, [])
        return parsed if isinstance(parsed, list) else []

    def _crew_json_dict(self, value: Any) -> dict:
        parsed = self._json_loads(value, {})
        return parsed if isinstance(parsed, dict) else {}

    def _row_to_crew_reasoning(self, row: sqlite3.Row) -> Dict:
        result = dict(row)
        for key in [
            "context_used",
            "evidence_refs",
            "memory_refs",
            "spine_refs",
            "risks",
            "recommendations",
            "downstream_departments",
        ]:
            result[key] = self._crew_json_list(result.get(key))
        result["metadata"] = self._crew_json_dict(result.get("metadata"))
        result["requires_creator_decision"] = bool(result.get("requires_creator_decision"))
        result["advisory_only"] = bool(result.get("advisory_only"))
        return result

    def save_crew_reasoning_record(self, record: Dict) -> Dict:
        data = dict(record)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO crew_reasoning_records (
                    reasoning_id, project_id, task_id, workflow_execution_id,
                    agent_role, department_name, reasoning_type, scene_id, shot_id,
                    asset_id, render_job_id, package_id, observation, context_used,
                    inference, recommendation_summary, creator_note, evidence_refs,
                    memory_refs, spine_refs, risks, recommendations,
                    downstream_departments, requires_creator_decision,
                    escalation_reason, status, confidence_label, advisory_only,
                    trace_id, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["reasoning_id"],
                    data["project_id"],
                    data.get("task_id"),
                    data.get("workflow_execution_id"),
                    data["agent_role"],
                    data.get("department_name", ""),
                    data["reasoning_type"],
                    data.get("scene_id"),
                    data.get("shot_id"),
                    data.get("asset_id"),
                    data.get("render_job_id"),
                    data.get("package_id"),
                    data.get("observation", ""),
                    json.dumps(data.get("context_used", []), default=str),
                    data.get("inference", ""),
                    data.get("recommendation_summary", ""),
                    data.get("creator_note", ""),
                    json.dumps(data.get("evidence_refs", []), default=str),
                    json.dumps(data.get("memory_refs", []), default=str),
                    json.dumps(data.get("spine_refs", []), default=str),
                    json.dumps(data.get("risks", []), default=str),
                    json.dumps(data.get("recommendations", []), default=str),
                    json.dumps(data.get("downstream_departments", []), default=str),
                    1 if data.get("requires_creator_decision") else 0,
                    data.get("escalation_reason"),
                    data.get("status", "active"),
                    data.get("confidence_label", "emerging"),
                    1 if data.get("advisory_only", True) else 0,
                    data.get("trace_id", ""),
                    data["created_at"],
                    json.dumps(data.get("metadata", {}), default=str),
                ),
            )
            conn.commit()
        return self.get_crew_reasoning_record(data["reasoning_id"]) or data

    def get_crew_reasoning_record(self, reasoning_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crew_reasoning_records WHERE reasoning_id = ?", (reasoning_id,))
            row = cursor.fetchone()
            return self._row_to_crew_reasoning(row) if row else None

    def list_crew_reasoning_records(
        self,
        project_id: str,
        filters: Optional[Dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        filters = filters or {}
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        for key in ["agent_role", "reasoning_type", "scene_id", "task_id", "status"]:
            if filters.get(key):
                clauses.append(f"{key} = ?")
                params.append(filters[key])
        if filters.get("requires_creator_decision") is not None:
            clauses.append("requires_creator_decision = ?")
            params.append(1 if filters["requires_creator_decision"] else 0)
        params.extend([max(1, min(int(limit), 200)), max(0, int(offset))])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT * FROM crew_reasoning_records
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            return [self._row_to_crew_reasoning(row) for row in cursor.fetchall()]

    def _row_to_crew_handoff(self, row: sqlite3.Row) -> Dict:
        result = dict(row)
        for key in ["requirements", "open_questions", "evidence_refs", "memory_refs", "spine_refs", "risks"]:
            result[key] = self._crew_json_list(result.get(key))
        result["metadata"] = self._crew_json_dict(result.get("metadata"))
        return result

    def save_crew_handoff_packet(self, handoff: Dict) -> Dict:
        data = dict(handoff)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO crew_handoff_packets (
                    handoff_id, project_id, source_role, target_role,
                    source_task_id, target_task_id, scene_id, shot_id, asset_id,
                    context_summary, requirements, open_questions, evidence_refs,
                    memory_refs, spine_refs, risks, status, acknowledged_by,
                    acknowledged_at, completed_at, failed_reason, trace_id,
                    created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["handoff_id"],
                    data["project_id"],
                    data["source_role"],
                    data["target_role"],
                    data.get("source_task_id"),
                    data.get("target_task_id"),
                    data.get("scene_id"),
                    data.get("shot_id"),
                    data.get("asset_id"),
                    data.get("context_summary", ""),
                    json.dumps(data.get("requirements", []), default=str),
                    json.dumps(data.get("open_questions", []), default=str),
                    json.dumps(data.get("evidence_refs", []), default=str),
                    json.dumps(data.get("memory_refs", []), default=str),
                    json.dumps(data.get("spine_refs", []), default=str),
                    json.dumps(data.get("risks", []), default=str),
                    data.get("status", "created"),
                    data.get("acknowledged_by"),
                    data.get("acknowledged_at"),
                    data.get("completed_at"),
                    data.get("failed_reason"),
                    data.get("trace_id", ""),
                    data["created_at"],
                    data["updated_at"],
                    json.dumps(data.get("metadata", {}), default=str),
                ),
            )
            conn.commit()
        return self.get_crew_handoff_packet(data["handoff_id"]) or data

    def get_crew_handoff_packet(self, handoff_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crew_handoff_packets WHERE handoff_id = ?", (handoff_id,))
            row = cursor.fetchone()
            return self._row_to_crew_handoff(row) if row else None

    def list_crew_handoff_packets(
        self,
        project_id: str,
        filters: Optional[Dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        filters = filters or {}
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        for key in ["source_role", "target_role", "scene_id", "status"]:
            if filters.get(key):
                clauses.append(f"{key} = ?")
                params.append(filters[key])
        params.extend([max(1, min(int(limit), 200)), max(0, int(offset))])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT * FROM crew_handoff_packets
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            return [self._row_to_crew_handoff(row) for row in cursor.fetchall()]

    def update_crew_handoff_status(self, handoff_id: str, updates: Dict) -> Optional[Dict]:
        current = self.get_crew_handoff_packet(handoff_id)
        if not current:
            return None
        merged = {**current, **updates, "updated_at": updates.get("updated_at", datetime.now().isoformat())}
        return self.save_crew_handoff_packet(merged)

    def _row_to_crew_deliberation(self, row: sqlite3.Row) -> Dict:
        result = dict(row)
        for key in [
            "participating_roles",
            "triggering_reasoning_ids",
            "triggering_task_ids",
            "points_of_agreement",
            "points_of_tension",
            "evidence_refs",
            "risks",
        ]:
            result[key] = self._crew_json_list(result.get(key))
        result["requires_creator_decision"] = bool(result.get("requires_creator_decision"))
        result["metadata"] = self._crew_json_dict(result.get("metadata"))
        return result

    def save_crew_deliberation_record(self, record: Dict) -> Dict:
        data = dict(record)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO crew_deliberation_records (
                    deliberation_id, project_id, conflict_id, scene_id, shot_id,
                    asset_id, participating_roles, triggering_reasoning_ids,
                    triggering_task_ids, issue_summary, points_of_agreement,
                    points_of_tension, evidence_refs, risks, recommended_resolution,
                    requires_creator_decision, creator_question, status,
                    resolution_summary, resolved_by, resolved_at, trace_id,
                    created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["deliberation_id"],
                    data["project_id"],
                    data.get("conflict_id"),
                    data.get("scene_id"),
                    data.get("shot_id"),
                    data.get("asset_id"),
                    json.dumps(data.get("participating_roles", []), default=str),
                    json.dumps(data.get("triggering_reasoning_ids", []), default=str),
                    json.dumps(data.get("triggering_task_ids", []), default=str),
                    data.get("issue_summary", ""),
                    json.dumps(data.get("points_of_agreement", []), default=str),
                    json.dumps(data.get("points_of_tension", []), default=str),
                    json.dumps(data.get("evidence_refs", []), default=str),
                    json.dumps(data.get("risks", []), default=str),
                    data.get("recommended_resolution", ""),
                    1 if data.get("requires_creator_decision") else 0,
                    data.get("creator_question"),
                    data.get("status", "open"),
                    data.get("resolution_summary"),
                    data.get("resolved_by"),
                    data.get("resolved_at"),
                    data.get("trace_id", ""),
                    data["created_at"],
                    data["updated_at"],
                    json.dumps(data.get("metadata", {}), default=str),
                ),
            )
            conn.commit()
        return self.get_crew_deliberation_record(data["deliberation_id"]) or data

    def get_crew_deliberation_record(self, deliberation_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM crew_deliberation_records WHERE deliberation_id = ?", (deliberation_id,))
            row = cursor.fetchone()
            return self._row_to_crew_deliberation(row) if row else None

    def list_crew_deliberation_records(
        self,
        project_id: str,
        filters: Optional[Dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        filters = filters or {}
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        for key in ["scene_id", "status"]:
            if filters.get(key):
                clauses.append(f"{key} = ?")
                params.append(filters[key])
        if filters.get("requires_creator_decision") is not None:
            clauses.append("requires_creator_decision = ?")
            params.append(1 if filters["requires_creator_decision"] else 0)
        params.extend([max(1, min(int(limit), 200)), max(0, int(offset))])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT * FROM crew_deliberation_records
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            return [self._row_to_crew_deliberation(row) for row in cursor.fetchall()]

    def save_crew_department_status_snapshot(self, snapshot: Dict) -> Dict:
        data = dict(snapshot)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO crew_department_status_snapshots (
                    snapshot_id, project_id, agent_role, department_name, state,
                    current_task_id, current_activity, last_reasoning_id,
                    active_handoff_count, unresolved_risk_count,
                    needs_creator_attention, created_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["snapshot_id"],
                    data["project_id"],
                    data["agent_role"],
                    data.get("department_name", ""),
                    data.get("state", "idle"),
                    data.get("current_task_id"),
                    data.get("current_activity", ""),
                    data.get("last_reasoning_id"),
                    data.get("active_handoff_count", 0),
                    data.get("unresolved_risk_count", 0),
                    1 if data.get("needs_creator_attention") else 0,
                    data["created_at"],
                    json.dumps(data.get("metadata", {}), default=str),
                ),
            )
            conn.commit()
        return data

    def list_crew_department_status_snapshots(
        self,
        project_id: str,
        agent_role: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if agent_role:
            clauses.append("agent_role = ?")
            params.append(agent_role)
        params.append(max(1, min(int(limit), 200)))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT * FROM crew_department_status_snapshots
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            )
            rows = []
            for row in cursor.fetchall():
                item = dict(row)
                item["needs_creator_attention"] = bool(item.get("needs_creator_attention"))
                item["metadata"] = self._crew_json_dict(item.get("metadata"))
                rows.append(item)
            return rows

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

    def save_production_acceptance_report(self, report) -> Any:
        payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
        blocker_count = sum(1 for check in payload.get("checks", []) if check.get("severity") == "blocker")
        warning_count = sum(1 for check in payload.get("checks", []) if check.get("severity") == "warning")
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO production_acceptance_reports (
                    acceptance_id, project_id, package_id, disposition, stale,
                    blocker_count, warning_count, final_output_url,
                    acceptance_input_hash, report_json, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("acceptance_id"),
                    payload.get("project_id"),
                    payload.get("package_id") or "",
                    payload.get("disposition"),
                    1 if payload.get("stale") else 0,
                    blocker_count,
                    warning_count,
                    context.get("final_output_url") or "",
                    context.get("acceptance_input_hash") or "",
                    json.dumps(payload),
                    payload.get("generated_at") or datetime.now().isoformat(),
                ),
            )
            conn.commit()
        return report

    def _row_to_production_acceptance_report(self, row: sqlite3.Row):
        from app.models.production_acceptance import ProductionAcceptanceReport

        payload = json.loads(row["report_json"] or "{}")
        return ProductionAcceptanceReport(**payload)

    def get_production_acceptance_report(self, acceptance_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM production_acceptance_reports WHERE acceptance_id = ?",
                (acceptance_id,),
            )
            row = cursor.fetchone()
            return self._row_to_production_acceptance_report(row) if row else None

    def list_production_acceptance_reports_for_project(
        self,
        project_id: str,
        package_id: str | None = None,
        limit: int = 20,
    ) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if package_id:
                cursor.execute(
                    """
                    SELECT * FROM production_acceptance_reports
                    WHERE project_id = ? AND package_id = ?
                    ORDER BY generated_at DESC
                    LIMIT ?
                    """,
                    (project_id, package_id, int(limit)),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM production_acceptance_reports
                    WHERE project_id = ?
                    ORDER BY generated_at DESC
                    LIMIT ?
                    """,
                    (project_id, int(limit)),
                )
            return [self._row_to_production_acceptance_report(row) for row in cursor.fetchall()]

    def get_latest_production_acceptance_report(self, project_id: str, package_id: str | None = None):
        reports = self.list_production_acceptance_reports_for_project(project_id, package_id=package_id, limit=1)
        return reports[0] if reports else None

    # =========================================================================
    # FILM CUT VERSIONS + TIMELINE
    # =========================================================================

    def commit_film_cut_version(
        self,
        cut: dict[str, Any],
        *,
        supersede_cut_id: str | None = None,
        application: Any | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            if supersede_cut_id:
                cursor.execute(
                    """UPDATE film_cut_versions SET status = 'superseded', updated_at = ?
                       WHERE cut_id = ? AND project_id = ? AND status = 'draft'""",
                    (now, supersede_cut_id, cut["project_id"]),
                )
            cursor.execute(
                """
                INSERT INTO film_cut_versions (
                    cut_id, project_id, version_number, status, source_cut_id,
                    source_analysis_id, source_application_id, scene_order_json,
                    timeline_json, metadata_json, created_at, updated_at,
                    approved_at, approved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cut["cut_id"],
                    cut["project_id"],
                    int(cut["version_number"]),
                    cut.get("status") or "draft",
                    cut.get("source_cut_id"),
                    cut.get("source_analysis_id"),
                    cut.get("source_application_id"),
                    json.dumps(cut.get("scene_order") or []),
                    json.dumps(cut.get("timeline") or []),
                    json.dumps(cut.get("metadata") or {}, sort_keys=True),
                    cut.get("created_at") or now,
                    cut.get("updated_at") or now,
                    cut.get("approved_at"),
                    cut.get("approved_by"),
                ),
            )
            cursor.execute(
                """
                INSERT INTO film_cut_state (project_id, current_cut_id, approved_cut_id, updated_at)
                VALUES (?, ?, NULL, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    current_cut_id = excluded.current_cut_id,
                    updated_at = excluded.updated_at
                """,
                (cut["project_id"], cut["cut_id"], now),
            )
            if application is not None:
                payload = application.model_dump(mode="json") if hasattr(application, "model_dump") else dict(application)
                cursor.execute(
                    """
                    INSERT INTO editorial_decision_applications (
                        application_id, project_id, analysis_id, decision_ids_json,
                        source_cut_id, result_cut_id, application_status,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["application_id"],
                        payload["project_id"],
                        payload["analysis_id"],
                        json.dumps(payload.get("decision_ids") or []),
                        payload.get("source_cut_id") or "default",
                        payload.get("result_cut_id") or "",
                        payload.get("application_status") or "applied",
                        json.dumps(payload),
                        payload.get("created_at") or now,
                    ),
                )
            conn.commit()
        return self.get_film_cut_version(cut["cut_id"]) or {}

    def get_film_cut_version(self, cut_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM film_cut_versions WHERE cut_id = ?", (cut_id,)).fetchone()
        return self._film_cut_row_to_dict(row) if row else None

    def get_current_film_cut(self, project_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT v.* FROM film_cut_state s
                   JOIN film_cut_versions v ON v.cut_id = s.current_cut_id
                   WHERE s.project_id = ?""",
                (project_id,),
            ).fetchone()
        return self._film_cut_row_to_dict(row) if row else None

    def list_film_cut_versions(self, project_id: str) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM film_cut_versions
                   WHERE project_id = ? ORDER BY version_number ASC""",
                (project_id,),
            ).fetchall()
        return [self._film_cut_row_to_dict(row) for row in rows]

    def approve_film_cut(self, project_id: str, cut_id: str, approved_by: str) -> dict[str, Any] | None:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            state = cursor.execute(
                "SELECT current_cut_id FROM film_cut_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if state is None or state["current_cut_id"] != cut_id:
                conn.rollback()
                raise ValueError("Only the current Film Cut can be approved")
            row = cursor.execute(
                "SELECT * FROM film_cut_versions WHERE cut_id = ? AND project_id = ?",
                (cut_id, project_id),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            cursor.execute(
                """UPDATE film_cut_versions
                   SET status = 'approved', approved_at = ?, approved_by = ?, updated_at = ?
                   WHERE cut_id = ? AND project_id = ?""",
                (now, approved_by, now, cut_id, project_id),
            )
            cursor.execute(
                """UPDATE film_cut_state SET approved_cut_id = ?, updated_at = ?
                   WHERE project_id = ?""",
                (cut_id, now, project_id),
            )
            updated = cursor.execute(
                "SELECT * FROM film_cut_versions WHERE cut_id = ?",
                (cut_id,),
            ).fetchone()
            conn.commit()
        return self._film_cut_row_to_dict(updated)

    def get_film_cut_state(self, project_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM film_cut_state WHERE project_id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def _film_cut_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["scene_order"] = json.loads(data.pop("scene_order_json") or "[]")
        data["timeline"] = json.loads(data.pop("timeline_json") or "[]")
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def save_editorial_analysis_record(self, record) -> Any:
        payload = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO editorial_analysis_records (
                    analysis_id, project_id, source_cut_id, source_package_id,
                    context_hash, analysis_status, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("analysis_id"),
                    payload.get("project_id"),
                    payload.get("source_cut_id") or "default",
                    payload.get("source_package_id") or "",
                    payload.get("context_hash") or "",
                    payload.get("analysis_status") or "complete",
                    json.dumps(payload),
                    payload.get("created_at") or datetime.now().isoformat(),
                ),
            )
            conn.commit()
        return record

    def _row_to_editorial_analysis_record(self, row: sqlite3.Row):
        from app.models.editorial_intelligence import EditorialAnalysisRecord

        payload = json.loads(row["payload_json"] or "{}")
        return EditorialAnalysisRecord(**payload)

    def get_editorial_analysis_record(self, analysis_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM editorial_analysis_records WHERE analysis_id = ?", (analysis_id,))
            row = cursor.fetchone()
            return self._row_to_editorial_analysis_record(row) if row else None

    def list_editorial_analysis_records_for_project(self, project_id: str, limit: int = 20) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM editorial_analysis_records
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, max(1, int(limit))),
            )
            return [self._row_to_editorial_analysis_record(row) for row in cursor.fetchall()]

    def get_latest_editorial_analysis_record(self, project_id: str):
        rows = self.list_editorial_analysis_records_for_project(project_id, limit=1)
        return rows[0] if rows else None

    def save_editorial_decision_application(self, application) -> Any:
        payload = application.model_dump(mode="json") if hasattr(application, "model_dump") else dict(application)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO editorial_decision_applications (
                    application_id, project_id, analysis_id, decision_ids_json,
                    source_cut_id, result_cut_id, application_status,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("application_id"),
                    payload.get("project_id"),
                    payload.get("analysis_id"),
                    json.dumps(payload.get("decision_ids") or []),
                    payload.get("source_cut_id") or "default",
                    payload.get("result_cut_id") or "",
                    payload.get("application_status") or "applied",
                    json.dumps(payload),
                    payload.get("created_at") or datetime.now().isoformat(),
                ),
            )
            conn.commit()
        return application

    def _row_to_editorial_decision_application(self, row: sqlite3.Row):
        from app.models.editorial_intelligence import EditorialApplyResult

        payload = json.loads(row["payload_json"] or "{}")
        return EditorialApplyResult(**payload)

    def get_editorial_decision_application(self, application_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM editorial_decision_applications WHERE application_id = ?",
                (application_id,),
            )
            row = cursor.fetchone()
            return self._row_to_editorial_decision_application(row) if row else None

    def list_editorial_decision_applications_for_project(self, project_id: str, limit: int = 20) -> List[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM editorial_decision_applications
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, max(1, int(limit))),
            )
            return [self._row_to_editorial_decision_application(row) for row in cursor.fetchall()]

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

    # =========================================================================
    # CONTINUITY GRAPH PERSISTENCE
    # =========================================================================

    def save_continuity_graph(self, film_id: str, graph: dict) -> bool:
        """
        Persist the current continuity graph for a film.

        Overwrites any existing graph for the same film_id.
        The graph dict is serialized as JSON.

        Args:
            film_id: The film/project identifier (primary key).
            graph:   The graph dict to persist.

        Returns:
            True on success.
        """
        now = datetime.now().isoformat()
        graph_json = json.dumps(graph, default=str)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO continuity_graphs (film_id, graph_json, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (film_id, graph_json, now),
                )
                conn.commit()

        self._execute_write_with_retry("save_continuity_graph", _write)
        return True

    def load_continuity_graph(self, film_id: str) -> Optional[dict]:
        """
        Load the current continuity graph for a film.

        Args:
            film_id: The film/project identifier.

        Returns:
            The deserialized graph dict, or None if no graph exists.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT graph_json FROM continuity_graphs WHERE film_id = ?",
                (film_id,),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["graph_json"])
                except (json.JSONDecodeError, TypeError):
                    return None
            return None

    def save_continuity_graph_version(
        self,
        film_id: str,
        version_id: str,
        graph: dict,
    ) -> bool:
        """
        Persist a versioned snapshot of a continuity graph.

        Each version is immutable once written (INSERT OR IGNORE).

        Args:
            film_id:    The film/project identifier.
            version_id: A unique identifier for this version (e.g. UUID).
            graph:      The graph dict to persist.

        Returns:
            True on success.
        """
        now = datetime.now().isoformat()
        graph_json = json.dumps(graph, default=str)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO continuity_graph_versions
                        (version_id, film_id, graph_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (version_id, film_id, graph_json, now),
                )
                conn.commit()

        self._execute_write_with_retry("save_continuity_graph_version", _write)
        return True

    def load_continuity_graph_version(
        self,
        film_id: str,
        version_id: str,
    ) -> Optional[dict]:
        """
        Load a specific versioned snapshot of a continuity graph.

        Args:
            film_id:    The film/project identifier (used for validation).
            version_id: The version identifier.

        Returns:
            The deserialized graph dict, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT graph_json FROM continuity_graph_versions
                WHERE version_id = ? AND film_id = ?
                """,
                (version_id, film_id),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["graph_json"])
                except (json.JSONDecodeError, TypeError):
                    return None
            return None

    def list_continuity_graph_versions(self, film_id: str) -> List[dict]:
        """
        List all version metadata for a film's continuity graph, ordered by
        created_at ascending (oldest first).

        Args:
            film_id: The film/project identifier.

        Returns:
            List of dicts with keys: version_id, film_id, created_at.
            (graph_json is excluded to keep the list lightweight.)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT version_id, film_id, created_at
                FROM continuity_graph_versions
                WHERE film_id = ?
                ORDER BY created_at ASC
                """,
                (film_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # Film DNA Persistence
    # =========================================================================

    def save_film_dna(self, film_id: str, dna: dict) -> bool:
        """
        Persist the Film DNA profile for a film.

        Overwrites any existing DNA for the same film_id.
        The DNA dict is serialized as JSON.

        Args:
            film_id: The film/project identifier (primary key).
            dna:     The DNA dict to persist.

        Returns:
            True on success.
        """
        now = datetime.now().isoformat()
        dna_json = json.dumps(dna, default=str)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO film_dna (film_id, dna_json, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (film_id, dna_json, now),
                )
                conn.commit()

        self._execute_write_with_retry("save_film_dna", _write)
        return True

    def load_film_dna(self, film_id: str) -> Optional[dict]:
        """
        Load the Film DNA profile for a film.

        Args:
            film_id: The film/project identifier.

        Returns:
            The deserialized DNA dict, or None if no DNA exists.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT dna_json FROM film_dna WHERE film_id = ?",
                (film_id,),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["dna_json"])
                except (json.JSONDecodeError, TypeError):
                    return None
            return None

    # =========================================================================
    # Director Intent Persistence
    # =========================================================================

    def save_director_intent(self, project_id: str, intent: dict) -> bool:
        """
        Save or merge director intent for a project.

        Merges with existing intent rather than replacing entirely.
        Only updates fields that are provided in the intent dict.

        Args:
            project_id: The project identifier.
            intent:     The intent dict to save/merge.

        Returns:
            True on success.
        """
        from datetime import datetime

        # Load existing project
        project = self.get_project(project_id)
        if not project:
            return False

        # Get existing intent or create new one
        existing_intent = project.director_intent or {}

        # Merge with new intent
        merged_intent = {**existing_intent, **intent}

        # Update timestamps
        if not merged_intent.get("captured_at"):
            merged_intent["captured_at"] = datetime.now().isoformat()
        merged_intent["last_updated"] = datetime.now().isoformat()

        # Update project
        project.director_intent = merged_intent
        self.save_project(project)
        return True

    def load_director_intent(self, project_id: str) -> Optional[dict]:
        """
        Load director intent for a project.

        Args:
            project_id: The project identifier.

        Returns:
            The intent dict, or None if no intent exists.
        """
        project = self.get_project(project_id)
        if not project:
            return None
        return project.director_intent

    # =========================================================================
    # Session Debrief Persistence
    # =========================================================================

    def save_session_debrief(self, project_id: str, debrief: dict) -> bool:
        """
        Save a session debrief for a project.

        Args:
            project_id: The project identifier.
            debrief:    The debrief dict to save.

        Returns:
            True on success.
        """
        import uuid

        debrief_id = debrief.get("id") or f"debrief_{uuid.uuid4().hex[:12]}"
        session_start = debrief.get("session_start", "")
        session_end = debrief.get("session_end", "")
        generated_at = debrief.get("generated_at", datetime.now().isoformat())

        debrief_json = json.dumps(debrief, default=str)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO session_debriefs
                    (id, project_id, session_start, session_end, debrief_json, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (debrief_id, project_id, session_start, session_end, debrief_json, generated_at),
                )
                conn.commit()

        self._execute_write_with_retry("save_session_debrief", _write)
        return True

    def list_session_debriefs(self, project_id: str, limit: int = 10) -> List[dict]:
        """
        List session debriefs for a project, most recent first.

        Args:
            project_id: The project identifier.
            limit:      Maximum number of debriefs to return.

        Returns:
            List of debrief dicts (summary only).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_start, session_end, generated_at, debrief_json
                FROM session_debriefs
                WHERE project_id = ?
                ORDER BY generated_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            )
            rows = cursor.fetchall()

            debriefs = []
            for row in rows:
                try:
                    full_debrief = json.loads(row["debrief_json"])
                    # Return summary only
                    debriefs.append({
                        "id": row["id"],
                        "session_start": row["session_start"],
                        "session_end": row["session_end"],
                        "generated_at": row["generated_at"],
                        "advisory": full_debrief.get("advisory", ""),
                    })
                except (json.JSONDecodeError, TypeError):
                    continue

            return debriefs

    def get_session_debrief(self, project_id: str, debrief_id: str) -> Optional[dict]:
        """
        Get a specific session debrief.

        Args:
            project_id: The project identifier.
            debrief_id: The debrief identifier.

        Returns:
            The full debrief dict, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT debrief_json
                FROM session_debriefs
                WHERE project_id = ? AND id = ?
                """,
                (project_id, debrief_id),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["debrief_json"])
                except (json.JSONDecodeError, TypeError):
                    return None
            return None


    # =========================================================================
    # Export Package Persistence
    # =========================================================================

    def save_export_package(self, project_id: str, package: dict) -> bool:
        """
        Save an export package for a project.

        Args:
            project_id: The project identifier.
            package:    The export package dict to save.

        Returns:
            True on success.
        """
        package_id = package.get("package_id", "")
        if not package_id:
            return False

        created_at = package.get("created_at", datetime.now().isoformat())
        package_json = json.dumps(package, default=str)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO export_packages
                    (package_id, project_id, package_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (package_id, project_id, package_json, created_at),
                )
                conn.commit()

        self._execute_write_with_retry("save_export_package", _write)
        return True

    def load_export_package(self, package_id: str) -> Optional[dict]:
        """
        Load a specific export package.

        Args:
            package_id: The package identifier.

        Returns:
            The full package dict, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT package_json
                FROM export_packages
                WHERE package_id = ?
                """,
                (package_id,),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["package_json"])
                except (json.JSONDecodeError, TypeError):
                    return None
            return None

    def list_export_packages(self, project_id: str, limit: int = 10) -> List[dict]:
        """
        List export packages for a project, most recent first.

        Args:
            project_id: The project identifier.
            limit:      Maximum number of packages to return.

        Returns:
            List of package summaries.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT package_id, created_at, package_json
                FROM export_packages
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            )
            rows = cursor.fetchall()

            packages = []
            for row in rows:
                try:
                    full_package = json.loads(row["package_json"])
                    manifest = full_package.get("manifest", {})

                    # Return summary only
                    packages.append({
                        "package_id": row["package_id"],
                        "created_at": row["created_at"],
                        "status": full_package.get("status", "unknown"),
                        "scene_count": manifest.get("scene_count", 0),
                        "total_shots": manifest.get("total_shots", 0),
                    })
                except (json.JSONDecodeError, TypeError):
                    continue

            return packages

    # =========================================================================
    # Pitch Deck Persistence
    # =========================================================================

    def save_pitch_deck(self, project_id: str, deck: dict) -> bool:
        """
        Save a pitch deck for a project.

        Args:
            project_id: The project identifier.
            deck:       The pitch deck dict to save.

        Returns:
            True on success.
        """
        deck_id = deck.get("deck_id", "")
        if not deck_id:
            return False

        target_audience = deck.get("target_audience", "general")
        created_at = deck.get("generated_at", datetime.now().isoformat())
        deck_json = json.dumps(deck, default=str)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO pitch_decks
                    (deck_id, project_id, deck_json, target_audience, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (deck_id, project_id, deck_json, target_audience, created_at),
                )
                conn.commit()

        self._execute_write_with_retry("save_pitch_deck", _write)
        return True

    def load_pitch_deck(self, deck_id: str) -> Optional[dict]:
        """
        Load a specific pitch deck.

        Args:
            deck_id: The deck identifier.

        Returns:
            The full deck dict, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT deck_json
                FROM pitch_decks
                WHERE deck_id = ?
                """,
                (deck_id,),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["deck_json"])
                except (json.JSONDecodeError, TypeError):
                    return None
            return None

    def list_pitch_decks(self, project_id: str, limit: int = 10) -> List[dict]:
        """
        List pitch decks for a project, most recent first.

        Args:
            project_id: The project identifier.
            limit:      Maximum number of decks to return.

        Returns:
            List of deck summaries.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT deck_id, target_audience, created_at
                FROM pitch_decks
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            )
            rows = cursor.fetchall()

            decks = []
            for row in rows:
                decks.append({
                    "deck_id": row["deck_id"],
                    "target_audience": row["target_audience"],
                    "created_at": row["created_at"],
                })

            return decks

    # =========================================================================
    # STORYBOARD BLUEPRINTS
    # =========================================================================

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value if value is not None else {}, default=str)

    @staticmethod
    def _json_loads(value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        try:
            return json.loads(value)
        except Exception:
            return fallback

    def save_storyboard_blueprint(self, blueprint: Any) -> Any:
        data = blueprint.model_dump(mode="json") if hasattr(blueprint, "model_dump") else dict(blueprint)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO storyboard_blueprints (
                        blueprint_id, project_id, scene_id, current_version_id,
                        status, approved_version_id, locked, created_at, updated_at,
                        created_by, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["blueprint_id"],
                        data["project_id"],
                        data["scene_id"],
                        data.get("current_version_id"),
                        data.get("status", "draft"),
                        data.get("approved_version_id"),
                        1 if data.get("locked") else 0,
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("updated_at") or datetime.now().isoformat(),
                        data.get("created_by") or "",
                        self._json_dumps(data.get("metadata", {})),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_storyboard_blueprint", _write)
        return blueprint

    def _row_to_storyboard_blueprint(self, row: sqlite3.Row) -> Any:
        from app.models.storyboard_blueprint import StoryboardBlueprint

        return StoryboardBlueprint(
            blueprint_id=row["blueprint_id"],
            project_id=row["project_id"],
            scene_id=row["scene_id"],
            current_version_id=row["current_version_id"],
            status=row["status"],
            approved_version_id=row["approved_version_id"],
            locked=bool(row["locked"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by=row["created_by"] or "",
            metadata=self._json_loads(row["metadata"], {}),
        )

    def get_storyboard_blueprint(self, project_id: str, scene_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM storyboard_blueprints WHERE project_id = ? AND scene_id = ? LIMIT 1",
                (project_id, scene_id),
            )
            row = cursor.fetchone()
            return self._row_to_storyboard_blueprint(row) if row else None

    def get_storyboard_blueprint_by_id(self, blueprint_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM storyboard_blueprints WHERE blueprint_id = ?", (blueprint_id,))
            row = cursor.fetchone()
            return self._row_to_storyboard_blueprint(row) if row else None

    def list_storyboard_blueprints(self, project_id: str) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM storyboard_blueprints WHERE project_id = ? ORDER BY scene_id ASC",
                (project_id,),
            )
            return [self._row_to_storyboard_blueprint(row) for row in cursor.fetchall()]

    def save_storyboard_blueprint_version(self, version: Any) -> Any:
        data = version.model_dump(mode="json") if hasattr(version, "model_dump") else dict(version)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO storyboard_blueprint_versions (
                        version_id, blueprint_id, project_id, scene_id, version_number,
                        status, change_reason, source_version_id, provenance_json,
                        inspection_json, created_at, approved_at, approved_by, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["version_id"],
                        data["blueprint_id"],
                        data["project_id"],
                        data["scene_id"],
                        int(data.get("version_number") or 1),
                        data.get("status", "draft"),
                        data.get("change_reason") or "",
                        data.get("source_version_id"),
                        self._json_dumps(data.get("provenance", {})),
                        self._json_dumps(data.get("inspection", {})),
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("approved_at"),
                        data.get("approved_by") or "",
                        self._json_dumps(data.get("metadata", {})),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_storyboard_blueprint_version", _write)
        return version

    def _row_to_storyboard_blueprint_version(self, row: sqlite3.Row) -> Any:
        from app.models.storyboard_blueprint import (
            StoryboardBlueprintInspection,
            StoryboardBlueprintProvenance,
            StoryboardBlueprintVersion,
        )

        return StoryboardBlueprintVersion(
            version_id=row["version_id"],
            blueprint_id=row["blueprint_id"],
            project_id=row["project_id"],
            scene_id=row["scene_id"],
            version_number=int(row["version_number"] or 1),
            status=row["status"],
            change_reason=row["change_reason"] or "",
            source_version_id=row["source_version_id"],
            provenance=StoryboardBlueprintProvenance(**self._json_loads(row["provenance_json"], {})),
            inspection=StoryboardBlueprintInspection(**self._json_loads(row["inspection_json"], {})),
            created_at=row["created_at"],
            approved_at=row["approved_at"],
            approved_by=row["approved_by"] or "",
            metadata=self._json_loads(row["metadata"], {}),
        )

    def get_storyboard_blueprint_version(self, version_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM storyboard_blueprint_versions WHERE version_id = ?", (version_id,))
            row = cursor.fetchone()
            return self._row_to_storyboard_blueprint_version(row) if row else None

    def list_storyboard_blueprint_versions(self, blueprint_id: str) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM storyboard_blueprint_versions
                WHERE blueprint_id = ?
                ORDER BY version_number ASC
                """,
                (blueprint_id,),
            )
            return [self._row_to_storyboard_blueprint_version(row) for row in cursor.fetchall()]

    def save_storyboard_shot(self, shot: Any) -> Any:
        data = shot.model_dump(mode="json") if hasattr(shot, "model_dump") else dict(shot)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO storyboard_shots (
                        storyboard_shot_id, blueprint_id, version_id, project_id, scene_id,
                        shot_id, shot_number, status, intent_json, visual_plan_json,
                        continuity_plan_json, render_contract_json, department_notes_json,
                        storyboard_image_url, previs_image_id, rationale, locked,
                        created_at, updated_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["storyboard_shot_id"],
                        data["blueprint_id"],
                        data["version_id"],
                        data["project_id"],
                        data["scene_id"],
                        data["shot_id"],
                        int(data.get("shot_number") or 1),
                        data.get("status", "draft"),
                        self._json_dumps(data.get("intent", {})),
                        self._json_dumps(data.get("visual_plan", {})),
                        self._json_dumps(data.get("continuity_plan", {})),
                        self._json_dumps(data.get("render_contract", {})),
                        self._json_dumps(data.get("department_notes", [])),
                        data.get("storyboard_image_url"),
                        data.get("previs_image_id"),
                        data.get("rationale") or "",
                        1 if data.get("locked") else 0,
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("updated_at") or datetime.now().isoformat(),
                        self._json_dumps(data.get("metadata", {})),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_storyboard_shot", _write)
        return shot

    def _row_to_storyboard_shot(self, row: sqlite3.Row) -> Any:
        from app.models.storyboard_blueprint import (
            StoryboardDepartmentNote,
            StoryboardShot,
            StoryboardShotContinuityPlan,
            StoryboardShotIntent,
            StoryboardShotRenderContract,
            StoryboardShotVisualPlan,
        )

        return StoryboardShot(
            storyboard_shot_id=row["storyboard_shot_id"],
            blueprint_id=row["blueprint_id"],
            version_id=row["version_id"],
            project_id=row["project_id"],
            scene_id=row["scene_id"],
            shot_id=row["shot_id"],
            shot_number=int(row["shot_number"] or 1),
            status=row["status"],
            intent=StoryboardShotIntent(**self._json_loads(row["intent_json"], {})),
            visual_plan=StoryboardShotVisualPlan(**self._json_loads(row["visual_plan_json"], {})),
            continuity_plan=StoryboardShotContinuityPlan(**self._json_loads(row["continuity_plan_json"], {})),
            render_contract=StoryboardShotRenderContract(**self._json_loads(row["render_contract_json"], {})),
            department_notes=[
                StoryboardDepartmentNote(**item)
                for item in self._json_loads(row["department_notes_json"], [])
                if isinstance(item, dict)
            ],
            storyboard_image_url=row["storyboard_image_url"],
            previs_image_id=row["previs_image_id"],
            rationale=row["rationale"] or "",
            locked=bool(row["locked"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=self._json_loads(row["metadata"], {}),
        )

    def get_storyboard_shot(self, storyboard_shot_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM storyboard_shots WHERE storyboard_shot_id = ?", (storyboard_shot_id,))
            row = cursor.fetchone()
            return self._row_to_storyboard_shot(row) if row else None

    def get_shot_visual_plan(self, project_id: str, shot_id: str) -> dict:
        """Return a shot's reviewed visual-plan staging as a plain dict.

        Keyed by (project_id, shot_id) because that is what the render path has
        in scope -- the storyboard_shot_id primary key is not available there.
        Newest row wins when a shot exists across blueprint versions. Returns an
        empty dict when the shot has no staging, so the render path can treat
        "no staging" as "use the scene-level fallbacks" without special-casing.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT visual_plan_json FROM storyboard_shots
                WHERE project_id = ? AND shot_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (project_id, shot_id),
            )
            row = cursor.fetchone()
        if not row or not row[0]:
            return {}
        try:
            data = json.loads(row[0])
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def list_scene_shots(self, project_id: str, scene_id: str) -> list[dict]:
        """Return one row per shot in a scene (newest version wins), as plain
        dicts with shot_id, shot_number, intent_json and visual_plan_json.

        Used by the scene-staging previs assist to iterate a scene's shots
        without going through the blueprint-version model. Newest-per-shot keeps
        it consistent with get_shot_visual_plan, which the render path reads.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT shot_id, shot_number, intent_json, visual_plan_json
                FROM storyboard_shots
                WHERE project_id = ? AND scene_id = ?
                ORDER BY shot_number ASC, updated_at DESC
                """,
                (project_id, scene_id),
            )
            rows = cursor.fetchall()
        seen: set = set()
        shots: list[dict] = []
        for shot_id, shot_number, intent_json, visual_plan_json in rows:
            if shot_id in seen:
                continue
            seen.add(shot_id)
            shots.append({
                "shot_id": shot_id,
                "shot_number": shot_number,
                "intent_json": intent_json,
                "visual_plan_json": visual_plan_json,
            })
        return shots

    def update_shot_visual_plan(self, project_id: str, shot_id: str, plan: dict) -> bool:
        """Merge staging fields into a shot's visual_plan (newest row).

        The write counterpart of get_shot_visual_plan. MERGES: only the keys in
        `plan` are changed, so it never blanks a field the storyboard already
        set, and an empty `plan` is a no-op. Returns True if a row was updated.
        """
        if not isinstance(plan, dict) or not plan:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT rowid, visual_plan_json FROM storyboard_shots
                WHERE project_id = ? AND shot_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (project_id, shot_id),
            )
            row = cursor.fetchone()
            if not row:
                return False
            rowid, existing_json = row
            try:
                existing = json.loads(existing_json) if existing_json else {}
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}
            existing.update(plan)
            cursor.execute(
                "UPDATE storyboard_shots SET visual_plan_json = ?, "
                "updated_at = datetime('now') WHERE rowid = ?",
                (json.dumps(existing), rowid),
            )
            conn.commit()
        return True

    def list_storyboard_shots(self, blueprint_id: str, version_id: str | None = None) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if version_id:
                cursor.execute(
                    """
                    SELECT * FROM storyboard_shots
                    WHERE blueprint_id = ? AND version_id = ?
                    ORDER BY shot_number ASC, shot_id ASC
                    """,
                    (blueprint_id, version_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM storyboard_shots
                    WHERE blueprint_id = ?
                    ORDER BY shot_number ASC, shot_id ASC
                    """,
                    (blueprint_id,),
                )
            return [self._row_to_storyboard_shot(row) for row in cursor.fetchall()]

    def commit_storyboard_blueprint_version(
        self,
        *,
        blueprint: Any,
        version: Any,
        shots: list[Any],
        superseded_version: Any | None = None,
        expected_version_id: str | None = None,
    ) -> Any:
        """Persist a blueprint pointer, version, and its shots in one transaction."""
        blueprint_data = blueprint.model_dump(mode="json") if hasattr(blueprint, "model_dump") else dict(blueprint)
        version_data = version.model_dump(mode="json") if hasattr(version, "model_dump") else dict(version)
        superseded_data = (
            superseded_version.model_dump(mode="json")
            if hasattr(superseded_version, "model_dump")
            else dict(superseded_version)
        ) if superseded_version is not None else None
        shot_rows = [
            shot.model_dump(mode="json") if hasattr(shot, "model_dump") else dict(shot)
            for shot in shots
        ]

        def _write_version(cursor: sqlite3.Cursor, data: dict[str, Any]) -> None:
            cursor.execute(
                """
                INSERT OR REPLACE INTO storyboard_blueprint_versions (
                    version_id, blueprint_id, project_id, scene_id, version_number,
                    status, change_reason, source_version_id, provenance_json,
                    inspection_json, created_at, approved_at, approved_by, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["version_id"], data["blueprint_id"], data["project_id"], data["scene_id"],
                    int(data.get("version_number") or 1), data.get("status", "draft"),
                    data.get("change_reason") or "", data.get("source_version_id"),
                    self._json_dumps(data.get("provenance", {})),
                    self._json_dumps(data.get("inspection", {})),
                    data.get("created_at") or datetime.now().isoformat(), data.get("approved_at"),
                    data.get("approved_by") or "", self._json_dumps(data.get("metadata", {})),
                ),
            )

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("BEGIN IMMEDIATE" if expected_version_id is not None else "BEGIN")
                    if expected_version_id is not None:
                        current = cursor.execute("SELECT current_version_id FROM storyboard_blueprints WHERE blueprint_id = ?", (blueprint_data["blueprint_id"],)).fetchone()
                        if current is None or current[0] != expected_version_id:
                            raise ValueError("Storyboard version changed")
                    if superseded_data is not None:
                        _write_version(cursor, superseded_data)
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO storyboard_blueprints (
                            blueprint_id, project_id, scene_id, current_version_id,
                            status, approved_version_id, locked, created_at, updated_at,
                            created_by, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            blueprint_data["blueprint_id"], blueprint_data["project_id"],
                            blueprint_data["scene_id"], blueprint_data.get("current_version_id"),
                            blueprint_data.get("status", "draft"), blueprint_data.get("approved_version_id"),
                            1 if blueprint_data.get("locked") else 0,
                            blueprint_data.get("created_at") or datetime.now().isoformat(),
                            blueprint_data.get("updated_at") or datetime.now().isoformat(),
                            blueprint_data.get("created_by") or "",
                            self._json_dumps(blueprint_data.get("metadata", {})),
                        ),
                    )
                    _write_version(cursor, version_data)
                    for data in shot_rows:
                        cursor.execute(
                            """
                            INSERT INTO storyboard_shots (
                                storyboard_shot_id, blueprint_id, version_id, project_id, scene_id,
                                shot_id, shot_number, status, intent_json, visual_plan_json,
                                continuity_plan_json, render_contract_json, department_notes_json,
                                storyboard_image_url, previs_image_id, rationale, locked,
                                created_at, updated_at, metadata
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                data["storyboard_shot_id"], data["blueprint_id"], data["version_id"],
                                data["project_id"], data["scene_id"], data["shot_id"],
                                int(data.get("shot_number") or 1), data.get("status", "draft"),
                                self._json_dumps(data.get("intent", {})), self._json_dumps(data.get("visual_plan", {})),
                                self._json_dumps(data.get("continuity_plan", {})),
                                self._json_dumps(data.get("render_contract", {})),
                                self._json_dumps(data.get("department_notes", [])), data.get("storyboard_image_url"),
                                data.get("previs_image_id"), data.get("rationale") or "",
                                1 if data.get("locked") else 0,
                                data.get("created_at") or datetime.now().isoformat(),
                                data.get("updated_at") or datetime.now().isoformat(),
                                self._json_dumps(data.get("metadata", {})),
                            ),
                        )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

        self._execute_write_with_retry("commit_storyboard_blueprint_version", _write)
        return version

    def delete_storyboard_shot(self, storyboard_shot_id: str, version_id: str) -> bool:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM storyboard_shots WHERE storyboard_shot_id = ? AND version_id = ?",
                    (storyboard_shot_id, version_id),
                )
                conn.commit()
                return cursor.rowcount > 0

        return bool(self._execute_write_with_retry("delete_storyboard_shot", _write))

    def reorder_storyboard_shots(self, version_id: str, ordered_storyboard_shot_ids: list[str]) -> bool:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("BEGIN")
                    cursor.execute(
                        "SELECT storyboard_shot_id FROM storyboard_shots WHERE version_id = ?",
                        (version_id,),
                    )
                    existing = {str(row["storyboard_shot_id"]) for row in cursor.fetchall()}
                    if existing != set(ordered_storyboard_shot_ids) or len(existing) != len(ordered_storyboard_shot_ids):
                        raise ValueError("Storyboard reorder must contain every current shot exactly once")
                    for position, storyboard_shot_id in enumerate(ordered_storyboard_shot_ids, start=1):
                        cursor.execute(
                            "UPDATE storyboard_shots SET shot_number = ?, updated_at = ? WHERE storyboard_shot_id = ? AND version_id = ?",
                            (position, datetime.now().isoformat(), storyboard_shot_id, version_id),
                        )
                    conn.commit()
                    return True
                except Exception:
                    conn.rollback()
                    raise

        return bool(self._execute_write_with_retry("reorder_storyboard_shots", _write))

    def save_storyboard_render_link(self, link: Any) -> Any:
        data = link.model_dump(mode="json") if hasattr(link, "model_dump") else dict(link)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO storyboard_render_links (
                        link_id, project_id, scene_id, shot_id, storyboard_shot_id,
                        blueprint_id, version_id, render_job_id, link_type, created_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["link_id"],
                        data["project_id"],
                        data["scene_id"],
                        data["shot_id"],
                        data["storyboard_shot_id"],
                        data["blueprint_id"],
                        data["version_id"],
                        data["render_job_id"],
                        data.get("link_type") or "initial_render",
                        data.get("created_at") or datetime.now().isoformat(),
                        self._json_dumps(data.get("metadata", {})),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_storyboard_render_link", _write)
        return link

    def list_storyboard_render_links(
        self,
        project_id: str | None = None,
        shot_id: str | None = None,
        render_job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM storyboard_render_links WHERE 1=1"
            params: list[Any] = []
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            if shot_id:
                query += " AND shot_id = ?"
                params.append(shot_id)
            if render_job_id:
                query += " AND render_job_id = ?"
                params.append(render_job_id)
            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            return [
                {
                    **dict(row),
                    "metadata": self._json_loads(row["metadata"], {}),
                }
                for row in cursor.fetchall()
            ]

    def save_storyboard_revision_link(self, link: Any) -> Any:
        data = link.model_dump(mode="json") if hasattr(link, "model_dump") else dict(link)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO storyboard_revision_links (
                        link_id, project_id, scene_id, shot_id, revision_id,
                        original_version_id, proposed_version_id, change_scope_json,
                        created_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["link_id"],
                        data["project_id"],
                        data["scene_id"],
                        data["shot_id"],
                        data["revision_id"],
                        data["original_version_id"],
                        data.get("proposed_version_id"),
                        self._json_dumps(data.get("change_scope", {})),
                        data.get("created_at") or datetime.now().isoformat(),
                        self._json_dumps(data.get("metadata", {})),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_storyboard_revision_link", _write)
        return link

    def list_storyboard_revision_links(
        self,
        project_id: str | None = None,
        revision_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM storyboard_revision_links WHERE 1=1"
            params: list[Any] = []
            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)
            if revision_id:
                query += " AND revision_id = ?"
                params.append(revision_id)
            query += " ORDER BY created_at DESC"
            cursor.execute(query, params)
            return [
                {
                    **dict(row),
                    "change_scope": self._json_loads(row["change_scope_json"], {}),
                    "metadata": self._json_loads(row["metadata"], {}),
                }
                for row in cursor.fetchall()
            ]

    # =========================================================================
    # PROFESSIONAL STUDIO WORKFLOW PERSISTENCE
    # =========================================================================

    def _row_to_studio_workflow_project_state(self, row: sqlite3.Row) -> Any:
        from app.models.studio_workflow import StudioWorkflowProjectState

        return StudioWorkflowProjectState(
            project_id=row["project_id"],
            current_phase=row["current_phase"] or "intake",
            workflow_status=row["workflow_status"] or "active",
            active_version_id=row["active_version_id"] or "",
            active_gate_id=row["active_gate_id"] or "",
            metadata=self._json_loads(row["metadata_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_studio_workflow_project_state(self, project_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM studio_workflow_project_states WHERE project_id = ?", (project_id,))
            row = cursor.fetchone()
            return self._row_to_studio_workflow_project_state(row) if row else None

    def save_studio_workflow_project_state(self, state: Any) -> Any:
        data = state.model_dump(mode="json") if hasattr(state, "model_dump") else dict(state)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO studio_workflow_project_states (
                        project_id, current_phase, workflow_status, active_version_id,
                        active_gate_id, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["project_id"],
                        data.get("current_phase") or "intake",
                        data.get("workflow_status") or "active",
                        data.get("active_version_id") or "",
                        data.get("active_gate_id") or "",
                        self._json_dumps(data.get("metadata", {})),
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("updated_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_studio_workflow_project_state", _write)
        return state

    def _row_to_studio_collaborator(self, row: sqlite3.Row) -> Any:
        from app.models.studio_workflow import StudioCollaborator

        return StudioCollaborator(
            collaborator_id=row["collaborator_id"],
            project_id=row["project_id"],
            actor_id=row["actor_id"],
            display_name=row["display_name"] or "",
            role=row["role"] or "reviewer",
            permission_scope=row["permission_scope"] or "project",
            status=row["status"] or "active",
            last_seen_at=row["last_seen_at"],
            metadata=self._json_loads(row["metadata_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def upsert_studio_collaborator(self, collaborator: Any) -> Any:
        data = collaborator.model_dump(mode="json") if hasattr(collaborator, "model_dump") else dict(collaborator)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO studio_collaborators (
                        collaborator_id, project_id, actor_id, display_name, role,
                        permission_scope, status, last_seen_at, metadata_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, actor_id) DO UPDATE SET
                        display_name = excluded.display_name,
                        role = excluded.role,
                        permission_scope = excluded.permission_scope,
                        status = excluded.status,
                        last_seen_at = excluded.last_seen_at,
                        metadata_json = excluded.metadata_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        data["collaborator_id"],
                        data["project_id"],
                        data["actor_id"],
                        data.get("display_name") or "",
                        data.get("role") or "reviewer",
                        data.get("permission_scope") or "project",
                        data.get("status") or "active",
                        data.get("last_seen_at"),
                        self._json_dumps(data.get("metadata", {})),
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("updated_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("upsert_studio_collaborator", _write)
        return collaborator

    def get_studio_collaborator(self, project_id: str, actor_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM studio_collaborators WHERE project_id = ? AND actor_id = ? LIMIT 1",
                (project_id, actor_id),
            )
            row = cursor.fetchone()
            return self._row_to_studio_collaborator(row) if row else None

    def list_studio_collaborators(self, project_id: str, limit: int = 200) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM studio_collaborators
                WHERE project_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (project_id, max(1, min(int(limit), 500))),
            )
            return [self._row_to_studio_collaborator(row) for row in cursor.fetchall()]

    def _row_to_studio_artifact_version(self, row: sqlite3.Row) -> Any:
        from app.models.studio_workflow import StudioArtifactVersion, StudioWorkflowEvidenceRef

        evidence = [
            StudioWorkflowEvidenceRef(**item)
            for item in self._json_loads(row["evidence_json"], [])
            if isinstance(item, dict)
        ]
        return StudioArtifactVersion(
            version_id=row["version_id"],
            project_id=row["project_id"],
            artifact_type=row["artifact_type"],
            artifact_id=row["artifact_id"],
            version_number=int(row["version_number"] or 1),
            status=row["status"] or "draft",
            title=row["title"] or "",
            summary=row["summary"] or "",
            source_version_id=row["source_version_id"],
            canonical_ref_type=row["canonical_ref_type"] or "",
            canonical_ref_id=row["canonical_ref_id"] or "",
            snapshot=self._json_loads(row["snapshot_json"], {}),
            evidence=evidence,
            created_by=row["created_by"] or "",
            approved_by=row["approved_by"] or "",
            approved_at=row["approved_at"],
            locked_at=row["locked_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def next_studio_artifact_version_number(self, project_id: str, artifact_type: str, artifact_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT MAX(version_number) AS max_version
                FROM studio_artifact_versions
                WHERE project_id = ? AND artifact_type = ? AND artifact_id = ?
                """,
                (project_id, artifact_type, artifact_id),
            )
            row = cursor.fetchone()
            return int((row["max_version"] if row else 0) or 0) + 1

    def save_studio_artifact_version(self, version: Any) -> Any:
        data = version.model_dump(mode="json") if hasattr(version, "model_dump") else dict(version)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO studio_artifact_versions (
                        version_id, project_id, artifact_type, artifact_id, version_number,
                        status, title, summary, source_version_id, canonical_ref_type,
                        canonical_ref_id, snapshot_json, evidence_json, created_by,
                        approved_by, approved_at, locked_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["version_id"],
                        data["project_id"],
                        data["artifact_type"],
                        data["artifact_id"],
                        int(data.get("version_number") or 1),
                        data.get("status") or "draft",
                        data.get("title") or "",
                        data.get("summary") or "",
                        data.get("source_version_id"),
                        data.get("canonical_ref_type") or "",
                        data.get("canonical_ref_id") or "",
                        self._json_dumps(data.get("snapshot", {})),
                        self._json_dumps(data.get("evidence", [])),
                        data.get("created_by") or "",
                        data.get("approved_by") or "",
                        data.get("approved_at"),
                        data.get("locked_at"),
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("updated_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_studio_artifact_version", _write)
        return version

    def get_studio_artifact_version(self, version_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM studio_artifact_versions WHERE version_id = ?", (version_id,))
            row = cursor.fetchone()
            return self._row_to_studio_artifact_version(row) if row else None

    def list_studio_artifact_versions(
        self,
        project_id: str,
        artifact_type: str | None = None,
        artifact_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM studio_artifact_versions WHERE project_id = ?"
            params: list[Any] = [project_id]
            if artifact_type:
                query += " AND artifact_type = ?"
                params.append(artifact_type)
            if artifact_id:
                query += " AND artifact_id = ?"
                params.append(artifact_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY artifact_type ASC, artifact_id ASC, version_number DESC LIMIT ?"
            params.append(max(1, min(int(limit), 200)))
            cursor.execute(query, params)
            return [self._row_to_studio_artifact_version(row) for row in cursor.fetchall()]

    def save_studio_version_lineage(self, lineage: Any) -> Any:
        data = lineage.model_dump(mode="json") if hasattr(lineage, "model_dump") else dict(lineage)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO studio_version_lineage (
                        lineage_id, project_id, parent_version_id, child_version_id,
                        relationship_type, change_summary, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["lineage_id"],
                        data["project_id"],
                        data["parent_version_id"],
                        data["child_version_id"],
                        data.get("relationship_type") or "revision",
                        data.get("change_summary") or "",
                        data.get("created_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_studio_version_lineage", _write)
        return lineage

    def list_studio_version_lineage(self, version_id: str) -> list[Any]:
        from app.models.studio_workflow import StudioVersionLineage

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM studio_version_lineage
                WHERE parent_version_id = ? OR child_version_id = ?
                ORDER BY created_at ASC
                """,
                (version_id, version_id),
            )
            return [
                StudioVersionLineage(
                    lineage_id=row["lineage_id"],
                    project_id=row["project_id"],
                    parent_version_id=row["parent_version_id"],
                    child_version_id=row["child_version_id"],
                    relationship_type=row["relationship_type"] or "revision",
                    change_summary=row["change_summary"] or "",
                    created_at=row["created_at"],
                )
                for row in cursor.fetchall()
            ]

    def _row_to_studio_approval_gate(self, row: sqlite3.Row) -> Any:
        from app.models.studio_workflow import StudioApprovalGate

        return StudioApprovalGate(
            gate_id=row["gate_id"],
            project_id=row["project_id"],
            gate_type=row["gate_type"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            version_id=row["version_id"],
            status=row["status"] or "pending",
            required_role=row["required_role"] or "producer",
            required_decision=row["required_decision"] or "approve",
            queue_item_id=row["queue_item_id"],
            manual_dependency_id=row["manual_dependency_id"],
            evidence_policy=self._json_loads(row["evidence_policy_json"], {}),
            latest_evaluation=self._json_loads(row["latest_evaluation_json"], {}),
            opened_by=row["opened_by"] or "",
            closed_by=row["closed_by"] or "",
            closed_at=row["closed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_studio_approval_gate(self, gate: Any) -> Any:
        data = gate.model_dump(mode="json") if hasattr(gate, "model_dump") else dict(gate)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO studio_approval_gates (
                        gate_id, project_id, gate_type, target_type, target_id, version_id,
                        status, required_role, required_decision, queue_item_id,
                        manual_dependency_id, evidence_policy_json, latest_evaluation_json,
                        opened_by, closed_by, closed_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["gate_id"],
                        data["project_id"],
                        data["gate_type"],
                        data["target_type"],
                        data["target_id"],
                        data.get("version_id"),
                        data.get("status") or "pending",
                        data.get("required_role") or "producer",
                        data.get("required_decision") or "approve",
                        data.get("queue_item_id"),
                        data.get("manual_dependency_id"),
                        self._json_dumps(data.get("evidence_policy", {})),
                        self._json_dumps(data.get("latest_evaluation", {})),
                        data.get("opened_by") or "",
                        data.get("closed_by") or "",
                        data.get("closed_at"),
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("updated_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_studio_approval_gate", _write)
        return gate

    def get_studio_approval_gate(self, gate_id: str) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM studio_approval_gates WHERE gate_id = ?", (gate_id,))
            row = cursor.fetchone()
            return self._row_to_studio_approval_gate(row) if row else None

    def list_studio_approval_gates(
        self,
        project_id: str,
        status: str | None = None,
        gate_type: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM studio_approval_gates WHERE project_id = ?"
            params: list[Any] = [project_id]
            if status:
                query += " AND status = ?"
                params.append(status)
            if gate_type:
                query += " AND gate_type = ?"
                params.append(gate_type)
            if target_type:
                query += " AND target_type = ?"
                params.append(target_type)
            if target_id:
                query += " AND target_id = ?"
                params.append(target_id)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 200)))
            cursor.execute(query, params)
            return [self._row_to_studio_approval_gate(row) for row in cursor.fetchall()]

    def _row_to_studio_approval_decision(self, row: sqlite3.Row) -> Any:
        from app.models.studio_workflow import StudioApprovalDecision, StudioWorkflowEvidenceRef

        evidence = [
            StudioWorkflowEvidenceRef(**item)
            for item in self._json_loads(row["evidence_json"], [])
            if isinstance(item, dict)
        ]
        return StudioApprovalDecision(
            decision_id=row["decision_id"],
            project_id=row["project_id"],
            gate_id=row["gate_id"],
            version_id=row["version_id"],
            actor_id=row["actor_id"],
            actor_role=row["actor_role"] or "reviewer",
            decision=row["decision"],
            rationale=row["rationale"] or "",
            notes=row["notes"] or "",
            evidence=evidence,
            created_at=row["created_at"],
        )

    def save_studio_approval_decision(self, decision: Any) -> Any:
        data = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO studio_approval_decisions (
                        decision_id, project_id, gate_id, version_id, actor_id,
                        actor_role, decision, rationale, notes, evidence_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["decision_id"],
                        data["project_id"],
                        data["gate_id"],
                        data.get("version_id"),
                        data["actor_id"],
                        data.get("actor_role") or "reviewer",
                        data["decision"],
                        data.get("rationale") or "",
                        data.get("notes") or "",
                        self._json_dumps(data.get("evidence", [])),
                        data.get("created_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_studio_approval_decision", _write)
        return decision

    def commit_studio_approval_transition(
        self,
        *,
        decision: Any,
        gate: Any,
        version: Any | None = None,
        task: Any | None = None,
    ) -> Any:
        """Atomically persist the canonical records changed by one approval decision."""
        decision_data = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)
        gate_data = gate.model_dump(mode="json") if hasattr(gate, "model_dump") else dict(gate)
        version_data = (
            version.model_dump(mode="json") if hasattr(version, "model_dump") else dict(version)
        ) if version is not None else None
        task_data = (
            task.model_dump(mode="json") if hasattr(task, "model_dump") else dict(task)
        ) if task is not None else None

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("BEGIN")
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO studio_approval_decisions (
                            decision_id, project_id, gate_id, version_id, actor_id,
                            actor_role, decision, rationale, notes, evidence_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            decision_data["decision_id"],
                            decision_data["project_id"],
                            decision_data["gate_id"],
                            decision_data.get("version_id"),
                            decision_data["actor_id"],
                            decision_data.get("actor_role") or "reviewer",
                            decision_data["decision"],
                            decision_data.get("rationale") or "",
                            decision_data.get("notes") or "",
                            self._json_dumps(decision_data.get("evidence", [])),
                            decision_data.get("created_at") or datetime.now().isoformat(),
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO studio_approval_gates (
                            gate_id, project_id, gate_type, target_type, target_id, version_id,
                            status, required_role, required_decision, queue_item_id,
                            manual_dependency_id, evidence_policy_json, latest_evaluation_json,
                            opened_by, closed_by, closed_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            gate_data["gate_id"],
                            gate_data["project_id"],
                            gate_data["gate_type"],
                            gate_data["target_type"],
                            gate_data["target_id"],
                            gate_data.get("version_id"),
                            gate_data.get("status") or "pending",
                            gate_data.get("required_role") or "producer",
                            gate_data.get("required_decision") or "approve",
                            gate_data.get("queue_item_id"),
                            gate_data.get("manual_dependency_id"),
                            self._json_dumps(gate_data.get("evidence_policy", {})),
                            self._json_dumps(gate_data.get("latest_evaluation", {})),
                            gate_data.get("opened_by") or "",
                            gate_data.get("closed_by") or "",
                            gate_data.get("closed_at"),
                            gate_data.get("created_at") or datetime.now().isoformat(),
                            gate_data.get("updated_at") or datetime.now().isoformat(),
                        ),
                    )
                    if version_data is not None:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO studio_artifact_versions (
                                version_id, project_id, artifact_type, artifact_id, version_number,
                                status, title, summary, source_version_id, canonical_ref_type,
                                canonical_ref_id, snapshot_json, evidence_json, created_by,
                                approved_by, approved_at, locked_at, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                version_data["version_id"],
                                version_data["project_id"],
                                version_data["artifact_type"],
                                version_data["artifact_id"],
                                int(version_data.get("version_number") or 1),
                                version_data.get("status") or "draft",
                                version_data.get("title") or "",
                                version_data.get("summary") or "",
                                version_data.get("source_version_id"),
                                version_data.get("canonical_ref_type") or "",
                                version_data.get("canonical_ref_id") or "",
                                self._json_dumps(version_data.get("snapshot", {})),
                                self._json_dumps(version_data.get("evidence", [])),
                                version_data.get("created_by") or "",
                                version_data.get("approved_by") or "",
                                version_data.get("approved_at"),
                                version_data.get("locked_at"),
                                version_data.get("created_at") or datetime.now().isoformat(),
                                version_data.get("updated_at") or datetime.now().isoformat(),
                            ),
                        )
                    if task_data is not None:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO studio_workflow_tasks (
                                workflow_task_id, project_id, title, task_type, target_type, target_id,
                                version_id, assignee_actor_id, status, priority, queue_item_id,
                                due_at, metadata_json, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                task_data["workflow_task_id"],
                                task_data["project_id"],
                                task_data["title"],
                                task_data["task_type"],
                                task_data.get("target_type") or "",
                                task_data.get("target_id") or "",
                                task_data.get("version_id"),
                                task_data.get("assignee_actor_id") or "",
                                task_data.get("status") or "open",
                                task_data.get("priority") or "normal",
                                task_data.get("queue_item_id"),
                                task_data.get("due_at"),
                                self._json_dumps(task_data.get("metadata", {})),
                                task_data.get("created_at") or datetime.now().isoformat(),
                                task_data.get("updated_at") or datetime.now().isoformat(),
                            ),
                        )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

        self._execute_write_with_retry("commit_studio_approval_transition", _write)
        return decision

    def list_studio_approval_decisions(self, project_id: str, gate_id: str | None = None, limit: int = 50) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM studio_approval_decisions WHERE project_id = ?"
            params: list[Any] = [project_id]
            if gate_id:
                query += " AND gate_id = ?"
                params.append(gate_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 200)))
            cursor.execute(query, params)
            return [self._row_to_studio_approval_decision(row) for row in cursor.fetchall()]

    def _row_to_studio_workflow_comment(self, row: sqlite3.Row) -> Any:
        from app.models.studio_workflow import StudioWorkflowComment

        return StudioWorkflowComment(
            comment_id=row["comment_id"],
            project_id=row["project_id"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            version_id=row["version_id"],
            parent_comment_id=row["parent_comment_id"],
            actor_id=row["actor_id"],
            actor_role=row["actor_role"] or "reviewer",
            display_name=row["display_name"] or "",
            body=row["body"],
            status=row["status"] or "open",
            resolved_by=row["resolved_by"],
            resolved_at=row["resolved_at"],
            metadata=self._json_loads(row["metadata_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_studio_workflow_comment(self, comment: Any) -> Any:
        data = comment.model_dump(mode="json") if hasattr(comment, "model_dump") else dict(comment)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO studio_workflow_comments (
                        comment_id, project_id, target_type, target_id, version_id,
                        parent_comment_id, actor_id, actor_role, display_name, body,
                        status, resolved_by, resolved_at, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["comment_id"],
                        data["project_id"],
                        data["target_type"],
                        data["target_id"],
                        data.get("version_id"),
                        data.get("parent_comment_id"),
                        data["actor_id"],
                        data.get("actor_role") or "reviewer",
                        data.get("display_name") or "",
                        data["body"],
                        data.get("status") or "open",
                        data.get("resolved_by"),
                        data.get("resolved_at"),
                        self._json_dumps(data.get("metadata", {})),
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("updated_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_studio_workflow_comment", _write)
        return comment

    def list_studio_workflow_comments(
        self,
        project_id: str,
        target_type: str | None = None,
        target_id: str | None = None,
        version_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM studio_workflow_comments WHERE project_id = ?"
            params: list[Any] = [project_id]
            if target_type:
                query += " AND target_type = ?"
                params.append(target_type)
            if target_id:
                query += " AND target_id = ?"
                params.append(target_id)
            if version_id:
                query += " AND version_id = ?"
                params.append(version_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 200)))
            cursor.execute(query, params)
            return [self._row_to_studio_workflow_comment(row) for row in cursor.fetchall()]

    def _row_to_studio_workflow_task(self, row: sqlite3.Row) -> Any:
        from app.models.studio_workflow import StudioWorkflowTask

        return StudioWorkflowTask(
            workflow_task_id=row["workflow_task_id"],
            project_id=row["project_id"],
            title=row["title"],
            task_type=row["task_type"],
            target_type=row["target_type"] or "",
            target_id=row["target_id"] or "",
            version_id=row["version_id"],
            assignee_actor_id=row["assignee_actor_id"] or "",
            status=row["status"] or "open",
            priority=row["priority"] or "normal",
            queue_item_id=row["queue_item_id"],
            due_at=row["due_at"],
            metadata=self._json_loads(row["metadata_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_studio_workflow_task(self, task: Any) -> Any:
        data = task.model_dump(mode="json") if hasattr(task, "model_dump") else dict(task)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO studio_workflow_tasks (
                        workflow_task_id, project_id, title, task_type, target_type, target_id,
                        version_id, assignee_actor_id, status, priority, queue_item_id,
                        due_at, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["workflow_task_id"],
                        data["project_id"],
                        data["title"],
                        data["task_type"],
                        data.get("target_type") or "",
                        data.get("target_id") or "",
                        data.get("version_id"),
                        data.get("assignee_actor_id") or "",
                        data.get("status") or "open",
                        data.get("priority") or "normal",
                        data.get("queue_item_id"),
                        data.get("due_at"),
                        self._json_dumps(data.get("metadata", {})),
                        data.get("created_at") or datetime.now().isoformat(),
                        data.get("updated_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_studio_workflow_task", _write)
        return task

    def list_studio_workflow_tasks(self, project_id: str, status: str | None = None, limit: int = 50) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM studio_workflow_tasks WHERE project_id = ?"
            params: list[Any] = [project_id]
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 200)))
            cursor.execute(query, params)
            return [self._row_to_studio_workflow_task(row) for row in cursor.fetchall()]

    def _row_to_studio_workflow_event(self, row: sqlite3.Row) -> Any:
        from app.models.studio_workflow import StudioWorkflowEvent

        return StudioWorkflowEvent(
            event_id=row["event_id"],
            project_id=row["project_id"],
            event_type=row["event_type"],
            actor_id=row["actor_id"] or "",
            target_type=row["target_type"] or "",
            target_id=row["target_id"] or "",
            version_id=row["version_id"],
            gate_id=row["gate_id"],
            decision_id=row["decision_id"],
            message=row["message"] or "",
            details=self._json_loads(row["details_json"], {}),
            created_at=row["created_at"],
        )

    def save_studio_workflow_event(self, event: Any) -> Any:
        data = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO studio_workflow_events (
                        event_id, project_id, event_type, actor_id, target_type, target_id,
                        version_id, gate_id, decision_id, message, details_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["event_id"],
                        data["project_id"],
                        data["event_type"],
                        data.get("actor_id") or "",
                        data.get("target_type") or "",
                        data.get("target_id") or "",
                        data.get("version_id"),
                        data.get("gate_id"),
                        data.get("decision_id"),
                        data.get("message") or "",
                        self._json_dumps(data.get("details", {})),
                        data.get("created_at") or datetime.now().isoformat(),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_studio_workflow_event", _write)
        return event

    def list_studio_workflow_events(
        self,
        project_id: str,
        target_type: str | None = None,
        target_id: str | None = None,
        gate_id: str | None = None,
        version_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM studio_workflow_events WHERE project_id = ?"
            params: list[Any] = [project_id]
            if target_type:
                query += " AND target_type = ?"
                params.append(target_type)
            if target_id:
                query += " AND target_id = ?"
                params.append(target_id)
            if gate_id:
                query += " AND gate_id = ?"
                params.append(gate_id)
            if version_id:
                query += " AND version_id = ?"
                params.append(version_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(1, min(int(limit), 200)))
            cursor.execute(query, params)
            return [self._row_to_studio_workflow_event(row) for row in cursor.fetchall()]

    def satisfy_manual_queue_dependencies(self, manual_dependency_id: str, reason: str = "") -> int:
        now = datetime.now().isoformat()

        def _write() -> int:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE production_queue_dependencies
                    SET status = 'satisfied', updated_at = ?, reason = COALESCE(NULLIF(?, ''), reason)
                    WHERE depends_on_type = 'manual_gate' AND depends_on_id = ?
                    """,
                    (now, reason, manual_dependency_id),
                )
                count = cursor.rowcount
                conn.commit()
                return count

        return self._execute_write_with_retry("satisfy_manual_queue_dependencies", _write)

    # =========================================================================
    # PREVIS IMAGES
    # =========================================================================

    def save_previs_image(
        self,
        project_id: str,
        scene_id: str,
        shot_id: Optional[str],
        image_path: str,
        job_id: str,
        status: str,
        prompt_used: str,
        fallback: bool,
        previs_seed: Optional[int] = None,
        seed_locked: bool = False,
        *,
        image_id: str | None = None,
        blueprint_id: str | None = None,
        blueprint_version_id: str | None = None,
        storyboard_shot_id: str | None = None,
        source_previs_image_id: str | None = None,
        attempt_number: int = 1,
        failure_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Save or update a previs image record.

        Args:
            project_id: Project identifier
            scene_id: Scene identifier
            shot_id: Optional shot identifier (None for scene hero images)
            image_path: Path or URL to the image
            job_id: Render job ID that generated this image
            status: Status (pending, complete, failed)
            prompt_used: The prompt used to generate the image
            fallback: Whether this is a fallback/placeholder image
            previs_seed: Pollinations.ai seed for consistent generation
            seed_locked: Whether to lock this seed for future regenerations

        Returns:
            True if saved successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            record_id = image_id or f"previs_{project_id}_{scene_id}_{shot_id or 'hero'}_{uuid4().hex[:8]}"
            now = datetime.now().isoformat()

            cursor.execute(
                """
                INSERT INTO previs_images (
                    id, project_id, scene_id, shot_id, image_path,
                    job_id, status, prompt_used, fallback, previs_seed, seed_locked,
                    blueprint_id, blueprint_version_id, storyboard_shot_id,
                    source_previs_image_id, attempt_number, failure_reason, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    project_id,
                    scene_id,
                    shot_id,
                    image_path,
                    job_id,
                    status,
                    prompt_used,
                    1 if fallback else 0,
                    previs_seed,
                    1 if seed_locked else 0,
                    blueprint_id,
                    blueprint_version_id,
                    storyboard_shot_id,
                    source_previs_image_id,
                    max(1, int(attempt_number)),
                    failure_reason,
                    json.dumps(metadata or {}, sort_keys=True),
                    now,
                    now,
                ),
            )
            conn.commit()
            return True

    def load_previs_images(self, project_id: str, scene_id: Optional[str] = None) -> list:
        """
        Load previs images for a project, optionally filtered by scene.

        Args:
            project_id: Project identifier
            scene_id: Optional scene identifier to filter by

        Returns:
            List of previs image records
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if scene_id:
                cursor.execute(
                    """
                    SELECT * FROM previs_images
                    WHERE project_id = ? AND scene_id = ?
                    ORDER BY created_at DESC
                    """,
                    (project_id, scene_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM previs_images
                    WHERE project_id = ?
                    ORDER BY scene_id, created_at DESC
                    """,
                    (project_id,),
                )

            rows = cursor.fetchall()
            images = []
            for row in rows:
                row_dict = dict(row)
                images.append({
                    "id": row_dict["id"],
                    "project_id": row_dict["project_id"],
                    "scene_id": row_dict["scene_id"],
                    "shot_id": row_dict["shot_id"],
                    "image_path": row_dict["image_path"],
                    "job_id": row_dict["job_id"],
                    "status": row_dict["status"],
                    "prompt_used": row_dict["prompt_used"],
                    "fallback": bool(row_dict["fallback"]),
                    "previs_seed": row_dict.get("previs_seed"),
                    "seed_locked": bool(row_dict.get("seed_locked", 0)),
                    "blueprint_id": row_dict.get("blueprint_id"),
                    "blueprint_version_id": row_dict.get("blueprint_version_id"),
                    "storyboard_shot_id": row_dict.get("storyboard_shot_id"),
                    "approved": bool(row_dict.get("approved", 0)),
                    "approved_at": row_dict.get("approved_at"),
                    "approved_by": row_dict.get("approved_by"),
                    "failure_reason": row_dict.get("failure_reason"),
                    "source_previs_image_id": row_dict.get("source_previs_image_id"),
                    "attempt_number": int(row_dict.get("attempt_number") or 1),
                    "metadata": json.loads(row_dict.get("metadata_json") or "{}"),
                    "created_at": row_dict["created_at"],
                    "updated_at": row_dict.get("updated_at", row_dict["created_at"]),
                })

            return images

    def update_previs_image_status(
        self,
        job_id: str,
        status: str,
        image_path: Optional[str] = None,
        failure_reason: str | None = None,
    ) -> bool:
        """
        Update the status of a previs image by job_id.

        Args:
            job_id: Render job ID
            status: New status (pending, complete, failed)
            image_path: Optional new image path/URL

        Returns:
            True if updated successfully
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute(
                """
                UPDATE previs_images
                SET status = ?,
                    image_path = CASE WHEN ? IS NULL THEN image_path ELSE ? END,
                    failure_reason = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (status, image_path, image_path, failure_reason, now, job_id),
            )

            conn.commit()
            return cursor.rowcount > 0

    def get_previs_image(self, image_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM previs_images WHERE id = ?", (image_id,)).fetchone()
        return self._previs_row_to_dict(row) if row else None

    def get_previs_image_by_job(self, job_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM previs_images WHERE job_id = ?", (job_id,)).fetchone()
        return self._previs_row_to_dict(row) if row else None

    def approve_previs_image(self, image_id: str, project_id: str, approved_by: str) -> dict[str, Any] | None:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            row = cursor.execute(
                "SELECT * FROM previs_images WHERE id = ? AND project_id = ?",
                (image_id, project_id),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            current = dict(row)
            if current["status"] not in {"complete", "approved"} or not str(current["image_path"] or "").strip():
                conn.rollback()
                raise ValueError("Only completed Previs images with an output can be approved")
            target_column = "storyboard_shot_id" if current.get("storyboard_shot_id") else "shot_id"
            target_value = current.get(target_column)
            cursor.execute(
                f"""
                UPDATE previs_images
                SET approved = 0,
                    status = CASE WHEN status = 'approved' THEN 'superseded' ELSE status END,
                    updated_at = ?
                WHERE project_id = ? AND scene_id = ? AND {target_column} = ? AND id != ? AND approved = 1
                """,
                (now, project_id, current["scene_id"], target_value, image_id),
            )
            cursor.execute(
                """
                UPDATE previs_images
                SET approved = 1, status = 'approved', approved_at = ?, approved_by = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (now, approved_by, now, image_id, project_id),
            )
            updated = cursor.execute("SELECT * FROM previs_images WHERE id = ?", (image_id,)).fetchone()
            conn.commit()
        return self._previs_row_to_dict(updated)

    def save_previs_production_package(self, package: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().isoformat()
        package_id = str(package.get("package_id") or f"previs_pkg_{uuid4().hex[:12]}")
        payload = dict(package.get("payload") or {})
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO previs_production_packages (
                    package_id, project_id, scene_id, blueprint_id, blueprint_version_id,
                    status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    package_id,
                    package["project_id"],
                    package["scene_id"],
                    package["blueprint_id"],
                    package["blueprint_version_id"],
                    package.get("status") or "ready",
                    json.dumps(payload, sort_keys=True),
                    package.get("created_at") or now,
                    now,
                ),
            )
            conn.commit()
        return self.get_previs_production_package(package_id) or {}

    def get_previs_production_package(self, package_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM previs_production_packages WHERE package_id = ?",
                (package_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
        return data

    def list_previs_production_packages(self, project_id: str, scene_id: str | None = None) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            if scene_id:
                rows = conn.execute(
                    """SELECT * FROM previs_production_packages
                       WHERE project_id = ? AND scene_id = ? ORDER BY created_at DESC""",
                    (project_id, scene_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM previs_production_packages
                       WHERE project_id = ? ORDER BY scene_id, created_at DESC""",
                    (project_id,),
                ).fetchall()
        packages = []
        for row in rows:
            data = dict(row)
            data["payload"] = json.loads(data.pop("payload_json") or "{}")
            packages.append(data)
        return packages

    def _previs_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        return {
            "id": data["id"],
            "project_id": data["project_id"],
            "scene_id": data["scene_id"],
            "shot_id": data["shot_id"],
            "image_path": data["image_path"],
            "job_id": data["job_id"],
            "status": data["status"],
            "prompt_used": data["prompt_used"],
            "fallback": bool(data["fallback"]),
            "previs_seed": data.get("previs_seed"),
            "seed_locked": bool(data.get("seed_locked", 0)),
            "blueprint_id": data.get("blueprint_id"),
            "blueprint_version_id": data.get("blueprint_version_id"),
            "storyboard_shot_id": data.get("storyboard_shot_id"),
            "approved": bool(data.get("approved", 0)),
            "approved_at": data.get("approved_at"),
            "approved_by": data.get("approved_by"),
            "failure_reason": data.get("failure_reason"),
            "source_previs_image_id": data.get("source_previs_image_id"),
            "attempt_number": int(data.get("attempt_number") or 1),
            "metadata": json.loads(data.get("metadata_json") or "{}"),
            "created_at": data["created_at"],
            "updated_at": data.get("updated_at") or data["created_at"],
        }

    # =========================================================================
    # SCREENING ROOM OUTPUTS
    # =========================================================================

    def upsert_screening_output(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO screening_outputs (
                    screening_output_id, project_id, scene_id, shot_id, source_type,
                    source_id, output_type, original_url, playback_url, mime_type,
                    media_status, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(screening_output_id) DO UPDATE SET
                    scene_id = excluded.scene_id,
                    shot_id = excluded.shot_id,
                    original_url = excluded.original_url,
                    playback_url = excluded.playback_url,
                    mime_type = excluded.mime_type,
                    media_status = excluded.media_status,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    record["screening_output_id"],
                    record["project_id"],
                    record.get("scene_id"),
                    record.get("shot_id"),
                    record["source_type"],
                    record["source_id"],
                    record["output_type"],
                    record["original_url"],
                    record["playback_url"],
                    record.get("mime_type") or "video/mp4",
                    record.get("media_status") or "available",
                    json.dumps(record.get("metadata") or {}, sort_keys=True),
                    record.get("created_at") or now,
                    now,
                ),
            )
            conn.commit()
        return self.get_screening_output(record["screening_output_id"]) or {}

    def get_screening_output(self, screening_output_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM screening_outputs WHERE screening_output_id = ?",
                (screening_output_id,),
            ).fetchone()
        return self._screening_row_to_dict(row) if row else None

    def list_screening_outputs(self, project_id: str) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM screening_outputs
                   WHERE project_id = ? ORDER BY created_at DESC, screening_output_id DESC""",
                (project_id,),
            ).fetchall()
        return [self._screening_row_to_dict(row) for row in rows]

    def approve_screening_output(
        self,
        screening_output_id: str,
        project_id: str,
        approved_by: str,
    ) -> dict[str, Any] | None:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            row = cursor.execute(
                "SELECT * FROM screening_outputs WHERE screening_output_id = ? AND project_id = ?",
                (screening_output_id, project_id),
            ).fetchone()
            if row is None:
                conn.rollback()
                return None
            target = dict(row)
            if target["media_status"] != "available":
                conn.rollback()
                raise ValueError("Only available media can be approved")
            if target["output_type"] == "final":
                scope_sql = "output_type = 'final'"
                scope_params: tuple[Any, ...] = ()
            elif target.get("shot_id"):
                scope_sql = "output_type = ? AND shot_id = ?"
                scope_params = (target["output_type"], target["shot_id"])
            else:
                scope_sql = "output_type = ? AND scene_id = ?"
                scope_params = (target["output_type"], target.get("scene_id"))
            previous = cursor.execute(
                f"""SELECT screening_output_id FROM screening_outputs
                    WHERE project_id = ? AND {scope_sql} AND approved = 1 AND screening_output_id != ?
                    ORDER BY approved_at DESC LIMIT 1""",
                (project_id, *scope_params, screening_output_id),
            ).fetchone()
            previous_id = previous["screening_output_id"] if previous else None
            cursor.execute(
                f"""UPDATE screening_outputs SET approved = 0, updated_at = ?
                    WHERE project_id = ? AND {scope_sql} AND screening_output_id != ? AND approved = 1""",
                (now, project_id, *scope_params, screening_output_id),
            )
            cursor.execute(
                """UPDATE screening_outputs
                   SET approved = 1, approved_at = ?, approved_by = ?,
                       supersedes_output_id = COALESCE(?, supersedes_output_id), updated_at = ?
                   WHERE screening_output_id = ? AND project_id = ?""",
                (now, approved_by, previous_id, now, screening_output_id, project_id),
            )
            if target["output_type"] == "final":
                cursor.execute(
                    """
                    INSERT INTO screening_project_state (
                        project_id, current_final_output_id, completion_status,
                        completed_at, updated_at, metadata_json
                    ) VALUES (?, ?, 'complete', ?, ?, '{}')
                    ON CONFLICT(project_id) DO UPDATE SET
                        current_final_output_id = excluded.current_final_output_id,
                        completion_status = 'complete',
                        completed_at = excluded.completed_at,
                        updated_at = excluded.updated_at
                    """,
                    (project_id, screening_output_id, now, now),
                )
            updated = cursor.execute(
                "SELECT * FROM screening_outputs WHERE screening_output_id = ?",
                (screening_output_id,),
            ).fetchone()
            conn.commit()
        return self._screening_row_to_dict(updated)

    def get_screening_project_state(self, project_id: str) -> dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM screening_project_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return {
                "project_id": project_id,
                "current_final_output_id": None,
                "completion_status": "in_progress",
                "completed_at": None,
                "updated_at": None,
                "metadata": {},
            }
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _screening_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["approved"] = bool(data.get("approved"))
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    # =========================================================================
    # CANONICAL PRODUCTION WORKFLOW
    # =========================================================================

    def create_canonical_workflow_run(self, run: dict[str, Any]) -> dict[str, Any]:
        """Create one workflow run per approved Blueprint version, idempotently."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            existing = cursor.execute(
                """SELECT * FROM canonical_workflow_runs
                   WHERE project_id = ? AND scene_id = ? AND blueprint_version_id = ?""",
                (run["project_id"], run["scene_id"], run["blueprint_version_id"]),
            ).fetchone()
            if existing is not None:
                conn.commit()
                return self._canonical_workflow_row_to_dict(existing)
            cursor.execute(
                """
                INSERT INTO canonical_workflow_runs (
                    run_id, project_id, script_id, scene_id, blueprint_id,
                    blueprint_version_id, status, context_hash, data_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["run_id"],
                    run["project_id"],
                    run["script_id"],
                    run["scene_id"],
                    run["blueprint_id"],
                    run["blueprint_version_id"],
                    run["status"],
                    run["context_hash"],
                    json.dumps(run.get("data") or {}, sort_keys=True),
                    run.get("created_at") or now,
                    run.get("updated_at") or now,
                ),
            )
            created = cursor.execute(
                "SELECT * FROM canonical_workflow_runs WHERE run_id = ?",
                (run["run_id"],),
            ).fetchone()
            conn.commit()
        return self._canonical_workflow_row_to_dict(created)

    def get_canonical_workflow_run(self, run_id: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM canonical_workflow_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._canonical_workflow_row_to_dict(row) if row else None

    def get_canonical_workflow_run_for_source(
        self,
        project_id: str,
        scene_id: str,
        blueprint_version_id: str,
    ) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM canonical_workflow_runs
                   WHERE project_id = ? AND scene_id = ? AND blueprint_version_id = ?""",
                (project_id, scene_id, blueprint_version_id),
            ).fetchone()
        return self._canonical_workflow_row_to_dict(row) if row else None

    def list_canonical_workflow_runs(
        self,
        project_id: str,
        scene_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            if scene_id:
                rows = conn.execute(
                    """SELECT * FROM canonical_workflow_runs
                       WHERE project_id = ? AND scene_id = ?
                       ORDER BY created_at, run_id""",
                    (project_id, scene_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM canonical_workflow_runs
                       WHERE project_id = ? ORDER BY created_at, run_id""",
                    (project_id,),
                ).fetchall()
        return [self._canonical_workflow_row_to_dict(row) for row in rows]

    def commit_canonical_workflow_transition(
        self,
        run: dict[str, Any],
        transition: dict[str, Any],
        *,
        expected_status: str,
    ) -> dict[str, Any]:
        """Atomically persist state before exposing its transition event."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            current = cursor.execute(
                "SELECT * FROM canonical_workflow_runs WHERE run_id = ?",
                (run["run_id"],),
            ).fetchone()
            if current is None:
                conn.rollback()
                raise ValueError("Canonical workflow run not found")
            duplicate = cursor.execute(
                """SELECT transition_id FROM canonical_workflow_transitions
                   WHERE run_id = ? AND idempotency_key = ?""",
                (run["run_id"], transition["idempotency_key"]),
            ).fetchone()
            if duplicate is not None:
                conn.commit()
                return self._canonical_workflow_row_to_dict(current)
            if current["status"] != expected_status:
                conn.rollback()
                raise ValueError(
                    f"Canonical workflow state changed: expected {expected_status}, found {current['status']}"
                )
            cursor.execute(
                """UPDATE canonical_workflow_runs
                   SET status = ?, context_hash = ?, data_json = ?, updated_at = ?
                   WHERE run_id = ? AND status = ?""",
                (
                    run["status"],
                    run["context_hash"],
                    json.dumps(run.get("data") or {}, sort_keys=True),
                    run.get("updated_at") or now,
                    run["run_id"],
                    expected_status,
                ),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                raise ValueError("Canonical workflow transition lost an ownership race")
            cursor.execute(
                """
                INSERT INTO canonical_workflow_transitions (
                    transition_id, run_id, idempotency_key, from_status,
                    to_status, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition["transition_id"],
                    run["run_id"],
                    transition["idempotency_key"],
                    transition["from_status"],
                    transition["to_status"],
                    transition["event_type"],
                    json.dumps(transition.get("payload") or {}, sort_keys=True),
                    transition.get("created_at") or now,
                ),
            )
            updated = cursor.execute(
                "SELECT * FROM canonical_workflow_runs WHERE run_id = ?",
                (run["run_id"],),
            ).fetchone()
            conn.commit()
        return self._canonical_workflow_row_to_dict(updated)

    def list_canonical_workflow_transitions(self, run_id: str) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM canonical_workflow_transitions
                   WHERE run_id = ? ORDER BY created_at, transition_id""",
                (run_id,),
            ).fetchall()
        return [self._canonical_workflow_transition_row_to_dict(row) for row in rows]

    def _canonical_workflow_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["data"] = json.loads(data.pop("data_json") or "{}")
        return data

    def _canonical_workflow_transition_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
        return data

    def save_emotion_analysis_result(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().isoformat()
        created_at = str(record.get("created_at") or now)
        updated_at = str(record.get("updated_at") or now)

        def _write() -> None:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO emotion_analysis_results (
                        analysis_id, project_id, scene_id, context_hash, provider,
                        model, analysis_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, scene_id, context_hash) DO UPDATE SET
                        provider = excluded.provider,
                        model = excluded.model,
                        analysis_json = excluded.analysis_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record["analysis_id"],
                        record["project_id"],
                        record["scene_id"],
                        record["context_hash"],
                        record["provider"],
                        record["model"],
                        json.dumps(record["analysis"], ensure_ascii=False),
                        created_at,
                        updated_at,
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_emotion_analysis_result", _write)
        saved = self.get_emotion_analysis_result(
            record["project_id"],
            record["scene_id"],
            record["context_hash"],
        )
        if saved is None:
            raise RuntimeError("Emotion analysis result was not persisted")
        return saved

    def get_emotion_analysis_result(
        self,
        project_id: str,
        scene_id: str,
        context_hash: str | None = None,
    ) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            if context_hash:
                row = conn.execute(
                    """
                    SELECT * FROM emotion_analysis_results
                    WHERE project_id = ? AND scene_id = ? AND context_hash = ?
                    LIMIT 1
                    """,
                    (project_id, scene_id, context_hash),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM emotion_analysis_results
                    WHERE project_id = ? AND scene_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (project_id, scene_id),
                ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["analysis"] = json.loads(result.pop("analysis_json") or "{}")
        return result

    def get_scene_previs_seed(self, project_id: str, scene_id: str) -> Optional[int]:
        """
        Get the previs seed for a scene (returns seed if it exists, None otherwise).

        Args:
            project_id: Project identifier
            scene_id: Scene identifier

        Returns:
            Seed integer if exists, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT previs_seed FROM previs_images
                WHERE project_id = ? AND scene_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id, scene_id),
            )
            row = cursor.fetchone()
            return row["previs_seed"] if row else None

    def update_previs_seed_lock(self, project_id: str, scene_id: str, locked: bool) -> bool:
        """
        Update the seed_locked status for a scene's previs image.

        Args:
            project_id: Project identifier
            scene_id: Scene identifier
            locked: Whether to lock the seed

        Returns:
            True if updated successfully
        """
        from datetime import datetime

        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute(
                """
                UPDATE previs_images
                SET seed_locked = ?, updated_at = ?
                WHERE project_id = ? AND scene_id = ?
                """,
                (1 if locked else 0, now, project_id, scene_id),
            )

            conn.commit()
            return cursor.rowcount > 0
    # STUDY MEMORIES (Active Memory persistence)
    # ========================================================================

    def save_study_memory(
        self,
        project_id: str,
        category: str,
        content: str,
        source_reference: str | None = None,
    ) -> dict:
        """Upsert a study memory entry. On duplicate (same project + category + content),
        update the existing row rather than inserting a new one."""
        now = datetime.now().isoformat()
        memory_id = f"sm_{uuid4().hex[:12]}"

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Check for existing entry with same project + category + content
                cursor.execute(
                    """SELECT id FROM study_memories
                       WHERE project_id = ? AND category = ? AND content = ?""",
                    (project_id, category, content),
                )
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        """UPDATE study_memories
                           SET updated_at = ?, source_reference = COALESCE(?, source_reference)
                           WHERE id = ?""",
                        (now, source_reference, existing["id"]),
                    )
                    conn.commit()
                    return {
                        "id": existing["id"],
                        "project_id": project_id,
                        "category": category,
                        "content": content,
                        "source_reference": source_reference,
                        "created_at": None,
                        "updated_at": now,
                    }
                cursor.execute(
                    """INSERT INTO study_memories (id, project_id, category, content, source_reference, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (memory_id, project_id, category, content, source_reference, now, now),
                )
                conn.commit()
                return {
                    "id": memory_id,
                    "project_id": project_id,
                    "category": category,
                    "content": content,
                    "source_reference": source_reference,
                    "created_at": now,
                    "updated_at": now,
                }

        return self._execute_write_with_retry("save_study_memory", _write)

    def get_study_memories(self, project_id: str) -> list[dict]:
        """Get all study memories for a project, ordered by category."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, project_id, category, content, source_reference, created_at, updated_at
                   FROM study_memories
                   WHERE project_id = ?
                   ORDER BY category, created_at ASC""",
                (project_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_study_memories_by_category(self, project_id: str, category: str) -> list[dict]:
        """Get study memories for a project filtered by category."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, project_id, category, content, source_reference, created_at, updated_at
                   FROM study_memories
                   WHERE project_id = ? AND category = ?
                   ORDER BY created_at ASC""",
                (project_id, category),
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_study_memory(self, memory_id: str) -> bool:
        """Delete a single study memory entry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM study_memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_study_memories_for_project(self, project_id: str) -> int:
        """Delete all study memories for a project. Returns count deleted."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM study_memories WHERE project_id = ?", (project_id,))
            conn.commit()
            return cursor.rowcount


    # ------------------------------------------------------------------
    # Character Descriptions
    # ------------------------------------------------------------------

    def save_character(self, project_id: str, name: str, data: dict) -> dict:
        """Upsert a character record. Matches on (project_id, name).

        Handles the Phase 1 dual-read columns (appearance_core, appearance_notes,
        description_status) introduced by migration #27. These columns are
        optional — callers that do not provide them preserve existing values
        (on update) or receive schema defaults (on insert).
        """
        now = datetime.now().isoformat()
        _new_id = data.get("id") or f"chr_{uuid4().hex[:12]}"

        def _write():
            nonlocal _new_id
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id FROM characters WHERE project_id = ? AND name = ?""",
                    (project_id, name),
                )
                existing = cursor.fetchone()
                if existing:
                    char_id = existing["id"]
                    cursor.execute(
                        """UPDATE characters SET age=?, look=?, energy=?, core_wound=?,
                           core_desire=?, relationship_notes=?, visual_prompt_summary=?,
                           appearance_core=COALESCE(?, appearance_core),
                           appearance_notes=COALESCE(?, appearance_notes),
                           description_status=COALESCE(?, description_status),
                           elevenlabs_voice_id=COALESCE(?, elevenlabs_voice_id),
                           elevenlabs_voice_name=COALESCE(?, elevenlabs_voice_name),
                           voice_provider=COALESCE(?, voice_provider),
                           voice_id=COALESCE(?, voice_id),
                           voice_name=COALESCE(?, voice_name),
                           voice_source_type=COALESCE(?, voice_source_type),
                           voice_style_prompt=COALESCE(?, voice_style_prompt),
                           identity_core_json=COALESCE(?, identity_core_json),
                           default_appearance_json=COALESCE(?, default_appearance_json),
                           continuity_state_json=COALESCE(?, continuity_state_json),
                           appearance_version_history_json=COALESCE(?, appearance_version_history_json),
                           updated_at=?
                           WHERE id=?""",
                        (
                            data.get("age"),
                            data.get("look"),
                            data.get("energy"),
                            data.get("core_wound"),
                            data.get("core_desire"),
                            data.get("relationship_notes"),
                            data.get("visual_prompt_summary"),
                            data.get("appearance_core"),
                            data.get("appearance_notes"),
                            data.get("description_status"),
                            data.get("elevenlabs_voice_id"),
                            data.get("elevenlabs_voice_name"),
                            data.get("voice_provider"),
                            data.get("voice_id"),
                            data.get("voice_name"),
                            data.get("voice_source_type"),
                            data.get("voice_style_prompt"),
                            data.get("identity_core_json"),
                            data.get("default_appearance_json"),
                            data.get("continuity_state_json"),
                            data.get("appearance_version_history_json"),
                            now,
                            char_id,
                        ),
                    )
                else:
                    char_id = _new_id
                    cursor.execute(
                        """INSERT INTO characters (id, project_id, name, age, look, energy,
                           core_wound, core_desire, relationship_notes, visual_prompt_summary,
                           appearance_core, appearance_notes, description_status,
                           elevenlabs_voice_id, elevenlabs_voice_name,
                           voice_provider, voice_id, voice_name, voice_source_type, voice_style_prompt,
                           identity_core_json, default_appearance_json, continuity_state_json,
                           appearance_version_history_json,
                           created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            char_id,
                            project_id,
                            name,
                            data.get("age"),
                            data.get("look"),
                            data.get("energy"),
                            data.get("core_wound"),
                            data.get("core_desire"),
                            data.get("relationship_notes"),
                            data.get("visual_prompt_summary"),
                            data.get("appearance_core"),
                            data.get("appearance_notes"),
                            data.get("description_status") or "legacy",
                            data.get("elevenlabs_voice_id"),
                            data.get("elevenlabs_voice_name"),
                            data.get("voice_provider"),
                            data.get("voice_id"),
                            data.get("voice_name"),
                            data.get("voice_source_type"),
                            data.get("voice_style_prompt"),
                            data.get("identity_core_json"),
                            data.get("default_appearance_json"),
                            data.get("continuity_state_json"),
                            data.get("appearance_version_history_json"),
                            now,
                            now,
                        ),
                    )
                conn.commit()
                cursor.execute("SELECT * FROM characters WHERE id = ? AND project_id = ?", (char_id, project_id))
                return dict(cursor.fetchone())

        return self._execute_write_with_retry("save_character", _write)

    def patch_character_revision(
        self, project_id: str, character_id: str, updates: dict, expected_updated_at: str,
    ) -> dict | None:
        """Atomically update scoped character columns if the caller's revision is current."""
        columns = {
            "name", "age", "look", "energy", "core_wound", "core_desire", "relationship_notes",
            "visual_prompt_summary", "appearance_core", "appearance_notes", "description_status",
            "identity_core_json", "default_appearance_json", "continuity_state_json",
            "appearance_version_history_json", "voice_provider", "voice_id", "voice_name",
            "voice_source_type", "voice_style_prompt", "elevenlabs_voice_id", "elevenlabs_voice_name",
        }
        if not updates or not set(updates).issubset(columns):
            raise ValueError("Unsupported character columns")
        assignments = ", ".join(f"{column} = ?" for column in updates)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.execute(
                    f"UPDATE characters SET {assignments}, updated_at = ? "
                    "WHERE id = ? AND project_id = ? AND updated_at = ?",
                    (*updates.values(), datetime.now().isoformat(), character_id, project_id, expected_updated_at),
                )
                if cursor.rowcount != 1:
                    return None
                row = conn.execute("SELECT * FROM characters WHERE id = ? AND project_id = ?", (character_id, project_id)).fetchone()
                conn.commit()
                return dict(row)

        return self._execute_write_with_retry("patch_character_revision", _write)

    # ── Character Stagings (Phase 1: scene-aware character staging) ──────────

    def get_character_staging(
        self,
        character_id: str,
        scene_id: str,
        shot_id: str | None,
    ) -> dict | None:
        """Look up the most specific character staging record.

        Resolution order (§4.1):
        1. Exact (character_id, scene_id, shot_id)
        2. Scene-level (character_id, scene_id, NULL shot_id)

        Returns the staging dict or None when no staging exists (legacy path).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if shot_id:
                cursor.execute(
                    """SELECT * FROM character_stagings
                       WHERE character_id = ? AND scene_id = ? AND shot_id = ?""",
                    (character_id, scene_id, shot_id),
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
            cursor.execute(
                """SELECT * FROM character_stagings
                   WHERE character_id = ? AND scene_id = ? AND shot_id IS NULL""",
                (character_id, scene_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_character_staging(self, staging: dict) -> dict:
        """Upsert a character staging record.

        Matches on the UNIQUE(character_id, scene_id, shot_id) constraint.
        """
        now = datetime.now().isoformat()
        character_id = staging["character_id"]
        scene_id = staging["scene_id"]
        shot_id = staging.get("shot_id")
        staging_prompt = staging["staging_prompt"]
        appearance_override = staging.get("appearance_override")
        source = staging.get("source") or "manual"
        staging_id = staging.get("id") or f"cstg_{uuid4().hex[:12]}"

        def _write():
            nonlocal staging_id
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT id FROM character_stagings
                       WHERE character_id = ? AND scene_id = ?
                         AND (shot_id IS ? OR shot_id = ?)""",
                    (character_id, scene_id, shot_id, shot_id),
                )
                existing = cursor.fetchone()
                if existing:
                    staging_id = existing["id"]
                    cursor.execute(
                        """UPDATE character_stagings
                           SET staging_prompt=?, appearance_override=?, source=?, updated_at=?
                           WHERE id=?""",
                        (staging_prompt, appearance_override, source, now, staging_id),
                    )
                else:
                    cursor.execute(
                        """INSERT INTO character_stagings
                           (id, character_id, scene_id, shot_id, staging_prompt,
                            appearance_override, source, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            staging_id,
                            character_id,
                            scene_id,
                            shot_id,
                            staging_prompt,
                            appearance_override,
                            source,
                            now,
                            now,
                        ),
                    )
                conn.commit()
                cursor.execute("SELECT * FROM character_stagings WHERE id = ?", (staging_id,))
                return dict(cursor.fetchone())

        return self._execute_write_with_retry("save_character_staging", _write)

    def get_characters(self, project_id: str) -> list[dict]:
        """Get all character records for a project."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM characters WHERE project_id = ? ORDER BY name ASC""",
                (project_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_character(self, character_id: str, project_id: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""SELECT * FROM characters WHERE id = ? AND project_id = ?""", (character_id, project_id))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_character_by_name(self, project_id: str, name: str) -> dict | None:
        """Get a character by project_id and name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM characters WHERE project_id = ? AND name = ?""",
                (project_id, name),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_character(self, character_id: str, project_id: str) -> bool:
        """Delete a character record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM characters WHERE id = ? AND project_id = ?", (character_id, project_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_character_voice_by_name(self, project_id: str, name: str) -> str | None:
        """Look up a character's assigned ElevenLabs voice ID by project + name.

        Returns the ``elevenlabs_voice_id`` value or ``None`` when no
        assignment exists (or the character is not found).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT elevenlabs_voice_id FROM characters
                   WHERE project_id = ? AND name = ?
                   AND elevenlabs_voice_id IS NOT NULL
                   AND elevenlabs_voice_id != ''""",
                (project_id, name),
            )
            row = cursor.fetchone()
            return row["elevenlabs_voice_id"] if row else None

    def get_character_voice_casting_by_name(
        self,
        project_id: str,
        name: str,
        provider: str | None = None,
    ) -> dict | None:
        """Look up a provider-aware character voice casting by project + name."""
        clean_provider = (provider or "").strip().lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """SELECT voice_provider, voice_id, voice_name, voice_source_type, voice_style_prompt
                       FROM characters
                       WHERE project_id = ? AND name = ?
                       AND voice_id IS NOT NULL
                       AND voice_id != ''"""
            params: list[Any] = [project_id, name]
            if clean_provider:
                query += " AND LOWER(COALESCE(voice_provider, '')) = ?"
                params.append(clean_provider)
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def set_character_voice(
        self,
        character_id: str,
        project_id: str,
        voice_id: str,
        voice_name: str | None = None,
    ) -> dict | None:
        """Set the ElevenLabs voice assignment for a character.

        Pass ``voice_id=""`` to clear the assignment.
        """
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE characters
                   SET elevenlabs_voice_id=?, elevenlabs_voice_name=?,
                       updated_at=?
                   WHERE id=? AND project_id=?""",
                (voice_id or None, voice_name or None, now, character_id, project_id),
            )
            if cursor.rowcount == 0:
                conn.commit()
                return None
            conn.commit()
            cursor.execute(
                "SELECT * FROM characters WHERE id = ? AND project_id = ?",
                (character_id, project_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def set_character_voice_casting(
        self,
        character_id: str,
        project_id: str,
        provider: str,
        voice_id: str,
        voice_name: str | None = None,
        source_type: str | None = None,
        style_prompt: str | None = None,
    ) -> dict | None:
        """Set provider-aware project Casting voice assignment for a character."""
        now = datetime.now().isoformat()
        clean_provider = (provider or "").strip().lower() or None
        clean_voice_id = (voice_id or "").strip() or None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE characters
                   SET voice_provider=?, voice_id=?, voice_name=?,
                       voice_source_type=?, voice_style_prompt=?, updated_at=?
                   WHERE id=? AND project_id=?""",
                (
                    clean_provider,
                    clean_voice_id,
                    voice_name or None,
                    source_type or None,
                    style_prompt or None,
                    now,
                    character_id,
                    project_id,
                ),
            )
            if cursor.rowcount == 0:
                conn.commit()
                return None
            conn.commit()
            cursor.execute(
                "SELECT * FROM characters WHERE id = ? AND project_id = ?",
                (character_id, project_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def seed_demo_characters(self, project_id: str) -> int:
        """Seed character descriptions for the demo project. Idempotent."""
        existing = self.get_characters(project_id)
        if existing:
            return 0

        characters = [
            {
                "name": "MARA",
                "age": "32",
                "look": "Dark hair usually tied back. Tired eyes that still notice everything. Weathered hands. Practical clothing: old jackets, worn boots, faded sweaters. Nothing flashy. Carries herself like someone who learned early that life does not wait.",
                "energy": "Quiet intensity. Listens more than she talks. Sarcastic edge when uncomfortable, deep tenderness underneath.",
                "core_wound": "Her father disappeared and left behind a question instead of an answer.",
                "core_desire": "",
                "relationship_notes": "",
                "visual_prompt_summary": "32-year-old woman, dark hair tied back, tired knowing eyes, weathered hands, worn practical clothing, old jacket and boots, quiet intensity, coastal working class aesthetic",
            },
            {
                "name": "ELI",
                "age": "67",
                "look": "Lifelong fisherman. Gray beard. Sun-damaged skin. Heavy work jacket. Old boots. Looks like he belongs in an old photograph.",
                "energy": "Ancient calm. Has accepted nature does not owe humans anything. Wise but still gets angry, tired, worried.",
                "core_wound": "",
                "core_desire": "",
                "relationship_notes": "",
                "visual_prompt_summary": "67-year-old fisherman, gray beard, sun-weathered skin, heavy work jacket, old worn boots, ancient calm presence, looks like an old photograph",
            },
            {
                "name": "CHILD",
                "age": "7",
                "look": "Messy hair. Always barefoot or wearing worn shoes. Curious eyes.",
                "energy": "Pure hope. Sees beginnings where Mara sees endings.",
                "core_wound": "",
                "core_desire": "",
                "relationship_notes": "",
                "visual_prompt_summary": "7-year-old child, messy hair, barefoot or worn shoes, wide curious eyes, embodies hope and wonder",
            },
            {
                "name": "REPRESENTATIVE",
                "age": "41",
                "look": "Clean, professional, composed. Neutral clothing. Looks like she belongs in a boardroom. Slightly uncomfortable outside her environment.",
                "energy": "Controlled empathy. Not a villain. Genuinely believes she is helping. That makes her complicated.",
                "core_wound": "",
                "core_desire": "",
                "relationship_notes": "",
                "visual_prompt_summary": "41-year-old woman, professional composed appearance, neutral business clothing, controlled expression, slightly out of place in coastal setting",
            },
        ]

        count = 0
        for char_data in characters:
            self.save_character(project_id, char_data["name"], char_data)
            count += 1
        return count

    def detect_unknown_characters(self, project_id: str, scene_characters: list[str]) -> list[str]:
        """Given a list of character names from scenes, return those not yet in the DB."""
        known = {c["name"].upper() for c in self.get_characters(project_id)}
        return [c for c in scene_characters if c.upper() not in known]

    # ── Render Attempts Management ────────────────────────────────────────────

    def list_render_attempts(
        self,
        project_id: Optional[str] = None,
        shot_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        List render attempts, optionally filtered by project/shot.

        Args:
            project_id: Optional project ID filter (ignored if column doesn't exist)
            shot_id: Optional shot ID filter
            limit: Maximum number of attempts to return

        Returns:
            List of render attempt dicts with parsed JSON fields
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check if project_id column exists
            cursor.execute("PRAGMA table_info(render_attempts)")
            columns_info = cursor.fetchall()
            has_project_id = any(col[1] == "project_id" for col in columns_info)

            query = "SELECT * FROM render_attempts WHERE 1=1"
            params = []

            if project_id and has_project_id:
                query += " AND project_id = ?"
                params.append(project_id)

            if shot_id:
                query += " AND shot_id = ?"
                params.append(shot_id)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]

            attempts = []
            for row in cursor.fetchall():
                attempt = dict(zip(columns, row))

                # Parse JSON fields
                if attempt.get("score_json"):
                    try:
                        attempt["score_json"] = json.loads(attempt["score_json"])
                    except Exception:
                        pass

                if attempt.get("diff_json"):
                    try:
                        attempt["diff_json"] = json.loads(attempt["diff_json"])
                    except Exception:
                        pass

                # Normalize field name
                if "attempt_n" in attempt:
                    attempt["attempt_number"] = attempt["attempt_n"]

                attempts.append(attempt)

            return attempts

    def get_render_attempt(self, attempt_id: str) -> Optional[dict]:
        """Get a single render attempt by ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM render_attempts WHERE id = ?", (attempt_id,))
            row = cursor.fetchone()

            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            attempt = dict(zip(columns, row))

            # Parse JSON fields
            if attempt.get("score_json"):
                try:
                    attempt["score_json"] = json.loads(attempt["score_json"])
                except Exception:
                    pass

            if attempt.get("diff_json"):
                try:
                    attempt["diff_json"] = json.loads(attempt["diff_json"])
                except Exception:
                    pass

            # Normalize field name
            if "attempt_n" in attempt:
                attempt["attempt_number"] = attempt["attempt_n"]

            return attempt

    # ── Standing Corrections ──────────────────────────────────────────────────

    def list_standing_corrections(
        self,
        project_id: str,
        slot: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List standing corrections for a project, optionally filtered by slot/status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM standing_corrections WHERE project_id = ?"
            params: list = [project_id]

            if slot:
                query += " AND slot = ?"
                params.append(slot)
            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY confidence DESC, hits DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]

            corrections = []
            for row in cursor.fetchall():
                corr = dict(zip(columns, row))
                if corr.get("trigger_json"):
                    try:
                        corr["trigger_json"] = json.loads(corr["trigger_json"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                corrections.append(corr)

            return corrections

    def get_standing_correction(self, correction_id: str) -> dict | None:
        """Get a single standing correction by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM standing_corrections WHERE correction_id = ?",
                (correction_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            corr = dict(zip(columns, row))
            if corr.get("trigger_json"):
                try:
                    corr["trigger_json"] = json.loads(corr["trigger_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            return corr

    def save_standing_correction(self, correction: dict) -> bool:
        """Insert or update a standing correction.

        This is the ONLY storage path for creating standing correction rows.
        The service layer must enforce the propose-then-confirm gate — no
        service method may call this without an explicit confirm action.
        """
        correction_id = correction.get("correction_id", "")
        if not correction_id:
            return False

        trigger_json = correction.get("trigger_json", {})
        if isinstance(trigger_json, dict):
            trigger_json = json.dumps(trigger_json)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO standing_corrections
                    (correction_id, project_id, slot, trigger_json, injection_text,
                     confidence, hits, misses, last_applied, status, superseded_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        correction_id,
                        correction.get("project_id", ""),
                        correction.get("slot", ""),
                        trigger_json,
                        correction.get("injection_text", ""),
                        correction.get("confidence", 0.5),
                        correction.get("hits", 0),
                        correction.get("misses", 0),
                        correction.get("last_applied"),
                        correction.get("status", "active"),
                        correction.get("superseded_by"),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_standing_correction", _write)
        return True

    # ── Reference Assets ──────────────────────────────────────────────────────

    def save_reference_asset(self, asset: dict) -> bool:
        """Insert or update a confirmed reference asset.

        This is the ONLY storage path for creating reference_asset rows.
        The route layer must enforce the propose-then-confirm gate — no
        code path may call this without an explicit confirm action.
        """
        ref_id = asset.get("ref_id", "")
        if not ref_id:
            return False

        embedding = asset.get("embedding")
        if isinstance(embedding, list):
            embedding = json.dumps(embedding)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO reference_assets
                    (ref_id, project_id, kind, image_url, embedding,
                     source_shot_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ref_id,
                        asset.get("project_id", ""),
                        asset.get("kind", "character_full"),
                        asset.get("image_url", ""),
                        embedding,
                        asset.get("source_shot_id"),
                        asset.get("created_at"),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_reference_asset", _write)
        return True

    def list_reference_assets(
        self,
        project_id: str,
        kind: str | None = None,
        source_shot_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List confirmed reference assets for a project, optionally filtered."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM reference_assets WHERE project_id = ?"
            params: list = [project_id]

            if kind:
                query += " AND kind = ?"
                params.append(kind)
            if source_shot_id:
                query += " AND source_shot_id = ?"
                params.append(source_shot_id)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]

            assets = []
            for row in cursor.fetchall():
                asset = dict(zip(columns, row))
                if asset.get("embedding"):
                    try:
                        asset["embedding"] = json.loads(asset["embedding"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                assets.append(asset)

            return assets

    def get_reference_asset(self, ref_id: str) -> dict | None:
        """Get a single reference asset by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM reference_assets WHERE ref_id = ?",
                (ref_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            asset = dict(zip(columns, row))
            if asset.get("embedding"):
                try:
                    asset["embedding"] = json.loads(asset["embedding"])
                except (json.JSONDecodeError, TypeError):
                    pass
            return asset

    # ── Character Reference Locks ───────────────────────────────────────────

    def save_character_reference_lock(self, lock: dict) -> dict:
        """Persist the locked visual reference for a project character."""
        now = datetime.now().isoformat()
        lock_id = lock.get("lock_id") or f"charlock_{uuid4().hex[:12]}"

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO character_reference_locks
                    (lock_id, project_id, character_id, character_name,
                     source_shot_id, image_url, lock_status, provider,
                     capture_method, created_at, updated_at, reference_role,
                     reliability, source_job_id, source_status, review_status,
                     trace_notes, look_id, frame_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lock_id,
                        lock.get("project_id", ""),
                        lock.get("character_id", ""),
                        lock.get("character_name", ""),
                        lock.get("source_shot_id", ""),
                        lock.get("image_url", ""),
                        lock.get("lock_status") or "locked",
                        lock.get("provider", ""),
                        lock.get("capture_method") or "thumbnail",
                        lock.get("created_at") or now,
                        lock.get("updated_at") or now,
                        lock.get("reference_role") or "general",
                        lock.get("reliability") or "medium",
                        lock.get("source_job_id", ""),
                        lock.get("source_status") or (
                            "approved" if (lock.get("lock_status") or "locked") == "locked" else "provisional"
                        ),
                        lock.get("review_status") or "unreviewed",
                        lock.get("trace_notes", ""),
                        lock.get("look_id") or "default",
                        float(lock.get("frame_score") or 0.0),
                    ),
                )
                conn.commit()
                cursor.execute(
                    "SELECT * FROM character_reference_locks WHERE lock_id = ?",
                    (lock_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else {}

        return self._execute_write_with_retry("save_character_reference_lock", _write)

    def get_character_reference_lock(
        self,
        project_id: str,
        character_id: str,
        lock_status: str = "locked",
        reference_role: str | None = None,
        look_id: str | None = None,
    ) -> dict | None:
        """Return a character's active visual reference lock within a project.

        A character can now hold one locked reference per role, so `reference_role`
        narrows to a specific one. Omitting it keeps the original behaviour of
        returning the most recent lock of any role.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = (
                "SELECT * FROM character_reference_locks "
                "WHERE project_id = ? AND character_id = ? AND lock_status = ?"
            )
            params: list = [project_id, character_id, lock_status]
            if reference_role:
                query += " AND reference_role = ?"
                params.append(reference_role)
            if look_id:
                query += " AND look_id = ?"
                params.append(look_id)
            query += " ORDER BY created_at DESC LIMIT 1"
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_character_reference_locks_for_character(
        self,
        project_id: str,
        character_id: str,
        lock_status: str = "locked",
        limit: int = 9,
        look_id: str | None = None,
    ) -> list[dict]:
        """Return every locked reference held for one character, newest first.

        happyhorse-1.1-r2v accepts up to 9 reference images, so this is the
        multi-view read path that replaces fetching a single lock per character.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM character_reference_locks
                WHERE project_id = ? AND character_id = ? AND lock_status = ?
                  AND (? IS NULL OR look_id = ?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, character_id, lock_status, look_id, look_id, max(1, limit)),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_character_reference_locks(
        self,
        project_id: str,
        character_ids: list[str] | None = None,
        lock_status: str | None = "locked",
        limit: int = 50,
    ) -> list[dict]:
        """List character visual reference locks with project isolation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = (
                "SELECT * FROM character_reference_locks "
                "WHERE project_id = ?"
            )
            params: list = [project_id]
            if lock_status:
                query += " AND lock_status = ?"
                params.append(lock_status)
            clean_ids = [
                str(character_id).strip()
                for character_id in (character_ids or [])
                if str(character_id).strip()
            ]
            if clean_ids:
                placeholders = ",".join("?" for _ in clean_ids)
                query += f" AND character_id IN ({placeholders})"
                params.extend(clean_ids)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    # Colorist Intelligence
    # ------------------------------------------------------------------ #

    def _save_color_payload(
        self,
        table: str,
        id_column: str,
        item: Any,
        columns: dict[str, Any],
        operation_name: str,
    ) -> Any:
        data = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        payload = self._json_dumps(data)
        clean_columns = {key: value for key, value in columns.items()}
        names = [id_column, *clean_columns.keys(), "payload_json"]
        placeholders = ", ".join("?" for _ in names)

        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"INSERT OR REPLACE INTO {table} ({', '.join(names)}) VALUES ({placeholders})",
                    (data[id_column], *clean_columns.values(), payload),
                )
                conn.commit()

        self._execute_write_with_retry(operation_name, _write)
        return item

    def _get_color_payload(self, table: str, id_column: str, item_id: str, model: Any) -> Any | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT payload_json FROM {table} WHERE {id_column} = ?", (item_id,))
            row = cursor.fetchone()
            return model(**self._json_loads(row["payload_json"], {})) if row else None

    def _list_color_payloads(
        self,
        table: str,
        model: Any,
        project_id: str,
        filters: dict[str, Any] | None = None,
        order_column: str = "created_at",
        limit: int = 50,
    ) -> list[Any]:
        filters = filters or {}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = f"SELECT payload_json FROM {table} WHERE project_id = ?"
            params: list[Any] = [project_id]
            for column, value in filters.items():
                if value is None or value == "":
                    continue
                query += f" AND {column} = ?"
                params.append(1 if isinstance(value, bool) else value)
            query += f" ORDER BY {order_column} DESC LIMIT ?"
            params.append(max(1, min(int(limit), 500)))
            cursor.execute(query, params)
            return [model(**self._json_loads(row["payload_json"], {})) for row in cursor.fetchall()]

    def save_color_look_bible(self, look_bible: Any) -> Any:
        data = look_bible.model_dump(mode="json") if hasattr(look_bible, "model_dump") else dict(look_bible)
        return self._save_color_payload(
            "color_look_bibles",
            "look_bible_id",
            look_bible,
            {
                "project_id": data["project_id"],
                "scope": data.get("scope") or "project",
                "act_id": data.get("act_id"),
                "sequence_id": data.get("sequence_id"),
                "status": data.get("status") or "active",
                "source_fingerprint": data.get("source_fingerprint") or "",
                "look_fingerprint": data.get("look_fingerprint") or "",
                "created_at": data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                "updated_at": data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
            },
            "save_color_look_bible",
        )

    def get_color_look_bible(self, look_bible_id: str) -> Any | None:
        from app.models.colorist import ColorLookBible

        return self._get_color_payload("color_look_bibles", "look_bible_id", look_bible_id, ColorLookBible)

    def list_color_look_bibles(self, project_id: str, scope: str | None = None, sequence_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Any]:
        from app.models.colorist import ColorLookBible

        return self._list_color_payloads(
            "color_look_bibles",
            ColorLookBible,
            project_id,
            {"scope": scope, "sequence_id": sequence_id, "status": status},
            limit=limit,
        )

    def mark_color_look_bible_stale(self, look_bible_id: str) -> bool:
        current = self.get_color_look_bible(look_bible_id)
        if current is None:
            return False
        data = current.model_dump(mode="json")
        data["status"] = "stale"
        data["updated_at"] = datetime.utcnow().isoformat() + "Z"
        from app.models.colorist import ColorLookBible

        self.save_color_look_bible(ColorLookBible(**data))
        return True

    def save_colorist_look_plan(self, plan: Any) -> Any:
        data = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else dict(plan)
        return self._save_color_payload(
            "colorist_look_plans",
            "plan_id",
            plan,
            {
                "project_id": data["project_id"],
                "look_bible_id": data.get("look_bible_id"),
                "scene_id": data.get("scene_id"),
                "shot_id": data.get("shot_id"),
                "take_id": data.get("take_id"),
                "asset_id": data.get("asset_id"),
                "render_job_id": data.get("render_job_id"),
                "scope": data.get("scope") or "scene",
                "status": data.get("status") or "active",
                "source_fingerprint": data.get("source_fingerprint") or "",
                "look_fingerprint": data.get("look_fingerprint") or "",
                "stale": 1 if data.get("stale", False) else 0,
                "created_at": data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                "updated_at": data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
            },
            "save_colorist_look_plan",
        )

    def get_colorist_look_plan(self, plan_id: str) -> Any | None:
        from app.models.colorist import ColoristLookPlan

        return self._get_color_payload("colorist_look_plans", "plan_id", plan_id, ColoristLookPlan)

    def list_colorist_look_plans(self, project_id: str, look_bible_id: str | None = None, scene_id: str | None = None, shot_id: str | None = None, asset_id: str | None = None, render_job_id: str | None = None, status: str | None = None, stale: bool | None = None, limit: int = 50) -> list[Any]:
        from app.models.colorist import ColoristLookPlan

        return self._list_color_payloads(
            "colorist_look_plans",
            ColoristLookPlan,
            project_id,
            {
                "look_bible_id": look_bible_id,
                "scene_id": scene_id,
                "shot_id": shot_id,
                "asset_id": asset_id,
                "render_job_id": render_job_id,
                "status": status,
                "stale": stale,
            },
            limit=limit,
        )

    def mark_colorist_look_plan_stale(self, plan_id: str, reason: str = "") -> bool:
        current = self.get_colorist_look_plan(plan_id)
        if current is None:
            return False
        data = current.model_dump(mode="json")
        data["status"] = "stale"
        data["stale"] = True
        data["stale_reason"] = reason or "Source inputs changed."
        data["updated_at"] = datetime.utcnow().isoformat() + "Z"
        from app.models.colorist import ColoristLookPlan

        self.save_colorist_look_plan(ColoristLookPlan(**data))
        return True

    def save_color_palette_continuity_record(self, record: Any) -> Any:
        data = record.model_dump(mode="json") if hasattr(record, "model_dump") else dict(record)
        return self._save_color_payload(
            "color_palette_continuity_records",
            "palette_record_id",
            record,
            {
                "project_id": data["project_id"],
                "scope": data.get("scope") or "project",
                "scene_id": data.get("scene_id"),
                "sequence_id": data.get("sequence_id"),
                "character_id": data.get("character_id"),
                "location_id": data.get("location_id"),
                "prop_id": data.get("prop_id"),
                "motif_id": data.get("motif_id"),
                "source_type": data.get("source_type") or "project",
                "source_id": data.get("source_id") or "",
                "created_at": data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                "updated_at": data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
            },
            "save_color_palette_continuity_record",
        )

    def list_color_palette_continuity_records(self, project_id: str, scope: str | None = None, scene_id: str | None = None, sequence_id: str | None = None, character_id: str | None = None, location_id: str | None = None, prop_id: str | None = None, motif_id: str | None = None, limit: int = 50) -> list[Any]:
        from app.models.colorist import ColorPaletteContinuityRecord

        return self._list_color_payloads(
            "color_palette_continuity_records",
            ColorPaletteContinuityRecord,
            project_id,
            {
                "scope": scope,
                "scene_id": scene_id,
                "sequence_id": sequence_id,
                "character_id": character_id,
                "location_id": location_id,
                "prop_id": prop_id,
                "motif_id": motif_id,
            },
            limit=limit,
        )

    def get_color_palette_continuity_record(self, palette_record_id: str) -> Any | None:
        from app.models.colorist import ColorPaletteContinuityRecord

        return self._get_color_payload(
            "color_palette_continuity_records",
            "palette_record_id",
            palette_record_id,
            ColorPaletteContinuityRecord,
        )

    def save_color_story_arc(self, story_arc: Any) -> Any:
        data = story_arc.model_dump(mode="json") if hasattr(story_arc, "model_dump") else dict(story_arc)
        return self._save_color_payload(
            "color_story_arcs",
            "color_arc_id",
            story_arc,
            {
                "project_id": data["project_id"],
                "look_bible_id": data.get("look_bible_id"),
                "status": data.get("status") or "active",
                "source_fingerprint": data.get("source_fingerprint") or "",
                "created_at": data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                "updated_at": data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
            },
            "save_color_story_arc",
        )

    def get_color_story_arc(self, color_arc_id: str) -> Any | None:
        from app.models.colorist import ColorStoryArc

        return self._get_color_payload("color_story_arcs", "color_arc_id", color_arc_id, ColorStoryArc)

    def list_color_story_arcs(self, project_id: str, look_bible_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Any]:
        from app.models.colorist import ColorStoryArc

        return self._list_color_payloads("color_story_arcs", ColorStoryArc, project_id, {"look_bible_id": look_bible_id, "status": status}, limit=limit)

    def save_color_grade_observation(self, observation: Any) -> Any:
        data = observation.model_dump(mode="json") if hasattr(observation, "model_dump") else dict(observation)
        return self._save_color_payload(
            "color_grade_observations",
            "observation_id",
            observation,
            {
                "project_id": data["project_id"],
                "plan_id": data.get("plan_id"),
                "look_bible_id": data.get("look_bible_id"),
                "asset_id": data.get("asset_id"),
                "render_job_id": data.get("render_job_id"),
                "scene_id": data.get("scene_id"),
                "shot_id": data.get("shot_id"),
                "scope": data.get("scope") or "asset",
                "status": data.get("status") or "active",
                "confidence_label": data.get("confidence_label") or "low_data",
                "created_at": data.get("created_at") or datetime.utcnow().isoformat() + "Z",
            },
            "save_color_grade_observation",
        )

    def get_color_grade_observation(self, observation_id: str) -> Any | None:
        from app.models.colorist import ColorGradeObservation

        return self._get_color_payload("color_grade_observations", "observation_id", observation_id, ColorGradeObservation)

    def list_color_grade_observations(self, project_id: str, plan_id: str | None = None, asset_id: str | None = None, render_job_id: str | None = None, scene_id: str | None = None, shot_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Any]:
        from app.models.colorist import ColorGradeObservation

        return self._list_color_payloads(
            "color_grade_observations",
            ColorGradeObservation,
            project_id,
            {"plan_id": plan_id, "asset_id": asset_id, "render_job_id": render_job_id, "scene_id": scene_id, "shot_id": shot_id, "status": status},
            limit=limit,
        )

    def save_color_match_assessment(self, assessment: Any) -> Any:
        data = assessment.model_dump(mode="json") if hasattr(assessment, "model_dump") else dict(assessment)
        return self._save_color_payload(
            "color_match_assessments",
            "assessment_id",
            assessment,
            {
                "project_id": data["project_id"],
                "plan_id": data["plan_id"],
                "observation_id": data["observation_id"],
                "look_bible_id": data.get("look_bible_id"),
                "asset_id": data.get("asset_id"),
                "render_job_id": data.get("render_job_id"),
                "scene_id": data.get("scene_id"),
                "shot_id": data.get("shot_id"),
                "status": data.get("status") or "active",
                "requires_creator_attention": 1 if data.get("requires_creator_attention", False) else 0,
                "confidence_label": data.get("confidence_label") or "emerging",
                "created_at": data.get("created_at") or datetime.utcnow().isoformat() + "Z",
            },
            "save_color_match_assessment",
        )

    def get_color_match_assessment(self, assessment_id: str) -> Any | None:
        from app.models.colorist import ColorMatchAssessment

        return self._get_color_payload("color_match_assessments", "assessment_id", assessment_id, ColorMatchAssessment)

    def list_color_match_assessments(self, project_id: str, plan_id: str | None = None, observation_id: str | None = None, look_bible_id: str | None = None, asset_id: str | None = None, render_job_id: str | None = None, scene_id: str | None = None, shot_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Any]:
        from app.models.colorist import ColorMatchAssessment

        return self._list_color_payloads(
            "color_match_assessments",
            ColorMatchAssessment,
            project_id,
            {"plan_id": plan_id, "observation_id": observation_id, "look_bible_id": look_bible_id, "asset_id": asset_id, "render_job_id": render_job_id, "scene_id": scene_id, "shot_id": shot_id, "status": status},
            limit=limit,
        )

    def save_color_final_verification(self, verification: Any) -> Any:
        data = verification.model_dump(mode="json") if hasattr(verification, "model_dump") else dict(verification)
        return self._save_color_payload(
            "color_final_verifications",
            "verification_id",
            verification,
            {
                "project_id": data["project_id"],
                "package_id": data.get("package_id"),
                "asset_id": data.get("asset_id"),
                "look_bible_id": data.get("look_bible_id"),
                "status": data.get("status") or "active",
                "source_fingerprint": data.get("source_fingerprint") or "",
                "confidence_label": data.get("confidence_label") or "emerging",
                "created_at": data.get("created_at") or datetime.utcnow().isoformat() + "Z",
            },
            "save_color_final_verification",
        )

    def get_color_final_verification(self, verification_id: str) -> Any | None:
        from app.models.colorist import ColorFinalVerification

        return self._get_color_payload("color_final_verifications", "verification_id", verification_id, ColorFinalVerification)

    def list_color_final_verifications(self, project_id: str, package_id: str | None = None, asset_id: str | None = None, look_bible_id: str | None = None, status: str | None = None, limit: int = 50) -> list[Any]:
        from app.models.colorist import ColorFinalVerification

        return self._list_color_payloads(
            "color_final_verifications",
            ColorFinalVerification,
            project_id,
            {"package_id": package_id, "asset_id": asset_id, "look_bible_id": look_bible_id, "status": status},
            limit=limit,
        )

    def save_colorist_decision_projection(self, decision: Any) -> Any:
        data = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)
        return self._save_color_payload(
            "colorist_decision_projections",
            "decision_id",
            decision,
            {
                "project_id": data["project_id"],
                "decision_text": data["decision_text"],
                "scene_id": data.get("scene_id"),
                "plan_id": data.get("plan_id"),
                "assessment_id": data.get("assessment_id"),
                "look_bible_id": data.get("look_bible_id"),
                "saved_by": data.get("saved_by") or "creator",
                "saved_at": data.get("saved_at") or datetime.utcnow().isoformat() + "Z",
                "memory_entry_id": data.get("memory_entry_id"),
                "editable": 1 if data.get("editable", True) else 0,
                "forgotten_at": data.get("forgotten_at"),
            },
            "save_colorist_decision_projection",
        )

    def list_colorist_decision_projections(self, project_id: str, plan_id: str | None = None, assessment_id: str | None = None, look_bible_id: str | None = None, limit: int = 50) -> list[Any]:
        from app.models.colorist import ColoristDecisionProjection

        return self._list_color_payloads(
            "colorist_decision_projections",
            ColoristDecisionProjection,
            project_id,
            {"plan_id": plan_id, "assessment_id": assessment_id, "look_bible_id": look_bible_id},
            order_column="saved_at",
            limit=limit,
        )


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

    # ------------------------------------------------------------------ #
    # Performance Intelligence
    # ------------------------------------------------------------------ #

    def save_performance_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(analysis or {})
        now = datetime.now().isoformat()
        payload.setdefault("generated_at", now)
        payload.setdefault("updated_at", now)
        payload.setdefault("model_version", "performance-intelligence-v1")
        payload.setdefault("summary", "")
        payload.setdefault("reasoning_trace", [])
        payload.setdefault("guardrail_report", {})

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_analyses (
                        analysis_id, project_id, scene_id, analysis_scope, status,
                        generated_at, updated_at, source_signature, model_version,
                        summary_json, reasoning_trace_json, guardrail_report_json, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["analysis_id"],
                        payload["project_id"],
                        payload.get("scene_id"),
                        payload.get("analysis_scope", "scene"),
                        payload.get("status", "complete"),
                        payload["generated_at"],
                        payload["updated_at"],
                        payload.get("source_signature", ""),
                        payload["model_version"],
                        json.dumps({"summary": payload.get("summary", "")}, ensure_ascii=True, sort_keys=True),
                        json.dumps(payload.get("reasoning_trace", []), ensure_ascii=True, sort_keys=True),
                        json.dumps(payload.get("guardrail_report", {}), ensure_ascii=True, sort_keys=True),
                        json.dumps(payload, ensure_ascii=True, sort_keys=True),
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_analysis", operation)

    def get_latest_performance_analysis(self, project_id: str, scene_id: str | None = None) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            if scene_id:
                row = conn.execute(
                    """
                    SELECT payload_json FROM performance_analyses
                    WHERE project_id = ? AND scene_id = ?
                    ORDER BY generated_at DESC LIMIT 1
                    """,
                    (project_id, scene_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT payload_json FROM performance_analyses
                    WHERE project_id = ?
                    ORDER BY generated_at DESC LIMIT 1
                    """,
                    (project_id,),
                ).fetchone()
        if not row:
            return None
        try:
            parsed = json.loads(row["payload_json"] or "{}")
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def list_performance_analyses(
        self,
        project_id: str,
        *,
        scene_id: str | None = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 500))
        with self._get_connection() as conn:
            if scene_id:
                rows = conn.execute(
                    """
                    SELECT payload_json FROM performance_analyses
                    WHERE project_id = ? AND scene_id = ?
                    ORDER BY generated_at DESC LIMIT ?
                    """,
                    (project_id, scene_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT payload_json FROM performance_analyses
                    WHERE project_id = ?
                    ORDER BY generated_at DESC LIMIT ?
                    """,
                    (project_id, limit),
                ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                parsed = json.loads(row["payload_json"] or "{}")
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                out.append(parsed)
        return out

    def save_performance_brief(self, brief: Dict[str, Any], *, analysis_id: str, project_id: str) -> Dict[str, Any]:
        payload = dict(brief or {})
        now = datetime.now().isoformat()
        payload.setdefault("created_at", now)
        payload.setdefault("updated_at", now)
        uncertainty = payload.get("uncertainty") if isinstance(payload.get("uncertainty"), dict) else {}

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_briefs (
                        brief_id, analysis_id, project_id, scene_id, character_id, character_name,
                        objective, obstacle, tactic, emotional_start, emotional_end, mask, reveal,
                        subtext_summary, continuity_note, uncertainty_label, uncertainty_reason,
                        payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["brief_id"],
                        analysis_id,
                        project_id,
                        payload.get("scene_id", ""),
                        payload.get("character_id", ""),
                        payload.get("character_name", ""),
                        payload.get("objective", ""),
                        payload.get("obstacle", ""),
                        payload.get("tactic", ""),
                        payload.get("emotional_start", ""),
                        payload.get("emotional_end", ""),
                        payload.get("mask", ""),
                        payload.get("reveal", ""),
                        payload.get("subtext_summary", ""),
                        payload.get("continuity_note", ""),
                        uncertainty.get("label", "emerging"),
                        uncertainty.get("reason", ""),
                        json.dumps(payload, ensure_ascii=True, sort_keys=True),
                        payload["created_at"],
                        payload["updated_at"],
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_brief", operation)

    def list_performance_briefs_for_scene(self, project_id: str, scene_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM performance_briefs
                WHERE project_id = ? AND scene_id = ?
                ORDER BY created_at DESC
                """,
                (project_id, scene_id),
            ).fetchall()
        return [json.loads(row["payload_json"] or "{}") for row in rows]

    def list_performance_briefs_for_character(self, project_id: str, character_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 500))
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM performance_briefs
                WHERE project_id = ? AND character_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (project_id, character_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"] or "{}") for row in rows]

    def save_performance_beat(self, beat: Dict[str, Any], *, brief_id: str, project_id: str, scene_id: str, character_id: str) -> Dict[str, Any]:
        payload = dict(beat or {})
        payload.setdefault("created_at", datetime.now().isoformat())

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_beats (
                        beat_id, brief_id, project_id, scene_id, character_id, beat_index,
                        beat_label, visible_action, internal_action, dialogue_subtext,
                        physical_direction, voice_direction, camera_relevance,
                        evidence_json, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["beat_id"],
                        brief_id,
                        project_id,
                        scene_id,
                        character_id,
                        int(payload.get("beat_index", 0)),
                        payload.get("beat_label", ""),
                        payload.get("visible_action", ""),
                        payload.get("internal_action", ""),
                        payload.get("dialogue_subtext", ""),
                        payload.get("physical_direction", ""),
                        payload.get("voice_direction", ""),
                        payload.get("camera_relevance", ""),
                        json.dumps(payload.get("evidence_refs", []), ensure_ascii=True, sort_keys=True),
                        json.dumps(payload, ensure_ascii=True, sort_keys=True),
                        payload["created_at"],
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_beat", operation)

    def save_performance_relationship_read(self, relationship: Dict[str, Any], *, analysis_id: str, project_id: str) -> Dict[str, Any]:
        payload = dict(relationship or {})
        payload.setdefault("created_at", datetime.now().isoformat())
        uncertainty = payload.get("uncertainty") if isinstance(payload.get("uncertainty"), dict) else {}

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_relationship_reads (
                        relationship_read_id, analysis_id, project_id, scene_id,
                        character_a, character_b, relationship_state, pressure, power_shift,
                        trust_state, conflict_residue, evidence_json, uncertainty_label,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["relationship_read_id"],
                        analysis_id,
                        project_id,
                        payload.get("scene_id", ""),
                        payload.get("character_a", ""),
                        payload.get("character_b", ""),
                        payload.get("relationship_state", ""),
                        payload.get("pressure", ""),
                        payload.get("power_shift", ""),
                        payload.get("trust_state", ""),
                        payload.get("conflict_residue", ""),
                        json.dumps(payload.get("evidence_refs", []), ensure_ascii=True, sort_keys=True),
                        uncertainty.get("label", "emerging"),
                        json.dumps(payload, ensure_ascii=True, sort_keys=True),
                        payload["created_at"],
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_relationship_read", operation)

    def save_performance_evidence_refs(
        self,
        refs: List[Dict[str, Any]],
        *,
        analysis_id: str,
        project_id: str,
        brief_id: str | None = None,
        beat_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        rows = [dict(ref or {}) for ref in refs or []]
        now = datetime.now().isoformat()

        def operation():
            with self._get_connection() as conn:
                for payload in rows:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO performance_evidence_refs (
                            evidence_id, analysis_id, brief_id, beat_id, project_id,
                            source_type, source_id, scene_id, character_id, field_path,
                            excerpt, relevance, reliability_label, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            payload["evidence_id"],
                            analysis_id,
                            brief_id,
                            beat_id,
                            project_id,
                            payload.get("source_type", ""),
                            payload.get("source_id", ""),
                            payload.get("scene_id"),
                            payload.get("character_id"),
                            payload.get("field_path", ""),
                            payload.get("excerpt", ""),
                            payload.get("relevance", ""),
                            payload.get("reliability_label", "emerging"),
                            payload.get("created_at", now),
                        ),
                    )
                conn.commit()
            return rows

        return self._execute_write_with_retry("save_performance_evidence_refs", operation)

    def save_performance_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(decision or {})
        payload.setdefault("saved_at", datetime.now().isoformat())
        payload.setdefault("editable", True)

        def operation():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO performance_decisions (
                        decision_id, project_id, scene_id, character_id, source_brief_id,
                        decision_text, inferred_tradeoff, saved_by, saved_at,
                        memory_entry_id, editable, forgotten_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["decision_id"],
                        payload["project_id"],
                        payload.get("scene_id"),
                        payload.get("character_id"),
                        payload.get("source_brief_id"),
                        payload.get("decision_text", ""),
                        payload.get("inferred_tradeoff", ""),
                        payload.get("saved_by", "creator"),
                        payload["saved_at"],
                        payload.get("memory_entry_id"),
                        1 if payload.get("editable", True) else 0,
                        payload.get("forgotten_at"),
                    ),
                )
                conn.commit()
            return payload

        return self._execute_write_with_retry("save_performance_decision", operation)

    def list_performance_decisions(
        self,
        project_id: str,
        *,
        character_id: str | None = None,
        include_forgotten: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 500))
        clauses = ["project_id = ?"]
        params: List[Any] = [project_id]
        if character_id:
            clauses.append("character_id = ?")
            params.append(character_id)
        if not include_forgotten:
            clauses.append("forgotten_at IS NULL")
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM performance_decisions
                WHERE {' AND '.join(clauses)}
                ORDER BY saved_at DESC LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            {
                "decision_id": row["decision_id"],
                "project_id": row["project_id"],
                "scene_id": row["scene_id"],
                "character_id": row["character_id"],
                "source_brief_id": row["source_brief_id"],
                "decision_text": row["decision_text"],
                "inferred_tradeoff": row["inferred_tradeoff"],
                "saved_by": row["saved_by"],
                "saved_at": row["saved_at"],
                "memory_entry_id": row["memory_entry_id"],
                "editable": bool(row["editable"]),
                "forgotten_at": row["forgotten_at"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    # Casting Intelligence & Talent Management
    # ------------------------------------------------------------------ #

    def _payload_model(self, row: sqlite3.Row, model: Any) -> Any:
        return model(**self._json_loads(row["payload_json"], {}))

    def save_casting_role_breakdown(self, role: Any) -> Any:
        data = role.model_dump(mode="json") if hasattr(role, "model_dump") else dict(role)

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO casting_role_breakdowns (
                        role_id, project_id, character_id, character_name, status, readiness_label,
                        source_signature, stale, created_at, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["role_id"],
                        data["project_id"],
                        data["character_id"],
                        data.get("character_name") or data["character_id"],
                        data.get("status") or "draft",
                        data.get("readiness_label") or "needs_review",
                        data.get("source_signature") or "",
                        1 if data.get("stale", False) else 0,
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_casting_role_breakdown", _write)
        return role

    def get_casting_role_breakdown(self, role_id: str) -> Any | None:
        from app.models.casting_intelligence import CastingRoleBreakdown

        with self._get_connection() as conn:
            row = conn.execute("SELECT payload_json FROM casting_role_breakdowns WHERE role_id = ?", (role_id,)).fetchone()
            return self._payload_model(row, CastingRoleBreakdown) if row else None

    def list_casting_role_breakdowns(
        self,
        project_id: str,
        status: str | None = None,
        stale: bool | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from app.models.casting_intelligence import CastingRoleBreakdown

        query = "SELECT payload_json FROM casting_role_breakdowns WHERE project_id = ?"
        params: list[Any] = [project_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if stale is not None:
            query += " AND stale = ?"
            params.append(1 if stale else 0)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CastingRoleBreakdown(**self._json_loads(row["payload_json"], {})) for row in rows]

    def save_talent_profile(self, profile: Any) -> Any:
        from app.models.casting_intelligence import TalentConsentRecord

        data = profile.model_dump(mode="json") if hasattr(profile, "model_dump") else dict(profile)

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO talent_profiles (
                        talent_id, project_id, display_name, modality, availability_label,
                        stale, created_at, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["talent_id"],
                        data["project_id"],
                        data.get("display_name") or data["talent_id"],
                        data.get("modality") or "human",
                        data.get("availability_label") or "unknown",
                        1 if data.get("stale", False) else 0,
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                for raw in data.get("consent_records", []) or []:
                    consent = TalentConsentRecord(**raw)
                    consent_data = consent.model_dump(mode="json")
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO talent_consent_records (
                            consent_id, project_id, talent_id, modality, status,
                            created_at, updated_at, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            consent_data["consent_id"],
                            consent_data["project_id"],
                            consent_data["talent_id"],
                            consent_data["modality"],
                            consent_data.get("status") or "pending",
                            consent_data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                            consent_data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                            self._json_dumps(consent_data),
                        ),
                    )
                conn.commit()

        self._execute_write_with_retry("save_talent_profile", _write)
        return profile

    def get_talent_profile(self, talent_id: str) -> Any | None:
        from app.models.casting_intelligence import TalentProfile

        with self._get_connection() as conn:
            row = conn.execute("SELECT payload_json FROM talent_profiles WHERE talent_id = ?", (talent_id,)).fetchone()
            return self._payload_model(row, TalentProfile) if row else None

    def list_talent_profiles(
        self,
        project_id: str,
        modality: str | None = None,
        stale: bool | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from app.models.casting_intelligence import TalentProfile

        query = "SELECT payload_json FROM talent_profiles WHERE project_id = ?"
        params: list[Any] = [project_id]
        if modality:
            query += " AND modality = ?"
            params.append(modality)
        if stale is not None:
            query += " AND stale = ?"
            params.append(1 if stale else 0)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [TalentProfile(**self._json_loads(row["payload_json"], {})) for row in rows]

    def save_audition_package(self, package: Any) -> Any:
        data = package.model_dump(mode="json") if hasattr(package, "model_dump") else dict(package)

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO audition_packages (
                        package_id, project_id, role_id, character_id, status,
                        created_at, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["package_id"],
                        data["project_id"],
                        data["role_id"],
                        data.get("character_id") or "",
                        data.get("status") or "open",
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_audition_package", _write)
        return package

    def get_audition_package(self, package_id: str) -> Any | None:
        from app.models.casting_intelligence import AuditionPackage

        with self._get_connection() as conn:
            row = conn.execute("SELECT payload_json FROM audition_packages WHERE package_id = ?", (package_id,)).fetchone()
            return self._payload_model(row, AuditionPackage) if row else None

    def list_audition_packages(self, project_id: str, role_id: str | None = None, limit: int = 100) -> list[Any]:
        from app.models.casting_intelligence import AuditionPackage

        query = "SELECT payload_json FROM audition_packages WHERE project_id = ?"
        params: list[Any] = [project_id]
        if role_id:
            query += " AND role_id = ?"
            params.append(role_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AuditionPackage(**self._json_loads(row["payload_json"], {})) for row in rows]

    def save_audition_submission(self, audition: Any) -> Any:
        data = audition.model_dump(mode="json") if hasattr(audition, "model_dump") else dict(audition)

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO audition_submissions (
                        audition_id, project_id, package_id, role_id, talent_id,
                        status, submitted_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["audition_id"],
                        data["project_id"],
                        data["package_id"],
                        data["role_id"],
                        data["talent_id"],
                        data.get("status") or "submitted",
                        data.get("submitted_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_audition_submission", _write)
        return audition

    def get_audition_submission(self, audition_id: str) -> Any | None:
        from app.models.casting_intelligence import AuditionSubmission

        with self._get_connection() as conn:
            row = conn.execute("SELECT payload_json FROM audition_submissions WHERE audition_id = ?", (audition_id,)).fetchone()
            return self._payload_model(row, AuditionSubmission) if row else None

    def list_audition_submissions(
        self,
        project_id: str,
        role_id: str | None = None,
        talent_id: str | None = None,
        package_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from app.models.casting_intelligence import AuditionSubmission

        query = "SELECT payload_json FROM audition_submissions WHERE project_id = ?"
        params: list[Any] = [project_id]
        filters = {"role_id": role_id, "talent_id": talent_id, "package_id": package_id}
        for column, value in filters.items():
            if value:
                query += f" AND {column} = ?"
                params.append(value)
        query += " ORDER BY submitted_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AuditionSubmission(**self._json_loads(row["payload_json"], {})) for row in rows]

    def save_audition_evaluation(self, evaluation: Any) -> Any:
        data = evaluation.model_dump(mode="json") if hasattr(evaluation, "model_dump") else dict(evaluation)

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO audition_evaluations (
                        evaluation_id, project_id, audition_id, role_id, talent_id,
                        uncertainty_label, created_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["evaluation_id"],
                        data["project_id"],
                        data["audition_id"],
                        data["role_id"],
                        data["talent_id"],
                        data.get("uncertainty_label") or "emerging",
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_audition_evaluation", _write)
        return evaluation

    def get_audition_evaluation(self, evaluation_id: str) -> Any | None:
        from app.models.casting_intelligence import AuditionEvaluation

        with self._get_connection() as conn:
            row = conn.execute("SELECT payload_json FROM audition_evaluations WHERE evaluation_id = ?", (evaluation_id,)).fetchone()
            return self._payload_model(row, AuditionEvaluation) if row else None

    def list_audition_evaluations(
        self,
        project_id: str,
        role_id: str | None = None,
        audition_id: str | None = None,
        talent_id: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from app.models.casting_intelligence import AuditionEvaluation

        query = "SELECT payload_json FROM audition_evaluations WHERE project_id = ?"
        params: list[Any] = [project_id]
        filters = {"role_id": role_id, "audition_id": audition_id, "talent_id": talent_id}
        for column, value in filters.items():
            if value:
                query += f" AND {column} = ?"
                params.append(value)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AuditionEvaluation(**self._json_loads(row["payload_json"], {})) for row in rows]

    def save_casting_recommendation(self, recommendation: Any) -> Any:
        data = recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else dict(recommendation)

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO casting_recommendations (
                        recommendation_id, project_id, role_id, talent_id, audition_id,
                        evaluation_id, readiness_label, source_signature, stale, created_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["recommendation_id"],
                        data["project_id"],
                        data["role_id"],
                        data["talent_id"],
                        data.get("audition_id"),
                        data.get("evaluation_id"),
                        data.get("readiness_label") or "needs_review",
                        data.get("source_signature") or "",
                        1 if data.get("stale", False) else 0,
                        data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_casting_recommendation", _write)
        return recommendation

    def get_casting_recommendation(self, recommendation_id: str) -> Any | None:
        from app.models.casting_intelligence import CastingRecommendation

        with self._get_connection() as conn:
            row = conn.execute("SELECT payload_json FROM casting_recommendations WHERE recommendation_id = ?", (recommendation_id,)).fetchone()
            return self._payload_model(row, CastingRecommendation) if row else None

    def list_casting_recommendations(
        self,
        project_id: str,
        role_id: str | None = None,
        talent_id: str | None = None,
        stale: bool | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from app.models.casting_intelligence import CastingRecommendation

        query = "SELECT payload_json FROM casting_recommendations WHERE project_id = ?"
        params: list[Any] = [project_id]
        filters = {"role_id": role_id, "talent_id": talent_id}
        for column, value in filters.items():
            if value:
                query += f" AND {column} = ?"
                params.append(value)
        if stale is not None:
            query += " AND stale = ?"
            params.append(1 if stale else 0)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CastingRecommendation(**self._json_loads(row["payload_json"], {})) for row in rows]

    def save_casting_decision(self, decision: Any) -> Any:
        data = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)

        def _write():
            with self._get_connection() as conn:
                old_row = None
                if data.get("active", True):
                    old_row = conn.execute(
                        """
                        SELECT decision_id, payload_json FROM casting_decisions
                        WHERE project_id = ? AND role_id = ? AND active = 1 AND decision_id != ?
                        """,
                        (data["project_id"], data["role_id"], data["decision_id"]),
                    ).fetchone()
                    if old_row:
                        old_payload = self._json_loads(old_row["payload_json"], {})
                        old_payload["active"] = False
                        old_payload["status"] = "superseded"
                        old_payload["superseded_by_decision_id"] = data["decision_id"]
                        conn.execute(
                            """
                            UPDATE casting_decisions
                            SET active = 0, status = 'superseded',
                                superseded_by_decision_id = ?, payload_json = ?
                            WHERE decision_id = ?
                            """,
                            (data["decision_id"], self._json_dumps(old_payload), old_row["decision_id"]),
                        )
                        data["supersedes_decision_id"] = data.get("supersedes_decision_id") or old_row["decision_id"]
                conn.execute(
                    """
                    INSERT OR REPLACE INTO casting_decisions (
                        decision_id, project_id, role_id, character_id, talent_id,
                        recommendation_id, audition_id, evaluation_id, status, active,
                        approved_at, readiness_label, stale, supersedes_decision_id,
                        superseded_by_decision_id, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["decision_id"],
                        data["project_id"],
                        data["role_id"],
                        data["character_id"],
                        data["talent_id"],
                        data.get("recommendation_id"),
                        data.get("audition_id"),
                        data.get("evaluation_id"),
                        data.get("status") or "approved",
                        1 if data.get("active", True) else 0,
                        data.get("approved_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("readiness_label") or "needs_review",
                        1 if data.get("stale", False) else 0,
                        data.get("supersedes_decision_id"),
                        data.get("superseded_by_decision_id"),
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_casting_decision", _write)
        if hasattr(decision, "supersedes_decision_id"):
            decision.supersedes_decision_id = data.get("supersedes_decision_id")
        return decision

    def get_casting_decision(self, decision_id: str) -> Any | None:
        from app.models.casting_intelligence import CastingDecision

        with self._get_connection() as conn:
            row = conn.execute("SELECT payload_json FROM casting_decisions WHERE decision_id = ?", (decision_id,)).fetchone()
            return self._payload_model(row, CastingDecision) if row else None

    def list_casting_decisions(
        self,
        project_id: str,
        role_id: str | None = None,
        character_id: str | None = None,
        active: bool | None = None,
        limit: int = 100,
    ) -> list[Any]:
        from app.models.casting_intelligence import CastingDecision

        query = "SELECT payload_json FROM casting_decisions WHERE project_id = ?"
        params: list[Any] = [project_id]
        filters = {"role_id": role_id, "character_id": character_id}
        for column, value in filters.items():
            if value:
                query += f" AND {column} = ?"
                params.append(value)
        if active is not None:
            query += " AND active = ?"
            params.append(1 if active else 0)
        query += " ORDER BY approved_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CastingDecision(**self._json_loads(row["payload_json"], {})) for row in rows]

    def save_casting_readiness_report(self, report: Any) -> Any:
        data = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO casting_readiness_reports (
                        report_id, project_id, scope, role_id, readiness_label, generated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["report_id"],
                        data["project_id"],
                        data.get("scope") or "project",
                        data.get("role_id"),
                        data.get("readiness_label") or "needs_review",
                        data.get("generated_at") or datetime.utcnow().isoformat() + "Z",
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_casting_readiness_report", _write)
        return report

    def save_casting_decision_memory_projection(self, decision: Any) -> Any:
        data = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)

        def _write():
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO casting_decision_memory_projections (
                        decision_id, project_id, role_id, character_id, talent_id,
                        casting_decision_id, decision_text, inferred_tradeoff, saved_by,
                        saved_at, memory_entry_id, editable, forgotten_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["decision_id"],
                        data["project_id"],
                        data.get("role_id"),
                        data.get("character_id"),
                        data.get("talent_id"),
                        data.get("casting_decision_id"),
                        data.get("decision_text") or "",
                        data.get("inferred_tradeoff") or "",
                        data.get("saved_by") or "creator",
                        data.get("saved_at") or datetime.utcnow().isoformat() + "Z",
                        data.get("memory_entry_id"),
                        1 if data.get("editable", True) else 0,
                        data.get("forgotten_at"),
                        self._json_dumps(data),
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_casting_decision_memory_projection", _write)
        return decision

    def get_casting_decision_memory_projection(self, decision_id: str) -> Any | None:
        from app.models.casting_intelligence import CastingDecisionMemoryProjection

        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM casting_decision_memory_projections WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            return self._payload_model(row, CastingDecisionMemoryProjection) if row else None

    def list_casting_decision_memory_projections(self, project_id: str, limit: int = 50) -> list[Any]:
        from app.models.casting_intelligence import CastingDecisionMemoryProjection

        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM casting_decision_memory_projections
                WHERE project_id = ? AND forgotten_at IS NULL
                ORDER BY saved_at DESC LIMIT ?
                """,
                (project_id, max(1, min(int(limit), 500))),
            ).fetchall()
        return [CastingDecisionMemoryProjection(**self._json_loads(row["payload_json"], {})) for row in rows]

    def update_casting_decision_memory_projection(
        self,
        project_id: str,
        decision_id: str,
        updates: Dict[str, Any],
    ) -> Any | None:
        current = self.get_casting_decision_memory_projection(decision_id)
        if not current or current.project_id != project_id:
            return None
        data = current.model_dump(mode="json")
        for key, value in updates.items():
            if value is not None:
                data[key] = value
        from app.models.casting_intelligence import CastingDecisionMemoryProjection

        updated = CastingDecisionMemoryProjection(**data)
        self.save_casting_decision_memory_projection(updated)
        return updated

    def forget_casting_decision_memory_projection(self, project_id: str, decision_id: str) -> Any | None:
        current = self.get_casting_decision_memory_projection(decision_id)
        if not current or current.project_id != project_id:
            return None
        current.forgotten_at = datetime.utcnow().isoformat() + "Z"
        self.save_casting_decision_memory_projection(current)
        return current


def _json_storage_save_performance_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
    return dict(analysis or {})


def _json_storage_get_latest_performance_analysis(self, project_id: str, scene_id: str | None = None) -> Optional[Dict[str, Any]]:
    return None


def _json_storage_list_performance_analyses(
    self,
    project_id: str,
    *,
    scene_id: str | None = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    return []


def _json_storage_save_performance_brief(self, brief: Dict[str, Any], *, analysis_id: str, project_id: str) -> Dict[str, Any]:
    return dict(brief or {})


def _json_storage_list_performance_briefs_for_scene(self, project_id: str, scene_id: str) -> List[Dict[str, Any]]:
    return []


def _json_storage_list_performance_briefs_for_character(self, project_id: str, character_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    return []


def _json_storage_save_performance_beat(
    self,
    beat: Dict[str, Any],
    *,
    brief_id: str,
    project_id: str,
    scene_id: str,
    character_id: str,
) -> Dict[str, Any]:
    return dict(beat or {})


def _json_storage_save_performance_relationship_read(self, relationship: Dict[str, Any], *, analysis_id: str, project_id: str) -> Dict[str, Any]:
    return dict(relationship or {})


def _json_storage_save_performance_evidence_refs(
    self,
    refs: List[Dict[str, Any]],
    *,
    analysis_id: str,
    project_id: str,
    brief_id: str | None = None,
    beat_id: str | None = None,
) -> List[Dict[str, Any]]:
    return [dict(ref or {}) for ref in refs or []]


def _json_storage_save_performance_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
    return dict(decision or {})


def _json_storage_list_performance_decisions(
    self,
    project_id: str,
    *,
    character_id: str | None = None,
    include_forgotten: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    return []


def _json_storage_update_performance_decision(self, project_id: str, decision_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return None


def _json_storage_forget_performance_decision(self, project_id: str, decision_id: str) -> Optional[Dict[str, Any]]:
    return None


JsonFileStorage.save_performance_analysis = _json_storage_save_performance_analysis
JsonFileStorage.get_latest_performance_analysis = _json_storage_get_latest_performance_analysis
JsonFileStorage.list_performance_analyses = _json_storage_list_performance_analyses
JsonFileStorage.save_performance_brief = _json_storage_save_performance_brief
JsonFileStorage.list_performance_briefs_for_scene = _json_storage_list_performance_briefs_for_scene
JsonFileStorage.list_performance_briefs_for_character = _json_storage_list_performance_briefs_for_character
JsonFileStorage.save_performance_beat = _json_storage_save_performance_beat
JsonFileStorage.save_performance_relationship_read = _json_storage_save_performance_relationship_read
JsonFileStorage.save_performance_evidence_refs = _json_storage_save_performance_evidence_refs
JsonFileStorage.save_performance_decision = _json_storage_save_performance_decision
JsonFileStorage.list_performance_decisions = _json_storage_list_performance_decisions
JsonFileStorage.update_performance_decision = _json_storage_update_performance_decision
JsonFileStorage.forget_performance_decision = _json_storage_forget_performance_decision

DatabaseStorage._payload_model = JsonFileStorage._payload_model
DatabaseStorage.save_casting_role_breakdown = JsonFileStorage.save_casting_role_breakdown
DatabaseStorage.get_casting_role_breakdown = JsonFileStorage.get_casting_role_breakdown
DatabaseStorage.list_casting_role_breakdowns = JsonFileStorage.list_casting_role_breakdowns
DatabaseStorage.save_talent_profile = JsonFileStorage.save_talent_profile
DatabaseStorage.get_talent_profile = JsonFileStorage.get_talent_profile
DatabaseStorage.list_talent_profiles = JsonFileStorage.list_talent_profiles
DatabaseStorage.save_audition_package = JsonFileStorage.save_audition_package
DatabaseStorage.get_audition_package = JsonFileStorage.get_audition_package
DatabaseStorage.list_audition_packages = JsonFileStorage.list_audition_packages
DatabaseStorage.save_audition_submission = JsonFileStorage.save_audition_submission
DatabaseStorage.get_audition_submission = JsonFileStorage.get_audition_submission
DatabaseStorage.list_audition_submissions = JsonFileStorage.list_audition_submissions
DatabaseStorage.save_audition_evaluation = JsonFileStorage.save_audition_evaluation
DatabaseStorage.get_audition_evaluation = JsonFileStorage.get_audition_evaluation
DatabaseStorage.list_audition_evaluations = JsonFileStorage.list_audition_evaluations
DatabaseStorage.save_casting_recommendation = JsonFileStorage.save_casting_recommendation
DatabaseStorage.get_casting_recommendation = JsonFileStorage.get_casting_recommendation
DatabaseStorage.list_casting_recommendations = JsonFileStorage.list_casting_recommendations
DatabaseStorage.save_casting_decision = JsonFileStorage.save_casting_decision
DatabaseStorage.get_casting_decision = JsonFileStorage.get_casting_decision
DatabaseStorage.list_casting_decisions = JsonFileStorage.list_casting_decisions
DatabaseStorage.save_casting_readiness_report = JsonFileStorage.save_casting_readiness_report
DatabaseStorage.save_casting_decision_memory_projection = JsonFileStorage.save_casting_decision_memory_projection
DatabaseStorage.get_casting_decision_memory_projection = JsonFileStorage.get_casting_decision_memory_projection
DatabaseStorage.list_casting_decision_memory_projections = JsonFileStorage.list_casting_decision_memory_projections
DatabaseStorage.update_casting_decision_memory_projection = JsonFileStorage.update_casting_decision_memory_projection
DatabaseStorage.forget_casting_decision_memory_projection = JsonFileStorage.forget_casting_decision_memory_projection


def _json_storage_save_casting_artifact(self, artifact: Any) -> Any:
    return artifact


def _json_storage_get_casting_artifact(self, *args: Any, **kwargs: Any) -> Any | None:
    return None


def _json_storage_list_casting_artifacts(self, *args: Any, **kwargs: Any) -> list[Any]:
    return []


JsonFileStorage._payload_model = lambda self, row, model: None
JsonFileStorage.save_casting_role_breakdown = _json_storage_save_casting_artifact
JsonFileStorage.get_casting_role_breakdown = _json_storage_get_casting_artifact
JsonFileStorage.list_casting_role_breakdowns = _json_storage_list_casting_artifacts
JsonFileStorage.save_talent_profile = _json_storage_save_casting_artifact
JsonFileStorage.get_talent_profile = _json_storage_get_casting_artifact
JsonFileStorage.list_talent_profiles = _json_storage_list_casting_artifacts
JsonFileStorage.save_audition_package = _json_storage_save_casting_artifact
JsonFileStorage.get_audition_package = _json_storage_get_casting_artifact
JsonFileStorage.list_audition_packages = _json_storage_list_casting_artifacts
JsonFileStorage.save_audition_submission = _json_storage_save_casting_artifact
JsonFileStorage.get_audition_submission = _json_storage_get_casting_artifact
JsonFileStorage.list_audition_submissions = _json_storage_list_casting_artifacts
JsonFileStorage.save_audition_evaluation = _json_storage_save_casting_artifact
JsonFileStorage.get_audition_evaluation = _json_storage_get_casting_artifact
JsonFileStorage.list_audition_evaluations = _json_storage_list_casting_artifacts
JsonFileStorage.save_casting_recommendation = _json_storage_save_casting_artifact
JsonFileStorage.get_casting_recommendation = _json_storage_get_casting_artifact
JsonFileStorage.list_casting_recommendations = _json_storage_list_casting_artifacts
JsonFileStorage.save_casting_decision = _json_storage_save_casting_artifact
JsonFileStorage.get_casting_decision = _json_storage_get_casting_artifact
JsonFileStorage.list_casting_decisions = _json_storage_list_casting_artifacts
JsonFileStorage.save_casting_readiness_report = _json_storage_save_casting_artifact
JsonFileStorage.save_casting_decision_memory_projection = _json_storage_save_casting_artifact
JsonFileStorage.get_casting_decision_memory_projection = _json_storage_get_casting_artifact
JsonFileStorage.list_casting_decision_memory_projections = _json_storage_list_casting_artifacts
JsonFileStorage.update_casting_decision_memory_projection = _json_storage_get_casting_artifact
JsonFileStorage.forget_casting_decision_memory_projection = _json_storage_get_casting_artifact


def _knowledge_json_list(storage: Any, raw: Any) -> list[Any]:
    return storage._json_loads(raw, []) if hasattr(storage, "_json_loads") else json.loads(raw or "[]")


def _knowledge_json_dict(storage: Any, raw: Any) -> dict[str, Any]:
    return storage._json_loads(raw, {}) if hasattr(storage, "_json_loads") else json.loads(raw or "{}")


def _db_row_to_knowledge_bible(self: Any, row: sqlite3.Row) -> Any:
    from app.models.studio_knowledge import KnowledgeBible, KnowledgeBibleStatus

    return KnowledgeBible(
        bible_id=row["bible_id"],
        project_id=row["project_id"],
        title=row["title"],
        bible_type=row["bible_type"] or "general",
        content_type=row["content_type"] or "markdown",
        source_filename=row["source_filename"] or "",
        source_uri=row["source_uri"] or "",
        status=KnowledgeBibleStatus(row["status"] or "registered"),
        source_fingerprint=row["source_fingerprint"] or "",
        section_count=int(row["section_count"] or 0),
        atom_count=int(row["atom_count"] or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=_knowledge_json_dict(self, row["metadata_json"]),
    )


def _db_row_to_knowledge_section(self: Any, row: sqlite3.Row) -> Any:
    from app.models.studio_knowledge import KnowledgeBibleSection

    return KnowledgeBibleSection(
        section_id=row["section_id"],
        bible_id=row["bible_id"],
        project_id=row["project_id"],
        heading=row["heading"] or "",
        section_index=int(row["section_index"] or 0),
        content=row["content"] or "",
        source_fingerprint=row["source_fingerprint"] or "",
        created_at=row["created_at"],
        metadata=_knowledge_json_dict(self, row["metadata_json"]),
    )


def _db_row_to_knowledge_atom(self: Any, row: sqlite3.Row) -> Any:
    from app.models.studio_knowledge import (
        KnowledgeAtom,
        KnowledgeAtomEvidenceRef,
        KnowledgeAtomType,
        KnowledgeAuthorityLevel,
        KnowledgeConfidenceLabel,
        KnowledgeScopeType,
        KnowledgeSourceRef,
    )

    source_ref = KnowledgeSourceRef(**_knowledge_json_dict(self, row["source_ref_json"]))
    return KnowledgeAtom(
        atom_id=row["atom_id"],
        project_id=row["project_id"],
        source_ref=source_ref,
        atom_type=KnowledgeAtomType(row["atom_type"]),
        authority_level=KnowledgeAuthorityLevel(row["authority_level"]),
        scope_type=KnowledgeScopeType(row["scope_type"] or "project"),
        scope_id=row["scope_id"] or "",
        department=row["department"] or "",
        canonical_text=row["canonical_text"],
        summary=row["summary"] or "",
        tags=[str(item) for item in _knowledge_json_list(self, row["tags_json"])],
        evidence_refs=[KnowledgeAtomEvidenceRef(**item) for item in _knowledge_json_list(self, row["evidence_refs_json"]) if isinstance(item, dict)],
        confidence_label=KnowledgeConfidenceLabel(row["confidence_label"] or "emerging"),
        extraction_method=row["extraction_method"] or "deterministic",
        source_fingerprint=row["source_fingerprint"] or "",
        status=row["status"] or "active",
        expires_at=row["expires_at"],
        supersedes_atom_id=row["supersedes_atom_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        metadata=_knowledge_json_dict(self, row["metadata_json"]),
    )


def _db_row_to_knowledge_conflict(self: Any, row: sqlite3.Row) -> Any:
    from app.models.studio_knowledge import CanonicalConflict, KnowledgeConflictStatus, KnowledgeScopeType

    return CanonicalConflict(
        conflict_id=row["conflict_id"],
        project_id=row["project_id"],
        conflict_type=row["conflict_type"],
        severity=row["severity"] or "advisory",
        status=KnowledgeConflictStatus(row["status"] or "open"),
        primary_atom_id=row["primary_atom_id"],
        conflicting_atom_id=row["conflicting_atom_id"],
        summary=row["summary"],
        resolution_guidance=row["resolution_guidance"] or "",
        scope_type=KnowledgeScopeType(row["scope_type"] or "project"),
        scope_id=row["scope_id"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        acknowledged_by=row["acknowledged_by"] or "",
        acknowledged_at=row["acknowledged_at"] or "",
        metadata=_knowledge_json_dict(self, row["metadata_json"]),
    )


def _db_row_to_knowledge_trace(self: Any, row: sqlite3.Row) -> Any:
    from app.models.studio_knowledge import KnowledgeReasoningTrace

    return KnowledgeReasoningTrace(
        trace_id=row["trace_id"],
        pack_id=row["pack_id"],
        project_id=row["project_id"],
        department=row["department"],
        purpose=row["purpose"] or "planning",
        consumer_id=row["consumer_id"] or "",
        selected_atom_ids=[str(item) for item in _knowledge_json_list(self, row["selected_atom_ids_json"])],
        excluded_atom_ids=[str(item) for item in _knowledge_json_list(self, row["excluded_atom_ids_json"])],
        conflict_ids=[str(item) for item in _knowledge_json_list(self, row["conflict_ids_json"])],
        source_counts={str(k): int(v) for k, v in _knowledge_json_dict(self, row["source_counts_json"]).items()},
        selection_notes=[str(item) for item in _knowledge_json_list(self, row["selection_notes_json"])],
        created_at=row["created_at"],
        metadata=_knowledge_json_dict(self, row["metadata_json"]),
    )


def _db_row_to_knowledge_rebuild(self: Any, row: sqlite3.Row) -> Any:
    from app.models.studio_knowledge import KnowledgeRebuildRun, KnowledgeSourceType

    return KnowledgeRebuildRun(
        run_id=row["run_id"],
        project_id=row["project_id"],
        status=row["status"] or "complete",
        source_types=[KnowledgeSourceType(item) for item in _knowledge_json_list(self, row["source_types_json"])],
        source_count=int(row["source_count"] or 0),
        atom_count=int(row["atom_count"] or 0),
        conflict_count=int(row["conflict_count"] or 0),
        started_at=row["started_at"],
        completed_at=row["completed_at"] or "",
        duration_ms=int(row["duration_ms"] or 0),
        warnings=[str(item) for item in _knowledge_json_list(self, row["warnings_json"])],
        metadata=_knowledge_json_dict(self, row["metadata_json"]),
    )


def _db_save_knowledge_bible(self: Any, bible: Any, content: str = "") -> Any:
    data = bible.model_dump(mode="json") if hasattr(bible, "model_dump") else dict(bible)
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO knowledge_bibles (
                bible_id, project_id, title, bible_type, content_type, source_filename,
                source_uri, status, source_fingerprint, content, section_count,
                atom_count, created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["bible_id"],
                data["project_id"],
                data["title"],
                data.get("bible_type") or "general",
                data.get("content_type") or "markdown",
                data.get("source_filename") or "",
                data.get("source_uri") or "",
                data.get("status") or "registered",
                data.get("source_fingerprint") or "",
                content,
                int(data.get("section_count") or 0),
                int(data.get("atom_count") or 0),
                data["created_at"],
                data["updated_at"],
                self._json_dumps(data.get("metadata", {})),
            ),
        )
        conn.commit()
    return self.get_knowledge_bible(data["bible_id"])


def _db_get_knowledge_bible(self: Any, bible_id: str) -> Any | None:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_bibles WHERE bible_id = ?", (bible_id,))
        row = cursor.fetchone()
        return _db_row_to_knowledge_bible(self, row) if row else None


def _db_get_knowledge_bible_content(self: Any, bible_id: str) -> str:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM knowledge_bibles WHERE bible_id = ?", (bible_id,))
        row = cursor.fetchone()
        return str(row["content"] or "") if row else ""


def _db_list_knowledge_bibles(self: Any, project_id: str, status: str | None = None, limit: int = 50) -> list[Any]:
    query = "SELECT * FROM knowledge_bibles WHERE project_id = ?"
    params: list[Any] = [project_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [_db_row_to_knowledge_bible(self, row) for row in cursor.fetchall()]


def _db_delete_knowledge_sections_for_bible(self: Any, bible_id: str) -> int:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_bible_sections WHERE bible_id = ?", (bible_id,))
        conn.commit()
        return int(cursor.rowcount)


def _db_save_knowledge_section(self: Any, section: Any) -> Any:
    data = section.model_dump(mode="json") if hasattr(section, "model_dump") else dict(section)
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO knowledge_bible_sections (
                section_id, bible_id, project_id, heading, section_index, content,
                source_fingerprint, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["section_id"],
                data["bible_id"],
                data["project_id"],
                data.get("heading") or "",
                int(data.get("section_index") or 0),
                data.get("content") or "",
                data.get("source_fingerprint") or "",
                data["created_at"],
                self._json_dumps(data.get("metadata", {})),
            ),
        )
        conn.commit()
    return section


def _db_list_knowledge_sections(self: Any, bible_id: str) -> list[Any]:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM knowledge_bible_sections WHERE bible_id = ? ORDER BY section_index",
            (bible_id,),
        )
        return [_db_row_to_knowledge_section(self, row) for row in cursor.fetchall()]


def _db_save_knowledge_atom(self: Any, atom: Any) -> Any:
    data = atom.model_dump(mode="json") if hasattr(atom, "model_dump") else dict(atom)
    source_ref = data.get("source_ref") or {}
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO knowledge_atoms (
                atom_id, project_id, source_type, source_id, source_ref_json,
                atom_type, authority_level, scope_type, scope_id, department,
                canonical_text, summary, tags_json, evidence_refs_json,
                confidence_label, extraction_method, source_fingerprint, status,
                expires_at, supersedes_atom_id, created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["atom_id"],
                data["project_id"],
                source_ref.get("source_type") or "",
                source_ref.get("source_id") or "",
                self._json_dumps(source_ref),
                data["atom_type"],
                data["authority_level"],
                data.get("scope_type") or "project",
                data.get("scope_id") or "",
                data.get("department") or "",
                data["canonical_text"],
                data.get("summary") or "",
                self._json_dumps(data.get("tags", [])),
                self._json_dumps(data.get("evidence_refs", [])),
                data.get("confidence_label") or "emerging",
                data.get("extraction_method") or "deterministic",
                data.get("source_fingerprint") or "",
                data.get("status") or "active",
                data.get("expires_at"),
                data.get("supersedes_atom_id"),
                data["created_at"],
                data["updated_at"],
                self._json_dumps(data.get("metadata", {})),
            ),
        )
        conn.commit()
    return atom


def _db_list_knowledge_atoms(
    self: Any,
    project_id: str,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Any]:
    filters = filters or {}
    clauses = ["project_id = ?"]
    params: list[Any] = [project_id]
    for key in ["source_type", "atom_type", "authority_level", "scope_type", "scope_id", "department", "status"]:
        if filters.get(key):
            clauses.append(f"{key} = ?")
            params.append(str(filters[key]))
    params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT * FROM knowledge_atoms
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )
        return [_db_row_to_knowledge_atom(self, row) for row in cursor.fetchall()]


def _db_delete_knowledge_atoms_for_source(self: Any, project_id: str, source_type: str, source_id: str) -> int:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM knowledge_atoms WHERE project_id = ? AND source_type = ? AND source_id = ?",
            (project_id, source_type, source_id),
        )
        conn.commit()
        return int(cursor.rowcount)


def _db_delete_knowledge_atoms_for_project(self: Any, project_id: str) -> int:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_atoms WHERE project_id = ?", (project_id,))
        conn.commit()
        return int(cursor.rowcount)


def _db_save_knowledge_conflict(self: Any, conflict: Any) -> Any:
    data = conflict.model_dump(mode="json") if hasattr(conflict, "model_dump") else dict(conflict)
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO knowledge_conflicts (
                conflict_id, project_id, conflict_type, severity, status,
                primary_atom_id, conflicting_atom_id, summary, resolution_guidance,
                scope_type, scope_id, created_at, updated_at, acknowledged_by,
                acknowledged_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["conflict_id"],
                data["project_id"],
                data["conflict_type"],
                data.get("severity") or "advisory",
                data.get("status") or "open",
                data["primary_atom_id"],
                data["conflicting_atom_id"],
                data["summary"],
                data.get("resolution_guidance") or "",
                data.get("scope_type") or "project",
                data.get("scope_id") or "",
                data["created_at"],
                data["updated_at"],
                data.get("acknowledged_by") or "",
                data.get("acknowledged_at") or "",
                self._json_dumps(data.get("metadata", {})),
            ),
        )
        conn.commit()
    return conflict


def _db_get_knowledge_conflict(self: Any, conflict_id: str) -> Any | None:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_conflicts WHERE conflict_id = ?", (conflict_id,))
        row = cursor.fetchone()
        return _db_row_to_knowledge_conflict(self, row) if row else None


def _db_list_knowledge_conflicts(self: Any, project_id: str, status: str | None = None, limit: int = 100) -> list[Any]:
    query = "SELECT * FROM knowledge_conflicts WHERE project_id = ?"
    params: list[Any] = [project_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [_db_row_to_knowledge_conflict(self, row) for row in cursor.fetchall()]


def _db_save_knowledge_context_pack(self: Any, pack: Any) -> Any:
    data = pack.model_dump(mode="json") if hasattr(pack, "model_dump") else dict(pack)
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO knowledge_context_pack_snapshots (
                pack_id, project_id, department, purpose, scene_id, shot_id, asset_id,
                trace_id, atom_ids_json, conflict_ids_json, payload_json, created_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["pack_id"],
                data["project_id"],
                data["department"],
                data.get("purpose") or "planning",
                data.get("scene_id"),
                data.get("shot_id"),
                data.get("asset_id"),
                data.get("trace_id") or "",
                self._json_dumps([item.get("atom_id") for item in data.get("atoms", []) if isinstance(item, dict)]),
                self._json_dumps([item.get("conflict_id") for item in data.get("conflicts", []) if isinstance(item, dict)]),
                self._json_dumps(data),
                data["created_at"],
                self._json_dumps(data.get("metadata", {})),
            ),
        )
        conn.commit()
    return pack


def _db_save_knowledge_trace(self: Any, trace: Any) -> Any:
    data = trace.model_dump(mode="json") if hasattr(trace, "model_dump") else dict(trace)
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO knowledge_reasoning_traces (
                trace_id, pack_id, project_id, department, purpose, consumer_id,
                selected_atom_ids_json, excluded_atom_ids_json, conflict_ids_json,
                source_counts_json, selection_notes_json, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["trace_id"],
                data["pack_id"],
                data["project_id"],
                data["department"],
                data.get("purpose") or "planning",
                data.get("consumer_id") or "",
                self._json_dumps(data.get("selected_atom_ids", [])),
                self._json_dumps(data.get("excluded_atom_ids", [])),
                self._json_dumps(data.get("conflict_ids", [])),
                self._json_dumps(data.get("source_counts", {})),
                self._json_dumps(data.get("selection_notes", [])),
                data["created_at"],
                self._json_dumps(data.get("metadata", {})),
            ),
        )
        conn.commit()
    return trace


def _db_get_knowledge_trace(self: Any, trace_id: str) -> Any | None:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_reasoning_traces WHERE trace_id = ?", (trace_id,))
        row = cursor.fetchone()
        return _db_row_to_knowledge_trace(self, row) if row else None


def _db_list_knowledge_traces(self: Any, project_id: str, department: str | None = None, limit: int = 100) -> list[Any]:
    query = "SELECT * FROM knowledge_reasoning_traces WHERE project_id = ?"
    params: list[Any] = [project_id]
    if department:
        query += " AND department = ?"
        params.append(department)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [_db_row_to_knowledge_trace(self, row) for row in cursor.fetchall()]


def _db_save_knowledge_rebuild_run(self: Any, run: Any) -> Any:
    data = run.model_dump(mode="json") if hasattr(run, "model_dump") else dict(run)
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO knowledge_rebuild_runs (
                run_id, project_id, status, source_types_json, source_count,
                atom_count, conflict_count, started_at, completed_at, duration_ms,
                warnings_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["run_id"],
                data["project_id"],
                data.get("status") or "complete",
                self._json_dumps(data.get("source_types", [])),
                int(data.get("source_count") or 0),
                int(data.get("atom_count") or 0),
                int(data.get("conflict_count") or 0),
                data["started_at"],
                data.get("completed_at") or "",
                int(data.get("duration_ms") or 0),
                self._json_dumps(data.get("warnings", [])),
                self._json_dumps(data.get("metadata", {})),
            ),
        )
        conn.commit()
    return run


def _db_get_knowledge_rebuild_run(self: Any, run_id: str) -> Any | None:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_rebuild_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        return _db_row_to_knowledge_rebuild(self, row) if row else None


def _db_list_knowledge_rebuild_runs(self: Any, project_id: str, limit: int = 25) -> list[Any]:
    with self._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM knowledge_rebuild_runs WHERE project_id = ? ORDER BY started_at DESC LIMIT ?",
            (project_id, max(1, min(int(limit), 100))),
        )
        return [_db_row_to_knowledge_rebuild(self, row) for row in cursor.fetchall()]


DatabaseStorage.save_knowledge_bible = _db_save_knowledge_bible
DatabaseStorage.get_knowledge_bible = _db_get_knowledge_bible
DatabaseStorage.get_knowledge_bible_content = _db_get_knowledge_bible_content
DatabaseStorage.list_knowledge_bibles = _db_list_knowledge_bibles
DatabaseStorage.delete_knowledge_sections_for_bible = _db_delete_knowledge_sections_for_bible
DatabaseStorage.save_knowledge_section = _db_save_knowledge_section
DatabaseStorage.list_knowledge_sections = _db_list_knowledge_sections
DatabaseStorage.save_knowledge_atom = _db_save_knowledge_atom
DatabaseStorage.list_knowledge_atoms = _db_list_knowledge_atoms
DatabaseStorage.delete_knowledge_atoms_for_source = _db_delete_knowledge_atoms_for_source
DatabaseStorage.delete_knowledge_atoms_for_project = _db_delete_knowledge_atoms_for_project
DatabaseStorage.save_knowledge_conflict = _db_save_knowledge_conflict
DatabaseStorage.get_knowledge_conflict = _db_get_knowledge_conflict
DatabaseStorage.list_knowledge_conflicts = _db_list_knowledge_conflicts
DatabaseStorage.save_knowledge_context_pack = _db_save_knowledge_context_pack
DatabaseStorage.save_knowledge_trace = _db_save_knowledge_trace
DatabaseStorage.get_knowledge_trace = _db_get_knowledge_trace
DatabaseStorage.list_knowledge_traces = _db_list_knowledge_traces
DatabaseStorage.save_knowledge_rebuild_run = _db_save_knowledge_rebuild_run
DatabaseStorage.get_knowledge_rebuild_run = _db_get_knowledge_rebuild_run
DatabaseStorage.list_knowledge_rebuild_runs = _db_list_knowledge_rebuild_runs


def _studio_brain_model_from_payload(self: Any, row: Any, model: Any) -> Any | None:
    if not row:
        return None
    return model(**self._json_loads(row["payload_json"], {}))


def _db_save_studio_brain_session(self: Any, session: Any) -> Any:
    data = session.model_dump(mode="json") if hasattr(session, "model_dump") else dict(session)

    def _write():
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO studio_brain_sessions (
                    session_id, project_id, purpose, status, active_plan_id,
                    latest_readiness_snapshot_id, created_by, created_at, updated_at,
                    closed_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["session_id"],
                    data["project_id"],
                    data.get("purpose") or "project_overview",
                    data.get("status") or "open",
                    data.get("active_plan_id") or "",
                    data.get("latest_readiness_snapshot_id") or "",
                    data.get("created_by") or "",
                    data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                    data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                    data.get("closed_at"),
                    self._json_dumps(data),
                ),
            )
            conn.commit()

    self._execute_write_with_retry("save_studio_brain_session", _write)
    return session


def _db_get_studio_brain_session(self: Any, session_id: str) -> Any | None:
    from app.models.studio_brain import StudioBrainExecutiveSession

    with self._get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json FROM studio_brain_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return _studio_brain_model_from_payload(self, row, StudioBrainExecutiveSession)


def _db_list_studio_brain_sessions(
    self: Any,
    project_id: str,
    status: str | None = None,
    limit: int = 20,
) -> list[Any]:
    from app.models.studio_brain import StudioBrainExecutiveSession

    query = "SELECT payload_json FROM studio_brain_sessions WHERE project_id = ?"
    params: list[Any] = [project_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 100)))
    with self._get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [StudioBrainExecutiveSession(**self._json_loads(row["payload_json"], {})) for row in rows]


def _db_save_studio_brain_department_signal(self: Any, signal: Any) -> Any:
    data = signal.model_dump(mode="json") if hasattr(signal, "model_dump") else dict(signal)

    def _write():
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO studio_brain_department_signals (
                    signal_id, session_id, project_id, agent_role, department_name,
                    status, purpose, requires_creator_decision, generated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["signal_id"],
                    data["session_id"],
                    data["project_id"],
                    data["agent_role"],
                    data.get("department_name") or "",
                    data.get("status") or "standby",
                    data.get("purpose") or "project_overview",
                    1 if data.get("requires_creator_decision") else 0,
                    data.get("generated_at") or datetime.utcnow().isoformat() + "Z",
                    self._json_dumps(data),
                ),
            )
            conn.commit()

    self._execute_write_with_retry("save_studio_brain_department_signal", _write)
    return signal


def _db_list_studio_brain_department_signals(self: Any, session_id: str) -> list[Any]:
    from app.models.studio_brain import StudioBrainDepartmentSignal

    with self._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT payload_json FROM studio_brain_department_signals
            WHERE session_id = ?
            ORDER BY generated_at DESC
            """,
            (session_id,),
        ).fetchall()
    return [StudioBrainDepartmentSignal(**self._json_loads(row["payload_json"], {})) for row in rows]


def _db_save_studio_brain_production_plan(self: Any, plan: Any) -> Any:
    data = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else dict(plan)

    def _write():
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO studio_brain_production_plans (
                    plan_id, session_id, project_id, purpose, status, phase,
                    readiness_snapshot_id, reasoning_trace_id, supersedes_plan_id,
                    created_at, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["plan_id"],
                    data["session_id"],
                    data["project_id"],
                    data.get("purpose") or "project_overview",
                    data.get("status") or "draft",
                    data.get("phase") or "",
                    data.get("readiness_snapshot_id") or "",
                    data.get("reasoning_trace_id") or "",
                    data.get("supersedes_plan_id"),
                    data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                    data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                    self._json_dumps(data),
                ),
            )
            conn.commit()

    self._execute_write_with_retry("save_studio_brain_production_plan", _write)
    return plan


def _db_get_studio_brain_production_plan(self: Any, plan_id: str) -> Any | None:
    from app.models.studio_brain import StudioBrainProductionPlan

    with self._get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json FROM studio_brain_production_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
    return _studio_brain_model_from_payload(self, row, StudioBrainProductionPlan)


def _db_save_studio_brain_conflict(self: Any, conflict: Any) -> Any:
    data = conflict.model_dump(mode="json") if hasattr(conflict, "model_dump") else dict(conflict)

    def _write():
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO studio_brain_conflicts (
                    conflict_id, session_id, project_id, conflict_type, severity,
                    status, requires_creator_decision, created_at, resolved_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["conflict_id"],
                    data["session_id"],
                    data["project_id"],
                    data["conflict_type"],
                    data.get("severity") or "advisory",
                    data.get("status") or "open",
                    1 if data.get("requires_creator_decision") else 0,
                    data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                    data.get("resolved_at"),
                    self._json_dumps(data),
                ),
            )
            conn.commit()

    self._execute_write_with_retry("save_studio_brain_conflict", _write)
    return conflict


def _db_get_studio_brain_conflict(self: Any, conflict_id: str) -> Any | None:
    from app.models.studio_brain import StudioBrainConflictCase

    with self._get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json FROM studio_brain_conflicts WHERE conflict_id = ?",
            (conflict_id,),
        ).fetchone()
    return _studio_brain_model_from_payload(self, row, StudioBrainConflictCase)


def _db_list_studio_brain_conflicts(
    self: Any,
    session_id: str,
    status: str | None = None,
) -> list[Any]:
    from app.models.studio_brain import StudioBrainConflictCase

    query = "SELECT payload_json FROM studio_brain_conflicts WHERE session_id = ?"
    params: list[Any] = [session_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    with self._get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [StudioBrainConflictCase(**self._json_loads(row["payload_json"], {})) for row in rows]


def _db_save_studio_brain_resolution_decision(self: Any, decision: Any) -> Any:
    data = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)

    def _write():
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO studio_brain_resolution_decisions (
                    resolution_id, conflict_id, session_id, project_id, mode,
                    resolved_by, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["resolution_id"],
                    data["conflict_id"],
                    data["session_id"],
                    data["project_id"],
                    data["mode"],
                    data.get("resolved_by") or "studio_brain",
                    data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                    self._json_dumps(data),
                ),
            )
            conn.commit()

    self._execute_write_with_retry("save_studio_brain_resolution_decision", _write)
    return decision


def _db_save_studio_brain_execution_directive(self: Any, directive: Any) -> Any:
    data = directive.model_dump(mode="json") if hasattr(directive, "model_dump") else dict(directive)

    def _write():
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO studio_brain_execution_directives (
                    directive_id, session_id, project_id, directive_type, status,
                    target_service, target_method, idempotency_key, source_plan_id,
                    source_conflict_id, requires_creator_approval, approval_gate_id,
                    created_at, dispatched_at, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["directive_id"],
                    data["session_id"],
                    data["project_id"],
                    data["directive_type"],
                    data.get("status") or "proposed",
                    data.get("target_service") or "",
                    data.get("target_method") or "",
                    data["idempotency_key"],
                    data.get("source_plan_id") or "",
                    data.get("source_conflict_id") or "",
                    1 if data.get("requires_creator_approval") else 0,
                    data.get("approval_gate_id") or "",
                    data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                    data.get("dispatched_at"),
                    data.get("updated_at") or datetime.utcnow().isoformat() + "Z",
                    self._json_dumps(data),
                ),
            )
            conn.commit()

    self._execute_write_with_retry("save_studio_brain_execution_directive", _write)
    return directive


def _db_get_studio_brain_execution_directive(self: Any, directive_id: str) -> Any | None:
    from app.models.studio_brain import StudioBrainExecutionDirective

    with self._get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json FROM studio_brain_execution_directives WHERE directive_id = ?",
            (directive_id,),
        ).fetchone()
    return _studio_brain_model_from_payload(self, row, StudioBrainExecutionDirective)


def _db_get_studio_brain_execution_directive_by_key(self: Any, project_id: str, idempotency_key: str) -> Any | None:
    from app.models.studio_brain import StudioBrainExecutionDirective

    with self._get_connection() as conn:
        row = conn.execute(
            """
            SELECT payload_json FROM studio_brain_execution_directives
            WHERE project_id = ? AND idempotency_key = ?
            """,
            (project_id, idempotency_key),
        ).fetchone()
    return _studio_brain_model_from_payload(self, row, StudioBrainExecutionDirective)


def _db_list_studio_brain_execution_directives(self: Any, session_id: str) -> list[Any]:
    from app.models.studio_brain import StudioBrainExecutionDirective

    with self._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT payload_json FROM studio_brain_execution_directives
            WHERE session_id = ?
            ORDER BY created_at DESC
            """,
            (session_id,),
        ).fetchall()
    return [StudioBrainExecutionDirective(**self._json_loads(row["payload_json"], {})) for row in rows]


def _db_save_studio_brain_readiness_snapshot(self: Any, snapshot: Any) -> Any:
    data = snapshot.model_dump(mode="json") if hasattr(snapshot, "model_dump") else dict(snapshot)

    def _write():
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO studio_brain_readiness_snapshots (
                    snapshot_id, session_id, project_id, phase, status, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["snapshot_id"],
                    data["session_id"],
                    data["project_id"],
                    data.get("phase") or "",
                    data.get("status") or "insufficient_evidence",
                    data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                    self._json_dumps(data),
                ),
            )
            conn.commit()

    self._execute_write_with_retry("save_studio_brain_readiness_snapshot", _write)
    return snapshot


def _db_get_studio_brain_readiness_snapshot(self: Any, snapshot_id: str) -> Any | None:
    from app.models.studio_brain import StudioBrainReadinessSnapshot

    with self._get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json FROM studio_brain_readiness_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
    return _studio_brain_model_from_payload(self, row, StudioBrainReadinessSnapshot)


def _db_save_studio_brain_reasoning_trace(self: Any, trace: Any) -> Any:
    data = trace.model_dump(mode="json") if hasattr(trace, "model_dump") else dict(trace)

    def _write():
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO studio_brain_reasoning_traces (
                    trace_id, session_id, project_id, trace_type, operation,
                    duration_ms, created_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["trace_id"],
                    data["session_id"],
                    data["project_id"],
                    data.get("trace_type") or "",
                    data.get("operation") or "",
                    int(data.get("duration_ms") or 0),
                    data.get("created_at") or datetime.utcnow().isoformat() + "Z",
                    self._json_dumps(data),
                ),
            )
            conn.commit()

    self._execute_write_with_retry("save_studio_brain_reasoning_trace", _write)
    return trace


def _db_list_studio_brain_reasoning_traces(self: Any, session_id: str) -> list[Any]:
    from app.models.studio_brain import StudioBrainReasoningTrace

    with self._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT payload_json FROM studio_brain_reasoning_traces
            WHERE session_id = ?
            ORDER BY created_at DESC
            """,
            (session_id,),
        ).fetchall()
    return [StudioBrainReasoningTrace(**self._json_loads(row["payload_json"], {})) for row in rows]


DatabaseStorage.save_studio_brain_session = _db_save_studio_brain_session
DatabaseStorage.get_studio_brain_session = _db_get_studio_brain_session
DatabaseStorage.list_studio_brain_sessions = _db_list_studio_brain_sessions
DatabaseStorage.save_studio_brain_department_signal = _db_save_studio_brain_department_signal
DatabaseStorage.list_studio_brain_department_signals = _db_list_studio_brain_department_signals
DatabaseStorage.save_studio_brain_production_plan = _db_save_studio_brain_production_plan
DatabaseStorage.get_studio_brain_production_plan = _db_get_studio_brain_production_plan
DatabaseStorage.save_studio_brain_conflict = _db_save_studio_brain_conflict
DatabaseStorage.get_studio_brain_conflict = _db_get_studio_brain_conflict
DatabaseStorage.list_studio_brain_conflicts = _db_list_studio_brain_conflicts
DatabaseStorage.save_studio_brain_resolution_decision = _db_save_studio_brain_resolution_decision
DatabaseStorage.save_studio_brain_execution_directive = _db_save_studio_brain_execution_directive
DatabaseStorage.get_studio_brain_execution_directive = _db_get_studio_brain_execution_directive
DatabaseStorage.get_studio_brain_execution_directive_by_key = _db_get_studio_brain_execution_directive_by_key
DatabaseStorage.list_studio_brain_execution_directives = _db_list_studio_brain_execution_directives
DatabaseStorage.save_studio_brain_readiness_snapshot = _db_save_studio_brain_readiness_snapshot
DatabaseStorage.get_studio_brain_readiness_snapshot = _db_get_studio_brain_readiness_snapshot
DatabaseStorage.save_studio_brain_reasoning_trace = _db_save_studio_brain_reasoning_trace
DatabaseStorage.list_studio_brain_reasoning_traces = _db_list_studio_brain_reasoning_traces


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

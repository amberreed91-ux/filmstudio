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

    def cascade_delete_project(self, project_id: str) -> bool:
        """Delete a project and ALL child records in correct order.
        Wraps the entire delete in a transaction for atomicity."""
        child_tables = [
            "surfaced_disagreements",
            "previs_images",
            "pitch_decks",
            "export_packages",
            "session_debriefs",
            "video_frame_analyses",
            "video_keyframes",
            "workflow_executions",
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
        seed_locked: bool = False
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
        import uuid
        from datetime import datetime
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            image_id = f"previs_{project_id}_{scene_id}_{shot_id or 'hero'}_{uuid.uuid4().hex[:8]}"
            now = datetime.now().isoformat()
            
            cursor.execute(
                """
                INSERT OR REPLACE INTO previs_images (
                    id, project_id, scene_id, shot_id, image_path,
                    job_id, status, prompt_used, fallback, previs_seed, seed_locked, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image_id,
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
                    "created_at": row_dict["created_at"],
                    "updated_at": row_dict.get("updated_at", row_dict["created_at"]),
                })
            
            return images

    def update_previs_image_status(
        self,
        job_id: str,
        status: str,
        image_path: Optional[str] = None
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
        from datetime import datetime
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            if image_path:
                cursor.execute(
                    """
                    UPDATE previs_images
                    SET status = ?, image_path = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (status, image_path, now, job_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE previs_images
                    SET status = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (status, now, job_id),
                )
            
            conn.commit()
            return cursor.rowcount > 0

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
                           created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                            now,
                            now,
                        ),
                    )
                conn.commit()
                cursor.execute("SELECT * FROM characters WHERE id = ? AND project_id = ?", (char_id, project_id))
                return dict(cursor.fetchone())

        return self._execute_write_with_retry("save_character", _write)

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
                    except:
                        pass
                
                if attempt.get("diff_json"):
                    try:
                        attempt["diff_json"] = json.loads(attempt["diff_json"])
                    except:
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
                except:
                    pass
            
            if attempt.get("diff_json"):
                try:
                    attempt["diff_json"] = json.loads(attempt["diff_json"])
                except:
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

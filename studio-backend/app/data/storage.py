import json
import os
import sqlite3
import os
import logging
import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Any, List, Dict
from datetime import datetime
from contextlib import contextmanager
from queue import Queue
import threading

from app.models import StudioProject, StudioOverview, BuildInfo, RenderJobModel, ShortFilmReview, ClipRevision, FinalShortFilmPackage, VideoAsset, VideoKeyframe, ShotBoundary, SceneMemoryRecord, ContinuityIssue, DirectorCommentary, FrameAnalysisRecord, StyleSignature, DirectorSignature, StyleDriftIssue, WorkflowDefinition, WorkflowExecution, VideoMetadataMatch, VisualEmbedding, CinematicMemoryRecord

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
        self._sqlite_timeout_seconds = 30.0
        self._sqlite_busy_timeout_ms = 10000
        self._connection_pool: Queue = Queue(maxsize=10)
        self._pool_size = 10
        self._lock = threading.Lock()
        self._init_schema()
        self._ensure_initial_data()
        self._log_sqlite_runtime_diagnostics()

    def _log_sqlite_runtime_diagnostics(self) -> None:
        journal_mode = "unknown"
        busy_timeout_ms = None
        try:
            with self._get_connection() as conn:
                journal_row = conn.execute("PRAGMA journal_mode").fetchone()
                if journal_row:
                    journal_mode = str(journal_row[0])
                busy_row = conn.execute("PRAGMA busy_timeout").fetchone()
                if busy_row:
                    busy_timeout_ms = int(busy_row[0])
        except Exception as exc:
            logger.warning("Unable to read SQLite journal_mode: %s", exc)
        logger.info(
            "SQLite runtime db_path=%s pid=%s journal_mode=%s connect_timeout_seconds=%s busy_timeout_ms=%s",
            self.db_path,
            os.getpid(),
            journal_mode,
            self._sqlite_timeout_seconds,
            busy_timeout_ms if busy_timeout_ms is not None else self._sqlite_busy_timeout_ms,
        )
        lsof_bin = shutil.which("lsof")
        if not lsof_bin:
            return
        for port in (8000, 8010, 8011):
            try:
                proc = subprocess.run(
                    [lsof_bin, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=0.5,
                )
                pids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
                unique_pids = sorted(set(pids))
                if len(unique_pids) > 1:
                    logger.warning(
                        "Multiple listeners detected on port %s pids=%s",
                        port,
                        ",".join(unique_pids),
                    )
            except Exception:
                continue

    def _create_connection(self):
        """Create a new database connection"""
        conn = sqlite3.connect(self.db_path, timeout=self._sqlite_timeout_seconds)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={self._sqlite_busy_timeout_ms}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _is_sqlite_lock_error(exc: BaseException) -> bool:
        message = str(exc).lower()
        return "database is locked" in message or "database table is locked" in message

    def _execute_write_with_retry(self, operation_name: str, operation):
        max_attempts = 5
        base_backoff_seconds = 0.05
        for attempt in range(1, max_attempts + 1):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if not self._is_sqlite_lock_error(exc) or attempt == max_attempts:
                    logger.error(
                        "SQLite write failed op=%s attempt=%s/%s error=%s",
                        operation_name,
                        attempt,
                        max_attempts,
                        exc,
                    )
                    raise
                sleep_seconds = base_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "SQLite locked op=%s attempt=%s/%s; retrying in %.2fs",
                    operation_name,
                    attempt,
                    max_attempts,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

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
            (7, "Add short_film_reviews table", """
                CREATE TABLE IF NOT EXISTS short_film_reviews (
                    review_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    output_url TEXT NOT NULL,
                    decision TEXT NOT NULL DEFAULT 'pending'
                        CHECK (decision IN ('pending', 'approved', 'needs_revision', 'rejected')),
                    reviewer TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (review_id != ''),
                    CHECK (project_id != ''),
                    CHECK (output_url != '')
                );
                
                CREATE INDEX IF NOT EXISTS idx_reviews_project ON short_film_reviews(project_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_decision ON short_film_reviews(decision);
                CREATE INDEX IF NOT EXISTS idx_reviews_created ON short_film_reviews(created_at);
            """),
            (8, "Add clip_revisions table", """
                CREATE TABLE IF NOT EXISTS clip_revisions (
                    revision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    review_id TEXT NOT NULL,
                    original_job_id TEXT NOT NULL,
                    new_job_id TEXT,
                    provider TEXT NOT NULL,
                    revision_prompt TEXT NOT NULL,
                    revision_reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'submitted', 'complete', 'failed', 'cancelled')),
                    output_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (revision_id != ''),
                    CHECK (project_id != ''),
                    CHECK (review_id != ''),
                    CHECK (original_job_id != ''),
                    CHECK (provider != ''),
                    CHECK (revision_prompt != ''),
                    CHECK (revision_reason != '')
                );
                
                CREATE INDEX IF NOT EXISTS idx_clip_revisions_project ON clip_revisions(project_id);
                CREATE INDEX IF NOT EXISTS idx_clip_revisions_review ON clip_revisions(review_id);
                CREATE INDEX IF NOT EXISTS idx_clip_revisions_original_job ON clip_revisions(original_job_id);
                CREATE INDEX IF NOT EXISTS idx_clip_revisions_new_job ON clip_revisions(new_job_id);
                CREATE INDEX IF NOT EXISTS idx_clip_revisions_status ON clip_revisions(status);
                CREATE INDEX IF NOT EXISTS idx_clip_revisions_created ON clip_revisions(created_at);
            """),
            (9, "Add final_short_film_packages table", """
                CREATE TABLE IF NOT EXISTS final_short_film_packages (
                    package_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    film_title TEXT NOT NULL,
                    final_output_url TEXT NOT NULL,
                    final_output_path TEXT,
                    review_id TEXT,
                    review_decision TEXT NOT NULL DEFAULT 'pending'
                        CHECK (review_decision IN ('pending', 'approved', 'needs_revision', 'rejected')),
                    runtime_seconds REAL,
                    scene_count INTEGER NOT NULL DEFAULT 0,
                    shot_count INTEGER NOT NULL DEFAULT 0,
                    render_job_ids TEXT,
                    revision_ids TEXT,
                    has_title_card INTEGER NOT NULL DEFAULT 0 CHECK (has_title_card IN (0, 1)),
                    has_end_card INTEGER NOT NULL DEFAULT 0 CHECK (has_end_card IN (0, 1)),
                    has_soundtrack INTEGER NOT NULL DEFAULT 0 CHECK (has_soundtrack IN (0, 1)),
                    package_status TEXT NOT NULL DEFAULT 'draft'
                        CHECK (package_status IN ('draft', 'ready_for_review', 'approved', 'packaged', 'archived')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (package_id != ''),
                    CHECK (project_id != ''),
                    CHECK (film_title != ''),
                    CHECK (final_output_url != '')
                );
                
                CREATE INDEX IF NOT EXISTS idx_final_packages_project ON final_short_film_packages(project_id);
                CREATE INDEX IF NOT EXISTS idx_final_packages_review ON final_short_film_packages(review_id);
                CREATE INDEX IF NOT EXISTS idx_final_packages_status ON final_short_film_packages(package_status);
                CREATE INDEX IF NOT EXISTS idx_final_packages_created ON final_short_film_packages(created_at);
            """),
            (10, "Add video_assets table", """
                CREATE TABLE IF NOT EXISTS video_assets (
                    asset_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_type TEXT NOT NULL
                        CHECK (source_type IN ('uploaded_file', 'generated_output', 'external_url', 'local_file')),
                    source_url TEXT,
                    local_path TEXT,
                    title TEXT NOT NULL,
                    description TEXT,
                    duration_seconds REAL,
                    file_size_bytes INTEGER,
                    status TEXT NOT NULL DEFAULT 'registered'
                        CHECK (status IN ('registered', 'available', 'analysis_pending', 'analyzed', 'failed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (asset_id != ''),
                    CHECK (project_id != ''),
                    CHECK (title != '')
                );

                CREATE INDEX IF NOT EXISTS idx_video_assets_project ON video_assets(project_id);
                CREATE INDEX IF NOT EXISTS idx_video_assets_status ON video_assets(status);
                CREATE INDEX IF NOT EXISTS idx_video_assets_source_type ON video_assets(source_type);
                CREATE INDEX IF NOT EXISTS idx_video_assets_created ON video_assets(created_at);
            """),
            (11, "Add video_keyframes table", """
                CREATE TABLE IF NOT EXISTS video_keyframes (
                    keyframe_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    timestamp_seconds REAL NOT NULL,
                    frame_path TEXT NOT NULL,
                    frame_url TEXT,
                    frame_index INTEGER NOT NULL,
                    extraction_reason TEXT NOT NULL DEFAULT 'interval'
                        CHECK (extraction_reason IN ('interval', 'shot_boundary', 'manual', 'representative')),
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (keyframe_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (project_id != ''),
                    CHECK (frame_path != '')
                );

                CREATE INDEX IF NOT EXISTS idx_video_keyframes_asset ON video_keyframes(asset_id);
                CREATE INDEX IF NOT EXISTS idx_video_keyframes_project ON video_keyframes(project_id);
                CREATE INDEX IF NOT EXISTS idx_video_keyframes_created ON video_keyframes(created_at);
                CREATE INDEX IF NOT EXISTS idx_video_keyframes_frame_index ON video_keyframes(frame_index);
            """),
            (12, "Add shot_boundaries table", """
                CREATE TABLE IF NOT EXISTS shot_boundaries (
                    boundary_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    transition_type TEXT NOT NULL DEFAULT 'hard_cut'
                        CHECK (transition_type IN ('hard_cut', 'fade', 'dissolve')),
                    metadata TEXT,
                    CHECK (boundary_id != ''),
                    CHECK (asset_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_shot_boundaries_asset ON shot_boundaries(asset_id);
                CREATE INDEX IF NOT EXISTS idx_shot_boundaries_start ON shot_boundaries(start_time);
            """),
            (13, "Add video_scene_memories table", """
                CREATE TABLE IF NOT EXISTS video_scene_memories (
                    memory_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    dominant_mood TEXT NOT NULL,
                    visual_style TEXT NOT NULL,
                    lighting_style TEXT NOT NULL,
                    pacing_profile TEXT NOT NULL,
                    character_presence TEXT,
                    composition_patterns TEXT,
                    cinematic_notes TEXT NOT NULL,
                    embeddings TEXT,
                    created_at TEXT NOT NULL,
                    CHECK (memory_id != ''),
                    CHECK (asset_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_video_scene_memories_asset ON video_scene_memories(asset_id);
                CREATE INDEX IF NOT EXISTS idx_video_scene_memories_created ON video_scene_memories(created_at);
            """),
            (14, "Add continuity_issues table", """
                CREATE TABLE IF NOT EXISTS continuity_issues (
                    issue_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium'
                        CHECK (severity IN ('low', 'medium', 'high')),
                    description TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    notes TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    CHECK (issue_id != ''),
                    CHECK (project_id != ''),
                    CHECK (asset_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_continuity_issues_project ON continuity_issues(project_id);
                CREATE INDEX IF NOT EXISTS idx_continuity_issues_asset ON continuity_issues(asset_id);
                CREATE INDEX IF NOT EXISTS idx_continuity_issues_category ON continuity_issues(category);
            """),
            (15, "Add director_commentary table", """
                CREATE TABLE IF NOT EXISTS director_commentary (
                    commentary_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    scene_reference TEXT NOT NULL,
                    interpretation TEXT NOT NULL,
                    emotional_read TEXT NOT NULL,
                    visual_language_notes TEXT NOT NULL,
                    pacing_notes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (commentary_id != ''),
                    CHECK (asset_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_director_commentary_asset ON director_commentary(asset_id);
                CREATE INDEX IF NOT EXISTS idx_director_commentary_created ON director_commentary(created_at);
            """),
            (16, "Add video_frame_analyses table", """
                CREATE TABLE IF NOT EXISTS video_frame_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    keyframe_id TEXT,
                    caption TEXT,
                    mood_tags TEXT,
                    lighting_tags TEXT,
                    camera_tags TEXT,
                    embeddings TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (analysis_id != ''),
                    CHECK (asset_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_video_frame_analyses_asset ON video_frame_analyses(asset_id);
                CREATE INDEX IF NOT EXISTS idx_video_frame_analyses_keyframe ON video_frame_analyses(keyframe_id);
                CREATE INDEX IF NOT EXISTS idx_video_frame_analyses_created ON video_frame_analyses(created_at);
            """),
            (17, "Add style_signatures table", """
                CREATE TABLE IF NOT EXISTS style_signatures (
                    signature_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    framing_tendencies TEXT,
                    pacing_patterns TEXT,
                    color_motifs TEXT,
                    camera_movement_patterns TEXT,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    advisory_only INTEGER NOT NULL DEFAULT 1 CHECK (advisory_only IN (0, 1)),
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    CHECK (signature_id != ''),
                    CHECK (project_id != '')
                );

                CREATE INDEX IF NOT EXISTS idx_style_signatures_project ON style_signatures(project_id);
                CREATE INDEX IF NOT EXISTS idx_style_signatures_created ON style_signatures(created_at);
            """),
            (18, "Add render job recovery columns", """
                ALTER TABLE render_jobs ADD COLUMN last_polled_at TEXT;
                ALTER TABLE render_jobs ADD COLUMN recovery_status TEXT NOT NULL DEFAULT 'none';
            """),
(19, "Add workflow_executions table", """
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    execution_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
                    started_at TEXT,
                    completed_at TEXT,
                    current_step TEXT,
                    completed_steps TEXT,
                    failed_steps TEXT,
                    step_results TEXT,
                    inputs TEXT,
                    outputs TEXT,
                    error_message TEXT,
                    progress_percentage REAL NOT NULL DEFAULT 0.0,
                    CHECK (execution_id != ''),
                    CHECK (workflow_id != ''),
                    CHECK (project_id != ''),
                    CHECK (progress_percentage >= 0.0 AND progress_percentage <= 100.0)
                );

                CREATE INDEX IF NOT EXISTS idx_workflow_executions_workflow ON workflow_executions(workflow_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_executions_project ON workflow_executions(project_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status);
                CREATE INDEX IF NOT EXISTS idx_workflow_executions_started ON workflow_executions(started_at);
            """),
            (20, "Add video_metadata_matches table", """
                CREATE TABLE IF NOT EXISTS video_metadata_matches (
                    match_id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL,
                    metadata_id TEXT NOT NULL,
                    project_id TEXT,
                    match_status TEXT NOT NULL DEFAULT 'proposed'
                        CHECK (match_status IN ('proposed', 'confirmed', 'rejected', 'auto_confirmed')),
                    match_confidence REAL NOT NULL DEFAULT 0.0
                        CHECK (match_confidence >= 0.0 AND match_confidence <= 1.0),
                    match_reason TEXT,
                    matched_fields TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (match_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (metadata_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_video_metadata_matches_asset ON video_metadata_matches(asset_id);
                CREATE INDEX IF NOT EXISTS idx_video_metadata_matches_status ON video_metadata_matches(match_status);
            """),
            (21, "Expand video_keyframes schema for visual evidence metadata", """
                ALTER TABLE video_keyframes ADD COLUMN source_type TEXT;
                ALTER TABLE video_keyframes ADD COLUMN image_path TEXT;
                ALTER TABLE video_keyframes ADD COLUMN image_url TEXT;
                ALTER TABLE video_keyframes ADD COLUMN width INTEGER;
                ALTER TABLE video_keyframes ADD COLUMN height INTEGER;
                ALTER TABLE video_keyframes ADD COLUMN extraction_method TEXT;
            """),
            (22, "Add frame_analyses table", """
                CREATE TABLE IF NOT EXISTS frame_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    keyframe_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    caption TEXT,
                    visual_summary TEXT,
                    mood_tags TEXT,
                    lighting_tags TEXT,
                    composition_tags TEXT,
                    color_palette TEXT,
                    detected_subjects TEXT,
                    camera_notes TEXT,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    provider TEXT NOT NULL DEFAULT 'unavailable',
                    model TEXT NOT NULL DEFAULT 'unconfigured',
                    status TEXT NOT NULL DEFAULT 'unavailable',
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (analysis_id != ''),
                    CHECK (keyframe_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_frame_analyses_asset ON frame_analyses(asset_id);
                CREATE INDEX IF NOT EXISTS idx_frame_analyses_project ON frame_analyses(project_id);
                CREATE INDEX IF NOT EXISTS idx_frame_analyses_keyframe ON frame_analyses(keyframe_id);
                CREATE INDEX IF NOT EXISTS idx_frame_analyses_created ON frame_analyses(created_at);
            """),
            (23, "Add visual_embeddings table", """
                CREATE TABLE IF NOT EXISTS visual_embeddings (
                    embedding_id TEXT PRIMARY KEY,
                    keyframe_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'unavailable',
                    model TEXT NOT NULL DEFAULT 'unconfigured',
                    vector_dimension INTEGER NOT NULL DEFAULT 0,
                    embedding_vector TEXT,
                    status TEXT NOT NULL DEFAULT 'unavailable',
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (embedding_id != ''),
                    CHECK (keyframe_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (project_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_visual_embeddings_keyframe ON visual_embeddings(keyframe_id);
                CREATE INDEX IF NOT EXISTS idx_visual_embeddings_asset ON visual_embeddings(asset_id);
                CREATE INDEX IF NOT EXISTS idx_visual_embeddings_project ON visual_embeddings(project_id);
            """),
            (24, "Add cinematic_memory_records table", """
                CREATE TABLE IF NOT EXISTS cinematic_memory_records (
                    memory_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    keyframe_id TEXT NOT NULL,
                    analysis_id TEXT,
                    embedding_id TEXT,
                    memory_type TEXT NOT NULL DEFAULT 'keyframe_memory',
                    summary TEXT,
                    visual_tags TEXT,
                    emotional_tags TEXT,
                    composition_tags TEXT,
                    lighting_tags TEXT,
                    searchable_text TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    CHECK (memory_id != ''),
                    CHECK (project_id != ''),
                    CHECK (asset_id != ''),
                    CHECK (keyframe_id != '')
                );
                CREATE INDEX IF NOT EXISTS idx_cinematic_memory_project ON cinematic_memory_records(project_id);
                CREATE INDEX IF NOT EXISTS idx_cinematic_memory_asset ON cinematic_memory_records(asset_id);
                CREATE INDEX IF NOT EXISTS idx_cinematic_memory_keyframe ON cinematic_memory_records(keyframe_id);
            """),
            (25, "Expand continuity_issues table with keyframe refs and issue_type", """
                CREATE TABLE IF NOT EXISTS continuity_issues_new (
                    issue_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_keyframe_id TEXT,
                    compared_keyframe_id TEXT,
                    source_asset_id TEXT,
                    compared_asset_id TEXT,
                    issue_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium'
                        CHECK (severity IN ('low', 'medium', 'high')),
                    confidence REAL NOT NULL DEFAULT 0.0,
                    description TEXT NOT NULL,
                    evidence TEXT,
                    recommendation TEXT,
                    notes TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    CHECK (issue_id != ''),
                    CHECK (project_id != ''),
                    CHECK (issue_type != '')
                );
                
                -- Copy data from old table with mapping
                INSERT OR IGNORE INTO continuity_issues_new 
                    (issue_id, project_id, source_asset_id, issue_type, severity, description, confidence, notes, metadata, created_at)
                    SELECT issue_id, project_id, asset_id, category, severity, description, confidence, notes, metadata, created_at
                    FROM continuity_issues;
                
                -- Rename tables
                DROP TABLE IF EXISTS continuity_issues;
                ALTER TABLE continuity_issues_new RENAME TO continuity_issues;
                
                -- Recreate indexes
                CREATE INDEX IF NOT EXISTS idx_continuity_issues_project ON continuity_issues(project_id);
                CREATE INDEX IF NOT EXISTS idx_continuity_issues_source_keyframe ON continuity_issues(source_keyframe_id);
                CREATE INDEX IF NOT EXISTS idx_continuity_issues_compared_keyframe ON continuity_issues(compared_keyframe_id);
                CREATE INDEX IF NOT EXISTS idx_continuity_issues_issue_type ON continuity_issues(issue_type);
            """),
            (26, "Add director_signatures and style_drift_issues tables", """
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
                CREATE INDEX IF NOT EXISTS idx_director_signatures_created ON director_signatures(project_id, created_at);

                CREATE TABLE IF NOT EXISTS style_drift_issues (
                    drift_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    keyframe_id TEXT NOT NULL DEFAULT '',
                    asset_id TEXT NOT NULL DEFAULT '',
                    drift_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium'
                        CHECK (severity IN ('low', 'medium', 'high')),
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
                CREATE INDEX IF NOT EXISTS idx_style_drift_keyframe ON style_drift_issues(keyframe_id);
                CREATE INDEX IF NOT EXISTS idx_style_drift_asset ON style_drift_issues(asset_id);
                CREATE INDEX IF NOT EXISTS idx_style_drift_type ON style_drift_issues(drift_type);
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
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(projects)")
                columns = [row[1] for row in cursor.fetchall()]
                payload = json.dumps(project.model_dump(mode='json'))
                if {"project_id", "data", "created_at", "updated_at"}.issubset(set(columns)):
                    now = datetime.now().isoformat()
                    cursor.execute(
                        """INSERT OR REPLACE INTO projects (project_id, data, created_at, updated_at) 
                           VALUES (?, ?, COALESCE((SELECT created_at FROM projects WHERE project_id = ?), ?), ?)""",
                        (project.project_id, payload, project.project_id, now, project.updated_at)
                    )
                elif {"project_id", "data", "updated_at"}.issubset(set(columns)):
                    cursor.execute(
                        """INSERT OR REPLACE INTO projects (project_id, data, updated_at)
                           VALUES (?, ?, ?)""",
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
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO render_jobs 
                       (id, project_id, shot_id, provider, provider_job_id, status, progress,
                        input_payload, output_payload, error_message, last_polled_at, retry_count, recovery_status,
                        created_at, updated_at, completed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job.id, job.project_id, job.shot_id, job.provider, job.provider_job_id,
                        job.status, job.progress,
                        json.dumps(job.input_payload.model_dump()) if job.input_payload else None,
                        json.dumps(job.output_payload.model_dump()) if job.output_payload else None,
                        job.error_message, job.last_polled_at, job.retry_count, job.recovery_status,
                        job.created_at, job.updated_at, job.completed_at
                    )
                )
                conn.commit()
        self._execute_write_with_retry("save_job", _write)
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

    # Short Film Review Persistence
    def save_review(self, review) -> Any:
        from app.models import ShortFilmReview
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO short_film_reviews 
                       (review_id, project_id, output_url, decision, reviewer, notes, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        review.review_id,
                        review.project_id,
                        review.output_url,
                        review.decision,
                        review.reviewer,
                        review.notes,
                        review.created_at,
                        review.updated_at,
                        json.dumps(review.metadata) if review.metadata else "{}"
                    )
                )
                conn.commit()
        self._execute_write_with_retry("save_review", _write)
        return review

    def get_review(self, review_id: str) -> Optional[ShortFilmReview]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM short_film_reviews WHERE review_id = ?", (review_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_review(row)
            return None

    def list_reviews_for_project(self, project_id: str) -> List[ShortFilmReview]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM short_film_reviews WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,)
            )
            return [self._row_to_review(row) for row in cursor.fetchall()]

    def update_review(self, review) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE short_film_reviews 
                   SET decision = ?, reviewer = ?, notes = ?, updated_at = ?, metadata = ?
                   WHERE review_id = ?""",
                (
                    review.decision,
                    review.reviewer,
                    review.notes,
                    review.updated_at,
                    json.dumps(review.metadata) if review.metadata else "{}",
                    review.review_id
                )
            )
            conn.commit()
        return review

    def _row_to_review(self, row: sqlite3.Row) -> ShortFilmReview:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        
        return ShortFilmReview(
            review_id=row["review_id"],
            project_id=row["project_id"],
            output_url=row["output_url"],
            decision=row["decision"],
            reviewer=row["reviewer"] or "",
            notes=row["notes"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata
        )

    # Clip Revision Persistence
    def save_clip_revision(self, revision) -> Any:
        from app.models import ClipRevision
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO clip_revisions 
                       (revision_id, project_id, review_id, original_job_id, new_job_id, provider, 
                        revision_prompt, revision_reason, status, output_url, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                        json.dumps(revision.metadata) if revision.metadata else "{}"
                    )
                )
                conn.commit()
        self._execute_write_with_retry("save_clip_revision", _write)
        return revision

    def get_clip_revision(self, revision_id: str) -> Optional[ClipRevision]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clip_revisions WHERE revision_id = ?", (revision_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_clip_revision(row)
            return None

    def list_clip_revisions_for_project(self, project_id: str) -> List[ClipRevision]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM clip_revisions WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,)
            )
            return [self._row_to_clip_revision(row) for row in cursor.fetchall()]

    def list_clip_revisions_for_review(self, review_id: str) -> List[ClipRevision]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM clip_revisions WHERE review_id = ? ORDER BY created_at DESC",
                (review_id,)
            )
            return [self._row_to_clip_revision(row) for row in cursor.fetchall()]

    def update_clip_revision(self, revision) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE clip_revisions 
                   SET new_job_id = ?, status = ?, output_url = ?, updated_at = ?, metadata = ?
                   WHERE revision_id = ?""",
                (
                    revision.new_job_id,
                    revision.status,
                    revision.output_url,
                    revision.updated_at,
                    json.dumps(revision.metadata) if revision.metadata else "{}",
                    revision.revision_id
                )
            )
            conn.commit()
        return revision

    def _row_to_clip_revision(self, row: sqlite3.Row) -> ClipRevision:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        
        return ClipRevision(
            revision_id=row["revision_id"],
            project_id=row["project_id"],
            review_id=row["review_id"],
            original_job_id=row["original_job_id"],
            new_job_id=row["new_job_id"],
            provider=row["provider"],
            revision_prompt=row["revision_prompt"],
            revision_reason=row["revision_reason"],
            status=row["status"],
            output_url=row["output_url"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata
        )

    # Final Short Film Package Persistence
    def save_final_short_film_package(self, package) -> Any:
        from app.models import FinalShortFilmPackage
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO final_short_film_packages 
                       (package_id, project_id, film_title, final_output_url, final_output_path, review_id, 
                        review_decision, runtime_seconds, scene_count, shot_count, render_job_ids, revision_ids,
                        has_title_card, has_end_card, has_soundtrack, package_status, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        package.package_id,
                        package.project_id,
                        package.film_title,
                        package.final_output_url,
                        package.final_output_path,
                        package.review_id,
                        package.review_decision,
                        package.runtime_seconds,
                        package.scene_count,
                        package.shot_count,
                        json.dumps(package.render_job_ids) if package.render_job_ids else "[]",
                        json.dumps(package.revision_ids) if package.revision_ids else "[]",
                        int(package.has_title_card),
                        int(package.has_end_card),
                        int(package.has_soundtrack),
                        package.package_status,
                        package.created_at,
                        package.updated_at,
                        json.dumps(package.metadata) if package.metadata else "{}"
                    )
                )
                conn.commit()
        self._execute_write_with_retry("save_final_short_film_package", _write)
        return package

    def get_final_short_film_package(self, package_id: str) -> Optional[FinalShortFilmPackage]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM final_short_film_packages WHERE package_id = ?", (package_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_final_short_film_package(row)
            return None

    def list_final_short_film_packages_for_project(self, project_id: str) -> List[FinalShortFilmPackage]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM final_short_film_packages WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,)
            )
            return [self._row_to_final_short_film_package(row) for row in cursor.fetchall()]

    def update_final_short_film_package(self, package) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE final_short_film_packages 
                   SET package_status = ?, updated_at = ?, metadata = ?
                   WHERE package_id = ?""",
                (
                    package.package_status,
                    package.updated_at,
                    json.dumps(package.metadata) if package.metadata else "{}",
                    package.package_id
                )
            )
            conn.commit()
        return package

    def _row_to_final_short_film_package(self, row: sqlite3.Row) -> FinalShortFilmPackage:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        
        render_job_ids = []
        if row["render_job_ids"]:
            try:
                render_job_ids = json.loads(row["render_job_ids"])
            except json.JSONDecodeError:
                render_job_ids = []
        
        revision_ids = []
        if row["revision_ids"]:
            try:
                revision_ids = json.loads(row["revision_ids"])
            except json.JSONDecodeError:
                revision_ids = []
        
        return FinalShortFilmPackage(
            package_id=row["package_id"],
            project_id=row["project_id"],
            film_title=row["film_title"],
            final_output_url=row["final_output_url"],
            final_output_path=row["final_output_path"],
            review_id=row["review_id"],
            review_decision=row["review_decision"],
            runtime_seconds=row["runtime_seconds"],
            scene_count=row["scene_count"],
            shot_count=row["shot_count"],
            render_job_ids=render_job_ids,
            revision_ids=revision_ids,
            has_title_card=bool(row["has_title_card"]),
            has_end_card=bool(row["has_end_card"]),
            has_soundtrack=bool(row["has_soundtrack"]),
            package_status=row["package_status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata
        )

    # Video Asset Persistence
    def save_video_asset(self, asset: VideoAsset) -> VideoAsset:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO video_assets
                       (asset_id, project_id, source_type, source_url, local_path, title, description,
                        duration_seconds, file_size_bytes, status, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                        json.dumps(asset.metadata) if asset.metadata else "{}",
                    ),
                )
                conn.commit()
        self._execute_write_with_retry("save_video_asset", _write)
        return asset

    def get_video_asset(self, asset_id: str) -> Optional[VideoAsset]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_assets WHERE asset_id = ?", (asset_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_video_asset(row)
            return None

    def list_video_assets_for_project(self, project_id: str) -> List[VideoAsset]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_assets WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_video_asset(row) for row in cursor.fetchall()]

    def list_video_assets(self, source_type: Optional[str] = None) -> List[VideoAsset]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if source_type:
                cursor.execute(
                    "SELECT * FROM video_assets WHERE source_type = ? ORDER BY created_at DESC",
                    (source_type,),
                )
            else:
                cursor.execute("SELECT * FROM video_assets ORDER BY created_at DESC")
            return [self._row_to_video_asset(row) for row in cursor.fetchall()]

    def update_video_asset(self, asset: VideoAsset) -> VideoAsset:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE video_assets
                   SET project_id = ?, source_type = ?, source_url = ?, local_path = ?, title = ?, description = ?,
                       duration_seconds = ?, file_size_bytes = ?, status = ?, updated_at = ?, metadata = ?
                   WHERE asset_id = ?""",
                (
                    asset.project_id,
                    asset.source_type,
                    asset.source_url,
                    asset.local_path,
                    asset.title,
                    asset.description,
                    asset.duration_seconds,
                    asset.file_size_bytes,
                    asset.status,
                    asset.updated_at,
                    json.dumps(asset.metadata) if asset.metadata else "{}",
                    asset.asset_id,
                ),
            )
            conn.commit()
        return asset

    def _row_to_video_asset(self, row: sqlite3.Row) -> VideoAsset:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}

        return VideoAsset(
            asset_id=row["asset_id"],
            project_id=row["project_id"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            local_path=row["local_path"],
            title=row["title"],
            description=row["description"],
            duration_seconds=row["duration_seconds"],
            file_size_bytes=row["file_size_bytes"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata,
        )

    # Video Keyframe Persistence
    def save_video_keyframe(self, keyframe: VideoKeyframe) -> VideoKeyframe:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(video_keyframes)")
            columns = {row[1] for row in cursor.fetchall()}
            image_path = keyframe.image_path or keyframe.frame_path or ""
            image_url = keyframe.image_url or keyframe.frame_url
            extraction_method = keyframe.extraction_method or keyframe.extraction_reason or "interval"
            source_type = keyframe.source_type or "unknown"
            if {"source_type", "image_path", "image_url", "width", "height", "extraction_method"}.issubset(columns):
                cursor.execute(
                    """INSERT OR REPLACE INTO video_keyframes
                       (keyframe_id, asset_id, project_id, source_type, timestamp_seconds, frame_index,
                        image_path, image_url, width, height, extraction_method, frame_path, frame_url,
                        extraction_reason, created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        keyframe.keyframe_id,
                        keyframe.asset_id,
                        keyframe.project_id,
                        source_type,
                        keyframe.timestamp_seconds,
                        keyframe.frame_index,
                        image_path,
                        image_url,
                        keyframe.width,
                        keyframe.height,
                        extraction_method,
                        image_path,
                        image_url,
                        extraction_method,
                        keyframe.created_at,
                        json.dumps(keyframe.metadata) if keyframe.metadata else "{}",
                    ),
                )
            else:
                cursor.execute(
                    """INSERT OR REPLACE INTO video_keyframes
                       (keyframe_id, asset_id, project_id, timestamp_seconds, frame_path, frame_url,
                        frame_index, extraction_reason, created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        keyframe.keyframe_id,
                        keyframe.asset_id,
                        keyframe.project_id,
                        keyframe.timestamp_seconds,
                        image_path,
                        image_url,
                        keyframe.frame_index,
                        extraction_method,
                        keyframe.created_at,
                        json.dumps(keyframe.metadata) if keyframe.metadata else "{}",
                    ),
                )
            conn.commit()
        return keyframe

    def get_video_keyframe(self, keyframe_id: str) -> Optional[VideoKeyframe]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_keyframes WHERE keyframe_id = ?", (keyframe_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_video_keyframe(row)
            return None

    def list_video_keyframes_for_asset(self, asset_id: str) -> List[VideoKeyframe]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_keyframes WHERE asset_id = ? ORDER BY frame_index ASC, timestamp_seconds ASC",
                (asset_id,),
            )
            return [self._row_to_video_keyframe(row) for row in cursor.fetchall()]

    def list_video_keyframes_for_project(self, project_id: str) -> List[VideoKeyframe]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_keyframes WHERE project_id = ? ORDER BY created_at DESC, frame_index ASC",
                (project_id,),
            )
            return [self._row_to_video_keyframe(row) for row in cursor.fetchall()]

    def delete_video_keyframes_for_asset(self, asset_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM video_keyframes WHERE asset_id = ?", (asset_id,))
            conn.commit()
            return cursor.rowcount

    def _row_to_video_keyframe(self, row: sqlite3.Row) -> VideoKeyframe:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}

        return VideoKeyframe(
            keyframe_id=row["keyframe_id"],
            asset_id=row["asset_id"],
            project_id=row["project_id"],
            source_type=row["source_type"] if "source_type" in row.keys() and row["source_type"] else "unknown",
            timestamp_seconds=row["timestamp_seconds"],
            image_path=(row["image_path"] if "image_path" in row.keys() and row["image_path"] else row["frame_path"]),
            image_url=(row["image_url"] if "image_url" in row.keys() and row["image_url"] else row["frame_url"]),
            frame_index=row["frame_index"],
            width=row["width"] if "width" in row.keys() else None,
            height=row["height"] if "height" in row.keys() else None,
            extraction_method=(row["extraction_method"] if "extraction_method" in row.keys() and row["extraction_method"] else row["extraction_reason"]),
            frame_path=row["frame_path"],
            frame_url=row["frame_url"],
            extraction_reason=row["extraction_reason"],
            created_at=row["created_at"],
            metadata=metadata,
        )

    # Video Metadata Match Persistence
    def save_video_metadata_match(self, match: VideoMetadataMatch) -> VideoMetadataMatch:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO video_metadata_matches
                       (match_id, asset_id, metadata_id, project_id, match_status, match_confidence,
                        match_reason, matched_fields, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        match.match_id,
                        match.asset_id,
                        match.metadata_id,
                        match.project_id,
                        match.match_status,
                        match.match_confidence,
                        match.match_reason,
                        json.dumps(match.matched_fields) if match.matched_fields else "[]",
                        match.created_at,
                        match.updated_at,
                        json.dumps(match.metadata) if match.metadata else "{}",
                    ),
                )
                conn.commit()
        self._execute_write_with_retry("save_video_metadata_match", _write)
        return match

    def get_video_metadata_match(self, match_id: str) -> Optional[VideoMetadataMatch]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_metadata_matches WHERE match_id = ?", (match_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_video_metadata_match(row)
            return None

    def list_video_metadata_matches_for_asset(self, asset_id: str) -> List[VideoMetadataMatch]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_metadata_matches WHERE asset_id = ? ORDER BY match_confidence DESC",
                (asset_id,),
            )
            return [self._row_to_video_metadata_match(row) for row in cursor.fetchall()]

    def list_video_metadata_matches(self, status: Optional[str] = None) -> List[VideoMetadataMatch]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM video_metadata_matches WHERE match_status = ? ORDER BY created_at DESC",
                    (status,),
                )
            else:
                cursor.execute("SELECT * FROM video_metadata_matches ORDER BY created_at DESC")
            return [self._row_to_video_metadata_match(row) for row in cursor.fetchall()]

    def delete_video_metadata_match(self, match_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM video_metadata_matches WHERE match_id = ?", (match_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_video_metadata_match(self, row: sqlite3.Row) -> VideoMetadataMatch:
        matched_fields = []
        if row["matched_fields"]:
            try:
                matched_fields = json.loads(row["matched_fields"])
            except json.JSONDecodeError:
                matched_fields = []

        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}

        return VideoMetadataMatch(
            match_id=row["match_id"],
            asset_id=row["asset_id"],
            metadata_id=row["metadata_id"],
            project_id=row["project_id"],
            match_status=row["match_status"],
            match_confidence=row["match_confidence"],
            match_reason=row["match_reason"] or "",
            matched_fields=matched_fields,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata,
        )

    # Shot Boundary Persistence
    def save_shot_boundary(self, boundary: ShotBoundary) -> ShotBoundary:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO shot_boundaries
                   (boundary_id, asset_id, start_time, end_time, confidence, transition_type, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    boundary.boundary_id,
                    boundary.asset_id,
                    boundary.start_time,
                    boundary.end_time,
                    boundary.confidence,
                    boundary.transition_type,
                    json.dumps(boundary.metadata) if boundary.metadata else "{}",
                ),
            )
            conn.commit()
        return boundary

    def list_shot_boundaries_for_asset(self, asset_id: str) -> List[ShotBoundary]:
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

    def _row_to_shot_boundary(self, row: sqlite3.Row) -> ShotBoundary:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        return ShotBoundary(
            boundary_id=row["boundary_id"],
            asset_id=row["asset_id"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            confidence=row["confidence"],
            transition_type=row["transition_type"],
            metadata=metadata,
        )

    # Scene Memory Persistence
    def save_video_scene_memory(self, memory: SceneMemoryRecord) -> SceneMemoryRecord:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO video_scene_memories
                   (memory_id, asset_id, dominant_mood, visual_style, lighting_style, pacing_profile,
                    character_presence, composition_patterns, cinematic_notes, embeddings, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory.memory_id,
                    memory.asset_id,
                    memory.dominant_mood,
                    memory.visual_style,
                    memory.lighting_style,
                    memory.pacing_profile,
                    json.dumps(memory.character_presence or []),
                    json.dumps(memory.composition_patterns or []),
                    memory.cinematic_notes,
                    json.dumps(memory.embeddings) if memory.embeddings is not None else None,
                    memory.created_at,
                ),
            )
            conn.commit()
        return memory

    def list_video_scene_memories_for_asset(self, asset_id: str) -> List[SceneMemoryRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_scene_memories WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_video_scene_memory(row) for row in cursor.fetchall()]

    def get_video_scene_memory(self, memory_id: str) -> Optional[SceneMemoryRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_scene_memories WHERE memory_id = ?", (memory_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_video_scene_memory(row)
            return None

    def list_video_scene_memories(self, limit: int = 200) -> List[SceneMemoryRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_scene_memories ORDER BY created_at DESC LIMIT ?", (limit,))
            return [self._row_to_video_scene_memory(row) for row in cursor.fetchall()]

    def _row_to_video_scene_memory(self, row: sqlite3.Row) -> SceneMemoryRecord:
        def _load_list(value: Any) -> List[str]:
            if not value:
                return []
            try:
                loaded = json.loads(value)
                return [str(v) for v in loaded] if isinstance(loaded, list) else []
            except Exception:
                return []

        embeddings = None
        if row["embeddings"]:
            try:
                loaded_embeddings = json.loads(row["embeddings"])
                if isinstance(loaded_embeddings, list):
                    embeddings = [float(v) for v in loaded_embeddings]
            except Exception:
                embeddings = None

        return SceneMemoryRecord(
            memory_id=row["memory_id"],
            asset_id=row["asset_id"],
            dominant_mood=row["dominant_mood"],
            visual_style=row["visual_style"],
            lighting_style=row["lighting_style"],
            pacing_profile=row["pacing_profile"],
            character_presence=_load_list(row["character_presence"]),
            composition_patterns=_load_list(row["composition_patterns"]),
            cinematic_notes=row["cinematic_notes"],
            embeddings=embeddings,
            created_at=row["created_at"],
        )

    # Continuity Issue Persistence
    def save_continuity_issue(self, issue: ContinuityIssue) -> ContinuityIssue:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Check if table has new columns
            cursor.execute("PRAGMA table_info(continuity_issues)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if "issue_type" in columns:
                # New schema with issue_type
                cursor.execute(
                    """INSERT OR REPLACE INTO continuity_issues
                       (issue_id, project_id, source_keyframe_id, compared_keyframe_id, 
                        source_asset_id, compared_asset_id, issue_type, severity, confidence,
                        description, evidence, recommendation, notes, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue.issue_id,
                        issue.project_id,
                        issue.source_keyframe_id,
                        issue.compared_keyframe_id,
                        issue.source_asset_id,
                        issue.compared_asset_id,
                        issue.issue_type,
                        issue.severity,
                        issue.confidence,
                        issue.description,
                        issue.evidence,
                        issue.recommendation,
                        issue.notes,
                        json.dumps(issue.metadata) if issue.metadata else "{}",
                        issue.created_at,
                    ),
                )
            else:
                # Legacy schema with category instead of issue_type
                cursor.execute(
                    """INSERT OR REPLACE INTO continuity_issues
                       (issue_id, project_id, asset_id, category, severity, description, confidence,
                        notes, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue.issue_id,
                        issue.project_id,
                        issue.asset_id,
                        issue.issue_type,  # Use issue_type as category for legacy
                        issue.severity,
                        issue.description,
                        issue.confidence,
                        issue.notes,
                        json.dumps(issue.metadata) if issue.metadata else "{}",
                        issue.created_at,
                    ),
                )
            conn.commit()
        return issue

    def list_continuity_issues_for_project(self, project_id: str) -> List[ContinuityIssue]:
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

    def _row_to_continuity_issue(self, row: sqlite3.Row) -> ContinuityIssue:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        
        # Determine issue_type from schema
        issue_type = ""
        if "issue_type" in row.keys() and row["issue_type"]:
            issue_type = row["issue_type"]
        elif "category" in row.keys() and row["category"]:
            issue_type = row["category"]
        
        return ContinuityIssue(
            issue_id=row["issue_id"],
            project_id=row["project_id"],
            source_keyframe_id=(row["source_keyframe_id"] if "source_keyframe_id" in row.keys() else None),
            compared_keyframe_id=(row["compared_keyframe_id"] if "compared_keyframe_id" in row.keys() else None),
            source_asset_id=(row["source_asset_id"] if "source_asset_id" in row.keys() else None),
            compared_asset_id=(row["compared_asset_id"] if "compared_asset_id" in row.keys() else None),
            asset_id=(row["asset_id"] if "asset_id" in row.keys() else None),
            issue_type=issue_type,
            severity=row["severity"],
            description=row["description"],
            confidence=row["confidence"],
            evidence=(row["evidence"] if "evidence" in row.keys() else ""),
            recommendation=(row["recommendation"] if "recommendation" in row.keys() else ""),
            notes=row["notes"] or "",
            metadata=metadata,
            created_at=row["created_at"],
        )

    # Video Metadata Match Persistence
    def save_video_metadata_match(self, match: VideoMetadataMatch) -> VideoMetadataMatch:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO video_metadata_matches
                       (match_id, asset_id, metadata_id, project_id, match_status,
                        match_confidence, match_reason, matched_fields, created_at, updated_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        match.match_id,
                        match.asset_id,
                        match.metadata_id,
                        match.project_id,
                        match.match_status,
                        match.match_confidence,
                        match.match_reason,
                        json.dumps(match.matched_fields) if match.matched_fields else "[]",
                        match.created_at,
                        match.updated_at,
                        json.dumps(match.metadata) if match.metadata else "{}",
                    ),
                )
                conn.commit()
        self._execute_write_with_retry("save_video_metadata_match", _write)
        return match

    def get_video_metadata_match(self, match_id: str) -> Optional[VideoMetadataMatch]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM video_metadata_matches WHERE match_id = ?", (match_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_video_metadata_match(row)

    def list_video_metadata_matches_for_asset(self, asset_id: str) -> List[VideoMetadataMatch]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_metadata_matches WHERE asset_id = ? ORDER BY match_confidence DESC",
                (asset_id,),
            )
            return [self._row_to_video_metadata_match(row) for row in cursor.fetchall()]

    def list_video_metadata_matches(self) -> List[VideoMetadataMatch]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM video_metadata_matches ORDER BY created_at DESC"
            )
            return [self._row_to_video_metadata_match(row) for row in cursor.fetchall()]

    def _row_to_video_metadata_match(self, row: sqlite3.Row) -> VideoMetadataMatch:
        matched_fields = []
        if row["matched_fields"]:
            try:
                matched_fields = json.loads(row["matched_fields"])
            except json.JSONDecodeError:
                matched_fields = []
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        return VideoMetadataMatch(
            match_id=row["match_id"],
            asset_id=row["asset_id"],
            metadata_id=row["metadata_id"],
            project_id=row["project_id"],
            match_status=row["match_status"],
            match_confidence=row["match_confidence"],
            match_reason=row["match_reason"] or "",
            matched_fields=matched_fields,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata,
        )

    # Director Commentary Persistence
    def save_director_commentary(self, commentary: DirectorCommentary) -> DirectorCommentary:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO director_commentary
                   (commentary_id, asset_id, scene_reference, interpretation, emotional_read,
                    visual_language_notes, pacing_notes, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    commentary.commentary_id,
                    commentary.asset_id,
                    commentary.scene_reference,
                    commentary.interpretation,
                    commentary.emotional_read,
                    commentary.visual_language_notes,
                    commentary.pacing_notes,
                    commentary.created_at,
                    json.dumps(commentary.metadata) if commentary.metadata else "{}",
                ),
            )
            conn.commit()
        return commentary

    def list_director_commentary_for_asset(self, asset_id: str) -> List[DirectorCommentary]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM director_commentary WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_director_commentary(row) for row in cursor.fetchall()]

    def delete_director_commentary_for_asset(self, asset_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM director_commentary WHERE asset_id = ?", (asset_id,))
            conn.commit()
            return cursor.rowcount

    def _row_to_director_commentary(self, row: sqlite3.Row) -> DirectorCommentary:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        return DirectorCommentary(
            commentary_id=row["commentary_id"],
            asset_id=row["asset_id"],
            scene_reference=row["scene_reference"],
            interpretation=row["interpretation"],
            emotional_read=row["emotional_read"],
            visual_language_notes=row["visual_language_notes"],
            pacing_notes=row["pacing_notes"],
            created_at=row["created_at"],
            metadata=metadata,
        )

    # Frame Analysis Persistence
    def save_frame_analysis(self, analysis: FrameAnalysisRecord) -> FrameAnalysisRecord:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(frame_analyses)")
            has_frame_analyses = len(cursor.fetchall()) > 0
            if not has_frame_analyses:
                # Backward compatibility for older DB schemas during migration.
                return self.save_video_frame_analysis(analysis)
            composition_tags = analysis.composition_tags or analysis.camera_tags or []
            cursor.execute(
                """INSERT OR REPLACE INTO frame_analyses
                   (analysis_id, keyframe_id, asset_id, project_id, caption, visual_summary, mood_tags, lighting_tags,
                    composition_tags, color_palette, detected_subjects, camera_notes, confidence, provider, model, status,
                    created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis.analysis_id,
                    analysis.keyframe_id,
                    analysis.asset_id,
                    analysis.project_id,
                    analysis.caption,
                    analysis.visual_summary,
                    json.dumps(analysis.mood_tags or []),
                    json.dumps(analysis.lighting_tags or []),
                    json.dumps(composition_tags),
                    json.dumps(analysis.color_palette or []),
                    json.dumps(analysis.detected_subjects or []),
                    analysis.camera_notes,
                    float(analysis.confidence or 0.0),
                    analysis.provider,
                    analysis.model,
                    analysis.status,
                    analysis.created_at,
                    json.dumps(analysis.metadata) if analysis.metadata else "{}",
                ),
            )
            conn.commit()
        return analysis

    def get_frame_analysis(self, analysis_id: str) -> Optional[FrameAnalysisRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(frame_analyses)")
            if len(cursor.fetchall()) > 0:
                cursor.execute("SELECT * FROM frame_analyses WHERE analysis_id = ?", (analysis_id,))
                row = cursor.fetchone()
                return self._row_to_frame_analysis(row) if row else None
            cursor.execute("SELECT * FROM video_frame_analyses WHERE analysis_id = ?", (analysis_id,))
            row = cursor.fetchone()
            return self._row_to_video_frame_analysis(row) if row else None

    def list_frame_analyses_for_asset(self, asset_id: str) -> List[FrameAnalysisRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(frame_analyses)")
            if len(cursor.fetchall()) > 0:
                cursor.execute(
                    "SELECT * FROM frame_analyses WHERE asset_id = ? ORDER BY created_at DESC",
                    (asset_id,),
                )
                return [self._row_to_frame_analysis(row) for row in cursor.fetchall()]
            return self.list_video_frame_analyses_for_asset(asset_id)

    def list_frame_analyses_for_project(self, project_id: str) -> List[FrameAnalysisRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(frame_analyses)")
            if len(cursor.fetchall()) > 0:
                cursor.execute(
                    "SELECT * FROM frame_analyses WHERE project_id = ? ORDER BY created_at DESC",
                    (project_id,),
                )
                return [self._row_to_frame_analysis(row) for row in cursor.fetchall()]
            # Legacy fallback: derive by joining asset rows.
            cursor.execute(
                """SELECT a.* FROM video_frame_analyses a
                   INNER JOIN video_assets v ON v.asset_id = a.asset_id
                   WHERE v.project_id = ?
                   ORDER BY a.created_at DESC""",
                (project_id,),
            )
            return [self._row_to_video_frame_analysis(row) for row in cursor.fetchall()]

    # Backward compatibility methods (legacy table)
    def save_video_frame_analysis(self, analysis: FrameAnalysisRecord) -> FrameAnalysisRecord:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO video_frame_analyses
                   (analysis_id, asset_id, keyframe_id, caption, mood_tags, lighting_tags, camera_tags,
                    embeddings, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    analysis.analysis_id,
                    analysis.asset_id,
                    analysis.keyframe_id,
                    analysis.caption,
                    json.dumps(analysis.mood_tags or []),
                    json.dumps(analysis.lighting_tags or []),
                    json.dumps(analysis.composition_tags or analysis.camera_tags or []),
                    json.dumps(analysis.embeddings) if analysis.embeddings is not None else None,
                    analysis.created_at,
                    json.dumps(analysis.metadata) if analysis.metadata else "{}",
                ),
            )
            conn.commit()
        return analysis

    def list_video_frame_analyses_for_asset(self, asset_id: str) -> List[FrameAnalysisRecord]:
        return self.list_frame_analyses_for_asset(asset_id)

    def list_video_frame_analyses(self, limit: int = 500) -> List[FrameAnalysisRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(frame_analyses)")
            if len(cursor.fetchall()) > 0:
                cursor.execute("SELECT * FROM frame_analyses ORDER BY created_at DESC LIMIT ?", (limit,))
                return [self._row_to_frame_analysis(row) for row in cursor.fetchall()]
            cursor.execute("SELECT * FROM video_frame_analyses ORDER BY created_at DESC LIMIT ?", (limit,))
            return [self._row_to_video_frame_analysis(row) for row in cursor.fetchall()]

    def _row_to_frame_analysis(self, row: sqlite3.Row) -> FrameAnalysisRecord:
        def _load_list(value: Any) -> List[str]:
            if not value:
                return []
            try:
                loaded = json.loads(value)
                return [str(v) for v in loaded] if isinstance(loaded, list) else []
            except Exception:
                return []
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        composition = _load_list(row["composition_tags"])
        return FrameAnalysisRecord(
            analysis_id=row["analysis_id"],
            keyframe_id=row["keyframe_id"],
            asset_id=row["asset_id"],
            project_id=row["project_id"],
            caption=row["caption"] or "",
            visual_summary=row["visual_summary"] or "",
            mood_tags=_load_list(row["mood_tags"]),
            lighting_tags=_load_list(row["lighting_tags"]),
            composition_tags=composition,
            color_palette=_load_list(row["color_palette"]),
            detected_subjects=_load_list(row["detected_subjects"]),
            camera_notes=row["camera_notes"] or "",
            confidence=float(row["confidence"] or 0.0),
            provider=row["provider"] or "unavailable",
            model=row["model"] or "unconfigured",
            status=row["status"] or "unavailable",
            created_at=row["created_at"],
            metadata=metadata,
            camera_tags=composition,
            embeddings=None,
        )

    def _row_to_video_frame_analysis(self, row: sqlite3.Row) -> FrameAnalysisRecord:
        def _load_list(value: Any) -> List[str]:
            if not value:
                return []
            try:
                loaded = json.loads(value)
                return [str(v) for v in loaded] if isinstance(loaded, list) else []
            except Exception:
                return []

        embeddings = None
        if row["embeddings"]:
            try:
                loaded = json.loads(row["embeddings"])
                if isinstance(loaded, list):
                    embeddings = [float(v) for v in loaded]
            except Exception:
                embeddings = None

        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}

        return FrameAnalysisRecord(
            analysis_id=row["analysis_id"],
            keyframe_id=row["keyframe_id"] or "",
            asset_id=row["asset_id"],
            project_id=str(metadata.get("project_id") or "unassigned"),
            caption=row["caption"] or "",
            visual_summary=str(metadata.get("visual_summary") or ""),
            mood_tags=_load_list(row["mood_tags"]),
            lighting_tags=_load_list(row["lighting_tags"]),
            composition_tags=_load_list(row["camera_tags"]),
            color_palette=[str(v) for v in metadata.get("color_palette", [])] if isinstance(metadata.get("color_palette"), list) else [],
            detected_subjects=[str(v) for v in metadata.get("detected_subjects", [])] if isinstance(metadata.get("detected_subjects"), list) else [],
            camera_notes=str(metadata.get("camera_notes") or ""),
            confidence=float(metadata.get("confidence") or 0.0),
            provider=str(metadata.get("provider") or "legacy"),
            model=str(metadata.get("model") or "legacy"),
            status=str(metadata.get("status") or "complete"),
            embeddings=embeddings,
            created_at=row["created_at"],
            metadata=metadata,
            camera_tags=_load_list(row["camera_tags"]),
        )

    # Visual Embeddings Persistence
    def save_visual_embedding(self, embedding: VisualEmbedding) -> VisualEmbedding:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO visual_embeddings
                   (embedding_id, keyframe_id, asset_id, project_id, provider, model, vector_dimension,
                    embedding_vector, status, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    embedding.embedding_id,
                    embedding.keyframe_id,
                    embedding.asset_id,
                    embedding.project_id,
                    embedding.provider,
                    embedding.model,
                    int(embedding.vector_dimension or 0),
                    json.dumps(embedding.embedding_vector or []),
                    embedding.status,
                    embedding.created_at,
                    json.dumps(embedding.metadata) if embedding.metadata else "{}",
                ),
            )
            conn.commit()
        return embedding

    def get_visual_embedding(self, embedding_id: str) -> Optional[VisualEmbedding]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM visual_embeddings WHERE embedding_id = ?", (embedding_id,))
            row = cursor.fetchone()
            return self._row_to_visual_embedding(row) if row else None

    def get_visual_embedding_for_keyframe(self, keyframe_id: str) -> Optional[VisualEmbedding]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM visual_embeddings WHERE keyframe_id = ? ORDER BY created_at DESC LIMIT 1",
                (keyframe_id,),
            )
            row = cursor.fetchone()
            return self._row_to_visual_embedding(row) if row else None

    def list_visual_embeddings_for_asset(self, asset_id: str) -> List[VisualEmbedding]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM visual_embeddings WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_visual_embedding(row) for row in cursor.fetchall()]

    def list_visual_embeddings_for_project(self, project_id: str) -> List[VisualEmbedding]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM visual_embeddings WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_visual_embedding(row) for row in cursor.fetchall()]

    def list_visual_embeddings(self, limit: int = 2000) -> List[VisualEmbedding]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM visual_embeddings ORDER BY created_at DESC LIMIT ?", (limit,))
            return [self._row_to_visual_embedding(row) for row in cursor.fetchall()]

    def _row_to_visual_embedding(self, row: sqlite3.Row) -> VisualEmbedding:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        vector: List[float] = []
        if row["embedding_vector"]:
            try:
                loaded = json.loads(row["embedding_vector"])
                if isinstance(loaded, list):
                    vector = [float(v) for v in loaded]
            except Exception:
                vector = []
        return VisualEmbedding(
            embedding_id=row["embedding_id"],
            keyframe_id=row["keyframe_id"],
            asset_id=row["asset_id"],
            project_id=row["project_id"],
            provider=row["provider"] or "unavailable",
            model=row["model"] or "unconfigured",
            vector_dimension=int(row["vector_dimension"] or 0),
            embedding_vector=vector,
            status=row["status"] or "unavailable",
            created_at=row["created_at"],
            metadata=metadata,
        )

    # Cinematic Memory Persistence
    def save_cinematic_memory_record(self, row: CinematicMemoryRecord) -> CinematicMemoryRecord:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO cinematic_memory_records
                   (memory_id, project_id, asset_id, keyframe_id, analysis_id, embedding_id, memory_type, summary,
                    visual_tags, emotional_tags, composition_tags, lighting_tags, searchable_text, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row.memory_id,
                    row.project_id,
                    row.asset_id,
                    row.keyframe_id,
                    row.analysis_id,
                    row.embedding_id,
                    row.memory_type,
                    row.summary,
                    json.dumps(row.visual_tags or []),
                    json.dumps(row.emotional_tags or []),
                    json.dumps(row.composition_tags or []),
                    json.dumps(row.lighting_tags or []),
                    row.searchable_text,
                    row.created_at,
                    json.dumps(row.metadata) if row.metadata else "{}",
                ),
            )
            conn.commit()
        return row

    def list_cinematic_memory_for_project(self, project_id: str) -> List[CinematicMemoryRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cinematic_memory_records WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_cinematic_memory_record(row) for row in cursor.fetchall()]

    def list_cinematic_memory_for_asset(self, asset_id: str) -> List[CinematicMemoryRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cinematic_memory_records WHERE asset_id = ? ORDER BY created_at DESC",
                (asset_id,),
            )
            return [self._row_to_cinematic_memory_record(row) for row in cursor.fetchall()]

    def list_cinematic_memory_records(self, limit: int = 2000) -> List[CinematicMemoryRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cinematic_memory_records ORDER BY created_at DESC LIMIT ?", (limit,))
            return [self._row_to_cinematic_memory_record(row) for row in cursor.fetchall()]

    def get_cinematic_memory_for_keyframe(self, keyframe_id: str) -> List[CinematicMemoryRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cinematic_memory_records WHERE keyframe_id = ? ORDER BY created_at DESC",
                (keyframe_id,),
            )
            return [self._row_to_cinematic_memory_record(row) for row in cursor.fetchall()]

    def _row_to_cinematic_memory_record(self, row: sqlite3.Row) -> CinematicMemoryRecord:
        def _load_tags(raw: Any) -> List[str]:
            if not raw:
                return []
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    return [str(v) for v in loaded]
            except Exception:
                return []
            return []
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        return CinematicMemoryRecord(
            memory_id=row["memory_id"],
            project_id=row["project_id"],
            asset_id=row["asset_id"],
            keyframe_id=row["keyframe_id"],
            analysis_id=row["analysis_id"] or "",
            embedding_id=row["embedding_id"] or "",
            memory_type=row["memory_type"] or "keyframe_memory",
            summary=row["summary"] or "",
            visual_tags=_load_tags(row["visual_tags"]),
            emotional_tags=_load_tags(row["emotional_tags"]),
            composition_tags=_load_tags(row["composition_tags"]),
            lighting_tags=_load_tags(row["lighting_tags"]),
            searchable_text=row["searchable_text"] or "",
            created_at=row["created_at"],
            metadata=metadata,
        )

    # Style Signature Persistence
    def save_style_signature(self, signature: StyleSignature) -> StyleSignature:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO style_signatures
                   (signature_id, project_id, framing_tendencies, pacing_patterns, color_motifs,
                    camera_movement_patterns, confidence, advisory_only, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signature.signature_id,
                    signature.project_id,
                    json.dumps(signature.framing_tendencies or []),
                    json.dumps(signature.pacing_patterns or []),
                    json.dumps(signature.color_motifs or []),
                    json.dumps(signature.camera_movement_patterns or []),
                    signature.confidence,
                    1 if signature.advisory_only else 0,
                    json.dumps(signature.metadata) if signature.metadata else "{}",
                    signature.created_at,
                ),
            )
            conn.commit()
        return signature

    def list_style_signatures_for_project(self, project_id: str) -> List[StyleSignature]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM style_signatures WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_style_signature(row) for row in cursor.fetchall()]

    def get_style_signature(self, signature_id: str) -> Optional[StyleSignature]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM style_signatures WHERE signature_id = ?", (signature_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_style_signature(row)
            return None

    def _row_to_style_signature(self, row: sqlite3.Row) -> StyleSignature:
        def _load_list(value: Any) -> List[str]:
            if not value:
                return []
            try:
                loaded = json.loads(value)
                return [str(v) for v in loaded] if isinstance(loaded, list) else []
            except Exception:
                return []

        metadata = {}
        if row["metadata"]:
            try:
                loaded = json.loads(row["metadata"])
                if isinstance(loaded, dict):
                    metadata = loaded
            except Exception:
                metadata = {}

        return StyleSignature(
            signature_id=row["signature_id"],
            project_id=row["project_id"],
            framing_tendencies=_load_list(row["framing_tendencies"]),
            pacing_patterns=_load_list(row["pacing_patterns"]),
            color_motifs=_load_list(row["color_motifs"]),
            camera_movement_patterns=_load_list(row["camera_movement_patterns"]),
            confidence=float(row["confidence"] or 0.0),
            advisory_only=bool(row["advisory_only"]),
            metadata=metadata,
            created_at=row["created_at"],
        )

    # Director signature + style drift (advisory tables)
    def save_director_signature(self, signature: DirectorSignature) -> DirectorSignature:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO director_signatures
                       (signature_id, project_id, dominant_mood_tags, dominant_lighting_tags,
                        dominant_composition_tags, dominant_palette, pacing_notes, visual_language_summary,
                        confidence, evidence_keyframe_ids, evidence_memory_ids, created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        signature.signature_id,
                        signature.project_id,
                        json.dumps(signature.dominant_mood_tags or []),
                        json.dumps(signature.dominant_lighting_tags or []),
                        json.dumps(signature.dominant_composition_tags or []),
                        json.dumps(signature.dominant_palette or []),
                        signature.pacing_notes or "",
                        signature.visual_language_summary or "",
                        float(signature.confidence or 0.0),
                        json.dumps(signature.evidence_keyframe_ids or []),
                        json.dumps(signature.evidence_memory_ids or []),
                        signature.created_at,
                        json.dumps(signature.metadata) if signature.metadata else "{}",
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_director_signature", _write)
        return signature

    def list_director_signatures_for_project(self, project_id: str) -> List[DirectorSignature]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM director_signatures WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_director_signature(row) for row in cursor.fetchall()]

    def get_latest_director_signature(self, project_id: str) -> Optional[DirectorSignature]:
        rows = self.list_director_signatures_for_project(project_id)
        return rows[0] if rows else None

    def _row_to_director_signature(self, row: sqlite3.Row) -> DirectorSignature:
        def _load_list(value: Any) -> List[str]:
            if not value:
                return []
            try:
                loaded = json.loads(value)
                return [str(v) for v in loaded] if isinstance(loaded, list) else []
            except Exception:
                return []

        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
                if not isinstance(metadata, dict):
                    metadata = {}
            except Exception:
                metadata = {}
        return DirectorSignature(
            signature_id=row["signature_id"],
            project_id=row["project_id"],
            dominant_mood_tags=_load_list(row["dominant_mood_tags"]),
            dominant_lighting_tags=_load_list(row["dominant_lighting_tags"]),
            dominant_composition_tags=_load_list(row["dominant_composition_tags"]),
            dominant_palette=_load_list(row["dominant_palette"]),
            pacing_notes=row["pacing_notes"] or "",
            visual_language_summary=row["visual_language_summary"] or "",
            confidence=float(row["confidence"] or 0.0),
            evidence_keyframe_ids=_load_list(row["evidence_keyframe_ids"]),
            evidence_memory_ids=_load_list(row["evidence_memory_ids"]),
            created_at=row["created_at"],
            metadata=metadata,
        )

    def save_style_drift_issue(self, issue: StyleDriftIssue) -> StyleDriftIssue:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO style_drift_issues
                       (drift_id, project_id, keyframe_id, asset_id, drift_type, severity, confidence,
                        description, evidence, recommendation, compared_against_signature_id, created_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue.drift_id,
                        issue.project_id,
                        issue.keyframe_id or "",
                        issue.asset_id or "",
                        issue.drift_type,
                        issue.severity,
                        float(issue.confidence or 0.0),
                        issue.description or "",
                        issue.evidence or "",
                        issue.recommendation or "",
                        issue.compared_against_signature_id or "",
                        issue.created_at,
                        json.dumps(issue.metadata) if issue.metadata else "{}",
                    ),
                )
                conn.commit()

        self._execute_write_with_retry("save_style_drift_issue", _write)
        return issue

    def list_style_drift_issues_for_project(self, project_id: str) -> List[StyleDriftIssue]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM style_drift_issues WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            return [self._row_to_style_drift_issue(row) for row in cursor.fetchall()]

    def delete_style_drift_issues_for_project(self, project_id: str) -> int:
        def _write():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM style_drift_issues WHERE project_id = ?", (project_id,))
                conn.commit()
                return cursor.rowcount

        return int(self._execute_write_with_retry("delete_style_drift_issues_for_project", _write))

    def _row_to_style_drift_issue(self, row: sqlite3.Row) -> StyleDriftIssue:
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
                if not isinstance(metadata, dict):
                    metadata = {}
            except Exception:
                metadata = {}
        return StyleDriftIssue(
            drift_id=row["drift_id"],
            project_id=row["project_id"],
            keyframe_id=row["keyframe_id"] or "",
            asset_id=row["asset_id"] or "",
            drift_type=row["drift_type"],
            severity=row["severity"],
            confidence=float(row["confidence"] or 0.0),
            description=row["description"] or "",
            evidence=row["evidence"] or "",
            recommendation=row["recommendation"] or "",
            compared_against_signature_id=row["compared_against_signature_id"] or "",
            created_at=row["created_at"],
            metadata=metadata,
        )

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
            last_polled_at=row["last_polled_at"] if "last_polled_at" in row.keys() else None,
            retry_count=row["retry_count"],
            recovery_status=(row["recovery_status"] if "recovery_status" in row.keys() else "none") or "none",
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

    # ========================================================================
    # WORKFLOW STORAGE
    # ========================================================================

    def save_workflow_execution(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Save a workflow execution"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO workflow_executions (
                    execution_id, workflow_id, project_id, status, started_at, completed_at,
                    current_step, completed_steps, failed_steps, step_results, inputs, outputs,
                    error_message, progress_percentage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution.execution_id,
                execution.workflow_id,
                execution.project_id,
                execution.status,
                execution.started_at,
                execution.completed_at,
                execution.current_step,
                json.dumps(execution.completed_steps),
                json.dumps(execution.failed_steps),
                json.dumps(execution.step_results),
                json.dumps(execution.inputs),
                json.dumps(execution.outputs),
                execution.error_message,
                execution.progress_percentage
            ))
            conn.commit()
        return execution

    def get_workflow_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get a workflow execution by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM workflow_executions WHERE execution_id = ?
            """, (execution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            return WorkflowExecution(
                execution_id=row[0],
                workflow_id=row[1],
                project_id=row[2],
                status=row[3],
                started_at=row[4],
                completed_at=row[5],
                current_step=row[6],
                completed_steps=json.loads(row[7]),
                failed_steps=json.loads(row[8]),
                step_results=json.loads(row[9]),
                inputs=json.loads(row[10]),
                outputs=json.loads(row[11]),
                error_message=row[12],
                progress_percentage=row[13]
            )

    def list_workflow_executions(self, project_id: Optional[str] = None) -> List[WorkflowExecution]:
        """List workflow executions, optionally filtered by project"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute("""
                    SELECT * FROM workflow_executions WHERE project_id = ? ORDER BY started_at DESC
                """, (project_id,))
            else:
                cursor.execute("""
                    SELECT * FROM workflow_executions ORDER BY started_at DESC
                """)
            
            executions = []
            for row in cursor.fetchall():
                executions.append(WorkflowExecution(
                    execution_id=row[0],
                    workflow_id=row[1],
                    project_id=row[2],
                    status=row[3],
                    started_at=row[4],
                    completed_at=row[5],
                    current_step=row[6],
                    completed_steps=json.loads(row[7]),
                    failed_steps=json.loads(row[8]),
                    step_results=json.loads(row[9]),
                    inputs=json.loads(row[10]),
                    outputs=json.loads(row[11]),
                    error_message=row[12],
                    progress_percentage=row[13]
                ))
            return executions

    def delete_workflow_execution(self, execution_id: str) -> bool:
        """Delete a workflow execution"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM workflow_executions WHERE execution_id = ?
            """, (execution_id,))
            conn.commit()
            return cursor.rowcount > 0


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
    default_storage_path = str(Path(__file__).resolve().parents[2] / "data")
    configured_storage_path = kwargs.get("storage_path") or os.getenv("STUDIO_STORAGE_PATH") or default_storage_path
    if storage_type == "sqlite":
        return DatabaseStorage(configured_storage_path)
    elif storage_type == "json":
        return JsonFileStorage(configured_storage_path)
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

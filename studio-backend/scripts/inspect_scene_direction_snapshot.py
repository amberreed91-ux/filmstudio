#!/usr/bin/env python3
"""Read-only Scene Direction inspection against a forensic SQLite byte copy.

This diagnostic deliberately does not import ``main`` or initialize
``DatabaseStorage``. It copies the live database and any WAL/SHM siblings,
then opens only that copy through SQLite's read-only URI. No HTTP server is
started; the normal production startup path is never changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from app.data.db_guard import open_db_readonly
from types import ModuleType
from typing import Any

PROJECT_ID = "project_5907c60cddbc"
SCENE_ID = "scene_002"
# Approved v8 is the current approved storyboard version. Its five shot prompts
# and camera plans are hash-identical to the original v3 pin; v3 is retained
# nowhere. Selection is grounded in approved version metadata (see the
# version_status gate below), never inferred from version numbering alone.
APPROVED_VERSION_ID = "sbv_5fb97c8f5fa3"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = BACKEND_ROOT / "data" / "studio.db"
sys.dont_write_bytecode = True
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
BACKUP_DIR = BACKEND_ROOT / "backups"
DATA_DIR = BACKEND_ROOT / "data"
LINEAGE_FILE = DATA_DIR / "database_lineage.json"
RECOVERY_SNAPSHOT_DIR = DATA_DIR / "recovery-snapshots"
STATE_FILES = (BACKUP_DIR, LINEAGE_FILE, RECOVERY_SNAPSHOT_DIR)


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _files_state(paths: tuple[Path, ...]) -> dict[str, dict[str, Any]]:
    result = {}
    for path in paths:
        if path.is_dir():
            entries = sorted(p for p in path.rglob("*") if p.is_file())
            result[str(path)] = {
                "files": {
                    str(item.relative_to(path)): {
                        "size": item.stat().st_size,
                        "sha256": _sha256(item),
                    }
                    for item in entries
                }
            }
        elif path.is_file():
            result[str(path)] = {"size": path.stat().st_size, "sha256": _sha256(path)}
        else:
            result[str(path)] = {"exists": False}
    return result


def _assert_readonly_copy(source: Path, copy: Path) -> None:
    source_real = source.resolve(strict=True)
    copy_real = copy.resolve(strict=True)
    if source_real == copy_real or os.path.samefile(source_real, copy_real):
        raise RuntimeError("Inspection refused: disposable DB resolves to the live DB")
    if not copy_real.is_file() or not copy_real.stat().st_size:
        raise RuntimeError("Inspection refused: disposable DB copy is absent or empty")
    uri = f"{copy_real.as_uri()}?mode=ro"

    connection = open_db_readonly(copy_real)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        try:
            connection.execute("CREATE TABLE __inspection_write_probe(value INTEGER)")
        except sqlite3.OperationalError:
            pass
        else:
            raise RuntimeError("Inspection copy accepted a write despite read-only mode")
    finally:
        connection.close()


class ReadOnlySceneStorage:
    """Minimal SceneDirectionService storage backed by a read-only SQLite URI."""

    def __init__(self, db_path: Path, source_db: Path = LIVE_DB):
        _assert_readonly_copy(source_db, db_path)
        self.db_path = db_path.resolve(strict=True)
        self._uri = f"{self.db_path.as_uri()}?mode=ro"
        self.read_calls: list[str] = []
        with self._connect() as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            required = {"projects", "storyboard_blueprints", "storyboard_blueprint_versions", "storyboard_shots"}
            if not required.issubset(tables):
                raise RuntimeError("Disposable DB is missing Scene Direction tables")

    def _connect(self) -> sqlite3.Connection:
        connection = open_db_readonly(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection

    @staticmethod
    def _json(value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    def get_project(self, project_id: str):
        from app.models import StudioProject

        self.read_calls.append("get_project")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT data FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
        if row is None or not row["data"]:
            return None
        return StudioProject.model_validate(self._json(row["data"], {}))

    def get_storyboard_blueprint(self, project_id: str, scene_id: str):
        from app.models.storyboard_blueprint import StoryboardBlueprint

        self.read_calls.append("get_storyboard_blueprint")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM storyboard_blueprints WHERE project_id=? AND scene_id=? LIMIT 1",
                (project_id, scene_id),
            ).fetchone()
        if row is None:
            return None
        return StoryboardBlueprint(
            blueprint_id=row["blueprint_id"], project_id=row["project_id"],
            scene_id=row["scene_id"], current_version_id=row["current_version_id"],
            status=row["status"], approved_version_id=row["approved_version_id"],
            locked=bool(row["locked"]), created_at=row["created_at"],
            updated_at=row["updated_at"], created_by=row["created_by"] or "",
            metadata=self._json(row["metadata"], {}),
        )

    def get_storyboard_blueprint_version(self, version_id: str):
        from app.models.storyboard_blueprint import (
            StoryboardBlueprintInspection,
            StoryboardBlueprintProvenance,
            StoryboardBlueprintVersion,
        )

        self.read_calls.append("get_storyboard_blueprint_version")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM storyboard_blueprint_versions WHERE version_id=?", (version_id,)
            ).fetchone()
        if row is None:
            return None
        return StoryboardBlueprintVersion(
            version_id=row["version_id"], blueprint_id=row["blueprint_id"],
            project_id=row["project_id"], scene_id=row["scene_id"],
            version_number=int(row["version_number"] or 1), status=row["status"],
            change_reason=row["change_reason"] or "", source_version_id=row["source_version_id"],
            provenance=StoryboardBlueprintProvenance(**self._json(row["provenance_json"], {})),
            inspection=StoryboardBlueprintInspection(**self._json(row["inspection_json"], {})),
            created_at=row["created_at"], approved_at=row["approved_at"],
            approved_by=row["approved_by"] or "", metadata=self._json(row["metadata"], {}),
        )

    def list_storyboard_shots(self, blueprint_id: str, version_id: str | None = None):
        from app.models.storyboard_blueprint import (
            StoryboardDepartmentNote,
            StoryboardShot,
            StoryboardShotContinuityPlan,
            StoryboardShotIntent,
            StoryboardShotRenderContract,
            StoryboardShotVisualPlan,
        )

        self.read_calls.append("list_storyboard_shots")
        with self._connect() as connection:
            if version_id:
                rows = connection.execute(
                    "SELECT * FROM storyboard_shots WHERE blueprint_id=? AND version_id=? ORDER BY shot_number, shot_id",
                    (blueprint_id, version_id),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM storyboard_shots WHERE blueprint_id=? ORDER BY shot_number, shot_id",
                    (blueprint_id,),
                ).fetchall()
        return [
            StoryboardShot(
                storyboard_shot_id=row["storyboard_shot_id"], blueprint_id=row["blueprint_id"],
                version_id=row["version_id"], project_id=row["project_id"], scene_id=row["scene_id"],
                shot_id=row["shot_id"], shot_number=int(row["shot_number"] or 1), status=row["status"],
                intent=StoryboardShotIntent(**self._json(row["intent_json"], {})),
                visual_plan=StoryboardShotVisualPlan(**self._json(row["visual_plan_json"], {})),
                continuity_plan=StoryboardShotContinuityPlan(**self._json(row["continuity_plan_json"], {})),
                render_contract=StoryboardShotRenderContract(**self._json(row["render_contract_json"], {})),
                department_notes=[StoryboardDepartmentNote(**item) for item in self._json(row["department_notes_json"], []) if isinstance(item, dict)],
                storyboard_image_url=row["storyboard_image_url"], previs_image_id=row["previs_image_id"],
                rationale=row["rationale"] or "", locked=bool(row["locked"]),
                created_at=row["created_at"], updated_at=row["updated_at"],
                metadata=self._json(row["metadata"], {}),
            )
            for row in rows
        ]

    def list_storyboard_blueprint_versions(self, blueprint_id: str):
        from app.models.storyboard_blueprint import (
            StoryboardBlueprintInspection,
            StoryboardBlueprintProvenance,
            StoryboardBlueprintVersion,
        )

        self.read_calls.append("list_storyboard_blueprint_versions")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM storyboard_blueprint_versions WHERE blueprint_id=? ORDER BY version_number",
                (blueprint_id,),
            ).fetchall()
        return [StoryboardBlueprintVersion(
            version_id=row["version_id"], blueprint_id=row["blueprint_id"],
            project_id=row["project_id"], scene_id=row["scene_id"],
            version_number=int(row["version_number"] or 1), status=row["status"],
            change_reason=row["change_reason"] or "", source_version_id=row["source_version_id"],
            provenance=StoryboardBlueprintProvenance(**self._json(row["provenance_json"], {})),
            inspection=StoryboardBlueprintInspection(**self._json(row["inspection_json"], {})),
            created_at=row["created_at"], approved_at=row["approved_at"],
            approved_by=row["approved_by"] or "", metadata=self._json(row["metadata"], {}),
        ) for row in rows]

    def list_jobs(self, **_kwargs):
        with self._connect() as connection:
            return connection.execute("SELECT id FROM render_jobs WHERE project_id=?", (PROJECT_ID,)).fetchall()

    def close(self):
        return None


def _copied_db(root: Path, source_db: Path) -> Path:
    destination = root / "studio.db"
    source_db = source_db.resolve(strict=True)
    if not source_db.is_file():
        raise FileNotFoundError(source_db)
    source_hashes = {
        suffix: _sha256(Path(str(source_db) + suffix))
        for suffix in ("", "-wal", "-shm")
    }
    shutil.copy2(source_db, destination)
    # Preserve the forensic copy methodology exactly: copy sidecars byte-for-byte
    # next to the database, without opening/checkpointing the live SQLite file.
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(source_db) + suffix)
        if sidecar.is_file():
            shutil.copy2(sidecar, Path(str(destination) + suffix))
    copied_hashes = {
        suffix: _sha256(Path(str(destination) + suffix))
        for suffix in ("", "-wal", "-shm")
    }
    source_hashes_after = {
        suffix: _sha256(Path(str(source_db) + suffix))
        for suffix in ("", "-wal", "-shm")
    }
    if source_hashes != copied_hashes or source_hashes != source_hashes_after:
        raise RuntimeError("Forensic database copy did not capture a stable byte-identical DB/WAL/SHM set")
    _assert_readonly_copy(source_db, destination)
    return destination


def _loaded_inspection_imports() -> dict[str, bool]:
    forbidden_services = (
        "app.services.render",
        "app.services.production_queue_service",
        "app.services.visual_training_service",
        "app.services.database_backup",
        "app.services.recovery_lineage_guard",
        "app.services.render_job_backfill",
        "app.services.demo_seed_service",
        "app.services.production_recovery_service",
        "app.services.service_registry",
        "app.services.project_route_dependencies",
        "app.services.agent_executor",
        "app.services.orchestrator",
        "app.services.workflow_runner_service",
        "app.services.universe_graph_service",
        "app.services.poster_service",
        "app.services.character_extraction_service",
        "app.services.emotion_analysis_service",
        "app.services.study_memory_service",
        "app.services.study_context",
    )
    loaded = {name: name in sys.modules for name in forbidden_services}
    main_path = (BACKEND_ROOT / "main.py").resolve()
    loaded["application_main"] = any(
        Path(getattr(module, "__file__", "")).resolve() == main_path
        for module in sys.modules.values()
        if getattr(module, "__file__", None)
    )
    return loaded


def _assert_forbidden_imports_absent() -> dict[str, bool]:
    loaded = _loaded_inspection_imports()
    if any(loaded.values()):
        raise RuntimeError(f"Production application/lifecycle module imported in inspection mode: {loaded}")
    return loaded


def _semantic_snapshot(storage: ReadOnlySceneStorage, project_id: str, scene_id: str) -> dict[str, Any]:
    with storage._connect() as connection:
        counts = {
            "project_count": connection.execute("SELECT count(*) FROM projects").fetchone()[0],
            "render_job_count": connection.execute(
                "SELECT count(*) FROM render_jobs WHERE project_id=?", (project_id,)
            ).fetchone()[0],
            "demo_project_exists": connection.execute(
                "SELECT 1 FROM projects WHERE project_id='proj-001'"
            ).fetchone() is not None,
        }
        version = connection.execute(
            "SELECT version_id, status, metadata FROM storyboard_blueprint_versions WHERE version_id=?",
            (APPROVED_VERSION_ID,),
        ).fetchone()
        project_row = connection.execute("SELECT data FROM projects WHERE project_id=?", (project_id,)).fetchone()
        project = storage._json(project_row["data"], {}) if project_row else {}
        summary = project.get("execution_summary") or {}
        scene = next((row for row in summary.get("scenes", []) if isinstance(row, dict) and row.get("scene_id") == scene_id), {})
        prompts, camera_plans = {}, {}
        shot_rows = connection.execute(
            "SELECT shot_id, shot_number, render_contract_json FROM storyboard_shots WHERE version_id=? ORDER BY shot_number",
            (APPROVED_VERSION_ID,),
        ).fetchall()
        for row in shot_rows:
            contract = storage._json(row["render_contract_json"], {})
            parameters = contract.get("structured_parameters") or {}
            prompt = contract.get("provider_neutral_prompt")
            camera_plan = parameters.get("camera_plan")
            if not isinstance(prompt, str) or not prompt:
                raise RuntimeError(f"Approved shot {row['shot_id']} has no provider-neutral prompt")
            if not isinstance(camera_plan, dict) or not camera_plan:
                raise RuntimeError(f"Approved shot {row['shot_id']} has no structured camera plan")
            prompts[row["shot_id"]] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            camera_plans[row["shot_id"]] = hashlib.sha256(json.dumps(camera_plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        refs = [dict(row) for row in connection.execute(
            "SELECT * FROM reference_assets WHERE project_id=? ORDER BY ref_id", (project_id,)
        )]
    meta = storage._json(version["metadata"], {}) if version else {}
    saved = "scene_direction" in meta
    # Character looks now ship face + full-body pairs; select the authoritative
    # canonical row exactly as production does (reference_asset_service keeps a
    # canonical primary beside approved supporting rows; coverage and render
    # authorization require approved + canonical). The exactly-one gate below
    # keeps its fail-closed meaning: one canonical reference per subject.
    dre = [row for row in refs if row.get("target_type") == "character" and row.get("target_id") == "chr_f1425498cb68" and bool(row.get("canonical"))]
    maya = [row for row in refs if row.get("target_type") == "character" and row.get("target_id") == "chr_3c9e91741ef3" and bool(row.get("canonical"))]
    env = [row for row in refs if row.get("ref_id") == "ref_env_6b726885ed67ae4d"]
    reference_counts = {"DRE": len(dre), "MAYA": len(maya), "environment": len(env)}
    return {
        **counts,
        "version_status": str(version["status"]) if version else None,
        "version_id": version["version_id"] if version else None,
        "saved": saved,
        "creator_decisions_recorded": saved,
        "prompt_hashes": prompts,
        "camera_plan_hashes": camera_plans,
        "reference_hashes": {
            "DRE": hashlib.sha256(json.dumps(dre, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "MAYA": hashlib.sha256(json.dumps(maya, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "environment": hashlib.sha256(json.dumps(env, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        },
        "reference_counts": reference_counts,
        "expected_shot_count": len(shot_rows),
    }


def _install_inspection_service_namespace(inspection_storage: ReadOnlySceneStorage) -> dict[str, bool]:
    """Bypass app.services.__init__ and redirect singleton storage to the copy."""
    if "app.services" in sys.modules:
        raise RuntimeError("Inspection must start in a clean process before app.services is imported")
    package = ModuleType("app.services")
    package.__path__ = [str(BACKEND_ROOT / "app" / "services")]
    package.__package__ = "app.services"
    sys.modules["app.services"] = package

    import app.data.storage as storage_module

    blocked = {
        "production_storage_factory_called": False,
        "database_storage_initialized": False,
        "inspection_storage_factory_calls": 0,
        "singleton_storage_redirected_to_copy": False,
    }

    def inspection_storage_factory(*_args, **_kwargs):
        blocked["inspection_storage_factory_calls"] += 1
        blocked["singleton_storage_redirected_to_copy"] = True
        return inspection_storage

    def no_database_storage_init(*_args, **_kwargs):
        blocked["database_storage_initialized"] = True
        raise RuntimeError("DatabaseStorage initialization is disabled in inspection mode")

    storage_module.get_storage = inspection_storage_factory
    storage_module.DatabaseStorage.__init__ = no_database_storage_init
    import app.data as data_package
    data_package.get_storage = inspection_storage_factory
    return blocked


def _install_runtime_guards(disposable_db: Path) -> dict[str, int]:
    """Fail closed on live/writable SQLite, network, process, or worker startup."""
    import socket
    import subprocess
    import threading
    import urllib.parse

    guards = {
        "readonly_copy_connections": 0,
        "worker_thread_start_attempts": 0,
        "network_attempts": 0,
        "process_start_attempts": 0,
    }
    original_sqlite_connect = sqlite3.connect
    allowed_db = disposable_db.resolve(strict=True)

    def guarded_sqlite_connect(database, *args, **kwargs):
        if database in (None, ":memory:"):
            return original_sqlite_connect(database, *args, **kwargs)
        target = os.fspath(database)
        if not target.startswith("file:"):
            raise RuntimeError("Inspection allows SQLite access only through the disposable read-only URI")
        parsed = urllib.parse.urlsplit(target)
        resolved = Path(urllib.parse.unquote(parsed.path)).resolve(strict=True)
        query = urllib.parse.parse_qs(parsed.query)
        if resolved != allowed_db or query.get("mode") != ["ro"]:
            raise RuntimeError(f"Inspection blocked non-disposable or writable SQLite path: {target}")
        guards["readonly_copy_connections"] += 1
        return original_sqlite_connect(database, *args, **kwargs)

    sqlite3.connect = guarded_sqlite_connect

    def blocked_network(*_args, **_kwargs):
        guards["network_attempts"] += 1
        raise RuntimeError("Network access is disabled in Scene Direction inspection mode")

    socket.create_connection = blocked_network
    socket.getaddrinfo = blocked_network
    socket.gethostbyname = blocked_network
    socket.gethostbyaddr = blocked_network
    socket.socket.connect = blocked_network
    socket.socket.connect_ex = blocked_network
    socket.socket.send = blocked_network
    socket.socket.sendall = blocked_network
    socket.socket.sendto = blocked_network

    def block_process(*_args, **_kwargs):
        guards["process_start_attempts"] += 1
        raise RuntimeError("Subprocess execution is disabled in Scene Direction inspection mode")

    subprocess.Popen = block_process
    subprocess.run = block_process
    subprocess.call = block_process
    subprocess.check_call = block_process
    subprocess.check_output = block_process
    os.system = block_process

    def block_thread_start(_thread, *_args, **_kwargs):
        guards["worker_thread_start_attempts"] += 1
        raise RuntimeError("Worker/background threads are disabled in Scene Direction inspection mode")

    threading.Thread.start = block_thread_start
    try:
        import asyncio

        def block_async_task(*_args, **_kwargs):
            raise RuntimeError("Async background tasks are disabled in Scene Direction inspection mode")

        asyncio.create_task = block_async_task
        asyncio.ensure_future = block_async_task
    except ImportError:
        pass
    return guards


def check_inspection_decision_state(direction: Any) -> bool:
    """Enforce pristine decision gates, or report them skipped for saved boards.

    Returns True when strict decision assertions are skipped. Follows the
    G7 skip precedent: version-persisted scene_direction (surfaced as
    direction.saved) means the approved board legitimately carries creator
    decisions, so only the pristine-state gates are bypassed — approved
    prompts, camera details, references, shot identity, and every read-only
    and lifecycle gate stay enforced. Boards without saved decisions keep
    the strict fail-closed assertions; anomalous assigned rows without saved
    state still raise. Pure read: never mutates decisions.
    """
    if direction.saved:
        return True
    if any(row.status != "UNASSIGNED" for row in direction.coverage_decisions):
        raise RuntimeError("Unexpected creator decision data is present")
    if any(row.status != "UNASSIGNED" for row in direction.coverage_obligations):
        raise RuntimeError("Unexpected creator obligation assignments are present")
    return False


def inspect_scene(
    db_path: Path,
    *,
    source_db: Path = LIVE_DB,
    project_id: str = PROJECT_ID,
    scene_id: str = SCENE_ID,
) -> dict[str, Any]:
    _assert_readonly_copy(source_db, db_path)
    resolved_source = source_db.resolve(strict=True)
    resolved_copy = db_path.resolve(strict=True)
    if resolved_copy == LIVE_DB.resolve(strict=True):
        raise RuntimeError("Inspection refused: runtime database path resolves to the live database")
    if resolved_copy.parent == resolved_source.parent:
        raise RuntimeError("Inspection refused: disposable DB must live outside the source database directory")
    audio_output = BACKEND_ROOT / "outputs" / "audio"
    if not audio_output.is_dir():
        raise RuntimeError("Inspection refused: audio pipeline import would create a missing output directory")
    audio_before = _files_state((audio_output,))
    storage = ReadOnlySceneStorage(db_path, source_db=source_db)
    runtime_guards = _install_runtime_guards(storage.db_path)
    storage_guards = _install_inspection_service_namespace(storage)
    # Keep ProjectStore's import-time singleton within the disposable directory.
    os.environ["STUDIO_PROJECT_STORE_PATH"] = str(db_path.parent / "project_state_store.json")
    from app.services.scene_direction_service import SceneDirectionService
    from app.services.project_store import project_store as global_project_store

    # The coverage module uses the audio screenplay parser, but its service
    # module singleton creates outputs/audio and probes optional model packages.
    # Replace only that optional singleton with a pure-parser stub before the
    # coverage function's lazy import is reached.
    coverage_module_name = "app.services.scene_coverage_contract"
    coverage_path = BACKEND_ROOT / "app" / "services" / "scene_coverage_contract.py"
    coverage_spec = __import__("importlib.util", fromlist=["spec_from_file_location"])
    coverage_module_spec = coverage_spec.spec_from_file_location(coverage_module_name, coverage_path)
    if coverage_module_spec is None or coverage_module_spec.loader is None:
        raise RuntimeError("Could not load the current Scene Direction coverage contract")
    coverage_module = ModuleType(coverage_module_name)
    coverage_module.__file__ = str(coverage_path)
    coverage_module.__package__ = "app.services"
    sys.modules[coverage_module_name] = coverage_module
    coverage_module_spec.loader.exec_module(coverage_module)

    # Load only the existing pure parser definition; do not instantiate the
    # audio pipeline service or open audio/output files.
    import ast
    audio_source = (BACKEND_ROOT / "app" / "services" / "audio_pipeline_service.py").read_text()
    audio_tree = ast.parse(audio_source)
    parser_node = next((node for node in audio_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_extract_dialogue_lines"), None)
    if parser_node is None:
        raise RuntimeError("Pure screenplay dialogue parser not found")
    parser_module = ModuleType("_inspection_audio_parser")
    import re
    import typing
    import enum
    import hashlib as hashlib_module
    import json as json_module
    parser_module.__dict__.update({
        "re": re,
        "Any": Any,
        "List": typing.List,
        "Dict": typing.Dict,
        "Optional": typing.Optional,
    })
    parser_helper_names = {
        "_is_scene_heading", "_is_all_caps_section_header", "_is_action_line",
        "_SCENE_HEADING_RE", "_PARENTHETICAL_RE", "_VOCATIVE_PUNCT",
        "_ACTION_PRONOUNS", "_ACTION_PAUSE_OPENER_RE", "_ACTION_PAUSE_NOUNS",
    }
    selected_parser_nodes = []
    for node in audio_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in parser_helper_names:
            selected_parser_nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in parser_helper_names
            for target in node.targets
        ):
            selected_parser_nodes.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in parser_helper_names:
            selected_parser_nodes.append(node)
    selected_parser_nodes.append(parser_node)
    exec(compile(ast.Module(body=selected_parser_nodes, type_ignores=[]), str(BACKEND_ROOT / "app" / "services" / "audio_pipeline_service.py"), "exec"), parser_module.__dict__)
    original_import = __import__

    def inspection_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app.services.audio_pipeline_service":
            module = ModuleType(name)
            module._extract_dialogue_lines = parser_module._extract_dialogue_lines
            return module
        return original_import(name, globals, locals, fromlist, level)

    import builtins
    builtins.__import__ = inspection_import
    coverage_module._inspection_pure_audio_parser = parser_module._extract_dialogue_lines
    coverage_module._inspection_original_import = original_import
    coverage_module._inspection_import_hook = inspection_import

    expected_project_store_path = (db_path.parent / "project_state_store.json").resolve()
    if global_project_store._path.resolve() != expected_project_store_path:
        raise RuntimeError("ProjectStore singleton escaped the disposable inspection directory")
    if expected_project_store_path.exists():
        raise RuntimeError("Inspection refused to use a pre-existing project state store")
    service = SceneDirectionService(storage)

    def forbid_project_store_access(*_args, **_kwargs):
        raise RuntimeError("Scene Direction inspection must not read or write the ProjectStore")

    # The direct service read is fully backed by ReadOnlySceneStorage; fail closed
    # if a future dependency starts consulting the JSON project store.
    service.blueprints.project_store = type(
        "ForbiddenProjectStore",
        (),
        {"get_project": staticmethod(forbid_project_store_access)},
    )()
    # Inspection follows the approved-frozen rule (previs, canonical workflow,
    # render authorization), not the working draft: the approved opt-in keeps
    # the frozen contract stable while drafts advance. Same storage methods,
    # so the five-call read-only sequence is unchanged.
    direction = service.get(project_id, scene_id, version_selection="approved")
    # The second get_project call supports the scene setting identity read model
    # (SceneDirectionService._scene_setting_identity); both project reads are bounded and read-only.
    if storage.read_calls != [
        "get_storyboard_blueprint", "get_storyboard_blueprint_version", "list_storyboard_shots", "get_project", "get_project",
    ]:
        raise RuntimeError(f"Unexpected or mutating storage call path: {storage.read_calls}")
    if storage_guards["production_storage_factory_called"] or storage_guards["database_storage_initialized"]:
        raise RuntimeError(f"Production storage path was used: {storage_guards}")
    if storage_guards["inspection_storage_factory_calls"] != 1:
        raise RuntimeError(f"Expected one redirected service singleton factory call: {storage_guards}")
    if not storage_guards["singleton_storage_redirected_to_copy"]:
        raise RuntimeError("Service singleton storage was not redirected to the disposable database")
    if _files_state((audio_output,)) != audio_before:
        raise RuntimeError("Audio output artifacts changed during Scene Direction inspection")
    isolated_imports = _assert_forbidden_imports_absent()
    if runtime_guards["network_attempts"] or runtime_guards["process_start_attempts"] or runtime_guards["worker_thread_start_attempts"]:
        raise RuntimeError(f"Inspection attempted blocked runtime side effects: {runtime_guards}")
    if expected_project_store_path.exists():
        raise RuntimeError("Inspection created a ProjectStore file")
    imported_inspection_modules = {
        "scene_direction_service": "app.services.scene_direction_service" in sys.modules,
        "scene_coverage_contract": "app.services.scene_coverage_contract" in sys.modules,
        "scene_direction_models": "app.models.scene_direction" in sys.modules,
        "storyboard_models": "app.models.storyboard_blueprint" in sys.modules,
    }
    if not all(imported_inspection_modules.values()):
        raise RuntimeError(f"Required Scene Direction modules were not imported: {imported_inspection_modules}")
    if "app.services.audio_pipeline_service" in sys.modules:
        raise RuntimeError("Optional audio pipeline singleton was imported by the coverage inspection")
    counts = {
        "content_obligations": sum(row.obligation_type == "content" for row in direction.coverage_obligations),
        "dialogue_obligations": sum(row.obligation_type == "dialogue" for row in direction.coverage_obligations),
        "shot_content_dispositions": sum(row.obligation_type == "shot_content" for row in direction.coverage_decisions),
        "shot_dialogue_dispositions": sum(row.obligation_type == "shot_dialogue" for row in direction.coverage_decisions),
    }
    if counts != {
        "content_obligations": 40,
        "dialogue_obligations": 10,
        "shot_content_dispositions": 5,
        "shot_dialogue_dispositions": 5,
    }:
        raise RuntimeError(f"Coverage contract mismatch: {counts}")
    if direction.version_id != APPROVED_VERSION_ID or direction.version_status != "approved":
        raise RuntimeError("Scene Direction did not read the expected approved version")
    decision_assertions_skipped = check_inspection_decision_state(direction)
    snapshot = _semantic_snapshot(storage, project_id, scene_id)
    if len(snapshot["prompt_hashes"]) != 5 or len(snapshot["camera_plan_hashes"]) != 5:
        raise RuntimeError("Expected five prompts and camera plans in the approved storyboard version")
    if snapshot["reference_counts"] != {"DRE": 1, "MAYA": 1, "environment": 1}:
        raise RuntimeError(f"Expected exactly one DRE, MAYA, and environment canonical reference: {snapshot['reference_counts']}")
    return {
        "project_id": direction.project_id,
        "scene_id": direction.scene_id,
        "disposable_database": str(storage.db_path),
        "runtime_database_is_live_database": storage.db_path == LIVE_DB.resolve(strict=True),
        "inspection_runtime_pid": os.getpid(),
        "inspection_port": None,
        "version_id": direction.version_id,
        "version_status": direction.version_status,
        "saved": direction.saved,
        "creator_decisions_recorded": False,
        "saved_decisions_present": bool(direction.saved),
        "decision_assertions_skipped": decision_assertions_skipped,
        "coverage": counts,
        "unassigned_obligations": len(direction.coverage_obligations),
        "decision_status_counts": {"UNASSIGNED": sum(row.status == "UNASSIGNED" for row in direction.coverage_decisions)},
        "shot_ids": [shot.shot_id for shot in direction.shots],
        "prompts_identical_hashes": snapshot["prompt_hashes"],
        "camera_plans_identical_hashes": snapshot["camera_plan_hashes"],
        "canonical_reference_hashes": snapshot["reference_hashes"],
        "storage_calls": storage.read_calls,
        "production_storage_guards": storage_guards,
        "database_storage_initialized": storage_guards["database_storage_initialized"],
        "production_storage_factory_called": storage_guards["production_storage_factory_called"],
        "inspection_storage_factory_calls": storage_guards["inspection_storage_factory_calls"],
        "singleton_storage_redirected_to_copy": storage_guards["singleton_storage_redirected_to_copy"],
        "audio_output_unchanged": True,
        "audio_pipeline_service_imported": "app.services.audio_pipeline_service" in sys.modules,
        "isolated_imports": isolated_imports,
        "runtime_guards": runtime_guards,
        "schema_mutation_possible": False,
        "project_store_path": str(expected_project_store_path),
        "project_store_file_created": expected_project_store_path.exists(),
        "imported_inspection_modules": imported_inspection_modules,
        "queues_started": False,
        "runway_polling_started": False,
        "job_recovery_called": False,
        "lease_recovery_called": False,
        "training_refresh_called": False,
        "backup_created": False,
        "demo_seed_called": False,
        "schema_mutation_possible": False,
        "provider_contacted": False,
        "job_created": False,
        "render_occurred": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, default=LIVE_DB, help=argparse.SUPPRESS)
    parser.add_argument("--keep-copy", action="store_true", help="Keep the disposable DB copy and print its path")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON report")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source_db = args.source_db.resolve(strict=True)
    live_db_resolved = LIVE_DB.resolve(strict=True)
    live_before_db = _sha256(LIVE_DB)
    live_before_sidecars = {
        suffix: _sha256(Path(str(LIVE_DB) + suffix)) for suffix in ("-wal", "-shm")
    }
    before_state = _files_state(STATE_FILES)
    before_db = _sha256(source_db)
    before_sidecars = {suffix: _sha256(Path(str(source_db) + suffix)) for suffix in ("-wal", "-shm")}
    if source_db == live_db_resolved and (before_db != live_before_db or before_sidecars != live_before_sidecars):
        raise RuntimeError("Live database hashes changed while capturing the initial source state")
    scratch = Path(tempfile.mkdtemp(prefix="scene002-inspection-"))
    copy = _copied_db(scratch, source_db)
    copy_before = {suffix: _sha256(Path(str(copy) + suffix)) for suffix in ("", "-wal", "-shm")}
    storage = ReadOnlySceneStorage(copy, source_db=source_db)
    semantic_before = _semantic_snapshot(storage, PROJECT_ID, SCENE_ID)
    report = inspect_scene(copy, source_db=source_db)
    semantic_after = _semantic_snapshot(storage, PROJECT_ID, SCENE_ID)
    if any(report["runtime_guards"][key] for key in ("worker_thread_start_attempts", "network_attempts", "process_start_attempts")):
        raise RuntimeError(f"Inspection attempted to start a worker, access network, or spawn a process: {report['runtime_guards']}")
    if report["runtime_guards"]["readonly_copy_connections"] < 1:
        raise RuntimeError("Inspection did not verify its read-only disposable SQLite boundary")
    if semantic_before != semantic_after:
        raise RuntimeError("Approved storyboard version, prompt, camera, or reference data changed")
    copy_after = {suffix: _sha256(Path(str(copy) + suffix)) for suffix in ("", "-wal", "-shm")}
    after_db = _sha256(source_db)
    after_sidecars = {suffix: _sha256(Path(str(source_db) + suffix)) for suffix in ("-wal", "-shm")}
    after_state = _files_state(STATE_FILES)
    live_after_db = _sha256(LIVE_DB)
    live_after_sidecars = {
        suffix: _sha256(Path(str(LIVE_DB) + suffix)) for suffix in ("-wal", "-shm")
    }
    if copy_before != copy_after:
        raise RuntimeError("Disposable SQLite bytes changed during inspection")
    if before_db != after_db or before_sidecars != after_sidecars:
        raise RuntimeError("Source DB or WAL/SHM changed during inspection")
    if source_db == live_db_resolved and (live_before_db != after_db or live_before_sidecars != after_sidecars):
        raise RuntimeError("Live DB/WAL/SHM content differs from initial byte-copy source hashes")
    if before_state != after_state:
        raise RuntimeError("Backup or recovery-lineage state changed during inspection")
    if report["runtime_database_is_live_database"] or report["schema_mutation_possible"]:
        raise RuntimeError("Inspection runtime did not remain isolated from production SQLite")
    if not report["singleton_storage_redirected_to_copy"]:
        raise RuntimeError("No application singleton storage call confirmed disposable DB binding")
    if live_before_db != live_after_db or live_before_sidecars != live_after_sidecars:
        raise RuntimeError("Live DB or WAL/SHM changed during isolated inspection")
    report.update({
        "source_database": str(source_db),
        "approved_version_unchanged": True,
        "semantic_snapshot_before": semantic_before,
        "semantic_snapshot_after": semantic_after,
        "disposable_database": str(copy.resolve()),
        "disposable_db_hash_before": copy_before[""],
        "disposable_db_hash_after": copy_after[""],
        "source_db_hash_before": before_db,
        "source_db_hash_after": after_db,
        "live_db_hash_before": live_before_db,
        "live_db_hash_after": live_after_db,
        "source_sidecar_hashes_before": before_sidecars,
        "source_sidecar_hashes_after": after_sidecars,
        "live_sidecar_hashes_before": live_before_sidecars,
        "live_sidecar_hashes_after": live_after_sidecars,
        "live_backup_lineage_and_recovery_snapshots_unchanged": before_state == after_state,
        "stale_backend_pid_23048_stopped_or_restarted": False,
        "runtime": "direct service invocation; no HTTP server or listening port created",
        "inspection_runtime_pid": os.getpid(),
        "inspection_port": None,
        "copy_source_is_live_database": source_db == live_db_resolved,
        "runtime_database_is_live_database": copy.resolve() == live_db_resolved,
        "queues_started": report["queues_started"],
        "runway_polling_started": report["runway_polling_started"],
        "job_recovery_called": report["job_recovery_called"],
        "lease_recovery_called": report["lease_recovery_called"],
        "training_refresh_called": report["training_refresh_called"],
        "backup_created": report["backup_created"],
        "demo_seed_called": report["demo_seed_called"],
        "schema_mutation_possible": False,
        "database_storage_initialized": report["production_storage_guards"]["database_storage_initialized"],
        "production_storage_factory_called": report["production_storage_guards"]["production_storage_factory_called"],
        "inspection_storage_factory_calls": report["production_storage_guards"]["inspection_storage_factory_calls"],
        "singleton_storage_redirected_to_copy": report["production_storage_guards"]["singleton_storage_redirected_to_copy"],
        "runtime_guards": report["runtime_guards"],
        "readonly_write_probe_blocked": True,
        "provider_contacted": report["provider_contacted"],
        "job_created": report["job_created"],
        "render_occurred": report["render_occurred"],
    })
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    if not args.keep_copy:
        shutil.rmtree(scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
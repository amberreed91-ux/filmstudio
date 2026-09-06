from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Barrier, Lock, get_ident

import pytest

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.models.storyboard_blueprint import StoryboardShotVisualPlan
from app.services.editorial_intelligence_service import EditorialIntelligenceService
from app.services.project_store import ProjectStore


def test_legacy_storyboard_props_keep_the_saved_items():
    plan = StoryboardShotVisualPlan(props="L train, elevated tracks, stroller, Lake Michigan")
    assert plan.props == ["L train", "elevated tracks", "stroller", "Lake Michigan"]
    assert StoryboardShotVisualPlan(props=["brass key"]).props == ["brass key"]


@pytest.mark.parametrize("raises", [False, True])
def test_uncommitted_pool_connection_releases_writer_lock(tmp_path, raises):
    storage = DatabaseStorage(str(tmp_path / "database"))
    with storage._get_connection() as connection:
        connection.execute("CREATE TABLE activation_probe (value TEXT UNIQUE)")
        connection.commit()
    try:
        with storage._get_connection() as connection:
            connection.execute("INSERT INTO activation_probe VALUES ('uncommitted')")
            if raises:
                connection.execute("INSERT INTO activation_probe VALUES ('uncommitted')")
    except sqlite3.IntegrityError:
        assert raises
    # An independent connection must acquire a writer lock immediately after
    # either a failed write or an early return with an unfinished transaction.
    with sqlite3.connect(storage.db_path, timeout=0.1) as other:
        other.execute("BEGIN IMMEDIATE")
        assert other.execute("SELECT count(*) FROM activation_probe").fetchone()[0] == 0
        other.execute("INSERT INTO activation_probe VALUES ('committed')")
    with storage._get_connection() as connection:
        assert connection.execute("SELECT value FROM activation_probe").fetchone()[0] == "committed"


def _editorial(tmp_path, project_ids):
    storage = DatabaseStorage(str(tmp_path / "database"))
    state = ProjectStore(str(tmp_path / "projects.json"))
    for project_id in project_ids:
        project = {"project_id": project_id, "title": project_id,
                   "execution_summary": {"scenes": [{"scene_id": "scene_001", "text": "Maya holds the key."}]},
                   "film_cut": {"cut_id": "default", "scene_order": ["scene_001"]}}
        state.save_project(project)
        storage.save_project(StudioProject(**project))
    return EditorialIntelligenceService(storage=storage, project_store_service=state), storage


def test_legacy_default_cut_ids_do_not_collide_between_films(tmp_path):
    service, storage = _editorial(tmp_path, ["film-one", "film-two"])
    first = service.get_current_cut("film-one")
    second = service.get_current_cut("film-two")
    assert first["cut_id"] != second["cut_id"]
    assert first["project_id"] == "film-one"
    assert second["project_id"] == "film-two"
    assert first["scene_order"] == second["scene_order"] == ["scene_001"]
    assert service.get_current_cut("film-two")["cut_id"] == second["cut_id"]


def test_concurrent_cut_bootstrap_reuses_the_same_committed_version(tmp_path, monkeypatch):
    service, storage = _editorial(tmp_path, ["film-one"])
    original = storage.get_current_film_cut
    barrier, lock, seen = Barrier(2), Lock(), set()
    def synchronize_initial_read(project_id):
        result = original(project_id)
        with lock:
            first = get_ident() not in seen
            seen.add(get_ident())
        if first:
            barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(storage, "get_current_film_cut", synchronize_initial_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.get_current_cut, ["film-one", "film-one"]))
    assert results[0]["cut_id"] == results[1]["cut_id"]
    assert len(storage.list_film_cut_versions("film-one")) == 1

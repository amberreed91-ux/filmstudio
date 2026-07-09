from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.data.storage import DatabaseStorage
from app.models.video_assets import VideoAsset, VideoMetadataMatch
from app.services.scene_intelligence_store import SceneIntelligenceStore
from app.services.video_metadata_matching_service import VideoMetadataMatchingService


class _AssetServiceStub:
    def __init__(self, assets: dict[str, VideoAsset]):
        self.assets = assets
        self.updated: dict[str, dict] = {}

    def get_asset(self, asset_id: str):
        return self.assets.get(asset_id)

    def list_assets(self, source_type: str | None = None):
        rows = list(self.assets.values())
        if source_type:
            rows = [a for a in rows if a.source_type == source_type]
        return rows

    def update_asset_status(self, *, asset_id: str, status: str, metadata_patch: dict | None = None):
        asset = self.assets.get(asset_id)
        if not asset:
            return None
        merged = dict(asset.metadata or {})
        if metadata_patch:
            merged.update(metadata_patch)
        asset.metadata = merged
        asset.status = status
        asset.updated_at = datetime.now(timezone.utc).isoformat()
        self.updated[asset_id] = merged
        return asset


def _mk_asset(*, asset_id: str, title: str, filename: str, duration: float | None = None, size: int | None = None, tags=None) -> VideoAsset:
    return VideoAsset(
        asset_id=asset_id,
        project_id="project-test",
        source_type="uploaded_file",
        title=title,
        description="",
        duration_seconds=duration,
        file_size_bytes=size,
        status="available",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        metadata={"original_filename": filename, "tags": tags or []},
    )


def _service(tmp_path: Path, asset_service: _AssetServiceStub) -> VideoMetadataMatchingService:
    storage = DatabaseStorage(str(tmp_path / "match.db"))
    scene_store = SceneIntelligenceStore(path=str(tmp_path / "scene_intelligence.json"))
    scene_store.import_batch(
        {
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "film_title": "Noir Test",
                    "scene_name": "Downtown Chase",
                    "intent": "Fast chase",
                    "emotional_beat_arc": ["tension"],
                    "camera_logic": ["tracking"],
                    "pacing_curve": ["fast"],
                    "director_notes": "Go kinetic",
                    "expected_video_filename": "scene_001.mp4",
                    "duration_seconds": 12.0,
                    "tags": ["chase", "night"],
                },
                {
                    "scene_id": "scene_002",
                    "film_title": "Noir Test",
                    "scene_name": "Rooftop Confession",
                    "intent": "Emotional reveal",
                    "emotional_beat_arc": ["quiet"],
                    "camera_logic": ["static"],
                    "pacing_curve": ["slow"],
                    "director_notes": "Hold longer",
                    "duration_seconds": 20.0,
                    "tags": ["rooftop", "dialogue"],
                },
            ]
        }
    )

    svc = VideoMetadataMatchingService()
    svc._storage = storage
    svc._video_asset_service = asset_service
    svc._scene_intelligence_store = scene_store
    return svc


def test_exact_filename_match_auto_confirms(tmp_path: Path):
    asset = _mk_asset(asset_id="asset-1", title="Scene 1", filename="scene_001.mp4")
    svc = _service(tmp_path, _AssetServiceStub({asset.asset_id: asset}))

    result = svc.auto_match_uploaded_asset(asset.asset_id)
    assert result is not None
    assert result["match"].match_status == "auto_confirmed"
    assert result["confidence"] >= 0.95


def test_normalized_filename_match_creates_strong_match(tmp_path: Path):
    asset = _mk_asset(asset_id="asset-2", title="Downtown Chase Alt", filename="downtown_chase.mov")
    svc = _service(tmp_path, _AssetServiceStub({asset.asset_id: asset}))

    result = svc.auto_match_uploaded_asset(asset.asset_id)
    assert result is not None
    assert result["confidence"] >= 0.80
    assert result["match"].metadata_id == "scene_001"


def test_duration_similarity_improves_score(tmp_path: Path):
    low = _mk_asset(asset_id="asset-low", title="Rooftop Confession", filename="rooftop_take.mp4", duration=45.0)
    high = _mk_asset(asset_id="asset-high", title="Rooftop Confession", filename="rooftop_take.mp4", duration=20.2)
    svc = _service(tmp_path, _AssetServiceStub({low.asset_id: low, high.asset_id: high}))

    record = dict(svc._scene_intelligence_store.get_record("scene_002"))
    record["duration_seconds"] = 20.0
    low_score = svc.score_metadata_match(low, record)[0]
    high_score = svc.score_metadata_match(high, record)[0]
    assert high_score > low_score


def test_unrelated_metadata_does_not_match(tmp_path: Path):
    asset = _mk_asset(asset_id="asset-3", title="Birthday Party", filename="vacation_2024.mp4")
    svc = _service(tmp_path, _AssetServiceStub({asset.asset_id: asset}))

    result = svc.auto_match_uploaded_asset(asset.asset_id)
    assert result is None


def test_proposed_match_can_be_confirmed(tmp_path: Path):
    asset = _mk_asset(asset_id="asset-4", title="Rooftop confession alt", filename="rooftop_dialogue_b.mp4")
    stub = _AssetServiceStub({asset.asset_id: asset})
    svc = _service(tmp_path, stub)

    res = svc.auto_match_uploaded_asset(asset.asset_id)
    assert res is not None
    match = res["match"]
    if match.match_status == "auto_confirmed":
        match.match_status = "proposed"
        svc._storage.save_video_metadata_match(match)

    confirmed = svc.confirm_match(match.match_id)
    assert confirmed is not None
    assert confirmed.match_status == "confirmed"


def test_proposed_match_can_be_rejected(tmp_path: Path):
    asset = _mk_asset(asset_id="asset-5", title="Rooftop confession alt", filename="rooftop_dialogue_b.mp4")
    svc = _service(tmp_path, _AssetServiceStub({asset.asset_id: asset}))

    res = svc.auto_match_uploaded_asset(asset.asset_id)
    assert res is not None
    match = res["match"]
    match.match_status = "proposed"
    svc._save_match(match)

    rejected = svc.reject_match(match.match_id)
    assert rejected is not None
    assert rejected.match_status == "rejected"


def test_confirmed_match_updates_video_asset_metadata_and_preserves_tags(tmp_path: Path):
    asset = _mk_asset(asset_id="asset-6", title="Scene 1", filename="scene_001.mp4", tags=["user-tag"])
    stub = _AssetServiceStub({asset.asset_id: asset})
    svc = _service(tmp_path, stub)

    res = svc.auto_match_uploaded_asset(asset.asset_id)
    assert res is not None
    match: VideoMetadataMatch = res["match"]
    svc.confirm_match(match.match_id)

    merged = stub.updated[asset.asset_id]
    assert "user-tag" in merged.get("tags", [])
    assert merged.get("matched_metadata_id") == "scene_001"


def test_list_unmatched_assets(tmp_path: Path):
    matched = _mk_asset(asset_id="asset-7", title="Scene 1", filename="scene_001.mp4")
    unmatched = _mk_asset(asset_id="asset-8", title="Unknown", filename="x_random.mp4")
    svc = _service(tmp_path, _AssetServiceStub({matched.asset_id: matched, unmatched.asset_id: unmatched}))

    assert svc.auto_match_uploaded_asset(matched.asset_id) is not None
    rows = svc.list_unmatched_assets()
    ids = {a.asset_id for a in rows}
    assert unmatched.asset_id in ids
    assert matched.asset_id not in ids

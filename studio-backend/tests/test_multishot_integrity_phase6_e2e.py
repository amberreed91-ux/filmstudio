from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.data.storage import DatabaseStorage
from app.models import RenderJobOutput, StudioProject
from app.models.scene_direction import SaveSceneDirection

from app.services import render as render_module
from app.services.project_store import ProjectStore
from app.services.scene_coverage_contract import resolve_scene_lineage
from app.services.scene_direction_service import SceneDirectionService
from app.services.scene_production_pipeline_service import SceneProductionPipelineService
from app.services.stability import ValidationError
from app.services.storyboard_blueprint_service import StoryboardBlueprintService

PROJECT_ID = "project_phase6_lantern_fixture"
SCENE_ID = "scene_lantern_17"
HEADING = "INT. GLASSWORKS - DAWN"
BODY = (
    "IVO\n"
    "I kept the winter key.\n"
    "Neri sets the brass key beside the cold furnace."
)
SCRIPT = f"{HEADING}\n{BODY}\n\nEXT. CANAL - DAY\nA ferry passes."
SHOT_IDS = [f"{SCENE_ID}_shot_{number:03d}" for number in (1, 2)]
# R4.5-B3.1 (Checkpoint G rebuild, T2): the production-path Router leg runs
# under this owner with a mocked adapter transport (sockets blocked). The
# rejected environment row is genuine fixture data through the real
# persistence API — the F5 mint requires a non-empty rejected list and the
# adapter refuses a synthesized or empty one.
CHECKPOINT_G_OWNER = "checkpoint-g-owner"
CHECKPOINT_G_ROUTER_CONFIG_ID = "offline-multishot-test-router"
CHECKPOINT_G_REJECTED_ENV_REF_ID = "ref-glassworks-rejected-alt"
CAMERA_PLAN = {
    "camera": "locked tripod",
    "framing": "medium close-up",
    "lens": "normal perspective",
    "focal_length": "50 mm",
    "aperture": "deep focus",
    "composition": "key in the lower third",
    "blocking": "IVO remains frame left; the key stays on the workbench",
}


class FakeVideoAdapter:
    """Captures the actual RenderService adapter boundary without network access."""

    def __init__(self, output_dir: Path, calls: list[dict]):
        self.output_dir = output_dir
        self.calls = calls

    async def submit_job(self, job):
        assert job.provider == "simulated"
        assert job.input_payload is not None
        self.calls.append({
            "provider": job.provider,
            "job_id": job.id,
            "shot_id": job.shot_id,
            "input": job.input_payload.model_dump(mode="json"),
            "metadata": deepcopy(job.metadata or {}),
        })
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{job.shot_id}.mp4"
        (self.output_dir / filename).write_bytes(b"synthetic-render")
        job.provider_job_id = f"fake-{job.id}"
        job.status = "complete"
        job.progress = 100
        job.output_payload = RenderJobOutput(asset_url=f"/outputs/renders/{filename}")
        return job


class FakeAudioService:
    def __init__(self):
        self.calls: list[dict] = []

    async def generate_full_pipeline(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        source = Path(kwargs["video_path"])
        final_path = source.with_name(f"{source.stem}_audio.mp4")
        final_path.write_bytes(b"synthetic-video-with-audio")
        return {
            "job_id": f"audio-{kwargs['scene_id']}",
            "dialogue_provider": "none",
            "score_ambient_provider": "none",
            "final_video_path": str(final_path),
            "final_video_url": f"/outputs/renders/{final_path.name}",
        }


class FakeStitchingService:
    def __init__(self):
        self.calls: list[dict] = []

    def stitch_scene(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return {
            "status": "complete",
            "clip_count": len(SHOT_IDS),
            "duration_seconds": 8.0,
            "shot_ids": list(SHOT_IDS),
            "output_url": f"/outputs/scene_assemblies/{PROJECT_ID}_{SCENE_ID}.mp4",
            "output_path": str(Path(kwargs["project"]["execution_summary"]["one_button_render_jobs"][0]["output_url"])),
        }


def _scene() -> dict:
    return {
        "scene_id": SCENE_ID,
        "heading": HEADING,
        "text": BODY,
        "description": "A key changes hands beside a cold furnace.",
        "characters": ["IVO", "Neri"],
        "setting_id": "set-glassworks-fixture",
        "emotional_tone": "quiet resolve",
    }


def _project() -> dict:
    return {
        "project_id": PROJECT_ID,
        "title": "The Last Lantern — synthetic fixture",
        "script_text": SCRIPT,
        "execution_summary": {
            "scenes": [_scene()],
            "dialogue_lines": [{
                "line_id": "dlg-lantern-ivo-001",
                "scene_id": SCENE_ID,
                "character": "IVO",
                "text": "I kept the winter key.",
            }],
        },
    }


@pytest.fixture

def phase6(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """All canonical/project/render state is scoped to this synthetic fixture."""
    from app.services import reference_validation
    from app.services import storyboard_blueprint_service as storyboard_module

    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    storage = DatabaseStorage(str(tmp_path / "sqlite"))
    state = ProjectStore(str(tmp_path / "project-state.json"))
    project = _project()
    project_model = StudioProject(**project)
    storage.save_project(project_model)
    state.save_project(project)

    monkeypatch.setattr(reference_validation, "project_store", state)
    monkeypatch.setattr("app.data.storage.get_storage", lambda *_args, **_kwargs: storage)
    monkeypatch.setattr(storyboard_module.storyboard_blueprint_service, "storage", storage)
    monkeypatch.setattr(storyboard_module.storyboard_blueprint_service, "project_store", state)

    storage.save_character(PROJECT_ID, "IVO", {"id": "char-ivo", "visual_prompt_summary": "IVO"})
    storage.save_character(PROJECT_ID, "Neri", {"id": "char-neri", "visual_prompt_summary": "Neri"})
    for ref_id, character_id in (("ref-ivo-face", "char-ivo"), ("ref-neri-face", "char-neri")):
        storage.save_reference_asset({
            "ref_id": ref_id,
            "project_id": PROJECT_ID,
            "kind": "character_face",
            "image_url": f"https://fixture.invalid/{character_id}.png",
            "target_type": "character",
            "target_id": character_id,
            "category": "face",
            "approval_state": "approved",
            "canonical": True,
            "source_kind": "confirmed",
        })

    storage.save_universe_node({
        "node_id": "set-glassworks-fixture",
        "project_id": PROJECT_ID,
        "node_type": "location",
        "name": "Glassworks",
        "description": "An abandoned glassworks at dawn.",
        "first_scene": SCENE_ID,
        "last_scene": SCENE_ID,
    })
    assert storage.save_reference_asset({
        "ref_id": "ref-glassworks-fixture",
        "project_id": PROJECT_ID,
        "kind": "environment",
        "image_url": "https://fixture.invalid/glassworks.png",
        "target_type": "setting",
        "target_id": "set-glassworks-fixture",
        "category": "environment",
        "approval_state": "approved",
        "canonical": True,
        "source_kind": "confirmed",
    })

    direction = SceneDirectionService(storage)
    direction.blueprints.project_store = state
    board = direction.blueprints.get_or_create_blueprint(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        shot_count=2,
    )
    source_version = board["version"].version_id
    source_shots = storage.list_storyboard_shots(board["blueprint"].blueprint_id, source_version)
    assert len(source_shots) == 2
    for number, shot in enumerate(source_shots, start=1):
        prompt = (
            "IVO studies the old brass key in still dawn light; restrained, precise action."
            if number == 1
            else "Neri places the brass key beside the cold furnace; quiet reaction, no spoken words."
        )
        shot.intent.character_focus = ["IVO"] if number == 1 else ["Neri"]
        shot.render_contract.provider_neutral_prompt = prompt
        shot.render_contract.render_readiness = "ready"
        shot.render_contract.render_blockers = []
        shot.render_contract.structured_parameters.update({
            "camera_plan": deepcopy(CAMERA_PLAN),
            "negative_prompt": "No text, no subtitles, no additional people.",
        })
        storage.save_storyboard_shot(shot)

    # The creator-flow regression starts from a genuinely approved source board;
    # its Scene Direction decision must create and approve a distinct successor.
    from app.models.storyboard_blueprint import StoryboardBlueprintStatus

    source = storage.get_storyboard_blueprint_version(source_version)
    source.status = StoryboardBlueprintStatus.APPROVED
    source.approved_at = "2026-10-01T00:00:00+00:00"
    source.approved_by = "synthetic-test-creator"
    storage.save_storyboard_blueprint_version(source)
    blueprint = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    blueprint.status = StoryboardBlueprintStatus.APPROVED
    blueprint.approved_version_id = source_version
    storage.save_storyboard_blueprint(blueprint)

    return {
        "tmp_path": tmp_path,
        "backend_root": backend_root,
        "storage": storage,
        "state": state,
        "project": project,
        "direction": direction,
        "board": board,
        "source_version": source_version,
        "source_shots": source_shots,
    }


def _decide_every_obligation(direction: SceneDirectionService, *, unresolved_content_id: str = "") -> SaveSceneDirection:
    data = direction.get(PROJECT_ID, SCENE_ID)
    decisions = []
    content_text = {
        row.obligation_id: row.source_text
        for row in data.coverage_obligations
        if row.obligation_type == "content"
    }
    for row in data.coverage_decisions:
        if row.obligation_type == "content":
            status = "UNASSIGNED" if row.obligation_id == unresolved_content_id else "ASSIGNED"
            source_text = content_text[row.obligation_id]
            decisions.append(row.model_copy(update={
                "status": status,
                "shot_id": None if status == "UNASSIGNED" else (
                    SHOT_IDS[1] if source_text.startswith("Neri sets") else SHOT_IDS[0]
                ),
                "reason": "",
            }))
        elif row.obligation_type == "dialogue":
            decisions.append(row.model_copy(update={"status": "ASSIGNED", "shot_id": SHOT_IDS[0], "reason": ""}))
        elif row.obligation_type == "shot_dialogue" and row.obligation_id == SHOT_IDS[1]:
            decisions.append(row.model_copy(update={
                "status": "INTENTIONAL_SILENCE",
                "reason": "The creator chose to hold this reaction without speech.",
            }))
        else:
            decisions.append(row)

    dialogue = [line.model_copy(update={"shot_id": SHOT_IDS[0]}) for line in data.dialogue]
    handoffs = [
        {"shot_id": shot.shot_id, "opening_state": "", "action_change": "", "ending_state": ""}
        for shot in data.shots
    ]
    return SaveSceneDirection(
        expected_version_id=data.version_id,
        dialogue=[line.model_dump() for line in dialogue],
        coverage_decisions=[row.model_dump() for row in decisions],
        handoffs=handoffs,
    )


def _prepare_approved_successor(fixture: dict, *, unresolved_content_id: str = ""):
    direction = fixture["direction"]
    payload = _decide_every_obligation(direction, unresolved_content_id=unresolved_content_id)
    saved = direction.save(PROJECT_ID, SCENE_ID, payload)
    direction_successor_id = saved.version_id
    assert fixture["storage"].get_storyboard_blueprint_version(
        direction_successor_id
    ).source_version_id == fixture["source_version"]
    successor_id = saved.version_id
    board = fixture["storage"].get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    successor_shots = fixture["storage"].list_storyboard_shots(board.blueprint_id, successor_id)

    # Scene Direction clones the approved source version. Restore the explicitly
    # authored camera plan and persist it on each successor shot before review.
    for shot in successor_shots:
        shot.render_contract.structured_parameters["camera_plan"] = deepcopy(CAMERA_PLAN)
        fixture["storage"].save_storyboard_shot(shot)

    # Scene Direction only records a setting choice against an already-approved
    # current version. Promote the reviewed test fixture version as creator input
    # before entering the separate decision-save step.
    from app.models.storyboard_blueprint import StoryboardBlueprintStatus

    review = fixture["storage"].get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    review.metadata = {
        **(review.metadata or {}),
        "continuity_review": {
            "version_id": successor_id,
            "status": "completed",
        },
    }
    fixture["storage"].save_storyboard_blueprint(review)
    fixture["direction"].blueprints.derive_and_approve_image_prompts_for_version(version_id=successor_id)
    board = fixture["direction"].blueprints.approve_version(
        blueprint_id=board.blueprint_id,
        version_id=successor_id,
        approved_by="synthetic-test-creator",
    )["blueprint"]
    current_direction = direction.get(PROJECT_ID, SCENE_ID)
    if current_direction.canonical_setting_id and current_direction.setting_reference_options:
        from app.models.scene_direction import SettingReferenceDecision

        setting_payload = _decide_every_obligation(direction, unresolved_content_id=unresolved_content_id).model_copy(
            update={"setting_reference_decision": SettingReferenceDecision(
                canonical_setting_id=current_direction.canonical_setting_id,
                reference_id=current_direction.setting_reference_options[0].ref_id,
            )}
        )
        saved = direction.save(PROJECT_ID, SCENE_ID, setting_payload)
        successor_id = saved.version_id
        board = fixture["storage"].get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
        successor_shots = fixture["storage"].list_storyboard_shots(board.blueprint_id, successor_id)
        for shot in successor_shots:
            shot.render_contract.structured_parameters["camera_plan"] = deepcopy(CAMERA_PLAN)
            fixture["storage"].save_storyboard_shot(shot)
        review = fixture["storage"].get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
        review.metadata = {
            **(review.metadata or {}),
            "continuity_review": {
                "version_id": successor_id,
                "status": "completed",
            },
        }
        fixture["storage"].save_storyboard_blueprint(review)
    fixture["direction"].blueprints.run_continuity_review(
        blueprint_id=board.blueprint_id,
        version_id=successor_id,
    )
    fixture["direction"].blueprints.derive_and_approve_image_prompts_for_version(version_id=successor_id)
    approved = fixture["direction"].blueprints.approve_version(
        blueprint_id=board.blueprint_id,
        version_id=successor_id,
        approved_by="synthetic-test-creator",
    )
    assert approved["version"].source_version_id == direction_successor_id
    return saved, approved


@pytest.mark.asyncio
async def test_creator_decisions_reach_real_multishot_render_dispatch_and_durable_results(
    phase6, monkeypatch: pytest.MonkeyPatch,
):
    from app.services import generation_cost_gate, generation_context_service

    fixture = phase6
    storage = fixture["storage"]
    saved, approved = _prepare_approved_successor(fixture)
    board = approved["blueprint"]
    source_version = storage.get_storyboard_blueprint_version(fixture["source_version"])
    source_shots = storage.list_storyboard_shots(board.blueprint_id, fixture["source_version"])
    source_prompts = {shot.shot_id: shot.render_contract.provider_neutral_prompt for shot in source_shots}

    lineage = resolve_scene_lineage(PROJECT_ID, fixture["project"], _scene())
    assert lineage["status"] == "RESOLVED"
    assert SCRIPT[lineage["scene_source_start"]:lineage["scene_source_end"]] == BODY
    assert saved.version_id != fixture["source_version"]
    assert saved.setting_reference_decision is not None
    assert saved.setting_reference_decision.canonical_setting_id == "set-glassworks-fixture"
    assert all(
        row.status != "UNASSIGNED"
        for row in saved.coverage_obligations
    )
    assert not any("canonical scene content unresolved" in blocker for blocker in saved.coverage_blockers)
    # Scene Direction's readiness snapshot also reports camera provenance, which
    # this test resolves in the pipeline's authoritative storyboard path below.
    assert source_version.status.value == "approved"
    assert all(shot.render_contract.provider_neutral_prompt == source_prompts[shot.shot_id] for shot in source_shots)
    assert board.current_version_id == board.approved_version_id == saved.version_id

    from app.access_context import access_user_id
    from app.adapters import RunwayRouterAdapter
    from app.models import ProviderConfig
    from app.models.storyboard_blueprint import StoryboardBlueprintStatus
    from app.services.providers import runway_router_provider
    from app.services.reference_asset_service import ReferenceAssetService
    from app.services.reference_validation import reference_binding_digest

    # R4.5-B3.1: the generic Router leg needs owner authority, a genuine
    # rejected environment row, and durable per-shot confirmations — all via
    # production storage/service APIs, seeded after the approved successor so
    # the successor decision still selects the approved anchor.
    storage.access_save_user(
        {"username": CHECKPOINT_G_OWNER, "user_id": CHECKPOINT_G_OWNER}, create=True
    )
    storage.access_claim_project(PROJECT_ID, CHECKPOINT_G_OWNER)
    storage.save_reference_asset({
        "ref_id": CHECKPOINT_G_REJECTED_ENV_REF_ID,
        "project_id": PROJECT_ID,
        "kind": "environment",
        "image_url": "https://fixture.invalid/glassworks-alt.png",
        "target_type": "setting",
        "target_id": "set-glassworks-fixture",
        "category": "environment",
        "approval_state": "rejected",
        "canonical": False,
        "source_kind": "confirmed",
    })
    binder = ReferenceAssetService(storage)
    for shot_id in SHOT_IDS:
        fresh = binder.resolve_shot_binding(PROJECT_ID, shot_id)
        binder.record_shot_confirmation(PROJECT_ID, shot_id, fresh["binding_digest"])

    # Mocked adapter transport: dry-run, submit, then a poll. Sockets stay
    # blocked by the r43k plugin — the doubles record every call as the
    # no-live-contact tripwire.
    transport_calls: list[dict] = []

    def _capture(url, *, method="GET", payload=None, api_key=None):
        transport_calls.append({"url": url, "method": method, "payload": deepcopy(payload)})
        if method == "POST" and payload and payload.get("dryRun"):
            return {
                "dryRun": True,
                "routing": {
                    "model": "gen4.5", "provider": "runway",
                    "configId": CHECKPOINT_G_ROUTER_CONFIG_ID,
                    "estimatedCost": {"credits": 1},
                },
            }
        if method == "POST":
            return {
                "dryRun": False,
                "id": "checkpoint-g-task",
                "routing": {
                    "model": "gen4.5", "provider": "runway",
                    "configId": CHECKPOINT_G_ROUTER_CONFIG_ID,
                    "estimatedCost": {"credits": 1},
                },
            }
        return {
            "id": "checkpoint-g-task",
            "status": "SUCCEEDED",
            "output": ["https://cdn.test/checkpoint-g.mp4"],
        }

    monkeypatch.setenv("RUNWAY_API_KEY", "test-key")
    monkeypatch.setenv("RUNWAY_ROUTER_CONFIG_ID", CHECKPOINT_G_ROUTER_CONFIG_ID)
    monkeypatch.setenv("STUDIO_MAX_COST_PER_GENERATION_CREDITS", "0")
    monkeypatch.setattr(runway_router_provider, "_runway_router_request", _capture)
    monkeypatch.setattr(runway_router_provider.time, "sleep", lambda *_: None)

    router_config = ProviderConfig(
        provider_id="runway_router",
        name="Runway Model Router",
        enabled=True,
        is_simulated=False,
        api_key="test-key",
        api_endpoint="https://api.dev.runwayml.com",
        requires=["api_key"],
        capabilities=["video_generation", "model_routing"],
    )
    adapter_calls: list[dict] = []
    adapter_factory_calls: list[str] = []

    class _CheckpointGRouterAdapter(RunwayRouterAdapter):
        """Runs the REAL adapter boundary (declaration, projection, mocked
        transport), then substitutes only the provider's rendered media bytes
        with a synthetic local file — the offline equivalent of a download."""

        async def submit_job(self, job, *, reference_storage=None):
            adapter_factory_calls.append(job.provider)
            result = await super().submit_job(job, reference_storage=reference_storage)
            adapter_calls.append({
                "provider": result.provider,
                "job_id": result.id,
                "shot_id": result.shot_id,
                "status": result.status,
                "input": result.input_payload.model_dump(mode="json"),
                "metadata": deepcopy(result.metadata or {}),
            })
            if result.status == "complete":
                output_dir = fixture["backend_root"] / "outputs" / "renders"
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / f"{result.shot_id}.mp4").write_bytes(b"synthetic-router-render")
                result.output_payload = result.output_payload.model_copy(
                    update={"asset_url": f"/outputs/renders/{result.shot_id}.mp4"}
                )
            return result

    render_svc = render_module.RenderService()
    monkeypatch.setattr(render_module, "_storage", storage)
    monkeypatch.setattr(
        render_module, "get_adapter",
        lambda provider, _config: _CheckpointGRouterAdapter(router_config),
    )
    for name in ("_run_continuity_review", "_run_render_quality_check", "_run_character_reference_lock", "_notify_update"):
        monkeypatch.setattr(render_module, name, AsyncMock())
    monkeypatch.setattr(generation_cost_gate.generation_cost_gate, "enforce_shot_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(generation_cost_gate.generation_cost_gate, "estimate_batch", lambda **_kwargs: {"estimated": False})

    audio = FakeAudioService()
    stitch = FakeStitchingService()
    pipeline = SceneProductionPipelineService(
        render_svc=render_svc,
        audio_svc=audio,
        stitching_svc=stitch,
        backend_root=fixture["backend_root"],
    )
    # R4.5-B3.1: the batch is prepared for the production Router provider
    # with the generic projection-authorization mint active (the submission
    # entrypoint signal). Every entry must carry its minted declaration.
    preflight = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="runway_router",
        mint_generic_authorization=True,
    )
    assert preflight["ready"] is True, preflight["blockers"]
    assert [shot["shot_id"] for shot in preflight["shots"]] == SHOT_IDS
    assert [entry["shot_id"] for entry in preflight["entries"]] == SHOT_IDS
    assert preflight["manifest"]["scene"]["scene_source_identity"] == lineage["scene_source_identity"]
    for entry in preflight["entries"]:
        authorization = entry["reference_projection_authorization"]
        assert isinstance(authorization, dict)
        assert authorization["authorization_policy_id"] == "runway_reference_projection_authorization"
        assert authorization["project_id"] == PROJECT_ID
        assert authorization["scene_id"] == SCENE_ID
        assert authorization["shot_id"] == entry["shot_id"]
        assert authorization["setting_id"] == "set-glassworks-fixture"
        assert authorization["authorized_environment_ref_id"] == "ref-glassworks-fixture"
        assert authorization["rejected_environment_ref_ids"] == [CHECKPOINT_G_REJECTED_ENV_REF_ID]
        assert authorization["frozen_reference_binding_sha256"] == reference_binding_digest(entry["reference_binding"])
        assert authorization["frozen_reference_binding"] == entry["reference_binding"]
        assert isinstance(authorization["confirmation_id"], str) and authorization["confirmation_id"]
        assert isinstance(entry["generic_authorization_audit"], dict)

    # Trace both ordinary multishot contracts through the exact deterministic
    # Runway Router request reconstruction used at adapter submission. R4.5-B1
    # (F8) freezes Router jobs with empty creative parameters, so the
    # reconstruction passes its creative-parameters gate and composes the
    # wire referenceImages from the frozen proof. The provider transport
    # remains untouched (mocked doubles below).
    from app.services.generation_contract import FrozenGenerationContract
    from app.services.providers.runway_router_provider import reconstruct_runway_router_video_request

    expected_reference_ids_by_shot = {
        SHOT_IDS[0]: ["ref-ivo-face", "ref-glassworks-fixture"],
        SHOT_IDS[1]: ["ref-neri-face", "ref-glassworks-fixture"],
    }
    expected_reference_uris_by_shot = {
        SHOT_IDS[0]: [
            "https://fixture.invalid/char-ivo.png",
            "https://fixture.invalid/glassworks.png",
        ],
        SHOT_IDS[1]: [
            "https://fixture.invalid/char-neri.png",
            "https://fixture.invalid/glassworks.png",
        ],
    }
    for entry in preflight["entries"]:
        shot_id = entry["shot_id"]
        expected_reference_ids = expected_reference_ids_by_shot[shot_id]
        expected_reference_uris = expected_reference_uris_by_shot[shot_id]
        assert len(expected_reference_ids) == len(expected_reference_uris)
        
        frozen = FrozenGenerationContract.from_record(entry["generation_contract"])
        frozen_references = [
            reference for reference in frozen.references
            if reference.source == "canonical_reference_binding"
        ]
        assert [reference.ref_id for reference in frozen_references] == expected_reference_ids
        assert [reference.uri for reference in frozen_references] == expected_reference_uris
        assert len(frozen_references) == 2
        wire_request = reconstruct_runway_router_video_request(
            entry["generation_contract"],
            preflight["manifest"],
            config_id="offline-multishot-test-router",
        )
        assert wire_request["input"]["referenceImages"] == [
            {"uri": reference.uri, "role": "reference"}
            for reference in frozen_references
        ]

    for entry in preflight["entries"]:
        camera = entry["generation_contract"]["payload"]["camera_plan"]
        assert camera == CAMERA_PLAN
        assert entry["camera_provenance"] == "APPROVED"
        assert entry["camera_source_storyboard_shot_id"]
        assert entry["camera_source_digest"]
        assert entry["generation_contract"]["payload"]["scene_coverage"]
        assert entry["generation_contract"]["payload"]["dialogue_handoff"]["payload"]["shot_id"] == entry["shot_id"]
        assert "I kept the winter key." not in entry["prompt"]

    # Owner authority the Router creation/submission gates require, provisioned
    # through production storage APIs from the prepared manifest identity.
    storyboard_version_id = str((preflight["manifest"].get("storyboard") or {}).get("storyboard_version") or "")
    assert storyboard_version_id
    version = storage.get_storyboard_blueprint_version(storyboard_version_id)
    version.status = StoryboardBlueprintStatus.APPROVED
    version.approved_at = version.approved_at or "2026-10-01T00:00:00+00:00"
    version.approved_by = CHECKPOINT_G_OWNER
    version.metadata = {
        **(version.metadata or {}),
        "production_approval": {"actor_id": CHECKPOINT_G_OWNER, "actor_authenticated": True},
    }
    storage.save_storyboard_blueprint_version(version)
    blueprint = storage.get_storyboard_blueprint(PROJECT_ID, SCENE_ID)
    blueprint.status = StoryboardBlueprintStatus.APPROVED
    blueprint.current_version_id = storyboard_version_id
    blueprint.approved_version_id = storyboard_version_id
    storage.save_storyboard_blueprint(blueprint)
    for row in preflight["manifest"].get("shots", []):
        board_shot = storage.get_storyboard_shot(str(row.get("storyboard_shot_id") or ""))
        if board_shot is not None:
            board_shot.status = StoryboardBlueprintStatus.APPROVED
            storage.save_storyboard_shot(board_shot)

    token = access_user_id.set(CHECKPOINT_G_OWNER)
    try:
        result = await pipeline.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=fixture["project"],
            provider="runway_router",
            require_persisted_confirmation=True,
            save_project=fixture["state"].save_project,
            prepared_snapshot_id=preflight["prepared_snapshot_id"],
        )
    finally:
        access_user_id.reset(token)

    assert result["status"] == "complete"
    assert adapter_factory_calls == ["runway_router", "runway_router"]
    assert [call["provider"] for call in adapter_calls] == ["runway_router", "runway_router"]
    assert all(call["status"] == "complete" for call in adapter_calls)
    # The production path reached the mocked adapter transport (dry-run +
    # submit per job, then polls) with zero live contact — sockets are
    # blocked, so any real network attempt would fail loudly here.
    dry_runs = [row for row in transport_calls if row["method"] == "POST" and (row["payload"] or {}).get("dryRun")]
    submits = [row for row in transport_calls if row["method"] == "POST" and not (row["payload"] or {}).get("dryRun")]
    assert len(dry_runs) == 2
    assert len(submits) == 2
    assert [call["shot_id"] for call in adapter_calls] == SHOT_IDS
    assert [call["input"]["prompt"] for call in adapter_calls] == [entry["prompt"] for entry in preflight["entries"]]
    for index, call in enumerate(adapter_calls):
        frozen = preflight["entries"][index]["generation_contract"]["payload"]
        # Router jobs persist the F7 compared keys (not the full camera plan)
        # in their inputs; the frozen contract remains the camera authority
        # (asserted per entry above).
        assert call["input"]["parameters"]["scene_coverage"] == frozen["scene_coverage"]
        assert call["input"]["parameters"]["dialogue_handoff"] == frozen["dialogue_handoff"]
        expected_references = [
            f"https://fixture.invalid/{'char-ivo' if index == 0 else 'char-neri'}.png",
            "https://fixture.invalid/glassworks.png",
        ]
        assert call["input"]["referenceAssets"] == expected_references
        assert [row["ref_id"] for row in call["metadata"]["frozen_reference_binding"]] == [
            "ref-ivo-face" if index == 0 else "ref-neri-face",
            "ref-glassworks-fixture",
        ]
        assert call["metadata"]["creative_generation_contract"]["payload"]["camera_plan"] == CAMERA_PLAN
        assert call["metadata"]["frozen_reference_binding"] == preflight["entries"][index]["reference_binding"]
        assert call["metadata"]["frozen_reference_binding"][0]["uri"] == expected_references[0]
        assert call["metadata"]["creative_generation_manifest"]["manifest_fingerprint"] == preflight["manifest"]["manifest_fingerprint"]
        # The minted declaration traveled with the job to the adapter.
        assert call["metadata"]["reference_projection_authorization"] == \
            preflight["entries"][index]["reference_projection_authorization"]

    assert len(audio.calls) == 2
    first_handoff = preflight["entries"][0]["dialogue_handoff"]["payload"]["lines"]
    second_handoff = preflight["entries"][1]["dialogue_handoff"]["payload"]["lines"]
    assert audio.calls[0]["dialogue_lines"] == first_handoff
    assert audio.calls[1]["dialogue_lines"] == second_handoff
    assert audio.calls[1]["dialogue_handoff"]["payload"]["silence"] is True
    assert len(stitch.calls) == 1
    assert stitch.calls[0]["project"]["execution_summary"]["one_button_render_jobs"]

    jobs = storage.list_jobs(project_id=PROJECT_ID)
    assert len(jobs) == 2
    assert [job.provider for job in jobs] == ["runway_router", "runway_router"]
    assert all(job.status == "complete" for job in jobs)
    assert all(job.metadata["creative_generation_contract"] for job in jobs)
    assert all(job.metadata["reference_projection_authorization"] for job in jobs)
    links = storage.list_storyboard_render_links(project_id=PROJECT_ID)
    assert {row["render_job_id"] for row in links} == {job.id for job in jobs}
    persisted_state = fixture["state"].get_project(PROJECT_ID)
    summary = persisted_state["execution_summary"]
    assert len(summary["one_button_render_jobs"]) == 2
    assert len(summary["scene_pipeline_assemblies"]) == 1
    assert summary["scene_pipeline_assemblies"][0]["status"] == "complete"
    assert result["output_url"] == summary["scene_pipeline_assemblies"][0]["output_url"]


@pytest.mark.asyncio
async def test_unresolved_creator_coverage_blocks_batch_and_creates_no_jobs_or_audio(
    phase6, monkeypatch: pytest.MonkeyPatch,
):
    fixture = phase6
    direction = fixture["direction"]
    before = direction.get(PROJECT_ID, SCENE_ID)
    unresolved = next(row.obligation_id for row in before.coverage_obligations if row.obligation_type == "content")
    saved, approved = _prepare_approved_successor(fixture, unresolved_content_id=unresolved)
    assert saved.coverage_blocked is True
    assert saved.version_id == approved["version"].version_id
    assert any("canonical scene content unresolved" in blocker for blocker in saved.coverage_blockers)

    render_svc = render_module.RenderService()
    monkeypatch.setattr(render_module, "_storage", fixture["storage"])
    monkeypatch.setattr(render_module, "get_adapter", lambda *_args: pytest.fail("provider adapter must not be created"))
    audio = FakeAudioService()
    stitch = FakeStitchingService()
    pipeline = SceneProductionPipelineService(
        render_svc=render_svc,
        audio_svc=audio,
        stitching_svc=stitch,
        backend_root=fixture["backend_root"],
    )

    preflight = pipeline.prepare_scene_batch(
        project_id=PROJECT_ID,
        scene_id=SCENE_ID,
        project=fixture["project"],
        provider="simulated",
    )
    assert preflight["ready"] is False
    assert any("canonical scene content unresolved" in blocker for blocker in preflight["blockers"])
    assert pipeline._prepared_scene_batches == {}

    with pytest.raises(ValidationError) as raised:
        await pipeline.generate_scene(
            project_id=PROJECT_ID,
            scene_id=SCENE_ID,
            project=fixture["project"],
            provider="simulated",
            save_project=fixture["state"].save_project,
        )
    assert raised.value.stage == "generation_readiness"
    assert fixture["storage"].list_jobs(project_id=PROJECT_ID) == []
    assert audio.calls == []
    assert stitch.calls == []

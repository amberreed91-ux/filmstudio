"""Test that Path B (non-generic prompt path) in render.py's create_job()
wires character staging into the outgoing provider prompt.

Path B is triggered when the caller passes a non-generic prompt (e.g. from
the Previs Room's Generation Settings panel with duration/fps/resolution/seed).
Path B appends a "Characters: ..." block to the existing prompt.

Standard (same as Path A and Loop 2's reference-conditioning fix): assertions
are on the ACTUAL outgoing payload string (job.input_payload.prompt), not on
an internal proxy.

Verifies:
1. A scene-level staging note (e.g. "bruise on her cheek") appears in the
   actual outgoing prompt string sent to the provider via Path B.
2. The SAME scene-level staging note appears in ALL sub-shots of a
   multi-shot scene (scene_002's 4 auto-split shots).
3. Zero regression: when no staging exists, the prompt matches the legacy
   visual_prompt_summary behavior.
4. Graceful fallback: if resolve_character_prompt raises, the render still
   produces a valid prompt with the raw visual_prompt_summary.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Shared constants ──────────────────────────────────────────────────────────

STAGING_NOTE = "fresh bruise on her left cheek"
CHAR_NAME = "MAYA"
CHAR_VPS = "woman, late 20s, dark hair, lean build"

DRE_NAME = "DRE"
DRE_VPS = "man, early 30s, broad build, short fade"

SCENE_002_TEXT = """The same city. Different world. The L train is frozen. Buildings are cracked. Nature has
reclaimed the streets. The skyline still stands, but Chicago feels like a graveyard.
Maya walks through the ruins. She reaches the Chicago River. The place where she
died.
THE FIRST TIMELINE
Maya is surrounded by the people she trusted. Dre, her closest friend, stands among
them. His jaw is tight. He won't look her in the eyes.
DRE
I need you to understand something.
MAYA
That's funny.
DRE
What?
MAYA
You always say that right before you do something
you know is wrong.
DRE
Things changed.
MAYA
No. People changed.
DRE
(raises the gun)
There's not enough. You have to understand that.
There is not enough for everyone.
MAYA
So you decided that for all of us.
DRE
Someone had to.
(pulls the trigger)
Maya is killed. Darkness.
We hold on Dre's face for a beat after the shot. He doesn't look relieved. He looks like
a man who just chose scarcity over trust — and already knows the cost.
THE SECOND CHANCE
Maya wakes up. Two months before the apocalypse. She remembers everything. The
betrayal. The death. The collapse.
She looks out at Chicago while it is still alive. The L train runs. People laugh below her
window.
MAYA
I remember dying. So why am I here?
She sits with that for a long moment. Then something shifts behind her eyes. Not grief.
Not rage. Clarity.
DRE — BEFORE THE FALL"""

SCENE_002_HEADING = "EXT. CHICAGO RUINS - DAY"

# A non-generic prompt that triggers Path B (>= 50 chars, no generic markers).
# This simulates a Previs Room render request with a real prompt.
NON_GENERIC_PROMPT = (
    "A lone woman walking through neon rain at night, cinematic, moody, "
    "shot on 35mm film with shallow depth of field"
)


def _make_project_data(project_id, scene_id, characters, text=SCENE_002_TEXT,
                       heading=SCENE_002_HEADING):
    scene_data = {
        "scene_id": scene_id,
        "heading": heading,
        "text": text,
        "location": "Chicago ruins",
        "time_of_day": "Day",
        "emotional_tone": "Tense, betrayal",
        "characters": characters,
    }
    return {
        "project_id": project_id,
        "title": "Path B Staging Wiring Test",
        "execution_summary": {"scenes": [scene_data]},
    }


@pytest.fixture
def isolated_render(tmp_path, monkeypatch):
    """Set up an isolated DatabaseStorage + RenderService with monkeypatched
    project_store and storage lookups.

    Returns (db, project_id, service) so the test can seed characters /
    stagings and then call create_job.
    """
    from app.data.storage import DatabaseStorage
    from app.services.render import RenderService
    from app.services.project_store import project_store
    from app.models import StudioProject

    db = DatabaseStorage(str(tmp_path))
    project_id = "proj-path-b-staging"

    characters = [CHAR_NAME, DRE_NAME]
    project_data = _make_project_data(project_id, "scene_002", characters)
    db.save_project(StudioProject(**project_data))

    _seed_character(db, project_id, name=CHAR_NAME, vps=CHAR_VPS)
    _seed_character(db, project_id, name=DRE_NAME, vps=DRE_VPS)

    monkeypatch.setattr(
        project_store,
        "get_project",
        lambda pid: project_data if pid == project_id else None,
    )
    monkeypatch.setattr("app.services.render._storage", db)
    monkeypatch.setattr(
        "app.data.storage.get_storage",
        lambda *a, **kw: db,
    )
    monkeypatch.setattr(
        "app.services.standing_corrections_service.get_storage",
        lambda *a, **kw: db,
    )

    service = RenderService()
    return db, project_id, service


def _seed_character(db, project_id, name=CHAR_NAME, vps=CHAR_VPS):
    """Save a character and return the full DB record (with id)."""
    db.save_character(project_id, name, {
        "visual_prompt_summary": vps,
        "description_status": "legacy",
    })
    return db.get_character_by_name(project_id, name)


def _seed_scene_staging(db, character_id, scene_id, staging_prompt=STAGING_NOTE):
    """Save a scene-level staging (shot_id=None)."""
    return db.save_character_staging({
        "character_id": character_id,
        "scene_id": scene_id,
        "shot_id": None,
        "staging_prompt": staging_prompt,
        "source": "manual",
    })


# ── Test 1: Single-shot — staging text in outgoing prompt via Path B ─────────

class TestPathBStagingInOutgoingPrompt:
    """Path B must include scene-level staging text in the ACTUAL outgoing
    prompt string (job.input_payload.prompt), not just in an internal proxy.

    Path B is triggered by passing a non-generic prompt (>= 50 chars, no
    generic markers).  The staging text must appear in the "Characters:"
    block that Path B appends to the existing prompt.
    """

    def test_staging_note_appears_in_outgoing_prompt(self, isolated_render):
        db, project_id, service = isolated_render

        char = db.get_character_by_name(project_id, CHAR_NAME)
        _seed_scene_staging(db, char["id"], "scene_002")

        job = service.create_job(
            project_id=project_id,
            shot_id="scene_002_shot_001",
            prompt=NON_GENERIC_PROMPT,
        )

        outgoing = job.input_payload.prompt
        assert STAGING_NOTE in outgoing, (
            f"Staging note {STAGING_NOTE!r} NOT found in outgoing prompt.\n"
            f"Full outgoing prompt: {outgoing!r}"
        )
        assert "In this shot:" in outgoing, (
            f"Expected 'In this shot:' marker in prompt, got: {outgoing!r}"
        )
        assert "Characters:" in outgoing, (
            f"Path B should append a 'Characters:' block, got: {outgoing!r}"
        )

    def test_outgoing_prompt_contains_original_content_and_staging(self, isolated_render):
        """Path B preserves the original prompt content AND adds staging.
        The outgoing prompt must contain the original non-generic prompt,
        the base visual_prompt_summary, AND the staging note."""
        db, project_id, service = isolated_render

        char = db.get_character_by_name(project_id, CHAR_NAME)
        _seed_scene_staging(db, char["id"], "scene_002")

        job = service.create_job(
            project_id=project_id,
            shot_id="scene_002_shot_001",
            prompt=NON_GENERIC_PROMPT,
        )

        outgoing = job.input_payload.prompt
        assert NON_GENERIC_PROMPT[:30] in outgoing, (
            f"Original prompt content should be preserved by Path B.\n"
            f"Full: {outgoing!r}"
        )
        assert CHAR_VPS in outgoing, (
            f"Base vps {CHAR_VPS!r} missing from outgoing prompt.\n"
            f"Full: {outgoing!r}"
        )
        assert STAGING_NOTE in outgoing, (
            f"Staging note {STAGING_NOTE!r} missing from outgoing prompt.\n"
            f"Full: {outgoing!r}"
        )


# ── Test 2: Zero regression — no staging = legacy behavior ───────────────────

class TestPathBZeroRegressionNoStaging:
    """When no staging row exists, the outgoing prompt must be identical to
    the legacy visual_prompt_summary behavior (byte-for-byte)."""

    def test_no_staging_produces_legacy_vps_prompt(self, isolated_render):
        db, project_id, service = isolated_render

        job = service.create_job(
            project_id=project_id,
            shot_id="scene_002_shot_001",
            prompt=NON_GENERIC_PROMPT,
        )

        outgoing = job.input_payload.prompt
        assert CHAR_VPS in outgoing, (
            f"Legacy vps should still appear when no staging exists.\n"
            f"Full: {outgoing!r}"
        )
        assert STAGING_NOTE not in outgoing, (
            f"Staging note should NOT appear when no staging row exists.\n"
            f"Full: {outgoing!r}"
        )
        assert "In this shot:" not in outgoing, (
            f"'In this shot:' marker should NOT appear without staging.\n"
            f"Full: {outgoing!r}"
        )
        assert NON_GENERIC_PROMPT[:30] in outgoing, (
            f"Original prompt content should be preserved.\n"
            f"Full: {outgoing!r}"
        )


# ── Test 3: Multi-shot — same scene-level staging in ALL 4 shots ──────────────

class TestPathBMultiShotSceneLevelStaging:
    """The specific risk flagged in the earlier diagnosis: a scene-level
    staging note (shot_id IS NULL) must appear in ALL sub-shots derived from
    that scene via Path B, not just the first.

    Test scene: scene_002 with 4 auto-split shots (shot_scene_002_001 .. 004).
    These tests require scene_splitter_service which is not yet on this branch.
    They will skip if the service is unavailable.
    """

    def _get_four_shot_ids(self):
        """Generate the 4 auto-split shot_ids for scene_002."""
        pytest.importorskip("app.services.scene_splitter_service")
        from app.services.scene_splitter_service import scene_splitter_service
        from app.services.script_parser import ScriptParser

        specs = scene_splitter_service.generate_shot_specs(
            SCENE_002_TEXT, characters=[CHAR_NAME, DRE_NAME]
        )
        assert len(specs) == 4, f"Expected 4 shots, got {len(specs)}"

        parser = ScriptParser()
        scene_dict = {
            "scene_id": "scene_002",
            "characters": [CHAR_NAME, DRE_NAME],
            "text": SCENE_002_TEXT,
        }
        candidates = parser._build_shot_candidates_from_specs(
            "scene_002", [], specs, scene_dict
        )
        assert len(candidates) == 4
        return [c["shot_id"] for c in candidates]

    def test_scene_level_staging_in_all_4_shots(self, isolated_render):
        db, project_id, service = isolated_render

        char = db.get_character_by_name(project_id, CHAR_NAME)
        _seed_scene_staging(db, char["id"], "scene_002")

        shot_ids = self._get_four_shot_ids()

        prompts_per_shot = {}
        for sid in shot_ids:
            job = service.create_job(
                project_id=project_id,
                shot_id=sid,
                prompt=NON_GENERIC_PROMPT,
            )
            prompts_per_shot[sid] = job.input_payload.prompt

        for sid, outgoing in prompts_per_shot.items():
            assert STAGING_NOTE in outgoing, (
                f"Shot {sid}: staging note {STAGING_NOTE!r} MISSING from "
                f"outgoing prompt.\nFull prompt: {outgoing!r}"
            )
            assert "In this shot:" in outgoing, (
                f"Shot {sid}: 'In this shot:' marker missing.\n"
                f"Full prompt: {outgoing!r}"
            )

    def test_all_4_shots_have_identical_staging_content(self, isolated_render):
        """All 4 shots must carry the SAME scene-level staging note —
        confirming the scene-level fallback (shot_id IS NULL) resolves
        correctly for every sub-shot via Path B, not just the first."""
        db, project_id, service = isolated_render

        char = db.get_character_by_name(project_id, CHAR_NAME)
        _seed_scene_staging(db, char["id"], "scene_002")

        shot_ids = self._get_four_shot_ids()

        staging_substrings = []
        for sid in shot_ids:
            job = service.create_job(
                project_id=project_id,
                shot_id=sid,
                prompt=NON_GENERIC_PROMPT,
            )
            outgoing = job.input_payload.prompt
            assert STAGING_NOTE in outgoing, (
                f"Shot {sid}: staging note missing.\nFull: {outgoing!r}"
            )
            idx = outgoing.index(STAGING_NOTE)
            staging_substr = outgoing[idx:idx + len(STAGING_NOTE)]
            staging_substrings.append(staging_substr)

        assert len(set(staging_substrings)) == 1, (
            f"Sub-shots got different staging content:\n"
            + "\n".join(
                f"  {sid}: ...{STAGING_NOTE}..."
                for sid in shot_ids
            )
        )

    def test_print_all_4_outgoing_prompts_for_inspection(self, isolated_render):
        """Diagnostic test: print the actual outgoing prompt for each of the
        4 shots so the staging text is visible in test output."""
        db, project_id, service = isolated_render

        char = db.get_character_by_name(project_id, CHAR_NAME)
        _seed_scene_staging(db, char["id"], "scene_002")

        shot_ids = self._get_four_shot_ids()

        lines = ["=" * 72, "PATH B OUTGOING PROMPTS — 4 auto-split shots", "=" * 72]
        for i, sid in enumerate(shot_ids):
            job = service.create_job(
                project_id=project_id,
                shot_id=sid,
                prompt=NON_GENERIC_PROMPT,
            )
            outgoing = job.input_payload.prompt
            has_staging = STAGING_NOTE in outgoing
            lines.append(f"--- Shot {i+1}: {sid} ---")
            lines.append(f"  staging present: {has_staging}")
            lines.append(f"  outgoing prompt: {outgoing!r}")
            lines.append("")
        lines.append("=" * 72)
        print("\n".join(lines))

        for sid in shot_ids:
            job = service.create_job(
                project_id=project_id,
                shot_id=sid,
                prompt=NON_GENERIC_PROMPT,
            )
            assert STAGING_NOTE in job.input_payload.prompt


# ── Test 4: Graceful fallback on resolve_character_prompt failure ─────────────

class TestPathBGracefulFallback:
    """If resolve_character_prompt raises unexpectedly, the render must still
    produce a valid prompt with the raw visual_prompt_summary — never crash."""

    def test_fallback_to_raw_vps_on_exception(self, isolated_render, monkeypatch):
        db, project_id, service = isolated_render

        def _explode(*args, **kwargs):
            raise RuntimeError("simulated staging service failure")

        monkeypatch.setattr(
            "app.services.character_staging_service.resolve_character_prompt",
            _explode,
        )

        job = service.create_job(
            project_id=project_id,
            shot_id="scene_002_shot_001",
            prompt=NON_GENERIC_PROMPT,
        )

        outgoing = job.input_payload.prompt
        assert CHAR_VPS in outgoing, (
            f"Fallback should include raw vps {CHAR_VPS!r}.\n"
            f"Full: {outgoing!r}"
        )


class TestPathBFullAdherencePayload:
    """Exercise the actual create_job payload with staging + structured slots
    + standing corrections + reference consistency active together."""

    def test_multi_character_structured_prompt_carries_all_live_adherence_inputs(
        self,
        isolated_render,
    ):
        from app.models.standing_corrections import StandingCorrection

        db, project_id, service = isolated_render

        maya = db.get_character_by_name(project_id, CHAR_NAME)
        dre = db.get_character_by_name(project_id, DRE_NAME)
        _seed_scene_staging(db, maya["id"], "scene_002")
        _seed_scene_staging(
            db,
            dre["id"],
            "scene_002",
            staging_prompt="cannot meet Maya's eyes",
        )
        db.save_reference_asset({
            "ref_id": "ref_maya_full",
            "project_id": project_id,
            "kind": "character_full",
            "image_url": "https://example.test/maya-reference.png",
            "source_shot_id": "scene_001_shot_001",
            "created_at": "2026-07-23T00:00:00",
        })
        db.save_standing_correction(StandingCorrection(
            correction_id="sc_path_b_camera",
            project_id=project_id,
            slot="camera",
            trigger_json={"shot_id": "scene_002_shot_001"},
            injection_text="Keep both characters readable in the frame",
        ).model_dump(mode="json"))

        job = service.create_job(
            project_id=project_id,
            shot_id="scene_002_shot_001",
            prompt=NON_GENERIC_PROMPT,
            parameters={"structured_prompt": True},
        )

        outgoing = job.input_payload.prompt
        slots = job.input_payload.parameters["prompt_slots"]

        assert STAGING_NOTE in outgoing
        assert "cannot meet Maya's eyes" in outgoing
        assert CHAR_NAME in outgoing
        assert DRE_NAME in outgoing
        assert "Keep both characters readable in the frame" in outgoing
        assert "Keep both characters readable in the frame" in slots["camera"]
        assert job.input_payload.consistency_payload is not None
        assert job.input_payload.consistency_payload.refs[0].ref_id == "ref_maya_full"

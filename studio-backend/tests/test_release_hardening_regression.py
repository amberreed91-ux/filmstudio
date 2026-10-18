"""Release-hardening regression tests: one per known failure class.

Each test pins a production failure mode observed on project_5907c60cddbc so it
can never silently return. All tests run on temp databases with no provider
calls (Runway is stubbed at the service boundary) and no live-DB access.

Failure classes (docs/audits/AUDIT_2026-10-17.md):
  1. Stale backend / DashScope path: no storyboard-image code path may import
     or call dashscope/qwen.
  2. Legacy provider aliases must all resolve to Runway.
  3. Runway promptText comes only from an approved image prompt; over-limit
     prompts fail closed BEFORE any provider call.
  4. Board approval blocks on missing / stale / unapproved / over-limit
     image prompts.
  5. Locked-appearance block must cover the shot's visible cast (SKIPPED:
     the selection fix has not landed — see marker below).

Do NOT weaken these tests to make CI pass. If one fails, the failure class
has returned; fix the product code, not the test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.data.storage import DatabaseStorage
from app.models import StudioProject
from app.services.runway_image_prompt_compactor import canonical_sha256
from app.services.runway_prompt_length import (
    RUNWAY_IMAGE_MAX_PROMPT_UTF16,
    utf16_length,
)
from app.services.stability import StateError, ValidationError
from app.services.storyboard_blueprint_service import StoryboardBlueprintService
from app.services.storyboard_image_service import (
    StoryboardImageResult,
    storyboard_image_service,
)

ROOT = Path(__file__).resolve().parents[1]

# Modules that form the storyboard-image render path. TTS/vision/LLM modules
# intentionally retain DashScope and are OUT of scope for class 1.
_STORYBOARD_PATH_MODULES = [
    ROOT / "app" / "services" / "storyboard_image_service.py",
    ROOT / "app" / "services" / "storyboard_blueprint_service.py",
    ROOT / "app" / "services" / "providers" / "runway_image_provider.py",
    ROOT / "app" / "services" / "storyboard_image_prompt_service.py",
    ROOT / "app" / "services" / "runway_image_prompt_compactor.py",
    ROOT / "app" / "services" / "runway_prompt_length.py",
]


# ----------------------------------------------------------------------
# Class 1: no storyboard-image code path imports or calls dashscope/qwen
# ----------------------------------------------------------------------

def _dashscope_bindings(tree: ast.AST) -> list[str]:
    """Import statements and live attribute roots naming dashscope/qwen.

    Comments, docstrings, string literals (legacy-value normalization sets,
    log messages) and method names like ``generate_qwen_image`` (a Runway
    routing shim) are NOT bindings — only real imports and attribute access
    on a dashscope-rooted object count.
    """
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "dashscope" in alias.name.lower() or alias.name.lower().startswith("qwen"):
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").lower()
            if "dashscope" in module or module.startswith("qwen"):
                hits.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Attribute):
            value = node
            while isinstance(value, ast.Attribute):
                value = value.value
            if isinstance(value, ast.Name) and value.id.lower() in {"dashscope"}:
                hits.append(f"dashscope.{node.attr}")
    return hits


@pytest.mark.parametrize(
    "module_path", _STORYBOARD_PATH_MODULES, ids=[p.name for p in _STORYBOARD_PATH_MODULES]
)
def test_storyboard_path_has_no_dashscope_binding(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    assert _dashscope_bindings(tree) == [], (
        f"{module_path.name} binds a dashscope/qwen module — "
        "the storyboard image path must stay Runway-only"
    )


def test_legacy_qwen_entry_routes_to_runway_without_provider_call(monkeypatch) -> None:
    """generate_qwen_image is a shim: it must delegate to the Runway engine."""
    calls: list[dict] = []

    def _stub(*, project_id, scene_id, prompt, output_root, **kwargs):
        calls.append({"project_id": project_id, "scene_id": scene_id, "prompt": prompt})
        return StoryboardImageResult(
            image_url="https://example.invalid/runway.png",
            stored_image_path=None,
            provider="runway",
            model="gen4_image",
            prompt_used=prompt,
        )

    monkeypatch.setattr(storyboard_image_service, "generate_runway_image", _stub)
    result = storyboard_image_service.generate_qwen_image(
        project_id="proj-hardening",
        scene_id="scene_001",
        prompt="A held look, golden hour.",
        output_root=Path("/tmp"),
    )
    assert result.provider == "runway"
    assert result.model == "gen4_image"
    assert len(calls) == 1
    assert calls[0]["prompt"] == "A held look, golden hour."


# ----------------------------------------------------------------------
# Helpers: temp-DB board
# ----------------------------------------------------------------------

def _board(tmp_path: Path, *, scene_text: str = "Maya waits by the doorway. " * 6):
    storage = DatabaseStorage(str(tmp_path / "storage"))
    storage.save_project(
        StudioProject(
            project_id="project-hardening",
            title="Hardening Test",
            execution_summary={"scenes": [{"scene_id": "scene_001", "description": scene_text}]},
        )
    )
    service = StoryboardBlueprintService(storage)
    detail = service.get_or_create_blueprint(
        project_id="project-hardening", scene_id="scene_001", shot_count=1
    )
    return storage, service, detail


def _approve_short_prompt(service: StoryboardBlueprintService, shot, text: str = "Maya waits by the doorway, golden hour, wide lock-off.") -> str:
    prompt_service = service._image_prompt_service()
    prompt_service.edit_for_shot(shot, image_prompt=text, edited_by="creator")
    prompt_service.approve_for_shot(shot, approved_by="creator")
    return text


# ----------------------------------------------------------------------
# Class 2: every legacy alias resolves to runway
# ----------------------------------------------------------------------

_LEGACY_ALIASES = ["runway", "qwen-image-max", "dashscope", "qwen", "wanx"]


@pytest.mark.parametrize("alias", _LEGACY_ALIASES + ["QWEN-IMAGE-MAX", " DashScope "])
def test_legacy_provider_alias_resolves_to_runway(tmp_path: Path, alias: str) -> None:
    """Aliases must pass provider validation into the Runway branch.

    With no approved image prompt the call must fail closed with StateError
    (missing render-ready prompt) — never ValidationError (provider
    rejected) and never a DashScope-shaped error. No provider is called:
    the failure happens before any provider call.
    """
    _, service, _ = _board(tmp_path)
    with pytest.raises(StateError) as exc_info:
        service.generate_storyboard_image_for_scene_shot(
            project_id="project-hardening",
            scene_id="scene_001",
            provider=alias,
            shot_number=1,
        )
    assert "dashscope" not in str(exc_info.value).lower()
    assert "qwen" not in str(exc_info.value).lower()


def test_unknown_provider_still_rejected(tmp_path: Path) -> None:
    _, service, _ = _board(tmp_path)
    with pytest.raises(ValidationError, match="provider must be one of"):
        service.generate_storyboard_image_for_scene_shot(
            project_id="project-hardening",
            scene_id="scene_001",
            provider="__bogus__",
            shot_number=1,
        )


# ----------------------------------------------------------------------
# Class 3: promptText comes only from the approved image prompt
# ----------------------------------------------------------------------

def test_runway_prompt_text_is_the_approved_image_prompt(tmp_path: Path, monkeypatch) -> None:
    """The canonical text is NEVER sent to Runway; the approved prompt is."""
    _, service, detail = _board(tmp_path)
    shot = detail["shots"][0]
    canonical = str(shot.render_contract.provider_neutral_prompt or "")
    assert canonical, "fixture must have a canonical prompt to contrast against"
    approved_text = _approve_short_prompt(service, shot)
    assert approved_text != canonical

    captured: dict = {}

    def _stub(*, project_id, scene_id, prompt, output_root, **kwargs):
        captured["prompt"] = prompt
        return StoryboardImageResult(
            image_url="https://example.invalid/runway.png",
            stored_image_path=None,
            provider="runway",
            model="gen4_image",
            prompt_used=prompt,
        )

    monkeypatch.setattr(storyboard_image_service, "generate_runway_image", _stub)
    result = service.generate_storyboard_image_for_scene_shot(
        project_id="project-hardening",
        scene_id="scene_001",
        provider="runway",
        shot_number=1,
    )
    assert result["provider"] == "runway"
    assert captured["prompt"] == approved_text
    assert utf16_length(captured["prompt"]) <= RUNWAY_IMAGE_MAX_PROMPT_UTF16


def test_over_limit_prompt_fails_closed_before_provider_call(tmp_path: Path, monkeypatch) -> None:
    """An over-limit write is rejected AND an over-limit stored record can
    never reach the provider: the render path fails closed first."""
    storage, service, detail = _board(tmp_path)
    shot = detail["shots"][0]
    prompt_service = service._image_prompt_service()

    # Write path fails closed.
    with pytest.raises(ValidationError, match="UTF-16"):
        prompt_service.edit_for_shot(shot, image_prompt="x" * 1001, edited_by="creator")

    # Even a directly-stored over-limit record fails closed at render time.
    record = prompt_service.derive_for_shot(shot)
    long_text = "y" * 1001
    record = {
        **record,
        "image_prompt": long_text,
        "image_prompt_sha256": canonical_sha256(long_text),
        "utf16_length": utf16_length(long_text),
        "status": "approved",
    }
    storage.save_storyboard_image_prompt(record)

    called: list = []

    def _stub(**kwargs):
        called.append(kwargs)
        raise AssertionError("provider must not be called for an over-limit prompt")

    monkeypatch.setattr(storyboard_image_service, "generate_runway_image", _stub)
    with pytest.raises(StateError):
        service.generate_storyboard_image_for_scene_shot(
            project_id="project-hardening",
            scene_id="scene_001",
            provider="runway",
            shot_number=1,
        )
    assert called == []


# ----------------------------------------------------------------------
# Class 4: board approval blocks on missing/stale/unapproved/over-limit
# ----------------------------------------------------------------------

def test_board_approval_blocks_for_each_image_prompt_state(tmp_path: Path) -> None:
    """approve_version must refuse while ANY shot is missing, stale,
    unapproved, or over-limit — without touching provider code."""
    storage, service, detail = _board(tmp_path)
    shot = detail["shots"][0]
    prompt_service = service._image_prompt_service()

    def _gate_state() -> str:
        gate = prompt_service.gate_for_version([shot])
        assert gate["approved"] is False
        return gate["not_ready"][0]["state"]

    # missing: a shot with no stored row at all
    ghost = shot.model_copy(deep=True)
    ghost.storyboard_shot_id = "sbs_missing_no_row"
    ghost_gate = prompt_service.gate_for_version([ghost])
    assert ghost_gate["approved"] is False
    assert ghost_gate["not_ready"][0]["state"] == "missing"

    # unapproved: derived proposal only (board creation auto-derives
    # proposals best-effort, so ensure one exists then check the state)
    prompt_service.derive_for_shot(shot)
    assert _gate_state() == "unapproved"

    # stale: canonical text changed after derivation
    stale_shot = shot.model_copy(deep=True)
    stale_shot.render_contract.provider_neutral_prompt = (
        str(shot.render_contract.provider_neutral_prompt) + " An added beat."
    )
    gate = prompt_service.gate_for_version([stale_shot])
    assert gate["approved"] is False
    assert gate["not_ready"][0]["state"] == "stale"

    # over-limit: stored record exceeds the Runway cap
    record = storage.get_storyboard_image_prompt(shot.storyboard_shot_id)
    assert record is not None
    long_text = "z" * 1001
    storage.save_storyboard_image_prompt(
        {
            **record,
            "image_prompt": long_text,
            "image_prompt_sha256": canonical_sha256(long_text),
            "utf16_length": utf16_length(long_text),
            "status": "approved",
        }
    )
    assert _gate_state() == "over_limit"

    # ready control: a short approved prompt clears the gate
    storage.save_storyboard_image_prompt(
        {
            **record,
            "image_prompt": "Maya waits by the doorway, golden hour.",
            "image_prompt_sha256": canonical_sha256("Maya waits by the doorway, golden hour."),
            "utf16_length": utf16_length("Maya waits by the doorway, golden hour."),
            "status": "approved",
        }
    )
    gate = prompt_service.gate_for_version([shot])
    assert gate["approved"] is True


# ----------------------------------------------------------------------
# Class 5: locked-appearance block covers the shot's visible cast
# ----------------------------------------------------------------------

def _locked_char(name: str) -> dict:
    return {
        "name": name,
        "continuity_state_json": {
            "appearance_approval": {"status": "locked", "version": "v1"}
        },
        "age": "late 20s",
        "look": f"distinct look for {name}",
    }


def test_locked_block_covers_visible_cast_not_alphabetical_first_three() -> None:
    """The locked-appearance selection fix (shot-scoped, no alphabetical
    truncation) must hold: a shot whose visible cast is only Maya must
    carry Maya in the Locked-appearance tail and must not leak uninvolved
    characters. Regression for docs/audits/SCENE001_BLOCKERS_2026-10-17.md
    section 2 (DRE/ELENA/JAY selected, Maya amputated)."""
    from app.services.shot_prompt_builder import build_locked_appearance_block

    characters = [_locked_char(name) for name in ["DRE", "ELENA", "JAY", "MAYA"]]
    block = build_locked_appearance_block(
        characters,
        {"characters": ["MAYA"]},
    )
    assert "MAYA" in block
    assert "DRE" not in block
    assert "ELENA" not in block
    assert "JAY" not in block


def test_locked_block_empty_when_nothing_in_scope() -> None:
    """An empty block is preferable to the wrong characters: with no
    shot/scene scope and no names in the shot text, other scenes' locked
    faces must never leak in."""
    from app.services.shot_prompt_builder import build_locked_appearance_block

    characters = [_locked_char(name) for name in ["DRE", "ELENA", "JAY", "MAYA"]]
    block = build_locked_appearance_block(characters, {"characters": []})
    assert block == ""

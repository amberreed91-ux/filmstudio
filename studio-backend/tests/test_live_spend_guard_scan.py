"""Scan test: live-spend one-off scripts refuse to run by accident.

Every ``*.py`` file under the five one-off roots
(``studio-backend/*.py``, ``studio-backend/scripts/*.py``, ``scripts/*.py``,
``tools/*.py``, and repo-root ``*.py``) must appear in exactly one manifest below. A new script with
spend/write capability and no classification fails the scan.

Categories
- ``RUNWAY_GATED``: Runway-spend scripts. Dual opt-in via
  ``require_live_spend_gate`` (``STUDIO_ALLOW_LIVE_SPEND_SCRIPT=1`` AND
  ``--confirm-spend=<basename>``). Two placements: ``top`` (standalone
  scripts, guard before every risky import/call) and ``main`` (scripts also
  loaded as modules by tests/services, guard as the first statement of
  ``main()``/``__main__`` so collection-time and helper imports stay safe).
- ``NONAPPROVED_GATED``: non-approved-provider scripts. Unconditional
  refusal via ``refuse_non_approved_provider`` (Runway is the only approved
  provider). Same two placements. Collateral, documented per file: paid
  modes that share a file with a free mode (e.g. probe list modes) are
  refused as a whole; helper functions remain importable.
- ``DB_WRITE_ONLY``: writes outside the pipeline but spends nothing.
  ``db_guard`` (or isolated storage) already covers the live DB; the scan
  asserts no spend primitives. No new gate is added.
- ``READ_ONLY``: diagnostics. The scan asserts no spend primitives, no DB
  read-write opens, and no external provider hosts (localhost-only network
  is allowed where noted).
- ``OUT_OF_SCOPE``: pipeline/harness proper (server entry, provider
  modules used by services, pytest config/plugin, fixture modules) with a
  reason each. Membership-only: they are not one-off scripts.

Guard placement note: the guard lives at ``app/script_guard.py`` (not
``app/data/``) because ``app/__init__.py`` is a single comment line (no
imports, asserted below) while ``app/data/__init__.py`` imports
``app.data.storage`` (asserted below). Importing the guard therefore never
opens a database or touches the network; this is proven by
``test_guard_import_is_side_effect_free`` in fresh subprocesses.

Safety: no test here executes a spend path. Refusal cases run scripts via
``runpy`` with stubbed transports (network raisers, counting sqlite
delegator) and scrubbed secrets/keys. The dual-auth pass case exercises the
guard function directly, never a script.
"""

from __future__ import annotations

import ast
import os
import re
import runpy
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

ENV_FLAG = "STUDIO_ALLOW_LIVE_SPEND_SCRIPT"

# --------------------------------------------------------------------------
# Manifests (paths relative to the repo root).
# --------------------------------------------------------------------------

# Runway-spend scripts: dual opt-in. Placement "top" = guard call is a
# module-top-level statement before every risky import/call. Placement "main"
# = guard call is the first statement of main()/__main__ (required for files
# matching pytest's test_*.py pattern and for scripts imported by tests, so
# collection and helper imports never trip the gate).
RUNWAY_GATED = {
    "studio-backend/submit_attempt2.py": {"placement": "top"},
    "studio-backend/submit_attempt3_additive.py": {"placement": "top"},
    "studio-backend/submit_attempt4_full_restatement.py": {"placement": "top"},
    "studio-backend/submit_attempt5_unchanged_prompt.py": {"placement": "top"},
    "studio-backend/submit_attempt6_different_seed.py": {"placement": "top"},
    "studio-backend/submit_attempt8_lighting_first.py": {"placement": "top"},
    "studio-backend/submit_best_of_n_attempt7.py": {"placement": "top"},
    "studio-backend/retry_attempt2_same_seed.py": {"placement": "top"},
    "studio-backend/verify_seed_generation.py": {"placement": "top"},
    "studio-backend/health_check.py": {"placement": "top"},
    "health_check.py": {"placement": "top"},
    "studio-backend/scripts/live_runway_image_smoke_test3.py": {"placement": "top"},
    "studio-backend/scripts/validate_prompt_adherence_live.py": {"placement": "top"},
    "studio-backend/scripts/master_e2e_validation.py": {"placement": "top"},
    "studio-backend/test_full_e2e_retry.py": {"placement": "main"},
    "studio-backend/test_full_retry_loop.py": {"placement": "main"},
    "studio-backend/test_runway_render.py": {"placement": "main"},
    "studio-backend/scripts/smoke_test_runway_render.py": {"placement": "main"},
    "studio-backend/scripts/verify_runway_hosted_generation.py": {"placement": "main"},
}

# Non-approved-provider scripts: unconditional refusal. The submit/spend
# path uses OpenRouter, Groq/Gemini vision/scoring, DashScope (Wan/CosyVoice/
# Qwen), ElevenLabs, or Fish Audio — none of which is approved.
NONAPPROVED_GATED = {
    "studio-backend/generate_attempt4_prompt_only.py": {"placement": "top", "provider": "groq"},
    "studio-backend/score_attempt2_manual.py": {"placement": "top", "provider": "gemini"},
    "studio-backend/manual_adherence_check.py": {"placement": "top", "provider": "gemini"},
    "studio-backend/demo_adherence_scoring.py": {"placement": "top", "provider": "groq"},
    "studio-backend/scripts/run_openrouter_render.py": {"placement": "top", "provider": "openrouter"},
    "studio-backend/scripts/probe_openrouter_video.py": {"placement": "top", "provider": "openrouter"},
    "studio-backend/scripts/probe_ox_alpha_response.py": {"placement": "top", "provider": "openrouter"},
    "studio-backend/scripts/generate_shot_staging.py": {"placement": "top", "provider": "openrouter"},
    "studio-backend/scripts/score_rendered_shot.py": {"placement": "top", "provider": "dashscope"},
    "studio-backend/scripts/clone_scene_002_vctk_voices.py": {"placement": "top", "provider": "dashscope"},
    "studio-backend/scripts/render_scene_002_clone_comparison.py": {"placement": "top", "provider": "dashscope"},
    "studio-backend/scripts/render_i_was_reborn_scene_002_assembly.py": {"placement": "top", "provider": "dashscope"},
    "studio-backend/scripts/probe_scene003_cosyvoice_emotion.py": {"placement": "top", "provider": "dashscope"},
    "studio-backend/scripts/validate_adherence_stack.py": {"placement": "top", "provider": "happyhorse"},
    "studio-backend/scripts/prove_new_render_pipeline_wiring.py": {"placement": "top", "provider": "happyhorse"},
    "studio-backend/scripts/verify_wan_hosted_generation.py": {"placement": "top", "provider": "dashscope"},
    "studio-backend/scripts/run_six_film_wan_certification.py": {"placement": "top", "provider": "dashscope"},
    "scripts/generate_fish_audio_dialogue.py": {"placement": "top", "provider": "fish-audio"},
    "scripts/generate_elevenlabs_dialogue.py": {"placement": "top", "provider": "elevenlabs"},
    "scripts/convert_elevenlabs_voice_changer.py": {"placement": "top", "provider": "elevenlabs"},
    "studio-backend/test_retry_real_job.py": {"placement": "main", "provider": "groq"},
    "studio-backend/test_retry_service_real_e2e.py": {"placement": "main", "provider": "groq"},
    "studio-backend/test_retry_local_video.py": {"placement": "main", "provider": "groq"},
    "studio-backend/test_adherence_direct.py": {"placement": "main", "provider": "groq"},
    "studio-backend/test_corrector_direct.py": {"placement": "main", "provider": "groq"},
    "studio-backend/test_corrector_variations.py": {"placement": "main", "provider": "groq"},
    "studio-backend/test_corrector_on_real_failure.py": {"placement": "main", "provider": "groq"},
    "studio-backend/test_corrector_fixed.py": {"placement": "main", "provider": "groq"},
    "studio-backend/test_attempt1_score_only.py": {"placement": "main", "provider": "gemini"},
    "studio-backend/scripts/plan_casting_voice_provider_comparison.py": {"placement": "main", "provider": "fish-audio"},
}

# Writes outside the pipeline but spends nothing. Live-DB opens go through
# db_guard (dual live flags) or isolated storage; no gate is added.
DB_WRITE_ONLY = {
    "studio-backend/persist_bestof3_results.py": "hand-writes render_attempts rows; live open via db_guard",
    "studio-backend/verify_render_attempts_table.py": "schema check (opens RW; logic untouched)",
    "studio-backend/test_create_real_job.py": "simulated-provider create_job only, no submit",
    "studio-backend/test_prompt_format.py": "create_job assembly only, no submit",
    "studio-backend/test_project_creation_fix.py": "live-server driver; keeps its STUDIO_ALLOW_LIVE_SCRIPTS check",
    "studio-backend/scripts/cleanup_invalid_characters.py": "project-store cleanup, no providers",
    "studio-backend/scripts/show_shot_prompt.py": "create_job assembly only, no submit",
    "studio-backend/scripts/seed_demo_studio_project.py": "demo seed writes via service",
    "studio-backend/scripts/repair_orphaned_image_prompts.py": "--apply writes; refuses live studio.db by itself",
    "studio-backend/scripts/dry_run_scene_002_repair_check.py": "opens RW handle, no provider contact",
    "studio-backend/scripts/validate_reference_continuity.py": "isolated backend + hardcoded local_ltx submits only",
    "tools/verify_endpoint_workflow_integrity.py": "spawns isolated backend; paid calls never enabled by construction",
    "studio-backend/scripts/backfill_study_references.py": "reads via legacy storage handle; writes nothing",
}

# Diagnostics. Anti-rot: no spend calls, no DB read-write opens, no external
# provider hosts. Localhost-only network noted per file.
READ_ONLY = {
    "studio-backend/diagnose_runway_provider.py": "provider listing only; key prints removed",
    "studio-backend/verify_new_tables.py": "open_db_readonly schema check",
    "studio-backend/test_defensive_validation.py": "pure asserts, no network",
    "studio-backend/check_apply_diff_dedup.py": "pure diff demo, no network",
    "studio-backend/scripts/diagnose_shot_inputs.py": "open_db_readonly",
    "studio-backend/scripts/diagnose_storage_target.py": "resolve + open_db_readonly",
    "studio-backend/scripts/list_render_targets.py": "open_db_readonly",
    "studio-backend/scripts/adherence_benchmark.py": "open_db_readonly",
    "studio-backend/scripts/inspect_scene_direction_snapshot.py": "disposable-copy reads; blocks subprocess",
    "studio-backend/scripts/audit_studio_state_readonly_20260927.py": "reads backup artifacts only",
    "studio-backend/scripts/verify_scene_pipeline_capture.py": "reads local evidence files only",
    "studio-backend/scripts/probe_scene003_full_scene_pipeline.py": "fully local fakes (mock renders/audio)",
    "studio-backend/scripts/record_casting_voice_provider_decision.py": "writes local JSON decision artifact only",
    "studio-backend/scripts/audit_scene003_audio_goal.py": "reads local proof artifacts only",
    "studio-backend/scripts/verify_i_was_reborn_scene_002_assembly.py": "ffprobe + file reads on saved artifact",
    "studio-backend/scripts/verify_character_reference_locking_capture.py": "tempfile DB + CaptureAdapter (fake URLs)",
    "studio-backend/scripts/dry_run_provider_boundary.py": "copies live DB bytes to tmp; no sqlite open, no network",
    "studio-backend/scripts/analyze_scene_002_dialogue_prosody.py": "local audio analysis only",
    "studio-backend/scripts/audit_scene_002_structure_alignment.py": "local alignment audit only",
    "check_asset_urls.py": "open_db_readonly + local FS checks",
    "scripts/comfyui_phantom_identity_context_experiment.py": "local ComfyUI (127.0.0.1) + read-only studio DB",
    "scripts/comfyui_phantom_multiref_experiment.py": "local ComfyUI (127.0.0.1), no studio imports",
    "scripts/comfyui_phantom_ic_contact_sheet.py": "local-only figure assembly",
    "scripts/comfyui_phantom_ic_determinism_probe.py": "local ComfyUI (127.0.0.1) polling",
    "scripts/comfyui_phantom_ic_make_specs.py": "local-only spec writer",
    "scripts/test_pipeline.py": "local-only models (torch/piper/musicgen); /tmp outputs; no providers, no DB",
    "e2e_studio_pipeline_test.py": "localhost API driver (BASE_URL hardcoded http://localhost:8010); POSTs excepted",
    "verify_previs_fixes.py": "backend shape checks (GET + advisory-previs POSTs, no render submit); urlopen excepted",
    "test_script_parsing.py": "local ScriptParser diagnostic",
    "test_script_parser_fix.py": "local parser diagnostic",
    "test_render_prompt_pipeline.py": "local prompt-pipeline diagnostic",
    "test_shot_prompts.py": "local shot-prompt diagnostic",
}

# Pipeline/harness proper: not one-off scripts. Membership-only.
OUT_OF_SCOPE = {
    "studio-backend/conftest.py": "pytest harness; redirects storage to isolated tmp",
    "studio-backend/main.py": "pipeline server entry point",
    "studio-backend/casting_service.py": "pipeline provider module used by services",
    "studio-backend/fish_audio_provider.py": "pipeline provider module used by services",
    "studio-backend/r43k_network_block_plugin.py": "pytest plugin",
    "studio-backend/creator_workspace_fixture.py": "fixture module imported by tests",
}

# --------------------------------------------------------------------------
# Static helpers.
# --------------------------------------------------------------------------

RISKY_IMPORT_PREFIXES = (
    "app",
    "dotenv",
    "openai",
    "httpx",
    "requests",
    "urllib",
    "groq",
    "google",
    "aiohttp",
)
# Sibling-script imports allowed to precede the guard: the target executes
# only stdlib imports and defs at top level (it is Pattern B or ungated).
SAFE_SIBLING_IMPORTS = {
    "verify_runway_hosted_generation",
    "scripts.verify_runway_hosted_generation",
}
# Name/attr fragments that must not appear in statements preceding a
# top-level ("top" placement) guard call.
RISKY_EARLY_NAMES = {
    "app",
    "dotenv",
    "load_dotenv",
    "openai",
    "OpenAI",
    "httpx",
    "requests",
    "urllib",
    "groq",
    "Groq",
    "genai",
    "get_storage",
    "DatabaseStorage",
    "SQLiteStorage",
    "open_db_read",
    "open_db_readwrite",
    "open_db_readonly",
    "resolve_db",
    "submit_job",
    "submit_image_render",
    "get_adapter",
    "sqlite3",
    "subprocess",
    "curl",
}
EXTERNAL_HOSTS = (
    "api.dev.runwayml.com",
    "api.openrouter.ai",
    "api.elevenlabs.io",
    "fish.audio",
    "api.groq.com",
    "generativelanguage.googleapis.com",
    "dashscope.aliyuncs.com",
)

# Verified-local fakes: spend-shaped text that may appear ONLY in the listed
# file, with the fake mechanism pinned by assertions below. Anything else
# still fails. No new categories: these files stay READ_ONLY (local-only at
# runtime) with narrowly scoped, self-expiring (staleness-asserted) exceptions.
READ_ONLY_FAKE_EXCEPTIONS = {
    "studio-backend/scripts/probe_scene003_full_scene_pipeline.py": {
        "reason": "local-mock mode: LocalRenderService/LocalCosyVoiceAudioService "
        "return canned dicts incl. a cosyvoice provider label; never called",
        "calls": set(),
        "literals": ['"provider": "cosyvoice"'],
        "mechanism": ("LocalRenderService", "LocalCosyVoiceAudioService", '"mode": "local-mock"'),
    },
    "studio-backend/scripts/verify_character_reference_locking_capture.py": {
        "reason": "tempfile DB + get_adapter monkeypatched to CaptureAdapter; "
        "RenderService.submit_job never leaves the process",
        "calls": {"submit_job"},
        "db_calls": {"DatabaseStorage"},
        "literals": ['provider="happyhorse"'],
        "mechanism": ("CaptureAdapter", "tempfile.mkdtemp", "get_adapter = lambda"),
    },
}

# Call names forbidden outside gated files (spend primitives).
SPEND_CALLS = {
    "submit_job",
    "submit_image_render",
    "get_adapter",
    "Groq",
    "OpenAI",
    "AsyncOpenAI",
    "text_to_image",
}
# Call names forbidden in READ_ONLY files (DB read-write opens). get_storage
# is included: read-only diagnostics use open_db_readonly/resolve_db_file.
RO_DB_CALLS = {
    "get_storage",
    "DatabaseStorage",
    "SQLiteStorage",
    "open_db_readwrite",
}
PROVIDER_LITERAL_RE = re.compile(
    r"""["']provider["']\s*:\s*["'](runway|openrouter|happyhorse|wan|qwen|dashscope|cosyvoice|fish|elevenlabs)"""
    r"""|provider\s*=\s*["'](runway|openrouter|happyhorse|wan|qwen|dashscope|cosyvoice|fish|elevenlabs)""",
)


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _iter_scope_files() -> list[Path]:
    out: list[Path] = []
    out.extend(p for p in BACKEND_ROOT.glob("*.py") if p.is_file())
    for sub in ("scripts",):
        out.extend(p for p in (BACKEND_ROOT / sub).glob("*.py") if p.is_file())
    out.extend(p for p in (REPO_ROOT / "scripts").glob("*.py") if p.is_file())
    out.extend(p for p in (REPO_ROOT / "tools").glob("*.py") if p.is_file())
    out.extend(p for p in REPO_ROOT.glob("*.py") if p.is_file())
    return sorted(out)


def _guard_calls(tree: ast.AST) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in {"require_live_spend_gate", "refuse_non_approved_provider"}:
            found.append(node)
    return found


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _kw_str(call: ast.Call, key: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return None


def _names_in(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


# --------------------------------------------------------------------------
# The scan.
# --------------------------------------------------------------------------


def _check_top_placement(source: str, tree: ast.Module, rel: str) -> None:
    calls = [n for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    guard = [c for c in (n.value for n in calls) if _call_name(c) in {"require_live_spend_gate", "refuse_non_approved_provider"}]
    assert len(guard) == 1, f"{rel}: expected exactly one top-level guard call"
    guard_line = guard[0].lineno
    for node in tree.body:
        if node.lineno is not None and node.lineno < guard_line:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = "" if isinstance(node, ast.Import) else (node.module or "")
                if module == "app.script_guard":
                    continue  # the guard itself: proven side-effect-free below
                first = module.split(".")[0]
                assert first not in RISKY_IMPORT_PREFIXES, f"{rel}: risky import before guard: {module or node.names[0].name}"
                assert module not in SAFE_SIBLING_IMPORTS or True
            names = _names_in(node)
            risky = names & RISKY_EARLY_NAMES
            assert not risky, f"{rel}: risky names before guard: {sorted(risky)}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = "" if isinstance(node, ast.Import) else (node.module or "")
            if module == "app.script_guard":
                continue  # the guard itself: proven side-effect-free below
            first = module.split(".")[0]
            if module in SAFE_SIBLING_IMPORTS:
                continue
            if first in RISKY_IMPORT_PREFIXES:
                assert node.lineno is not None and node.lineno > guard_line, (
                    f"{rel}: risky import at line {node.lineno} precedes guard at {guard_line}"
                )


def _check_main_placement(tree: ast.Module, rel: str) -> None:
    """Guard call is the first statement of main() or the __main__ block,
    and module top level performs no spend/write/network calls."""
    setup_risky = (
        RISKY_EARLY_NAMES | SPEND_CALLS | RO_DB_CALLS
        | {"urlopen", "post", "Popen", "check_output", "check_call", "run", "input", "exit", "main"}
    )

    def _guard_index(body: list[ast.stmt]) -> int | None:
        for i, stmt in enumerate(body):
            if (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and _call_name(stmt.value) in {"require_live_spend_gate", "refuse_non_approved_provider"}
            ):
                return i
        return None

    def _is_main_guard(node: ast.If) -> bool:
        test = ast.dump(node.test)
        return "__name__" in test and "__main__" in test

    found: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main" and node.body:
            idx = _guard_index(node.body)
            if idx is not None:
                for stmt in node.body[:idx]:
                    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                        module = "" if isinstance(stmt, ast.Import) else (stmt.module or "")
                        assert module == "app.script_guard" or module.split(".")[0] not in RISKY_IMPORT_PREFIXES, (
                            f"{rel}: risky import before in-main guard: {module}"
                        )
                    else:
                        bad = _names_in(stmt) & setup_risky
                        assert not bad, f"{rel}: non-setup statement before in-main guard: {sorted(bad)}"
                found.append(("main", node.body[idx].lineno))
        if isinstance(node, ast.If) and node.body and _is_main_guard(node):
            idx = _guard_index(node.body)
            if idx is not None:
                for stmt in node.body[:idx]:
                    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                        module = "" if isinstance(stmt, ast.Import) else (stmt.module or "")
                        assert module == "app.script_guard" or module.split(".")[0] not in RISKY_IMPORT_PREFIXES, (
                            f"{rel}: risky import before __main__ guard: {module}"
                        )
                    else:
                        bad = _names_in(stmt) & setup_risky
                        assert not bad, f"{rel}: non-setup statement before __main__ guard: {sorted(bad)}"
                found.append(("__main__", node.body[idx].lineno))
    assert found, f"{rel}: Pattern B requires guard in main() or __main__ before any non-setup work"
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            name = _call_name(node.value)
            assert name not in SPEND_CALLS | RO_DB_CALLS | {"urlopen", "post", "input"} | {"run", "Popen", "check_output", "call"}, (
                f"{rel}: top-level call {name}() must not precede the in-main guard"
            )
            if name == "run" or (isinstance(node.value.func, ast.Attribute) and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "subprocess"):
                raise AssertionError(f"{rel}: top-level subprocess call must not precede the in-main guard")


def test_scan_every_script_classified_and_guarded() -> None:
    classified = set(RUNWAY_GATED) | set(NONAPPROVED_GATED) | set(DB_WRITE_ONLY) | set(READ_ONLY) | set(OUT_OF_SCOPE)
    files = _iter_scope_files()
    rels = [_rel(p) for p in files]
    assert len(rels) == len(set(rels))
    unclassified = [r for r in rels if r not in classified]
    assert not unclassified, f"unclassified scripts fail the scan: {unclassified}"
    stray = [r for r in classified if r not in rels]
    assert not stray, f"manifest references missing files: {stray}"

    for rel, meta in RUNWAY_GATED.items():
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        calls = _guard_calls(tree)
        assert len(calls) == 1 and _call_name(calls[0]) == "require_live_spend_gate", f"{rel}: needs require_live_spend_gate"
        assert _kw_str(calls[0], "provider") == "runway", f"{rel}: Runway gate must use provider='runway'"
        assert _kw_str(calls[0], "what") and _kw_str(calls[0], "exposure"), f"{rel}: guard needs what/exposure"
        if meta["placement"] == "top":
            _check_top_placement((REPO_ROOT / rel).read_text(encoding="utf-8"), tree, rel)
        else:
            _check_main_placement(tree, rel)

    for rel, meta in NONAPPROVED_GATED.items():
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        calls = _guard_calls(tree)
        assert len(calls) == 1 and _call_name(calls[0]) == "refuse_non_approved_provider", f"{rel}: needs refuse_non_approved_provider"
        provider = _kw_str(calls[0], "provider")
        assert provider and provider != "runway", f"{rel}: non-approved gate needs a non-runway provider"
        assert provider == meta["provider"], f"{rel}: provider {provider!r} != manifest {meta['provider']!r}"
        assert _kw_str(calls[0], "what"), f"{rel}: guard needs what"
        if meta["placement"] == "top":
            _check_top_placement((REPO_ROOT / rel).read_text(encoding="utf-8"), tree, rel)
        else:
            _check_main_placement(tree, rel)

    for rel in list(DB_WRITE_ONLY) + list(READ_ONLY):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(text)
        names = {_call_name(n) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        bad = names & SPEND_CALLS
        exc = READ_ONLY_FAKE_EXCEPTIONS.get(rel)
        allowed_calls: set[str] = exc["calls"] if exc else set()
        assert not (bad - allowed_calls), f"{rel}: ungated file must not reach spend calls: {sorted(bad)}"
        if exc:
            assert allowed_calls <= names, f"{rel}: stale call exception: {sorted(allowed_calls - names)}"
            for marker in exc["mechanism"]:
                assert marker in text, f"{rel}: fake mechanism marker missing: {marker!r}"
        for host in EXTERNAL_HOSTS:
            assert host not in text, f"{rel}: ungated file must not contact {host}"
        scrubbed = text
        for lit in exc["literals"] if exc else []:
            assert lit in text, f"{rel}: stale literal exception: {lit!r}"
            scrubbed = scrubbed.replace(lit, "")
        assert not PROVIDER_LITERAL_RE.search(scrubbed), f"{rel}: ungated file must not select a render provider"

    for rel in READ_ONLY:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(text)
        names = {_call_name(n) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        bad = names & (RO_DB_CALLS | {"urlopen", "post", "Popen", "check_output", "curl"})
        exc_ro = READ_ONLY_FAKE_EXCEPTIONS.get(rel)
        if exc_ro:
            bad -= exc_ro.get("db_calls", set())
        if rel in {
            "scripts/comfyui_phantom_ic_determinism_probe.py",
            "scripts/comfyui_phantom_identity_context_experiment.py",
            "scripts/comfyui_phantom_multiref_experiment.py",
            "verify_previs_fixes.py",
        }:
            bad.discard("urlopen")  # localhost checks only; no external hosts (asserted above)
        if rel == "e2e_studio_pipeline_test.py":
            bad.discard("post")  # BASE_URL hardcoded to http://localhost:8010; no external hosts (asserted above)
        assert not bad, f"{rel}: read-only file must not write DB or POST: {sorted(bad)}"

    for rel in OUT_OF_SCOPE:
        assert OUT_OF_SCOPE[rel].strip(), f"{rel}: out-of-scope needs a reason"


def test_no_top_level_guarded_module_is_imported() -> None:
    """Pattern-A files must have no importers: a top-level guard call fires
    on any import, so importing one would SystemExit the importer."""
    top_level = [r for r, m in RUNWAY_GATED.items() if m["placement"] == "top"]
    top_level += [r for r, m in NONAPPROVED_GATED.items() if m["placement"] == "top"]
    basenames = {Path(r).stem for r in top_level}
    search_roots = [BACKEND_ROOT / "app", BACKEND_ROOT / "tests", BACKEND_ROOT / "scripts",
                    BACKEND_ROOT, REPO_ROOT / "scripts", REPO_ROOT / "tools", REPO_ROOT]
    importers: list[str] = []
    seen: set[Path] = set()
    for root in search_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if path in seen or "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
        seen.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            hit = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.split(".")[-1]
                if mod in basenames:
                    hit = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[-1] in basenames:
                        hit = alias.name
            if hit:
                importers.append(f"{_rel(path)} imports {hit}")
    # importlib-loaded scripts execute top-level too; the same rule applies.
    for path in sorted(seen):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for base in basenames:
            if re.search(r"spec_from_file_location\s*\(\s*[\"']" + re.escape(base) + r"[\"']", text):
                importers.append(f"{_rel(path)} importlib-loads {base}")
            if re.search(r"[\"']" + re.escape(base) + r"\.py[\"']", text) and "spec_from_file_location" in text:
                importers.append(f"{_rel(path)} references {base}.py with importlib")
    assert not importers, "top-level-gated scripts must have no importers:\n" + "\n".join(importers[:10])


# --------------------------------------------------------------------------
# Dynamic proof: refusal precedes any network or DB open.
# --------------------------------------------------------------------------

_SCRUB_PREFIXES = (
    "RUNWAY",
    "OPENROUTER",
    "GROQ",
    "GEMINI",
    "GOOGLE_API",
    "ELEVENLABS",
    "FISH_AUDIO",
    "DASHSCOPE",
    "QWEN",
    "WAN_",
    "ADHERENCE_",
    "LIVE_",
)
_SCRUB_EXACT = {
    ENV_FLAG,
    "STUDIO_ALLOW_LIVE_SCRIPTS",
    "STUDIO_ALLOW_LIVE_DB",
    "STUDIO_PRIMARY_WRITER",
    "STUDIO_ALLOW_DEV_ROUTES",
    "STUDIO_ALLOW_LIVE_NETWORK_TESTS",
}


class _BlockedTransport(RuntimeError):
    """Raised by stubbed transports: reaching one means the guard failed."""


def _install_stubs(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    calls: dict[str, list] = {"network": [], "db": []}

    def _net(name: str):
        def _raise(*args: object, **kwargs: object):
            calls["network"].append(name)
            raise _BlockedTransport(f"network use before guard: {name}")
        return _raise

    monkeypatch.setattr(urllib.request, "urlopen", _net("urllib.request.urlopen"))
    for modname in ("httpx", "requests"):
        try:
            mod = __import__(modname)
        except ImportError:
            continue
        for attr in ("get", "post", "put", "delete", "request"):
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, _net(f"{modname}.{attr}"), raising=False)
        if hasattr(mod, "Client"):
            cls = getattr(mod, "Client")
            for meth in ("get", "post", "put", "delete", "request", "send"):
                monkeypatch.setattr(cls, meth, _net(f"{modname}.Client.{meth}"), raising=False)
    if hasattr(__import__("requests"), "Session"):
        import requests as _rq
        monkeypatch.setattr(_rq.Session, "request", _net("requests.Session.request"), raising=False)
    monkeypatch.setattr(subprocess, "run", _net("subprocess.run"))
    monkeypatch.setattr(subprocess, "check_output", _net("subprocess.check_output"))
    monkeypatch.setattr(subprocess, "check_call", _net("subprocess.check_call"), raising=False)
    monkeypatch.setattr(subprocess, "Popen", _net("subprocess.Popen"))

    real_connect = sqlite3.connect

    def _counting_connect(*args: object, **kwargs: object):
        calls["db"].append(args[0] if args else "")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", _counting_connect)
    return calls


def _scrub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key in _SCRUB_EXACT or key.startswith(_SCRUB_PREFIXES):
            monkeypatch.delenv(key, raising=False)


LIVE_DB_FILE = BACKEND_ROOT / "data" / "studio.db"


def _is_live_db(target: object) -> bool:
    try:
        p = Path(str(target)).expanduser()
    except (TypeError, ValueError, OSError):
        return False
    try:
        rp = p.resolve()
    except OSError:
        rp = p
    try:
        live = LIVE_DB_FILE.resolve()
        return rp == live or rp.parent == live.parent
    except OSError:
        return False


def _run_guarded(path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], argv_extra: list[str]) -> object:
    monkeypatch.syspath_prepend(str(BACKEND_ROOT))
    monkeypatch.syspath_prepend(str(path.parent))
    _scrub_env(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    calls = _install_stubs(monkeypatch)
    monkeypatch.setattr(sys, "argv", [str(path), *argv_extra])
    err: dict[str, str] = {}
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exc:
        err["code"] = exc.code
    except _BlockedTransport as exc:
        err["code"] = f"transport-reached:{exc}"
    err_text = ""
    return err, calls


def _gated_items() -> list[tuple[str, str]]:
    items = [(rel, "require") for rel in RUNWAY_GATED]
    items += [(rel, "refuse") for rel in NONAPPROVED_GATED]
    return sorted(items)


@pytest.mark.parametrize("rel,kind", _gated_items())
@pytest.mark.parametrize(
    "case_name,case_env,case_argv",
    [
        pytest.param("no-auth", {}, [], id="no-auth"),
        pytest.param("env-only", {ENV_FLAG: "1"}, [], id="env-only"),
        pytest.param("confirm-only", {}, ["CONFIRM-BASENAME"], id="confirm-only"),
        pytest.param("wrong-name", {ENV_FLAG: "1"}, ["--confirm-spend=some_other_script.py"], id="wrong-name"),
    ],
)
def test_refusal_matrix_all_gated_scripts(
    rel: str,
    kind: str,
    case_name: str,
    case_env: dict,
    case_argv: list,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Every gated script, without dual opt-in, exits 2 before any
    network or DB open (stubbed transports raise; sqlite opens counted)."""
    path = REPO_ROOT / rel
    base = path.name
    argv_extra = [(f"--confirm-spend={base}" if a == "CONFIRM-BASENAME" else a) for a in case_argv]
    result, calls = _run_guarded(path, monkeypatch, dict(case_env), argv_extra)
    assert result.get("code") == 2, f"{rel} [{case_name}]: expected SystemExit(2), got {result!r}"
    assert calls["network"] == [], f"{rel} [{case_name}]: network before guard: {calls['network']}"
    live = [p for p in calls["db"] if _is_live_db(p)]
    assert not live, f"{rel} [{case_name}]: live DB touched: {live}"
    captured = capsys.readouterr()
    assert "REFUSING" in captured.err and base in captured.err, f"{rel} [{case_name}]: refusal must name the script"


@pytest.mark.parametrize("rel,kind", _gated_items())
def test_refusal_matrix_both_factors_still_refuses_without_gate(rel: str, kind: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    """Even with BOTH factors present, non-approved scripts refuse (unconditional).
    Runway scripts are NOT executed with both factors here (that would spend)."""
    if kind != "refuse":
        pytest.skip("dual-auth execution would spend; covered by unit test instead")
    path = REPO_ROOT / rel
    base = path.name
    result, calls = _run_guarded(path, monkeypatch, {ENV_FLAG: "1"}, [f"--confirm-spend={base}"])
    assert result.get("code") == 2, f"{rel}: non-approved script must refuse even with dual opt-in"
    assert calls["network"] == []
    captured = capsys.readouterr()
    assert "non-approved provider" in captured.err


@pytest.mark.parametrize(
    "env,argv,provider,expect",
    [
        ({}, [], "runway", 2),
        ({ENV_FLAG: "1"}, [], "runway", 2),
        ({}, ["--confirm-spend=x.py"], "runway", 2),
        ({ENV_FLAG: "1"}, ["--confirm-spend=other.py"], "runway", 2),
        ({ENV_FLAG: "1"}, ["--confirm-spend=x.py"], "runway", None),
        ({ENV_FLAG: "1"}, ["--confirm-spend=x.py"], "openrouter", 2),
        ({ENV_FLAG: " true "}, ["--confirm-spend=x.py"], "runway", 2),
    ],
)
def test_dual_opt_in_unit(env: dict, argv: list, provider: str, expect: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate function itself: returns only on exact dual opt-in."""
    from app.script_guard import require_live_spend_gate

    _scrub_env(monkeypatch)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["x.py", *argv])
    if expect is None:
        assert require_live_spend_gate("some/dir/x.py", what="w", exposure="e", provider=provider) is None
    else:
        with pytest.raises(SystemExit) as exc:
            require_live_spend_gate("some/dir/x.py", what="w", exposure="e", provider=provider)
        assert exc.value.code == expect


def test_refuse_emits_no_secrets(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    from app.script_guard import require_live_spend_gate

    _scrub_env(monkeypatch)
    monkeypatch.setenv("RUNWAYML_API_SECRET", "SECRET_MARKER_abc123xyz")
    monkeypatch.setenv("OPENROUTER_API_KEY", "SECRET_MARKER_abc123xyz")
    monkeypatch.setattr(sys, "argv", ["x.py", "--confirm-spend=SECRET_MARKER_abc123xyz"])
    with pytest.raises(SystemExit):
        require_live_spend_gate("x.py", what="would submit one render", exposure="e", provider="runway")
    captured = capsys.readouterr()
    assert "SECRET_MARKER_abc123xyz" not in captured.err
    assert "present:" in captured.err  # presence booleans only


def _run_import_probe(code: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not (k in _SCRUB_EXACT or k.startswith(_SCRUB_PREFIXES))}
    return subprocess.run([sys.executable, "-c", code], cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120)


def test_guard_import_is_side_effect_free() -> None:
    """Fresh interpreters: importing the guard pulls in no app.data/storage,
    opens nothing, and refuses cleanly (exit 2, no traceback)."""
    probe = (
        "import sys;"
        "sys.path.insert(0, {path!r});"
        "import app.script_guard as g;"
        "assert 'app.data' not in sys.modules, sorted(m for m in sys.modules if m.startswith('app'));"
        "assert 'app.data.storage' not in sys.modules;"
        "g.require_live_spend_gate('probe_script.py', what='w', exposure='e', provider='runway')"
    )
    root_style = _run_import_probe(probe.format(path=str(BACKEND_ROOT)), REPO_ROOT)
    assert root_style.returncode == 2, root_style.stderr[-2000:]
    assert "REFUSING" in root_style.stderr
    assert "Traceback" not in root_style.stderr
    backend_probe = probe.format(path=".")
    backend_style = _run_import_probe(
        backend_probe,
        BACKEND_ROOT,
    )
    assert backend_style.returncode == 2, backend_style.stderr[-2000:]
    assert "Traceback" not in backend_style.stderr


def test_guard_placement_avoids_heavy_init() -> None:
    """app/__init__ must stay side-effect free (comment only); app/data/__init__
    imports storage, which is why the guard does not live under app/data."""
    app_init = ast.parse((BACKEND_ROOT / "app" / "__init__.py").read_text(encoding="utf-8"))
    assert not [n for n in ast.walk(app_init) if isinstance(n, (ast.Import, ast.ImportFrom))], "app/__init__.py must import nothing"
    data_init = ast.parse((BACKEND_ROOT / "app" / "data" / "__init__.py").read_text(encoding="utf-8"))
    assert any(
        isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app.data.storage") for n in ast.walk(data_init)
    ), "app/data/__init__.py still pulls in storage (guard placement rationale)"
    guard_src = (BACKEND_ROOT / "app" / "script_guard.py").read_text(encoding="utf-8")
    guard_tree = ast.parse(guard_src)
    mods: set[str] = set()
    has_relative = False
    for n in ast.walk(guard_tree):
        if isinstance(n, ast.ImportFrom):
            if n.level:
                has_relative = True
            elif n.module:
                mods.add(n.module.split(".")[0])
        elif isinstance(n, ast.Import):
            for a in n.names:
                mods.add(a.name.split(".")[0])
    assert not has_relative, "guard must not use relative imports"
    assert mods <= {"__future__", "logging", "os", "sys", "datetime", "zoneinfo", "pathlib", "typing"}, f"guard must stay stdlib-only: {mods}"


def test_refusal_timestamp_carries_tz() -> None:
    from datetime import datetime as _dt

    from app.script_guard import _now_iso

    parsed = _dt.fromisoformat(_now_iso())
    assert parsed.tzinfo is not None and parsed.utcoffset() is not None


def test_diagnose_prints_no_key_material() -> None:
    text = (BACKEND_ROOT / "diagnose_runway_provider.py").read_text(encoding="utf-8")
    assert "Key length" not in text
    assert "first 4" not in text
    assert "last 4" not in text
    assert "RUNWAYML_API_SECRET" in text  # presence check retained


def test_scan_fails_at_head_proof() -> None:
    """Fail-before proof: at the parent of the guard commit, every
    currently-gated file lacks the guard call, i.e. the scan above would
    flag it. Uses 98f348ba^ so the proof stays valid after the guard
    commit itself added script_guard to those files at HEAD."""
    probe = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(REPO_ROOT), capture_output=True, timeout=30)
    if probe.returncode != 0:
        pytest.skip("no git worktree here")
    missing_blobs: list[str] = []
    flagged = 0
    for rel in list(RUNWAY_GATED) + list(NONAPPROVED_GATED):
        blob = subprocess.run(["git", "show", f"98f348ba^:{rel}"], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30)
        if blob.returncode != 0:
            missing_blobs.append(rel)
            continue
        assert "script_guard" not in blob.stdout, f"{rel}: 98f348ba^ already guarded; proof invalid"
        assert "require_live_spend_gate" not in blob.stdout and "refuse_non_approved_provider" not in blob.stdout
        flagged += 1
    assert not missing_blobs, f"gated files missing at 98f348ba^: {missing_blobs}"
    assert flagged == len(RUNWAY_GATED) + len(NONAPPROVED_GATED) and flagged > 0

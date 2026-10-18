from __future__ import annotations

import copy

import pytest

from app.services.camera_provenance import camera_plan_digest

from app.services.generation_contract import (
    FrozenGenerationContract,
    GenerationContractError,
    freeze_generation_contract,
)
from app.services.scene_coverage_contract import (
    build_scene_coverage_contract,
    resolve_scene_lineage,
    verify_scene_coverage_contract,
)
from app.services.providers.runway_router_provider import (
    build_runway_router_video_request,
    project_frozen_camera_plan_prompt,
)


# Synthetic project intentionally uses unique, non-production identities and
# content. It is separate from the forensic I Was Reborn specimen.
def _synthetic_state():
    scene_text = (
        "INT. GLASSWORKS - DAWN\n"
        "Neri balances the cracked lantern on the workbench.\n"
        "IVO\nThe glass remembers every hand.\n"
        "Neri turns the wick toward the window."
    )
    project_id = "project-synthetic-glass"
    scene_id = "scene_glass_17"
    script_text = f"TITLE: The Last Lantern\n{scene_text}\nEXT. CANAL - DAY\nA ferry passes."
    dialogue_line = {
        "line_id": "dlg-glass-ivo-001",
        "scene_id": scene_id,
        "character": "IVO",
        "text": "The glass remembers every hand.",
    }
    scene = {
        "scene_id": scene_id,
        "heading": "INT. GLASSWORKS - DAWN",
        "text": scene_text,
        "characters": ["Neri", "IVO"],
        "setting_id": "set-glassworks",
        "dialogue_dispositions": [],
    }
    shots = []
    for shot_id, shot_number, character, dialogue_lines, camera in (
        ("scene_glass_17_take_A", 1, "IVO", [dict(dialogue_line, shot_id="scene_glass_17_take_A")], "medium"),
        ("scene_glass_17_take_B", 2, "Neri", [], "close"),
    ):
        camera_plan = {"camera": "locked off", "framing": camera}
        camera_parameters = {
            "camera_provenance": "USER_SPECIFIED",
            "camera_plan": camera_plan,
            "creator_shot_planning": camera_plan,
            "camera_source_project_id": project_id,
            "camera_source_scene_id": scene_id,
            "camera_source_shot_id": shot_id,
            "camera_target_project_id": project_id,
            "camera_target_scene_id": scene_id,
            "camera_target_shot_id": shot_id,
            "character_focus": [character],
            "dialogue_lines": dialogue_lines,
        }
        camera_parameters["camera_source_digest"] = camera_plan_digest(
            camera_plan, "USER_SPECIFIED", source_project_id=project_id,
            source_scene_id=scene_id, source_shot_id=shot_id,
        )
        if not dialogue_lines:
            camera_parameters.update(
                dialogue_disposition="INTENTIONAL_SILENCE",
                dialogue_disposition_reason="Hold on Neri's silent reaction after the spoken line.",
            )
        shots.append({
            "shot_id": shot_id,
            "scene_id": scene_id,
            "shot_number": shot_number,
            "covered_content_ids": [],
            "parameters": camera_parameters,
        })
    scene["characters"] = ["Neri", "IVO"]
    project = {
        "project_id": project_id,
        "script_text": script_text,
        "execution_summary": {"scenes": [scene], "dialogue_lines": [dialogue_line]},
    }
    references = [
        {"ref_id": "ref-ivo-face", "uri": "https://assets.example.test/ivo.png", "target_type": "character", "target_id": "char-ivo", "role": "face", "approval_state": "approved", "canonical": True},
        {"ref_id": "ref-neri-face", "uri": "https://assets.example.test/neri.png", "target_type": "character", "target_id": "char-neri", "role": "face", "approval_state": "approved", "canonical": True},
        {"ref_id": "ref-setting-glass", "uri": "https://assets.example.test/glassworks.png", "target_type": "setting", "target_id": "set-glassworks", "role": "environment", "approval_state": "approved", "canonical": True},
    ]
    requirements = {
        "setting_id": "set-glassworks",
        "character_ids": ["char-ivo", "char-neri"],
        "characters": {
            "char-ivo": {"name": "IVO", "references": [references[0]]},
            "char-neri": {"name": "Neri", "references": [references[1]]},
        },
        "reference_binding": references,
    }
    return project_id, scene_id, project, scene, shots, requirements


def _creator_decisions(probe, shots, *, dialogue_status="ASSIGNED", dialogue_shot=0, dialogue_reason=""):
    """Explicit version-scoped Scene Direction decisions for the synthetic scene."""
    content_ids = [row["content_id"] for row in probe["content_units"]]
    # The canonical projection keeps the persisted line identity when the
    # creator-curated row exists in the structured projection.
    dialogue_id = probe["dialogue"][0]["dialogue_id"]
    decisions = [
        {"obligation_type": "content", "obligation_id": identity, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"] if index < 2 else shots[1]["shot_id"], "reason": ""}
        for index, identity in enumerate(content_ids)
    ]
    decisions.extend([
        {"obligation_type": "dialogue", "obligation_id": dialogue_id,
         "status": dialogue_status,
         "shot_id": shots[dialogue_shot]["shot_id"] if dialogue_status == "ASSIGNED" else None,
         "reason": dialogue_reason},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"],
         "status": "UNASSIGNED" if dialogue_status == "ASSIGNED" and dialogue_shot == 0
         else ("EXPLICITLY_OMITTED" if dialogue_status == "EXPLICITLY_OMITTED" else "INTENTIONAL_SILENCE"),
         "reason": dialogue_reason if dialogue_status == "EXPLICITLY_OMITTED" and dialogue_shot == 0 else ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"],
         "status": "INTENTIONAL_SILENCE" if dialogue_shot != 1 else "UNASSIGNED",
         "reason": "Hold on Neri's silent reaction after the spoken line." if dialogue_shot != 1 else ""},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ])
    return decisions


def _resolve_units(project_id, project, scene, shots, requirements):
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    content = probe["content_units"]
    decisions = _creator_decisions(probe, shots)
    result, blockers, assignments = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    return result, blockers, assignments


def _frozen_handoff(scene_coverage, shot_coverage):
    from app.services.generation_contract import freeze_dialogue_handoff

    covered = set(shot_coverage.get("covered_dialogue_ids") or [])
    lines = [
        {"line_id": row["dialogue_id"], "character": row["speaker"], "text": row["text"]}
        for row in scene_coverage.get("dialogue") or []
        if row.get("dialogue_id") in covered
    ]
    return freeze_dialogue_handoff(
        scene_id=shot_coverage["scene_id"], shot_id=shot_coverage["shot_id"], lines=lines,
    )


def test_lineage_accepts_separate_heading_and_body_and_excludes_trailing_section_header():
    project_id = "project-heading-body"
    heading = "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE"
    body = "Maya studies the water.\nDRE\nI need you to understand something.MAYA\nThat's funny."
    script = f"TITLE: Boundary\n{heading}\n{body}\nDRE — BEFORE THE FALL\nINT. APARTMENT - DAY\nThe next scene."
    project = {"project_id": project_id, "script_text": script}
    scene = {"scene_id": "scene_002", "heading": heading, "text": body + "\nDRE — BEFORE THE FALL"}

    lineage = resolve_scene_lineage(project_id, project, scene)

    assert lineage["status"] == "RESOLVED"
    assert lineage["scene_content"] == body
    assert lineage["scene_content"].endswith("That's funny.")
    assert "DRE — BEFORE THE FALL" not in lineage["scene_content"]
    assert script[lineage["scene_source_start"]:lineage["scene_source_end"]] == body


def test_lineage_rejects_trailing_section_header_inside_canonical_scene_body():
    project_id = "project-trailing-header"
    heading = "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE"
    body = "Maya studies the water."
    script = f"{heading}\n{body}\nDRE — BEFORE THE FALL\nINT. APARTMENT - DAY\nThe next scene."
    project = {"project_id": project_id, "script_text": script}
    scene = {"scene_id": "scene_002", "heading": heading, "text": body + "\nDRE — BEFORE THE FALL"}

    lineage = resolve_scene_lineage(project_id, project, scene)

    assert lineage["status"] == "RESOLVED"
    assert lineage["scene_content"] == body
    invalid = {**scene, "text": body + "\nDRE — BEFORE THE FALL\nINT. APARTMENT - DAY\nThe next scene."}
    assert resolve_scene_lineage(project_id, project, invalid)["status"] == "UNRESOLVED"


def test_script_lineage_binds_scene_to_exact_canonical_script_and_detects_stale_projection():
    project_id, _, project, scene, _, _ = _synthetic_state()
    lineage = resolve_scene_lineage(project_id, project, scene)
    assert lineage["status"] == "RESOLVED"
    assert lineage["canonical_script_sha256"]
    assert lineage["scene_source_identity"]
    stale = copy.deepcopy(scene)
    stale["text"] += "\nA line absent from the canonical script."
    assert resolve_scene_lineage(project_id, project, stale)["status"] == "UNRESOLVED"


def test_legacy_scene_coverage_fields_cannot_establish_creator_intent():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    legacy = copy.deepcopy(shots)
    for shot in legacy:
        shot["covered_content_ids"] = [row["content_id"] for row in probe["content_units"]]
        shot["parameters"]["dialogue_lines"] = [
            {"line_id": probe["dialogue"][0]["dialogue_id"], "scene_id": scene["scene_id"],
             "shot_id": shot["shot_id"], "character": "IVO", "text": "The glass remembers every hand."}
        ]
    project["execution_summary"]["dialogue_lines"][0]["shot_id"] = legacy[0]["shot_id"]
    contract, blockers, assignments = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=legacy,
        reference_requirements=requirements,
    )
    assert any("creator coverage decisions are missing" in blocker for blocker in blockers)
    assert all(row["disposition"] == "UNRESOLVED" for row in contract["content_units"])
    assert all(row["disposition"] == "UNRESOLVED" for row in contract["dialogue"])
    assert not any(rows for rows in assignments.values())


def test_scene_and_dialogue_ids_are_stable_ordered_and_traceable():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    first, _, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    second, _, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    assert [row["content_id"] for row in first["content_units"]] == [row["content_id"] for row in second["content_units"]]
    assert [row["dialogue_id"] for row in first["dialogue"]] == ["dlg-glass-ivo-001"]
    assert [row["order"] for row in first["content_units"]] == sorted(row["order"] for row in first["content_units"])
    assert all(row["scene_id"] == scene["scene_id"] for row in first["content_units"] + first["dialogue"])


def test_explicit_dialogue_assignment_and_shot_coverage_resolve_without_proximity_guessing():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    contract, blockers, assignments = _resolve_units(project_id, project, scene, shots, requirements)
    assert not [blocker for blocker in blockers if "dialogue" in blocker]
    line = contract["dialogue"][0]
    assert line["disposition"] == "ASSIGNED"
    assert line["shot_ids"] == [shots[0]["shot_id"]]
    assert assignments[shots[0]["shot_id"]][0]["line_id"] == line["dialogue_id"]
    assert contract["shots"][1]["dialogue_disposition"] == "INTENTIONAL_SILENCE"


def test_explicit_omission_is_distinct_from_silence_and_unresolved():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    decisions = _creator_decisions(
        probe, shots, dialogue_status="EXPLICITLY_OMITTED",
        dialogue_reason="The creator removed this line in the approved cut.",
    )
    shots[0]["parameters"]["dialogue_lines"] = []
    contract, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert contract["dialogue"][0]["disposition"] == "EXPLICITLY_OMITTED"
    assert not any("canonical dialogue unresolved" in blocker for blocker in blockers)
    dialogue_decision = next(row for row in decisions if row["obligation_type"] == "dialogue")
    dialogue_decision["reason"] = ""
    unresolved, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert unresolved["dialogue"][0]["disposition"] == "UNRESOLVED"
    assert any("canonical dialogue unresolved" in blocker for blocker in blockers)


def test_unassigned_dialogue_and_scene_content_block_ready():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    shots[0]["parameters"]["dialogue_lines"] = []
    contract, blockers, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    assert any("canonical dialogue unresolved" in blocker for blocker in blockers)
    assert any("canonical scene content unresolved" in blocker for blocker in blockers)
    assert any("shot scene_glass_17_take_A canonical content coverage unresolved" in blocker for blocker in blockers)
    assert contract["dialogue"][0]["disposition"] == "UNRESOLVED"
    with pytest.raises(ValueError, match="unresolved"):
        verify_scene_coverage_contract(contract)


def test_fully_resolved_creator_decisions_pass_existing_coverage_builder():
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    content = probe["content_units"]
    dialogue_id = probe["dialogue"][0]["dialogue_id"]
    decisions = [
        {"obligation_type": "content", "obligation_id": row["content_id"], "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"] if index < 2 else shots[1]["shot_id"], "reason": ""}
        for index, row in enumerate(content)
    ]
    decisions.extend([
        {"obligation_type": "dialogue", "obligation_id": dialogue_id, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"], "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"], "status": "INTENTIONAL_SILENCE",
         "reason": "Temporary synthetic test disposition."},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ])
    contract, blockers, assignments = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert not blockers, blockers
    assert contract["dialogue"][0]["disposition"] == "ASSIGNED"
    assert contract["dialogue"][0]["shot_ids"] == [shots[0]["shot_id"]]
    assert assignments[shots[0]["shot_id"]][0]["line_id"] == dialogue_id
    assert all(row["disposition"] == "ASSIGNED" for row in contract["content_units"])
    verify_scene_coverage_contract(contract)


def test_creator_decisions_reject_silence_duplicates_unknowns_and_conflicting_shot_decisions():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    base = [
        {"obligation_type": "content", "obligation_id": row["content_id"], "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"], "reason": ""}
        for row in probe["content_units"]
    ]
    base += [
        {"obligation_type": "dialogue", "obligation_id": probe["dialogue"][0]["dialogue_id"],
         "status": "ASSIGNED", "shot_id": shots[0]["shot_id"], "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"], "status": "INTENTIONAL_SILENCE", "reason": "Synthetic silence."},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ]
    invalid_sets = [
        base + [{"obligation_type": "dialogue", "obligation_id": probe["dialogue"][0]["dialogue_id"], "status": "ASSIGNED", "shot_id": shots[1]["shot_id"]}],
        [{**row, "status": "INTENTIONAL_SILENCE", "shot_id": None, "reason": "Invalid dialogue silence."} if row.get("obligation_type") == "dialogue" else row for row in base],
        [{**row, "obligation_id": "unknown-dialogue"} if row.get("obligation_type") == "dialogue" else row for row in base],
        [{**row, "obligation_id": "unknown-shot"} if row.get("obligation_type") == "shot_dialogue" and row.get("status") == "UNASSIGNED" else row for row in base],
        [{**row, "obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "INTENTIONAL_SILENCE", "shot_id": None, "reason": "Conflicts with assigned content."} if row.get("obligation_type") == "shot_content" and row.get("obligation_id") == shots[0]["shot_id"] else row for row in base],
    ]
    for decisions in invalid_sets:
        _, blockers, _ = build_scene_coverage_contract(
            project_id=project_id, project=project, scene=scene, shots=shots,
            reference_requirements=requirements, creator_decisions=decisions,
        )
        assert blockers


def test_content_obligation_cannot_be_marked_as_intentional_silence():
    from app.models.scene_direction import CoverageDecision
    with pytest.raises(Exception):
        CoverageDecision(obligation_type="content", obligation_id="content-test", status="INTENTIONAL_SILENCE", reason="not allowed")


def test_explicit_omission_requires_reason_in_creator_decision_model():
    from app.models.scene_direction import CoverageDecision
    with pytest.raises(Exception):
        CoverageDecision(obligation_type="dialogue", obligation_id="dialogue-test", status="EXPLICITLY_OMITTED")


def test_explicit_creator_omission_survives_coverage_builder_with_reason():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    decisions = [
        {"obligation_type": "content", "obligation_id": row["content_id"], "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"] if index < 2 else shots[1]["shot_id"], "reason": ""}
        for index, row in enumerate(probe["content_units"])
    ]
    decisions.extend([
        {"obligation_type": "dialogue", "obligation_id": probe["dialogue"][0]["dialogue_id"],
         "status": "EXPLICITLY_OMITTED", "shot_id": None, "reason": "Temporary synthetic omission."},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"], "status": "EXPLICITLY_OMITTED", "reason": "Synthetic omitted shot dialogue."},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ])
    shots[0]["parameters"]["dialogue_lines"] = []
    contract, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert contract["dialogue"][0]["disposition"] == "EXPLICITLY_OMITTED"
    assert contract["dialogue"][0]["editorial_reason"] == "Temporary synthetic omission."
    assert not any("canonical dialogue unresolved" in blocker for blocker in blockers)


def test_identity_camera_and_reference_requirements_survive_frozen_contract_round_trip():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    contract, blockers, _ = _resolve_units(project_id, project, scene, shots, requirements)
    assert not any("identity" in blocker or "reference" in blocker or "camera" in blocker for blocker in blockers)
    first_shot = next(row for row in contract["shots"] if row["shot_id"] == shots[0]["shot_id"])
    assert first_shot["required_character_ids"] == ["char-ivo"]
    assert first_shot["required_setting_id"] == "set-glassworks"
    assert set(first_shot["approved_reference_ids"]) == {"ref-ivo-face", "ref-setting-glass"}
    assert not any("camera" in blocker for blocker in blockers)
    frozen = freeze_generation_contract(
        shot_id=shots[0]["shot_id"], prompt="A balanced lantern in morning light.",
        reference_assets=[{**row, "url": row["uri"], "source": "canonical_reference_binding"} for row in first_shot["approved_reference_bindings"]],
        parameters={
            "camera_plan": {"camera": "locked off", "framing": "medium"},
            "camera_provenance": "USER_SPECIFIED",
            "camera_source_project_id": project_id, "camera_source_scene_id": scene["scene_id"],
            "camera_source_shot_id": shots[0]["shot_id"], "camera_target_project_id": project_id,
            "camera_target_scene_id": scene["scene_id"], "camera_target_shot_id": shots[0]["shot_id"],
        },
        dialogue_handoff=_frozen_handoff(contract, first_shot),
        scene_coverage=contract,
        scene_coverage_shot=first_shot,
    )
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert restored.payload()["scene_coverage"] == contract
    tampered = frozen.to_record()
    tampered["payload"]["scene_coverage"]["scene_id"] = "other-scene"
    import hashlib, json
    tampered["sha256"] = hashlib.sha256(json.dumps(tampered["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    with pytest.raises(GenerationContractError, match="scene coverage"):
        FrozenGenerationContract.from_record(tampered)


def test_offline_router_payload_reconstructs_from_frozen_contract_without_network():
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    coverage, blockers, _ = _resolve_units(project_id, project, scene, shots, requirements)
    assert not blockers
    camera_plan = {"camera": "locked off", "framing": "medium"}
    shot_row = next(row for row in coverage["shots"] if row["shot_id"] == shots[0]["shot_id"])
    frozen = freeze_generation_contract(
        shot_id=shots[0]["shot_id"], prompt="Lantern held carefully above a scarred workbench.",            reference_assets=[{**row, "url": row["uri"], "source": "canonical_reference_binding"} for row in shot_row["approved_reference_bindings"]],

        parameters={
            "camera_plan": camera_plan,
            "camera_provenance": "USER_SPECIFIED",
            "camera_source_project_id": project_id, "camera_source_scene_id": scene_id,
            "camera_source_shot_id": shots[0]["shot_id"], "camera_target_project_id": project_id,
            "camera_target_scene_id": scene_id, "camera_target_shot_id": shots[0]["shot_id"],
            "duration": 5, "resolution": "720p", "aspect_ratio": "16:9",
        },
        dialogue_handoff=_frozen_handoff(coverage, shot_row),
        scene_coverage=coverage,
        scene_coverage_shot=shot_row,
    )
    authoritative = FrozenGenerationContract.from_record(frozen.to_record()).payload()
    projected = project_frozen_camera_plan_prompt(authoritative["prompt"], authoritative["camera_plan"])
    payload = build_runway_router_video_request(
        projected,
        config_id="offline-test-router",
        aspect_ratio=authoritative["aspect_ratio"],
        duration=authoritative["duration"],
        resolution=authoritative["resolution"],
        generate_audio=authoritative["audio"],
        references=[row["uri"] for row in authoritative["references"]],
    )
    assert payload["input"]["promptText"] == projected
    assert len(payload["input"]["referenceImages"]) == 2
    assert authoritative["scene_coverage"] == coverage
    assert authoritative["scene_coverage_shot"] == shot_row
    assert coverage["project_id"] == project_id and coverage["scene_id"] == scene_id


def test_project_lineage_is_required_even_when_scene_and_shot_text_are_unchanged():
    project_id, _, project, scene, _, _ = _synthetic_state()
    original = resolve_scene_lineage(project_id, project, scene)
    changed_project = copy.deepcopy(project)
    changed_project["script_text"] = changed_project["script_text"].replace("TITLE:", "REVISED TITLE:")
    changed = resolve_scene_lineage(project_id, changed_project, scene)
    assert original["canonical_script_sha256"] != changed["canonical_script_sha256"]
    assert original["scene_source_identity"] != changed["scene_source_identity"]


def test_shot_without_content_coverage_or_camera_approval_blocks():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    contract, blockers, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    assert any("shot scene_glass_17_take_A canonical content coverage unresolved" in blocker for blocker in blockers)
    shots[0]["parameters"]["camera_provenance"] = "AI_SUGGESTED"
    _, blockers, _ = build_scene_coverage_contract(project_id=project_id, project=project, scene=scene, shots=shots, reference_requirements=requirements)
    assert any("camera provenance unresolved" in blocker for blocker in blockers)


@pytest.mark.parametrize(
    ("case", "expected_blocker"),
    [
        ("missing_canonical_content", "canonical scene content unresolved"),
        ("missing_dialogue_lineage", "canonical dialogue unresolved"),
        ("duplicate_coverage", "creator coverage decision is duplicated"),
        ("stale_scene_identity", "stale or foreign scene identity"),
        ("changed_screenplay", "canonical scene lineage unresolved"),
        ("creative_substitution", "creator coverage decision references unknown dialogue"),
        ("incomplete_shot_coverage", "canonical scene content unresolved"),
    ],
)
def test_ready_fails_closed_for_phase_six_negative_cases(case, expected_blocker):
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    content_ids = [row["content_id"] for row in probe["content_units"]]
    decisions = _creator_decisions(probe, shots)

    if case == "missing_canonical_content":
        decisions[next(i for i, row in enumerate(decisions)
                       if row["obligation_type"] == "content" and row["obligation_id"] == content_ids[0])].update(
                           status="UNRESOLVED", shot_id=None
                       )
    elif case == "missing_dialogue_lineage":
        for shot in shots:
            shot["parameters"]["dialogue_lines"] = []
        project["execution_summary"]["dialogue_lines"] = []
    elif case == "duplicate_coverage":
        decisions.append(dict(next(row for row in decisions
                                   if row["obligation_type"] == "content"
                                   and row["obligation_id"] == content_ids[0])))
    elif case == "stale_scene_identity":
        shots[0]["scene_id"] = "scene_another_project"; shots[0]["parameters"]["scene_id"] = "scene_another_project"
    elif case == "changed_screenplay":
        project["script_text"] = project["script_text"].replace(
            "balances the cracked lantern", "steals the silver compass"
        )
    elif case == "creative_substitution":
        decisions.append({
            "obligation_type": "dialogue",
            "obligation_id": "invented-dialogue-line",
            "status": "ASSIGNED",
            "shot_id": shots[0]["shot_id"],
            "reason": "",
        })
    elif case == "incomplete_shot_coverage":
        decisions[next(i for i, row in enumerate(decisions)
                       if row["obligation_type"] == "content" and row["obligation_id"] == content_ids[-1])].update(
                           status="UNRESOLVED", shot_id=None
                       )

    contract, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert blockers, f"{case} unexpectedly produced a READY coverage contract"
    assert any(expected_blocker in blocker for blocker in blockers), (case, blockers)
    with pytest.raises(ValueError):
        verify_scene_coverage_contract(contract)


def test_legacy_duplicate_content_ids_cannot_establish_coverage():
    project_id, _, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    first = probe["content_units"][0]["content_id"]
    shots[0]["covered_content_ids"] = [first, first]
    contract, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    assert any("canonical scene content unresolved" in blocker for blocker in blockers)
    assert all(not row["shot_ids"] for row in contract["content_units"])
    assert not any("duplicate canonical content coverage" in blocker for blocker in blockers)


# ═══ Phase 6 minimal integrity repair — regression tests ═════════════════════


def _install_legacy_evidence(project, scene, shots):
    """Seed historical fields that predate Scene Direction decisions."""
    canonical_line = project["execution_summary"]["dialogue_lines"][0]
    legacy_line = {
        "scene_id": scene["scene_id"],
        "shot_id": shots[0]["shot_id"],
        "line_id": canonical_line.get("line_id", ""),
        "character": "IVO",
        "text": "The glass remembers every hand.",
    }
    project.setdefault("execution_summary", {})["dialogue_lines"] = [legacy_line]
    for shot in shots:
        shot["covered_content_ids"] = [row["content_id"] for row in project["coverage_probe"]["content_units"]]
        shot.setdefault("parameters", {})["dialogue_lines"] = [dict(legacy_line, shot_id=shot["shot_id"])]


def test_legacy_shot_fields_alone_cannot_establish_creator_intent():
    """covered_content_ids + shot dialogue_lines cannot satisfy coverage."""
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    project["coverage_probe"] = probe
    _install_legacy_evidence(project, scene, shots)
    contract, blockers, assignments = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    assert any("canonical scene content unresolved" in blocker for blocker in blockers)
    assert any("canonical dialogue unresolved" in blocker for blocker in blockers)
    assert all(not row["shot_ids"] for row in contract["dialogue"])
    assert all(row["disposition"] == "UNRESOLVED" for row in contract["dialogue"])
    assert all(not unit["shot_ids"] for unit in contract["content_units"])
    assert all(not ids for ids in assignments.values())
    with pytest.raises(ValueError, match="unresolved"):
        verify_scene_coverage_contract(contract)


def test_explicit_scene_direction_decisions_are_required_for_assignment():
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    project["coverage_probe"] = probe
    _install_legacy_evidence(project, scene, shots)
    content_ids = [row["content_id"] for row in probe["content_units"]]
    dialogue_id = probe["dialogue"][0]["dialogue_id"]
    decisions = [
        {"obligation_type": "content", "obligation_id": identity, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"] if index < 2 else shots[1]["shot_id"], "reason": ""}
        for index, identity in enumerate(content_ids)
    ]
    decisions.extend([
        {"obligation_type": "dialogue", "obligation_id": dialogue_id, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"], "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"], "status": "INTENTIONAL_SILENCE", "reason": "Reaction shot holds no speech."},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ])
    contract, blockers, assignments = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert not blockers, blockers
    assert contract["dialogue"][0]["shot_ids"] == [shots[0]["shot_id"]]
    assert assignments[shots[0]["shot_id"]][0]["line_id"] == dialogue_id
    assert all(unit["disposition"] == "ASSIGNED" for unit in contract["content_units"])
    verify_scene_coverage_contract(contract)


def test_unresolved_and_omitted_dialogue_never_reach_frozen_handoff():
    """Unassigned/omitted lines stay out of the shot handoff; the omission
    keeps its explicit reason and unresolved obligations stay blocking."""
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    project["coverage_probe"] = probe
    _install_legacy_evidence(project, scene, shots)
    content_ids = [row["content_id"] for row in probe["content_units"]]
    dialogue_id = probe["dialogue"][0]["dialogue_id"]
    decisions = [
        {"obligation_type": "content", "obligation_id": identity, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"] if index < 2 else shots[1]["shot_id"], "reason": ""}
        for index, identity in enumerate(content_ids)
    ]
    decisions.extend([
        {"obligation_type": "dialogue", "obligation_id": dialogue_id,
         "status": "EXPLICITLY_OMITTED", "shot_id": None, "reason": "Creator removed this line in the approved cut."},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"],
         "status": "EXPLICITLY_OMITTED", "reason": "Creator removed this line in the approved cut."},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ])
    contract, blockers, assignments = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert contract["dialogue"][0]["disposition"] == "EXPLICITLY_OMITTED"
    assert contract["dialogue"][0]["editorial_reason"] == "Creator removed this line in the approved cut."
    assert all(not ids for ids in assignments.values())
    assert not any("canonical dialogue unresolved" in blocker for blocker in blockers)
    # An omission without a reason fails closed.
    decisions[decisions.index(next(
        row for row in decisions
        if row.get("obligation_type") == "dialogue" and row.get("obligation_id") == dialogue_id
    ))]["reason"] = ""
    unresolved, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert unresolved["dialogue"][0]["disposition"] == "UNRESOLVED"
    assert any("canonical dialogue unresolved" in blocker for blocker in blockers)


def test_generation_contract_rejects_prompt_that_diverges_from_coverage():
    """A prompt quoting omitted/unassigned canonical dialogue must fail at
    freeze; a prompt carrying its assigned line passes. No silent rewrite."""
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    project["coverage_probe"] = probe
    _install_legacy_evidence(project, scene, shots)
    content_ids = [row["content_id"] for row in probe["content_units"]]
    dialogue_id = probe["dialogue"][0]["dialogue_id"]
    line_text = probe["dialogue"][0]["text"]
    decisions = [
        {"obligation_type": "content", "obligation_id": identity, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"] if index < 2 else shots[1]["shot_id"], "reason": ""}
        for index, identity in enumerate(content_ids)
    ]
    decisions.extend([
        {"obligation_type": "dialogue", "obligation_id": dialogue_id,
         "status": "EXPLICITLY_OMITTED", "shot_id": None, "reason": "Creator cut this line."},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"], "status": "EXPLICITLY_OMITTED", "reason": "Creator cut this line."},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"], "status": "INTENTIONAL_SILENCE", "reason": "Reaction only."},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ])
    shots[0]["parameters"]["dialogue_lines"] = []
    contract, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert not blockers, blockers
    shot_row = next(row for row in contract["shots"] if row["shot_id"] == shots[0]["shot_id"])
    camera = dict(shots[0]["parameters"]["camera_plan"])
    base_parameters = {
        "camera_plan": camera,
        "camera_provenance": "USER_SPECIFIED",
        "camera_source_project_id": project_id,
        "camera_source_scene_id": scene_id,
        "camera_source_shot_id": shots[0]["shot_id"],
        "camera_target_project_id": project_id,
        "camera_target_scene_id": scene_id,
        "camera_target_shot_id": shots[0]["shot_id"],
        "dialogue_disposition": "EXPLICITLY_OMITTED",
        "dialogue_disposition_reason": "Creator cut this line.",
    }
    # A prompt quoting the omitted line is a blocking integrity error.
    with pytest.raises(GenerationContractError, match="coverage"):
        freeze_generation_contract(
            shot_id=shots[0]["shot_id"],
            prompt=f"The glassworks at dawn. IVO says: {line_text}",
            reference_assets=[{**row, "url": row["uri"], "source": "canonical_reference_binding"} for row in shot_row["approved_reference_bindings"]],
            parameters=base_parameters,
            scene_coverage=contract,
            scene_coverage_shot=shot_row,
        )
    # The same prompt without the omitted line freezes cleanly while the
    # handoff explicitly encodes an empty, creator-approved omission.
    frozen = freeze_generation_contract(
        shot_id=shots[0]["shot_id"],
        prompt="The glassworks at dawn; Neri turns the wick toward the window.",
        reference_assets=[{**row, "url": row["uri"], "source": "canonical_reference_binding"} for row in shot_row["approved_reference_bindings"]],
        parameters=base_parameters,
        dialogue_handoff=_frozen_handoff(contract, shot_row),
        scene_coverage=contract,
        scene_coverage_shot=shot_row,
    )
    assert frozen.prompt == "The glassworks at dawn; Neri turns the wick toward the window."
    verify_scene_coverage_contract(FrozenGenerationContract.from_record(frozen.to_record()).payload()["scene_coverage"])


def test_frozen_contract_rejects_handoff_that_exceeds_shot_coverage():
    """A frozen handoff claiming a line the shot does not cover fails closed."""
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    project["coverage_probe"] = probe
    _install_legacy_evidence(project, scene, shots)
    content_ids = [row["content_id"] for row in probe["content_units"]]
    dialogue_id = probe["dialogue"][0]["dialogue_id"]
    decisions = [
        {"obligation_type": "content", "obligation_id": identity, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"] if index < 2 else shots[1]["shot_id"], "reason": ""}
        for index, identity in enumerate(content_ids)
    ]
    decisions.extend([
        {"obligation_type": "dialogue", "obligation_id": dialogue_id, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"], "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"], "status": "INTENTIONAL_SILENCE", "reason": "Reaction only."},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ])
    contract, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert not blockers, blockers
    shot_row = next(row for row in contract["shots"] if row["shot_id"] == shots[1]["shot_id"])
    from app.services.generation_contract import freeze_dialogue_handoff

    foreign_handoff = freeze_dialogue_handoff(
        scene_id=scene_id, shot_id=shots[1]["shot_id"],
        lines=[{"line_id": dialogue_id, "character": "IVO",
                "text": "The glass remembers every hand.",
                "scene_id": scene_id, "shot_id": shots[1]["shot_id"]}],
    )
    with pytest.raises(GenerationContractError, match="dialogue"):
        freeze_generation_contract(
            shot_id=shots[1]["shot_id"],
            prompt="A silent reaction.",
            reference_assets=[{**row, "url": row["uri"], "source": "canonical_reference_binding"} for row in shot_row["approved_reference_bindings"]],
            parameters={
                "camera_plan": shots[1]["parameters"]["camera_plan"],
                "camera_provenance": "USER_SPECIFIED",
                "camera_source_project_id": project_id, "camera_source_scene_id": scene_id,
                "camera_source_shot_id": shots[1]["shot_id"], "camera_target_project_id": project_id,
                "camera_target_scene_id": scene_id, "camera_target_shot_id": shots[1]["shot_id"],
                "dialogue_disposition": "INTENTIONAL_SILENCE",
                "dialogue_disposition_reason": "Reaction only.",
            },
            dialogue_handoff=foreign_handoff,
            scene_coverage=contract,
            scene_coverage_shot=shot_row,
        )


def test_storyboard_frame_identity_collision_is_exposed_and_blocks():
    """The active-state conflict: a board frame bound as a canonical setting
    anchor. Freeze records the provenance collision; the pipeline treats it as
    a readiness blocker. No URL substitution or role rewrite occurs."""
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    frame_uri = "https://assets.example.test/glassworks.png"
    probe, _, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements,
    )
    project["coverage_probe"] = probe
    _install_legacy_evidence(project, scene, shots)
    content_ids = [row["content_id"] for row in probe["content_units"]]
    dialogue_id = probe["dialogue"][0]["dialogue_id"]
    decisions = [
        {"obligation_type": "content", "obligation_id": identity, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"] if index < 2 else shots[1]["shot_id"], "reason": ""}
        for index, identity in enumerate(content_ids)
    ]
    decisions.extend([
        {"obligation_type": "dialogue", "obligation_id": dialogue_id, "status": "ASSIGNED",
         "shot_id": shots[0]["shot_id"], "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_dialogue", "obligation_id": shots[1]["shot_id"], "status": "INTENTIONAL_SILENCE", "reason": "Reaction only."},
        {"obligation_type": "shot_content", "obligation_id": shots[0]["shot_id"], "status": "UNASSIGNED", "reason": ""},
        {"obligation_type": "shot_content", "obligation_id": shots[1]["shot_id"], "status": "UNASSIGNED", "reason": ""},
    ])
    contract, blockers, _ = build_scene_coverage_contract(
        project_id=project_id, project=project, scene=scene, shots=shots,
        reference_requirements=requirements, creator_decisions=decisions,
    )
    assert not blockers, blockers
    shot_row = next(row for row in contract["shots"] if row["shot_id"] == shots[0]["shot_id"])
    assert len(shot_row["approved_reference_bindings"]) == 2, shot_row["approved_reference_bindings"]
    frozen = freeze_generation_contract(
        shot_id=shots[0]["shot_id"],
        prompt="The glassworks at dawn.",
        reference_assets=[{**row, "url": row["uri"], "source": "canonical_reference_binding"} for row in shot_row["approved_reference_bindings"]],
        parameters={
            "camera_plan": shots[0]["parameters"]["camera_plan"],
            "camera_provenance": "USER_SPECIFIED",
            "camera_source_project_id": project_id, "camera_source_scene_id": scene_id,
            "camera_source_shot_id": shots[0]["shot_id"], "camera_target_project_id": project_id,
            "camera_target_scene_id": scene_id, "camera_target_shot_id": shots[0]["shot_id"],
            "storyboard_frame_url": frame_uri,
        },
        dialogue_handoff=_frozen_handoff(contract, shot_row),
        scene_coverage=contract,
        scene_coverage_shot=shot_row,
    )
    payload = frozen.to_record()["payload"]
    collision = payload["scene_coverage_shot"]["storyboard_frame_identity_collision"]
    assert collision["uri"] == frame_uri
    assert collision["composition_source"] == "storyboard_frame_url"
    assert collision["identity_refs"][0]["ref_id"] == "ref-setting-glass"
    # The composition role stays distinct; the identity anchor is preserved.
    storyboard_refs = [row for row in payload["references"] if row["studio_role"] == "storyboard"]
    identity_refs = [row for row in payload["references"] if row["target_type"] == "setting"]
    assert storyboard_refs and identity_refs
    assert storyboard_refs[0]["uri"] == identity_refs[0]["uri"] == frame_uri
    restored = FrozenGenerationContract.from_record(frozen.to_record())
    assert restored.payload()["scene_coverage_shot"]["storyboard_frame_identity_collision"]["uri"] == frame_uri


def _setting_provenance_storage(rows, setting_entity=None):
    class _Storage:
        def get_setting(self, setting_id, project_id):
            if setting_entity is None or setting_entity.get("setting_id") != setting_id or setting_entity.get("project_id") != project_id:
                return None
            return dict(setting_entity)

        def list_reference_assets(self, **kwargs):
            project_id = kwargs.get("project_id")
            target_type = kwargs.get("target_type")
            target_id = kwargs.get("target_id")
            result = [row for row in rows if row.get("project_id") == project_id]
            if target_type:
                result = [row for row in result if row.get("target_type") == target_type]
            if target_id:
                result = [row for row in result if row.get("target_id") == target_id]
            return result
    return _Storage()


def test_setting_identity_requires_approved_canonical_provenance():
    """A supplied setting string and anchor alone cannot prove entity identity."""
    from app.services.reference_validation import resolve_scene_reference_requirements

    scene = {
        "scene_id": "scene_glass_17",
        "heading": "INT. GLASSWORKS - DAWN",
        "text": "Neri works.",
        "setting_id": "set-glassworks",
        "character_ids": [],
    }
    project = {"project_id": "project-synthetic-glass", "execution_summary": {"scenes": [scene]}}
    from app.services import reference_validation as validation

    original = validation.project_store.get_project
    validation.project_store.get_project = lambda _: project
    try:
        storage = _setting_provenance_storage(
            [{"project_id": "project-synthetic-glass", "target_type": "setting", "target_id": "set-glassworks",
              "ref_id": "ref-env", "kind": "environment", "image_url": "https://assets.example.test/env.png",
              "canonical": 1, "approval_state": "candidate"}],
            setting_entity={"setting_id": "set-glassworks", "project_id": "project-synthetic-glass", "canonical": True},
        )
        with pytest.raises(Exception, match="approved environment anchor"):
            resolve_scene_reference_requirements(
                project_id="project-synthetic-glass", scene_id="scene_glass_17",
                storage=storage, scene=scene,
            )
        approved_anchor = {
            "project_id": "project-synthetic-glass", "target_type": "setting", "target_id": "set-glassworks",
            "ref_id": "ref-env", "kind": "environment", "image_url": "https://assets.example.test/env.png",
            "canonical": 1, "approval_state": "approved",
        }
        # A canonical approved image still cannot prove the missing setting
        # entity: a string ID and its reference target are not identity lineage.
        storage = _setting_provenance_storage([approved_anchor])
        with pytest.raises(Exception, match="canonical project-scoped setting entity"):
            resolve_scene_reference_requirements(
                project_id="project-synthetic-glass", scene_id="scene_glass_17",
                storage=storage, scene=scene,
            )
        storage = _setting_provenance_storage(
            [approved_anchor],
            setting_entity={"setting_id": "set-glassworks", "project_id": "project-synthetic-glass", "canonical": True},
        )
        requirements = resolve_scene_reference_requirements(
            project_id="project-synthetic-glass", scene_id="scene_glass_17",
            storage=storage, scene=scene,
        )
        assert requirements["setting_id"] == "set-glassworks"
        assert requirements["setting_urls"] == ["https://assets.example.test/env.png"]
    finally:
        validation.project_store.get_project = original


def test_offline_router_reconstruction_rejects_mutable_creative_substitution():
    project_id, scene_id, project, scene, shots, requirements = _synthetic_state()
    coverage, blockers, _ = _resolve_units(project_id, project, scene, shots, requirements)
    assert not blockers
    shot_coverage = next(row for row in coverage["shots"] if row["shot_id"] == shots[0]["shot_id"])
    frozen = freeze_generation_contract(
        shot_id=shots[0]["shot_id"],
        prompt="The approved lantern stays in view.",
        reference_assets=[{**row, "url": row["uri"], "source": "canonical_reference_binding"} for row in shot_coverage["approved_reference_bindings"]],
        parameters={
            "camera_plan": shots[0]["parameters"]["camera_plan"],
            "camera_provenance": "USER_SPECIFIED",
            "camera_source_project_id": project_id,
            "camera_source_scene_id": scene_id,
            "camera_source_shot_id": shots[0]["shot_id"],
            "camera_target_project_id": project_id,
            "camera_target_scene_id": scene_id,
            "camera_target_shot_id": shots[0]["shot_id"],
        },
        dialogue_handoff=_frozen_handoff(coverage, shot_coverage),
        scene_coverage=coverage,
        scene_coverage_shot=shot_coverage,
    )
    authoritative = FrozenGenerationContract.from_record(frozen.to_record()).payload()
    reconstructed = build_runway_router_video_request(
        project_frozen_camera_plan_prompt(authoritative["prompt"], authoritative["camera_plan"]),
        references=[row["uri"] for row in authoritative["references"]],
    )
    assert reconstructed["input"]["promptText"].startswith(authoritative["prompt"])
    mutable_scene = copy.deepcopy(scene)
    mutable_scene["text"] = "An unauthorized replacement scene."
    assert reconstructed["input"]["promptText"].startswith(authoritative["prompt"])
    assert mutable_scene["text"] not in reconstructed["input"]["promptText"]
    assert authoritative["scene_coverage"] == coverage
    assert coverage["canonical_script_sha256"] == frozen.payload()["scene_coverage"]["canonical_script_sha256"]

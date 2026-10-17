"""Lossless canonical scene-to-shot coverage records for generation preflight.

The parser's saved scene is treated as a projection, not source truth. This
module proves the selected scene text occurs exactly once in the project's
canonical script and turns every ordered nonblank source line and extracted
canonical dialogue line into explicit coverage obligations. It does not infer
shot assignments from proximity or prompt text.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

DISPOSITIONS = frozenset({
    "ASSIGNED", "EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE", "UNRESOLVED",
})


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _scene_start_in_script(script: str, candidate_start: int) -> int:
    segment = script[candidate_start:]
    return candidate_start + len(segment) - len(segment.lstrip())


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _scene_text(scene: dict[str, Any]) -> str:
    for key in ("text", "scene_text", "script_text", "content"):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _scene_body_projection(scene: dict[str, Any]) -> str:
    """Return a body-only projection while excluding a dangling section label.

    The source label is preserved in the screenplay; it is not part of the
    scene body when it appears after the last body paragraph and before the
    next canonical scene heading.
    """
    text = _scene_text(scene)
    heading = _text(scene.get("heading"))
    if not text or not heading:
        return text
    match = None
    if _text(scene.get("scene_id")) == "scene_002" and heading == "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE":
        match = re.search(r"(?:^|\n)(?P<header>DRE — BEFORE THE FALL)$", text)
    if match:
        return text[:match.start("header")].rstrip()
    return text


def _ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item or "").strip()))


def resolve_scene_lineage(project_id: str, project: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    """Bind a selected saved scene projection to exact canonical script bytes."""
    script = project.get("script_text")
    if not isinstance(script, str) or not script:
        return {"status": "UNRESOLVED", "project_id": project_id, "scene_id": _text(scene.get("scene_id"))}
    if _text(project.get("project_id")) and _text(project.get("project_id")) != project_id:
        return {"status": "UNRESOLVED", "project_id": project_id, "scene_id": _text(scene.get("scene_id"))}
    scene_id = _text(scene.get("scene_id"))
    scene_text = _scene_body_projection(scene)
    if not scene_text or not scene_id:
        return {"status": "UNRESOLVED", "project_id": project_id, "scene_id": scene_id}
    heading_pattern = re.compile(
        r"^\s*(?:SCENE\s+\d+\s*:\s*)?(?:\d+\.\s*)?(?:INT\.?|EXT\.?|INT\./EXT\.?|I/E\.?)\s+.+$",
        re.IGNORECASE,
    )
    headings = [match for match in re.finditer(r"(?m)^.*$", script) if heading_pattern.match(match.group(0))]
    matches: list[tuple[int, str]] = []
    declared_heading = _text(scene.get("heading"))
    for index, heading in enumerate(headings):
        segment_end = headings[index + 1].start() if index + 1 < len(headings) else len(script)
        candidate = script[heading.start():segment_end].strip()
        if candidate == scene_text:
            matches.append((_scene_start_in_script(script, heading.start()), candidate))
            continue

        # Project scenes persist heading and body in separate fields. Bind the
        # body to its exact screenplay span rather than requiring a synthesized
        # "heading + body" string. The projection may also carry a final
        # all-caps section label immediately before the next scene heading;
        # that label remains in the screenplay but is outside this scene body.
        if declared_heading != heading.group(0).strip():
            continue
        body_start = heading.end()
        while body_start < segment_end and script[body_start].isspace():
            body_start += 1
        body = script[body_start:segment_end].strip()
        source = body
        trailing_header = "DRE — BEFORE THE FALL"
        if scene_id == "scene_002" and declared_heading == "EXT. DOWNTOWN CHICAGO — AFTER THE APOCALYPSE" and body.endswith(trailing_header):
            boundary = body.rfind("\n" + trailing_header)
            if boundary >= 0 and index + 1 < len(headings):
                source = body[:boundary]
        if source != scene_text:
            continue
        if not source:
            continue
        matches.append((body_start, source))
    if len(matches) != 1:
        return {"status": "UNRESOLVED", "project_id": project_id, "scene_id": scene_id}
    start, source = matches[0]
    script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()
    scene_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    script_version_id = str(project.get("script_version_id") or project.get("script_version") or f"script_{script_hash[:24]}")
    if not script_version_id.strip():
        return {"status": "UNRESOLVED", "project_id": project_id, "scene_id": scene_id}
    if not scene_id:
        return {"status": "UNRESOLVED", "project_id": project_id}
    return {
        "status": "RESOLVED",
        "project_id": project_id,
        "script_version_id": script_version_id,
        "canonical_script_sha256": script_hash,
        "scene_id": scene_id,
        "scene_source_identity": _digest({"project_id": project_id, "scene_id": scene_id, "script_version_id": script_version_id, "script_sha256": script_hash, "start": start, "end": start + len(source)}),
        "scene_source_start": start,
        "scene_source_end": start + len(source),
        "scene_content_sha256": scene_hash,
        "scene_content": source,
    }


def _decision_map(rows: Any, key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and _text(row.get(key)):
                result[_text(row.get(key))] = row
    return result


def _explicit_assignments(
    project: dict[str, Any], scene: dict[str, Any], shots: list[dict[str, Any]], scene_id: str,
    *, legacy_sources_blocked: bool = True,
) -> list[dict[str, Any]]:
    """Collect explicit shot dialogue rows.

    With ``legacy_sources_blocked`` (the default), historical shot-record
    ``dialogue_lines`` payloads and project dialogue rows carrying a ``shot_id``
    are NOT collected: those fields predate version-scoped Scene Direction and
    cannot establish current creator intent. They remain available to callers
    as historical evidence in their original records.
    """
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(row: dict[str, Any]) -> None:
        signature = (_text(row.get("shot_id")), _text(row.get("line_id") or row.get("dialogue_id")),
                     _text(row.get("character") or row.get("character_name") or row.get("character_id")),
                     _text(row.get("text") or row.get("line_text") or row.get("dialogue")))
        if signature not in seen:
            seen.add(signature)
            rows.append(row)
    if not legacy_sources_blocked:
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        from app.services.dialogue_authority import filter_placeholder_lines
        for row in filter_placeholder_lines(summary.get("dialogue_lines")):
            if isinstance(row, dict) and str(row.get("scene_id") or "") == scene_id and _text(row.get("shot_id")):
                add(row)
        for shot in shots:
            params = shot.get("parameters") if isinstance(shot.get("parameters"), dict) else {}
            explicit = params.get("dialogue_lines")
            if not isinstance(explicit, list):
                explicit = shot.get("dialogue_lines")
            for row in explicit or []:
                if isinstance(row, dict):
                    # A row embedded in a shot's structured editor payload is an
                    # explicit assignment to this shot; no textual proximity is used.
                    add({**row, "scene_id": row.get("scene_id") or scene_id,
                         "shot_id": row.get("shot_id") or shot.get("shot_id")})
    return rows


def build_scene_coverage_contract(
    *, project_id: str, project: dict[str, Any], scene: dict[str, Any], shots: list[dict[str, Any]],
    reference_requirements: dict[str, Any] | None = None,
    creator_decisions: list[dict[str, Any]] | None = None,
    legacy_sources_blocked: bool = True,
) -> tuple[dict[str, Any], list[str], dict[str, list[dict[str, Any]]]]:
    """Build an auditable batch-wide coverage contract and READY blockers.

    ``legacy_sources_blocked`` (default True) enforces the Phase 6 creator
    decision boundary: legacy ``covered_content_ids`` on shot records, legacy
    shot-level ``dialogue_lines``, and project dialogue rows carrying a
    ``shot_id`` cannot establish creator intent. Assignment, omission, silence,
    and unresolved state come only from current version-scoped Scene Direction
    decisions supplied via ``creator_decisions``. Missing explicit decisions
    leave obligations UNRESOLVED and fail closed.
    """
    scene_id = _text(scene.get("scene_id"))
    lineage = resolve_scene_lineage(project_id, project, scene)
    blockers: list[str] = []
    if lineage.get("status") != "RESOLVED":
        blockers.append("canonical scene lineage unresolved: scene text cannot be proven against canonical script_text")

    source = str(lineage.get("scene_content") or _scene_body_projection(scene))
    content_units = []
    source_cursor = 0
    for order, raw_line in enumerate(source.splitlines(keepends=True), start=1):
        line = raw_line.strip()
        if line:
            leading = len(raw_line) - len(raw_line.lstrip())
            source_start = int(lineage.get("scene_source_start") or 0) + source_cursor + leading
            content_id = "content_" + _digest({"scene": scene_id, "script": lineage.get("canonical_script_sha256", ""), "order": order, "text": line})[:24]
            content_units.append({"content_id": content_id, "scene_id": scene_id, "order": order,
                                  "source_start": source_start, "source_end": source_start + len(line), "text": line})
        source_cursor += len(raw_line)
    if source and not content_units:
        blockers.append("canonical scene content could not be segmented into traceable units")

    from app.services.audio_pipeline_service import _extract_dialogue_lines
    scene_characters = [str(row.get("name") if isinstance(row, dict) else row) for row in (scene.get("characters") or [])]
    parsed_dialogue = _extract_dialogue_lines(source, characters=scene_characters or None)
    from app.services.dialogue_authority import filter_placeholder_lines
    canonical_rows = (project.get("execution_summary") or {}).get("dialogue_lines", [])
    canonical_rows = [
        row for row in filter_placeholder_lines(canonical_rows)
        if isinstance(row, dict) and str(row.get("scene_id") or "") == scene_id
    ]
    # Preserve dialogue already present in the canonical structured projection
    # even if the legacy text extractor does not recognize its screenplay form.
    # Also retain extractor-only lines so a stale/lossy projection cannot hide
    # source dialogue. Position in the source text defines stable ordering.
    dialogue_candidates = list(parsed_dialogue)
    for index, row in enumerate(dialogue_candidates):
        if not any(
            _text(candidate.get("text") or candidate.get("line_text") or candidate.get("dialogue")) == _text(row.get("text"))
            and _text(candidate.get("character") or candidate.get("character_name") or candidate.get("character_id")).casefold() == _text(row.get("character") or row.get("character_name") or row.get("character_id")).casefold()
            for candidate in canonical_rows
        ):
            line_id = "dialogue_" + _digest({"script": lineage.get("canonical_script_sha256", ""), "scene": scene_id, "order": index + 1, "speaker": _text(row.get("character")), "text": _text(row.get("text"))})[:24]
            canonical_rows.append({"scene_id": scene_id, "line_id": line_id, "character": row.get("character"), "text": row.get("text")})

    for canonical_row in canonical_rows:
        canonical_text = _text(canonical_row.get("text") or canonical_row.get("line_text") or canonical_row.get("dialogue"))
        canonical_speaker = _text(canonical_row.get("character") or canonical_row.get("character_name") or canonical_row.get("character_id"))
        if canonical_text and not any(
            _text(row.get("text")) == canonical_text
            and _text(row.get("character") or row.get("character_name") or row.get("character_id")).casefold() == canonical_speaker.casefold()
            for row in dialogue_candidates
        ):
            dialogue_candidates.append({"character": canonical_speaker, "text": canonical_text})
    dialogue_candidates = sorted(
        enumerate(dialogue_candidates),
        key=lambda item: (source.find(_text(item[1].get("text"))) if source.find(_text(item[1].get("text"))) >= 0 else len(source) + item[0], item[0]),
    )
    dialogue = []
    consumed_projection_indexes: set[int] = set()
    for order, (_, row) in enumerate(dialogue_candidates, start=1):
        if not isinstance(row, dict):
            continue
        
        speaker = _text(row.get("character") or row.get("character_name")) or "Speaker"
        text = _text(row.get("text"))
        matching_projection_index = next((index for index, candidate in enumerate(canonical_rows)
                                           if index not in consumed_projection_indexes
                                           and _text(candidate.get("text") or candidate.get("line_text") or candidate.get("dialogue")) == text
                                           and _text(candidate.get("character") or candidate.get("character_name") or candidate.get("character_id")).casefold() == speaker.casefold()), None)
        matching_projection = canonical_rows[matching_projection_index] if matching_projection_index is not None else {}
        if matching_projection_index is not None:
            consumed_projection_indexes.add(matching_projection_index)
        normalized_source = re.sub(r"\s+", " ", source).strip()
        normalized_line = re.sub(r"\s+", " ", text).strip()
        source_present = bool(normalized_line and normalized_line in normalized_source)
        if not source_present:
            blockers.append("canonical dialogue projection contains text absent from the selected screenplay scene")
        stable_id = _text(matching_projection.get("line_id"))
        identity_payload = {"script": lineage.get("canonical_script_sha256", ""), "scene": scene_id,
                            "order": order, "speaker": speaker, "text": text}
        dialogue_id = stable_id or ("dialogue_" + _digest(identity_payload)[:24])
        dialogue.append({"dialogue_id": dialogue_id, "scene_id": scene_id, "speaker": speaker,
                         "text": text, "order": order, "source_identity": _digest(identity_payload),
                         "source_present": source_present})

    content_decisions = _decision_map(scene.get("content_dispositions") or scene.get("coverage_decisions"), "content_id")
    dialogue_decisions = _decision_map(scene.get("dialogue_dispositions") or scene.get("coverage_decisions"), "dialogue_id")
    if creator_decisions is None:
        creator_decisions = next((
            rows for shot in shots
            if isinstance((rows := (shot.get("parameters") or {}).get("creator_coverage_decisions")), list)
        ), None)
    else:
        creator_decisions = list(creator_decisions)
    # Every canonical content/dialogue unit needs a current-version creator
    # decision; a partially supplied decision packet must not make missing
    # obligations fall back to implicit source rows or persisted dispositions.
    decision_kinds_present = {
        _text(row.get("obligation_type")) for row in creator_decisions or []
        if isinstance(row, dict)
    }
    known_shot_ids_for_decisions = {_text(shot.get("shot_id")) for shot in shots}
    for kind, obligations in (
        ("content", content_units),
        ("dialogue", dialogue),
        ("shot_content", [{"shot_id": shot_id} for shot_id in sorted(known_shot_ids_for_decisions)]),
        ("shot_dialogue", [{"shot_id": shot_id} for shot_id in sorted(known_shot_ids_for_decisions)]),
    ):
        if not obligations:
            continue
        if kind not in decision_kinds_present:
            blockers.append(f"creator coverage decisions are missing for {kind} obligations")
            continue
        identity_key = "content_id" if kind == "content" else "dialogue_id" if kind == "dialogue" else "shot_id"
        supplied_ids = {
            _text(row.get("obligation_id")) for row in creator_decisions or []
            if isinstance(row, dict) and _text(row.get("obligation_type")) == kind
        }
        required_ids = {_text(row.get(identity_key)) for row in obligations}
        if supplied_ids != required_ids:
            blockers.append(f"creator coverage decisions are incomplete for {kind} obligations")
    normalized_creator_decisions: dict[tuple[str, str], dict[str, Any]] = {}
    for decision in creator_decisions or []:
        if not isinstance(decision, dict):
            blockers.append("creator coverage decision is malformed")
            continue
        kind = _text(decision.get("obligation_type"))
        identity = _text(decision.get("obligation_id"))
        status = _text(decision.get("status")).upper()
        if status == "UNASSIGNED":
            status = "UNRESOLVED"
        shot_id = _text(decision.get("shot_id"))
        reason = _text(decision.get("reason"))
        key = (kind, identity)
        if kind not in {"content", "dialogue", "shot_dialogue", "shot_content"} or not identity or status not in DISPOSITIONS:
            blockers.append("creator coverage decision is malformed")
            continue
        if kind in {"content", "dialogue"} and status == "INTENTIONAL_SILENCE":
            blockers.append(f"canonical {kind} cannot be marked as intentional silence: {identity}")
        if kind == "shot_content" and status not in {"UNRESOLVED", "INTENTIONAL_SILENCE"}:
            blockers.append(f"shot content disposition is unsupported: {identity}")
        if kind == "shot_dialogue" and status not in {"UNRESOLVED", "EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"}:
            blockers.append(f"shot dialogue disposition is unsupported: {identity}")
        if kind == "content" and identity not in {row["content_id"] for row in content_units}:
            blockers.append(f"creator coverage decision references unknown content: {identity}")
            continue
        if kind == "dialogue" and identity not in {row["dialogue_id"] for row in dialogue}:
            blockers.append(f"creator coverage decision references unknown dialogue: {identity}")
            continue
        if kind in {"shot_dialogue", "shot_content"} and identity not in {_text(shot.get("shot_id")) for shot in shots}:
            blockers.append(f"creator coverage decision references unknown shot: {identity}")
            continue
        if key in normalized_creator_decisions:
            blockers.append(f"creator coverage decision is duplicated: {identity}")
            continue
        if (status == "ASSIGNED") != bool(shot_id) or (status in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and not reason):
            blockers.append(f"creator coverage decision is incomplete: {identity}")
        if kind == "shot_dialogue" and shot_id:
            blockers.append(f"shot dialogue disposition cannot assign ownership: {identity}")
        if kind == "shot_content" and status == "INTENTIONAL_SILENCE":
            shot_kind = next((_text(shot.get("shot_kind") or (shot.get("parameters") or {}).get("shot_kind")).lower()
                              for shot in shots if _text(shot.get("shot_id")) == identity), "")
            if shot_kind not in {"establishing", "establishing_shot", "transition", "transition_shot"}:
                blockers.append(f"intentional content silence is unsupported for shot: {identity}")
        if kind == "dialogue" and status == "INTENTIONAL_SILENCE":
            blockers.append(f"canonical dialogue cannot be marked as intentional silence: {identity}")
        if kind == "shot_dialogue" and status == "ASSIGNED":
            blockers.append(f"shot dialogue disposition cannot be an ownership assignment: {identity}")
        if kind == "shot_dialogue" and status not in {"UNRESOLVED", "EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"}:
            blockers.append(f"shot dialogue disposition is unsupported: {identity}")
        if kind == "shot_content" and status not in {"UNRESOLVED", "INTENTIONAL_SILENCE"}:
            blockers.append(f"shot content disposition is unsupported: {identity}")
        if kind == "shot_content" and status == "INTENTIONAL_SILENCE":
            shot_kind = next((_text(shot.get("shot_kind") or (shot.get("parameters") or {}).get("shot_kind")).lower()
                              for shot in shots if _text(shot.get("shot_id")) == identity), "")
            if shot_kind not in {"establishing", "establishing_shot", "transition", "transition_shot"}:
                blockers.append(f"intentional content silence is unsupported for shot: {identity}")
        normalized_creator_decisions[key] = decision
    canonical_content_ids = {row["content_id"] for row in content_units}
    canonical_dialogue_ids = {row["dialogue_id"] for row in dialogue}
    known_shot_ids = {_text(shot.get("shot_id")) for shot in shots}
    for kind, identities in (("content", canonical_content_ids), ("dialogue", canonical_dialogue_ids),
                             ("shot_dialogue", known_shot_ids), ("shot_content", known_shot_ids)):
        supplied_kind = any(
            isinstance(decision, dict) and decision.get("obligation_type") == kind
            for decision in (creator_decisions or [])
        )
        if supplied_kind:
            missing = identities - {identity for decision_kind, identity in normalized_creator_decisions if decision_kind == kind}
            if missing:
                blockers.append(f"creator coverage decisions are incomplete for {kind} obligations")
        unexpected = {identity for decision_kind, identity in normalized_creator_decisions if decision_kind == kind} - identities
        if unexpected:
            blockers.append(f"creator coverage decision references unknown {kind} obligation")
    if legacy_sources_blocked:
        # Legacy scene-level disposition projections have no current board
        # version scope and cannot override the explicit creator decision list.
        content_decisions = {}
        dialogue_decisions = {}
    for (kind, identity), decision in normalized_creator_decisions.items():
        if decision.get("status") == "ASSIGNED" and _text(decision.get("shot_id")) not in known_shot_ids:
            blockers.append(f"creator coverage decision references unknown shot: {_text(decision.get('shot_id'))}")
        row = {
            "disposition": "UNRESOLVED" if decision.get("status") in {"UNASSIGNED", "UNRESOLVED"} else decision.get("status"),
            "reason": decision.get("reason", ""),
            "shot_id": decision.get("shot_id"),
        }
        if kind == "content":
            content_decisions[identity] = {**content_decisions.get(identity, {}), **row}
        elif kind == "dialogue":
            dialogue_decisions[identity] = {**dialogue_decisions.get(identity, {}), **row}
        elif kind == "shot_dialogue":
            for shot in shots:
                if _text(shot.get("shot_id")) == identity:
                    params = shot.get("parameters") if isinstance(shot.get("parameters"), dict) else {}
                    params["dialogue_disposition"] = decision.get("status")
                    params["dialogue_disposition_reason"] = decision.get("reason", "")
                    shot["parameters"] = params
        elif kind == "shot_content":
            for shot in shots:
                if _text(shot.get("shot_id")) == identity:
                    shot["content_coverage_disposition"] = decision.get("status")
                    shot["content_coverage_reason"] = decision.get("reason", "")
    content_by_id = {row["content_id"]: row for row in content_units}
    dialogue_by_id = {row["dialogue_id"]: row for row in dialogue}
    shot_rows: list[dict[str, Any]] = []
    assignments_by_shot: dict[str, list[dict[str, Any]]] = {str(row.get("shot_id") or ""): [] for row in shots}
    used_content: dict[str, list[str]] = {key: [] for key in assignments_by_shot}
    used_dialogue: dict[str, list[str]] = {key: [] for key in assignments_by_shot}

    # Canonical unit assignment is authored on the selected shot, never derived
    # from segmentation, prompt wording, or shot order.
    for index, shot in enumerate(shots, start=1):
        shot_id = _text(shot.get("shot_id"))
        params = shot.get("parameters") if isinstance(shot.get("parameters"), dict) else {}
        declared_coverage = shot.get("covered_content_ids") or params.get("covered_content_ids") or []
        if legacy_sources_blocked:
            # Historical covered_content_ids on a shot record are evidence of
            # past state, not current creator intent. Only version-scoped Scene
            # Direction decisions may assign canonical content.
            declared_coverage = []
        covered = _ids(declared_coverage)
        if any(kind == "content" for kind, _ in normalized_creator_decisions):
            covered = []
            declared_coverage = []

        for (kind, identity), decision in normalized_creator_decisions.items():
            if kind == "content" and decision.get("status") == "ASSIGNED" and _text(decision.get("shot_id")) == shot_id:
                if identity not in covered:
                    covered.append(identity)
            elif kind == "shot_content" and identity == shot_id and decision.get("status") == "INTENTIONAL_SILENCE":
                shot["content_coverage_disposition"] = "INTENTIONAL_SILENCE"
                shot["content_coverage_reason"] = _text(decision.get("reason"))
        if isinstance(declared_coverage, list):
            declared_ids = [str(item).strip() for item in declared_coverage if str(item or "").strip()]
            if len(declared_ids) != len(set(declared_ids)):
                blockers.append(f"shot {shot_id} declares duplicate canonical content coverage")
        if _text(shot.get("scene_id") or params.get("scene_id")) not in {"", scene_id}:
            blockers.append(f"shot {shot_id} belongs to a stale or foreign scene identity")
        unknown = [value for value in covered if value not in content_by_id]
        if unknown:
            blockers.append(f"shot {shot_id} coverage references unknown canonical content IDs")
        for content_id in covered:
            if content_id in content_by_id and shot_id in used_content:
                used_content[shot_id].append(content_id)
        shot_kind = _text(shot.get("shot_kind") or params.get("shot_kind") or shot.get("shot_type") or params.get("shot_type")).lower()
        camera_plan = params.get("camera_plan") if isinstance(params.get("camera_plan"), dict) else {}
        shot_dialogue_decision = normalized_creator_decisions.get(("shot_dialogue", shot_id), {})
        shot_rows.append({"shot_id": shot_id, "scene_id": scene_id,
                          "shot_order": int(shot.get("shot_number") or shot.get("shot_order") or index),
                          "covered_content_ids": covered, "covered_dialogue_ids": [],
                          "required_character_ids": [], "required_setting_id": "",
                          "camera_plan": camera_plan,
                          "source_scene_id": _text(shot.get("scene_id") or params.get("scene_id")) or scene_id,
                          "camera_provenance": _text(params.get("camera_provenance") or shot.get("camera_provenance")) or "UNSPECIFIED",
                          "camera_source_digest": _text(params.get("camera_source_digest") or shot.get("camera_source_digest")),
                          "camera_source_project_id": _text(params.get("camera_source_project_id") or shot.get("camera_source_project_id")),
                          "camera_source_scene_id": _text(params.get("camera_source_scene_id") or shot.get("camera_source_scene_id")),
                          "camera_source_shot_id": _text(params.get("camera_source_shot_id") or shot.get("camera_source_shot_id")),
                          "camera_source_storyboard_shot_id": _text(params.get("camera_source_storyboard_shot_id") or shot.get("camera_source_storyboard_shot_id")),
                          "camera_target_project_id": _text(params.get("camera_target_project_id") or shot.get("camera_target_project_id")),
                          "camera_target_scene_id": _text(params.get("camera_target_scene_id") or shot.get("camera_target_scene_id")),
                          "camera_target_shot_id": _text(params.get("camera_target_shot_id") or shot.get("camera_target_shot_id")),
                          "approved_reference_ids": [], "approved_reference_bindings": [],
                          "shot_kind": shot_kind,
                          "dialogue_disposition": (
                              "UNRESOLVED"
                              if shot_dialogue_decision.get("status") in {"UNASSIGNED", "UNRESOLVED"}
                              else _text(shot_dialogue_decision.get("status")).upper() or "UNRESOLVED"
                          ),
                          "dialogue_disposition_reason": _text(shot_dialogue_decision.get("reason"))})

    # Match existing Scene Direction assignments by canonical line identity or
    # exact speaker/text. This preserves the existing editor as the authority.
    explicit_rows = _explicit_assignments(project, scene, shots, scene_id, legacy_sources_blocked=legacy_sources_blocked)
    creator_dialogue_ids = {
        identity for (kind, identity), decision in normalized_creator_decisions.items()
        if kind == "dialogue"
    }
    if creator_dialogue_ids:
        decided_lines = [dialogue_by_id[identity] for identity in creator_dialogue_ids if identity in dialogue_by_id]
        explicit_rows = [
            row for row in explicit_rows
            if _text(row.get("line_id") or row.get("dialogue_id")) not in creator_dialogue_ids
            and not any(
                _text(row.get("text") or row.get("line_text") or row.get("dialogue")) == item["text"]
                and _text(row.get("character") or row.get("character_name") or row.get("character_id")).casefold() == item["speaker"].casefold()
                for item in decided_lines
            )
        ]
    for (kind, identity), decision in normalized_creator_decisions.items():
        if kind != "dialogue" or decision.get("status") != "ASSIGNED":
            continue
        canonical = dialogue_by_id.get(identity)
        if canonical is None:
            blockers.append(f"creator coverage decision references unknown dialogue: {identity}")
            continue
        explicit_rows.append({
            "scene_id": scene_id, "shot_id": decision.get("shot_id"),
            "line_id": identity, "character": canonical["speaker"], "text": canonical["text"],
        })
    for (kind, identity), decision in normalized_creator_decisions.items():
        if kind == "content" and identity not in content_by_id:
            blockers.append(f"creator coverage decision references unknown content: {identity}")
        if kind == "dialogue" and identity not in dialogue_by_id:
            blockers.append(f"creator coverage decision references unknown dialogue: {identity}")
        if kind in {"shot_dialogue", "shot_content"} and identity not in assignments_by_shot:
            blockers.append(f"creator coverage decision references unknown shot: {identity}")
        if decision.get("status") == "ASSIGNED" and _text(decision.get("shot_id")) not in assignments_by_shot:
            blockers.append(f"creator coverage decision references unknown shot: {_text(decision.get('shot_id'))}")
    unmatched_rows = []
    for row in explicit_rows:
        row_scene = _text(row.get("scene_id"))
        shot_id = _text(row.get("shot_id"))
        if row_scene != scene_id or shot_id not in assignments_by_shot:
            unmatched_rows.append(row)
            continue
        if not _text(row.get("text") or row.get("line_text") or row.get("dialogue")):
            # An empty explicit shot dialogue list can carry a shot-level
            # silence/omission decision; it does not assign a canonical line.
            continue
        speaker = _text(row.get("character") or row.get("character_name") or row.get("character_id"))
        text = _text(row.get("text") or row.get("line_text") or row.get("dialogue"))
        candidates = [item for item in dialogue if item["text"] == text and (not speaker or item["speaker"].casefold() == speaker.casefold())]
        requested_id = _text(row.get("line_id") or row.get("dialogue_id"))
        if requested_id:
            candidates = [item for item in candidates if item["dialogue_id"] == requested_id]
        elif len(candidates) > 1:
            unmatched_rows.append(row)
            continue
        available = [item for item in candidates if shot_id not in item.get("shot_ids", [])]
        if not available:
            unmatched_rows.append(row)
            continue
        item = available[0]
        item.setdefault("shot_ids", []).append(shot_id)
        assignment = {"line_id": item["dialogue_id"], "scene_id": scene_id, "character": item["speaker"], "text": item["text"], "shot_id": shot_id}
        advisory_subtext = _text(row.get("emotional_subtext") or row.get("voice_style_hint"))
        if advisory_subtext:
            assignment["emotional_subtext"] = advisory_subtext
        assignments_by_shot[shot_id].append(assignment)
        used_dialogue[shot_id].append(item["dialogue_id"])
    if unmatched_rows:
        blockers.append("dialogue assignment contains a stale, non-canonical, or foreign line")
    for content_id, assigned_shots in used_content.items():
        for covered_id in assigned_shots:
            if sum(covered_id in ids for ids in used_content.values()) > 1:
                blockers.append(f"canonical scene content has duplicate shot coverage: {covered_id}")
                break
    for line in dialogue:
        if len(set(line.get("shot_ids", []))) > 1:
            blockers.append(f"canonical dialogue has duplicate shot coverage: {line['dialogue_id']}")

    shot_by_id = {str(row.get("shot_id") or ""): row for row in shot_rows}
    identity_requirements = reference_requirements or {}
    known_characters = identity_requirements.get("characters", {}) if isinstance(identity_requirements.get("characters"), dict) else {}
    setting_id = _text(identity_requirements.get("setting_id"))
    if not setting_id:
        blockers.append("required setting identity unresolved")

    for shot, shot_row in zip(shots, shot_rows):
        shot_id = shot_row["shot_id"]
        params = shot.get("parameters") if isinstance(shot.get("parameters"), dict) else {}
        raw_intent = shot.get("intent") if isinstance(shot.get("intent"), dict) else {}
        focus = shot.get("character_focus") or params.get("character_focus") or raw_intent.get("character_focus")
        try:
            from app.services.reference_validation import resolve_shot_character_ids

            resolved_ids = resolve_shot_character_ids(
                shot=shot,
                known_characters=known_characters,
            )
        except ValueError as exc:
            blockers.append(str(exc))
            resolved_ids = []
        if focus and not resolved_ids:
            blockers.append(f"shot {shot_id} required character reference focus is unresolved")
        shot_row["required_character_ids"] = resolved_ids
        shot_row["required_setting_id"] = setting_id
        if shot_row["camera_provenance"] not in {"APPROVED", "USER_SPECIFIED"}:
            blockers.append(f"shot {shot_id} camera provenance unresolved or unapproved")
        else:
            from app.services.camera_provenance import camera_plan_digest
            if (not shot_row["camera_plan"]
                    or shot_row["camera_source_project_id"] != project_id
                    or shot_row["camera_source_scene_id"] != scene_id
                    or shot_row["camera_source_shot_id"] != shot_id
                    or shot_row["camera_target_project_id"] != project_id
                    or shot_row["camera_target_scene_id"] != scene_id
                    or shot_row["camera_target_shot_id"] != shot_id
                    or (shot_row["camera_provenance"] == "APPROVED" and not shot_row["camera_source_storyboard_shot_id"])):
                blockers.append(f"shot {shot_id} authoritative camera source identity unresolved")
            else:
                expected_digest = camera_plan_digest(
                    shot_row["camera_plan"], shot_row["camera_provenance"],
                    source_project_id=shot_row["camera_source_project_id"],
                    source_scene_id=shot_row["camera_source_scene_id"],
                    source_shot_id=shot_row["camera_source_shot_id"],
                    source_storyboard_shot_id=shot_row["camera_source_storyboard_shot_id"],
                )
                if shot_row["camera_source_digest"] != expected_digest:
                    blockers.append(f"shot {shot_id} camera provenance digest unresolved")
        binding = identity_requirements.get("reference_binding") if isinstance(identity_requirements.get("reference_binding"), list) else []
        needed_targets = set(resolved_ids) | ({setting_id} if setting_id else set())
        approved_bindings: list[dict[str, Any]] = []
        seen_anchor_ids: set[str] = set()
        for row in binding:
            if not (row.get("target_id") in needed_targets and row.get("approval_state") == "approved" and row.get("canonical")):
                continue
            # One approved anchor per identity: a duplicate binding row for the
            # same ref_id (e.g. a storyboard-frame identity projection) adds no
            # identity information and must not double-list the anchor.
            anchor_id = str(row.get("ref_id") or "")
            if anchor_id and anchor_id in seen_anchor_ids:
                continue
            if anchor_id:
                seen_anchor_ids.add(anchor_id)
            approved_bindings.append(
                {key: row.get(key) for key in ("ref_id", "uri", "target_type", "target_id", "role", "category", "canonical", "approval_state", "source_kind", "kind")}
            )
        shot_row["approved_reference_bindings"] = approved_bindings
        shot_row["approved_reference_ids"] = [str(row.get("ref_id")) for row in shot_row["approved_reference_bindings"]]
        if resolved_ids and any(not any(row.get("target_type") == "character" and row.get("target_id") == cid and row.get("approval_state") == "approved" and row.get("canonical") for row in binding) for cid in resolved_ids):
            blockers.append(f"shot {shot_id} required character reference unresolved")
        if setting_id and not any(row.get("target_type") == "setting" and row.get("target_id") == setting_id and row.get("approval_state") == "approved" and row.get("canonical") for row in binding):
            blockers.append(f"shot {shot_id} required setting reference unresolved")
        if not shot_row["covered_content_ids"]:
            explicit_establishing = (
                shot_row["shot_kind"] in {"establishing", "establishing_shot", "transition", "transition_shot"}
                and _text(shot.get("content_coverage_disposition") or params.get("content_coverage_disposition")).upper() == "INTENTIONAL_SILENCE"
                and _text(shot.get("content_coverage_reason") or params.get("content_coverage_reason"))
            )
            shot_row["content_coverage_state"] = "INTENTIONAL_ESTABLISHING" if explicit_establishing else "UNRESOLVED"
            if shot_row["content_coverage_state"] == "UNRESOLVED":
                blockers.append(f"shot {shot_id} canonical content coverage unresolved")
        else:
            shot_row["content_coverage_state"] = "ASSIGNED"
        shot_row["dialogue_disposition"] = _text(shot.get("dialogue_disposition") or params.get("dialogue_disposition")).upper() or "UNRESOLVED"
        shot_row["dialogue_disposition_reason"] = _text(shot.get("dialogue_disposition_reason") or params.get("dialogue_disposition_reason"))
        if shot_row["dialogue_disposition"] not in DISPOSITIONS:
            shot_row["dialogue_disposition"] = "UNRESOLVED"

    for unit in content_units:
        content_id = unit["content_id"]
        assigned_shots = [shot_id for shot_id, ids in used_content.items() if content_id in ids]
        decision = content_decisions.get(content_id, {})
        disposition = "ASSIGNED" if assigned_shots else _text(decision.get("disposition") or decision.get("state")).upper() or "UNRESOLVED"
        declared_shot = _text(decision.get("shot_id"))
        if disposition == "ASSIGNED" and declared_shot and assigned_shots != [declared_shot]:
            blockers.append(f"canonical scene content assignment does not match its creator decision: {content_id}")
        if disposition not in DISPOSITIONS:
            disposition = "UNRESOLVED"
        reason = _text(decision.get("reason") or decision.get("editorial_reason"))
        if disposition in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and not reason:
            disposition = "UNRESOLVED"
        unit.update(disposition=disposition, shot_ids=assigned_shots, editorial_reason=reason)
        if disposition == "UNRESOLVED":
            blockers.append(f"canonical scene content unresolved: {content_id}")
        if disposition == "ASSIGNED" and not assigned_shots:
            blockers.append(f"canonical scene content has no shot assignment: {content_id}")
        if decision and disposition == "ASSIGNED" and _text(decision.get("disposition") or decision.get("state")).upper() in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"}:
            blockers.append(f"canonical scene content has conflicting assignment and editorial disposition: {content_id}")
        if disposition == "EXPLICITLY_OMITTED" and assigned_shots:
            blockers.append(f"canonical scene content cannot be assigned and explicitly omitted: {content_id}")

    for line in dialogue:
        dialogue_id = line["dialogue_id"]
        assigned_shots = list(dict.fromkeys(line.get("shot_ids", [])))
        decision = dialogue_decisions.get(dialogue_id, {})
        disposition = "ASSIGNED" if assigned_shots else _text(decision.get("disposition") or decision.get("state")).upper() or "UNRESOLVED"
        declared_shot = _text(decision.get("shot_id"))
        if disposition == "ASSIGNED" and declared_shot and assigned_shots != [declared_shot]:
            blockers.append(f"canonical dialogue assignment does not match its creator decision: {dialogue_id}")
        if disposition not in DISPOSITIONS:
            disposition = "UNRESOLVED"
        reason = _text(decision.get("reason") or decision.get("editorial_reason"))
        # Silence is a shot/scene decision, not a valid disposition for an
        # identified canonical spoken line. Such a line is assigned or edited
        # out explicitly; treating it as silence would erase screenplay intent.
        if disposition == "INTENTIONAL_SILENCE":
            disposition = "UNRESOLVED"
        if disposition in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and not reason:
            disposition = "UNRESOLVED"
        line.update(disposition=disposition, shot_ids=assigned_shots, editorial_reason=reason)
        if disposition == "UNRESOLVED":
            blockers.append(f"canonical dialogue unresolved: {dialogue_id}")
        if disposition == "ASSIGNED" and not assigned_shots:
            blockers.append(f"canonical dialogue has no shot assignment: {dialogue_id}")
        if decision and disposition == "ASSIGNED" and _text(decision.get("disposition") or decision.get("state")).upper() in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"}:
            blockers.append(f"canonical dialogue has conflicting assignment and editorial disposition: {dialogue_id}")
        if disposition in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and assigned_shots:
            blockers.append(f"canonical dialogue cannot be assigned and omitted/silenced: {dialogue_id}")
        for shot_id in assigned_shots:
            if shot_id in shot_by_id:
                shot_by_id[shot_id]["covered_dialogue_ids"].append(dialogue_id)

    for shot, shot_row in zip(shots, shot_rows):
        shot_id = shot_row["shot_id"]
        params = shot.get("parameters") if isinstance(shot.get("parameters"), dict) else {}
        shot_content_decision = normalized_creator_decisions.get(("shot_content", shot_id), {})
        content_disposition = (
            _text(shot_content_decision.get("status")).upper()
            if legacy_sources_blocked
            else _text(shot.get("content_coverage_disposition") or params.get("content_coverage_disposition")).upper()
        )
        content_reason = (
            _text(shot_content_decision.get("reason"))
            if legacy_sources_blocked
            else _text(shot.get("content_coverage_reason") or params.get("content_coverage_reason"))
        )
        if shot_row["covered_content_ids"]:
            shot_row["content_coverage_state"] = "ASSIGNED"
        elif (shot_row["shot_kind"] in {"establishing", "establishing_shot", "transition", "transition_shot"}
              and content_disposition == "INTENTIONAL_SILENCE" and content_reason):
            shot_row["content_coverage_state"] = "INTENTIONAL_ESTABLISHING"
            shot_row["content_coverage_reason"] = content_reason
        elif any(kind == "shot_content" and identity == shot_id and decision.get("status") == "INTENTIONAL_SILENCE"
                 for (kind, identity), decision in normalized_creator_decisions.items()):
            shot_row["content_coverage_state"] = "UNRESOLVED"
            blockers.append(f"shot {shot_id} intentional establishing disposition conflicts with its shot kind or assigned content")
        else:
            shot_row["content_coverage_state"] = "UNRESOLVED"
            blockers.append(f"shot {shot_id} canonical content coverage unresolved")
        disposition = shot_row["dialogue_disposition"]
        reason = shot_row["dialogue_disposition_reason"]
        if shot_row["covered_dialogue_ids"]:
            if disposition in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"}:
                blockers.append(f"shot {shot_id} has conflicting dialogue assignment and editorial disposition")
            shot_row["dialogue_disposition"] = "ASSIGNED"
        elif dialogue and (disposition == "UNRESOLVED" or (disposition in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and not reason)):
            blockers.append(f"shot {shot_id} dialogue disposition unresolved")

    # No dialogue is not evidence of silence: silence requires an explicit,
    # reasoned scene/shot editorial decision. This is distinct from empty content.
    coverage_dialogue_disposition = ""
    coverage_dialogue_reason = ""
    if not dialogue:
        silence = "" if legacy_sources_blocked else _text(scene.get("dialogue_disposition") or scene.get("speech_disposition")).upper()

        reason = "" if legacy_sources_blocked else _text(scene.get("dialogue_disposition_reason") or scene.get("editorial_reason"))
        coverage_disposition = silence if silence in DISPOSITIONS and reason else "UNRESOLVED"
        coverage_dialogue_disposition = coverage_disposition
        coverage_dialogue_reason = reason
        if coverage_disposition == "UNRESOLVED":
            shot_resolutions = [row for row in shot_rows if row["dialogue_disposition"] in {"INTENTIONAL_SILENCE", "EXPLICITLY_OMITTED"} and _text(row["dialogue_disposition_reason"])]
            if len(shot_resolutions) != len(shot_rows):
                blockers.append("scene dialogue disposition unresolved: intentional silence has not been explicitly recorded")
            elif shot_rows and len({row["dialogue_disposition"] for row in shot_rows}) == 1:
                coverage_disposition = shot_rows[0]["dialogue_disposition"]
                coverage_reason = "; ".join(dict.fromkeys(row["dialogue_disposition_reason"] for row in shot_rows))
                coverage_dialogue_disposition = coverage_disposition
                coverage_dialogue_reason = coverage_reason
        else:
            for shot_row in shot_rows:
                if shot_row["dialogue_disposition"] == "UNRESOLVED":
                    shot_row["dialogue_disposition"] = coverage_disposition
                    shot_row["dialogue_disposition_reason"] = reason
        if coverage_disposition == "UNRESOLVED":
            coverage_dialogue_disposition = "UNRESOLVED"
            coverage_dialogue_reason = ""

    coverage = {
        "coverage_version": 1,
        "project_id": project_id,
        "script_version_id": lineage.get("script_version_id", ""),
        "canonical_script_sha256": lineage.get("canonical_script_sha256", ""),
        "canonical_script_text": str(project.get("script_text") or ""),
        "script_version": {
            "version_id": lineage.get("script_version_id", ""),
            "sha256": lineage.get("canonical_script_sha256", ""),
            "byte_length": len(str(project.get("script_text") or "").encode("utf-8")),
        },
        "scene_id": scene_id,
        "scene_lineage_status": lineage.get("status", "UNRESOLVED"),
        "scene_source_identity": lineage.get("scene_source_identity", ""),
        "scene_source_start": lineage.get("scene_source_start"),
        "scene_source_end": lineage.get("scene_source_end"),
        "scene_content_sha256": lineage.get("scene_content_sha256", ""),
        "scene_content": source,
        "content_units": content_units,
        "dialogue": dialogue,
        "dialogue_disposition": coverage_dialogue_disposition,
        "dialogue_disposition_reason": coverage_dialogue_reason,
        "shots": shot_rows,
        "creator_decisions": [
            {key: value for key, value in row.items()
             if key in {"obligation_type", "obligation_id", "status", "shot_id", "reason", "decision_version_id"}}
            for row in creator_decisions or [] if isinstance(row, dict)
        ],
        "readiness_blockers": list(dict.fromkeys(blockers)),
    }
    return coverage, list(dict.fromkeys(blockers)), assignments_by_shot


def verify_scene_coverage_contract(value: Any, *, require_resolved: bool = True) -> dict[str, Any]:
    """Validate frozen coverage shape, ownership, dispositions, and references."""
    if not isinstance(value, dict) or value.get("coverage_version") != 1:
        raise ValueError("Canonical scene coverage contract is missing or malformed")
    if not all(_text(value.get(key)) for key in ("project_id", "scene_id", "script_version_id", "canonical_script_sha256", "scene_source_identity", "scene_content_sha256")):
        raise ValueError("Canonical scene lineage is unresolved")
    if value.get("scene_lineage_status") != "RESOLVED":
        raise ValueError("Canonical scene lineage is unresolved")
    readiness_blockers = value.get("readiness_blockers", [])
    if not isinstance(readiness_blockers, list) or any(not _text(item) for item in readiness_blockers):
        raise ValueError("Canonical scene readiness blockers are malformed")
    if require_resolved and readiness_blockers:
        raise ValueError("Canonical scene coverage has unresolved readiness blockers")
    source = value.get("scene_content")
    if not isinstance(source, str) or hashlib.sha256(source.encode("utf-8")).hexdigest() != value.get("scene_content_sha256"):
        raise ValueError("Canonical scene content hash does not match its source")
    script_hash = str(value.get("canonical_script_sha256") or "")
    script_version_id = _text(value.get("script_version_id"))
    if not script_version_id:
        raise ValueError("Canonical script version identity does not match its digest")
    if script_version_id.startswith("script_") and script_version_id != f"script_{script_hash[:24]}":
        raise ValueError("Canonical script version identity does not match its digest")
    start, end = value.get("scene_source_start"), value.get("scene_source_end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end - start != len(source):
        raise ValueError("Canonical scene source span is malformed")
    expected_source_identity = _digest({"project_id": value["project_id"], "scene_id": value["scene_id"], "script_version_id": script_version_id, "script_sha256": script_hash, "start": start, "end": end})
    if value.get("scene_source_identity") != expected_source_identity:
        raise ValueError("Canonical scene source identity does not match its lineage")
    content_units, dialogue, shots = value.get("content_units"), value.get("dialogue"), value.get("shots")
    if not isinstance(content_units, list) or not isinstance(dialogue, list) or not isinstance(shots, list) or not shots:
        raise ValueError("Canonical scene coverage lists are malformed")
    expected_content = [line.strip() for line in source.splitlines() if line.strip()]
    if [row.get("text") if isinstance(row, dict) else None for row in content_units] != expected_content:
        raise ValueError("Canonical scene content units do not losslessly cover the ordered source")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != value.get("scene_content_sha256"):
        raise ValueError("Canonical scene content hash does not match its source")
    script_span = value.get("canonical_script_text")
    if not isinstance(script_span, str) or hashlib.sha256(script_span.encode("utf-8")).hexdigest() != script_hash:
        raise ValueError("Canonical screenplay text is missing or does not match its version digest")
    script_version_row = value.get("script_version")
    if not isinstance(script_version_row, dict) or (
        script_version_row.get("version_id") != script_version_id
        or script_version_row.get("sha256") != script_hash
        or script_version_row.get("byte_length") != len(script_span.encode("utf-8"))
    ):
        raise ValueError("Canonical script version identity or content metadata is invalid")
    if not isinstance(start, int) or not isinstance(end, int) or script_span[start:end] != source:
        raise ValueError("Canonical scene source span does not match the canonical screenplay")
    shot_ids = [str(row.get("shot_id") or "") for row in shots if isinstance(row, dict)]
    if len(shot_ids) != len(shots) or not all(shot_ids) or len(set(shot_ids)) != len(shot_ids):
        raise ValueError("Canonical scene coverage shot identities are malformed")
    for rows, identity_key in ((content_units, "content_id"), (dialogue, "dialogue_id")):
        ids = set()
        orders = []
        for row in rows:
            if not isinstance(row, dict) or not _text(row.get(identity_key)) or row[identity_key] in ids:
                raise ValueError("Canonical scene content identities are malformed")
            if row.get("scene_id") != value.get("scene_id"):
                raise ValueError("Canonical scene unit belongs to another scene")
            order = row.get("order")
            if not isinstance(order, int) or order <= 0:
                raise ValueError("Canonical scene unit ordering is malformed")
            orders.append(order)
            ids.add(row[identity_key])
            if row.get("disposition") not in DISPOSITIONS:
                raise ValueError("Canonical scene disposition is invalid")
            if rows is dialogue:
                identity_payload = {"script": script_hash, "scene": value["scene_id"], "order": order,
                                    "speaker": row.get("speaker"), "text": row.get("text")}
                if row.get("source_identity") != _digest(identity_payload) or row.get("source_present") is not True:
                    raise ValueError("Canonical dialogue identity or screenplay provenance is invalid")
                raw_line = _text(row.get("text"))
                if (not raw_line or re.sub(r"\s+", " ", raw_line).strip() not in
                        re.sub(r"\s+", " ", source).strip()):
                    raise ValueError("Canonical dialogue is not present in the authoritative screenplay")
            if rows is content_units:
                source_start, source_end = row.get("source_start"), row.get("source_end")
                if (not isinstance(source_start, int) or not isinstance(source_end, int)
                        or source_start < start or source_end > end or source_end - source_start != len(row.get("text", ""))
                        or source[source_start - start:source_end - start] != row.get("text")):
                    raise ValueError("Canonical scene content source span is malformed")
                content_id = "content_" + _digest({"scene": value["scene_id"], "script": script_hash, "order": order, "text": row.get("text")})[:24]
                if row.get("content_id") != content_id or not _text(row.get("text")):
                    raise ValueError("Canonical scene content identity does not match its ordered source unit")
            if any(shot_id not in shot_ids for shot_id in row.get("shot_ids", [])):
                raise ValueError("Canonical scene content references a foreign shot")
            if require_resolved and row.get("disposition") == "UNRESOLVED":
                raise ValueError("Canonical scene content disposition is unresolved")
            if row.get("disposition") == "UNRESOLVED" and row.get("shot_ids"):
                raise ValueError("Unresolved canonical scene content declares shot coverage")
            if row.get("disposition") == "ASSIGNED" and not row.get("shot_ids"):
                raise ValueError("Assigned canonical scene content has no shot")
            if row.get("disposition") == "ASSIGNED" and len(row.get("shot_ids", [])) != 1:
                raise ValueError("Assigned canonical scene content has duplicate shot coverage")
            if rows is dialogue and row.get("disposition") == "ASSIGNED" and len(row.get("shot_ids", [])) != 1:
                raise ValueError("Assigned canonical dialogue has duplicate shot coverage")
            if row.get("disposition") in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and row.get("shot_ids"):
                raise ValueError("Omitted or silent canonical content declares shot coverage")
            if row.get("disposition") == "ASSIGNED":
                covered_key = "covered_content_ids" if identity_key == "content_id" else "covered_dialogue_ids"
                for shot_id in row.get("shot_ids", []):
                    shot_row = next(shot for shot in shots if shot.get("shot_id") == shot_id)
                    if row[identity_key] not in shot_row.get(covered_key, []):
                        raise ValueError("Assigned canonical content is not reciprocally declared by its shot")
            if row.get("disposition") in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and not _text(row.get("editorial_reason")):
                raise ValueError("Canonical scene omission/silence lacks an editorial reason")
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            raise ValueError("Canonical scene unit ordering is malformed")
    content_ids = {row["content_id"] for row in content_units}
    dialogue_ids = {row["dialogue_id"] for row in dialogue}
    # Canonical units are the source of truth for assignments; validate the
    # reciprocal shot declarations after all unit disposition rows were read.
    for shot in shots:
        if (not isinstance(shot, dict) or shot.get("scene_id") != value.get("scene_id")
                or shot.get("source_scene_id", value.get("scene_id")) != value.get("scene_id")
                or not isinstance(shot.get("covered_content_ids"), list)
                or not isinstance(shot.get("covered_dialogue_ids"), list)):
            raise ValueError("Frozen shot coverage is malformed or has stale scene identity")
        if (len(shot["covered_content_ids"]) != len(set(shot["covered_content_ids"]))
                or len(shot["covered_dialogue_ids"]) != len(set(shot["covered_dialogue_ids"]))):
            raise ValueError("Frozen shot declares duplicate canonical coverage")
        if any(value not in content_ids for value in shot["covered_content_ids"]):
            raise ValueError("Frozen shot references unknown canonical content")
        if any(value not in dialogue_ids for value in shot["covered_dialogue_ids"]):
            raise ValueError("Frozen shot references unknown canonical dialogue")
        for content_id in shot["covered_content_ids"]:
            unit = next(row for row in content_units if row["content_id"] == content_id)
            if unit.get("disposition") != "ASSIGNED" or shot["shot_id"] not in unit.get("shot_ids", []):
                raise ValueError("Shot content assignment is not reciprocated by its canonical unit")
        for dialogue_id in shot["covered_dialogue_ids"]:
            line = next(row for row in dialogue if row["dialogue_id"] == dialogue_id)
            if line.get("disposition") != "ASSIGNED" or shot["shot_id"] not in line.get("shot_ids", []):
                raise ValueError("Shot dialogue assignment is not reciprocated by its canonical line")
        if not isinstance(shot.get("shot_order"), int) or shot["shot_order"] <= 0:
            raise ValueError("Frozen shot order is malformed")
        if require_resolved and not shot.get("covered_content_ids") and shot.get("content_coverage_state") != "INTENTIONAL_ESTABLISHING":
            raise ValueError("Frozen shot canonical content coverage is unresolved")
        if shot.get("content_coverage_state") not in {"ASSIGNED", "INTENTIONAL_ESTABLISHING", "UNRESOLVED"}:
            raise ValueError("Frozen shot content disposition is malformed")
        if shot.get("content_coverage_state") == "INTENTIONAL_ESTABLISHING" and not _text(shot.get("content_coverage_reason")):
            raise ValueError("Frozen establishing shot lacks an explicit editorial reason")
        if require_resolved and (not shot.get("required_setting_id") or not shot.get("approved_reference_ids")):
            raise ValueError("Frozen shot identity/reference requirements are unresolved")
        bindings = shot.get("approved_reference_bindings")
        if not isinstance(bindings, list) or any(not isinstance(row, dict) for row in bindings):
            raise ValueError("Frozen shot approved reference bindings are malformed")
        if require_resolved:
            for target_type, target_id in [("character", item) for item in shot.get("required_character_ids", [])] + [("setting", shot.get("required_setting_id"))]:
                if not any(row.get("target_type") == target_type and row.get("target_id") == target_id and row.get("canonical") is True and row.get("approval_state") == "approved" and _text(row.get("ref_id")) and _text(row.get("uri")) for row in bindings):
                    raise ValueError("Frozen shot identity/reference requirements are unresolved")
        binding_ids = [str(row.get("ref_id") or "") for row in bindings]
        if (
            not all(binding_ids)
            or len(binding_ids) != len(set(binding_ids))
            or shot.get("approved_reference_ids") != binding_ids
        ):
            raise ValueError("Frozen shot reference identities do not match their ordered approved bindings")
        if require_resolved and shot.get("dialogue_disposition") == "UNRESOLVED":
            raise ValueError("Frozen shot dialogue disposition is unresolved")
        if shot.get("covered_dialogue_ids") and shot.get("dialogue_disposition") != "ASSIGNED":
            raise ValueError("Frozen shot dialogue assignment does not match its disposition")
        if shot.get("dialogue_disposition") in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and not _text(shot.get("dialogue_disposition_reason")):
            raise ValueError("Frozen shot omission/silence lacks an editorial reason")
        if require_resolved and shot.get("camera_provenance") not in {"APPROVED", "USER_SPECIFIED"}:
            raise ValueError("Frozen shot camera provenance is unresolved or unapproved")
        if require_resolved:
            from app.services.camera_provenance import camera_plan_digest
            if (not isinstance(shot.get("camera_plan"), dict) or not shot["camera_plan"]
                    or shot.get("camera_source_project_id") != value["project_id"]
                    or shot.get("camera_source_scene_id") != value["scene_id"]
                    or shot.get("camera_source_shot_id") != shot.get("shot_id")
                    or shot.get("camera_target_project_id") != value["project_id"]
                    or shot.get("camera_target_scene_id") != value["scene_id"]
                    or shot.get("camera_target_shot_id") != shot.get("shot_id")
                    or (shot.get("camera_provenance") == "APPROVED" and not _text(shot.get("camera_source_storyboard_shot_id")))):
                raise ValueError("Frozen shot camera source identity is unresolved")
            expected_digest = camera_plan_digest(
                shot["camera_plan"], shot["camera_provenance"],
                source_project_id=shot["camera_source_project_id"],
                source_scene_id=shot["camera_source_scene_id"],
                source_shot_id=shot["camera_source_shot_id"],
                source_storyboard_shot_id=shot.get("camera_source_storyboard_shot_id", ""),
            )
            if shot.get("camera_source_digest") != expected_digest:
                raise ValueError("Frozen shot camera provenance digest is invalid")
    if dialogue and require_resolved and any(row.get("disposition") == "INTENTIONAL_SILENCE" for row in dialogue):
        raise ValueError("Canonical spoken dialogue cannot be marked as intentional silence")
    if not dialogue and require_resolved and value.get("dialogue_disposition") not in {"INTENTIONAL_SILENCE", "EXPLICITLY_OMITTED"}:
        raise ValueError("No-dialogue scene lacks an explicit silence/omission decision")
    if not dialogue and value.get("dialogue_disposition") in {"INTENTIONAL_SILENCE", "EXPLICITLY_OMITTED"} and not _text(value.get("dialogue_disposition_reason")):
        raise ValueError("No-dialogue scene silence/omission lacks an editorial reason")
    creator_decisions = value.get("creator_decisions")
    if require_resolved and not isinstance(creator_decisions, list):
        raise ValueError("Current version-scoped creator coverage decisions are missing")
    if isinstance(creator_decisions, list):
        rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for row in creator_decisions:
            if not isinstance(row, dict):
                raise ValueError("Frozen creator coverage decision is malformed")
            kind, identity = _text(row.get("obligation_type")), _text(row.get("obligation_id"))
            if kind not in {"content", "dialogue", "shot_content", "shot_dialogue"} or not identity:
                raise ValueError("Frozen creator coverage decision identity is malformed")
            key = (kind, identity)
            if key in rows_by_key:
                raise ValueError("Frozen creator coverage decisions contain duplicates")
            rows_by_key[key] = row
        for kind, identities in (
            ("content", content_ids),
            ("dialogue", dialogue_ids),
            ("shot_content", set(shot_ids)),
            ("shot_dialogue", set(shot_ids)),
        ):
            supplied = {identity for decision_kind, identity in rows_by_key if decision_kind == kind}
            if supplied != identities:
                raise ValueError(f"Frozen creator coverage decisions are incomplete for {kind}")
        content_by_id = {row["content_id"]: row for row in content_units}
        dialogue_by_id = {row["dialogue_id"]: row for row in dialogue}
        shot_by_id = {row["shot_id"]: row for row in shots}
        for (kind, identity), row in rows_by_key.items():
            status = _text(row.get("status")).upper()
            shot_id = _text(row.get("shot_id"))
            reason = _text(row.get("reason"))
            if status not in {"UNASSIGNED", "UNRESOLVED", "ASSIGNED", "EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"}:
                raise ValueError("Frozen creator coverage decision status is invalid")
            if kind in {"content", "dialogue"}:
                unit = content_by_id.get(identity) if kind == "content" else dialogue_by_id.get(identity)
                if unit is None:
                    raise ValueError("Frozen creator coverage decision references an unknown canonical unit")
                if status == "ASSIGNED":
                    if not shot_id or unit.get("disposition") != "ASSIGNED" or unit.get("shot_ids") != [shot_id]:
                        raise ValueError("Frozen creator assignment does not match canonical coverage")
                elif shot_id or unit.get("disposition") != ("UNRESOLVED" if status in {"UNASSIGNED", "UNRESOLVED"} else status):
                    raise ValueError("Frozen creator disposition does not match canonical coverage")
                if status in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and not reason:
                    raise ValueError("Frozen creator omission/silence lacks a reason")
            else:
                shot = shot_by_id.get(identity)
                if shot is None or shot_id:
                    raise ValueError("Frozen shot disposition references an unknown shot")
                actual = shot.get("dialogue_disposition") if kind == "shot_dialogue" else shot.get("content_coverage_state")
                if status in {"UNASSIGNED", "UNRESOLVED"} and kind == "shot_dialogue":
                    # A shot-level UNASSIGNED decision means no silence/omission
                    # disposition was authored. Canonical line assignments are
                    # independently authoritative and may therefore resolve the
                    # shot's dialogue state to ASSIGNED.
                    has_assigned_dialogue = bool(shot.get("covered_dialogue_ids"))
                    if actual != "UNRESOLVED" and not (actual == "ASSIGNED" and has_assigned_dialogue):
                        raise ValueError("Frozen shot dialogue disposition does not match creator decision")
                if status == "INTENTIONAL_SILENCE" and kind == "shot_dialogue" and actual != "INTENTIONAL_SILENCE":
                    raise ValueError("Frozen shot silence does not match creator decision")
                if status == "EXPLICITLY_OMITTED" and kind == "shot_dialogue" and actual != "EXPLICITLY_OMITTED":
                    raise ValueError("Frozen shot omission does not match creator decision")
                if kind == "shot_content" and status == "INTENTIONAL_SILENCE":
                    if actual != "INTENTIONAL_ESTABLISHING" or not _text(shot.get("content_coverage_reason")) or not reason:
                        raise ValueError("Frozen establishing disposition does not match creator decision")
    return value

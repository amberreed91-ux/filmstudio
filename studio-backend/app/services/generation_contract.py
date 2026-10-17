"""Frozen provider-neutral generation contract.

RenderJobInput remains a mutable persistence/API model. This separate value
object captures approved creative inputs, uses immutable scalar/tuple members,
and is serialized with a SHA-256 integrity check. Provider execution metadata
is excluded from the contract.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


class GenerationContractError(ValueError):
    """The stored generation contract is missing, malformed, or changed."""


# One shared classification for provider/execution observations. Both frozen
# contracts and creative manifests use this set so an execution-only field
# cannot become creative state in one fingerprint path but not the other.
EXECUTION_ONLY_PARAMETER_KEYS = frozenset(
    {
        "provider", "model", "selected_provider", "provider_selection", "manifest_provider",
        "generation_context_id", "generation_contract_record", "routing_mode", "router_config_id", "router_selection", "router_execution",
        "execution_metadata", "execution_cost", "execution_costs", "cost", "cost_estimate",
        "realized_cost_credits", "provider_payload_metadata", "provider_response_normalized", "prompt_budget",
        "negative_prompt_budget", "final_provider_prompt", "pipeline", "resolved_model",
        "resolved_settings", "resolved_input", "routing_provider", "capacity_fallback",
        "no_eligible_model", "references_forwarded", "estimated_cost_credits",
        "estimated_cost", "cost_estimate", "estimated_credits", "estimated_total_credits",
        "readiness", "readiness_status", "blockers", "selected_model", "selection_reason",
        "selection_mode", "model_selection", "generation_context", "generation_contract",
        "manifest_fingerprint", "runway_task_id", "task_id", "provider_job_id",
        "creative_manifest_fingerprint", "reference_roles", "reference_videos",
        "reference_audio", "keyframes", "content_moderation", "contentModeration",
        "camera_plan", "audio_intent", "generate_audio", "negative_prompt", "duration",
        "duration_seconds", "resolution", "aspect_ratio", "ratio", "seed", "storyboard",
        "preserve_shot_prompt", "dialogue_lines", "dialogue_handoff", "storyboard_frame_url",
        "last_frame_reference_url", "use_mock_success", "reference_assets", "source_refs",
        "reference_count", "shot_id", "scene_id", "creator_shot_planning", "shot_planning",
        "frozen_reference_binding", "reference_projection_authorization", "scene_coverage", "scene_coverage_shot",
        "camera_instructions", "camera_provenance", "camera_source_digest",
        "camera_source_project_id", "camera_source_scene_id", "camera_source_shot_id",
        "camera_source_storyboard_shot_id", "camera_target_project_id", "camera_target_scene_id",
        "camera_target_shot_id", "storyboard_shot_id",
        "project_id", "storyboard_frame_identity_collision",
    }
)


# Per-shot selection/provenance metadata the pipeline resolves (R4.5-A3: all
# class (2) — the authoritative carriers scene_coverage, dialogue_handoff and
# references are frozen and verified independently at every gate). For Router
# jobs these are recorded as digest-linked selection evidence instead of
# frozen creative parameters, which the Router wire body cannot represent.
# Never applies to non-router providers.
ROUTER_SELECTION_EVIDENCE_KEYS = (
    "character_focus",
    "character_focus_ids",
    "content_coverage_disposition",
    "content_coverage_reason",
    "covered_content_ids",
    "creator_coverage_decisions",
    "dialogue_disposition",
    "dialogue_disposition_reason",
    "strict_render_settings",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def freeze_dialogue_handoff(*, scene_id: str, shot_id: str, lines: Any) -> dict[str, Any]:
    """Freeze canonical dialogue for one scene/shot with an integrity digest."""
    from app.services.dialogue_authority import filter_placeholder_lines, is_placeholder_dialogue

    if not isinstance(lines, list):
        raise GenerationContractError("Dialogue handoff lines must be an ordered list")
    normalized: list[dict[str, str]] = []
    for index, row in enumerate(lines):
        if not isinstance(row, dict):
            raise GenerationContractError(f"Dialogue handoff line {index} must be an object")
        text = row.get("text", row.get("line_text", row.get("dialogue")))
        if not isinstance(text, str) or not text.strip():
            raise GenerationContractError(f"Dialogue handoff line {index} must have non-empty text")
        row_scene = str(row.get("scene_id") or "")
        row_shot = str(row.get("shot_id") or "")
        if row_scene and row_scene != scene_id or row_shot and row_shot != shot_id:
            raise GenerationContractError("Dialogue handoff contains a row owned by another scene or shot")
        if is_placeholder_dialogue(text):
            continue
        canonical_row: dict[str, str] = {}
        for key, value in row.items():
            if value is None:
                continue
            if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
                raise GenerationContractError(f"Dialogue handoff line {index} contains unsupported fields")
            canonical_row[key] = str(value)
        canonical_row["text"] = text.strip()
        normalized.append(canonical_row)
    # Keep the authority's filtering semantics explicit at the frozen boundary.
    normalized = [dict(row) for row in filter_placeholder_lines(normalized)]
    payload = {
        "version": 1,
        "scene_id": scene_id,
        "shot_id": shot_id,
        "lines": normalized,
        "silence": not normalized,
    }
    return {"payload": payload, "sha256": hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()}


def _normalize_prompt_text(value: Any) -> str:
    """Whitespace-collapsed prompt text for containment checks."""
    return " ".join(str(value or "").split())


def _prompt_dialogue_problems(
    *,
    prompt: str,
    assigned_dialogue: list[dict[str, Any]],
    omitted_dialogue: list[dict[str, Any]],
) -> list[str]:
    """Detect silent divergence between an approved prompt and coverage truth.

    A prompt must never quote canonical dialogue that coverage records as
    omitted or unresolved. Dialogue is independently bound by the frozen
    handoff; this check rejects contradictory prompt text without requiring a
    visual prompt to repeat spoken dialogue. Callers fail closed instead of
    rewriting approved prompts.
    """
    problems: list[str] = []
    normalized_prompt = _normalize_prompt_text(prompt)
    for line in omitted_dialogue:
        text = _normalize_prompt_text(line.get("text"))
        if text and text in normalized_prompt:
            problems.append(
                f"approved prompt quotes dialogue that coverage does not assign to this shot"
                f" (unresolved or omitted line for speaker {_normalize_prompt_text(line.get('speaker'))})"
            )
    return problems


def verify_dialogue_handoff(record: Any, *, scene_id: str | None = None, shot_id: str | None = None) -> dict[str, Any]:
    """Verify the dialogue proof and reject stale, fabricated, or malformed rows."""
    from app.services.dialogue_authority import is_placeholder_dialogue

    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        raise GenerationContractError("Frozen dialogue handoff is missing or malformed")
    payload = record["payload"]
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    if record.get("sha256") != digest:
        raise GenerationContractError("Frozen dialogue handoff integrity check failed")
    if (
        payload.get("version") != 1
        or not isinstance(payload.get("scene_id"), str)
        or not isinstance(payload.get("shot_id"), str)
        or not isinstance(payload.get("lines"), list)
        or not isinstance(payload.get("silence"), bool)
    ):
        raise GenerationContractError("Frozen dialogue handoff payload is malformed")
    if scene_id is not None and payload["scene_id"] != scene_id or shot_id is not None and payload["shot_id"] != shot_id:
        raise GenerationContractError("Frozen dialogue handoff identity does not match its shot")
    if payload["silence"] is not (len(payload["lines"]) == 0):
        raise GenerationContractError("Frozen dialogue handoff silence marker does not match its lines")
    for index, row in enumerate(payload["lines"]):
        if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"].strip():
            raise GenerationContractError(f"Frozen dialogue handoff line {index} is malformed")
        if is_placeholder_dialogue(row["text"]):
            raise GenerationContractError("Frozen dialogue handoff contains fabricated placeholder dialogue")
        if row.get("scene_id") not in (None, "", payload["scene_id"]) or row.get("shot_id") not in (None, "", payload["shot_id"]):
            raise GenerationContractError("Frozen dialogue handoff contains stale shot dialogue")
    return payload


def creative_parameter_values(parameters: Any) -> dict[str, Any]:
    """Project a parameter object onto its creative, non-execution values."""
    if not isinstance(parameters, dict):
        return {}
    return {
        key: creative_parameter_value(value)
        for key, value in parameters.items()
        if key not in EXECUTION_ONLY_PARAMETER_KEYS
    }


def creative_parameter_value(value: Any) -> Any:
    """Remove nested execution observations using the shared classification."""
    if isinstance(value, dict):
        return {
            key: creative_parameter_value(item)
            for key, item in value.items()
            if key not in EXECUTION_ONLY_PARAMETER_KEYS
        }
    if isinstance(value, list):
        return [creative_parameter_value(item) for item in value]
    return value


@dataclass(frozen=True)
class GenerationReference:
    uri: str
    role: str = "reference"
    studio_role: str = "reference"
    category: str = ""
    source: str = "referenceAssets"
    ref_id: str = ""
    target_type: str = ""
    target_id: str = ""
    canonical: bool = False
    approval_state: str = "approved"
    source_kind: str = "confirmed"
    kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "uri": self.uri,
            "role": self.role,
            "studio_role": self.studio_role,
            "category": self.category,
            "source": self.source,
            "ref_id": self.ref_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "canonical": self.canonical,
            "approval_state": self.approval_state,
            "source_kind": self.source_kind,
        }
        if self.kind:
            payload["kind"] = self.kind
        return payload


@dataclass(frozen=True)
class FrozenGenerationContract:
    """Immutable creative request values; execution metadata is not accepted."""

    shot_id: str
    prompt: str
    negative_prompt: str
    references: tuple[GenerationReference, ...]
    aspect_ratio: str
    duration: int | None
    resolution: str | None
    seed: int | None
    audio: bool
    content_moderation: str | None
    camera_plan_json: str
    camera_provenance: str
    camera_source_digest: str
    camera_instructions_json: str
    camera_source_project_id: str
    camera_source_scene_id: str
    camera_source_shot_id: str
    camera_source_storyboard_shot_id: str
    camera_target_project_id: str
    camera_target_scene_id: str
    camera_target_shot_id: str
    reference_videos_json: str
    reference_audio_json: str
    keyframes_json: str
    creative_parameters_json: str
    dialogue_handoff_json: str = "{}"
    scene_coverage_json: str = "{}"
    scene_coverage_shot_json: str = "{}"
    manifest_fingerprint: str = ""

    def payload(self) -> dict[str, Any]:
        payload = {
            "contract_version": 1,
            "shot_id": self.shot_id,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "references": [reference.to_dict() for reference in self.references],
            "aspect_ratio": self.aspect_ratio,
            "duration": self.duration,
            "resolution": self.resolution,
            "seed": self.seed,
            "audio": self.audio,
            "content_moderation": self.content_moderation,
            "camera_plan": json.loads(self.camera_plan_json),
            "camera_provenance": self.camera_provenance,
            "camera_source_digest": self.camera_source_digest,
            "camera_instructions": json.loads(self.camera_instructions_json),
            "camera_source_project_id": self.camera_source_project_id,
            "camera_source_scene_id": self.camera_source_scene_id,
            "camera_source_shot_id": self.camera_source_shot_id,
            "camera_source_storyboard_shot_id": self.camera_source_storyboard_shot_id,
            "camera_target_project_id": self.camera_target_project_id,
            "camera_target_scene_id": self.camera_target_scene_id,
            "camera_target_shot_id": self.camera_target_shot_id,
            "reference_videos": json.loads(self.reference_videos_json),
            "reference_audio": json.loads(self.reference_audio_json),
            "keyframes": json.loads(self.keyframes_json),
            "creative_parameters": json.loads(self.creative_parameters_json),
            "manifest_fingerprint": self.manifest_fingerprint,
        }
        dialogue_handoff = json.loads(self.dialogue_handoff_json)
        if dialogue_handoff:
            payload["dialogue_handoff"] = dialogue_handoff
        scene_coverage = json.loads(self.scene_coverage_json)
        if scene_coverage:
            payload["scene_coverage"] = scene_coverage
        scene_coverage_shot = json.loads(self.scene_coverage_shot_json)
        if scene_coverage_shot:
            payload["scene_coverage_shot"] = scene_coverage_shot
        return payload

    def creative_digest(self) -> str:
        """Digest creative values independently of the manifest link."""
        payload = self.payload()
        payload.pop("manifest_fingerprint", None)
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def to_record(self) -> dict[str, Any]:
        payload = self.payload()
        canonical = _canonical_json(payload)
        return {"payload": payload, "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}

    @classmethod
    def from_record(cls, record: Any) -> "FrozenGenerationContract":
        if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
            raise GenerationContractError("Frozen generation contract is missing or malformed")
        payload = record["payload"]
        digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        if not isinstance(record.get("sha256"), str) or record["sha256"] != digest:
            raise GenerationContractError("Frozen generation contract integrity check failed")
        if payload.get("contract_version") != 1:
            raise GenerationContractError("Unsupported frozen generation contract version")
        refs = payload.get("references")
        if not isinstance(refs, list):
            raise GenerationContractError("Frozen generation contract references are malformed")
        if (
            not isinstance(payload.get("shot_id"), str)
            or not payload["shot_id"].strip()
            or not isinstance(payload.get("prompt"), str)
        ):
            raise GenerationContractError("Frozen generation contract identity and prompt are malformed")
        if not isinstance(payload.get("camera_plan", {}), dict):
            raise GenerationContractError("Frozen generation contract camera_plan must be an object")
        from app.services.camera_provenance import verify_camera_source_identity
        try:
            verified_camera_plan, verified_camera_provenance = verify_camera_source_identity(
                plan=payload.get("camera_plan", {}),
                provenance=payload.get("camera_provenance"),
                source_digest=payload.get("camera_source_digest"),
                target_project_id=str(payload.get("camera_target_project_id") or ""),
                target_scene_id=str(payload.get("camera_target_scene_id") or ""),
                target_shot_id=str(payload.get("camera_target_shot_id") or ""),
                source_project_id=str(payload.get("camera_source_project_id") or ""),
                source_scene_id=str(payload.get("camera_source_scene_id") or ""),
                source_shot_id=str(payload.get("camera_source_shot_id") or ""),
                source_storyboard_shot_id=str(payload.get("camera_source_storyboard_shot_id") or ""),
            )
            if verified_camera_plan != payload.get("camera_plan", {}) or verified_camera_provenance != payload.get("camera_provenance"):
                raise GenerationContractError("Frozen camera plan does not match its canonical provenance")
            if payload.get("camera_provenance") in {"APPROVED", "USER_SPECIFIED"}:
                if (
                    payload.get("camera_source_project_id") != payload.get("camera_target_project_id")
                    or payload.get("camera_source_scene_id") != payload.get("camera_target_scene_id")
                    or payload.get("camera_source_shot_id") != payload.get("camera_target_shot_id")
                ):
                    raise GenerationContractError("Frozen camera source identity does not match the selected shot")
                if payload.get("camera_provenance") == "APPROVED" and not payload.get("camera_source_storyboard_shot_id"):
                    raise GenerationContractError("Approved storyboard camera requires exact storyboard shot identity")
            if payload.get("camera_provenance") == "USER_SPECIFIED" and payload.get("camera_source_storyboard_shot_id"):
                raise GenerationContractError("Creator camera source cannot claim a storyboard shot identity")
            if payload.get("camera_target_shot_id") and payload.get("camera_target_shot_id") != payload.get("shot_id"):
                raise GenerationContractError("Frozen camera target shot does not match the contract shot")
            from app.services.camera_provenance import verify_camera_instructions

            verify_camera_instructions(
                payload.get("camera_plan", {}),
                payload.get("camera_provenance"),
                payload.get("camera_instructions", []),
            )
        except GenerationContractError:
            raise
        for field in ("reference_videos", "reference_audio", "keyframes"):
            value = payload.get(field, [])
            if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                raise GenerationContractError(f"Frozen generation contract {field} must be a list of objects")
        if not isinstance(payload.get("creative_parameters", {}), dict):
            raise GenerationContractError("Frozen generation contract creative_parameters must be an object")
        dialogue_handoff = payload.get("dialogue_handoff")
        if dialogue_handoff:
            verify_dialogue_handoff(dialogue_handoff, shot_id=payload.get("shot_id"))
        scene_coverage = payload.get("scene_coverage")
        scene_coverage_shot = payload.get("scene_coverage_shot")
        if scene_coverage is not None:
            from app.services.scene_coverage_contract import verify_scene_coverage_contract
            try:
                verify_scene_coverage_contract(scene_coverage)
            except ValueError as exc:
                raise GenerationContractError(f"Frozen scene coverage is invalid: {exc}") from exc
            coverage_shots = [row for row in scene_coverage.get("shots", []) if row.get("shot_id") == payload.get("shot_id")]
            if len(coverage_shots) != 1 or scene_coverage_shot != coverage_shots[0]:
                raise GenerationContractError("Frozen scene coverage does not contain exactly one matching shot contract")
            if any(not isinstance(row, dict) for row in refs):
                raise GenerationContractError("Frozen generation contract reference entry is malformed")
            # The frozen handoff must name exactly the dialogue obligations this
            # shot covers — no unassigned, omitted, or foreign line may pass.
            dialogue_handoff = payload.get("dialogue_handoff") or {}
            handoff_line_ids = {
                str(row.get("line_id") or "") for row in dialogue_handoff.get("payload", {}).get("lines", [])
                if isinstance(row, dict)
            }
            covered_ids = {str(row) for row in (scene_coverage_shot.get("covered_dialogue_ids") or [])}
            if handoff_line_ids != covered_ids:
                raise GenerationContractError(
                    "Frozen dialogue handoff does not match the dialogue covered by this shot"
                )
            coverage_binding = coverage_shots[0].get("approved_reference_bindings")
            if not isinstance(coverage_binding, list) or any(not isinstance(row, dict) for row in coverage_binding):
                raise GenerationContractError("Frozen shot coverage approved reference bindings are malformed")
            canonical_refs = [
                {
                    "ref_id": ref.get("ref_id", ""),
                    "uri": ref.get("uri", ""),
                    "target_type": ref.get("target_type", ""),
                    "target_id": ref.get("target_id", ""),
                    "role": ref.get("studio_role", ref.get("role", "")),
                    "category": ref.get("category", ""),
                    "canonical": ref.get("canonical", False),
                    "approval_state": ref.get("approval_state", ""),
                    "source_kind": ref.get("source_kind", ""),
                    "kind": ref.get("kind", ""),
                }
                for ref in refs if isinstance(ref, dict) and ref.get("source") == "canonical_reference_binding"
            ]
            canonical_refs = [
                {**row, "role": coverage_row.get("role")}
                for row, coverage_row in zip(canonical_refs, coverage_binding)
            ]
            from app.services.reference_validation import (
                reference_binding_coverage_projection,
                verify_shot_reference_coverage_binding,
            )
            try:
                verify_shot_reference_coverage_binding(
                    actual_binding=reference_binding_coverage_projection(canonical_refs),
                    coverage_shot=coverage_shots[0],
                )
            except ValueError as exc:
                raise GenerationContractError(str(exc)) from exc
            contract_shot_ids = set(coverage_shots[0].get("covered_content_ids", []))
            contract_dialogue_ids = set(coverage_shots[0].get("covered_dialogue_ids", []))
            if not contract_shot_ids.issubset({row.get("content_id") for row in scene_coverage.get("content_units", [])}):
                raise GenerationContractError("Frozen shot coverage references content outside its scene")
            if not contract_dialogue_ids.issubset({row.get("dialogue_id") for row in scene_coverage.get("dialogue", [])}):
                raise GenerationContractError("Frozen shot coverage references dialogue outside its scene")
        elif scene_coverage_shot:
            raise GenerationContractError("Frozen per-shot coverage cannot exist without the scene coverage contract")
        for field in ("resolution", "content_moderation", "manifest_fingerprint"):
            value = payload.get(field)
            if value is not None and not isinstance(value, str):
                raise GenerationContractError(f"Frozen generation contract {field} must be a string or null")
        if payload.get("manifest_fingerprint") is not None and payload["manifest_fingerprint"] and not payload["manifest_fingerprint"].strip():
            raise GenerationContractError("Frozen generation contract manifest fingerprint is malformed")
        if any(
            not isinstance(row.get("uri"), str) or not row["uri"].strip()
            or any(not isinstance(row.get(key, ""), str) for key in ("role", "studio_role", "category", "source", "ref_id", "target_type", "target_id", "approval_state", "source_kind", "kind"))
            or not isinstance(row.get("canonical", False), bool)
            for row in refs if isinstance(row, dict)
        ):
            raise GenerationContractError("Frozen generation contract reference fields are malformed")
        if any(not isinstance(row, dict) for row in refs):
            raise GenerationContractError("Frozen generation contract reference entry is malformed")
        if not isinstance(payload.get("negative_prompt", ""), str):
            raise GenerationContractError("Frozen generation contract negative prompt must be a string")
        if not isinstance(payload.get("aspect_ratio"), str) or not isinstance(payload.get("audio"), bool):
            raise GenerationContractError("Frozen generation contract aspect ratio/audio values are malformed")
        for field in ("duration", "seed"):
            value = payload.get(field)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
                raise GenerationContractError(f"Frozen generation contract {field} must be an integer or null")
        try:
            return cls(
                shot_id=str(payload["shot_id"]),
                prompt=str(payload["prompt"]),
                negative_prompt=str(payload.get("negative_prompt", "")),
                references=tuple(GenerationReference(**row) for row in refs),
                aspect_ratio=str(payload["aspect_ratio"]),
                duration=payload.get("duration"),
                resolution=payload.get("resolution"),
                seed=payload.get("seed"),
                audio=payload["audio"],
                content_moderation=payload.get("content_moderation"),
                camera_plan_json=_canonical_json(payload.get("camera_plan", {})),
                camera_provenance=str(payload.get("camera_provenance") or ""),
                camera_source_digest=str(payload.get("camera_source_digest") or ""),
                camera_instructions_json=_canonical_json(payload.get("camera_instructions", [])),
                camera_source_project_id=str(payload.get("camera_source_project_id") or ""),
                camera_source_scene_id=str(payload.get("camera_source_scene_id") or ""),
                camera_source_shot_id=str(payload.get("camera_source_shot_id") or ""),
                camera_source_storyboard_shot_id=str(payload.get("camera_source_storyboard_shot_id") or ""),
                camera_target_project_id=str(payload.get("camera_target_project_id") or ""),
                camera_target_scene_id=str(payload.get("camera_target_scene_id") or ""),
                camera_target_shot_id=str(payload.get("camera_target_shot_id") or ""),
                reference_videos_json=_canonical_json(payload.get("reference_videos", [])),
                reference_audio_json=_canonical_json(payload.get("reference_audio", [])),
                keyframes_json=_canonical_json(payload.get("keyframes", [])),
                creative_parameters_json=_canonical_json(payload.get("creative_parameters", {})),
                dialogue_handoff_json=_canonical_json(dialogue_handoff or {}),
                scene_coverage_json=_canonical_json(scene_coverage or {}),
                scene_coverage_shot_json=_canonical_json(scene_coverage_shot or {}),
                manifest_fingerprint=str(payload.get("manifest_fingerprint") or ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GenerationContractError(f"Frozen generation contract is malformed: {exc}") from exc


def _reference_uri(value: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(value, str):
        return value, {}
    if isinstance(value, dict):
        uri = next((value.get(key) for key in ("image_url", "url", "uri", "asset_url") if value.get(key)), "")
        return str(uri or ""), value
    return "", {}


def _studio_reference_role(raw: dict[str, Any], fallback: Any = None) -> tuple[str, str, str]:
    explicit_role = raw.get("studio_role") or raw.get("reference_role")
    explicit = explicit_role or fallback
    # Category is an independent part of the canonical reference identity.
    # Do not synthesize it from kind: the frozen binding and shot coverage must
    # retain their exact category (including an intentionally empty one).
    category = str(raw.get("category") or "").strip()
    semantic_category = category or str(raw.get("kind") or "").strip()
    token = str(explicit or "").strip().lower().replace("-", "_").replace(" ", "_")
    if token in {"storyboard", "storyboard_frame", "first", "first_frame"}:
        return "storyboard", "first", category
    if token in {"storyboard_last", "last_frame", "last"}:
        return "storyboard_last", "last", category
    if token in {"", "reference", "generic"} and (not category or explicit_role):
        return "reference", "reference", category
    # Distinct Studio roles/categories are retained and rejected if Runway's
    # schema lacks an equivalent; they are never flattened into generic refs.
    semantic = semantic_category if token in {"", "reference", "generic"} else token
    return semantic or "reference", "reference", category


def _audio_enabled(parameters: dict[str, Any]) -> bool:
    def parse(value: Any, field: str) -> bool:
        if isinstance(value, bool):
            return value
        token = str(value).strip().lower()
        if token in {"none", "off", "disabled", "no_audio"}:
            return False
        if token in {"generate", "generated", "on", "enabled", "audio"}:
            return True
        raise GenerationContractError(
            f"Approved {field} cannot be represented as an on/off video-audio choice"
        )

    explicit = []
    if "generate_audio" in parameters:
        explicit.append(parse(parameters["generate_audio"], "generate_audio"))
    if parameters.get("audio_intent") is not None:
        explicit.append(parse(parameters["audio_intent"], "audio_intent"))
    if len(set(explicit)) > 1:
        raise GenerationContractError("Approved audio_intent and generate_audio values conflict")
    return explicit[0] if explicit else False


def freeze_generation_contract(
    *,
    shot_id: str,
    prompt: str,
    negative_prompt: str = "",
    reference_assets: list[Any] | None = None,
    parameters: dict[str, Any] | None = None,
    consistency_payload: Any = None,
    manifest_fingerprint: str = "",
    dialogue_handoff: dict[str, Any] | None = None,
    scene_coverage: dict[str, Any] | None = None,
    scene_coverage_shot: dict[str, Any] | None = None,
) -> FrozenGenerationContract:
    """Snapshot approved values in input order without mutating their source."""
    params = dict(parameters or {})
    raw_assets = list(reference_assets or [])
    aligned_roles = params.get("reference_roles")
    if aligned_roles is None:
        aligned_roles = []
    if not isinstance(aligned_roles, list):
        raise GenerationContractError("Approved reference_roles must be an ordered list")
    if len(aligned_roles) > len(raw_assets):
        raise GenerationContractError("Approved reference_roles contains roles without corresponding references")
    storyboard_url = params.get("storyboard_frame_url")
    last_frame_url = params.get("last_frame_reference_url")
    for label, value in (("storyboard_frame_url", storyboard_url), ("last_frame_reference_url", last_frame_url)):
        if value is not None and not isinstance(value, str):
            raise GenerationContractError(f"Approved {label} must be a URI string")
    references: list[GenerationReference] = []
    storyboard_seen = False

    for index, item in enumerate(raw_assets):
        uri, raw = _reference_uri(item)
        if not uri:
            raise GenerationContractError(f"Approved reference at index {index} has no URI")
        role_fallback = aligned_roles[index] if index < len(aligned_roles) else None
        studio_role, router_role, category = _studio_reference_role(raw, role_fallback)
        # A canonical identity anchor (approved character/setting reference)
        # keeps its identity role even when its URI equals the board frame URL;
        # composition conditioning is appended separately below so the frozen
        # contract carries both provenances without conflating them.
        is_identity_anchor = bool(raw.get("canonical")) and raw.get("target_type") in {"character", "setting"}
        if storyboard_url and uri == storyboard_url and not is_identity_anchor:
            studio_role, router_role, category = "storyboard", "first", category or "storyboard"
            storyboard_seen = True
        elif last_frame_url and uri == last_frame_url:
            studio_role, router_role, category = "storyboard_last", "last", category or "storyboard_last"
        references.append(GenerationReference(
            uri=uri, role=router_role, studio_role=studio_role, category=category,
            source=str(raw.get("source") or "referenceAssets"), ref_id=str(raw.get("ref_id") or ""),
            target_type=str(raw.get("target_type") or ""), target_id=str(raw.get("target_id") or ""),
            canonical=bool(raw.get("canonical", False)), approval_state=str(raw.get("approval_state") or "approved"),
            source_kind=str(raw.get("source_kind") or "confirmed"),
            kind=str(raw.get("kind") or ""),
        ))
    if storyboard_url and not storyboard_seen:
        references.append(GenerationReference(
            uri=str(storyboard_url), role="first", studio_role="storyboard", category="storyboard",
            source="storyboard_frame_url",
        ))
    if last_frame_url and not any(row.uri == last_frame_url for row in references):
        references.append(GenerationReference(
            uri=str(last_frame_url), role="last", studio_role="storyboard_last", category="storyboard_last",
            source="last_frame_reference_url",
        ))

    cp_refs = getattr(consistency_payload, "refs", None)
    if cp_refs is None and isinstance(consistency_payload, dict):
        cp_refs = consistency_payload.get("refs")
    for index, item in enumerate(cp_refs or []):

        raw = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        if not isinstance(raw, dict):
            raise GenerationContractError(f"Approved consistency reference at index {index} is malformed")
        uri, raw = _reference_uri(raw)
        if not uri:
            raise GenerationContractError(f"Approved consistency reference at index {index} has no URI")
        studio_role, router_role, category = _studio_reference_role(raw)
        references.append(GenerationReference(
            uri=uri, role=router_role, studio_role=studio_role, category=category,
            source=str(raw.get("source") or "consistency_payload"), ref_id=str(raw.get("ref_id") or ""),
            target_type=str(raw.get("target_type") or ""), target_id=str(raw.get("target_id") or ""),
            canonical=bool(raw.get("canonical", False)), approval_state=str(raw.get("approval_state") or "approved"),
            source_kind=str(raw.get("source_kind") or "confirmed"),
            kind=str(raw.get("kind") or ""),
        ))

    def integer(key: str, *fallbacks: str) -> int | None:
        value = next((params.get(name) for name in (key, *fallbacks) if params.get(name) is not None), None)
        if value is None:
            return None
        if isinstance(value, bool):
            raise GenerationContractError(f"Approved {key} must be an integer")
        try:
            parsed = int(value)
            if isinstance(value, float) and value != parsed:
                raise ValueError("fractional value")
            if isinstance(value, str) and str(parsed) != value.strip():
                raise ValueError("non-canonical integer")
            return parsed
        except (TypeError, ValueError) as exc:
            raise GenerationContractError(f"Approved {key} must be an integer") from exc

    ratio = params.get("aspect_ratio", params.get("ratio", "16:9"))
    if not isinstance(ratio, str) or not ratio.strip():
        raise GenerationContractError("Approved aspect ratio must be a non-empty string")
    ratio = ratio.strip()
    resolution = params.get("resolution")
    if resolution is not None and (not isinstance(resolution, str) or not resolution.strip()):
        raise GenerationContractError("Approved resolution must be a non-empty string")
    moderation = params.get("content_moderation", params.get("contentModeration"))
    if moderation is not None and (not isinstance(moderation, str) or moderation not in {"low", "standard"}):
        raise GenerationContractError("Approved content moderation setting must be 'low' or 'standard'")

    from app.services.camera_provenance import (
        CAMERA_PROVENANCE_AI,
        CAMERA_PROVENANCE_CREATOR,
        CAMERA_PROVENANCE_STORYBOARD,
        CAMERA_PROVENANCE_UNSPECIFIED,
        camera_plan_digest,
        verify_camera_source_identity,
        canonical_camera_plan,
        canonical_camera_instructions,
        verify_camera_instructions,
    )

    camera_plan = canonical_camera_plan(params.get("camera_plan", {}))
    camera_provenance = params.get("camera_provenance", CAMERA_PROVENANCE_UNSPECIFIED)
    raw_camera_instructions = params.get("camera_instructions")
    camera_source_project_id = str(params.get("camera_source_project_id") or "")
    camera_source_scene_id = str(params.get("camera_source_scene_id") or "")
    camera_source_shot_id = str(params.get("camera_source_shot_id") or "")
    camera_source_storyboard_shot_id = str(params.get("camera_source_storyboard_shot_id") or "")
    camera_target_project_id = str(params.get("camera_target_project_id") or "")
    camera_target_scene_id = str(params.get("camera_target_scene_id") or "")
    camera_target_shot_id = str(params.get("camera_target_shot_id") or "")
    if camera_provenance not in {
        CAMERA_PROVENANCE_STORYBOARD,
        CAMERA_PROVENANCE_CREATOR,
        CAMERA_PROVENANCE_UNSPECIFIED,
        CAMERA_PROVENANCE_AI,
    }:
        raise GenerationContractError("Camera provenance classification is missing or invalid")
    expected_camera_source_digest = camera_plan_digest(
        camera_plan,
        camera_provenance,
        source_project_id=camera_source_project_id,
        source_scene_id=camera_source_scene_id,
        source_shot_id=camera_source_shot_id,
        source_storyboard_shot_id=camera_source_storyboard_shot_id,
    )
    supplied_camera_source_digest = params.get("camera_source_digest")
    if supplied_camera_source_digest is not None and supplied_camera_source_digest != expected_camera_source_digest:
        raise GenerationContractError("Supplied camera provenance digest does not match the camera plan and source")
    camera_source_digest = expected_camera_source_digest
    if camera_target_shot_id and camera_target_shot_id != str(shot_id):
        raise GenerationContractError("Frozen camera target shot does not match the contract shot")
    verified_camera_plan, verified_camera_provenance = verify_camera_source_identity(
        plan=camera_plan,
        provenance=camera_provenance,
        source_digest=camera_source_digest,
        target_project_id=camera_target_project_id,
        target_scene_id=camera_target_scene_id,
        target_shot_id=camera_target_shot_id,
        source_project_id=camera_source_project_id,
        source_scene_id=camera_source_scene_id,
        source_shot_id=camera_source_shot_id,
        source_storyboard_shot_id=camera_source_storyboard_shot_id,
    )
    camera_plan = verified_camera_plan
    camera_provenance = verified_camera_provenance
    if raw_camera_instructions is None:
        raw_camera_instructions = canonical_camera_instructions(camera_plan, camera_provenance)
    camera_instructions = _canonical_json(
        verify_camera_instructions(camera_plan, camera_provenance, raw_camera_instructions)
    )

    def ordered_objects(key: str) -> str:
        value = params.get(key)
        if value is None:
            value = []
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise GenerationContractError(f"Approved {key} must be an ordered list of objects")
        return _canonical_json(value)
    creative_params = creative_parameter_values(params)
    if dialogue_handoff is not None:
        verify_dialogue_handoff(dialogue_handoff, shot_id=shot_id)
    if scene_coverage is not None:
        from app.services.scene_coverage_contract import verify_scene_coverage_contract
        try:
            verify_scene_coverage_contract(scene_coverage)
        except ValueError as exc:
            raise GenerationContractError(f"Scene coverage is unresolved: {exc}") from exc
        matches = [row for row in scene_coverage.get("shots", []) if row.get("shot_id") == shot_id]
        if len(matches) != 1:
            raise GenerationContractError("Scene coverage does not contain exactly one generation shot")
        if scene_coverage_shot is not None and scene_coverage_shot != matches[0]:
            raise GenerationContractError("Per-shot scene coverage does not match the scene coverage contract")
        scene_coverage_shot = matches[0]
        # Prompt consistency: an approved prompt must not quote canonical
        # dialogue that coverage does not assign to this shot (unresolved or
        # explicitly omitted material). Divergence is exposed as a blocking
        # integrity error — approved prompts are never silently rewritten.
        covered_dialogue_ids = {str(row) for row in (scene_coverage_shot.get("covered_dialogue_ids") or [])}
        prompt_problems = _prompt_dialogue_problems(
            prompt=prompt,
            assigned_dialogue=[],
            omitted_dialogue=[
                line for line in scene_coverage.get("dialogue") or []
                if line.get("dialogue_id") not in covered_dialogue_ids
            ],
        )
        if prompt_problems:
            raise GenerationContractError(
                "Approved prompt and scene coverage disagree: " + "; ".join(prompt_problems)
            )
        coverage_binding = scene_coverage_shot.get("approved_reference_bindings")
        if not isinstance(coverage_binding, list) or any(not isinstance(row, dict) for row in coverage_binding):
            raise GenerationContractError("Frozen shot coverage approved reference bindings are malformed")
        canonical_refs = [
            {
                "ref_id": reference.ref_id,
                "uri": reference.uri,
                "target_type": reference.target_type,
                "target_id": reference.target_id,
                "role": reference.studio_role,
                "category": reference.category,
                "canonical": reference.canonical,
                "approval_state": reference.approval_state,
                "source_kind": reference.source_kind,
                "kind": reference.kind,
            }
            for reference in references if reference.source == "canonical_reference_binding"
        ]
        canonical_refs = [
            {**row, "role": coverage_row.get("role")}
            for row, coverage_row in zip(canonical_refs, coverage_binding)
        ]
        from app.services.reference_validation import (
            reference_binding_coverage_projection,
            verify_shot_reference_coverage_binding,
        )
        try:
            verify_shot_reference_coverage_binding(
                actual_binding=reference_binding_coverage_projection(canonical_refs),
                coverage_shot=scene_coverage_shot,
                allow_missing=True,
            )
        except ValueError as exc:
            raise GenerationContractError(str(exc)) from exc
        # Record a storyboard-frame identity collision in the frozen per-shot
        # coverage: the approved board frame is bound both as composition
        # conditioning and as a canonical identity anchor. This is a provenance
        # record only — approved creative state and reference roles are not
        # rewritten here.
        params_storyboard_url = params.get("storyboard_frame_url")
        if params_storyboard_url:
            collided = [
                row for row in scene_coverage_shot.get("approved_reference_bindings") or []
                if row.get("target_type") in {"character", "setting"}
                and str(row.get("uri") or "") == str(params_storyboard_url)
            ]
            if collided:
                scene_coverage_shot = {
                    **scene_coverage_shot,
                    "storyboard_frame_identity_collision": {
                        "uri": str(params_storyboard_url),
                        "composition_source": "storyboard_frame_url",
                        "identity_refs": collided,
                        "detail": (
                            "the approved storyboard frame is also bound as a canonical"
                            " identity reference; composition conditioning and identity"
                            " anchoring are distinct provenances"
                        ),
                    },
                }
                scene_coverage = {
                    **scene_coverage,
                    "shots": [
                        scene_coverage_shot if row.get("shot_id") == shot_id else row
                        for row in scene_coverage.get("shots", [])
                    ],
                }
        # Prove the frozen handoff corresponds to the dialogue THIS shot covers:
        # the handoff's line identities must equal the shot's covered dialogue
        # obligations. Unassigned, omitted, or foreign lines can never pass.
        handoff_line_ids = {
            str(row.get("line_id") or "") for row in (dialogue_handoff or {}).get("payload", {}).get("lines", [])
            if isinstance(row, dict)
        }
        covered_ids = {str(row) for row in (scene_coverage_shot.get("covered_dialogue_ids") or [])}
        if handoff_line_ids != covered_ids:
            raise GenerationContractError(
                "Frozen dialogue handoff does not match the dialogue covered by this shot"
            )
    elif scene_coverage_shot is not None:
        raise GenerationContractError("Per-shot scene coverage requires the scene coverage contract")
    return FrozenGenerationContract(
        shot_id=str(shot_id), prompt=str(prompt), negative_prompt=str(negative_prompt or ""),
        references=tuple(references),
        aspect_ratio=ratio,

        duration=integer("duration", "duration_seconds"),
        resolution=resolution.strip() if resolution is not None else None,
        seed=integer("seed"), audio=_audio_enabled(params),
        content_moderation=moderation,
        camera_plan_json=_canonical_json(camera_plan),
        camera_provenance=str(camera_provenance),
        camera_source_digest=camera_source_digest,
        camera_instructions_json=camera_instructions,
        camera_source_project_id=camera_source_project_id,
        camera_source_scene_id=camera_source_scene_id,
        camera_source_shot_id=camera_source_shot_id,
        camera_source_storyboard_shot_id=camera_source_storyboard_shot_id,
        camera_target_project_id=camera_target_project_id,
        camera_target_scene_id=camera_target_scene_id,
        camera_target_shot_id=camera_target_shot_id,
        reference_videos_json=ordered_objects("reference_videos"),

        reference_audio_json=ordered_objects("reference_audio"),
        keyframes_json=ordered_objects("keyframes"),
        creative_parameters_json=_canonical_json(creative_params),
        dialogue_handoff_json=_canonical_json(dialogue_handoff or {}),
        scene_coverage_json=_canonical_json(scene_coverage or {}),
        scene_coverage_shot_json=_canonical_json(scene_coverage_shot or {}),
        manifest_fingerprint=manifest_fingerprint,
    )

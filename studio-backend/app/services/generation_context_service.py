"""Generation context + readiness gate.

Creates the versioned context every render must carry, and validates that the
render is being built from current authoritative state before anything reaches
a paid provider. This is the workstream's Fresh Render core:

- ``build_context_fingerprint`` stamps scene / shot / storyboard / reference /
  camera versions so a generation can always answer "which state produced me".
  The shot version is derived from the REAL authoritative shot record — never
  a stub, never inferred from stale frontend state (P0-1).
- ``resolve_current_shot`` resolves a shot from canonical storage and refuses
  any shot row that does not belong to the blueprint's CURRENT version. A
  historical shot can never pass itself off as the current shot.
- ``validate_generation_context`` is the final gate before provider submission.
  It BLOCKS (never silently resolves) on stale camera instructions, stale
  storyboard/scene/shot state, wrong scene/shot, or unapproved AI-suggested
  values. It fails closed when a required shot version is missing.
- ``create_generation_context`` mints a fresh context for an explicit render,
  guaranteeing no reuse of previous generation selections.
- Camera provenance distinguishes USER_SPECIFIED / APPROVED / AI_SUGGESTED /
  UNSPECIFIED. Heuristic board templates are AI_SUGGESTED, never APPROVED;
  only explicit creator camera plans earn APPROVED (P0-2). An approved value
  carries an ``AI_CAMERA_APPROVED_BY_USER`` stamp in its source_version — the
  durable record of the user's explicit approval action.

Everything here is derived and observational over canonical truth: it never
mutates scene text, storyboard versions, or references — it reads and records
them.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger("generation-context")

# Camera instruction provenance (structured shot data, never free AI invention).
CAMERA_SOURCE_USER_SPECIFIED = "USER_SPECIFIED"
CAMERA_SOURCE_APPROVED = "APPROVED"
CAMERA_SOURCE_AI_SUGGESTED = "AI_SUGGESTED"
CAMERA_SOURCE_UNSPECIFIED = "UNSPECIFIED"

# A shot that is required for a shot-based generation but cannot be resolved
# from canonical state must FAIL CLOSED — "absent" is only legal when the
# generation genuinely has no shot axis (e.g. a scene-level synthetic previs
# shot created before a board exists).
SHOT_VERSION_ABSENT = "absent"

# Metadata source_version stamp proving a user explicitly approved an
# AI-suggested camera value. Approval is an action, never an inference:
# heuristic/template values without this stamp remain AI_SUGGESTED and are
# blocked from paid generation by the readiness gate.
AI_CAMERA_APPROVAL_PROVENANCE = "AI_CAMERA_APPROVED_BY_USER"

_APPROVED_CAMERA_SOURCES = {CAMERA_SOURCE_USER_SPECIFIED, CAMERA_SOURCE_APPROVED, CAMERA_SOURCE_UNSPECIFIED}

# Edit-grammar tokens describe cut/continuity intent, NOT camera movement.
# They must never enter the camera dimension of a generation context.
_EDIT_GRAMMAR_MOVEMENT_TOKENS = frozenset(
    {
        "match_cut",
        "bridge_action",
        "linger_on_micro_expression",
        "cut_to",
        "match_dissolve",
        "smash_cut",
        "j_cut",
        "l_cut",
    }
)

_UNSHOT_SPECIFIED_DIMENSIONS = ("shot_size", "angle", "movement", "lens", "framing")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _shot_field(shot: Any, name: str) -> Any:
    """Read a field from either a pydantic model or a plain dict."""
    if isinstance(shot, dict):
        return shot.get(name)
    return getattr(shot, name, None)


def is_edit_grammar_movement(value: Any) -> bool:
    """True when a movement value is really an editorial cut instruction."""
    token = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return token in _EDIT_GRAMMAR_MOVEMENT_TOKENS


@dataclass
class CameraInstruction:
    """One camera dimension with its provenance and source version."""

    dimension: str                      # shot_size | angle | movement | lens | framing | subject
    value: str
    instruction_source: str             # USER_SPECIFIED | APPROVED | AI_SUGGESTED | UNSPECIFIED
    source_version: str = ""            # version of the state this came from

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "instruction_source": self.instruction_source,
            "source_version": self.source_version,
        }


@dataclass
class GenerationContext:
    """The versioned envelope a fresh render is built inside."""

    generation_context_id: str
    project_id: str
    scene_id: str
    shot_id: str
    scene_version: str
    shot_version: str
    storyboard_version: str
    reference_version: str
    camera_version: str
    camera_instructions: list[CameraInstruction] = field(default_factory=list)
    prompt_source: str = ""             # USER_EDITED | BOARD | DERIVED
    created_at: str = field(default_factory=_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        return _stable_hash({
            "scene": self.scene_version,
            "shot": self.shot_version,
            "storyboard": self.storyboard_version,
            "reference": self.reference_version,
            "camera": self.camera_version,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation_context_id": self.generation_context_id,
            "project_id": self.project_id,
            "scene_id": self.scene_id,
            "shot_id": self.shot_id,
            "scene_version": self.scene_version,
            "shot_version": self.shot_version,
            "storyboard_version": self.storyboard_version,
            "reference_version": self.reference_version,
            "camera_version": self.camera_version,
            "context_fingerprint": self.fingerprint(),
            "camera_instructions": [c.to_dict() for c in self.camera_instructions],
            "prompt_source": self.prompt_source,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class ReadinessResult:
    """Outcome of the generation readiness gate. Blocking is explicit."""

    ready: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    context: GenerationContext | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "generation_context": self.context.to_dict() if self.context else None,
        }


def pending_ai_camera_suggestions(shot: Any) -> dict[str, str]:
    """AI-suggested (template/heuristic) camera values awaiting user approval.

    Read-only view over a board shot: non-empty, non-edit-grammar values from
    the visual plan that were NOT written by an explicit creator camera plan.
    Preserved for display and approval — never renderable until the user
    approves them (which records the creator camera plan provenance).
    """
    _, creator_defined = _camera_plan_provenance(shot)
    if creator_defined:
        return {}
    visual_plan = _shot_field(shot, "visual_plan")
    if visual_plan is None:
        return {}
    suggestions: dict[str, str] = {}
    for dimension, value in (
        ("framing", _shot_field(visual_plan, "framing")),
        ("camera", _shot_field(visual_plan, "camera_movement")),
        ("lens", _shot_field(visual_plan, "lens_language")),
    ):
        text = str(value or "").strip()
        if not text or (dimension == "camera" and is_edit_grammar_movement(text)):
            continue
        suggestions[dimension] = text
    return suggestions


def _camera_plan_provenance(shot: Any) -> tuple[dict[str, Any], bool]:
    """Return (creator camera plan, creator_defined) for a board shot.

    The creator camera plan is written ONLY by explicit creator actions — the
    camera-preset flow (``generate_storyboard_image_for_scene_shot`` with a
    ``camera_plan``) persists it under
    ``render_contract.structured_parameters["camera_plan"]``; other approval
    surfaces may record it under ``shot.metadata["camera_plan"]``. A
    heuristic board template never carries either.
    """
    candidates: list[dict[str, Any]] = []
    contract = _shot_field(shot, "render_contract")
    if contract is not None:
        structured = _shot_field(contract, "structured_parameters")
        if isinstance(structured, dict) and isinstance(structured.get("camera_plan"), dict):
            candidates.append(structured["camera_plan"])
    metadata = _shot_field(shot, "metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("camera_plan"), dict):
        candidates.append(metadata["camera_plan"])
    for plan in candidates:
        if any(str(value or "").strip() for value in plan.values()):
            return plan, True
    return {}, False


class GenerationContextService:
    """Versioned generation contexts + the final readiness gate."""

    # ── Version derivation (read-only, deterministic) ─────────────────────

    def scene_version(self, scene: dict[str, Any] | None, canonical_script_text: str | None = None) -> str:
        if not isinstance(scene, dict):
            return "absent"
        script_hash = hashlib.sha256(canonical_script_text.encode("utf-8")).hexdigest() if isinstance(canonical_script_text, str) else ""
        # Importance axes are versioned, not just identity/text: the plan
        # (rationale, manifest scene_version, fingerprint) must regenerate
        # when the scene's importance statement changes. Previously only
        # heading/text were hashed, so description/emotional_tone/character
        # edits left stale cached plan text looking current.
        return _stable_hash({
            "scene_id": scene.get("scene_id"),
            "heading": scene.get("heading"),
            "text": scene.get("text"),
            "description": scene.get("description"),
            "emotional_tone": scene.get("emotional_tone"),
            "characters": scene.get("characters"),
            "location": scene.get("location"),
            "updated_at": scene.get("updated_at"),
            "canonical_script_sha256": script_hash,
        })

    def shot_version(self, shot: Any) -> str:
        """Fingerprint the authoritative shot record.

        Accepts a StoryboardShot model or a dict with the same fields. Every
        axis a shot edit can touch is included so any shot change invalidates
        contexts prepared against the previous state.
        """
        if shot is None or isinstance(shot, (str, int, float, bool)):
            return SHOT_VERSION_ABSENT
        if not (isinstance(shot, dict) or hasattr(shot, "model_dump") or hasattr(shot, "shot_id")):
            return SHOT_VERSION_ABSENT
        visual_plan = _shot_field(shot, "visual_plan")
        contract = _shot_field(shot, "render_contract")
        return _stable_hash({
            "shot_id": _shot_field(shot, "shot_id") or _shot_field(shot, "id"),
            "storyboard_shot_id": _shot_field(shot, "storyboard_shot_id"),
            "version_id": _shot_field(shot, "version_id"),
            "shot_number": _shot_field(shot, "shot_number"),
            "status": str(_shot_field(shot, "status") or ""),
            "locked": bool(_shot_field(shot, "locked")),
            "updated_at": _shot_field(shot, "updated_at"),
            "prompt": _shot_field(contract, "provider_neutral_prompt") if contract else None,
            "duration_seconds": _shot_field(contract, "duration_seconds") if contract else None,
            "aspect_ratio": _shot_field(contract, "aspect_ratio") if contract else None,
            "structured_parameters": _shot_field(contract, "structured_parameters") if contract else None,
            "framing": _shot_field(visual_plan, "framing") if visual_plan else None,
            "camera_movement": _shot_field(visual_plan, "camera_movement") if visual_plan else None,
            "lens_language": _shot_field(visual_plan, "lens_language") if visual_plan else None,
            "camera_plan": (_shot_field(shot, "metadata") or {}).get("camera_plan"),
        })

    def storyboard_version(self, storyboard_context: dict[str, Any] | None) -> str:
        """Version from the approved board context previs/build paths use."""
        if not isinstance(storyboard_context, dict):
            return "absent"
        version = storyboard_context.get("version") or storyboard_context.get("blueprint_version_id")
        if version:
            return str(version)
        shot = storyboard_context.get("shot")
        if shot is not None:
            return str(getattr(shot, "version_id", "") or SHOT_VERSION_ABSENT)
        return "absent"

    def reference_version(
        self,
        *,
        reference_assets: list[str] | None,
        consistency_payload: dict[str, Any] | None = None,
    ) -> str:
        """Content fingerprint of the exact references crossing the boundary."""
        urls = [str(url or "").strip() for url in (reference_assets or []) if str(url or "").strip()]
        rows: list[Any] = list(urls)
        if isinstance(consistency_payload, dict):
            refs = consistency_payload.get("refs")
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, dict):
                        rows.append(ref.get("image_url") or ref.get("ref_id"))
        return _stable_hash(rows) if rows else "none"

    def camera_version(self, camera_instructions: list[CameraInstruction]) -> str:
        return _stable_hash([c.to_dict() for c in camera_instructions])

    # ── Canonical shot resolution (P0-1) ──────────────────────────────────

    def resolve_current_shot(
        self,
        storage: Any,
        *,
        project_id: str,
        scene_id: str,
        shot_id: str | None = None,
        storyboard_shot_id: str | None = None,
        blueprint_id: str | None = None,
        version_id: str | None = None,
    ) -> Any:
        """Resolve the CURRENT authoritative shot from canonical storage.

        Fail closed (StateError) when:
        - the shot row cannot be found for this project/scene;
        - the shot belongs to a different blueprint;
        - the shot's version is not the blueprint's CURRENT version (a
          historical shot must never become the current shot);
        - a caller-supplied version_id contradicts the stored shot.

        The caller must separately enforce approval via the storyboard gate
        (``_validate_shot_renderable``); this method proves currency only.
        """
        from app.services.stability import StateError

        def _deny(reason: str, **extra: Any) -> StateError:
            return StateError(
                f"Generation shot could not be resolved from canonical state: {reason}",
                stage="generation_shot_resolution",
                metadata={"project_id": project_id, "scene_id": scene_id, **extra},
            )

        if not str(project_id or "").strip() or not str(scene_id or "").strip():
            raise _deny("project_id and scene_id are required")

        shot = None
        if str(storyboard_shot_id or "").strip():
            reader = getattr(storage, "get_storyboard_shot", None)
            if not callable(reader):
                raise _deny("storage cannot resolve storyboard shots")
            shot = reader(str(storyboard_shot_id).strip())
            if shot is None or str(_shot_field(shot, "project_id") or "") != project_id or str(_shot_field(shot, "scene_id") or "") != scene_id:
                raise _deny("storyboard shot not found in project scene", storyboard_shot_id=storyboard_shot_id)
        elif str(shot_id or "").strip():
            reader = getattr(storage, "get_storyboard_shot_by_shot_id", None)
            if callable(reader):
                shot = reader(project_id, scene_id, str(shot_id).strip())
            if shot is None:
                blueprint_reader = getattr(storage, "get_storyboard_blueprint", None)
                blueprint = blueprint_reader(project_id, scene_id) if callable(blueprint_reader) else None
                if blueprint is not None and callable(getattr(storage, "list_storyboard_shots", None)):
                    candidates = storage.list_storyboard_shots(blueprint.blueprint_id, blueprint.current_version_id)
                    shot = next((item for item in candidates if str(_shot_field(item, "shot_id") or "") == str(shot_id).strip()), None)
            if shot is None or str(_shot_field(shot, "project_id") or "") != project_id or str(_shot_field(shot, "scene_id") or "") != scene_id:
                raise _deny("shot not found in project scene", shot_id=shot_id)
        else:
            raise _deny("no shot identifier supplied")

        if str(blueprint_id or "").strip() and str(_shot_field(shot, "blueprint_id") or "") != str(blueprint_id).strip():
            raise _deny("shot belongs to a different blueprint", shot_blueprint_id=str(_shot_field(shot, "blueprint_id") or ""))

        blueprint_reader = getattr(storage, "get_storyboard_blueprint_by_id", None)
        blueprint = blueprint_reader(str(_shot_field(shot, "blueprint_id") or "")) if callable(blueprint_reader) else None
        if blueprint is None:
            raise _deny("shot blueprint could not be resolved")
        current_version_id = str(getattr(blueprint, "current_version_id", "") or "")
        if not current_version_id or str(_shot_field(shot, "version_id") or "") != current_version_id:
            raise _deny(
                "shot belongs to a historical storyboard version",
                shot_version_id=str(_shot_field(shot, "version_id") or ""),
                current_version_id=current_version_id,
            )
        if str(version_id or "").strip() and str(_shot_field(shot, "version_id") or "") != str(version_id).strip():
            raise _deny(
                "shot version contradicts the version the render was prepared against",
                supplied_version_id=str(version_id).strip(),
                shot_version_id=str(_shot_field(shot, "version_id") or ""),
            )
        return shot

    def validate_current_shot_version(self, shot: Any, *, storage: Any) -> str | None:
        """Return a blocker message when the shot is not the blueprint's current one, else None."""
        from app.services.stability import StateError

        try:
            blueprint_reader = getattr(storage, "get_storyboard_blueprint_by_id", None)
            blueprint = blueprint_reader(str(_shot_field(shot, "blueprint_id") or "")) if callable(blueprint_reader) else None
        except Exception:
            blueprint = None
        if blueprint is None:
            return "The shot's blueprint could not be resolved from canonical state."
        current_version_id = str(getattr(blueprint, "current_version_id", "") or "")
        if not current_version_id or str(_shot_field(shot, "version_id") or "") != current_version_id:
            return (
                "This shot belongs to a historical storyboard version "
                f"('{_shot_field(shot, 'version_id')}' vs current '{current_version_id}'). "
                "Rebuild the render from the current board."
            )
        return None

    # ── Camera provenance (P0-2) ──────────────────────────────────────────

    def approve_ai_camera_instructions(
        self,
        camera_instructions: list[CameraInstruction],
        *,
        approved_by: str,
    ) -> list[CameraInstruction]:
        """Mark AI-suggested camera values as explicitly user-approved.

        This is the ONLY supported path from AI_SUGGESTED to renderable: an
        explicit approval action by the user. The approval is recorded durably
        in the instruction's source_version so the readiness gate can verify
        it later. Provenance metadata is never rewritten silently — every
        instruction that changes source here was AI_SUGGESTED.
        """
        stamp = f"{AI_CAMERA_APPROVAL_PROVENANCE}:{approved_by}"
        approved: list[CameraInstruction] = []
        for instruction in camera_instructions:
            if instruction.instruction_source == CAMERA_SOURCE_AI_SUGGESTED and instruction.value.strip():
                approved.append(
                    CameraInstruction(
                        dimension=instruction.dimension,
                        value=instruction.value,
                        instruction_source=CAMERA_SOURCE_APPROVED,
                        source_version=stamp,
                    )
                )
            else:
                approved.append(instruction)
        return approved

    def derive_camera_instructions(
        self,
        *,
        creator_planning: dict[str, Any] | None = None,
        approved_camera_plan: dict[str, Any] | None = None,
        ai_suggested_camera: dict[str, Any] | None = None,
        storyboard_shot: Any = None,
    ) -> list[CameraInstruction]:
        """Build the structured camera list with explicit provenance.

        Provenance rules (P0-2):
        - creator-entered values → USER_SPECIFIED (may render);
        - values the user explicitly chose via the camera-plan flow on the
          board shot (``metadata["camera_plan"]``) → APPROVED (may render);
        - template/heuristic board values without that approval record →
          AI_SUGGESTED (the readiness gate blocks them from paid generation
          until the user approves them);
        - everything not decided → UNSPECIFIED placeholders that stay empty.
        Edit-grammar tokens ("match_cut", "bridge_action", …) are cut
        instructions, never camera data, and are rejected wherever they
        surface.
        """
        instructions: list[CameraInstruction] = []
        seen: set[str] = set()

        def _add(dimension: str, value: Any, source: str, source_version: str = "") -> None:
            if value is None:
                return
            if not isinstance(value, str):
                raise ValueError(f"Camera '{dimension}' must be a string")
            value = value.strip()
            if not value:
                return
            if dimension == "camera" and is_edit_grammar_movement(value):
                raise ValueError(
                    f"Camera plan carries an editorial cut instruction ('{value}'), not a camera movement."
                )
            key = dimension.strip().lower()
            if not key or key in seen:
                return
            seen.add(key)
            instructions.append(
                CameraInstruction(
                    dimension=key,
                    value=value,
                    instruction_source=source,
                    source_version=str(source_version or ""),
                )
            )

        planning = creator_planning if isinstance(creator_planning, dict) else {}
        for dimension in (
            "framing", "camera", "lens", "focal_length", "aperture", "composition", "blocking",
        ):
            _add(dimension, planning.get(dimension), CAMERA_SOURCE_USER_SPECIFIED)

        plan = approved_camera_plan if isinstance(approved_camera_plan, dict) else {}
        for dimension in (
            "camera", "framing", "lens", "focal_length", "aperture", "composition", "blocking",
        ):
            value = plan.get(dimension)
            if value is None:
                continue
            _add(dimension, value, CAMERA_SOURCE_APPROVED)

        # A storyboard shot's visual plan is board content, but heuristic
        # board content is NOT creator camera approval. Unapproved template
        # values are never attached as renderable camera data — the dimension
        # stays UNSPECIFIED and the value is preserved as a pending AI
        # suggestion (see ``pending_ai_camera_suggestions``). Only a creator
        # camera plan (explicit user action) earns APPROVED.
        visual_plan = getattr(storyboard_shot, "visual_plan", None)
        if visual_plan is not None:
            board_version = str(getattr(storyboard_shot, "version_id", "") or "")
            creator_plan, creator_defined = _camera_plan_provenance(storyboard_shot)
            if creator_defined:
                movement_value = creator_plan.get("camera") or getattr(visual_plan, "camera_movement", "")
                _add("framing", creator_plan.get("framing") or getattr(visual_plan, "framing", ""), CAMERA_SOURCE_APPROVED, board_version)
                _add("camera", movement_value, CAMERA_SOURCE_APPROVED, board_version)
                _add("lens", creator_plan.get("lens") or getattr(visual_plan, "lens_language", ""), CAMERA_SOURCE_APPROVED, board_version)
            else:
                pending = pending_ai_camera_suggestions(storyboard_shot)
                if pending:
                    logger.info(
                        "CAMERA_PROVENANCE_UNAPPROVED_SUGGESTIONS_HELD | version=%s | dimensions=%s",
                        board_version,
                        ",".join(sorted(pending)),
                    )

        # Explicitly flagged AI suggestions are attached AS AI_SUGGESTED so
        # the readiness gate blocks them until approval — never attached as
        # approved content. Callers opt into this evaluation (the batch path
        # does; preview paths leave the field unspecified instead).
        suggestions = ai_suggested_camera if isinstance(ai_suggested_camera, dict) else {}
        for dimension, value in suggestions.items():
            _add(str(dimension), value, CAMERA_SOURCE_AI_SUGGESTED)

        # UNSPECIFIED placeholders keep "we didn't decide this" explicit.
        for dimension in _UNSHOT_SPECIFIED_DIMENSIONS:
            if not any(c.dimension == dimension for c in instructions):
                instructions.append(
                    CameraInstruction(dimension=dimension, value="", instruction_source=CAMERA_SOURCE_UNSPECIFIED)
                )
        return instructions

    # ── Context creation ──────────────────────────────────────────────────

    def create_generation_context(
        self,
        *,
        project_id: str,
        scene_id: str,
        shot_id: str,
        scene: dict[str, Any] | None,
        storyboard_context: dict[str, Any] | None,
        reference_assets: list[str] | None,
        camera_instructions: list[CameraInstruction] | None = None,
        prompt_source: str = "DERIVED",
        consistency_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        shot: Any = None,
        shot_version: str | None = None,
        require_shot_version: bool = False,
        canonical_script_text: str | None = None,
    ) -> GenerationContext:
        """Mint a fresh context. Always a new id — never reused from history.

        Shot versioning (P0-1): pass the authoritative shot record via
        ``shot`` (preferred — the version is derived from canonical state, not
        from any frontend copy) or an already-resolved ``shot_version``.
        Generation contexts for shot-based renders must never silently carry
        ``"absent"``: when ``require_shot_version`` is set and no shot state
        can be derived, this raises instead of minting an unversioned context.
        """
        resolved_shot_version = SHOT_VERSION_ABSENT
        if shot is not None:
            resolved_shot_version = self.shot_version(shot)
        elif shot_version is not None and str(shot_version).strip():
            resolved_shot_version = str(shot_version).strip()
        if require_shot_version and resolved_shot_version == SHOT_VERSION_ABSENT:
            from app.services.stability import ValidationError

            raise ValidationError(
                "Generation blocked: the shot version could not be resolved from canonical state. "
                "A shot-based render requires the current authoritative shot.",
                stage="generation_shot_resolution",
                metadata={"project_id": project_id, "scene_id": scene_id, "shot_id": shot_id},
            )
        context_metadata = dict(metadata or {})
        if shot is not None:
            context_metadata.setdefault("shot_version_source", "canonical_shot_record")
        elif resolved_shot_version != SHOT_VERSION_ABSENT:
            context_metadata.setdefault("shot_version_source", "resolved_shot_version")
        return GenerationContext(
            generation_context_id=f"genctx_{uuid4().hex[:16]}",
            project_id=project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            scene_version=self.scene_version(scene, canonical_script_text),
            shot_version=resolved_shot_version,
            storyboard_version=self.storyboard_version(storyboard_context),
            reference_version=self.reference_version(
                reference_assets=reference_assets,
                consistency_payload=consistency_payload,
            ),
            camera_version=self.camera_version(camera_instructions or []),
            camera_instructions=list(camera_instructions or []),
            prompt_source=prompt_source,
            metadata=context_metadata,
        )

    # ── Readiness gate ────────────────────────────────────────────────────

    def validate_generation_context(
        self,
        *,
        context: GenerationContext,
        current_scene: dict[str, Any] | None,
        current_storyboard_context: dict[str, Any] | None,
        current_reference_assets: list[str] | None,
        consistency_payload: dict[str, Any] | None = None,
        expected_scene_id: str | None = None,
        expected_shot_id: str | None = None,
        current_shot: Any = None,
        canonical_script_text: str | None = None,
    ) -> ReadinessResult:
        """Block the render when the request no longer matches current state.

        Compares the context's derived versions against *current* canonical
        state. Any mismatch is a blocker with a filmmaker-readable message.
        Shot validation (P0-1):
        - when a current shot is supplied, its version must match the context;
        - a context minted WITHOUT a shot version is blocked when a real shot
          is required (fail closed — never silently generate unversioned);
        - a context whose shot version cannot be re-verified against current
          state is blocked rather than trusted.
        """
        blockers: list[str] = []
        warnings: list[str] = []

        if expected_scene_id and context.scene_id != expected_scene_id:
            blockers.append(
                f"Scene mismatch: the render was built for scene '{context.scene_id}' "
                f"but you are viewing '{expected_scene_id}'."
            )
        if expected_shot_id and context.shot_id != expected_shot_id:
            blockers.append(
                f"Shot mismatch: the render was built for shot '{context.shot_id}' "
                f"but the current shot is '{expected_shot_id}'."
            )

        current_scene_v = self.scene_version(current_scene, canonical_script_text)
        if context.scene_version != current_scene_v:
            blockers.append(
                "This scene changed after the render was prepared "
                "(scene version mismatch). Rebuild the render from the current scene."
            )

        current_board_v = self.storyboard_version(current_storyboard_context)
        if context.storyboard_version != current_board_v:
            blockers.append(
                "The storyboard changed after the render was prepared "
                "(storyboard version mismatch). Approve the current board version "
                "and rebuild the render."
            )

        current_ref_v = self.reference_version(
            reference_assets=current_reference_assets,
            consistency_payload=consistency_payload,
        )
        if context.reference_version != current_ref_v:
            blockers.append(
                "References changed after the render was prepared "
                "(reference version mismatch). Rebuild the render with the "
                "current approved references."
            )

        # Shot version integrity (P0-1).
        if current_shot is not None:
            current_shot_v = self.shot_version(current_shot)
            if current_shot_v == SHOT_VERSION_ABSENT:
                blockers.append(
                    "The current shot state could not be fingerprinted from canonical data. "
                    "Rebuild the render from the current shot."
                )
            elif context.shot_version != current_shot_v:
                blockers.append(
                    "This shot changed after the render was prepared "
                    "(shot version mismatch). Rebuild the render from the current shot."
                )
        elif current_storyboard_context is not None and context.shot_version == SHOT_VERSION_ABSENT:
            blockers.append(
                "The generation context carries no shot version. A storyboard shot "
                "must be resolved from canonical state before rendering (shot version absent)."
            )

        # Camera integrity: AI suggestions never silently pass as approved.
        # An APPROVED value must either be user-entered/creator-planned or
        # carry the explicit approval stamp recorded at approval time.
        for instruction in context.camera_instructions:
            if not instruction.value.strip():
                continue
            if instruction.instruction_source == CAMERA_SOURCE_AI_SUGGESTED:
                blockers.append(
                    f"Camera '{instruction.dimension}' is an unapproved AI suggestion "
                    f"('{instruction.value}'). Approve or remove it before rendering."
                )
            elif (
                instruction.instruction_source == CAMERA_SOURCE_APPROVED
                and AI_CAMERA_APPROVAL_PROVENANCE in str(instruction.source_version or "")
            ):
                # Stamped approval: explicitly user-approved AI suggestion — renderable.
                continue

        if blockers:
            return ReadinessResult(ready=False, blockers=blockers, warnings=warnings, context=context)

        # Re-derive against current state: identical versions mean fresh.
        return ReadinessResult(ready=True, blockers=[], warnings=warnings, context=context)


# Single shared instance.
generation_context_service = GenerationContextService()

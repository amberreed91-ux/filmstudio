"""Isolated, synthetic API for the Creator Decision Workspace preview.

This module deliberately does not import ``main``, production routes, services,
or storage. Its entire data store exists in process memory and is seeded only
with the synthetic values below. It is not a bridge to a real Studio project.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

PROJECT_ID = "project_5907c60cddbc"
SCENE_ID = "scene_002"
SETTING_ID = "loc-c8f88b9c"
SOURCE_VERSION_ID = "sbv_a6096cb1fea5"
LEGACY_REFERENCE_ID = "ref_env_6b726885ed67ae4d"
SHOT_IDS = tuple(f"scene_002_shot_{number:03d}" for number in range(1, 6))

CoverageKind = Literal["content", "dialogue", "shot_content", "shot_dialogue"]
CoverageStatus = Literal["UNASSIGNED", "ASSIGNED", "EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"]


class CoverageChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_type: CoverageKind
    obligation_id: str = Field(min_length=1, max_length=200)
    status: CoverageStatus
    shot_id: str | None = None
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_choice(self) -> "CoverageChoice":
        if self.obligation_type in {"content", "dialogue"}:
            if self.status == "INTENTIONAL_SILENCE":
                raise ValueError("Content and dialogue cannot be marked intentional silence")
            if self.status == "ASSIGNED" and not self.shot_id:
                raise ValueError("An explicit shot is required for an assignment")
            if self.status not in {"ASSIGNED", "UNASSIGNED"} and not self.reason.strip():
                raise ValueError("An explicit creator reason is required for an omission")
            if self.status != "ASSIGNED" and self.shot_id is not None:
                raise ValueError("Only an assigned decision may name a shot")
        elif self.obligation_type == "shot_content":
            if self.status not in {"UNASSIGNED", "INTENTIONAL_SILENCE"}:
                raise ValueError("Shot content permits only unresolved or intentional silence")
            if self.status == "INTENTIONAL_SILENCE" and not self.reason.strip():
                raise ValueError("Intentional silence requires a creator reason")
            if self.shot_id is not None:
                raise ValueError("Shot content is scoped by its obligation ID")
        else:
            if self.status not in {"UNASSIGNED", "EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"}:
                raise ValueError("Shot dialogue permits unresolved, omitted, or intentional silence")
            if self.status in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"} and not self.reason.strip():
                raise ValueError("A shot dialogue disposition requires a creator reason")
            if self.shot_id is not None:
                raise ValueError("Shot dialogue is scoped by its obligation ID")
        return self


class DirectionHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_id: str = Field(min_length=1, max_length=200)
    opening_state: str = Field(default="", max_length=1500)
    action_change: str = Field(default="", max_length=1500)
    ending_state: str = Field(default="", max_length=1500)


class ReferenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_setting_id: str = Field(min_length=1, max_length=256)
    reference_id: str = Field(min_length=1, max_length=256)


class DialogueRow(BaseModel):
    # Preserve contract compatibility while ignoring optional production-only
    # dialogue metadata that this intentionally narrow fixture does not model.
    model_config = ConfigDict(extra="ignore")

    line_id: str
    character: str
    text: str
    shot_id: str | None = None


class SaveDirection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version_id: str = Field(min_length=1, strict=True)
    dialogue: list[DialogueRow]
    coverage_decisions: list[CoverageChoice] = Field(max_length=1000)
    handoffs: list[DirectionHandoff] = Field(max_length=100)
    setting_reference_decision: ReferenceDecision | None = None


class RegisterReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_url: str = Field(min_length=1, max_length=4096)
    category: str = Field(default="environment", max_length=64)


@dataclass
class FixtureStore:
    """Explicit disposable state; no filesystem, DB, or global storage access."""

    direction: dict[str, Any] = field(init=False)
    references: list[dict[str, Any]] = field(default_factory=list)
    approved_source: dict[str, Any] = field(init=False)
    successor_sequence: int = 0

    def __post_init__(self) -> None:
        self.direction = build_fixture_direction()
        self.approved_source = {
            "version_id": SOURCE_VERSION_ID,
            "version_status": "approved",
            "direction": deepcopy(self.direction),
        }


def build_fixture_direction() -> dict[str, Any]:
    """Build the documented synthetic 40/10/5/5 fixture, all unresolved."""
    shots = [
        {
            "shot_id": shot_id,
            "shot_number": number,
            "shot_kind": "establishing" if number == 1 else "medium_shot",
            "locked": False,
            "opening_state": "",
            "action_change": "",
            "ending_state": "",
            "frame_url": None,
            "saved_frame_url": None,
            "frame_changed": False,
            "previous_ending_state": "",
            "dialogue_disposition": "UNASSIGNED",
            "dialogue_disposition_reason": "",
        }
        for number, shot_id in enumerate(SHOT_IDS, start=1)
    ]
    content = [
        {
            "obligation_type": "content",
            "obligation_id": f"content_{number:02d}",
            "source_text": f"Synthetic source unit {number} — fixture text, not the project screenplay.",
            "source_start": (number - 1) * 10,
            "source_end": (number - 1) * 10 + 9,
            "status": "UNASSIGNED",
            "shot_id": None,
            "reason": "",
            "reason_required": False,
        }
        for number in range(1, 41)
    ]
    dialogue = [
        {"line_id": f"line_{number:02d}", "character": "MAYA" if number % 2 else "DRE",
         "text": f"Synthetic dialogue line {number} — fixture text, not canonical dialogue.", "shot_id": None}
        for number in range(1, 11)
    ]
    decisions = [
        {"obligation_type": row["obligation_type"], "obligation_id": row["obligation_id"],
         "status": "UNASSIGNED", "shot_id": None, "reason": ""}
        for row in content
    ]
    decisions.extend(
        {"obligation_type": "dialogue", "obligation_id": row["line_id"],
         "status": "UNASSIGNED", "shot_id": None, "reason": ""}
        for row in dialogue
    )
    decisions.extend(
        {"obligation_type": kind, "obligation_id": shot_id,
         "status": "UNASSIGNED", "shot_id": None, "reason": ""}
        for kind in ("shot_content", "shot_dialogue") for shot_id in SHOT_IDS
    )
    return {
        "project_id": PROJECT_ID,
        "scene_id": SCENE_ID,
        "version_id": SOURCE_VERSION_ID,
        "version_status": "approved",
        "canonical_setting_id": SETTING_ID,
        "setting_reference_decision": None,
        "setting_reference_options": [],
        "dialogue": dialogue,
        "coverage_obligations": content,
        "coverage_decisions": decisions,
        "unassigned_line_ids": [row["line_id"] for row in dialogue],
        "coverage_blocked": True,
        "coverage_blockers": ["60 synthetic coverage decisions remain unresolved."],
        "shots": shots,
        "saved": False,
    }


def _require_scope(project_id: str, scene_id: str | None = None) -> None:
    if project_id != PROJECT_ID or (scene_id is not None and scene_id != SCENE_ID):
        raise HTTPException(status_code=404, detail="No fixture exists for that project or scene")


def _decision_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(row["obligation_type"], row["obligation_id"]): row for row in rows}


def _resolved_for_ui(row: dict[str, Any], decisions: list[dict[str, Any]]) -> bool:
    if row["status"] != "UNASSIGNED":
        return True
    if row["obligation_type"] == "shot_content":
        return any(d["obligation_type"] == "content" and d["status"] == "ASSIGNED"
                   and d["shot_id"] == row["obligation_id"] for d in decisions)
    if row["obligation_type"] == "shot_dialogue":
        return any(d["obligation_type"] == "dialogue" and d["status"] == "ASSIGNED"
                   and d["shot_id"] == row["obligation_id"] for d in decisions)
    return False


def create_app(store: FixtureStore | None = None) -> FastAPI:
    """Create the small fixture app; deliberately has no custom lifespan."""
    fixture = store if store is not None else FixtureStore()
    app = FastAPI(title="Creator Workspace Synthetic Fixture", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.fixture_store = fixture

    @app.get("/api/f51/studio/projects/{project_id}/scenes/{scene_id}/direction")
    def get_direction(project_id: str, scene_id: str) -> dict[str, Any]:
        _require_scope(project_id, scene_id)
        # Return a detached value. Reading does not update or normalize state.
        result = deepcopy(fixture.direction)
        result["setting_reference_options"] = [
            {
                "ref_id": row["ref_id"], "image_url": row["image_url"],
                "target_type": row["target_type"], "target_id": row["target_id"],
                "kind": row["kind"], "approval_state": row["approval_state"],
                "canonical": row["canonical"],
            }
            for row in fixture.references
            if row["project_id"] == PROJECT_ID and row["target_type"] == "setting"
            and row["target_id"] == SETTING_ID and row["kind"] == "environment"
            and row["approval_state"] == "approved" and row["canonical"]
            and row["ref_id"] != LEGACY_REFERENCE_ID
        ]
        return result

    @app.put("/api/f51/studio/projects/{project_id}/scenes/{scene_id}/direction")
    def save_direction(project_id: str, scene_id: str, payload: SaveDirection) -> dict[str, Any]:
        _require_scope(project_id, scene_id)
        current = fixture.direction
        if payload.expected_version_id != current["version_id"]:
            raise HTTPException(status_code=409, detail="The fixture direction changed. Reload before saving.")
        if current["version_status"] == "locked":
            raise HTTPException(status_code=409, detail="This fixture version is locked.")

        expected_rows = current["coverage_decisions"]
        expected_keys = {(row["obligation_type"], row["obligation_id"]) for row in expected_rows}
        submitted_keys = [(row.obligation_type, row.obligation_id) for row in payload.coverage_decisions]
        if len(submitted_keys) != len(set(submitted_keys)) or set(submitted_keys) != expected_keys:
            raise HTTPException(status_code=422, detail="Submit exactly one decision for every fixture obligation.")

        shots = {row["shot_id"]: row for row in current["shots"]}
        decisions = [row.model_dump() for row in payload.coverage_decisions]
        for row in decisions:
            if row["shot_id"] is not None and row["shot_id"] not in shots:
                raise HTTPException(status_code=422, detail="Choose a shot in this fixture scene.")
            if row["obligation_type"] in {"shot_content", "shot_dialogue"}:
                shot = shots.get(row["obligation_id"])
                if shot is None:
                    raise HTTPException(status_code=422, detail="Choose a known fixture shot disposition.")
                if row["obligation_type"] == "shot_content" and row["status"] == "INTENTIONAL_SILENCE" and shot["shot_kind"].lower() not in {"establishing", "establishing_shot", "transition", "transition_shot"}:
                    raise HTTPException(status_code=422, detail="Intentional content silence requires an eligible establishing or transition shot.")

        by_key = _decision_index(decisions)
        dialogue_assigned_shots = {row["shot_id"] for row in decisions
                                   if row["obligation_type"] == "dialogue" and row["status"] == "ASSIGNED"}
        content_assigned_shots = {row["shot_id"] for row in decisions
                                  if row["obligation_type"] == "content" and row["status"] == "ASSIGNED"}
        for shot_id in SHOT_IDS:
            dialogue_disposition = by_key[("shot_dialogue", shot_id)]
            if shot_id in dialogue_assigned_shots and dialogue_disposition["status"] in {"EXPLICITLY_OMITTED", "INTENTIONAL_SILENCE"}:
                raise HTTPException(status_code=422, detail="A shot with assigned dialogue cannot also be omitted or silent.")
            content_disposition = by_key[("shot_content", shot_id)]
            if shot_id in content_assigned_shots and content_disposition["status"] == "INTENTIONAL_SILENCE":
                raise HTTPException(status_code=422, detail="A shot with assigned content cannot also be marked silent.")

        canonical_dialogue = {row["line_id"]: row for row in fixture.approved_source["direction"]["dialogue"]}
        submitted_dialogue = [row.model_dump() for row in payload.dialogue]
        if len(submitted_dialogue) != len(canonical_dialogue) or {row["line_id"] for row in submitted_dialogue} != set(canonical_dialogue):
            raise HTTPException(status_code=422, detail="Keep every canonical fixture dialogue row exactly once.")
        for line in submitted_dialogue:
            original = canonical_dialogue[line["line_id"]]
            if line["text"] != original["text"] or line["character"] != original["character"]:
                raise HTTPException(status_code=422, detail="Fixture dialogue source wording is read-only.")
            decision = by_key[("dialogue", line["line_id"])]
            if line["shot_id"] != (decision["shot_id"] if decision["status"] == "ASSIGNED" else None):
                raise HTTPException(status_code=422, detail="Dialogue assignments must match the explicit coverage decision.")

        handoffs = [row.model_dump() for row in payload.handoffs]
        if len(handoffs) != len(shots) or {row["shot_id"] for row in handoffs} != set(shots):
            raise HTTPException(status_code=422, detail="Include every fixture shot handoff exactly once.")

        prior_raw = current.get("setting_reference_decision")
        prior_decision: ReferenceDecision | None = None
        if prior_raw is not None:
            try:
                prior_decision = ReferenceDecision.model_validate(prior_raw)
            except Exception:
                raise HTTPException(status_code=422, detail="The saved fixture setting reference decision is malformed.")
        setting_decision = payload.setting_reference_decision
        if "setting_reference_decision" not in payload.model_fields_set:
            setting_decision = prior_decision
        if setting_decision is not None:
            is_unchanged_carry = (
                prior_decision is not None
                and setting_decision.model_dump() == prior_decision.model_dump()
            )
            is_draft_current = current.get("version_status") == "draft"
            # Option B parity with the real service: unchanged decisions carry
            # on the current draft; new/changed decisions require the approved source.
            if not (is_unchanged_carry and is_draft_current):
                if current.get("version_status") != "approved" or current.get("version_id") != fixture.approved_source.get("version_id"):
                    raise HTTPException(status_code=409, detail="Scene Direction decisions can only authorize the current approved storyboard version.")
            if setting_decision.canonical_setting_id != SETTING_ID:
                raise HTTPException(status_code=422, detail="Select the exact fixture setting entity.")
            eligible = any(row["ref_id"] == setting_decision.reference_id
                           and row["target_type"] == "setting" and row["target_id"] == SETTING_ID
                           and row["kind"] == "environment" and row["approval_state"] == "approved"
                           and row["canonical"] for row in fixture.references)
            if not eligible or setting_decision.reference_id == LEGACY_REFERENCE_ID:
                raise HTTPException(status_code=422, detail="The selected fixture reference is not approved and canonical for this setting.")

        # All validation completes before creating a successor. The approved
        # source snapshot is retained, never edited; only this in-memory fixture
        # gets a new draft version.
        fixture.successor_sequence += 1
        successor_id = f"sbv_fixture_successor_{fixture.successor_sequence:04d}"
        updated = deepcopy(current)
        updated["source_version_id"] = current["version_id"]
        updated["version_id"] = successor_id
        updated["version_status"] = "draft"
        updated["setting_reference_decision"] = setting_decision.model_dump() if setting_decision else None
        updated["coverage_decisions"] = decisions
        updated["dialogue"] = submitted_dialogue
        content_decisions = {row["obligation_id"]: row for row in decisions if row["obligation_type"] == "content"}
        updated["coverage_obligations"] = [
            {**row, "status": content_decisions[row["obligation_id"]]["status"],
             "shot_id": content_decisions[row["obligation_id"]]["shot_id"],
             "reason": content_decisions[row["obligation_id"]]["reason"],
             "reason_required": content_decisions[row["obligation_id"]]["status"] == "EXPLICITLY_OMITTED"}
            for row in updated["coverage_obligations"]
        ]
        handoff_by_id = {row["shot_id"]: row for row in handoffs}
        for shot in updated["shots"]:
            shot.update({key: value for key, value in handoff_by_id[shot["shot_id"]].items() if key != "shot_id"})
            disposition = by_key[("shot_dialogue", shot["shot_id"])]
            shot["dialogue_disposition"] = disposition["status"]
            shot["dialogue_disposition_reason"] = disposition["reason"]
        updated["unassigned_line_ids"] = [row["line_id"] for row in submitted_dialogue
                                           if by_key[("dialogue", row["line_id"])]["status"] == "UNASSIGNED"]
        unresolved = sum(not _resolved_for_ui(row, decisions) for row in decisions)
        updated["coverage_blocked"] = unresolved > 0
        updated["coverage_blockers"] = ([f"{unresolved} fixture coverage decisions remain unresolved."] if unresolved else [])
        updated["saved"] = True
        fixture.direction = updated
        return deepcopy(updated)

    @app.get("/api/f51/studio/projects/{project_id}/setting-references/{setting_id}")
    def list_references(project_id: str, setting_id: str) -> dict[str, Any]:
        _require_scope(project_id)
        if setting_id != SETTING_ID:
            raise HTTPException(status_code=404, detail="No fixture exists for that setting.")
        rows = deepcopy(fixture.references)
        return {"project_id": PROJECT_ID, "target_type": "setting", "target_id": SETTING_ID,
                "reference_assets": rows, "count": len(rows)}

    @app.post("/api/f51/studio/projects/{project_id}/setting-references/{setting_id}")
    def register_reference(project_id: str, setting_id: str, payload: RegisterReference) -> dict[str, Any]:
        _require_scope(project_id)
        if setting_id != SETTING_ID:
            raise HTTPException(status_code=404, detail="No fixture exists for that setting.")
        # Do not fetch, import, or resolve user-supplied media URLs in fixture mode.
        if not payload.image_url.startswith("fixture://"):
            raise HTTPException(status_code=422, detail="Fixture mode accepts fixture:// identifiers only; no media is fetched or stored.")
        if payload.category != "environment":
            raise HTTPException(status_code=422, detail="Only the exact environment reference contract is available in this fixture.")
        row = {"ref_id": f"ref_set_fixture_{uuid4().hex[:12]}", "project_id": PROJECT_ID,
               "kind": "environment", "image_url": "", "source_shot_id": None,
               "target_type": "setting", "target_id": SETTING_ID, "category": "environment",
               "approval_state": "candidate", "canonical": False, "source_kind": "fixture",
               "created_at": None}
        fixture.references.append(row)
        return {"reference_asset": deepcopy(row)}

    @app.post("/api/f51/studio/projects/{project_id}/setting-references/{setting_id}/{reference_id}/approve")
    def approve_reference(project_id: str, setting_id: str, reference_id: str) -> dict[str, Any]:
        _require_scope(project_id)
        if setting_id != SETTING_ID:
            raise HTTPException(status_code=404, detail="No fixture exists for that setting.")
        row = next((asset for asset in fixture.references if asset["ref_id"] == reference_id), None)
        if row is None or row["target_id"] != SETTING_ID:
            raise HTTPException(status_code=404, detail="Fixture reference not found.")
        if row["approval_state"] != "candidate":
            raise HTTPException(status_code=409, detail="Only a candidate can be explicitly approved.")
        row["approval_state"] = "approved"
        return {"reference_asset": deepcopy(row)}

    @app.post("/api/f51/studio/projects/{project_id}/setting-references/{setting_id}/{reference_id}/canonical")
    def designate_reference(project_id: str, setting_id: str, reference_id: str) -> dict[str, Any]:
        _require_scope(project_id)
        if setting_id != SETTING_ID:
            raise HTTPException(status_code=404, detail="No fixture exists for that setting.")
        row = next((asset for asset in fixture.references if asset["ref_id"] == reference_id), None)
        if row is None or row["target_id"] != SETTING_ID:
            raise HTTPException(status_code=404, detail="Fixture reference not found.")
        if row["approval_state"] != "approved" or row["kind"] != "environment":
            raise HTTPException(status_code=409, detail="Explicit approval is required before canonical designation.")
        for asset in fixture.references:
            asset["canonical"] = asset["ref_id"] == reference_id
        return {"reference_asset": deepcopy(row)}

    @app.post("/api/f51/studio/projects/{project_id}/setting-references/{setting_id}/upload")
    async def upload_reference(project_id: str, setting_id: str) -> None:
        _require_scope(project_id)
        if setting_id != SETTING_ID:
            raise HTTPException(status_code=404, detail="No fixture exists for that setting.")
        raise HTTPException(status_code=501, detail="Uploads are disabled in the in-memory fixture; register a fixture:// identifier instead.")

    return app


# This singleton contains synthetic in-memory data only; importing the module
# creates no production app, storage, lifespan task, or external connection.
app = create_app()

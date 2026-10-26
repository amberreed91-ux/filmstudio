"""Per-shot integrity gates — read-only aggregate for the Integrity Engine.

One GET backing the visual per-shot gate pipeline. Answers, for a single
shot, the eight gates the Engine renders as plain chips:

image (D4 prompt) / words (D6 send-text) / look (setting anchor) /
settled (durable confirmation) / contract (frozen contract on file) /
preflight (recorded authorization posture) / spend (recorded price only) /
duplicate (upstream-task / reconcile posture).

Side-effect contract (STEP 1): this module calls ONLY pure read paths.
It deliberately does NOT call
``SceneProductionPipelineService.prepare_scene_batch`` (that method calls
``_register_prepared_scene_batch`` — a write to the service's in-memory
registry — and runs the cost gate), does NOT call
``estimate_router_shot_via_dry_run`` / ``submit_runway_router_video_render``
(any dry run contacts the provider network), does NOT touch the universe
graph (which lazily auto-populates), does NOT refresh anything, creates
no jobs, saves no seeds, records no confirmations, and invokes no
provider. See READ_CALLS below; every entry is a SELECT or an in-memory
derivation over already-loaded rows.

Gate-state vocabulary (neutral, never "ready to send"):

- ``pass``        the persisted record shows this gate satisfied.
- ``blocked``     a persisted record refuses (with its recorded reason).
- ``cant_check``  cannot be evaluated from persisted rows — and this
  endpoint refuses to run the preparation that would evaluate it.
- ``not_yet``     nothing recorded yet; expected before preparation.

The ``preflight`` gate NEVER reports ``pass`` as permission for a future
send. At most it reports the historical fact that a persisted job was
authorized when sent (past tense, scoped to that job id). A new send
always needs a fresh preparation, which this endpoint never performs.

``spend`` NEVER carries a computed number. ``estimated_credits`` echoes
only a value already persisted on the latest job's
``metadata.router_execution`` (Runway's own recorded figure, labeled
advisory). When the resolved binding carries local (non-http) reference
URIs the spend gate is ``cant_check`` unconditionally — even when a
persisted estimate exists — because local bytes must be materialized
before Runway can price the shot, and pricing requires a dry run this
endpoint refuses to perform.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from app.data.storage import get_storage
from app.services.project_persistence_service import project_persistence_service
from app.services.reference_asset_service import ReferenceAssetService
from app.services.stability import StateError
from app.services.storyboard_image_prompt_service import StoryboardImagePromptService

logger = logging.getLogger("shot-integrity-gates-service")

# Every storage/service call this module makes. All reads; no writes, no
# table creation of its own, no refresh, no provider, no job creation.
READ_CALLS = [
    "project_persistence_service.load_readonly_existing "
    "(read existing project JSON, no hydration/normalization/sync)",
    "reference_asset_service.resolve_shot_binding "
    "(read-only binding preview; derives scene, freezes canonical order, digests)",
    "storage.get_storyboard_blueprint (SELECT storyboard_blueprints)",
    "storage.list_storyboard_shots (SELECT storyboard_shots)",
    "read-only sqlite_master probe for storyboard_image_prompts (mode=ro; "
    "gates the prompt reads so an absent table is never CREATEed)",
    "storyboard_image_prompt_service.status_for_shot "
    "(D4 states over SELECTed image-prompt row; no derive/edit/approve)",
    "storyboard_image_prompt_service.resolve_provider_send_text "
    "(D6 fail-closed verdict over the same SELECTed row; raises, never sends)",
    "reference_validation.resolve_scene_reference_requirements "
    "(documented read-only: no provisional locks, no approval change)",
    "reference_asset_service.get_shot_confirmation "
    "(revalidates the durable row against the fresh binding; creates nothing)",
    "storage.list_jobs (SELECT render_jobs, newest-first per shot)",
]

PASS = "pass"
BLOCKED = "blocked"
CANT_CHECK = "cant_check"
NOT_YET = "not_yet"

# Substrings that mark a recorded authorization/contract refusal. Matched
# case-insensitively against router_execution.reason / provider_failure text.
_CONTRACT_REFUSALS = frozenset(
    {
        "frozen_generation_contract_unavailable",
        "frozen_contract_or_binding_mismatch",
        "frozen_contract_digest_mismatch",
        "missing_generation_contract",
    }
)

_AUTHORIZATION_REFUSALS = frozenset(
    {
        "frozen_generation_contract_unavailable",
        "model_rejected_on_router_path",
        "cost_estimate_unknown",
        "cost_estimate_invalid",
        "confirmation_mismatch",
        "confirmed_reference_binding_stale",
        "confirmed_reference_binding_unresolvable",
        "missing_confirmation",
    }
)

_UNEVALUATABLE_ANCHOR_FAILURES = frozenset({"project_not_found", "unknown_scene"})

# Next actions. One plain-language token per shot; the Engine renders the
# sentence. Never a send authorization.
NEXT_APPROVE_IMAGE = "approve_image_prompts"
NEXT_APPROVE_WORDS = "approve_send_text"
NEXT_CONFIRM_ANCHOR = "confirm_setting_anchor"
NEXT_CONFIRM_BINDING = "confirm_binding"
NEXT_PREPARE_SCENE = "prepare_scene"
NEXT_CHECK_PRICE = "check_price"
NEXT_CHECK_DUPLICATE = "check_duplicate_task"
NEXT_AWAIT_MEDIA = "await_media"
NEXT_RETRY_JOB = "retry_failed_job"
NEXT_CHECK_DATA = "check_shot_data"
NEXT_NONE = "no_action"


def _image_prompts_table_present(storage: Any) -> bool:
    """DDL-free existence check for the image-prompts table (read-only).

    Mirrors the Desk aggregate: ``get_storyboard_image_prompt`` runs
    ``CREATE TABLE IF NOT EXISTS`` as a side effect, so a ``mode=ro`` URI
    connection — which can never create anything — probes
    ``sqlite_master`` first. An absent table means no prompt row can exist
    and every D4/D6 read reports ``not_yet`` without a schema change.
    """
    try:
        from app.data.db_guard import open_db_readonly

        db_path = getattr(storage, "db_path", None)
        if db_path is None:
            return True
        conn = open_db_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'storyboard_image_prompts'"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return True


def _is_local_uri(uri: Any) -> bool:
    """True when a reference URI is not directly fetchable by the provider."""
    text = str(uri or "").strip().lower()
    if not text:
        return True
    return not (text.startswith("http://") or text.startswith("https://"))


def _binding_has_local_refs(binding: Any) -> bool:
    if not isinstance(binding, list):
        return False
    for row in binding:
        if not isinstance(row, dict):
            continue
        uri = row.get("uri", row.get("image_url", row.get("url")))
        if _is_local_uri(uri):
            return True
    return False


def _latest_job_for_shot(jobs: list[Any], shot_id: str) -> Any | None:
    matches = [job for job in jobs if str(getattr(job, "shot_id", "") or "") == shot_id]
    if not matches:
        return None

    def _created(job: Any) -> str:
        return str(getattr(job, "created_at", "") or "")

    matches.sort(key=_created)
    return matches[-1]


def _job_metadata(job: Any) -> dict[str, Any]:
    metadata = getattr(job, "metadata", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _router_execution(job: Any) -> dict[str, Any]:
    execution = _job_metadata(job).get("router_execution")
    return dict(execution) if isinstance(execution, dict) else {}


def _router_reconciliation(job: Any) -> dict[str, Any]:
    reconciliation = _job_metadata(job).get("router_reconciliation")
    return dict(reconciliation) if isinstance(reconciliation, dict) else {}


def _recorded_refusal_text(job: Any) -> str:
    """Newest recorded refusal reason on a job, or empty string."""
    execution = _router_execution(job)
    reason = str(execution.get("reason") or "").strip()
    failure = _job_metadata(job).get("provider_failure")
    failure_text = ""
    if isinstance(failure, dict):
        failure_text = str(
            failure.get("error") or failure.get("code") or failure.get("message") or ""
        ).strip()
    elif failure:
        failure_text = str(failure).strip()
    return reason or failure_text


def classify_spend(binding: Any, job: Any) -> dict[str, Any]:
    """Pure spend classifier over already-loaded rows (no network, no dry run).

    Local refs force ``cant_check`` with ``estimated_credits=None`` — never
    a number — even when a persisted estimate exists.
    """
    if _binding_has_local_refs(binding):
        return {
            "state": CANT_CHECK,
            "label": "Price unknown",
            "detail": (
                "This shot's references are local files Runway cannot fetch, "
                "so no Studio price can be read for it. Pricing needs a "
                "fresh preparation, which this view never runs."
            ),
            "estimated_credits": None,
            "cost_status": "local_refs_unpriced",
        }
    if job is None:
        return {
            "state": NOT_YET,
            "label": "Nothing priced",
            "detail": "No job exists for this shot yet, so nothing has been priced.",
            "estimated_credits": None,
            "cost_status": "no_job",
        }
    execution = _router_execution(job)
    realized = execution.get("realized_cost_credits", _job_metadata(job).get("realized_cost_credits"))
    estimated = execution.get("estimated_cost_credits")
    cost_gate = execution.get("cost_gate")
    cost_status = ""
    if isinstance(cost_gate, dict):
        cost_status = str(cost_gate.get("cost_status") or "").strip()
    if isinstance(realized, bool) or not isinstance(realized, (int, float)):
        realized = None
    if isinstance(estimated, bool) or not isinstance(estimated, (int, float)):
        estimated = None
    if cost_status == "invalid":
        return {
            "state": BLOCKED,
            "label": "Price refused",
            "detail": "Runway returned an unusable estimate for this job, so sending is blocked.",
            "estimated_credits": None,
            "cost_status": cost_status,
        }
    if realized is not None:
        return {
            "state": PASS,
            "label": "Price on file",
            "detail": f"Runway recorded {realized:g} credits for job {getattr(job, 'id', '')} (realized, advisory).",
            "estimated_credits": float(realized),
            "cost_status": cost_status or "realized",
        }
    if estimated is not None:
        return {
            "state": PASS,
            "label": "Price on file",
            "detail": (
                f"Runway priced job {getattr(job, 'id', '')} at {estimated:g} credits "
                "(recorded estimate, advisory — not a Studio cap)."
            ),
            "estimated_credits": float(estimated),
            "cost_status": cost_status or "estimated",
        }
    return {
        "state": CANT_CHECK,
        "label": "Price unknown",
        "detail": (
            "No usable price is recorded for this shot, and this view never "
            "prices a shot itself. A fresh preparation would ask Runway."
        ),
        "estimated_credits": None,
        "cost_status": cost_status or "unknown",
    }


def classify_duplicate(job: Any) -> dict[str, Any]:
    """Pure duplicate-guard classifier over one persisted job (no lookup)."""
    if job is None:
        return {
            "state": NOT_YET,
            "label": "Nothing sent",
            "detail": "Nothing has been sent for this shot, so there is no upstream task to duplicate.",
        }
    execution = _router_execution(job)
    task_id = str(
        execution.get("runway_task_id") or _job_metadata(job).get("runway_task_id") or ""
    ).strip()
    if not task_id:
        return {
            "state": PASS,
            "label": "No duplicate risk",
            "detail": "No upstream Runway task is recorded for this shot.",
        }
    status = str(getattr(job, "status", "") or "").lower()
    if status == "complete":
        return {
            "state": PASS,
            "label": "No duplicate risk",
            "detail": "The recorded upstream task completed; retrying would make new media, not a duplicate send.",
        }
    reconciliation = _router_reconciliation(job)
    verdict = str(reconciliation.get("verdict") or "").strip().lower()
    retry_permitted = reconciliation.get("retry_permitted")
    if verdict in {"terminal_failure", "dead", "failed"} and retry_permitted is True:
        return {
            "state": PASS,
            "label": "No duplicate risk",
            "detail": "The recorded upstream task is dead and the reconciliation record permits a retry.",
        }
    if status in {"pending", "submitted", "rendering", "queued"} or retry_permitted is False or not reconciliation:
        if status in {"failed", "error"} and not reconciliation:
            return {
                "state": CANT_CHECK,
                "label": "Check the task",
                "detail": (
                    "The job failed but its upstream task was never reconciled; "
                    "check the Runway task before retrying."
                ),
            }
        return {
            "state": BLOCKED,
            "label": "Possible duplicate",
            "detail": (
                "An upstream task is already recorded and its outcome is not "
                "known-dead; retrying could create a duplicate upstream task."
            ),
        }
    return {
        "state": CANT_CHECK,
        "label": "Check the task",
        "detail": "The upstream task state cannot be determined from the stored record.",
    }


def _gate(state: str, label: str, detail: str) -> dict[str, str]:
    return {"state": state, "label": label, "detail": detail}


class ShotIntegrityGatesService:
    """Read-only per-shot integrity gates."""

    def get_gates(self, project_id: str, shot_id: str) -> dict[str, Any]:
        started = perf_counter()
        cleaned_project = str(project_id or "").strip()
        cleaned_shot = str(shot_id or "").strip()
        if not cleaned_project:
            raise ValueError("project_id is required")
        if not cleaned_shot:
            raise ValueError("shot_id is required")
        storage = get_storage("sqlite")
        prompt_service = StoryboardImagePromptService(storage=storage)
        reference_service = ReferenceAssetService(storage=storage)
        try:
            result = self._build(
                project_id=cleaned_project,
                shot_id=cleaned_shot,
                storage=storage,
                prompt_service=prompt_service,
                reference_service=reference_service,
            )
        except (LookupError, ValueError):
            raise
        except Exception as exc:
            from app.services.stability import PersistenceError

            raise PersistenceError(
                f"Shot integrity lookup failed: {exc}",
                stage="shot_integrity_gates",
            ) from exc
        logger.info(
            "project_id=%s job_id=%s provider=%s stage=%s duration_ms=%d",
            cleaned_project,
            cleaned_shot,
            "none",
            "shot_integrity_gates",
            int((perf_counter() - started) * 1000),
        )
        return result

    def _build(
        self,
        *,
        project_id: str,
        shot_id: str,
        storage: Any,
        prompt_service: StoryboardImagePromptService,
        reference_service: ReferenceAssetService,
    ) -> dict[str, Any]:
        project = project_persistence_service.load_readonly_existing(project_id)
        if project is None:
            raise LookupError(f"Project {project_id} not found")

        # 1. Locate the shot from persisted rows first (SELECTs only), so a
        # genuinely absent shot fails with 404 instead of a 200 guess. A
        # scene with no board yet stays 200/not_yet — the shots are simply
        # unknown before the board exists.
        from app.utils.helpers import derive_scene_id_from_shot_id as _derive_scene

        try:
            scene_id = str(_derive_scene(shot_id) or "").strip()
        except Exception:  # noqa: BLE001 — malformed id, fail closed
            raise LookupError(f"Shot {shot_id} not found in project {project_id}")
        if not scene_id:
            raise LookupError(f"Shot {shot_id} not found in project {project_id}")

        binding_error = ""
        fresh: dict[str, Any] | None = None
        try:
            fresh = reference_service.resolve_shot_binding(project_id, shot_id)
            scene_id = str(fresh.get("scene_id") or "").strip() or scene_id
        except LookupError:
            raise LookupError(f"Shot {shot_id} not found in project {project_id}")
        except (ValueError, StateError) as exc:
            binding_error = str(exc)[:300]
        except Exception as exc:  # noqa: BLE001 — fail closed, never invent
            binding_error = str(exc)[:300]
        binding = (fresh or {}).get("binding")
        digest = str((fresh or {}).get("binding_digest") or "")

        # Scene entry for the anchor check (whatever the project record holds).
        # An unknown scene is a 404, not a guess: without the scene record no
        # gate below can be evaluated honestly.
        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        raw_scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        scene_entry: dict[str, Any] | None = None
        for entry in raw_scenes:
            if isinstance(entry, dict) and str(entry.get("scene_id") or "") == scene_id:
                scene_entry = entry
                break
        if scene_entry is None:
            raise LookupError(f"Shot {shot_id} not found in project {project_id}")

        # 2. Storyboard shot row (SELECTs only).
        shot_row: Any | None = None
        board_missing = False
        try:
            blueprint = storage.get_storyboard_blueprint(project_id, scene_id)
        except Exception:  # noqa: BLE001 — absence reads as missing board
            blueprint = None
        if blueprint is None:
            board_missing = True
        else:
            board_lookup_ok = True
            try:
                version_id = getattr(blueprint, "current_version_id", None)
                for shot in storage.list_storyboard_shots(blueprint.blueprint_id, version_id) or []:
                    if str(getattr(shot, "shot_id", "") or "") == shot_id:
                        shot_row = shot
                        break
            except Exception:  # noqa: BLE001 — read failure reads as missing board
                board_lookup_ok = False
            if shot_row is None and board_lookup_ok:
                # The board is known and this shot is not on it.
                raise LookupError(f"Shot {shot_id} not found in project {project_id}")
            if shot_row is None:
                board_missing = True

        prompts_table_present = _image_prompts_table_present(storage)

        # 3. D4 image gate.
        if board_missing or not prompts_table_present:
            image = _gate(NOT_YET, "No image prompt yet", "No Runway image prompt has been derived for this shot yet.")
            d4_ready = False
        elif shot_row is None:
            image = _gate(NOT_YET, "No image prompt yet", "No Runway image prompt has been derived for this shot yet.")
            d4_ready = False
        else:
            try:
                d4 = prompt_service.status_for_shot(shot_row)
                d4_state = str(d4.get("state") or "unapproved")
                d4_ready = bool(d4.get("render_ready"))
                d4_message = str(d4.get("message") or "")
                if d4_ready:
                    image = _gate(PASS, "Image ready", "The approved image prompt is current.")
                else:
                    image = _gate(
                        BLOCKED,
                        "Image waiting",
                        f"D4 image prompt {d4_state}{': ' + d4_message if d4_message else '.'}",
                    )
            except Exception as exc:  # noqa: BLE001 — fail closed, never invent
                d4_ready = False
                image = _gate(CANT_CHECK, "Can't check image", str(exc)[:300] or "The image prompt could not be read.")

        # 4. D6 send-text gate (same SELECTed row; raises, never sends).
        if board_missing or not prompts_table_present or shot_row is None:
            words = _gate(NOT_YET, "No words yet", "Send text cannot be checked before an image prompt exists.")
            d6_ready = False
        else:
            try:
                prompt_service.resolve_provider_send_text(shot_row)
                d6_ready = True
                words = _gate(PASS, "Words ready", "The send text passed the provider gate.")
            except StateError as exc:
                d6_ready = False
                condition = ""
                if isinstance(exc.metadata, dict):
                    condition = str(exc.metadata.get("condition") or "")
                words = _gate(
                    BLOCKED, "Words waiting", f"Send-text gate {condition or 'blocked'}: {str(exc.message or '')[:200]}".rstrip(": "),
                )
            except Exception as exc:  # noqa: BLE001 — fail closed
                d6_ready = False
                words = _gate(CANT_CHECK, "Can't check words", str(exc)[:300] or "The send text could not be read.")

        # 5. Setting-anchor gate (read-only resolution; scene record injected).
        anchor_ready = False
        if scene_entry is None:
            look = _gate(CANT_CHECK, "Can't check look", "The scene record could not be found, so the setting look cannot be judged.")
        else:
            try:
                from app.services.reference_validation import resolve_scene_reference_requirements

                _ = resolve_scene_reference_requirements(
                    project_id=project_id,
                    scene_id=scene_id,
                    storage=storage,
                    scene=scene_entry,
                )
                anchor_ready = True
                look = _gate(PASS, "Look set", "The setting look is settled on an approved canonical reference.")
            except Exception as exc:  # noqa: BLE001 — classify, never invent
                metadata = getattr(exc, "metadata", None)
                failure_type = metadata.get("failure_type") if isinstance(metadata, dict) else None
                if failure_type in _UNEVALUATABLE_ANCHOR_FAILURES:
                    look = _gate(CANT_CHECK, "Can't check look", "Project data is unavailable for anchor evaluation.")
                else:
                    look = _gate(BLOCKED, "Look needed", str(exc)[:300] or "The setting look is not settled.")

        # 6. Confirmation gate (durable row revalidated; creates nothing).
        try:
            confirmation = reference_service.get_shot_confirmation(project_id, shot_id)
            confirm_status = str(confirmation.get("status") or "missing")
        except Exception:  # noqa: BLE001 — a lookup failure reads as missing
            confirm_status = "missing"
        if confirm_status == "confirmed":
            settled = _gate(PASS, "Confirmed", "The binding was explicitly confirmed and still matches.")
            confirm_ready = True
        elif confirm_status == "stale":
            confirm_ready = False
            settled = _gate(BLOCKED, "Changed since confirmed", "The confirmed binding differs from the current resolution; confirm again.")
        elif confirm_status == "unverifiable":
            confirm_ready = False
            settled = _gate(CANT_CHECK, "Can't check", "The current binding cannot be resolved, so the confirmation cannot be judged.")
        else:
            confirm_ready = False
            settled = _gate(NOT_YET, "Not confirmed yet", "This shot has not been explicitly confirmed yet.")

        # 7. Latest persisted job (SELECT only).
        try:
            jobs = storage.list_jobs(project_id, limit=500) or []
        except Exception:  # noqa: BLE001 — absence reads as no jobs
            jobs = []
        job = _latest_job_for_shot(list(jobs or []), shot_id)

        # 8. Frozen-contract gate (persisted rows only; never mint, never rebuild).
        metadata = _job_metadata(job)
        contract_record = metadata.get("creative_generation_contract")
        manifest_record = metadata.get("creative_generation_manifest")
        refusal = _recorded_refusal_text(job) if job is not None else ""
        refusal_lower = refusal.lower()
        contract_refusal = next((code for code in _CONTRACT_REFUSALS if code in refusal_lower), "")
        if contract_refusal:
            contract = _gate(BLOCKED, "Contract blocked", f"Recorded refusal: {contract_refusal}.")
            contract_ready = False
        elif isinstance(contract_record, dict) and isinstance(manifest_record, dict) and manifest_record.get("manifest_fingerprint"):
            contract_ready = True
            contract = _gate(
                PASS,
                "Contract on file",
                f"A frozen contract is persisted with job {getattr(job, 'id', '')}; "
                "it was enforced at creation/submission, not re-checked here.",
            )
        elif job is None:
            contract_ready = False
            contract = _gate(NOT_YET, "No contract yet", "Frozen contracts are minted when a scene is prepared; nothing is prepared for this shot yet.")
        else:
            contract_ready = False
            contract = _gate(CANT_CHECK, "Can't check contract", "No frozen contract is persisted for this shot, and this view never prepares one.")

        # 9. Preflight gate — NEVER permission for a future send.
        base_blocked: list[str] = []
        for name, gate in (("image", image), ("words", words), ("look", look), ("settled", settled)):
            if gate["state"] == BLOCKED:
                base_blocked.append(f"{name}: {gate['detail']}")
        auth_refusal = next((code for code in _AUTHORIZATION_REFUSALS if code in refusal_lower), "")
        if base_blocked:
            preflight = _gate(BLOCKED, "Not authorized", f"First blocker — {base_blocked[0]}")
        elif auth_refusal:
            preflight = _gate(BLOCKED, "Not authorized", f"Recorded refusal: {auth_refusal}.")
        elif contract_ready and job is not None:
            execution = _router_execution(job)
            sent = bool(execution.get("submission_attempted")) or bool(
                str(execution.get("runway_task_id") or metadata.get("runway_task_id") or "").strip()
            ) or str(getattr(job, "status", "") or "").lower() in {"submitted", "rendering", "complete", "failed"}
            if sent:
                preflight = _gate(
                    PASS,
                    "Last send authorized",
                    f"Job {getattr(job, 'id', '')} was authorized when sent; a new send always needs a fresh preparation.",
                )
            else:
                preflight = _gate(NOT_YET, "Nothing to authorize yet", "A contract is on file but no send is recorded for this shot.")
        elif image["state"] == CANT_CHECK or words["state"] == CANT_CHECK or look["state"] == CANT_CHECK or settled["state"] == CANT_CHECK or contract["state"] == CANT_CHECK:
            preflight = _gate(CANT_CHECK, "Can't check authorization", "Only a fresh preparation can authorize a send, and this view never prepares.")
        else:
            preflight = _gate(NOT_YET, "Nothing to authorize yet", "No authorization record exists for this shot yet.")

        # 10. Spend + duplicate (persisted rows only; never priced, never looked up).
        spend_info = classify_spend(binding, job)
        spend = _gate(spend_info["state"], spend_info["label"], spend_info["detail"])
        duplicate_info = classify_duplicate(job)
        duplicate = _gate(duplicate_info["state"], duplicate_info["label"], duplicate_info["detail"])

        gates = {
            "image": image,
            "words": words,
            "look": look,
            "settled": settled,
            "contract": contract,
            "preflight": preflight,
            "spend": spend,
            "duplicate": duplicate,
        }

        # 11. Next action (single plain token) + blockers.
        blockers = [
            f"{name}: {gate['detail']}"
            for name, gate in gates.items()
            if gate["state"] == BLOCKED
        ]
        if binding_error and fresh is None:
            blockers.append(f"binding: {binding_error}")
        if image["state"] == BLOCKED:
            next_action = NEXT_APPROVE_IMAGE
        elif words["state"] == BLOCKED:
            next_action = NEXT_APPROVE_WORDS
        elif look["state"] == BLOCKED:
            next_action = NEXT_CONFIRM_ANCHOR
        elif settled["state"] == BLOCKED:
            next_action = NEXT_CONFIRM_BINDING
        elif contract["state"] == BLOCKED or preflight["state"] == BLOCKED:
            next_action = NEXT_PREPARE_SCENE
        elif duplicate["state"] == BLOCKED:
            next_action = NEXT_CHECK_DUPLICATE
        elif spend["state"] == BLOCKED:
            next_action = NEXT_CHECK_PRICE
        elif job is not None and str(getattr(job, "status", "") or "").lower() == "failed":
            next_action = NEXT_RETRY_JOB
        elif spend["state"] == CANT_CHECK and "local" in spend["detail"].lower():
            next_action = NEXT_CHECK_PRICE
        elif NOT_YET in {image["state"], words["state"]}:
            next_action = NEXT_APPROVE_IMAGE
        elif look["state"] == CANT_CHECK or settled["state"] == CANT_CHECK or contract["state"] == CANT_CHECK:
            next_action = NEXT_CHECK_DATA
        elif job is None or not _job_has_media(job):
            next_action = NEXT_AWAIT_MEDIA
        else:
            next_action = NEXT_NONE

        return {
            "project_id": project_id,
            "shot_id": shot_id,
            "scene_id": scene_id,
            "gates": gates,
            "spend": {
                "estimated_credits": spend_info["estimated_credits"],
                "cost_status": spend_info.get("cost_status"),
            },
            "duplicate": {
                "runway_task_id": str(
                    _router_execution(job).get("runway_task_id")
                    or _job_metadata(job).get("runway_task_id")
                    or ""
                ).strip()
                or None,
            },
            "binding_digest": digest or None,
            "latest_job_id": str(getattr(job, "id", "") or "") or None,
            "latest_job_status": str(getattr(job, "status", "") or "") or None,
            "next_action": next_action,
            "blockers": blockers,
        }


def _job_has_media(job: Any) -> bool:
    if job is None:
        return False
    payload = getattr(job, "output_payload", None)
    url = ""
    if payload is not None:
        url = str(getattr(payload, "asset_url", "") or getattr(payload, "output_url", "") or "")
    if not url and isinstance(_job_metadata(job).get("output_payload"), dict):
        url = str(_job_metadata(job)["output_payload"].get("asset_url") or "")
    status = str(getattr(job, "status", "") or "").lower()
    return status == "complete" and bool(url)


shot_integrity_gates_service = ShotIntegrityGatesService()

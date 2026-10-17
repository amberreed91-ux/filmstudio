"""Scene mint (Phase 2): persisted-confirmation binding + environment basis.

Minimal proof point. ``generate_scene`` mints a scene pass that binds the
persisted shot confirmation digest together with the environment basis.
The adapter re-checks the pass fail-closed at submit time.

Counted row states for the basis coverage check: ``approved`` + ``candidate``.
Rejected rows are tracked separately in ``rejected_environment_ref_ids``.

"Basis re-enumeration" at the adapter means: re-read the CURRENT environment
row IDs in the counted states and require every one of them to already be
listed in the pass's ``environment_basis`` (gap detection for rows that
appeared after the mint). It does NOT re-validate that basis members are
still approved -- per Q1 there is deliberately no reference-row approval
liveness at the adapter in this session.

Limitations recorded (consistent with the existing no-revocation and TTL
decision): no reference-row approval liveness at submit time, no revocation
handling, TTL carried forward unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.stability import (
    ValidationError,
    elapsed_ms,
    log_stage_event,
    start_timer,
)
from app.utils.helpers import as_non_empty_string

PROVIDER = "scene-mint"

# Row states enumerated into the environment basis coverage check (Q2).
COUNTED_STATES: tuple[str, ...] = ("approved", "candidate")

# Stable refusal codes (Q4). Codes are machine-stable; messages are
# creator-facing (specific, actionable, no scores or ratings).
SCENE_NOT_MINTED = "SCENE_NOT_MINTED"
CONFIRMATION_DIGEST_MISMATCH = "CONFIRMATION_DIGEST_MISMATCH"
ENVIRONMENT_BASIS_GAP = "ENVIRONMENT_BASIS_GAP"
# Retired by owner decision A1 (single-environment scenes mint with an empty
# rejected list; drift is refused as ENVIRONMENT_BASIS_GAP). Kept defined so
# the Q4 machine-stable code vocabulary never shrinks.
REJECTED_BASIS_EMPTY = "REJECTED_BASIS_EMPTY"

_CREATOR_MESSAGES: dict[str, str] = {
    SCENE_NOT_MINTED: (
        "This scene wasn't prepared with a saved shot confirmation, "
        "so it can't be submitted yet. Keep the shot confirmation saved, "
        "then prepare the scene again."
    ),
    CONFIRMATION_DIGEST_MISMATCH: (
        "The shot confirmation changed after this scene was prepared, "
        "so the scene can't be submitted as-is. Re-confirm the shot, "
        "then prepare the scene again."
    ),
    ENVIRONMENT_BASIS_GAP: (
        "A new environment option appeared after this scene was prepared, "
        "so the scene's environment list is out of date. Prepare the scene "
        "again so it sees the full current list."
    ),
    REJECTED_BASIS_EMPTY: (
        "This scene was prepared without any rejected environments recorded, "
        "so it can't be submitted under the current rule. Record at least "
        "one rejected environment, then prepare the scene again."
    ),
}


def creator_message(code: str) -> str:
    """Creator-facing message for a stable refusal code (Q4)."""
    return _CREATOR_MESSAGES[code]


def _refuse(
    code: str,
    *,
    project_id: str,
    shot_id: str,
    stage: str,
    extra: Optional[dict] = None,
) -> ValidationError:
    metadata: Dict[str, Any] = {"refusal_code": code}
    if extra:
        metadata.update(extra)
    return ValidationError(creator_message(code), stage=stage, metadata=metadata)


@dataclass
class ScenePass:
    """Minted scene pass. Absence of a pass means "not minted"."""

    project_id: str
    shot_id: str
    confirmed_digest: str
    environment_basis: List[str] = field(default_factory=list)
    rejected_environment_ref_ids: List[str] = field(default_factory=list)
    minted: bool = True


class ShotConfirmationStore:
    """Persisted (project, shot) -> confirmed digest. Test/acceptance double."""

    def __init__(self) -> None:
        self._digests: Dict[tuple[str, str], str] = {}

    def save(self, project_id: str, shot_id: str, digest: str) -> None:
        self._digests[(project_id, shot_id)] = digest

    def read(self, project_id: str, shot_id: str) -> Optional[str]:
        return self._digests.get((project_id, shot_id))


class EnvironmentRowStore:
    """Environment rows with lifecycle states. Test/acceptance double."""

    def __init__(self) -> None:
        self._states: Dict[str, str] = {}

    def put(self, ref_id: str, state: str) -> None:
        self._states[ref_id] = state

    def counted_ids(self) -> List[str]:
        return sorted(ref_id for ref_id, state in self._states.items() if state in COUNTED_STATES)

    def rejected_ids(self) -> List[str]:
        return sorted(ref_id for ref_id, state in self._states.items() if state == "rejected")


class SceneMintService:
    """Mints scene passes and enforces them at adapter submit time."""

    def __init__(
        self,
        confirmations: Optional[ShotConfirmationStore] = None,
        environments: Optional[EnvironmentRowStore] = None,
    ) -> None:
        self._confirmations = confirmations or ShotConfirmationStore()
        self._environments = environments or EnvironmentRowStore()

    # -- mint ----------------------------------------------------------
    def generate_scene(
        self,
        project_id: str,
        shot_id: str,
        *,
        require_persisted_confirmation: bool = False,
    ) -> ScenePass:
        """Mint a scene pass, or raise a fail-closed refusal (Q1-Q3, Q5/A1).

        Without ``require_persisted_confirmation=True`` nothing is minted
        (Q3). Decision A1: the rejected-environment list is recorded exactly
        as enumerated (possibly empty for single-environment scenes) instead
        of requiring non-empty (Q5, superseded); forgery and drift are caught
        at submit time by exact-equality against the live rejected set.
        """
        started = start_timer()
        stage = "scene.generate"
        try:
            project = as_non_empty_string(project_id)
            shot = as_non_empty_string(shot_id)

            if require_persisted_confirmation is not True:
                raise _refuse(SCENE_NOT_MINTED, project_id=project, shot_id=shot, stage=stage)

            digest = self._confirmations.read(project, shot)
            if not digest or not digest.strip():
                raise _refuse(
                    SCENE_NOT_MINTED,
                    project_id=project,
                    shot_id=shot,
                    stage=stage,
                    extra={"reason": "missing_persisted_confirmation"},
                )

            basis = self._environments.counted_ids()
            rejected = self._environments.rejected_ids()

            scene_pass = ScenePass(
                project_id=project,
                shot_id=shot,
                confirmed_digest=digest,
                environment_basis=basis,
                rejected_environment_ref_ids=rejected,
            )
            log_stage_event(
                project_id=project,
                job_id=shot,
                provider=PROVIDER,
                stage=stage,
                duration_ms=elapsed_ms(started),
                extra={"result": "minted", "basis_size": len(basis)},
            )
            return scene_pass
        except ValidationError:
            log_stage_event(
                project_id=project_id,
                job_id=shot_id,
                provider=PROVIDER,
                stage=stage,
                duration_ms=elapsed_ms(started),
                extra={"result": "refused"},
            )
            raise

    # -- adapter submit-time check --------------------------------------
    def adapter_submit(self, scene_pass: Optional[ScenePass]) -> dict:
        """Fail-closed submit-time enforcement of a minted pass (Q1, Q2, Q5)."""
        started = start_timer()
        stage = "scene.adapter_submit"
        project = scene_pass.project_id if scene_pass else ""
        shot = scene_pass.shot_id if scene_pass else ""
        try:
            if scene_pass is None or scene_pass.minted is not True:
                raise _refuse(SCENE_NOT_MINTED, project_id=project, shot_id=shot, stage=stage)

            current_digest = self._confirmations.read(project, shot)
            if not current_digest or current_digest != scene_pass.confirmed_digest:
                raise _refuse(
                    CONFIRMATION_DIGEST_MISMATCH,
                    project_id=project,
                    shot_id=shot,
                    stage=stage,
                )

            current_counted = self._environments.counted_ids()
            missing = [ref_id for ref_id in current_counted if ref_id not in scene_pass.environment_basis]
            if missing:
                raise _refuse(
                    ENVIRONMENT_BASIS_GAP,
                    project_id=project,
                    shot_id=shot,
                    stage=stage,
                    extra={"unlisted_ref_ids": missing},
                )

            # Decision A1: the recorded rejected enumeration must exactly
            # equal the live rejected set (either direction fails closed).
            # Empty equals empty, so single-environment scenes submit; any
            # drift (new, removed, or flipped rows) refuses with a re-prepare
            # recovery instead of the retired non-empty rule.
            current_rejected = self._environments.rejected_ids()
            if sorted(scene_pass.rejected_environment_ref_ids) != sorted(current_rejected):
                raise _refuse(
                    ENVIRONMENT_BASIS_GAP,
                    project_id=project,
                    shot_id=shot,
                    stage=stage,
                    extra={
                        "unlisted_ref_ids": sorted(set(current_rejected) - set(scene_pass.rejected_environment_ref_ids)),
                        "stale_ref_ids": sorted(set(scene_pass.rejected_environment_ref_ids) - set(current_rejected)),
                    },
                )

            log_stage_event(
                project_id=project,
                job_id=shot,
                provider=PROVIDER,
                stage=stage,
                duration_ms=elapsed_ms(started),
                extra={"result": "accepted"},
            )
            return {"status": "accepted", "project_id": project, "shot_id": shot}
        except ValidationError:
            log_stage_event(
                project_id=project,
                job_id=shot,
                provider=PROVIDER,
                stage=stage,
                duration_ms=elapsed_ms(started),
                extra={"result": "refused"},
            )
            raise

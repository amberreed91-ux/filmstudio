from __future__ import annotations

import logging
import re
import sqlite3
import uuid
import warnings
from datetime import datetime, timezone
from hashlib import sha1, sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.data.storage import StorageInterface, get_storage
from app.models.consistency import ReferenceAsset
from app.services.stability import ValidationError

logger = logging.getLogger(__name__)

# Browser-usable asset namespaces served by the FastAPI app (StaticFiles mounts
# in main.py). Anything outside these namespaces cannot be fetched by the
# frontend and must not be handed to the UI as an image URL.
_SERVED_URL_PREFIXES = ("/outputs/", "/previs-assets/", "/static/")
# Legacy orphaned namespace found in old database rows (/media/<file>.png).
# These files were never under a served mount; the on-disk location is
# <backend>/outputs/reference-assets/<file> and the browser URL is /outputs/...
_LEGACY_MEDIA_PREFIX = "/media/"
_ASSET_FILE_RE = re.compile(r"[A-Za-z0-9._-]+\.(?:png|jpg|jpeg|webp)")

# Upload constraints — identical envelope to the character look workflow
# (app.services.character_look_service.MAX_REFERENCE_BYTES / validation), so
# every image entering the Studio respects one size and format contract.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_UPLOAD_PIXELS = 24_000_000
_UPLOAD_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
# Every uploaded file lands inside the served reference-assets tree (mounted at
# /outputs by main.py). Filenames are service-generated UUIDs — no client-supplied
# path segment ever reaches the filesystem, and extensions come from the decoded
# image format, never from the client's filename.
_UPLOAD_STORAGE_DIR = "reference-assets"  # under the served outputs root


def validate_reference_upload(data: bytes) -> str:
    """Validate raw upload bytes and return the decoded image extension.

    Rejects empty bodies, oversized files, unsupported formats, truncated or
    unreadable images, animations, and decompression-bomb dimensions — before
    anything is persisted. The extension derives from the decoded image format,
    not from any client-supplied filename, so arbitrary or hostile file names
    cannot influence storage.
    """
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a JPEG, PNG, or WebP image up to 10 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                extension = _UPLOAD_EXTENSIONS.get(image.format)
                if not extension or image.width * image.height > _MAX_UPLOAD_PIXELS or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Unsupported image dimensions, animation, or format")
                image.verify()
            # verify() is metadata-only for some formats; decode once to reject
            # truncated images.
            with Image.open(BytesIO(data)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Choose a valid, still JPEG, PNG, or WebP image under 24 megapixels.") from exc
    return extension


def upload_reference_storage_path(outputs_dir: Path, project_id: str, target_type: str, target_id: str, extension: str) -> Path:
    """Return a contained storage path for one uploaded reference image.

    Project/target scope is hashed into the directory (no caller-controlled
    path segments) and the filename is a fresh UUID with the decoded extension.
    The result is guaranteed to stay inside ``outputs_dir`` so an upload can
    never escape the project asset storage boundary.
    """
    scope = sha256(f"{project_id}:{target_type}:{target_id}".encode("utf-8")).hexdigest()[:24]
    relative = Path(_UPLOAD_STORAGE_DIR) / "uploads" / scope / f"{uuid.uuid4().hex}.{extension}"
    target = (outputs_dir / relative).resolve()
    outputs_root = outputs_dir.resolve()
    if not target.is_relative_to(outputs_root):
        raise ValueError("Upload storage path escaped the project asset boundary")
    return target


def _kind_for_target(target_type: str) -> str:
    return "character_full" if target_type == "character" else "environment"


def register_uploaded_reference(
    storage: StorageInterface,
    *,
    project_id: str,
    target_type: str,
    target_id: str,
    category: str,
    data: bytes,
    outputs_dir: Path,
) -> dict:
    """Validate one uploaded image, persist it, and register it as a candidate.

    Fail-closed ordering: the image is fully validated before any bytes are
    written, and the registry row is written only after the file is durably
    saved (a failed write removes the file and raises — no partially valid
    reference asset and no orphan record). The new asset is always a plain
    supporting ``candidate`` with ``source_kind='uploaded'``; it never touches
    the canonical reference, never auto-approves, and reaches generation only
    through the existing candidate → approve → registry pipeline shared with
    URL-based references.
    """
    if target_type not in {"character", "setting"}:
        raise ValueError("target_type must be character or setting")
    target_id = str(target_id or "").strip()
    if not target_id or len(target_id) > 256:
        raise ValueError("target_id is required for a reference upload")
    category = str(category or "").strip()[:64] or "other"
    extension = validate_reference_upload(data)
    target = upload_reference_storage_path(outputs_dir, project_id, target_type, target_id, extension)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError as exc:
        raise ValueError("The reference image could not be saved. Please try again.") from exc
    image_url = f"/outputs/{target.relative_to(outputs_dir.resolve()).as_posix()}"
    asset = ReferenceAsset(
        ref_id=f"ref_upl_{uuid.uuid4().hex[:24]}",
        kind=_kind_for_target(target_type),
        image_url=image_url,
        source_shot_id="reference-upload",
        project_id=project_id,
        target_type=target_type,
        target_id=target_id,
        category=category,
        approval_state="candidate",
        canonical=False,
        source_kind="uploaded",
    )
    asset_dict = asset.model_dump(mode="json")
    try:
        saved = storage.save_reference_asset(asset_dict)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise ValueError("The reference could not be registered. Please try again.") from exc
    if not saved:
        target.unlink(missing_ok=True)
        raise ValueError("The reference could not be registered. Please try again.")
    logger.info(
        "REFERENCE_ASSET_UPLOADED | project=%s | ref_id=%s | target=%s/%s | category=%s | bytes=%d",
        project_id,
        asset.ref_id,
        target_type,
        target_id,
        category,
        len(data),
    )
    return asset_dict


def _backend_outputs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "outputs"


def _is_http_url(url: str) -> bool:
    return urlparse(url).scheme in {"http", "https"}


SCENE002_PROJECT_ID = "project_5907c60cddbc"
SCENE002_SETTING_ID = "loc-c8f88b9c"
LEGACY_SCENE002_REFERENCE_ID = "ref_env_6b726885ed67ae4d"


def _is_exact_scene002_setting_row(row: dict, *, project_id: str) -> bool:
    return (
        isinstance(row, dict)
        and str(row.get("project_id") or "") == project_id
        and str(row.get("target_type") or "") == "setting"
        and str(row.get("target_id") or "") == SCENE002_SETTING_ID
        and str(row.get("kind") or "") == "environment"
        and str(row.get("ref_id") or "") != LEGACY_SCENE002_REFERENCE_ID
    )


def _validate_scene002_setting_uri(image_url: str) -> str:
    image_url = str(image_url or "").strip()
    if not image_url:
        raise ValueError("An image URI is required")
    parsed = urlparse(image_url)
    if _is_http_url(image_url) and bool(parsed.netloc):
        return image_url
    if image_url.startswith(("/outputs/", "/previs-assets/")):
        visible = browser_view_asset_dict({"ref_id": "candidate", "image_url": image_url})
        if visible is not None:
            return str(visible["image_url"])
    raise ValueError("Choose a usable HTTP(S) URI or an existing served image path")


def browser_view_asset_dict(asset: dict) -> dict | None:
    """Return the asset dict with a browser-usable ``image_url``, or None.

    The visual-training UI renders ``image_url`` directly (via buildStudioApiUrl),
    so the API must never return URLs it cannot serve: filesystem paths,
    unserved namespaces, video outputs promoted as images, or pointers to files
    that no longer exist. Such rows are hidden (None) rather than shipped as
    broken image tags — the data itself is untouched on disk.
    """
    if not isinstance(asset, dict):
        return None
    url = str(asset.get("image_url") or "").strip()
    if not url:
        return None

    if _is_http_url(url):
        return asset

    if url.startswith(_SERVED_URL_PREFIXES):
        # /previs-assets and /static are aliases already; /outputs must map to a
        # real file, otherwise the browser gets a 404.
        rel = url.removeprefix("/outputs/")
        path = _backend_outputs_dir() / rel
        if url.startswith("/outputs/") and not path.is_file():
            return None
        return asset

    if url.startswith(_LEGACY_MEDIA_PREFIX):
        filename = url.removeprefix(_LEGACY_MEDIA_PREFIX)
        if not _ASSET_FILE_RE.fullmatch(filename):
            return None
        repaired = f"/outputs/reference-assets/{filename}"
        if (_backend_outputs_dir() / "reference-assets" / filename).is_file():
            repaired_asset = dict(asset)
            repaired_asset["image_url"] = repaired
            return repaired_asset
        # Legacy file is gone: hide the row instead of serving a 404.
        logger.info(
            "REFERENCE_ASSET_UNSERVABLE_HIDDEN | ref_id=%s | image_url=%s",
            asset.get("ref_id"),
            url,
        )
        return None

    # Any other relative value (filesystem path, video URL, empty namespace):
    # not a browser-fetchable image. Keep the row out of image-bearing lists.
    return None


def scene002_setting_asset_view(asset: dict) -> dict | None:
    """Return an exact-lifecycle URI that is both syntactically and browser usable."""
    if not isinstance(asset, dict):
        return None
    try:
        image_url = _validate_scene002_setting_uri(str(asset.get("image_url") or ""))
    except ValueError:
        return None
    return browser_view_asset_dict({**asset, "image_url": image_url})


def _look_ref_id(character_id: str, role: str) -> str:
    """Deterministic ref_id for a creator-approved look reference.

    Deterministic so re-approving a look (new version, new upload) updates the
    same registry row instead of accumulating one row per approval.
    """
    digest = sha1(f"{character_id}:{role}".encode("utf-8")).hexdigest()[:16]
    return f"ref_look_{digest}"


def _env_ref_id(project_id: str, scene_id: str) -> str:
    """Deterministic ref_id for an approved environment (scene) still."""
    digest = sha1(f"{project_id}:{scene_id}".encode("utf-8")).hexdigest()[:16]
    return f"ref_env_{digest}"


def _casting_ref_id(job_id: str, image_url: str) -> str:
    """Deterministic ref_id for one generated casting image.

    Keyed by casting job + image URL so re-syncing a finished set updates
    rows in place instead of accumulating one row per sync pass.
    """
    digest = sha1(f"{job_id}:{image_url}".encode("utf-8")).hexdigest()[:16]
    return f"ref_cast_{digest}"


def _casting_look_folder(project_id: str, character_id: str) -> str:
    """Look-folder prefix mirror of CharacterLookService._folder.

    Kept as a pure path derivation (no service import) so the sync can
    recognize casting portraits that belong to this character.
    """
    project_scope = sha256(f"{project_id}".encode("utf-8")).hexdigest()[:24]
    character_scope = sha256(f"{character_id}".encode("utf-8")).hexdigest()[:24]
    return f"references/character-looks/{project_scope}/{character_scope}"


class ReferenceAssetService:
    def __init__(self, storage: StorageInterface | None = None):
        self._storage = storage

    def _require_scene002_setting_entity(self, project_id: str) -> None:
        if project_id != SCENE002_PROJECT_ID:
            raise LookupError("Scene 002 setting references are scoped to the exact project")
        storage = self._require_storage()
        entity_reader = getattr(storage, "get_setting", None)
        if callable(entity_reader):
            try:
                entity = entity_reader(SCENE002_SETTING_ID, project_id)
            except TypeError:
                try:
                    entity = entity_reader(project_id=project_id, setting_id=SCENE002_SETTING_ID)
                except Exception as exc:
                    raise LookupError("The exact project-scoped setting entity is not resolvable") from exc
            except Exception as exc:
                raise LookupError("The exact project-scoped setting entity is not resolvable") from exc
            if hasattr(entity, "model_dump"):
                entity = entity.model_dump(mode="json")
            if (not isinstance(entity, dict)
                    or str(entity.get("project_id") or "") != project_id
                    or str(entity.get("setting_id") or entity.get("id") or "") != SCENE002_SETTING_ID
                    or (entity.get("canonical") is False)):
                raise LookupError("The exact project-scoped setting entity is not resolvable")
            return
        from app.services.universe_id_resolution import resolve_setting_entity

        if resolve_setting_entity(storage, project_id, SCENE002_SETTING_ID) is None:
            raise LookupError("The exact project-scoped setting entity is not resolvable")

    def _require_storage(self):
        storage = self._storage or get_storage("sqlite")
        if storage is None:
            raise RuntimeError("Storage not configured")
        return storage

    def propose(self, project_id: str, shot_id: str, video_url: str) -> dict:
        attempts = self._require_storage().list_render_attempts(
            project_id=project_id,
            shot_id=shot_id,
            limit=10,
        )
        if not attempts:
            raise LookupError(
                f"No render attempts found for shot {shot_id} in project {project_id}"
            )
        for attempt in attempts:
            score_json = attempt.get("score_json") or {}
            character_state = (score_json.get("dimensions") or {}).get("character_state") or {}
            if character_state.get("score", 0) >= 90 and score_json.get("verdict", "") == "pass":
                proposal = ReferenceAsset(
                    ref_id=f"proposal_{uuid4().hex[:12]}",
                    kind="character_full",
                    image_url=video_url,
                    source_shot_id=shot_id,
                    project_id=project_id,
                )
                logger.info(
                    "REFERENCE_PROPOSAL_GENERATED | project=%s | shot=%s | attempt=%s",
                    project_id,
                    shot_id,
                    attempt.get("attempt_n"),
                )
                return {
                    "proposal": proposal.model_dump(mode="json"),
                    "qualifying_attempt": attempt.get("attempt_n"),
                    "note": "This is a proposal only; explicit confirmation is required.",
                }
        raise ValueError(
            f"Shot {shot_id} has no qualifying render attempt for reference promotion."
        )

    def confirm(self, project_id: str, payload: ReferenceAsset) -> dict:
        if payload.target_type == "setting" and payload.target_id == SCENE002_SETTING_ID:
            raise ValueError("Scene 002 setting references must use the separate create, approve, and canonical actions")
        if payload.project_id != project_id:
            raise ValueError(
                f"payload.project_id={payload.project_id!r} does not match URL project_id={project_id!r}"
            )
        clean_id = payload.ref_id.replace("proposal_", "ref_")
        if clean_id == payload.ref_id:
            clean_id = f"ref_{uuid4().hex[:24]}"
        # Canonical status is server-owned. The wire model keeps the field so
        # existing clients remain compatible, but a client-supplied value can
        # never confer authority: it is stripped here and the row is persisted
        # non-canonical. Canonical designation happens only through the explicit
        # designation operations (and the creator approval the sync mirrors).
        if payload.canonical:
            logger.warning(
                "REFERENCE_ASSET_CANONICAL_CLIENT_SUPPLIED_IGNORED | project=%s | ref_id=%s",
                project_id,
                clean_id,
            )
        asset = payload.model_copy(update={"ref_id": clean_id, "canonical": False})
        asset_dict = asset.model_dump(mode="json")
        try:
            created = self._require_storage().create_reference_asset(asset_dict)
        except sqlite3.IntegrityError as exc:
            raise ValueError("Reference asset ID already exists") from exc
        if not created:
            raise ValueError("Reference asset could not be created")
        logger.info(
            "REFERENCE_ASSET_CONFIRMED | project=%s | ref_id=%s | kind=%s | source_shot=%s",
            project_id,
            asset.ref_id,
            asset.kind,
            asset.source_shot_id,
        )
        return asset_dict

    def create_scene002_setting_candidate(
        self, project_id: str, image_url: str, *, category: str | None = None,
    ) -> dict:
        """Create a fresh candidate for the exact entity setting; never deduplicate URI."""
        image_url = _validate_scene002_setting_uri(image_url)
        self._require_scene002_setting_entity(project_id)
        storage = self._require_storage()
        create = getattr(storage, "create_scene002_setting_reference", None)
        if not callable(create):
            raise RuntimeError("Storage does not support create-only Scene 002 setting references")
        ref_id = f"ref_set_{uuid4().hex}"
        if not create(
            ref_id=ref_id,
            project_id=project_id,
            image_url=image_url,
            created_at=datetime.now(timezone.utc).isoformat(),
            category=str(category or "environment")[:64],
        ):
            raise ValueError("Setting reference could not be created")
        row = storage.get_reference_asset(ref_id)
        if not _is_exact_scene002_setting_row(row, project_id=project_id):
            raise RuntimeError("Created setting reference failed exact-scope verification")
        return row

    def upload_scene002_setting_candidate(
        self, project_id: str, data: bytes, *, category: str | None = None,
        outputs_dir: Path | None = None,
    ) -> dict:
        """Register one uploaded image as a fresh exact-target candidate.

        Create-only by construction: the fresh ``ref_set_`` identity is written
        through the insert-only storage call, so an identity collision fails the
        write instead of replacing an existing row, and no row sharing the same
        image URI is ever touched. The new row always starts
        ``approval_state=candidate`` / ``canonical=False`` for exactly
        ``setting/loc-c8f88b9c`` in the exact project, never reusing the legacy
        scene-targeted reference ID.
        """
        self._require_scene002_setting_entity(project_id)
        category = str(category or "environment").strip()[:64] or "environment"
        extension = validate_reference_upload(data)
        outputs_dir = outputs_dir or _backend_outputs_dir()
        target = upload_reference_storage_path(
            outputs_dir, project_id, "setting", SCENE002_SETTING_ID, extension,
        )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as exc:
            raise ValueError("The reference image could not be saved. Please try again.") from exc
        image_url = f"/outputs/{target.relative_to(outputs_dir.resolve()).as_posix()}"
        storage = self._require_storage()
        create = getattr(storage, "create_scene002_setting_reference", None)
        if not callable(create):
            target.unlink(missing_ok=True)
            raise RuntimeError("Storage does not support create-only Scene 002 setting references")
        ref_id = f"ref_set_{uuid4().hex}"
        try:
            created = create(
                ref_id=ref_id,
                project_id=project_id,
                image_url=image_url,
                created_at=datetime.now(timezone.utc).isoformat(),
                category=category,
            )
        except sqlite3.IntegrityError as exc:
            target.unlink(missing_ok=True)
            raise ValueError("Reference asset ID already exists") from exc
        except Exception:
            target.unlink(missing_ok=True)
            raise
        if not created:
            target.unlink(missing_ok=True)
            raise ValueError("Setting reference could not be created")
        row = storage.get_reference_asset(ref_id)
        if not _is_exact_scene002_setting_row(row, project_id=project_id):
            # Fail closed: never leave a partially verified row behind.
            try:
                storage.delete_reference_asset(ref_id, project_id)
            except Exception:
                logger.exception("SCENE002_SETTING_REFERENCE_ROLLBACK_FAILED | ref_id=%s", ref_id)
            target.unlink(missing_ok=True)
            raise RuntimeError("Uploaded setting reference failed exact-scope verification")
        logger.info(
            "SCENE002_SETTING_REFERENCE_UPLOADED | project=%s | ref_id=%s | target=%s/%s",
            project_id, ref_id, "setting", SCENE002_SETTING_ID,
        )
        return row

    def list_scene002_setting_references(self, project_id: str) -> list[dict]:
        """Read only exact-target rows through scoped storage; never synchronize."""
        self._require_scene002_setting_entity(project_id)
        try:
            rows = self._require_storage().list_reference_assets(
                project_id=project_id, target_type="setting", target_id=SCENE002_SETTING_ID, limit=200,
            ) or []
        except TypeError:
            rows = self._require_storage().list_reference_assets(project_id=project_id, limit=200) or []
        visible_rows = []
        for row in rows:
            if not _is_exact_scene002_setting_row(row, project_id=project_id):
                continue
            visible = scene002_setting_asset_view(row)
            if visible is not None:
                visible_rows.append(visible)
        return visible_rows

    def approve_scene002_setting_reference(self, project_id: str, ref_id: str) -> dict:
        self._require_scene002_setting_entity(project_id)
        storage = self._require_storage()
        row = storage.get_reference_asset(ref_id)
        if not _is_exact_scene002_setting_row(row, project_id=project_id):
            raise LookupError("Exact Scene 002 setting reference not found")
        if row.get("approval_state") != "candidate":
            raise ValueError("Only a noncanonical candidate can be explicitly approved; rejected references cannot be recovered")
        if scene002_setting_asset_view(row) is None:
            raise ValueError("Only a usable candidate image reference can be approved")
        if bool(row.get("canonical")):
            raise ValueError("Only a noncanonical candidate can be explicitly approved")
        if not storage.approve_scene002_setting_reference(ref_id=ref_id, project_id=project_id):
            raise LookupError("Candidate reference was not approved")
        approved = storage.get_reference_asset(ref_id)
        if not _is_exact_scene002_setting_row(approved, project_id=project_id):
            raise LookupError("Approved reference no longer resolves")
        return approved

    def reject_scene002_setting_reference(self, project_id: str, ref_id: str) -> dict:
        """Reject exactly one project/setting-owned reference without clearing canonical state."""
        self._require_scene002_setting_entity(project_id)
        storage = self._require_storage()
        row = storage.get_reference_asset(ref_id)
        if not _is_exact_scene002_setting_row(row, project_id=project_id):
            raise LookupError("Exact Scene 002 setting reference not found")
        reject = getattr(storage, "reject_scene002_setting_reference", None)
        if not callable(reject) or not reject(
            ref_id=ref_id, project_id=project_id, setting_id=SCENE002_SETTING_ID,
        ):
            raise ValueError("Reference could not be rejected in its exact setting scope")
        rejected = storage.get_reference_asset(ref_id)
        if not _is_exact_scene002_setting_row(rejected, project_id=project_id) or rejected.get("approval_state") != "rejected":
            raise LookupError("Rejected reference failed exact-scope verification")
        return rejected

    def designate_scene002_setting_reference_canonical(self, project_id: str, ref_id: str) -> dict:
        self._require_scene002_setting_entity(project_id)
        storage = self._require_storage()
        row = storage.get_reference_asset(ref_id)
        if not _is_exact_scene002_setting_row(row, project_id=project_id):
            raise LookupError("Exact Scene 002 setting reference not found")
        if row.get("approval_state") != "approved":
            raise ValueError("Only an approved exact-target environment reference can be canonical")
        if scene002_setting_asset_view(row) is None:
            raise ValueError("Only a usable approved image reference can be canonical")
        if not storage.set_scene002_setting_reference_canonical(
            ref_id=ref_id, project_id=project_id, canonical=True,
        ):
            raise LookupError("Approved reference could not be designated canonical")
        designated = storage.get_reference_asset(ref_id)
        if not _is_exact_scene002_setting_row(designated, project_id=project_id):
            raise LookupError("Canonical reference no longer resolves")
        return designated

    def designate_setting_reference_canonical(
        self, project_id: str, setting_id: str, ref_id: str,
    ) -> dict:
        """Explicitly designate one approved environment reference as canonical.

        Server-authoritative and scope-checked, the generic counterpart of
        :meth:`designate_scene002_setting_reference_canonical`:

        - the exact project-scoped canonical setting entity must resolve through
          the same provenance rules the production resolver enforces, so a
          phantom or scene-labelled target can never be designated;
        - the row must belong to this project and target exactly this setting
          entity (no cross-project or cross-scene promotion);
        - the row must be an environment reference whose authoritative state is
          ``approved`` with a browser-usable image, so candidates, rejected,
          revoked, or unusable references fail closed;
        - designation is exclusive, so competing canonical anchors for the same
          setting cannot coexist.

        Canonical status is conferred only by this explicit operation (or by
        the creator approval mirrored by the sync). A client-supplied flag can
        never reach it — see :meth:`confirm`, which strips the field. Every
        failed check raises before any write, leaving existing canonical
        authority untouched.
        """
        from app.services.reference_validation import verify_setting_entity_scope

        storage = self._require_storage()
        project_id = str(project_id or "").strip()
        setting_id = str(setting_id or "").strip()
        ref_id = str(ref_id or "").strip()
        if not project_id or not setting_id or not ref_id:
            raise ValueError("project_id, setting_id, and ref_id are required")
        if project_id == SCENE002_PROJECT_ID and setting_id == SCENE002_SETTING_ID:
            # The exact Scene 002 lifecycle owns this pair; the generic path must
            # never become a weaker shorthand for it.
            raise ValueError(
                "Scene 002 setting references must use the separate create, approve, and canonical actions"
            )
        verify_setting_entity_scope(
            storage=storage, project_id=project_id, setting_id=setting_id,
        )
        row = storage.get_reference_asset(ref_id)
        if (
            not isinstance(row, dict)
            or str(row.get("ref_id") or "") != ref_id
            or str(row.get("project_id") or "") != project_id
        ):
            raise LookupError("Reference asset not found in this project")
        if str(row.get("target_type") or "") != "setting" or str(row.get("target_id") or "") != setting_id:
            raise ValueError("Reference asset does not target the exact canonical setting entity")
        if str(row.get("kind") or "") != "environment":
            raise ValueError("Only an environment reference can be canonical for a setting")
        state = str(row.get("approval_state") or "").strip().lower()
        if state != "approved":
            raise ValueError(
                f"Only an approved environment reference can be canonical "
                f"(approval_state={state or 'unknown'!r}); approve it first"
            )
        if browser_view_asset_dict(row) is None:
            raise ValueError("Only a usable approved image reference can be canonical")
        if not storage.set_setting_reference_canonical(
            ref_id=ref_id, project_id=project_id, setting_id=setting_id, canonical=True,
        ):
            raise LookupError("Approved reference could not be designated canonical")
        designated = storage.get_reference_asset(ref_id)
        if (
            not isinstance(designated, dict)
            or str(designated.get("ref_id") or "") != ref_id
            or not bool(designated.get("canonical"))
        ):
            raise LookupError("Designated reference no longer resolves")
        logger.info(
            "SETTING_REFERENCE_CANONICAL_DESIGNATED | project=%s | setting=%s | ref_id=%s",
            project_id,
            setting_id,
            ref_id,
        )
        return browser_view_asset_dict(designated) or designated

    def list_assets(
        self,
        project_id: str,
        kind: str | None = None,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        approval_state: str | None = None,
    ) -> list[dict]:
        """Confirmed assets with browser-usable image URLs."""
        assets = self._require_storage().list_reference_assets(
            project_id=project_id,
            kind=kind,
            target_type=target_type,
            target_id=target_id,
            approval_state=approval_state,
        )
        visible: list[dict] = []
        for asset in assets:
            view = browser_view_asset_dict(asset)
            if view is not None:
                visible.append(view)
        return visible

    def list_library(self, project_id: str, target_type: str, target_id: str) -> dict:
        """Return canonical and supporting references for one existing entity."""
        if target_type not in {"character", "setting"} or not str(target_id).strip():
            raise ValueError("target_type must be character or setting and target_id is required")
        storage = self._require_storage()
        rows = self.list_assets(project_id, target_type=target_type, target_id=target_id)
        canonical = next((row for row in rows if bool(row.get("canonical"))), None)
        supporting = [row for row in rows if not bool(row.get("canonical")) and row.get("approval_state") == "approved"]
        candidates = [row for row in rows if row.get("approval_state") == "candidate"]
        categories = sorted({str(row.get("category") or "general") for row in rows})
        return {
            "project_id": project_id,
            "target_type": target_type,
            "target_id": target_id,
            "canonical": canonical,
            "supporting": supporting,
            "candidates": candidates,
            "categories": categories,
            "coverage": "covered" if supporting else "not_covered",
        }

    def get_asset(self, ref_id: str) -> dict | None:
        """Public read for a single registry row; routes must not reach into storage."""
        return self._require_storage().get_reference_asset(ref_id)

    def save_library_asset(self, asset: dict) -> bool:
        """Public write for an explicitly supplied library asset; same gate as confirm."""
        return self._require_storage().save_reference_asset(asset)

    def approve_supporting(self, project_id: str, ref_id: str) -> dict:
        storage = self._require_storage()
        asset = storage.get_reference_asset(ref_id)
        if not asset or asset.get("project_id") != project_id:
            raise LookupError("Reference asset not found")
        if asset.get("target_type") == "setting" and asset.get("target_id") == SCENE002_SETTING_ID:
            raise ValueError("Use the explicit setting-reference approval operation")
        if asset.get("canonical"):
            return browser_view_asset_dict(asset) or asset
        if not storage.update_reference_asset_state(ref_id, project_id, "approved"):
            raise LookupError("Reference asset not found")
        approved = storage.get_reference_asset(ref_id) or asset
        return browser_view_asset_dict(approved) or approved

    def register_upload(
        self,
        project_id: str,
        target_type: str,
        target_id: str,
        category: str,
        data: bytes,
        *,
        outputs_dir: Path | None = None,
    ) -> dict:
        """Register one uploaded image as a candidate supporting reference."""
        return register_uploaded_reference(
            self._require_storage(),
            project_id=project_id,
            target_type=target_type,
            target_id=target_id,
            category=category,
            data=data,
            outputs_dir=outputs_dir or _backend_outputs_dir(),
        )

    def remove_supporting(self, project_id: str, ref_id: str) -> bool:
        storage = self._require_storage()
        asset = storage.get_reference_asset(ref_id)
        if not asset or asset.get("project_id") != project_id:
            raise LookupError("Reference asset not found")
        if asset.get("target_type") == "setting" and asset.get("target_id") == SCENE002_SETTING_ID:
            raise ValueError("Scene 002 setting references are not removable through the legacy library")
        if asset.get("canonical"):
            raise ValueError("Canonical reference is protected; explicitly change the canonical asset first")
        return bool(storage.delete_reference_asset(ref_id, project_id))

    # ── Creator-approved visual sync ────────────────────────────────────────

    @staticmethod
    def _canonical_setting_id_for_sync(storage: StorageInterface, project_id: str, scene_id: str) -> str:
        """Resolve one scene's canonical setting entity id, or "" when unresolved.

        Read-only and best-effort: the sync must never fail, and must never
        invent a target identity, because a scene's canonical setting entity is
        missing. Unresolved scenes keep the scene-scoped convention instead.
        """
        try:
            from app.services.reference_validation import resolve_canonical_setting_id

            return str(
                resolve_canonical_setting_id(
                    project_id=project_id, scene_id=scene_id, storage=storage,
                ) or ""
            ).strip()
        except Exception as exc:  # noqa: BLE001 — an unresolvable setting is not a sync failure
            logger.debug(
                "REFERENCE_SYNC_SETTING_ID_UNRESOLVED | project=%s | scene=%s | error=%s",
                project_id,
                scene_id,
                exc,
            )
            return ""

    @staticmethod
    def _sync_environment_canonical_flag(
        storage: StorageInterface, *, project_id: str, setting_id: str, ref_id: str,
    ) -> bool:
        """Whether the sync may mark this environment row canonical.

        True unless a *different* approved canonical environment anchor already
        holds the same (project, setting) scope. An already-canonical row keeps
        its status — synchronization never downgrades a valid approved
        designation — and a scope whose authority was explicitly designated is
        never contradicted by the sync.
        """
        try:
            existing = storage.get_reference_asset(ref_id)
        except Exception:  # noqa: BLE001 — a lookup failure must not claim authority
            existing = None
        if isinstance(existing, dict) and bool(existing.get("canonical")):
            return True
        try:
            rows = storage.list_reference_assets(
                project_id=project_id, target_type="setting", target_id=setting_id, limit=200,
            ) or []
        except Exception:  # noqa: BLE001 — a listing failure must not claim authority
            rows = []
        competing = [
            row for row in rows
            if isinstance(row, dict)
            and str(row.get("ref_id") or "") != ref_id
            and bool(row.get("canonical"))
            and str(row.get("approval_state") or "approved") == "approved"
            and str(row.get("kind") or "") == "environment"
        ]
        return not competing

    def _upsert_synced_reference(self, storage: StorageInterface, asset: dict) -> bool:
        """Insert or update one synced reference row. True only when it changed."""
        ref_id = str(asset.get("ref_id") or "")
        if not ref_id:
            return False
        try:
            existing = storage.get_reference_asset(ref_id)
        except Exception as exc:
            logger.debug("REFERENCE_SYNC_LOOKUP_FAILED | ref_id=%s | error=%s", ref_id, exc)
            existing = None
        if (
            isinstance(existing, dict)
            and existing.get("image_url") == asset.get("image_url")
            and existing.get("kind") == asset.get("kind")
            # Scope/authority must match too: a legacy row carrying the same
            # deterministic ref_id but stale metadata (e.g. empty target scope
            # or canonical=0 from the pre-recovery pipeline) would otherwise be
            # silently skipped, leaving the creator's approval invisible to the
            # reference gate. Idempotency is preserved — a fully converged row
            # still short-circuits, so re-syncing never churns.
            and existing.get("target_type") == asset.get("target_type")
            and existing.get("target_id") == asset.get("target_id")
            and bool(existing.get("canonical")) == bool(asset.get("canonical"))
            and existing.get("approval_state") == asset.get("approval_state")
        ):
            return False
        try:
            payload = ReferenceAsset(
                ref_id=ref_id,
                kind=asset["kind"],
                image_url=asset["image_url"],
                source_shot_id=asset.get("source_shot_id"),
                project_id=asset["project_id"],
                target_type=asset.get("target_type"),
                target_id=asset.get("target_id"),
                category=asset.get("category"),
                approval_state=asset.get("approval_state", "approved"),
                canonical=bool(asset.get("canonical", False)),
                source_kind=asset.get("source_kind", "confirmed"),
            )
        except Exception as exc:
            logger.warning("REFERENCE_SYNC_ROW_INVALID | ref_id=%s | error=%s", ref_id, exc)
            return False
        stored = payload.model_dump(mode="json")
        stored["created_at"] = asset.get("created_at")
        saved = storage.save_reference_asset(stored)
        if saved:
            logger.info("REFERENCE_ASSET_SYNCED | ref_id=%s | kind=%s", ref_id, asset["kind"])
        return bool(saved)

    def sync_creator_references(self, project_id: str) -> dict[str, int]:
        """Mirror creator-approved visuals into the confirmed reference registry.

        Three conservative sources. The first two are already gated by an
        explicit human approval elsewhere in the product:

        - Locked character looks: a look only reaches ``locked`` status through
          the creator's explicit approval of chosen face/full-body uploads, so
          those images are confirmed references by construction.
        - Approved environment stills: a storyboard frame the creator approved
          in Previs carries the scene's approved look (complete, non-fallback,
          approved previs rows only, one per scene — the newest wins).
        - Generated casting candidates: finished casting portraits are mirrored
          as unapproved ``candidate`` rows (``source_kind='generated'``) so
          Reference Space can review them. They never auto-approve, never go
          canonical, and stay training-ineligible until the existing approval
          flow approves them.

        The visual-training panels read this registry, so without the sync a
        project could finish approving looks and still see "No approved
        references yet" — approval lived in the character continuity document
        while eligibility only looked at reference_assets rows.

        Additive and idempotent: deterministic ref_ids mean a re-sync updates
        rows in place rather than duplicating, nothing is deleted or
        downgraded, and rows confirmed through the explicit propose/confirm
        flow are never touched. Per-source failures are logged and skipped —
        listing references must not break because one continuity document or
        previs row is malformed.
        """
        storage = self._require_storage()
        if not hasattr(storage, "save_reference_asset"):
            return {"synced": 0, "character_looks": 0, "environment_stills": 0}

        from app.utils.character_appearance import appearance_approval
        from app.utils.character_casting import casting_jobs

        now = datetime.now(timezone.utc).isoformat()
        looks_synced = 0
        env_synced = 0
        casting_synced = 0

        try:
            characters = storage.get_characters(project_id) or []
        except Exception as exc:
            logger.warning("REFERENCE_SYNC_CHARACTERS_FAILED | project=%s | error=%s", project_id, exc)
            characters = []

        for character in characters:
            if not isinstance(character, dict) or not str(character.get("id") or "").strip():
                continue
            try:
                approval = appearance_approval(character)
            except Exception:
                # Malformed continuity document: skip this character, keep syncing.
                continue
            if approval.get("status") != "locked":
                continue
            has_face_reference = bool(str(approval.get("face_image_url") or "").strip())
            for field, kind, role in (
                ("face_image_url", "character_face", "face"),
                ("body_image_url", "character_full", "full_body"),
            ):
                url = str(approval.get(field) or "").strip()
                if not url:
                    continue
                if self._upsert_synced_reference(
                    storage,
                    {
                        "ref_id": _look_ref_id(str(character["id"]), role),
                        "project_id": project_id,
                        "kind": kind,
                        "image_url": url,
                        "source_shot_id": "character-look-approval",
                        "created_at": str(approval.get("approved_at") or now),
                        "target_type": "character",
                        "target_id": str(character["id"]),
                        "category": role,
                        # One canonical identity anchor per target. The approved
                        # face is authoritative when present; a body-only look
                        # remains canonical until a face is explicitly locked.
                        "canonical": role == "face" or (role == "full_body" and not has_face_reference),
                        "source_kind": "confirmed",
                    },
                ):
                    looks_synced += 1

        for character in characters:
            if not isinstance(character, dict) or not str(character.get("id") or "").strip():
                continue
            character_id = str(character["id"])
            try:
                jobs = casting_jobs(character)
            except Exception:
                # Malformed continuity document: skip this character, keep syncing.
                continue
            if not jobs:
                continue
            folder_prefix = f"/outputs/{_casting_look_folder(project_id, character_id)}/"
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                job_id = str(job.get("id") or "").strip()
                if not job_id:
                    continue
                for url in job.get("images", []) or []:
                    if not isinstance(url, str) or not url.startswith(folder_prefix):
                        continue
                    filename = url.removeprefix(folder_prefix)
                    # Same strict shape the look service requires for casting
                    # portraits: hex filename + still-image extension.
                    if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", filename):
                        continue
                    if not (_backend_outputs_dir() / _casting_look_folder(project_id, character_id) / filename).is_file():
                        continue
                    ref_id = _casting_ref_id(job_id, url)
                    try:
                        existing = storage.get_reference_asset(ref_id)
                    except Exception:
                        existing = None
                    if isinstance(existing, dict) and (
                        str(existing.get("approval_state") or "") == "approved" or bool(existing.get("canonical"))
                    ):
                        # Explicitly approved or canonicalized elsewhere: the
                        # sync must never downgrade it back to a candidate.
                        continue
                    if self._upsert_synced_reference(
                        storage,
                        {
                            "ref_id": ref_id,
                            "project_id": project_id,
                            "kind": "character_face",
                            "image_url": url,
                            "source_shot_id": f"casting:{job_id}",
                            "created_at": str(job.get("created_at") or now),
                            "target_type": "character",
                            "target_id": character_id,
                            "category": "casting",
                            "approval_state": "candidate",
                            "canonical": False,
                            "source_kind": "generated",
                        },
                    ):
                        casting_synced += 1

        try:
            previs_rows = storage.load_previs_images(project_id) or []
        except Exception as exc:
            logger.warning("REFERENCE_SYNC_PREVIS_FAILED | project=%s | error=%s", project_id, exc)
            previs_rows = []

        approved_by_scene: dict[str, dict] = {}
        for row in previs_rows:
            if not isinstance(row, dict):
                continue
            # ``approve_previs_image`` (the Previs UI approve action) sets
            # ``approved=1, status='approved'``; pipeline completion leaves
            # ``status='complete'`` with ``approved=0``. An approved row always
            # implies a completed render — ``approve_previs_image`` refuses
            # anything that is not complete with a real output — so both
            # states are eligible. The approved flag remains the creator-decision
            # authority; status alone must not silently drop an approved frame.
            if str(row.get("status") or "") not in {"complete", "approved"} or bool(row.get("fallback")):
                continue
            if not bool(row.get("approved")):
                continue
            image_path = str(row.get("image_path") or "").strip()
            scene_id = str(row.get("scene_id") or "").strip()
            if not image_path or not scene_id:
                continue
            if not image_path.startswith(("/previs-assets/", "/outputs/")):
                continue
            stamp = str(row.get("updated_at") or row.get("created_at") or "")
            current = approved_by_scene.get(scene_id)
            if current is None or stamp > str(current.get("_stamp") or ""):
                approved_by_scene[scene_id] = {**row, "_stamp": stamp}

        # Canonical blueprint approval: the approve action in the Previs UI
        # marks shots approved and records each shot's rendered storyboard
        # image. Approved shots with a real image are the approved environment
        # look for their scene.
        try:
            blueprints = storage.list_storyboard_blueprints(project_id) or []
        except Exception as exc:
            logger.warning("REFERENCE_SYNC_BLUEPRINTS_FAILED | project=%s | error=%s", project_id, exc)
            blueprints = []

        for raw_blueprint in blueprints:
            # list_storyboard_blueprints returns pydantic models; accept dicts too.
            if isinstance(raw_blueprint, dict):
                blueprint = raw_blueprint
            else:
                try:
                    blueprint = raw_blueprint.model_dump(mode="json")
                except Exception:
                    continue
            version_id = str(blueprint.get("approved_version_id") or "").strip()
            scene_id = str(blueprint.get("scene_id") or "").strip()
            if not version_id or not scene_id or scene_id in approved_by_scene:
                continue
            try:
                shots = storage.list_storyboard_shots(str(blueprint.get("blueprint_id")), version_id) or []
            except Exception as exc:
                logger.debug("REFERENCE_SYNC_BLUEPRINT_SHOTS_FAILED | blueprint=%s | error=%s", blueprint.get("blueprint_id"), exc)
                shots = []
            for shot in shots:
                # list_storyboard_shots returns pydantic models; be tolerant of
                # dict-shaped storages too.
                if isinstance(shot, dict):
                    data = shot
                else:
                    try:
                        data = shot.model_dump(mode="json")
                    except Exception:
                        continue
                if str(data.get("status") or "") not in {"approved", "locked"}:
                    continue
                image_url = str(data.get("storyboard_image_url") or "").strip()
                if not image_url:
                    continue
                approved_by_scene[scene_id] = {
                    "scene_id": scene_id,
                    "shot_id": str(data.get("shot_id") or ""),
                    "image_path": image_url,
                    "updated_at": str(data.get("updated_at") or ""),
                }
                break

        for scene_id, row in approved_by_scene.items():
            ref_id = _env_ref_id(project_id, scene_id)
            # Write the target identity the production consumer resolves: the
            # canonical setting ENTITY id, not the scene id. When the entity
            # cannot be resolved the scene-scoped id is preserved (identical to
            # prior behaviour, deterministic ref_id unchanged) — such a scene
            # cannot reach production at all, because the resolver fails closed
            # at setting identity provenance before any reference is used.
            setting_target = self._canonical_setting_id_for_sync(storage, project_id, scene_id) or scene_id
            if self._upsert_synced_reference(
                storage,
                {
                    "ref_id": ref_id,
                    "project_id": project_id,
                    "kind": "environment",
                    "image_url": str(row.get("image_path") or "").strip(),
                    "source_shot_id": str(row.get("shot_id") or f"scene:{scene_id}"),
                    "created_at": str(row.get("updated_at") or row.get("created_at") or now),
                    "target_type": "setting",
                    "target_id": setting_target,
                    "category": "canonical",
                    # Never claim canonical when a different canonical anchor
                    # already holds this scope: the creator's explicit
                    # designation stays the single authority.
                    "canonical": self._sync_environment_canonical_flag(
                        storage, project_id=project_id, setting_id=setting_target, ref_id=ref_id,
                    ),
                    "source_kind": "confirmed",
                },
            ):
                env_synced += 1

        synced = looks_synced + env_synced + casting_synced
        if synced:
            logger.info(
                "REFERENCE_ASSET_CREATOR_SYNC | project=%s | character_looks=%d | environment_stills=%d | casting_candidates=%d",
                project_id,
                looks_synced,
                env_synced,
                casting_synced,
            )
        return {"synced": synced, "character_looks": looks_synced, "environment_stills": env_synced, "casting_candidates": casting_synced}

    def resolve_shot_binding(self, project_id: str, shot_id: str) -> dict:
        """Resolve one shot's authorized reference binding (read-only preview).

        Derives the scene from the stable shot identifier, resolves the
        scene's approved canonical anchors through the authoritative
        validation module (all scene characters — the strictest focus, matching
        the default submission behavior), freezes them in canonical order, and
        digests the frozen binding.

        Strictly read-only: no registry sync, no writes, no job creation, no
        provider calls. The returned binding is a server-resolved proposal — it
        becomes durable only when attached to a created render job, where the
        existing frozen-binding verifiers re-validate it before any provider
        submission. Any gap raises LookupError/ValueError fail-closed.
        """
        from app.services.reference_validation import (
            reference_binding_digest,
            reference_binding_for_requirements,
            resolve_scene_reference_requirements,
        )
        from app.utils.helpers import derive_scene_id_from_shot_id

        project_id = str(project_id or "").strip()
        shot_id = str(shot_id or "").strip()
        if not project_id or not shot_id:
            raise ValueError("project_id and shot_id are required")
        scene_id = derive_scene_id_from_shot_id(shot_id)
        requirements = resolve_scene_reference_requirements(
            project_id=project_id,
            scene_id=scene_id,
            storage=self._require_storage(),
        )
        binding = reference_binding_for_requirements(requirements)
        if not binding:
            raise ValueError("No authorized canonical references are available for this shot")
        logger.info(
            "REFERENCE_BINDING_RESOLVED | project=%s | scene=%s | shot=%s | refs=%d",
            project_id,
            scene_id,
            shot_id,
            len(binding),
        )
        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "shot_id": shot_id,
            "character_ids": list(requirements.get("character_ids") or []),
            "setting_id": requirements.get("setting_id"),
            "binding": binding,
            "binding_digest": reference_binding_digest(binding),
            "allowed_urls": list(requirements.get("allowed_urls") or []),
        }

    def verify_confirmed_binding(
        self, project_id: str, shot_id: str, expected_digest: str | None
    ) -> dict:
        """Server-authoritatively check a Desk-confirmed binding proposal.

        Independently re-resolves the currently authorized binding for the
        exact project and shot, then compares its digest against the digest
        the Desk confirmation carried. The client-supplied reference list is
        never accepted: only the digest travels with the proposal, and only
        the freshly resolved server binding is returned.

        A stale, altered, unauthorized, cross-project, or wrong-shot proposal
        fails closed with ValidationError before any job creation. Returns
        the fresh authoritative resolution for the accepted binding.
        """
        try:
            fresh = self.resolve_shot_binding(project_id, shot_id)
        except (LookupError, ValueError, ValidationError) as exc:
            raise ValidationError(
                "The confirmed reference binding cannot be verified against "
                "current canonical state; resolve the shot again and confirm "
                "before submitting.",
                stage="reference_binding_confirmation",
                metadata={
                    "project_id": str(project_id or ""),
                    "shot_id": str(shot_id or ""),
                    "failure_type": "confirmed_reference_binding_unresolvable",
                },
            ) from exc
        expected = str(expected_digest or "").strip()
        if not expected or fresh["binding_digest"] != expected:
            raise ValidationError(
                "The confirmed reference binding is stale or does not match "
                "the currently authorized references; resolve the shot again "
                "and confirm before submitting.",
                stage="reference_binding_confirmation",
                metadata={
                    "project_id": fresh["project_id"],
                    "scene_id": fresh["scene_id"],
                    "shot_id": fresh["shot_id"],
                    "failure_type": "confirmed_reference_binding_stale",
                },
            )
        logger.info(
            "REFERENCE_BINDING_CONFIRMED | project=%s | scene=%s | shot=%s | refs=%d",
            fresh["project_id"],
            fresh["scene_id"],
            fresh["shot_id"],
            len(fresh["binding"]),
        )
        return fresh


    # ── Durable shot reference-binding confirmations (R4.2) ───────────────

    def record_shot_confirmation(self, project_id: str, shot_id: str, expected_digest: str | None) -> dict:
        """Persist one explicit shot confirmation after server re-verification.

        The ONLY write path for confirmation rows: the supplied digest is
        first checked with the authoritative ``verify_confirmed_binding``
        verifier (fresh server resolution decides; nothing client-supplied is
        trusted). Only a matching current binding is persisted, scoped to its
        exact project and shot with server-resolved scene identity and
        creation metadata. Any stale, unauthorized, cross-project, or
        wrong-shot claim raises fail-closed and persists nothing.
        """
        fresh = self.verify_confirmed_binding(project_id, shot_id, expected_digest)
        stored = self._require_storage().save_shot_reference_confirmation({
            "project_id": fresh["project_id"],
            "scene_id": fresh["scene_id"],
            "shot_id": fresh["shot_id"],
            "confirmed_digest": fresh["binding_digest"],
            "status": "confirmed",
        })
        if not stored:
            raise ValidationError(
                "The confirmed reference binding could not be persisted; confirm again before submitting.",
                stage="reference_binding_confirmation",
                metadata={
                    "project_id": fresh["project_id"],
                    "shot_id": fresh["shot_id"],
                    "failure_type": "confirmed_reference_binding_persistence_failed",
                },
            )
        logger.info(
            "REFERENCE_BINDING_CONFIRMATION_RECORDED | project=%s | scene=%s | shot=%s",
            stored["project_id"],
            stored["scene_id"],
            stored["shot_id"],
        )
        return self.get_shot_confirmation(fresh["project_id"], fresh["shot_id"])

    def get_persisted_confirmation_digest(self, project_id: str, shot_id: str) -> str | None:
        """Return the raw stored digest for one project-scoped shot, if any.

        No verification is performed here: the digest is evidence of a prior
        explicit approval, never authorization. Callers must re-resolve the
        current binding and compare before any submission decision.
        """
        try:
            row = self._require_storage().get_shot_reference_confirmation(
                str(project_id or "").strip(), str(shot_id or "").strip(),
            )
        except Exception:  # noqa: BLE001 — a lookup failure reads as "no confirmation"
            return None
        if not isinstance(row, dict):
            return None
        digest = str(row.get("confirmed_digest") or "").strip()
        return digest or None

    def get_shot_confirmation(self, project_id: str, shot_id: str) -> dict:
        """Recover one shot's confirmation status against current production state.

        Restores the durable record (survives reloads and navigation) and
        revalidates it against the freshly resolved binding. Never
        establishes authorization: ``confirmed`` means the stored digest
        matches the currently authorized binding; ``stale`` means the binding
        changed since confirmation; ``missing`` means no record exists for
        this exact project and shot; ``unverifiable`` means the current
        binding cannot be resolved. A malformed stored row reads as ``stale``
        — it can never match a fresh digest, so it fails closed.
        """
        project_id = str(project_id or "").strip()
        shot_id = str(shot_id or "").strip()
        if not project_id or not shot_id:
            raise ValueError("project_id and shot_id are required")
        try:
            row = self._require_storage().get_shot_reference_confirmation(project_id, shot_id)
        except Exception:  # noqa: BLE001 — a lookup failure reads as "no confirmation"
            row = None
        if not isinstance(row, dict):
            return {
                "project_id": project_id,
                "scene_id": None,
                "shot_id": shot_id,
                "status": "missing",
                "confirmed_digest": None,
                "current_digest": None,
                "created_at": None,
                "updated_at": None,
            }
        try:
            fresh = self.resolve_shot_binding(project_id, shot_id)
        except (LookupError, ValueError, ValidationError):
            return {
                "project_id": project_id,
                "scene_id": row.get("scene_id"),
                "shot_id": shot_id,
                "status": "unverifiable",
                "confirmed_digest": str(row.get("confirmed_digest") or "") or None,
                "current_digest": None,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        stored_digest = str(row.get("confirmed_digest") or "").strip()
        status = "confirmed" if stored_digest and stored_digest == fresh["binding_digest"] else "stale"
        return {
            "project_id": project_id,
            "scene_id": row.get("scene_id") or fresh.get("scene_id"),
            "shot_id": shot_id,
            "status": status,
            "confirmed_digest": stored_digest or None,
            "current_digest": fresh["binding_digest"],
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def list_scene_confirmations(self, project_id: str, scene_id: str) -> dict:
        """Recover every durable confirmation for one project scene with live status.

        Read-only: rows are revalidated against current bindings; nothing is
        created, mutated, approved, or submitted here.
        """
        project_id = str(project_id or "").strip()
        scene_id = str(scene_id or "").strip()
        if not project_id or not scene_id:
            raise ValueError("project_id and scene_id are required")
        try:
            rows = self._require_storage().list_shot_reference_confirmations_for_scene(
                project_id, scene_id,
            )
        except Exception:  # noqa: BLE001 — a listing failure reads as "no confirmations"
            rows = []
        confirmations = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            shot_id = str(row.get("shot_id") or "").strip()
            if not shot_id:
                continue
            confirmations.append(self.get_shot_confirmation(project_id, shot_id))
        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "confirmations": confirmations,
            "count": len(confirmations),
        }


reference_asset_service = ReferenceAssetService()

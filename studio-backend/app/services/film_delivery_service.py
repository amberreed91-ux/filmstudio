from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.data.storage import get_storage
from app.models.film_delivery import AssemblyStatusResponse, AssembleFilmResponse

from app.services.project_persistence_service import project_persistence_service
from app.services.scene_assembly_service import SceneAssemblyService, scene_assembly_service
from app.services.take_selection_service import TakeSelectionService
from app.services.scene_audio_source_service import SceneAudioSourceService
from app.services.stability import StateError, ValidationError, PlaybackError, PersistenceError, log_stage_event, start_timer, elapsed_ms


class FilmDeliveryService:
    def __init__(self, storage=None, projects=None, scenes=None, backend_root=None, project_loader=None):
        self._storage = storage
        self.projects = projects or project_persistence_service
        self.project_loader = project_loader or self.projects.load
        self.scenes = scenes or scene_assembly_service
        self.root = Path(backend_root or Path(__file__).resolve().parents[2])
        self.audio_sources = getattr(self.scenes, "audio_sources", None) or SceneAudioSourceService(self.root / "outputs" / "audio")
        if hasattr(self.scenes, "backend_root"):
            self.scenes.backend_root = self.root
        if hasattr(self.scenes, "composed_root"):
            self.scenes.composed_root = self.root / "static" / "composed"
        if storage is not None and hasattr(self.scenes, "storage"):
            self.scenes.storage = storage
        if hasattr(self.scenes, "audio_sources"):
            self.scenes.audio_sources = self.audio_sources
        self._assembly_locks: dict[str, asyncio.Lock] = {}

    def _assembly_lock(self, project_id: str) -> asyncio.Lock:
        lock = self._assembly_locks.get(project_id)
        if lock is None:
            lock = asyncio.Lock()
            self._assembly_locks[project_id] = lock
        return lock

    def _validate_cut_provenance(self, project_id: str, cut: dict, project: dict) -> None:
        current = self.storage.get_film_cut_version(cut["cut_id"])
        state = self.storage.get_film_cut_state(project_id)
        if (
            not current
            or current.get("project_id") != project_id
            or current.get("cut_id") != cut.get("cut_id")
            or current.get("version_number") != cut.get("version_number")
            or current.get("scene_order") != cut.get("scene_order")
            or current.get("updated_at") != cut.get("updated_at")
            or current.get("status") != "approved"
            or not state
            or state.get("current_cut_id") != cut.get("cut_id")
            or state.get("approved_cut_id") != cut.get("cut_id")
        ):
            raise StateError("The approved Film Cut changed during delivery", stage="film_delivery_inputs", metadata={"project_id": project_id})
        project_scene_ids = {
            str(row.get("scene_id") or "").strip()
            for row in (project.get("execution_summary") or {}).get("scenes", [])
            if isinstance(row, dict) and str(row.get("scene_id") or "").strip()
        }
        if set(cut.get("scene_order") or []) != project_scene_ids:
            raise StateError("The approved Film Cut no longer covers the current project scene set", stage="film_delivery_inputs", metadata={"project_id": project_id})

    async def _assemble_with_lock(self, project_id: str) -> AssembleFilmResponse:
        async with self._assembly_lock(project_id):
            return await self._assemble(project_id)

    async def assemble(self, project_id: str) -> AssembleFilmResponse:
        return await self._assemble_with_lock(project_id)

    def _approved_cut(self, project_id: str, project: dict):
        getter = getattr(self.storage, "get_current_film_cut", None)
        if not callable(getter):
            raise StateError("Canonical Film Cut persistence is unavailable; full-film delivery is blocked", stage="film_delivery_cut")
        cut = getter(project_id)
        state = self.storage.get_film_cut_state(project_id)
        if not cut:
            raise StateError("Create and approve a Film Cut version before assembling a full-film delivery", stage="film_delivery_cut")
        if (
            cut.get("project_id") != project_id
            or cut.get("status") != "approved"
            or not state
            or state.get("current_cut_id") != cut.get("cut_id")
            or state.get("approved_cut_id") != cut.get("cut_id")
        ):
            raise StateError("Approve the current Film Cut before assembling a full-film delivery", stage="film_delivery_cut")
        order = cut.get("scene_order")
        known = {
            str(row.get("scene_id") or "").strip()
            for row in (project.get("execution_summary") or {}).get("scenes", [])
            if isinstance(row, dict) and str(row.get("scene_id") or "").strip()
        }
        if not isinstance(order, list) or not order or any(not isinstance(scene, str) or not scene.strip() for scene in order):
            raise StateError("The approved Film Cut has no ordered scenes", stage="film_delivery_cut")
        if len(order) != len(set(order)) or not set(order).issubset(known):
            raise StateError("The approved Film Cut contains duplicate or foreign scenes", stage="film_delivery_cut")
        return cut

    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    def _inputs(self, project_id):
        project = self.project_loader(project_id)
        if not project:
            raise StateError("Project not found", stage="film_delivery")
        cut = self._approved_cut(project_id, project)
        order = list(cut["scene_order"])
        if not order or any(not scene for scene in order) or len(order) != len(set(order)):
            raise StateError("Save a scene list with distinct scene IDs before assembling", stage="film_delivery")
        compositions = {row["scene_id"]: row for row in self.storage.list_scene_compositions_for_project(project_id)}
        return order, compositions

    def _ordered_scene_provenance(self, project_id: str, order: list[str], compositions: dict) -> list[dict]:
        provenance = []
        for index, scene_id in enumerate(order):
            composition = compositions.get(scene_id) or {}
            manifest = self.storage.get_delivery_manifest(project_id, scene_id)
            source_media = manifest.get("source_media") if isinstance(manifest, dict) else None
            if (
                not composition.get("composed_url")
                or not isinstance(manifest, dict)
                or manifest.get("composed_url") != composition.get("composed_url")
                or not isinstance(source_media, dict)
                or not source_media
                or not manifest.get("job_ids")
            ):
                raise StateError(
                    f"Scene {scene_id} has no complete, project-scoped delivery manifest and source-media provenance",
                    stage="film_delivery_coverage",
                    metadata={"project_id": project_id, "scene_id": scene_id},
                )
            provenance.append({
                "order_index": index,
                "scene_id": scene_id,
                "composition_id": str(composition.get("id") or ""),
                "composed_url": str(composition["composed_url"]),
                "delivery_manifest": manifest,
                "job_ids": list(manifest["job_ids"]),
                "source_media": source_media,
            })
        return provenance

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _create_package_acceptance_handoff(self, project_id: str, result: AssembleFilmResponse, output: Path, manifest: dict) -> dict:
        storage = self.storage
        film_url = result.film_url
        delivery_id = f"film_{project_id}"
        manifest_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        delivery_file_hash = self._sha256_file(output)
        metadata = {
            "film_delivery_id": delivery_id,
            "assembly_id": storage.get_film(project_id).get("id") if storage.get_film(project_id) else "",
            "source_cut_id": manifest.get("source_cut_id"),
            "source_cut_version": manifest.get("source_cut_version"),
            "delivery_manifest_hash": manifest_hash,
            "film_output_sha256": delivery_file_hash,
            "canonical_delivery_manifest": manifest,
            "delivery_kind": "canonical_film_cut",
        }
        existing = storage.list_final_short_film_packages_for_project(project_id)
        package = next((row for row in existing if row.final_output_url == film_url and row.metadata == metadata), None)
        if package is None:
            matching_reviews = [
                row for row in storage.list_reviews_for_project(project_id)
                if row.project_id == project_id and row.output_url == film_url
            ]
            latest_review = max(matching_reviews, key=lambda row: (row.created_at, row.review_id), default=None)
            review_id = latest_review.review_id if latest_review else None
            review_decision = latest_review.decision if latest_review else "pending"
            project_title = str((self.project_loader(project_id) or {}).get("title") or "Untitled film")
            from app.models import FinalShortFilmPackage
            from uuid import uuid4
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            package = FinalShortFilmPackage(
                package_id=f"film-delivery-{project_id}-{uuid4().hex[:12]}",
                project_id=project_id,
                film_title=project_title,
                final_output_url=film_url,
                final_output_path=str(output),
                review_id=review_id,
                review_decision=review_decision,
                runtime_seconds=result.total_duration_seconds,
                scene_count=result.scene_count,
                shot_count=sum(len(row["job_ids"]) for row in manifest["scene_provenance"]),
                render_job_ids=list(dict.fromkeys(job_id for row in manifest["scene_provenance"] for job_id in row["job_ids"])),
                revision_ids=[],
                has_soundtrack=False,
                package_status="ready_for_review",
                created_at=now,
                updated_at=now,
                metadata=metadata,
            )
            storage.save_final_short_film_package(package)
            from app.models.video_assets import VideoAsset
            asset = VideoAsset(
                asset_id=f"asset-film-delivery-{uuid4().hex[:12]}",
                project_id=project_id,
                source_type="generated_output",
                source_url=film_url,
                local_path=str(output),
                title=f"{package.film_title} (Film Delivery)",
                description="Canonical film delivery output registered for package-scoped Production Integrity Gate acceptance.",
                duration_seconds=result.total_duration_seconds,
                file_size_bytes=output.stat().st_size,
                status="available",
                created_at=now,
                updated_at=now,
                metadata={"package_id": package.package_id, **metadata},
            )
            storage.save_video_asset(asset)
        from app.models.production_acceptance import ProductionAcceptanceRunRequest
        from app.services.production_acceptance_service import ProductionAcceptanceService

        from app.services.short_film_review_service import ShortFilmReviewService
        review_service = ShortFilmReviewService(storage=storage)
        latest_review = review_service.get_latest_review_for_project(project_id)
        if latest_review and latest_review.output_url == film_url and package.review_id != latest_review.review_id:
            package.review_id = latest_review.review_id
            package.review_decision = latest_review.decision
            package.updated_at = datetime.now(timezone.utc).isoformat()
            storage.update_final_short_film_package(package)
        acceptance = ProductionAcceptanceService(storage=storage)
        acceptance._outputs_root = self.root / "outputs"
        report = asyncio.run(acceptance.run_acceptance(
            project_id,
            ProductionAcceptanceRunRequest(package_id=package.package_id, include_advisory_checks=False),
        ))
        guard = acceptance.evaluate_package_approval_guard(package.package_id, desired_status="approved")
        screening_output_id = ""
        if guard.allowed:
            from app.services.screening_room_service import ScreeningRoomService

            screening = ScreeningRoomService(storage=storage, backend_root=self.root)
            registered = screening._register_final_package_output(project_id, package)
            screening_output_id = registered["screening_output_id"] if registered else ""
            if not screening_output_id:
                raise PersistenceError(
                    "Accepted canonical film delivery could not be registered in Screening",
                    stage="film_delivery_handoff",
                    metadata={"project_id": project_id, "package_id": package.package_id},
                )
        return {
            "package_id": package.package_id,
            "acceptance_id": report.acceptance_id,
            "acceptance_disposition": report.disposition,
            "accepted": bool(guard.allowed),
            "reason": guard.reason,
            "screening_output_id": screening_output_id,
        }

    def _restore_previous_delivery(self, project_id: str, film: dict | None, manifest: dict | None) -> None:
        restore_delivery = getattr(self.storage, "restore_film_delivery", None)
        if callable(restore_delivery):
            restore_delivery(project_id=project_id, film=film, manifest=manifest)
        elif film is not None and manifest is not None:
            self.storage.save_film(project_id=project_id, **{
                key: film[key]
                for key in ("film_url", "scene_count", "total_duration_seconds", "has_audio")
            })
            self.storage.save_delivery_manifest(project_id, "__film__", manifest)
        else:
            clear_delivery = getattr(self.storage, "clear_film_delivery", None)
            if callable(clear_delivery):
                clear_delivery(project_id)

    def _scene_outdated(self, project_id, scene_id, composition):
        if not composition or not composition.get("composed_url"):
            return True
        manifest = self.storage.get_delivery_manifest(project_id, scene_id)
        try:
            jobs = TakeSelectionService(self.storage).resolve(project_id, scene_id)
            audio_inputs = self.audio_sources.snapshot(project_id, scene_id, [job.shot_id for _, job in jobs])
            source_media = self.scenes.source_media_snapshot(jobs)
        except (StateError, ValidationError):
            return True

        if not manifest or manifest.get("composed_url") != composition["composed_url"]:
            return True
        if not isinstance(manifest.get("source_media"), dict) or not manifest.get("job_ids"):
            return True
        expected_job_ids = manifest.get("job_ids")
        if not isinstance(expected_job_ids, list) or not expected_job_ids:
            return True
        if not jobs or any(job.project_id != project_id for _, job in jobs):
            return True
        return ([job.id for _, job in jobs] != expected_job_ids
                or audio_inputs != manifest.get("audio_inputs")
                or source_media != manifest.get("source_media"))

    def status(self, project_id: str) -> AssemblyStatusResponse:
        order, compositions = self._inputs(project_id)
        stale = [sid for sid in order if self._scene_outdated(project_id, sid, compositions.get(sid))]
        film = self.storage.get_film(project_id)
        manifest = self.storage.get_delivery_manifest(project_id, "__film__")
        scene_urls = [compositions.get(sid, {}).get("composed_url") for sid in order]
        cut = self._approved_cut(project_id, self.project_loader(project_id))
        outdated = bool(film) and (
            bool(stale)
            or not manifest
            or manifest.get("scene_ids") != order
            or manifest.get("scene_urls") != scene_urls
            or manifest.get("film_url") != film.get("film_url")
            or manifest.get("source_cut_id") != cut.get("cut_id")
            or not isinstance(manifest.get("scene_provenance"), list)
        )
        return AssemblyStatusResponse(scenes_with_compositions=sum(bool(compositions.get(sid, {}).get("composed_url")) for sid in order), scenes_total=len(order), film_assembled=bool(film) and not outdated, film_url=film.get("film_url") if film else None, has_audio=bool(film and film.get("has_audio")), film_outdated=outdated, scenes_needing_assembly=stale)

    async def _materialize(self, client, value: str, target: Path):
        parsed = urlparse(value)
        if parsed.path.startswith(("/outputs/", "/static/")) and (not parsed.netloc or parsed.hostname in {"localhost", "127.0.0.1"}):
            source = (self.root / parsed.path.lstrip("/")).resolve()
            if not source.is_relative_to(self.root.resolve()) or not source.is_file():
                raise PlaybackError("A saved scene video is missing", stage="film_delivery_media")
            await asyncio.to_thread(shutil.copy2, source, target)
        elif not parsed.scheme and Path(value).is_absolute():
            source = Path(value).resolve()
            if not source.is_relative_to(self.root.resolve()) or not source.is_file():
                raise PlaybackError("Scene video is outside the project media store", stage="film_delivery_media")
            await asyncio.to_thread(shutil.copy2, source, target)
        elif parsed.scheme in {"https", "http"}:
            response = await client.get(value, timeout=120)
            response.raise_for_status()
            target.write_bytes(response.content)
        else:
            raise PlaybackError("Scene has an unsupported video location", stage="film_delivery_media")

    async def _assemble(self, project_id: str) -> AssembleFilmResponse:
        timer = start_timer()
        order, compositions = self._inputs(project_id)
        project = self.project_loader(project_id)
        cut = self._approved_cut(project_id, project)
        self._validate_cut_provenance(project_id, cut, project)
        for sid in order:
            if self._scene_outdated(project_id, sid, compositions.get(sid)):
                raise StateError(
                    f"Scene {sid} output is missing or stale; assemble and verify that scene before full-film delivery",
                    stage="film_delivery_coverage",
                    metadata={"project_id": project_id, "scene_id": sid},
                )
        scene_urls = [compositions[sid]["composed_url"] for sid in order]
        scene_provenance = self._ordered_scene_provenance(project_id, order, compositions)
        previous_film = self.storage.get_film(project_id)
        previous_manifest = self.storage.get_delivery_manifest(project_id, "__film__")
        delivery_saved = False
        directory = self.root / "outputs" / "film-deliveries" / project_id
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / f"film_{uuid4().hex[:12]}.mp4"
        try:
            with tempfile.TemporaryDirectory(prefix="film_delivery_") as temp:
                work = Path(temp)
                normalized = []
                expected_duration = 0.0
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    for index, url in enumerate(scene_urls):
                        source = work / f"scene_{index:03d}.mp4"
                        await self._materialize(client, url, source)
                        seconds = await asyncio.to_thread(SceneAssemblyService._probe_duration, source)
                        streams = await asyncio.to_thread(SceneAssemblyService._probe_streams, source)
                        video = next((row for row in streams if row.get("codec_type") == "video"), None)
                        if not video or not seconds or seconds <= 0:
                            raise PlaybackError("A scene has no playable video", stage="film_delivery_media", metadata={"scene_id": order[index]})
                        if index == 0:
                            width, height = int(video["width"]), int(video["height"])
                            width, height = width + width % 2, height + height % 2
                        expected_duration += seconds
                        target = work / f"normalized_{index:03d}.mp4"
                        command = ["ffmpeg", "-y", "-i", str(source)]
                        audio = any(row.get("codec_type") == "audio" for row in streams)
                        if not audio:
                            command += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                        command += ["-map", "0:v:0", "-map", "0:a:0" if audio else "1:a:0", "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24", "-af", "apad", "-t", str(seconds), "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(target)]
                        await asyncio.to_thread(SceneAssemblyService._run_ffmpeg, command, "film_delivery_normalize")
                        normalized.append(target)
                candidate = work / "film.mp4"
                await asyncio.to_thread(self.scenes._concat, normalized, candidate)
                duration = await asyncio.to_thread(SceneAssemblyService._probe_duration, candidate)
                if not duration or abs(duration - expected_duration) > max(0.3, len(order) * 0.1):
                    raise PlaybackError("The export duration does not match the complete scene list", stage="film_delivery_verify")
                await asyncio.to_thread(SceneAssemblyService._run_ffmpeg, ["ffmpeg", "-v", "error", "-i", str(candidate), "-f", "null", "-"], "film_delivery_decode")
                shutil.copy2(candidate, output)
            film_url = f"/outputs/film-deliveries/{project_id}/{output.name}"
            output_digest = await asyncio.to_thread(self._sha256_file, output)
            result = AssembleFilmResponse(film_url=film_url, scene_count=len(order), total_duration_seconds=duration, has_audio=SceneAssemblyService._has_audio(output), acceptance_status="unverified")
            current_order, current_compositions = self._inputs(project_id)
            current_project = self.project_loader(project_id)
            source_cut = self._approved_cut(project_id, current_project)
            self._validate_cut_provenance(project_id, source_cut, current_project)
            current_scene_provenance = self._ordered_scene_provenance(project_id, current_order, current_compositions)
            if (
                current_order != order
                or source_cut.get("cut_id") != cut.get("cut_id")
                or source_cut.get("updated_at") != cut.get("updated_at")
                or [current_compositions.get(sid, {}).get("composed_url") for sid in order] != scene_urls
                or current_scene_provenance != scene_provenance
                or any(self._scene_outdated(project_id, sid, current_compositions.get(sid)) for sid in order)
            ):
                raise StateError("The cut or recordings changed during export. Rebuild to deliver the current version.", stage="film_delivery_inputs", metadata={"project_id": project_id})
            delivery_manifest = {
                "film_url": film_url,
                "film_output_sha256": output_digest,
                "scene_ids": order,
                "scene_urls": scene_urls,
                "source_cut_id": cut.get("cut_id"),
                "source_cut_version": cut.get("version_number"),
                "source_cut_updated_at": cut.get("updated_at"),
                "scene_provenance": scene_provenance,
            }
            film_record = self.storage.save_film(
                project_id=project_id,
                film_url=result.film_url,
                scene_count=result.scene_count,
                total_duration_seconds=result.total_duration_seconds,
                has_audio=result.has_audio,
            )
            self.storage.save_delivery_manifest(project_id, "__film__", delivery_manifest)
            delivery_saved = True
            try:
                handoff = await asyncio.to_thread(self._create_package_acceptance_handoff, project_id, result, output, delivery_manifest)
            except Exception:
                self._restore_previous_delivery(project_id, previous_film, previous_manifest)
                delivery_saved = False
                raise
            result = result.model_copy(update={
                "acceptance_status": handoff["acceptance_disposition"],
                "acceptance_report_id": handoff["acceptance_id"],
                "package_id": handoff["package_id"],
                "screening_output_id": handoff["screening_output_id"],
            })
            if not handoff["accepted"]:
                self._restore_previous_delivery(project_id, previous_film, previous_manifest)
                delivery_saved = False
        except (StateError, PlaybackError, PersistenceError):
            if delivery_saved:
                self._restore_previous_delivery(project_id, previous_film, previous_manifest)
            raise
        except Exception as exc:
            raise PlaybackError("Film delivery failed; the previous export is preserved", stage="film_delivery", metadata={"cause": type(exc).__name__}) from exc
        log_stage_event(project_id=project_id, job_id=None, provider="ffmpeg", stage="film_delivery", duration_ms=elapsed_ms(timer), extra={"scene_count": len(order), "film_url": film_url})
        return result

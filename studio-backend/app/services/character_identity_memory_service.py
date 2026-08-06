from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from app.models.character_profile import (
    CanonicalCharacterIdentityRecord,
    CharacterAppearanceTraits,
    CharacterAppearanceVersion,
    CharacterIdentityCore,
    CharacterProfile,
    CharacterVisualReference,
)
from app.services.stability import PersistenceError


class CharacterIdentityMemoryService:
    _FIXED_CONFLICT_FIELDS = {
        "facial_identity": "facial identity",
        "body_and_silhouette": "body and silhouette",
        "skin_tone": "skin tone",
        "hair_color": "hair color",
        "age_presentation": "age presentation",
    }

    def _json_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _json_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return list(value)
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except Exception:
                return []
            return parsed if isinstance(parsed, list) else []
        return []

    def _split_traits(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if not isinstance(value, str) or not value.strip():
            return []
        separators = [";", "\n"]
        text = value
        for sep in separators:
            text = text.replace(sep, ",")
        return [part.strip(" .") for part in text.split(",") if part.strip(" .")]

    def _reliability(self, value: Any, default: str = "medium") -> str:
        clean = str(value or default).strip().lower()
        return clean if clean in {"low", "medium", "high"} else default

    def _reference_role(self, value: Any) -> str:
        clean = str(value or "general").strip().lower()
        return clean if clean in {"face", "full_body", "wardrobe", "temporary_state", "general"} else "general"

    def _supports_reference_images(self, provider_capability: Any) -> bool:
        if isinstance(provider_capability, dict):
            for key in (
                "supports_reference_images",
                "supports_image_references",
                "supports_init_image",
                "supports_image_to_video",
                "supports_character_reference",
            ):
                if provider_capability.get(key) is True:
                    return True
            provider = str(provider_capability.get("provider") or "").strip().lower()
        else:
            provider = str(provider_capability or "").strip().lower()
        return provider in {
            "text_and_reference",
            "reference_images_and_text",
            "runway",
            "runwayml",
            "happyhorse",
            "happyhorse-r2v",
            "qwen-image-max",
        }

    def _provider_label(self, provider_capability: Any) -> str:
        if isinstance(provider_capability, dict):
            return str(provider_capability.get("provider") or "unknown").strip() or "unknown"
        return str(provider_capability or "unknown").strip() or "unknown"

    def _merge_appearance(
        self,
        base: CharacterAppearanceTraits,
        overlay: CharacterAppearanceTraits,
    ) -> CharacterAppearanceTraits:
        return CharacterAppearanceTraits(
            wardrobe=overlay.wardrobe or base.wardrobe,
            accessories=overlay.accessories or base.accessories,
            persistent_props=overlay.persistent_props or base.persistent_props,
            injuries=[*base.injuries, *[item for item in overlay.injuries if item not in base.injuries]],
            dirt_blood_or_wear=[
                *base.dirt_blood_or_wear,
                *[item for item in overlay.dirt_blood_or_wear if item not in base.dirt_blood_or_wear],
            ],
            emotional_state=overlay.emotional_state or base.emotional_state,
            notes=[*base.notes, *[item for item in overlay.notes if item not in base.notes]],
        )

    def _continuity_key_active(
        self,
        *,
        scene_id: str,
        shot_id: str,
        starts_scene: str,
        starts_shot: str,
        clears_scene: str,
        clears_shot: str,
    ) -> bool:
        current = (scene_id or "", shot_id or "")
        starts = (starts_scene or "", starts_shot or "")
        clears = (clears_scene or "", clears_shot or "")
        if any(starts) and current < starts:
            return False
        if any(clears) and current >= clears:
            return False
        return True

    def resolve_active_appearance(
        self,
        record: CanonicalCharacterIdentityRecord,
        *,
        scene_id: str = "",
        shot_id: str = "",
    ) -> CharacterAppearanceTraits:
        appearance = record.default_appearance
        if scene_id and scene_id in record.scene_specific_appearance:
            appearance = self._merge_appearance(appearance, record.scene_specific_appearance[scene_id])
        for change in record.temporary_continuity_changes:
            if self._continuity_key_active(
                scene_id=scene_id,
                shot_id=shot_id,
                starts_scene=change.applies_from_scene_id or "",
                starts_shot=change.applies_from_shot_id or change.source_shot_id,
                clears_scene=change.clears_at_scene_id,
                clears_shot=change.clears_at_shot_id,
            ):
                appearance = self._merge_appearance(appearance, change.appearance)
        if shot_id and shot_id in record.shot_specific_state:
            appearance = self._merge_appearance(appearance, record.shot_specific_state[shot_id])
        return appearance

    def _legacy_core(self, row: dict[str, Any]) -> CharacterIdentityCore:
        core = self._json_dict(row.get("identity_core_json") or row.get("identity_core"))
        facial_identity = (
            core.get("facial_identity")
            or row.get("facial_identity")
            or row.get("appearance_core")
            or row.get("look")
            or ""
        )
        silhouette = (
            core.get("body_and_silhouette")
            or row.get("silhouette")
            or row.get("appearance_notes")
            or ""
        )
        return CharacterIdentityCore(
            face_reference=str(core.get("face_reference") or "").strip(),
            facial_identity=str(facial_identity or "").strip(),
            body_and_silhouette=str(silhouette or "").strip(),
            skin_tone=str(core.get("skin_tone") or "").strip(),
            hair_style=str(core.get("hair_style") or "").strip(),
            hair_length=str(core.get("hair_length") or "").strip(),
            hair_color=str(core.get("hair_color") or "").strip(),
            age_presentation=str(core.get("age_presentation") or row.get("age") or "").strip(),
        )

    def _legacy_appearance(self, row: dict[str, Any]) -> CharacterAppearanceTraits:
        data = self._json_dict(row.get("default_appearance_json") or row.get("default_appearance"))
        wardrobe = data.get("wardrobe") or row.get("wardrobe") or row.get("visual_prompt_summary") or ""
        return CharacterAppearanceTraits(
            wardrobe=self._split_traits(wardrobe),
            accessories=self._split_traits(data.get("accessories")),
            persistent_props=self._split_traits(data.get("persistent_props")),
            injuries=self._split_traits(data.get("injuries")),
            dirt_blood_or_wear=self._split_traits(data.get("dirt_blood_or_wear")),
            emotional_state=str(data.get("emotional_state") or row.get("energy") or "").strip(),
            notes=self._split_traits(data.get("notes")),
        )

    def build_canonical_record(
        self,
        character: Any,
        *,
        reference_locks: Any = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
    ) -> CanonicalCharacterIdentityRecord | None:
        if isinstance(character, CanonicalCharacterIdentityRecord):
            return character
        if isinstance(character, CharacterProfile):
            core = CharacterIdentityCore(
                facial_identity=character.facial_identity,
                body_and_silhouette=character.silhouette,
            )
            default = CharacterAppearanceTraits(
                wardrobe=list(character.wardrobe),
                emotional_state=character.emotional_baseline,
                notes=list(character.appearance_traits),
            )
            refs = [
                CharacterVisualReference(
                    ref_id=f"{character.character_id}:legacy:{index}",
                    image_url=image_url,
                    source_status="approved",
                    reliability="medium",
                )
                for index, image_url in enumerate(character.visual_references)
            ]
            return CanonicalCharacterIdentityRecord(
                character_id=character.character_id,
                name=character.name,
                identity_core=core,
                default_appearance=default,
                approved_visual_references=refs,
                reliability="medium" if refs else "low",
                needs_human_review=not bool(core.facial_identity and core.body_and_silhouette),
            )
        if not isinstance(character, dict):
            return None

        character_id = str(character.get("id") or character.get("character_id") or "").strip()
        if not character_id:
            return None
        state = self._json_dict(character.get("continuity_state_json") or character.get("continuity_state"))
        record = CanonicalCharacterIdentityRecord(
            character_id=character_id,
            name=str(character.get("name") or "").strip(),
            identity_core=self._legacy_core(character),
            default_appearance=self._legacy_appearance(character),
            scene_specific_appearance={
                str(key): CharacterAppearanceTraits(**value)
                for key, value in self._json_dict(state.get("scene_specific_appearance")).items()
                if isinstance(value, dict)
            },
            shot_specific_state={
                str(key): CharacterAppearanceTraits(**value)
                for key, value in self._json_dict(state.get("shot_specific_state")).items()
                if isinstance(value, dict)
            },
            temporary_continuity_changes=[
                CharacterAppearanceVersion(**item)
                for item in self._json_list(state.get("temporary_continuity_changes"))
                if isinstance(item, dict)
            ],
            appearance_version_history=[
                CharacterAppearanceVersion(**item)
                for item in self._json_list(character.get("appearance_version_history_json") or state.get("appearance_version_history"))
                if isinstance(item, dict)
            ],
            reliability=self._reliability(state.get("reliability")),  # type: ignore[arg-type]
            trace_sources=self._json_list(state.get("trace_sources")),
        )
        self._attach_reference_locks(record, reference_locks)
        record.conflict_warnings = self.detect_record_conflicts(record)
        record.needs_human_review = self.needs_human_review(record)
        return record

    def _attach_reference_locks(
        self,
        record: CanonicalCharacterIdentityRecord,
        reference_locks: Any,
    ) -> None:
        for raw in reference_locks if isinstance(reference_locks, list) else []:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("character_id") or "").strip() != record.character_id:
                continue
            status = str(raw.get("lock_status") or "locked").strip().lower()
            source_status = {
                "locked": "approved",
                "provisional": "provisional",
                "superseded": "superseded",
                "disabled": "rejected",
            }.get(status, "provisional")
            reliability = "high" if source_status == "approved" else "medium" if source_status == "provisional" else "low"
            ref = CharacterVisualReference(
                ref_id=str(raw.get("lock_id") or f"charlock:{record.character_id}"),
                image_url=str(raw.get("image_url") or "").strip(),
                source_shot_id=str(raw.get("source_shot_id") or "").strip(),
                source_job_id=str(raw.get("source_job_id") or "").strip(),
                source_status=source_status,  # type: ignore[arg-type]
                capture_method=str(raw.get("capture_method") or "").strip(),
                reliability=self._reliability(reliability),  # type: ignore[arg-type]
                role=self._reference_role(raw.get("reference_role")),  # type: ignore[arg-type]
            )
            if source_status in {"approved", "provisional"}:
                record.approved_visual_references.append(ref)
            else:
                record.rejected_visual_references.append(ref)

    def detect_record_conflicts(self, record: CanonicalCharacterIdentityRecord) -> list[str]:
        warnings: list[str] = []
        core = record.identity_core
        for field_name, label in self._FIXED_CONFLICT_FIELDS.items():
            value = str(getattr(core, field_name, "") or "").strip()
            if " vs " in value.lower() or "conflict:" in value.lower():
                warnings.append(f"{record.name or record.character_id}: conflicting {label} evidence needs review.")
        approved_urls = {ref.image_url for ref in record.approved_visual_references if ref.image_url}
        rejected_urls = {ref.image_url for ref in record.rejected_visual_references if ref.image_url}
        if approved_urls & rejected_urls:
            warnings.append(f"{record.name or record.character_id}: the same visual reference is both approved and rejected.")
        if len({ref.image_url for ref in record.approved_visual_references if ref.role in {'face', 'full_body'}}) > 1:
            warnings.append(f"{record.name or record.character_id}: multiple approved identity references may conflict.")
        return warnings

    def needs_human_review(self, record: CanonicalCharacterIdentityRecord) -> bool:
        core = record.identity_core
        if record.conflict_warnings:
            return True
        if not record.approved_visual_references and not core.face_reference:
            return True
        if not core.facial_identity or not core.body_and_silhouette:
            return True
        return record.reliability == "low"

    def build_records_from_storage(
        self,
        *,
        project_id: str,
        storage: Any,
        character_ids: list[str] | None = None,
    ) -> list[CanonicalCharacterIdentityRecord]:
        try:
            characters = storage.get_characters(project_id)
        except Exception as exc:
            raise PersistenceError(
                "Character identity memory lookup failed",
                stage="character_identity_memory",
                metadata={"cause": type(exc).__name__},
            ) from exc
        clean_ids = {str(item).strip() for item in (character_ids or []) if str(item).strip()}
        try:
            locks = storage.list_character_reference_locks(project_id, list(clean_ids) if clean_ids else None, None)
        except TypeError:
            locks = []
            for status in ("locked", "provisional", "superseded", "disabled"):
                try:
                    locks.extend(storage.list_character_reference_locks(project_id, list(clean_ids) if clean_ids else None, status))
                except Exception as exc:
                    raise PersistenceError(
                        "Character reference lock lookup failed",
                        stage="character_identity_memory",
                        metadata={"cause": type(exc).__name__},
                    ) from exc
        except Exception as exc:
            raise PersistenceError(
                "Character reference lock lookup failed",
                stage="character_identity_memory",
                metadata={"cause": type(exc).__name__},
            ) from exc
        records: list[CanonicalCharacterIdentityRecord] = []
        for character in characters:
            cid = str(character.get("id") or "").strip()
            if clean_ids and cid not in clean_ids:
                continue
            record = self.build_canonical_record(character, reference_locks=locks)
            if record:
                records.append(record)
        return records

    def build_appearance_version_from_job(
        self,
        *,
        character_id: str,
        source_shot_id: str,
        source_job_id: str,
        appearance: CharacterAppearanceTraits | None = None,
        reliability: str = "high",
        change_summary: str = "approved render reference",
    ) -> CharacterAppearanceVersion:
        return CharacterAppearanceVersion(
            version_id=f"appearance_{character_id}_{source_job_id}",
            source="render",
            source_shot_id=source_shot_id,
            source_job_id=source_job_id,
            change_summary=change_summary,
            appearance=appearance or CharacterAppearanceTraits(),
            reliability=self._reliability(reliability),  # type: ignore[arg-type]
            created_at=datetime.now().isoformat(),
        )

    def _as_profiles(self, profiles: Any) -> List[CharacterProfile]:
        out: List[CharacterProfile] = []
        if not isinstance(profiles, list):
            return out
        for row in profiles:
            if isinstance(row, CharacterProfile):
                out.append(row)
            elif isinstance(row, dict):
                try:
                    out.append(CharacterProfile(**row))
                except Exception:
                    continue
        return out

    def persist_reference_images(self, character_profiles: Any) -> Dict[str, List[str]]:
        refs: Dict[str, List[str]] = {}
        for profile in self._as_profiles(character_profiles):
            if profile.visual_references:
                refs[profile.character_id] = list(profile.visual_references)
        return refs

    def build_provider_identity_context(self, character_profiles: Any, scene_data: Any) -> Dict[str, Any]:
        profiles = self._as_profiles(character_profiles)
        scene = scene_data if isinstance(scene_data, dict) else {}
        scene_names = {
            str(name).strip().lower()
            for name in (scene.get("character_appearances") or scene.get("characters") or [])
            if str(name).strip()
        } if isinstance(scene.get("character_appearances") or scene.get("characters"), list) else set()
        lines: List[str] = []
        for profile in profiles:
            if scene_names and profile.name.lower() not in scene_names and profile.character_id.lower() not in scene_names:
                continue
            parts = [profile.name]
            if profile.facial_identity:
                parts.append(f"facial identity: {profile.facial_identity}")
            if profile.silhouette:
                parts.append(f"silhouette: {profile.silhouette}")
            if profile.movement_style:
                parts.append(f"movement: {profile.movement_style}")
            if profile.wardrobe:
                parts.append(f"wardrobe: {', '.join(profile.wardrobe[:2])}")
            lines.append(" | ".join(parts))
        return {
            "advisory_only": True,
            "identity_lines": lines,
            "reference_images": self.persist_reference_images(profiles),
        }

    def build_provider_context_from_records(
        self,
        records: Any,
        scene_data: Any = None,
        shot_id: str | None = None,
        provider_capability: Any = "text_and_reference",
    ) -> Dict[str, Any]:
        scene = scene_data if isinstance(scene_data, dict) else {}
        scene_id = str(scene.get("scene_id") or "").strip()
        scene_names = {
            str(name).strip().lower()
            for name in (scene.get("character_appearances") or scene.get("characters") or [])
            if str(name).strip()
        } if isinstance(scene.get("character_appearances") or scene.get("characters"), list) else set()
        canonical: list[CanonicalCharacterIdentityRecord] = []
        for raw in records if isinstance(records, list) else []:
            record = self.build_canonical_record(raw)
            if record:
                canonical.append(record)

        lines: list[str] = []
        references: dict[str, list[dict[str, Any]]] = {}
        warnings: list[str] = []
        review_required = False
        supports_reference_images = self._supports_reference_images(provider_capability)
        for record in canonical:
            if scene_names and record.name.lower() not in scene_names and record.character_id.lower() not in scene_names:
                continue
            appearance = self.resolve_active_appearance(
                record,
                scene_id=scene_id,
                shot_id=shot_id or "",
            )
            core = record.identity_core
            fixed = [
                part for part in [
                    f"face: {core.facial_identity}" if core.facial_identity else "",
                    f"silhouette: {core.body_and_silhouette}" if core.body_and_silhouette else "",
                    f"skin tone: {core.skin_tone}" if core.skin_tone else "",
                    f"hair: {' '.join(p for p in [core.hair_style, core.hair_length, core.hair_color] if p)}" if any([core.hair_style, core.hair_length, core.hair_color]) else "",
                    f"age presentation: {core.age_presentation}" if core.age_presentation else "",
                ] if part
            ]
            variable = [
                part for part in [
                    f"wardrobe: {', '.join(appearance.wardrobe[:3])}" if appearance.wardrobe else "",
                    f"accessories: {', '.join(appearance.accessories[:3])}" if appearance.accessories else "",
                    f"props: {', '.join(appearance.persistent_props[:2])}" if appearance.persistent_props else "",
                    f"temporary marks: {', '.join([*appearance.injuries, *appearance.dirt_blood_or_wear][:3])}" if appearance.injuries or appearance.dirt_blood_or_wear else "",
                    f"emotional state: {appearance.emotional_state}" if appearance.emotional_state else "",
                ] if part
            ]
            line = f"{record.name or record.character_id} fixed identity: {'; '.join(fixed) or 'not yet verified'}"
            if variable:
                line += f" | current appearance: {'; '.join(variable)}"
            if record.needs_human_review:
                line += " | human review needed before treating ambiguous evidence as canonical"
                review_required = True
            lines.append(line)
            references[record.character_id] = [
                ref.model_dump(mode="json") for ref in record.approved_visual_references
            ]
            warnings.extend(record.conflict_warnings)
        active_references = references if supports_reference_images else {}
        strategy = "reference_images_and_text" if supports_reference_images and any(references.values()) else "text_only"
        return {
            "advisory_only": True,
            "provider_capability": provider_capability,
            "provider": self._provider_label(provider_capability),
            "constraint_injection": {
                "strategy": strategy,
                "supports_reference_images": supports_reference_images,
                "text_constraints": lines,
                "reference_assets": active_references,
                "reference_policy": (
                    "Attach approved visual references and repeat identity text constraints."
                    if strategy == "reference_images_and_text"
                    else "Provider cannot accept visual references; inject fixed and changeable traits as text constraints."
                ),
            },
            "identity_lines": lines,
            "reference_images": active_references,
            "conflict_warnings": warnings,
            "human_review_required": review_required or bool(warnings),
        }

    def build_emotional_memory_continuity(self, character_profiles: Any, scene_data: Any) -> List[str]:
        profiles = self._as_profiles(character_profiles)
        scene = scene_data if isinstance(scene_data, dict) else {}
        scene_emotion = str(scene.get("emotional_target") or "").strip().lower()
        notes: List[str] = []
        for profile in profiles:
            baseline = profile.emotional_baseline.strip().lower()
            behavior = profile.emotional_behavior.strip().lower()
            if baseline:
                notes.append(f"{profile.name}: emotional baseline {baseline}.")
            if behavior:
                notes.append(f"{profile.name}: behavior pattern {behavior}.")
            if scene_emotion and baseline and scene_emotion != baseline:
                notes.append(f"{profile.name}: carry continuity from {baseline} into {scene_emotion}.")
        return notes

    def detect_identity_drift_warnings(self, character_profiles: Any, scene_data: Any) -> List[str]:
        profiles = self._as_profiles(character_profiles)
        scene = scene_data if isinstance(scene_data, dict) else {}
        drift: List[str] = []
        scene_tone = str(scene.get("emotional_target") or "").strip().lower()
        for profile in profiles:
            if not profile.name:
                continue
            if not profile.facial_identity:
                drift.append(f"{profile.name}: facial identity not set; drift risk across shots.")
            if not profile.silhouette:
                drift.append(f"{profile.name}: silhouette not set; framing drift risk.")
            if not profile.movement_style:
                drift.append(f"{profile.name}: movement style not set; motion drift risk.")
            if scene_tone and profile.emotional_baseline and scene_tone != profile.emotional_baseline.strip().lower():
                drift.append(
                    f"{profile.name}: emotional drift warning ({profile.emotional_baseline} -> {scene_tone})."
                )
        return drift


character_identity_memory_service = CharacterIdentityMemoryService()

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Any

from app.data import get_storage
from app.models.casting_intelligence import (
    AuditionEvaluation,
    AuditionPackage,
    AuditionPackageRequest,
    AuditionSubmission,
    AuditionSubmissionRequest,
    CastingDecision,
    CastingDecisionMemoryProjection,
    CastingDecisionRequest,
    CastingDecisionUpdateRequest,
    CastingDepartmentSignal,
    CastingEvidenceRef,
    CastingProjection,
    CastingReadinessReport,
    CastingReadinessRequest,
    CastingRecommendation,
    CastingRecommendationRequest,
    CastingRoleBreakdown,
    CastingSaveDecisionRequest,
    CastingSpineRef,
    HybridCastingAssignment,
    RoleBreakdownBuildRequest,
    RoleBreakdownBuildResponse,
    TalentConsentRecord,
    TalentProfile,
    TalentProfileRequest,
    TalentProfileUpdateRequest,
)
from app.services.project_store import project_store
from app.services.stability import StateError, ValidationError, elapsed_ms, log_stage_event, start_timer


_FORBIDDEN_PUBLIC_PATTERNS = [
    re.compile(r"\bscore\b", re.IGNORECASE),
    re.compile(r"\brating\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s*/\s*(?:10|100)\b"),
    re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
    re.compile(r"\bobjectively\b", re.IGNORECASE),
    re.compile(r"\bgreat job\b", re.IGNORECASE),
    re.compile(r"\blooks good overall\b", re.IGNORECASE),
]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _clean(value: Any) -> str:
    return str(value or "").strip()


class CastingIntelligenceService:
    """Canonical advisory casting and talent-management department."""

    def __init__(
        self,
        *,
        storage: Any = None,
        project_store_service: Any = project_store,
        performance_intelligence_service: Any = None,
        performance_audio_intelligence_service: Any = None,
        memory_service: Any = None,
        spine_service: Any = None,
    ):
        self._storage = storage
        self.project_store = project_store_service
        self._performance_intelligence_service = performance_intelligence_service
        self._performance_audio_intelligence_service = performance_audio_intelligence_service
        self._memory_service = memory_service
        self._spine_service = spine_service

    @property
    def storage(self):
        return self._storage or get_storage("sqlite")

    @property
    def performance_intelligence_service(self):
        if self._performance_intelligence_service is None:
            try:
                from app.services.performance_intelligence_service import performance_intelligence_service

                performance_intelligence_service._storage = self.storage
                self._performance_intelligence_service = performance_intelligence_service
            except Exception:
                self._performance_intelligence_service = None
        return self._performance_intelligence_service

    @property
    def memory_service(self):
        if self._memory_service is None:
            try:
                from app.services.memory import memory_service

                memory_service.storage = self.storage
                self._memory_service = memory_service
            except Exception:
                self._memory_service = None
        return self._memory_service

    @property
    def spine_service(self):
        if self._spine_service is None:
            try:
                from app.services.spine_service import SpineService

                self._spine_service = SpineService()
            except Exception:
                self._spine_service = None
        return self._spine_service

    def _require(self, value: Any, field: str) -> str:
        clean = _clean(value)
        if not clean:
            raise ValidationError(f"{field} required", stage="casting_validation")
        return clean

    def _character_id(self, name: str) -> str:
        clean = re.sub(r"[^a-z0-9]+", "_", _clean(name).lower()).strip("_")
        return clean or "character"

    def _signature(self, payload: Any) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _assert_public_language(self, payload: Any) -> None:
        text = json.dumps(payload, ensure_ascii=True, default=str)
        violations = [pattern.pattern for pattern in _FORBIDDEN_PUBLIC_PATTERNS if pattern.search(text)]
        if violations:
            raise StateError(
                "Casting output contained forbidden public precision language",
                stage="casting_public_language",
                metadata={"violations": violations},
            )

    def _project(self, project_id: str) -> dict[str, Any]:
        project_id = self._require(project_id, "project_id")
        project = self.project_store.get_project(project_id)
        if not project:
            raise ValidationError(f"Project {project_id} not found", stage="casting_project")
        return project

    def _all_scenes(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        scenes = project.get("scenes") if isinstance(project.get("scenes"), list) else []
        if not scenes:
            summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
            scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        return [scene for scene in scenes if isinstance(scene, dict)]

    def _scene_id(self, scene: dict[str, Any], index: int) -> str:
        return (
            _clean(scene.get("scene_id"))
            or _clean(scene.get("sceneId"))
            or _clean(scene.get("id"))
            or f"scene_{index + 1:03d}"
        )

    def _scene_text(self, scene: dict[str, Any]) -> str:
        parts = [
            scene.get("title"),
            scene.get("scene_title"),
            scene.get("description"),
            scene.get("scene_description"),
            scene.get("action"),
            scene.get("dialogue"),
            scene.get("emotional_target"),
            scene.get("unresolved_tension"),
        ]
        return " ".join(_clean(part) for part in parts if _clean(part))

    def _scene_characters(self, scene: dict[str, Any]) -> list[str]:
        raw = scene.get("scene_characters") or scene.get("characters") or scene.get("character_names") or []
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.replace(";", ",").split(",")]
        if not isinstance(raw, list):
            return []
        names: list[str] = []
        for item in raw:
            value = item.get("name") if isinstance(item, dict) else item
            clean = _clean(value)
            if clean and clean not in names:
                names.append(clean)
        return names

    def _character_index(self, project: dict[str, Any]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        raw = project.get("characters") if isinstance(project.get("characters"), list) else []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = _clean(item.get("name") or item.get("character_name") or item.get("id") or item.get("character_id"))
            cid = _clean(item.get("character_id") or item.get("id")) or self._character_id(name)
            if cid:
                out[cid] = item
        return out

    def _evidence(
        self,
        *,
        source_type: str,
        source_id: str,
        relevance: str,
        excerpt: str = "",
        field_path: str = "",
        scene_id: str | None = None,
        character_id: str | None = None,
        role_id: str | None = None,
        talent_id: str | None = None,
        audition_id: str | None = None,
        reliability_label: str = "emerging",
    ) -> CastingEvidenceRef:
        return CastingEvidenceRef(
            evidence_id=_new_id("cast-ev"),
            source_type=source_type,  # type: ignore[arg-type]
            source_id=source_id,
            field_path=field_path,
            scene_id=scene_id,
            character_id=character_id,
            role_id=role_id,
            talent_id=talent_id,
            audition_id=audition_id,
            excerpt=excerpt[:280],
            relevance=relevance,
            reliability_label=reliability_label,  # type: ignore[arg-type]
        )

    def _spine_refs(self, project_id: str) -> list[CastingSpineRef]:
        if self.spine_service is None:
            return []
        try:
            spine = self.spine_service.get_spine(project_id)
        except Exception:
            return []
        if not spine:
            return []
        refs: list[CastingSpineRef] = []
        restraint_rules = getattr(spine, "restraint_rules", []) or []
        for index, rule in enumerate(restraint_rules[:3]):
            refs.append(
                CastingSpineRef(
                    constraint_id=f"spine-restraint-{index + 1}",
                    field_name="restraint_rules",
                    summary=_clean(rule),
                    applied=True,
                    risk_if_ignored="Casting may make the role's emotional turn too explicit for the current creative spine.",
                )
            )
        frozen_fields = getattr(spine, "frozen_fields", []) or []
        for index, field in enumerate(frozen_fields[:3]):
            refs.append(
                CastingSpineRef(
                    constraint_id=f"spine-frozen-{index + 1}",
                    field_name="frozen_fields",
                    summary=_clean(field),
                    applied=True,
                    risk_if_ignored="Casting should not contradict a frozen creative-spine identity constraint.",
                )
            )
        return refs

    def build_role_breakdowns(self, project_id: str, request: RoleBreakdownBuildRequest | None = None) -> RoleBreakdownBuildResponse:
        started = start_timer()
        request = request or RoleBreakdownBuildRequest()
        project = self._project(project_id)
        scenes = self._all_scenes(project)
        character_rows = self._character_index(project)
        spine_refs = self._spine_refs(project_id)
        by_character: dict[str, dict[str, Any]] = {}
        for index, scene in enumerate(scenes):
            scene_id = self._scene_id(scene, index)
            text = self._scene_text(scene)
            for name in self._scene_characters(scene):
                character_id = self._character_id(name)
                entry = by_character.setdefault(
                    character_id,
                    {"name": name, "scene_ids": [], "texts": [], "evidence": []},
                )
                entry["scene_ids"].append(scene_id)
                if text:
                    entry["texts"].append(text)
                entry["evidence"].append(
                    self._evidence(
                        source_type="script_scene",
                        source_id=scene_id,
                        field_path="scene.characters",
                        scene_id=scene_id,
                        character_id=character_id,
                        excerpt=text or name,
                        relevance="Scene presence establishes role coverage and audition demands.",
                        reliability_label="supported",
                    )
                )
        for character_id, row in character_rows.items():
            name = _clean(row.get("name") or row.get("character_name") or character_id)
            by_character.setdefault(character_id, {"name": name, "scene_ids": [], "texts": [], "evidence": []})

        roles: list[CastingRoleBreakdown] = []
        for character_id, data in by_character.items():
            name = data["name"]
            role_id = f"role-{project_id}-{character_id}"
            scene_ids = list(dict.fromkeys(data["scene_ids"]))
            texts = data["texts"]
            role_size = "lead" if len(scene_ids) >= 5 else "supporting" if len(scene_ids) >= 2 else "day_player" if scene_ids else "unknown"
            demands = self._role_demands(name, " ".join(texts))
            voice_requirements = ["consistent vocal identity across dialogue scenes"]
            if any(word in " ".join(texts).lower() for word in ["whisper", "silent", "quiet"]):
                voice_requirements.append("can hold tension in restrained delivery")
            visual_requirements = ["must not contradict canonical character identity memory"]
            role = CastingRoleBreakdown(
                role_id=role_id,
                project_id=project_id,
                character_id=character_id,
                character_name=name,
                role_label=name,
                scene_ids=scene_ids,
                role_size=role_size,  # type: ignore[arg-type]
                performance_demands=demands,
                voice_requirements=voice_requirements,
                visual_requirements=visual_requirements,
                consent_requirements=["voice likeness consent", "visual likeness consent"],
                audition_sides=[text[:360] for text in texts[:3] if text],
                source_signature=self._signature({"character_id": character_id, "scene_ids": scene_ids, "texts": texts}),
                readiness_label="needs_review",
                evidence_refs=data["evidence"][:8],
                spine_refs=spine_refs,
                reasoning_trace=[
                    {"stage": "script_scene_scan", "scene_count": len(scene_ids)},
                    {"stage": "role_demand_extraction", "demand_count": len(demands)},
                ],
            )
            roles.append(role)
            if request.persist:
                self.storage.save_casting_role_breakdown(role)
        log_stage_event(
            project_id=project_id,
            job_id=None,
            provider="internal",
            stage="casting_role_breakdown_build",
            duration_ms=elapsed_ms(started),
            extra={"role_count": len(roles)},
        )
        return RoleBreakdownBuildResponse(roles=roles)

    def _role_demands(self, name: str, text: str) -> list[str]:
        lowered = text.lower()
        demands = [f"carry {name}'s scene objective through specific behavior rather than explanation"]
        if any(word in lowered for word in ["grief", "loss", "mourn"]):
            demands.append("hold grief with restraint and visible residue")
        if any(word in lowered for word in ["anger", "fight", "betray"]):
            demands.append("let conflict pressure rise without flattening into a single emotional color")
        if any(word in lowered for word in ["secret", "hide", "lie"]):
            demands.append("play concealment and subtext clearly enough for camera and voice direction")
        return demands

    def list_role_breakdowns(self, project_id: str, status: str | None = None, limit: int = 100) -> list[CastingRoleBreakdown]:
        self._require(project_id, "project_id")
        return self.storage.list_casting_role_breakdowns(project_id, status=status, limit=limit)

    def get_role_breakdown(self, project_id: str, role_id: str) -> CastingRoleBreakdown:
        self._require(project_id, "project_id")
        role = self.storage.get_casting_role_breakdown(self._require(role_id, "role_id"))
        if not role or role.project_id != project_id:
            raise StateError("Casting role not found", stage="casting_get_role")
        return role

    def create_talent_profile(self, project_id: str, request: TalentProfileRequest) -> TalentProfile:
        started = start_timer()
        project_id = self._require(project_id, "project_id")
        display_name = self._require(request.display_name, "display_name")
        talent_id = f"talent-{self._character_id(display_name)}-{uuid.uuid4().hex[:8]}"
        profile = TalentProfile(
            talent_id=talent_id,
            project_id=project_id,
            display_name=display_name,
            modality=request.modality,
            capabilities=request.capabilities,
            vocal_characteristics=request.vocal_characteristics,
            visual_characteristics=request.visual_characteristics,
            performance_strengths=request.performance_strengths,
            availability_label=request.availability_label,
            provider_bindings=request.provider_bindings,
            reference_asset_ids=request.reference_asset_ids,
            consent_records=request.consent_records,
            notes=request.notes,
            metadata=request.metadata,
        )
        self.storage.save_talent_profile(profile)
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="casting_talent_profile_save", duration_ms=elapsed_ms(started), extra={"talent_id": talent_id})
        return profile

    def update_talent_profile(self, project_id: str, talent_id: str, request: TalentProfileUpdateRequest) -> TalentProfile:
        project_id = self._require(project_id, "project_id")
        profile = self.storage.get_talent_profile(self._require(talent_id, "talent_id"))
        if not profile or profile.project_id != project_id:
            raise StateError("Talent profile not found", stage="casting_update_talent")
        data = profile.model_dump(mode="json")
        updates = request.model_dump(exclude_unset=True, mode="json")
        data.update({key: value for key, value in updates.items() if value is not None})
        data["updated_at"] = _now()
        updated = TalentProfile(**data)
        self.storage.save_talent_profile(updated)
        return updated

    def list_talent_profiles(self, project_id: str, modality: str | None = None, limit: int = 100) -> list[TalentProfile]:
        self._require(project_id, "project_id")
        return self.storage.list_talent_profiles(project_id, modality=modality, limit=limit)

    def create_audition_package(self, project_id: str, role_id: str, request: AuditionPackageRequest) -> AuditionPackage:
        started = start_timer()
        role = self.get_role_breakdown(project_id, role_id)
        package = AuditionPackage(
            package_id=_new_id("audpkg"),
            project_id=project_id,
            role_id=role.role_id,
            character_id=role.character_id,
            title=request.title or f"{role.character_name} audition",
            instructions=request.instructions or "Play the role demand with restraint; let behavior carry the subtext before dialogue explains it.",
            sides=request.sides or role.audition_sides,
            required_media=request.required_media or ["video", "audio"],
            performance_intent=request.performance_intent or "; ".join(role.performance_demands[:2]),
            evidence_refs=role.evidence_refs[:4],
        )
        self.storage.save_audition_package(package)
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="casting_audition_package_create", duration_ms=elapsed_ms(started), extra={"package_id": package.package_id, "role_id": role_id})
        return package

    def submit_audition(self, project_id: str, package_id: str, request: AuditionSubmissionRequest) -> AuditionSubmission:
        package = self.storage.get_audition_package(self._require(package_id, "package_id"))
        if not package or package.project_id != project_id:
            raise StateError("Audition package not found", stage="casting_submit_audition")
        talent = self.storage.get_talent_profile(self._require(request.talent_id, "talent_id"))
        if not talent or talent.project_id != project_id:
            raise StateError("Talent profile not found", stage="casting_submit_audition")
        audition = AuditionSubmission(
            audition_id=_new_id("audition"),
            project_id=project_id,
            package_id=package.package_id,
            role_id=package.role_id,
            talent_id=talent.talent_id,
            media_refs=request.media_refs,
            submitted_text=request.submitted_text,
            consent_snapshot=talent.consent_records,
            evidence_refs=[
                self._evidence(
                    source_type="talent_profile",
                    source_id=talent.talent_id,
                    talent_id=talent.talent_id,
                    role_id=package.role_id,
                    excerpt=talent.display_name,
                    relevance="Talent profile anchors the audition submission.",
                    reliability_label="supported",
                )
            ],
        )
        self.storage.save_audition_submission(audition)
        return audition

    def evaluate_audition(self, project_id: str, audition_id: str) -> AuditionEvaluation:
        started = start_timer()
        audition = self.storage.get_audition_submission(self._require(audition_id, "audition_id"))
        if not audition or audition.project_id != project_id:
            raise StateError("Audition not found", stage="casting_evaluate_audition")
        role = self.get_role_breakdown(project_id, audition.role_id)
        talent = self.storage.get_talent_profile(audition.talent_id)
        if not talent:
            raise StateError("Talent profile not found", stage="casting_evaluate_audition")
        consent_blockers = self._consent_blockers(talent, role)
        media_present = bool(audition.media_refs or _clean(audition.submitted_text))
        evidence = [
            self._evidence(source_type="role_breakdown", source_id=role.role_id, role_id=role.role_id, excerpt="; ".join(role.performance_demands[:2]), relevance="Role demands define audition evaluation criteria.", reliability_label="supported"),
            self._evidence(source_type="audition_submission", source_id=audition.audition_id, role_id=role.role_id, talent_id=talent.talent_id, audition_id=audition.audition_id, excerpt=audition.submitted_text or "Audition media submitted.", relevance="Audition evidence grounds the casting read.", reliability_label="supported" if media_present else "insufficient_context"),
        ]
        evaluation = AuditionEvaluation(
            evaluation_id=_new_id("audeval"),
            project_id=project_id,
            audition_id=audition.audition_id,
            role_id=role.role_id,
            talent_id=talent.talent_id,
            fit_read=f"{talent.display_name} appears aligned with {role.character_name} when the role is played through restraint and specific behavioral pressure.",
            performance_alignment=(talent.performance_strengths[0] if talent.performance_strengths else "Performance evidence is still emerging; review the audition before approval."),
            voice_alignment=(talent.vocal_characteristics[0] if talent.vocal_characteristics else "Voice fit needs creator review."),
            visual_alignment=(talent.visual_characteristics[0] if talent.visual_characteristics else "Visual fit should be checked against character identity memory."),
            risks=consent_blockers or ([] if media_present else ["Audition has limited media evidence."]),
            recommendations=["Review against the role's primary performance demand before approving a cast decision."],
            uncertainty_label="supported" if media_present and not consent_blockers else "conflicted" if consent_blockers else "insufficient_context",
            evidence_refs=evidence,
            reasoning_trace=[
                {"stage": "role_demands", "count": len(role.performance_demands)},
                {"stage": "consent_check", "blockers": consent_blockers},
                {"stage": "audition_evidence", "media_present": media_present},
            ],
        )
        self._assert_public_language(evaluation.model_dump(mode="json"))
        self.storage.save_audition_evaluation(evaluation)
        audition.status = "evaluated"
        self.storage.save_audition_submission(audition)
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="casting_audition_evaluate", duration_ms=elapsed_ms(started), extra={"audition_id": audition_id})
        return evaluation

    def recommend_casting(self, project_id: str, role_id: str, request: CastingRecommendationRequest | None = None) -> list[CastingRecommendation]:
        started = start_timer()
        request = request or CastingRecommendationRequest()
        role = self.get_role_breakdown(project_id, role_id)
        talents = self.list_talent_profiles(project_id, limit=500)
        if request.candidate_talent_ids:
            wanted = set(request.candidate_talent_ids)
            talents = [talent for talent in talents if talent.talent_id in wanted]
        recommendations: list[CastingRecommendation] = []
        for talent in talents:
            evaluations = self.storage.list_audition_evaluations(project_id, role_id=role.role_id, talent_id=talent.talent_id, limit=1)
            auditions = self.storage.list_audition_submissions(project_id, role_id=role.role_id, talent_id=talent.talent_id, limit=1)
            evaluation = evaluations[0] if evaluations else None
            audition = auditions[0] if auditions else None
            blockers = self._consent_blockers(talent, role)
            evidence = [
                self._evidence(source_type="role_breakdown", source_id=role.role_id, role_id=role.role_id, excerpt="; ".join(role.performance_demands[:2]), relevance="Role breakdown defines casting needs.", reliability_label="supported"),
                self._evidence(source_type="talent_profile", source_id=talent.talent_id, role_id=role.role_id, talent_id=talent.talent_id, excerpt=", ".join((talent.performance_strengths + talent.vocal_characteristics + talent.visual_characteristics)[:3]) or talent.display_name, relevance="Talent profile describes production-relevant capabilities.", reliability_label="emerging"),
            ]
            if evaluation:
                evidence.extend(evaluation.evidence_refs[:2])
            spine_refs = role.spine_refs or self._spine_refs(project_id)
            readiness = "blocked" if blockers else ("ready" if evaluation else "needs_review")
            recommendation = CastingRecommendation(
                recommendation_id=_new_id("cast-rec"),
                project_id=project_id,
                role_id=role.role_id,
                talent_id=talent.talent_id,
                audition_id=audition.audition_id if audition else None,
                evaluation_id=evaluation.evaluation_id if evaluation else None,
                recommendation=f"{talent.display_name} is a viable casting option for {role.character_name} if the creator wants the role's pressure carried through specific behavior.",
                rationale=(evaluation.fit_read if evaluation else "The talent profile has enough production metadata to begin review, but audition evidence should be added before final approval."),
                creative_fit_read="The casting read should preserve the role's restraint and avoid explaining the emotional turn too early.",
                consent_readiness=readiness,  # type: ignore[arg-type]
                readiness_label=readiness,  # type: ignore[arg-type]
                blockers=blockers,
                risks=blockers or ([] if evaluation else ["Recommendation has not been audition-verified yet."]),
                uncertainty_label="supported" if evaluation and not blockers else "conflicted" if blockers else "emerging",
                evidence_refs=evidence,
                spine_refs=spine_refs,
                source_signature=self._signature({"role": role.model_dump(mode="json"), "talent": talent.model_dump(mode="json"), "evaluation": evaluation.model_dump(mode="json") if evaluation else None}),
                reasoning_trace=[
                    {"stage": "role_match", "role_id": role.role_id},
                    {"stage": "audition_lookup", "has_evaluation": bool(evaluation)},
                    {"stage": "consent_check", "blockers": blockers},
                ],
            )
            self._assert_public_language(recommendation.model_dump(mode="json"))
            recommendations.append(recommendation)
            if request.persist:
                self.storage.save_casting_recommendation(recommendation)
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="casting_recommendation_create", duration_ms=elapsed_ms(started), extra={"role_id": role_id, "recommendation_count": len(recommendations)})
        return recommendations

    def _consent_blockers(self, talent: TalentProfile, role: CastingRoleBreakdown) -> list[str]:
        if talent.modality == "placeholder":
            return []
        records = talent.consent_records
        if talent.modality in {"ai", "visual_only"} and not records:
            return []
        statuses = {record.status for record in records}
        if statuses & {"revoked", "expired", "blocked"}:
            return ["Consent status blocks this casting path."]
        if talent.modality in {"human", "hybrid", "voice_only"} and not statuses & {"granted", "limited", "not_required"}:
            return ["Consent must be granted, limited, or not required before approval."]
        return []

    def approve_casting_decision(self, project_id: str, request: CastingDecisionRequest) -> CastingDecision:
        started = start_timer()
        role = self.get_role_breakdown(project_id, request.role_id)
        talent = self.storage.get_talent_profile(self._require(request.talent_id, "talent_id"))
        if not talent or talent.project_id != project_id:
            raise StateError("Talent profile not found", stage="casting_decision_approve")
        blockers = self._consent_blockers(talent, role)
        if blockers and not request.allow_blocked_consent:
            raise StateError("Casting decision has readiness blockers", stage="casting_decision_approve", metadata={"blockers": blockers})
        recommendation = self.storage.get_casting_recommendation(request.recommendation_id) if request.recommendation_id else None
        evidence = role.evidence_refs[:3] + talent.evidence_refs[:2]
        if recommendation:
            evidence.extend(recommendation.evidence_refs[:3])
        readiness = "blocked" if blockers else "ready"
        decision = CastingDecision(
            decision_id=_new_id("cast-decision"),
            project_id=project_id,
            role_id=role.role_id,
            character_id=role.character_id,
            talent_id=talent.talent_id,
            recommendation_id=request.recommendation_id,
            audition_id=request.audition_id,
            evaluation_id=request.evaluation_id,
            approved_by=request.approved_by or "creator",
            decision_rationale=request.decision_rationale or f"{talent.display_name} is approved for {role.character_name}.",
            hybrid_assignment=request.hybrid_assignment,
            provider_requirements=request.provider_requirements,
            evidence_refs=evidence,
            readiness_label=readiness,  # type: ignore[arg-type]
            blockers=blockers,
            source_signature=self._signature({"role": role.source_signature, "talent": talent.model_dump(mode="json"), "recommendation": request.recommendation_id}),
        )
        self._assert_public_language(decision.model_dump(mode="json"))
        self.storage.save_casting_decision(decision)
        if request.save_to_project_memory:
            self.save_casting_decision_memory(
                project_id,
                CastingSaveDecisionRequest(
                    role_id=role.role_id,
                    character_id=role.character_id,
                    talent_id=talent.talent_id,
                    casting_decision_id=decision.decision_id,
                    decision_text=decision.decision_rationale,
                    inferred_tradeoff="casting specificity versus production flexibility",
                    saved_by=request.approved_by or "creator",
                    save_to_project_memory=True,
                ),
            )
        log_stage_event(project_id=project_id, job_id=None, provider="internal", stage="casting_decision_approve", duration_ms=elapsed_ms(started), extra={"decision_id": decision.decision_id, "role_id": role.role_id})
        return decision

    def get_active_casting_projection(
        self,
        project_id: str,
        role_id: str | None = None,
        character_id: str | None = None,
    ) -> CastingProjection:
        project_id = self._require(project_id, "project_id")
        decisions = self.storage.list_casting_decisions(project_id, role_id=role_id, character_id=character_id, active=True, limit=500)
        talent_by_id = {decision.talent_id: self.storage.get_talent_profile(decision.talent_id) for decision in decisions}
        talents = [talent for talent in talent_by_id.values() if talent]
        blockers = [blocker for decision in decisions for blocker in decision.blockers]
        readiness = "blocked" if blockers else "ready" if decisions else "not_requested"
        return CastingProjection(
            projection_id=_new_id("cast-proj"),
            project_id=project_id,
            role_id=role_id,
            character_id=character_id,
            active_decisions=decisions,
            talent_profiles=talents,
            readiness_label=readiness,  # type: ignore[arg-type]
            blockers=blockers,
        )

    def create_readiness_report(self, project_id: str, request: CastingReadinessRequest | None = None) -> CastingReadinessReport:
        request = request or CastingReadinessRequest()
        roles = self.storage.list_casting_role_breakdowns(project_id, limit=500)
        if request.role_id:
            roles = [role for role in roles if role.role_id == request.role_id]
        decisions = self.storage.list_casting_decisions(project_id, active=True, limit=500)
        decision_roles = {decision.role_id for decision in decisions}
        blockers = [blocker for decision in decisions for blocker in decision.blockers]
        missing = [role for role in roles if role.role_id not in decision_roles]
        for role in missing[:5]:
            blockers.append(f"{role.character_name} has no active casting decision.")
        stale_count = len([decision for decision in decisions if decision.stale])
        readiness = "blocked" if any(decision.blockers for decision in decisions) else "needs_review" if missing else "ready" if roles else "not_requested"
        report = CastingReadinessReport(
            report_id=_new_id("cast-ready"),
            project_id=project_id,
            scope=request.scope,
            role_id=request.role_id,
            readiness_label=readiness,  # type: ignore[arg-type]
            covered_roles=len(decision_roles),
            total_roles=len(roles),
            stale_decision_count=stale_count,
            consent_blocker_count=len([blocker for blocker in blockers if "Consent" in blocker or "consent" in blocker]),
            blockers=blockers,
            risks=[] if readiness == "ready" else ["Casting coverage should be resolved before final production review."],
            recommendations=["Approve active casting decisions for every recurring role before production lock."] if missing else [],
            evidence_refs=[ref for role in roles for ref in role.evidence_refs[:1]],
        )
        self.storage.save_casting_readiness_report(report)
        return report

    def department_signal(self, project_id: str) -> CastingDepartmentSignal:
        roles = self.storage.list_casting_role_breakdowns(project_id, limit=500)
        decisions = self.storage.list_casting_decisions(project_id, active=True, limit=500)
        blockers = [blocker for decision in decisions for blocker in decision.blockers]
        readiness = "blocked" if blockers else "ready" if roles and len(decisions) >= len(roles) else "needs_review" if roles else "not_requested"
        return CastingDepartmentSignal(
            status="active" if roles or decisions else "standby",
            signal=(
                "cast coverage ready"
                if readiness == "ready"
                else "casting needs creator review"
                if readiness == "needs_review"
                else "casting coverage pending"
            ),
            readiness_label=readiness,  # type: ignore[arg-type]
            covered_roles=len({decision.role_id for decision in decisions}),
            total_roles=len(roles),
            blocker_count=len(blockers),
            stale_decision_count=len([decision for decision in decisions if decision.stale]),
            evidence_count=sum(len(role.evidence_refs) for role in roles),
            advisory="Resolve casting blockers before production lock." if blockers else "",
        )

    def save_casting_decision_memory(self, project_id: str, request: CastingSaveDecisionRequest) -> CastingDecisionMemoryProjection:
        project_id = self._require(project_id, "project_id")
        decision_text = self._require(request.decision_text, "decision_text")
        memory_entry_id = None
        if request.save_to_project_memory:
            try:
                saved = self.project_store.save_creative_memory(
                    project_id,
                    {
                        "decision_type": "casting_decision",
                        "user_note": decision_text,
                        "inferred_tradeoff": request.inferred_tradeoff or "casting specificity",
                        "source_context": {
                            "role_id": request.role_id,
                            "character_id": request.character_id,
                            "talent_id": request.talent_id,
                            "casting_decision_id": request.casting_decision_id,
                        },
                    },
                )
                if isinstance(saved, dict):
                    memory_entry_id = saved.get("memory_id")
            except Exception:
                memory_entry_id = None
        projection = CastingDecisionMemoryProjection(
            decision_id=_new_id("cast-memory"),
            project_id=project_id,
            role_id=request.role_id,
            character_id=request.character_id,
            talent_id=request.talent_id,
            casting_decision_id=request.casting_decision_id,
            decision_text=decision_text,
            inferred_tradeoff=request.inferred_tradeoff,
            saved_by=request.saved_by or "creator",
            memory_entry_id=memory_entry_id,
        )
        self.storage.save_casting_decision_memory_projection(projection)
        return projection

    def update_casting_decision_memory(self, project_id: str, decision_id: str, request: CastingDecisionUpdateRequest) -> CastingDecisionMemoryProjection:
        updated = self.storage.update_casting_decision_memory_projection(project_id, decision_id, request.model_dump(exclude_unset=True, mode="json"))
        if not updated:
            raise StateError("Casting memory decision not found", stage="casting_memory_update")
        return updated

    def forget_casting_decision_memory(self, project_id: str, decision_id: str) -> CastingDecisionMemoryProjection:
        forgotten = self.storage.forget_casting_decision_memory_projection(project_id, decision_id)
        if not forgotten:
            raise StateError("Casting memory decision not found", stage="casting_memory_forget")
        return forgotten

    def get_talent_profile(self, project_id: str, talent_id: str) -> TalentProfile:
        profile = self.storage.get_talent_profile(talent_id)
        if not profile or profile.project_id != project_id:
            raise StateError("Talent profile not found", stage="casting_get_talent")
        return profile

    def list_audition_packages(self, project_id: str, **filters):
        return self.storage.list_audition_packages(project_id, **filters)

    def list_audition_submissions(self, project_id: str, **filters):
        return self.storage.list_audition_submissions(project_id, **filters)

    def list_casting_recommendations(self, project_id: str, **filters):
        return self.storage.list_casting_recommendations(project_id, **filters)

    def list_casting_decisions(self, project_id: str, **filters):
        return self.storage.list_casting_decisions(project_id, **filters)


casting_intelligence_service = CastingIntelligenceService()

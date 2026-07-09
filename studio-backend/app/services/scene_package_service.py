from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.production_intelligence import (
    ProductionPackageProvenance,
    ScenePackageDerivedGuidance,
    SceneProductionPackage,
)


class ScenePackageService:
    """
    Read-only scene packaging service.

    This service builds a canonical production package from explicit scene input
    and existing film-brain context. It does not mutate memory, submit render
    jobs, or generate provider requests.
    """

    def build_scene_package(
        self,
        scene_data: Optional[Dict[str, Any]],
        creative_spine: Optional[Any] = None,
        film_memory: Optional[Any] = None,
        film_structure: Optional[Any] = None,
        director_evaluation: Optional[Dict[str, Any]] = None,
        film_intelligence_summary: Optional[Dict[str, Any]] = None,
        cinematic_language_summary: Optional[Dict[str, Any]] = None,
        taste_context: Optional[Dict[str, Any]] = None,
    ) -> SceneProductionPackage:
        """
        Build a canonical scene production package.

        Canonical fields are grounded in scene input and existing film truth.
        Derived guidance from film intelligence, cinematic language, and taste
        remains explicitly non-canonical.
        """
        safe_scene_data = scene_data if isinstance(scene_data, dict) else {}
        scene_id = str(safe_scene_data.get("scene_id") or "unknown_scene")
        film_id = self._resolve_film_id(safe_scene_data, film_memory, film_structure)

        provenance = ProductionPackageProvenance()
        provenance.canonical_sources["scene_input"] = bool(safe_scene_data)
        provenance.canonical_sources["creative_spine"] = creative_spine is not None
        provenance.canonical_sources["film_memory"] = film_memory is not None
        provenance.canonical_sources["film_structure"] = film_structure is not None
        provenance.canonical_sources["director_evaluation"] = isinstance(director_evaluation, dict)
        provenance.derived_sources["film_intelligence"] = isinstance(film_intelligence_summary, dict)
        provenance.derived_sources["cinematic_language"] = isinstance(cinematic_language_summary, dict)
        provenance.derived_sources["taste_context"] = isinstance(taste_context, dict)

        narrative_purpose = self._build_narrative_purpose(
            safe_scene_data=safe_scene_data,
            film_structure=film_structure,
            director_evaluation=director_evaluation,
            provenance=provenance,
        )
        emotional_target = self._build_emotional_target(
            safe_scene_data=safe_scene_data,
            film_memory=film_memory,
            film_structure=film_structure,
            provenance=provenance,
        )
        visual_target = self._build_visual_target(
            safe_scene_data=safe_scene_data,
            film_memory=film_memory,
            creative_spine=creative_spine,
            provenance=provenance,
        )
        motif_obligations = self._build_motif_obligations(
            scene_id=scene_id,
            safe_scene_data=safe_scene_data,
            film_memory=film_memory,
            provenance=provenance,
        )
        continuity_constraints = self._build_continuity_constraints(
            scene_id=scene_id,
            safe_scene_data=safe_scene_data,
            film_memory=film_memory,
            film_structure=film_structure,
            provenance=provenance,
        )
        restraint_rules, forbidden_moves = self._build_restraint_rules(
            film_memory=film_memory,
            creative_spine=creative_spine,
            provenance=provenance,
        )
        provider_neutral_execution_brief = self._build_execution_brief(
            narrative_purpose=narrative_purpose,
            emotional_target=emotional_target,
            visual_target=visual_target,
            motif_obligations=motif_obligations,
            continuity_constraints=continuity_constraints,
            restraint_rules=restraint_rules,
        )
        if provider_neutral_execution_brief:
            provenance.grounded_fields.append("provider_neutral_execution_brief")
        else:
            provenance.notes.append("Execution brief is sparse because grounded scene context is limited.")

        derived_guidance = ScenePackageDerivedGuidance(
            film_intelligence=self._build_film_intelligence_guidance(film_intelligence_summary, provenance),
            cinematic_language=self._build_cinematic_guidance(cinematic_language_summary, provenance),
            taste_guidance=self._build_taste_guidance(taste_context, provenance),
        )

        if not safe_scene_data:
            provenance.notes.append("No scene input provided; package uses conservative defaults.")
        if not film_memory:
            provenance.notes.append("No film memory provided; motif and restraint coverage may be sparse.")
        if not film_structure:
            provenance.notes.append("No film structure provided; act/sequence continuity cues may be sparse.")

        provenance.grounded_fields = sorted(set(provenance.grounded_fields))
        provenance.derived_fields = sorted(set(provenance.derived_fields))
        provenance.advisory_fields = sorted(set(provenance.advisory_fields))

        return SceneProductionPackage(
            scene_id=scene_id,
            film_id=film_id,
            narrative_purpose=narrative_purpose,
            emotional_target=emotional_target,
            visual_target=visual_target,
            motif_obligations=motif_obligations,
            continuity_constraints=continuity_constraints,
            restraint_rules=restraint_rules,
            forbidden_moves=forbidden_moves,
            provider_neutral_execution_brief=provider_neutral_execution_brief,
            derived_guidance=derived_guidance,
            provenance=provenance,
            derived_only=False,
        )

    def _resolve_film_id(
        self,
        safe_scene_data: Dict[str, Any],
        film_memory: Optional[Any],
        film_structure: Optional[Any],
    ) -> str:
        film_id = safe_scene_data.get("film_id")
        if film_id:
            return str(film_id)
        if film_memory is not None:
            memory_film_id = getattr(film_memory, "film_id", "")
            if memory_film_id:
                return str(memory_film_id)
        if film_structure is not None:
            structure_film_id = getattr(film_structure, "film_id", "")
            if structure_film_id:
                return str(structure_film_id)
        return "unknown_film"

    def _build_narrative_purpose(
        self,
        safe_scene_data: Dict[str, Any],
        film_structure: Optional[Any],
        director_evaluation: Optional[Dict[str, Any]],
        provenance: ProductionPackageProvenance,
    ) -> str:
        intent = str(safe_scene_data.get("intent", "")).strip()
        if intent:
            provenance.grounded_fields.append("narrative_purpose")
            return intent

        scene_id = str(safe_scene_data.get("scene_id", ""))
        if film_structure is not None and scene_id:
            sequence_goal = self._find_sequence_goal(film_structure, scene_id)
            if sequence_goal:
                provenance.grounded_fields.append("narrative_purpose")
                return sequence_goal

        if isinstance(director_evaluation, dict):
            notes = str(director_evaluation.get("notes", "")).strip()
            if notes:
                provenance.notes.append("Narrative purpose fell back to director notes because scene intent was sparse.")
                return notes

        return ""

    def _build_emotional_target(
        self,
        safe_scene_data: Dict[str, Any],
        film_memory: Optional[Any],
        film_structure: Optional[Any],
        provenance: ProductionPackageProvenance,
    ) -> str:
        for key in ("emotional_tone", "tone"):
            value = str(safe_scene_data.get(key, "")).strip()
            if value:
                provenance.grounded_fields.append("emotional_target")
                return value

        scene_id = str(safe_scene_data.get("scene_id", ""))
        if film_structure is not None and scene_id:
            act_contract = self._find_act_emotional_contract(film_structure, scene_id)
            if act_contract:
                provenance.grounded_fields.append("emotional_target")
                return act_contract

        if film_memory is not None:
            contract = str(getattr(film_memory, "emotional_contract", "")).strip()
            if contract:
                provenance.grounded_fields.append("emotional_target")
                return contract

        return ""

    def _build_visual_target(
        self,
        safe_scene_data: Dict[str, Any],
        film_memory: Optional[Any],
        creative_spine: Optional[Any],
        provenance: ProductionPackageProvenance,
    ) -> str:
        visual_bits: List[str] = []
        visual_description = str(safe_scene_data.get("visual_description", "")).strip()
        camera_work = str(safe_scene_data.get("camera_work", "")).strip()
        if visual_description:
            visual_bits.append(visual_description)
        if camera_work:
            visual_bits.append(camera_work)
        if visual_bits:
            provenance.grounded_fields.append("visual_target")
            return " | ".join(visual_bits)

        visual_philosophy = ""
        if film_memory is not None:
            visual_philosophy = str(getattr(film_memory, "visual_philosophy", "")).strip()
        if not visual_philosophy and creative_spine is not None:
            visual_philosophy = self._extract_spine_field_value(creative_spine, "visual_philosophy")
        if visual_philosophy:
            provenance.grounded_fields.append("visual_target")
            return visual_philosophy
        return ""

    def _build_motif_obligations(
        self,
        scene_id: str,
        safe_scene_data: Dict[str, Any],
        film_memory: Optional[Any],
        provenance: ProductionPackageProvenance,
    ) -> List[str]:
        if film_memory is None:
            return []

        scene_text = " ".join(
            str(safe_scene_data.get(key, "")).lower()
            for key in ("visual_description", "dialogue", "actions", "intent")
        )
        obligations: List[str] = []
        for motif in getattr(film_memory, "motifs", []) or []:
            motif_name = str(getattr(motif, "name", "")).strip()
            motif_id = str(getattr(motif, "motif_id", "")).strip()
            if not motif_name and not motif_id:
                continue
            if getattr(motif, "first_appearance_scene", "") == scene_id:
                obligations.append(f"Introduce motif: {motif_name or motif_id}")
                continue
            recurrence_scene_ids = [
                recurrence.get("scene_id", "")
                for recurrence in (getattr(motif, "recurrences", []) or [])
                if isinstance(recurrence, dict)
            ]
            if scene_id in recurrence_scene_ids:
                obligations.append(f"Reinforce motif: {motif_name or motif_id}")
                continue
            if motif_name and motif_name.lower() in scene_text:
                obligations.append(f"Preserve motif meaning: {motif_name}")

        if obligations:
            provenance.grounded_fields.append("motif_obligations")
        return obligations

    def _build_continuity_constraints(
        self,
        scene_id: str,
        safe_scene_data: Dict[str, Any],
        film_memory: Optional[Any],
        film_structure: Optional[Any],
        provenance: ProductionPackageProvenance,
    ) -> List[str]:
        constraints: List[str] = []
        character_ids = safe_scene_data.get("character_appearances") or []
        if isinstance(character_ids, list) and character_ids:
            constraints.append(
                "Maintain character continuity for: " + ", ".join(str(character_id) for character_id in character_ids)
            )

        if film_memory is not None:
            for tension in getattr(film_memory, "unresolved_tensions", []) or []:
                introduced_scene = str(getattr(tension, "introduced_scene", "")).strip()
                description = str(getattr(tension, "description", "")).strip()
                if description and introduced_scene and introduced_scene != scene_id:
                    constraints.append(f"Do not erase unresolved tension: {description}")

        if film_structure is not None and scene_id:
            act_number = self._find_act_number(film_structure, scene_id)
            if act_number:
                constraints.append(f"Stay aligned with act {act_number} progression")

        if constraints:
            provenance.grounded_fields.append("continuity_constraints")
        return constraints

    def _build_restraint_rules(
        self,
        film_memory: Optional[Any],
        creative_spine: Optional[Any],
        provenance: ProductionPackageProvenance,
    ) -> tuple[List[str], List[str]]:
        restraint_rules: List[str] = []
        forbidden_moves: List[str] = []

        for rule in getattr(film_memory, "restraint_rules", []) or [] if film_memory is not None else []:
            if isinstance(rule, dict):
                rule_text = str(rule.get("rule", "")).strip()
                alternative = str(rule.get("alternatives", "")).strip()
                if rule_text:
                    restraint_rules.append(rule_text)
                    forbidden_moves.append(rule_text)
                if alternative:
                    restraint_rules.append(f"Prefer instead: {alternative}")

        if creative_spine is not None:
            for field_name in getattr(creative_spine, "revisable_fields", []) or []:
                if field_name == "restraint_rules":
                    provenance.notes.append("Creative spine governance includes restraint rules.")
                    break

        if restraint_rules:
            provenance.grounded_fields.append("restraint_rules")
            provenance.grounded_fields.append("forbidden_moves")

        return restraint_rules, forbidden_moves

    def _build_execution_brief(
        self,
        narrative_purpose: str,
        emotional_target: str,
        visual_target: str,
        motif_obligations: List[str],
        continuity_constraints: List[str],
        restraint_rules: List[str],
    ) -> str:
        brief_parts: List[str] = []
        if narrative_purpose:
            brief_parts.append(f"Narrative purpose: {narrative_purpose}")
        if emotional_target:
            brief_parts.append(f"Emotional target: {emotional_target}")
        if visual_target:
            brief_parts.append(f"Visual target: {visual_target}")
        if motif_obligations:
            brief_parts.append("Motif obligations: " + "; ".join(motif_obligations[:3]))
        if continuity_constraints:
            brief_parts.append("Continuity constraints: " + "; ".join(continuity_constraints[:3]))
        if restraint_rules:
            brief_parts.append("Restraints: " + "; ".join(restraint_rules[:3]))
        return " | ".join(brief_parts)

    def _build_film_intelligence_guidance(
        self,
        film_intelligence_summary: Optional[Dict[str, Any]],
        provenance: ProductionPackageProvenance,
    ) -> Dict[str, object]:
        if not isinstance(film_intelligence_summary, dict):
            return {}

        guidance = {
            "scope": film_intelligence_summary.get("scope"),
            "sequence_summary": film_intelligence_summary.get("sequence_summary"),
            "act_summary": film_intelligence_summary.get("act_summary"),
            "film_summary": film_intelligence_summary.get("film_summary"),
            "debt_payoff_arc_counts": film_intelligence_summary.get("debt_payoff_arc_counts"),
        }
        if any(value for value in guidance.values()):
            provenance.derived_fields.append("derived_guidance.film_intelligence")
        return guidance

    def _build_cinematic_guidance(
        self,
        cinematic_language_summary: Optional[Dict[str, Any]],
        provenance: ProductionPackageProvenance,
    ) -> Dict[str, object]:
        if not isinstance(cinematic_language_summary, dict):
            return {}

        guidance = {
            "visual_intent": cinematic_language_summary.get("visual_intent"),
            "framing_meaning": cinematic_language_summary.get("framing_meaning"),
            "movement_significance": cinematic_language_summary.get("movement_significance"),
            "restraint_score": cinematic_language_summary.get("restraint_score"),
            "dialogue_substitution": cinematic_language_summary.get("dialogue_substitution"),
            "motif_evolution": cinematic_language_summary.get("motif_evolution"),
            "confidence": cinematic_language_summary.get("confidence"),
        }
        if any(value not in (None, "", {}, []) for value in guidance.values()):
            provenance.derived_fields.append("derived_guidance.cinematic_language")
        return guidance

    def _build_taste_guidance(
        self,
        taste_context: Optional[Dict[str, Any]],
        provenance: ProductionPackageProvenance,
    ) -> Dict[str, object]:
        if not isinstance(taste_context, dict):
            return {}

        dimension_adjustments = taste_context.get("dimension_adjustments") or {}
        dimension_confidence = taste_context.get("dimension_confidence") or {}
        signal_counts = taste_context.get("signal_counts") or {}
        if not isinstance(dimension_adjustments, dict):
            dimension_adjustments = {}
        if not isinstance(dimension_confidence, dict):
            dimension_confidence = {}
        if not isinstance(signal_counts, dict):
            signal_counts = {}

        guidance = {
            "advisory_only": True,
            "dimension_adjustments": dimension_adjustments,
            "dimension_confidence": dimension_confidence,
            "signal_counts": signal_counts,
        }
        has_signal = any(
            value
            for value in (dimension_adjustments, dimension_confidence, signal_counts)
        )
        if has_signal:
            provenance.derived_fields.append("derived_guidance.taste_guidance")
            provenance.advisory_fields.append("derived_guidance.taste_guidance")
        return guidance if has_signal else {}

    def _find_sequence_goal(self, film_structure: Any, scene_id: str) -> str:
        scene_index = self._extract_scene_index(scene_id)
        if scene_index is None:
            return ""
        for sequence in getattr(film_structure, "all_sequences", []) or []:
            start_index = getattr(sequence, "start_scene_index", None)
            end_index = getattr(sequence, "end_scene_index", None)
            if start_index is None or end_index is None:
                continue
            if start_index <= scene_index <= end_index:
                return str(getattr(sequence, "sequence_goal", "")).strip()
        return ""

    def _find_act_emotional_contract(self, film_structure: Any, scene_id: str) -> str:
        scene_index = self._extract_scene_index(scene_id)
        if scene_index is None:
            return ""
        for act in getattr(film_structure, "acts", []) or []:
            start_index = getattr(act, "start_scene_index", None)
            end_index = getattr(act, "end_scene_index", None)
            if start_index is None or end_index is None:
                continue
            if start_index <= scene_index <= end_index:
                return str(getattr(act, "emotional_contract", "")).strip()
        return ""

    def _find_act_number(self, film_structure: Any, scene_id: str) -> Optional[int]:
        scene_index = self._extract_scene_index(scene_id)
        if scene_index is None:
            return None
        for act in getattr(film_structure, "acts", []) or []:
            start_index = getattr(act, "start_scene_index", None)
            end_index = getattr(act, "end_scene_index", None)
            if start_index is None or end_index is None:
                continue
            if start_index <= scene_index <= end_index:
                try:
                    return int(getattr(act, "act_number", 0))
                except (TypeError, ValueError):
                    return None
        return None

    def _extract_scene_index(self, scene_id: str) -> Optional[int]:
        if not scene_id.startswith("scene_"):
            return None
        try:
            return int(scene_id.split("_", 1)[1])
        except (TypeError, ValueError):
            return None

    def _extract_spine_field_value(self, creative_spine: Any, field_name: str) -> str:
        constraint = None
        if hasattr(creative_spine, "get_constraint_for_field"):
            try:
                constraint = creative_spine.get_constraint_for_field(field_name)
            except Exception:
                constraint = None
        if constraint is None:
            return ""
        description = str(getattr(constraint, "description", "")).strip()
        return description


scene_package_service = ScenePackageService()


"""
Spine Consumption Service - Agent-facing API for spine, structure, and memory.

This service provides a safe, role-filtered way for agents to consume
the creative spine, film structure, and film memory. It builds on top of:
- SpineService: For spine constraints and governance
- FilmStructureService: For film structure and memory extraction

Usage:
    service = SpineConsumptionService()
    
    # Register a film's structure and memory locally
    service.register_film(film_id, structure=structure, memory=memory)
    
    # Create spine via spine service
    spine_service.create_spine_from_memory(film_id, memory)
    
    # Get full context for a director working on scene_45
    context = service.get_context_for_role(
        film_id="film_123",
        role=AgentRole.DIRECTOR,
        scene_id="scene_45"
    )
    
    # Get constraints only
    constraints = service.get_constraints_for_role(film_id, AgentRole.CINEMATOGRAPHER)
    
    # Get structure context for a scene
    structure = service.get_structure_context(film_id, scene_id="scene_45")
"""

from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime

from app.models.crew import AgentRole, FilmStructure, Act, Sequence, Beat
from app.models.spine import CreativeSpine, SpineConstraint
from app.models.memory import FilmLevelMemory
from app.models.taste_learning import TasteCalibrationContext, utc_now_iso
from app.models.co_director import SessionMode

# Import existing services
from app.services.spine_service import SpineService, spine_service
from app.services.film_structure_service import FilmStructureService, film_structure_service
from app.services.film_intelligence_service import film_intelligence_service
from app.services.taste_learning_service import taste_learning_service
from app.services.cinematic_language_service import CinematicLanguageAnalyzer
from app.services.scene_package_service import ScenePackageService, scene_package_service
from app.models.cinematic_language import CinematicLanguageContext
from app.services.co_director_session_service import co_director_session_service

if TYPE_CHECKING:
    from app.models.crew import CrewTask
from uuid import UUID


class SpineConsumptionService:
    """
    Service for agents to consume spine, structure, and memory context.
    
    This is the primary interface through which agents should access
    creative constraints and film context. It provides:
    - Role-filtered constraint access (delegates to SpineService)
    - Scene-specific structure context
    - Role-appropriate memory access
    - Safe handling of missing/partial data
    
    The service maintains its own registry of structures and memories,
    and delegates spine constraint retrieval to SpineService.
    """
    
    def __init__(self):
        """Initialize the consumption service."""
        self._spine_service = spine_service
        self._structure_service = film_structure_service
        self._scene_package_service = scene_package_service
        
        # Local registry of films (structure and memory cached locally)
        self._structures: Dict[str, FilmStructure] = {}
        self._memories: Dict[str, FilmLevelMemory] = {}
    
    # =========================================================================
    # Film Registration
    # =========================================================================
    
    def register_film(
        self,
        film_id: str,
        structure: Optional[FilmStructure] = None,
        memory: Optional[FilmLevelMemory] = None
    ) -> None:
        """
        Register a film's structure and memory for consumption.
        
        This should be called when a film is loaded or created.
        Spine should be created separately via SpineService.
        
        Args:
            film_id: Film identifier
            structure: Optional FilmStructure
            memory: Optional FilmLevelMemory
        """
        if structure:
            self._structures[film_id] = structure
        if memory:
            self._memories[film_id] = memory
    
    def register_structure(self, film_id: str, structure: FilmStructure) -> None:
        """Register a structure for a film."""
        self._structures[film_id] = structure
    
    def register_memory(self, film_id: str, memory: FilmLevelMemory) -> None:
        """Register a memory for a film."""
        self._memories[film_id] = memory

    def get_taste_context(
        self,
        project_id: Optional[str],
        film_id: str,
        scene_id: Optional[str] = None
    ) -> TasteCalibrationContext:
        """
        Get bounded taste calibration context for runtime visibility.

        This is a read-only helper that exposes taste-learning output without
        injecting it into any existing role context automatically. It is safe by
        default: missing memory, missing project identifiers, or service errors
        all return an empty calibration context rather than raising.
        """
        try:
            resolved_project_id = project_id
            if not resolved_project_id:
                registered_memory = self._memories.get(film_id)
                resolved_project_id = getattr(registered_memory, "project_id", None) or None

            if not resolved_project_id:
                return TasteCalibrationContext(
                    project_id=None,
                    film_id=film_id,
                    profile_scope="project",
                    generated_at=utc_now_iso(),
                )

            return taste_learning_service.get_calibration_context(
                project_id=resolved_project_id,
                film_id=film_id,
            )
        except Exception:
            return TasteCalibrationContext(
                project_id=project_id,
                film_id=film_id,
                profile_scope="project",
                generated_at=utc_now_iso(),
            )

    def get_co_director_context(
        self,
        project_id: Optional[str],
        film_id: str,
        session_id: Optional[UUID] = None,
        scene_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get bounded co-director session context for runtime visibility.

        This is a read-only helper that exposes co-director session state
        without injecting it into any existing role context automatically.
        It is safe by default: missing session, missing identifiers, or
        service errors all return an empty/default context rather than raising.

        Args:
            project_id: Project identifier (used for session lookup)
            film_id: Film identifier
            session_id: Optional explicit session ID (preferred lookup)
            scene_id: Optional scene ID to update active scene

        Returns:
            Dict with co-director context:
            - session_active: bool indicating if session exists
            - current_mode: SessionMode value or null
            - active_scene_id: str or null
            - revision_count: int (0 if no session)
            - repeated_critique_count: int (0 if no session)
            - last_accepted_suggestion: str or null
            - timestamps: dict with created_at and updated_at (or nulls)
            - derived: dict with advisory-only derived metrics
            - canonical_sources: dict indicating which sources were consulted
        """
        result: Dict[str, Any] = {
            "film_id": film_id,
            "session_id": str(session_id) if session_id else None,
            "scene_id": scene_id,
            "timestamp": datetime.utcnow().isoformat(),
            "session_active": False,
            "current_mode": None,
            "active_scene_id": None,
            "revision_count": 0,
            "repeated_critique_count": 0,
            "last_accepted_suggestion": None,
            "timestamps": {
                "created_at": None,
                "updated_at": None,
            },
            "derived": {
                "engagement_level": "inactive",
                "collaboration_depth": "none",
                "suggestion_acceptance_rate": None,
                "critique_repetition_risk": "low",
            },
            "canonical_sources": {
                "session_service": False,
                "session_record": False,
            },
            "notes": [],
        }

        try:
            # Mark service availability
            result["canonical_sources"]["session_service"] = True

            # Resolve session
            session = None
            if session_id:
                session = co_director_session_service.get_session(session_id)
            elif project_id and film_id:
                # No session lookup by project+film alone - requires explicit session_id
                result["notes"].append("Session lookup requires explicit session_id")

            if session is None:
                result["notes"].append("No active co-director session found")
                return result

            # Mark session record availability
            result["canonical_sources"]["session_record"] = True
            result["session_active"] = True

            # Populate canonical session data
            result["current_mode"] = session.current_mode.value if isinstance(session.current_mode, SessionMode) else session.current_mode
            result["active_scene_id"] = str(session.active_scene_id) if session.active_scene_id else None
            result["revision_count"] = session.revision_count
            result["repeated_critique_count"] = session.repeated_critique_count
            result["last_accepted_suggestion"] = session.last_accepted_suggestion
            result["timestamps"] = {
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            }

            # Update active scene if scene_id provided
            if scene_id:
                # Try to convert to UUID if valid, otherwise keep as string
                try:
                    scene_uuid = UUID(scene_id) if not isinstance(scene_id, UUID) else scene_id
                    if scene_uuid != session.active_scene_id:
                        updated_session = co_director_session_service.set_active_scene(
                            session_id=session.session_id,
                            scene_id=scene_uuid
                        )
                        if updated_session:
                            result["active_scene_id"] = str(updated_session.active_scene_id) if updated_session.active_scene_id else None
                except ValueError:
                    # scene_id is not a valid UUID (e.g., "scene_42"), just store as-is
                    result["active_scene_id"] = scene_id

            # Calculate advisory derived metrics
            result["derived"] = self._calculate_codirector_derived_metrics(session)

            return result

        except Exception as exc:
            result["notes"].append(f"Co-director context unavailable: {str(exc)}")
            return result

    def _calculate_codirector_derived_metrics(self, session) -> Dict[str, Any]:
        """
        Calculate advisory-only derived metrics from session state.

        These are clearly marked as derived/heuristic and should never
        be treated as canonical truth.
        """
        metrics: Dict[str, Any] = {
            "engagement_level": "inactive",
            "collaboration_depth": "none",
            "suggestion_acceptance_rate": None,
            "critique_repetition_risk": "low",
        }

        try:
            # Engagement level based on mode and revision activity
            mode = session.current_mode
            if isinstance(mode, str):
                mode = SessionMode(mode) if mode in [m.value for m in SessionMode] else SessionMode.PASSIVE

            if mode == SessionMode.PASSIVE:
                metrics["engagement_level"] = "passive"
            elif mode == SessionMode.ADVISORY:
                metrics["engagement_level"] = "advisory"
            elif mode == SessionMode.COLLABORATIVE:
                metrics["engagement_level"] = "highly_engaged"
            elif mode == SessionMode.EXPERIMENTAL:
                metrics["engagement_level"] = "experimental"

            # Collaboration depth based on revision count
            if session.revision_count == 0:
                metrics["collaboration_depth"] = "none"
            elif session.revision_count < 3:
                metrics["collaboration_depth"] = "surface"
            elif session.revision_count < 10:
                metrics["collaboration_depth"] = "moderate"
            else:
                metrics["collaboration_depth"] = "deep"

            # Suggestion acceptance rate (if we have data)
            if session.revision_count > 0 and session.last_accepted_suggestion:
                metrics["suggestion_acceptance_rate"] = "high"  # At least one accepted

            # Critique repetition risk based on count
            if session.repeated_critique_count == 0:
                metrics["critique_repetition_risk"] = "low"
            elif session.repeated_critique_count < 3:
                metrics["critique_repetition_risk"] = "moderate"
            else:
                metrics["critique_repetition_risk"] = "high"

        except Exception:
            pass  # Keep default values on any error

        return metrics

    def get_cinematic_language_context(
        self,
        film_id: str,
        scene_data: Optional[Dict[str, Any]] = None,
        scene_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get read-only derived cinematic language context.

        This exposes advisory visual storytelling analysis without mutating any
        evaluator, score, memory, or runtime behavior. Canonical structure,
        memory, and spine remain the only sources of truth.
        """
        safe_scene_data = scene_data if isinstance(scene_data, dict) else {}
        resolved_scene_id = scene_id or safe_scene_data.get("scene_id")
        result: Dict[str, Any] = {
            "film_id": film_id,
            "scene_id": resolved_scene_id,
            "timestamp": datetime.utcnow().isoformat(),
            "available": False,
            "derived_only": True,
            "canonical_sources": {
                "structure": False,
                "memory": False,
                "spine": False,
                "scene_data": bool(safe_scene_data),
            },
            "grounded_inputs": {
                "scene_id": resolved_scene_id,
                "visual_description": str(safe_scene_data.get("visual_description", "")),
                "camera_work": str(safe_scene_data.get("camera_work", "")),
                "lighting": str(safe_scene_data.get("lighting", "")),
                "dialogue": str(safe_scene_data.get("dialogue", "")),
                "actions": str(safe_scene_data.get("actions", "")),
            },
            "heuristic_outputs": {
                "visual_intent_category": "none_detected",
                "visual_intent_confidence": 0.5,
                "framing_meaning": "neutral",
                "framing_confidence": 0.5,
                "movement_significance": "none",
                "movement_confidence": 0.5,
                "restraint_score": 0.5,
                "restraint_indicators": [],
                "dialogue_substitution_opportunity": 0.5,
                "substitution_indicators": [],
                "motif_evolution_stage": "none",
                "motif_evolution_confidence": 0.5,
                "detected_motif_references": [],
            },
            "summary": {
                "visual_intent": "none_detected",
                "framing_meaning": "neutral",
                "movement_significance": "none",
                "restraint_score": 0.5,
                "dialogue_to_visual_substitution_opportunity": 0.5,
                "motif_evolution_stage": "none",
                "confidence": {
                    "visual_intent": 0.5,
                    "framing": 0.5,
                    "movement": 0.5,
                    "motif_evolution": 0.5,
                },
            },
            "notes": [],
        }

        try:
            structure = self._structures.get(film_id)
            memory = self._memories.get(film_id)
            spine = self._spine_service.get_spine(film_id)

            result["canonical_sources"]["structure"] = structure is not None
            result["canonical_sources"]["memory"] = memory is not None
            result["canonical_sources"]["spine"] = spine is not None

            if structure is None:
                result["notes"].append("No film structure registered")
            if memory is None:
                result["notes"].append("No film memory registered")
            if spine is None:
                result["notes"].append("No creative spine registered")

            if not (result["grounded_inputs"]["visual_description"] or result["grounded_inputs"]["camera_work"]):
                result["notes"].append("No visual or camera data available for cinematic language analysis")
                return result

            context = CinematicLanguageContext(
                scene_data=safe_scene_data,
                film_memory=memory,
                film_structure=structure,
                spine=spine,
            )
            signal = CinematicLanguageAnalyzer().analyze_scene(context)

            result["heuristic_outputs"] = {
                "visual_intent_category": signal.visual_intent_category,
                "visual_intent_confidence": signal.visual_intent_confidence,
                "framing_meaning": signal.framing_meaning,
                "framing_confidence": signal.framing_confidence,
                "movement_significance": signal.movement_significance,
                "movement_confidence": signal.movement_confidence,
                "restraint_score": signal.restraint_score,
                "restraint_indicators": list(signal.restraint_indicators),
                "dialogue_substitution_opportunity": signal.dialogue_substitution_opportunity,
                "substitution_indicators": list(signal.substitution_indicators),
                "motif_evolution_stage": signal.motif_evolution_stage,
                "motif_evolution_confidence": signal.motif_evolution_confidence,
                "detected_motif_references": list(signal.detected_motif_references),
            }
            result["summary"] = {
                "visual_intent": signal.visual_intent_category,
                "framing_meaning": signal.framing_meaning,
                "movement_significance": signal.movement_significance,
                "restraint_score": signal.restraint_score,
                "dialogue_to_visual_substitution_opportunity": signal.dialogue_substitution_opportunity,
                "motif_evolution_stage": signal.motif_evolution_stage,
                "confidence": {
                    "visual_intent": signal.visual_intent_confidence,
                    "framing": signal.framing_confidence,
                    "movement": signal.movement_confidence,
                    "motif_evolution": signal.motif_evolution_confidence,
                },
            }
            result["available"] = True
            return result
        except Exception as exc:
            result["notes"].append(f"Cinematic language context unavailable: {str(exc)}")
            return result

    def get_film_intelligence_context(
        self,
        film_id: str,
        scene_id: Optional[str] = None,
        act_number: Optional[int] = None,
        sequence_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get read-only derived film-intelligence context.

        This exposes derived sequence/act/film summaries for inspection and
        future tooling. Canonical film memory, structure, and spine remain the
        authoritative sources; returned summaries are explicitly derived only.
        """
        result: Dict[str, Any] = {
            "film_id": film_id,
            "scene_id": scene_id,
            "act_number": act_number,
            "sequence_id": sequence_id,
            "timestamp": datetime.utcnow().isoformat(),
            "available": False,
            "canonical_sources": {
                "structure": False,
                "memory": False,
                "spine": False,
            },
            "derived": {
                "scope": "film",
                "sequence": None,
                "act": None,
                "film": None,
                "debt_payoff_arc_summary": {
                    "setup_payoff_count": 0,
                    "open_tension_count": 0,
                    "motif_count": 0,
                    "arc_count": 0,
                },
            },
            "notes": [],
        }

        try:
            structure = self._structures.get(film_id)
            memory = self._memories.get(film_id)
            spine = self._spine_service.get_spine(film_id)

            result["canonical_sources"]["structure"] = structure is not None
            result["canonical_sources"]["memory"] = memory is not None
            result["canonical_sources"]["spine"] = spine is not None

            if structure is None:
                result["notes"].append("No film structure registered")
            if memory is None:
                result["notes"].append("No film memory registered")
            if spine is None:
                result["notes"].append("No creative spine registered")

            resolved_sequence_id = sequence_id
            if not resolved_sequence_id and scene_id and structure:
                scene_idx = self._extract_scene_index(scene_id)
                if scene_idx is not None:
                    for seq in getattr(structure, "all_sequences", []) or []:
                        scene_ids = getattr(seq, "scenes", []) or []
                        if scene_id in scene_ids:
                            resolved_sequence_id = getattr(seq, "sequence_id", None)
                            break
                        start_idx = getattr(seq, "start_scene_index", None)
                        end_idx = getattr(seq, "end_scene_index", None)
                        if (
                            resolved_sequence_id is None
                            and start_idx is not None
                            and end_idx is not None
                            and start_idx <= scene_idx <= end_idx
                        ):
                            resolved_sequence_id = getattr(seq, "sequence_id", None)
                            break

            resolved_act_number = act_number
            if resolved_act_number is None and scene_id and structure:
                scene_idx = self._extract_scene_index(scene_id)
                if scene_idx is not None:
                    for act in getattr(structure, "acts", []) or []:
                        start_idx = getattr(act, "start_scene_index", None)
                        end_idx = getattr(act, "end_scene_index", None)
                        if (
                            start_idx is not None
                            and end_idx is not None
                            and start_idx <= scene_idx <= end_idx
                        ):
                            resolved_act_number = getattr(act, "act_number", None)
                            break

            film_summary = film_intelligence_service.analyze_film(
                film_id=film_id,
                film_structure=structure,
                film_memory=memory,
                creative_spine=spine,
            )
            result["derived"]["film"] = self._film_intelligence_to_dict(film_summary)
            result["available"] = True

            if resolved_act_number is not None:
                act_summary = film_intelligence_service.analyze_act(
                    film_id=film_id,
                    act_number=resolved_act_number,
                    film_structure=structure,
                    film_memory=memory,
                    creative_spine=spine,
                )
                result["derived"]["act"] = self._film_intelligence_to_dict(act_summary)
                result["derived"]["scope"] = "act"
                result["act_number"] = resolved_act_number

            if resolved_sequence_id:
                sequence_summary = film_intelligence_service.analyze_sequence(
                    film_id=film_id,
                    sequence_id=resolved_sequence_id,
                    film_structure=structure,
                    film_memory=memory,
                    creative_spine=spine,
                )
                result["derived"]["sequence"] = self._film_intelligence_to_dict(sequence_summary)
                result["derived"]["scope"] = "sequence"
                result["sequence_id"] = resolved_sequence_id

            active_summary = (
                result["derived"]["sequence"]
                or result["derived"]["act"]
                or result["derived"]["film"]
                or {}
            )
            result["derived"]["debt_payoff_arc_summary"] = {
                "setup_payoff_count": len(active_summary.get("setup_payoff_summaries", []) or []),
                "open_tension_count": len(active_summary.get("tension_summaries", []) or []),
                "motif_count": len(active_summary.get("motif_summaries", []) or []),
                "arc_count": len(active_summary.get("arc_progression_summaries", []) or []),
            }
            return result
        except Exception as exc:
            result["notes"].append(f"Film intelligence unavailable: {str(exc)}")
            return result

    def get_scene_package_context(
        self,
        film_id: str,
        scene_data: Optional[Dict[str, Any]] = None,
        scene_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get read-only scene production package context.

        This exposes the canonical SceneProductionPackage built from available
        scene input, film brain context, and derived guidance. It is explicitly
        read-only and advisory - it does not mutate any runtime state.

        Args:
            film_id: Film identifier
            scene_data: Optional scene input dictionary
            scene_id: Optional scene ID (used if not in scene_data)

        Returns:
            Dict with:
            - film_id: Film identifier
            - scene_id: Scene identifier
            - timestamp: When package was generated
            - available: Whether package was successfully built
            - canonical: The SceneProductionPackage with grounded fields
            - derived: Derived guidance (film_intelligence, cinematic_language, taste)
            - provenance: Source tracking for each field
            - summary: Compact view of key canonical fields
            - notes: Any warnings or notes about missing data
        """
        result: Dict[str, Any] = {
            "film_id": film_id,
            "scene_id": scene_id or (scene_data.get("scene_id") if isinstance(scene_data, dict) else None),
            "timestamp": datetime.utcnow().isoformat(),
            "available": False,
            "canonical": {},
            "derived": {},
            "provenance": {},
            "summary": {},
            "notes": [],
        }

        try:
            # Resolve safe scene_data
            safe_scene_data: Optional[Dict[str, Any]] = None
            if isinstance(scene_data, dict):
                safe_scene_data = scene_data
            elif scene_id:
                safe_scene_data = {"scene_id": scene_id, "film_id": film_id}

            # Get registered context
            structure = self._structures.get(film_id)
            memory = self._memories.get(film_id)
            spine = self._spine_service.get_spine(film_id)

            result["provenance"] = {
                "structure_available": structure is not None,
                "memory_available": memory is not None,
                "spine_available": spine is not None,
            }

            # Build the package
            package = self._scene_package_service.build_scene_package(
                scene_data=safe_scene_data,
                creative_spine=spine,
                film_memory=memory,
                film_structure=structure,
            )

            # Extract canonical fields
            result["canonical"] = {
                "scene_id": package.scene_id,
                "film_id": package.film_id,
                "narrative_purpose": package.narrative_purpose,
                "emotional_target": package.emotional_target,
                "visual_target": package.visual_target,
                "motif_obligations": list(package.motif_obligations),
                "continuity_constraints": list(package.continuity_constraints),
                "restraint_rules": list(package.restraint_rules),
                "forbidden_moves": list(package.forbidden_moves),
                "provider_neutral_execution_brief": package.provider_neutral_execution_brief,
            }

            # Extract derived guidance (clearly marked as non-canonical)
            result["derived"] = {
                "film_intelligence": dict(package.derived_guidance.film_intelligence),
                "cinematic_language": dict(package.derived_guidance.cinematic_language),
                "taste_guidance": dict(package.derived_guidance.taste_guidance),
                "_note": "Derived guidance is advisory only, never canonical",
            }

            # Extract provenance tracking
            result["provenance"] = {
                "canonical_sources": dict(package.provenance.canonical_sources),
                "derived_sources": dict(package.provenance.derived_sources),
                "grounded_fields": list(package.provenance.grounded_fields),
                "derived_fields": list(package.provenance.derived_fields),
                "advisory_fields": list(package.provenance.advisory_fields),
                "notes": list(package.provenance.notes),
            }

            # Build compact summary
            result["summary"] = {
                "narrative_purpose": package.narrative_purpose,
                "emotional_target": package.emotional_target,
                "visual_target": package.visual_target,
                "motif_obligations": package.motif_obligations[:3] if package.motif_obligations else [],
                "continuity_constraints": package.continuity_constraints[:3] if package.continuity_constraints else [],
                "restraint_rules": package.restraint_rules[:3] if package.restraint_rules else [],
                "_note": "Summary shows up to 3 items per list field",
            }

            result["available"] = True

            # Add notes about sparse context
            if not safe_scene_data:
                result["notes"].append("No scene input provided; using conservative defaults")
            if not memory:
                result["notes"].append("No film memory registered; motif and restraint coverage may be sparse")
            if not structure:
                result["notes"].append("No film structure registered; act/sequence continuity cues may be sparse")

            return result

        except Exception as exc:
            result["notes"].append(f"Scene package unavailable: {str(exc)}")
            result["available"] = False
            return result
    
    # =========================================================================
    # Constraint Consumption (delegates to SpineService)
    # =========================================================================
    
    def get_constraints_for_role(
        self,
        film_id: str,
        role: AgentRole
    ) -> Dict[str, Any]:
        """
        Get spine constraints relevant to a specific role.
        
        This delegates to SpineService.get_constraints_for_role() which
        handles role-based filtering of immutable/revisable constraints.
        
        Args:
            film_id: Film identifier
            role: Agent role requesting constraints
            
        Returns:
            Dict with constraint categories:
            - immutable: Constraints that cannot be violated
            - revisable: Constraints that can evolve
            - restraint_rules: Explicit "do not do" rules
            - genre_conventions: Genre-specific requirements
        """
        return self._spine_service.get_constraints_for_role(film_id, role)
    
    def get_constraint_for_field(
        self,
        film_id: str,
        field_name: str
    ) -> Optional[SpineConstraint]:
        """
        Get constraint details for a specific field.
        
        Args:
            film_id: Film identifier
            field_name: Field name (e.g., "visual_philosophy", "pacing_philosophy")
            
        Returns:
            SpineConstraint if found, None otherwise
        """
        spine = self._spine_service.get_spine(film_id)
        if not spine:
            return None
        return spine.get_constraint_for_field(field_name)
    
    # =========================================================================
    # Structure Context
    # =========================================================================
    
    def get_structure_context(
        self,
        film_id: str,
        scene_id: Optional[str] = None,
        act_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get film structure context relevant to a scene or act.
        
        Args:
            film_id: Film identifier
            scene_id: Optional scene ID to get context for
            act_number: Optional act number to get context for
            
        Returns:
            Dict with structure context:
            - film_id: Film identifier
            - scene_id: Scene context was requested for
            - act_number: Act context
            - current_act: Act data if found
            - current_sequence: Sequence data if found
            - beats: Beats relevant to the context
            - available: Whether structure was found
            - notes: Any notes or warnings
        """
        result = {
            "film_id": film_id,
            "scene_id": scene_id,
            "act_number": act_number,
            "current_act": None,
            "current_sequence": None,
            "beats": [],
            "available": False,
            "notes": []
        }
        
        structure = self._structures.get(film_id)
        if not structure:
            result["notes"].append("No film structure registered")
            return result
        
        result["available"] = True
        
        # Get act context
        if act_number:
            act = self._structure_service.get_act(structure, act_number)
            if act:
                result["current_act"] = self._act_to_dict(act)
        elif scene_id:
            # Try to determine act from scene_id
            scene_idx = self._extract_scene_index(scene_id)
            if scene_idx is not None:
                for num in [1, 2, 3]:
                    act = self._structure_service.get_act(structure, num)
                    if act and hasattr(act, 'start_scene_index') and hasattr(act, 'end_scene_index'):
                        if act.start_scene_index <= scene_idx <= act.end_scene_index:
                            result["current_act"] = self._act_to_dict(act)
                            result["act_number"] = num
                            break
        
        # Get sequence context
        if scene_id:
            scene_idx = self._extract_scene_index(scene_id)
            if scene_idx is not None:
                for seq in self._structure_service.get_all_sequences(structure):
                    if hasattr(seq, 'scene_ids') and seq.scene_ids:
                        indices = self._parse_scene_indices(seq.scene_ids)
                        if scene_idx in indices:
                            result["current_sequence"] = self._sequence_to_dict(seq)
                            break
        
        # Get beats
        if result["current_act"] or result["current_sequence"]:
            beats = self._structure_service.get_all_beats(structure)
            # Filter beats relevant to context
            result["beats"] = [self._beat_to_dict(b) for b in beats[:10]]  # Limit to first 10
        
        return result
    
    def _act_to_dict(self, act: Act) -> Dict[str, Any]:
        """Convert Act to dict safely."""
        if hasattr(act, 'to_dict'):
            return act.to_dict()
        return {
            "act_number": getattr(act, 'act_number', None),
            "act_type": getattr(act, 'act_type', None),
            "scene_start": getattr(act, 'scene_start', None),
            "scene_end": getattr(act, 'scene_end', None),
        }
    
    def _sequence_to_dict(self, seq: Sequence) -> Dict[str, Any]:
        """Convert Sequence to dict safely."""
        if hasattr(seq, 'to_dict'):
            return seq.to_dict()
        return {
            "sequence_id": getattr(seq, 'sequence_id', None),
            "sequence_name": getattr(seq, 'sequence_name', None),
            "scene_ids": getattr(seq, 'scene_ids', []),
        }
    
    def _beat_to_dict(self, beat: Beat) -> Dict[str, Any]:
        """Convert Beat to dict safely."""
        if hasattr(beat, 'to_dict'):
            return beat.to_dict()
        return {
            "beat_id": getattr(beat, 'beat_id', None),
            "beat_type": getattr(beat, 'beat_type', None),
            "description": getattr(beat, 'description', None),
        }
    
    def _extract_scene_index(self, scene_id: str) -> Optional[int]:
        """Extract numeric index from scene_id like 'scene_45' -> 45."""
        try:
            if scene_id.startswith("scene_"):
                return int(scene_id.split("_")[1])
            return None
        except (ValueError, IndexError):
            return None
    
    def _parse_scene_indices(self, scene_ids: List[str]) -> List[int]:
        """Parse list of scene_ids to indices."""
        indices = []
        for sid in scene_ids:
            idx = self._extract_scene_index(sid)
            if idx is not None:
                indices.append(idx)
        return indices

    def _film_intelligence_to_dict(self, summary: Any) -> Dict[str, Any]:
        """Convert a derived film-intelligence model into a plain dict safely."""
        if summary is None:
            return {}
        if hasattr(summary, "model_dump"):
            return summary.model_dump()
        if isinstance(summary, dict):
            return summary
        return {}
    
    # =========================================================================
    # Memory Context
    # =========================================================================
    
    def get_memory_context(
        self,
        film_id: str,
        role: AgentRole,
        scene_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get film memory context relevant to a role and optional scene.
        
        Args:
            film_id: Film identifier
            role: Agent role requesting memory
            scene_id: Optional scene ID for scene-specific memory
            
        Returns:
            Dict with memory context appropriate to role:
            - film_id: Film identifier
            - role: Role context was requested for
            - scene_id: Scene context if provided
            - motifs: List of motif records
            - tensions: List of unresolved tensions
            - emotional_trajectory: Emotional arc points
            - role_specific: Role-appropriate subset
            - available: Whether memory was found
            - notes: Any notes or warnings
        """
        result = {
            "film_id": film_id,
            "role": role.value,
            "scene_id": scene_id,
            "motifs": [],
            "tensions": [],
            "emotional_trajectory": [],
            "role_specific": {},
            "available": False,
            "notes": []
        }
        
        memory = self._memories.get(film_id)
        if not memory:
            result["notes"].append("No film memory registered")
            return result
        
        result["available"] = True
        
        # Get motifs
        try:
            motifs = self._structure_service.get_motifs(memory)
            result["motifs"] = [self._motif_to_dict(m) for m in motifs]
        except Exception as e:
            result["notes"].append(f"Error loading motifs: {str(e)}")
        
        # Get unresolved tensions
        try:
            tensions = self._structure_service.get_unresolved_tensions(memory)
            result["tensions"] = [self._tension_to_dict(t) for t in tensions]
        except Exception as e:
            result["notes"].append(f"Error loading tensions: {str(e)}")
        
        # Get emotional trajectory
        try:
            trajectory = self._structure_service.get_emotional_trajectory(memory)
            result["emotional_trajectory"] = [self._trajectory_to_dict(t) for t in trajectory]
        except Exception as e:
            result["notes"].append(f"Error loading trajectory: {str(e)}")
        
        # Role-specific memory subset
        result["role_specific"] = self._get_role_specific_memory(role, memory)
        
        return result
    
    def _motif_to_dict(self, motif) -> Dict[str, Any]:
        """Convert MotifRecord to dict safely."""
        if hasattr(motif, 'to_dict'):
            return motif.to_dict()
        return {
            "motif_id": getattr(motif, 'motif_id', None),
            "type": getattr(motif, 'type', None),
            "description": getattr(motif, 'description', None),
        }
    
    def _tension_to_dict(self, tension) -> Dict[str, Any]:
        """Convert UnresolvedTension to dict safely."""
        if hasattr(tension, 'to_dict'):
            return tension.to_dict()
        return {
            "tension_id": getattr(tension, 'tension_id', None),
            "type": getattr(tension, 'type', None),
            "description": getattr(tension, 'description', None),
        }
    
    def _trajectory_to_dict(self, point) -> Dict[str, Any]:
        """Convert EmotionalTrajectoryPoint to dict safely."""
        if hasattr(point, 'to_dict'):
            return point.to_dict()
        return {
            "act": getattr(point, 'act', None),
            "emotional_state": getattr(point, 'emotional_state', None),
            "intensity": getattr(point, 'intensity', None),
        }
    
    def _get_role_specific_memory(
        self,
        role: AgentRole,
        memory: FilmLevelMemory
    ) -> Dict[str, Any]:
        """Get role-appropriate subset of memory."""
        role_memory = {
            "story_thesis": getattr(memory, 'story_thesis', None),
            "genre_lane": getattr(memory, 'genre_lane', None),
        }
        
        if role == AgentRole.DIRECTOR:
            role_memory["emotional_contract"] = getattr(memory, 'emotional_contract', None)
            role_memory["visual_philosophy"] = getattr(memory, 'visual_philosophy', None)
            role_memory["pacing_philosophy"] = getattr(memory, 'pacing_philosophy', None)
            
        elif role == AgentRole.CINEMATOGRAPHER:
            role_memory["visual_philosophy"] = getattr(memory, 'visual_philosophy', None)
            
        elif role == AgentRole.EDITOR:
            role_memory["pacing_philosophy"] = getattr(memory, 'pacing_philosophy', None)
            role_memory["emotional_trajectory"] = getattr(memory, 'emotional_trajectory', [])
            
        elif role == AgentRole.CONTINUITY_SUPERVISOR:
            role_memory["motifs"] = getattr(memory, 'motifs', [])
            role_memory["unresolved_tensions"] = getattr(memory, 'unresolved_tensions', [])
            
        elif role == AgentRole.SCRIPT_ANALYST:
            role_memory["emotional_contract"] = getattr(memory, 'emotional_contract', None)
            role_memory["unresolved_tensions"] = getattr(memory, 'unresolved_tensions', [])
            
        return role_memory
    
    # =========================================================================
    # Full Context Aggregation
    # =========================================================================
    
    def get_context_for_role(
        self,
        film_id: str,
        role: AgentRole,
        scene_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get complete context for an agent role working on a scene.
        
        This is the primary method agents should use to get their
        full working context. It combines:
        - Spine constraints (role-filtered)
        - Film structure (scene-relevant)
        - Film memory (role-appropriate)
        
        Args:
            film_id: Film identifier
            role: Agent role
            scene_id: Optional scene ID
            
        Returns:
            Dict with complete context:
            - film_id: Film identifier
            - role: Role context is for
            - scene_id: Scene being worked on
            - timestamp: When context was generated
            - constraints: Role-filtered spine constraints
            - structure: Film structure context
            - memory: Film memory context
        """
        return {
            "film_id": film_id,
            "role": role.value,
            "scene_id": scene_id,
            "timestamp": datetime.utcnow().isoformat(),
            "constraints": self.get_constraints_for_role(film_id, role),
            "structure": self.get_structure_context(film_id, scene_id=scene_id),
            "memory": self.get_memory_context(film_id, role, scene_id),
        }

    def get_continuity_context(
        self,
        film_id: str,
        scene_id: Optional[str] = None,
        act_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get continuity context for MemoryArchivistEvaluator.

        This method provides the combined context needed for continuity analysis:
        - Spine constraints (relevant to continuity)
        - Film structure context (acts, sequences, beats)
        - Film memory context (motifs, tensions, emotional trajectory)
        - Nearby scene/sequence context (for scene-level continuity)

        Args:
            film_id: Film identifier
            scene_id: Optional scene ID for scene-specific continuity context
            act_number: Optional act number for act-level continuity context

        Returns:
            Dict with continuity context:
            - film_id: Film identifier
            - scene_id: Scene context was requested for (if provided)
            - act_number: Act context (if provided)
            - timestamp: When context was generated
            - spine: Spine constraints relevant to continuity
            - structure: Film structure context
            - memory: Film memory context (motifs, tensions, trajectory)
            - nearby_scenes: Context about nearby scenes for scene-level continuity
            - available: Whether all components were available
            - notes: Any notes or warnings about missing data
        """
        result = {
            "film_id": film_id,
            "scene_id": scene_id,
            "act_number": act_number,
            "timestamp": datetime.utcnow().isoformat(),
            "spine": {},
            "structure": {},
            "memory": {},
            "nearby_scenes": [],
            "available": False,
            "notes": []
        }

        # Track availability
        has_spine = False
        has_structure = False
        has_memory = False

        # Get spine constraints for continuity analysis
        try:
            spine = self._spine_service.get_spine(film_id)
            if spine:
                has_spine = True
                # Get constraints relevant to continuity (character, theme, tone)
                result["spine"] = {
                    "frozen_fields": spine.frozen_fields,
                    "revisable_fields": spine.revisable_fields,
                    "constraint_weights": spine.constraint_weights,
                    "summary": spine.get_summary() if hasattr(spine, 'get_summary') else {}
                }
            else:
                result["notes"].append("No spine available")
        except Exception as e:
            result["notes"].append(f"Error loading spine: {str(e)}")

        # Get structure context
        try:
            structure_context = self.get_structure_context(film_id, scene_id, act_number)
            if structure_context.get("available"):
                has_structure = True
                result["structure"] = structure_context
            else:
                result["notes"].append("No structure available")
        except Exception as e:
            result["notes"].append(f"Error loading structure: {str(e)}")

        # Get memory context for continuity
        try:
            memory_context = self.get_memory_context(
                film_id,
                AgentRole.CONTINUITY_SUPERVISOR,  # MemoryArchivist uses continuity supervisor context
                scene_id
            )
            if memory_context.get("available"):
                has_memory = True
                result["memory"] = memory_context
            else:
                result["notes"].append("No memory available")
        except Exception as e:
            result["notes"].append(f"Error loading memory: {str(e)}")

        # Get nearby scenes context for scene-level continuity
        if scene_id and has_structure:
            result["nearby_scenes"] = self._get_nearby_scenes_context(film_id, scene_id)

        # Set overall availability
        result["available"] = has_spine or has_structure or has_memory

        return result

    def _get_nearby_scenes_context(
        self,
        film_id: str,
        scene_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get context about nearby scenes for continuity analysis.

        Args:
            film_id: Film identifier
            scene_id: Reference scene ID

        Returns:
            List of nearby scene contexts (previous and next scenes)
        """
        nearby = []
        scene_idx = self._extract_scene_index(scene_id)

        if scene_idx is None:
            return nearby

        structure = self._structures.get(film_id)
        if not structure:
            return nearby

        # Get scenes before and after (up to 3 each direction)
        for offset in range(-3, 4):
            if offset == 0:
                continue  # Skip the reference scene itself

            target_idx = scene_idx + offset
            target_scene_id = f"scene_{target_idx}"

            # Check if this scene exists in any sequence
            for seq in self._structure_service.get_all_sequences(structure):
                if hasattr(seq, 'scene_ids') and seq.scene_ids:
                    indices = self._parse_scene_indices(seq.scene_ids)
                    if target_idx in indices:
                        nearby.append({
                            "scene_id": target_scene_id,
                            "scene_index": target_idx,
                            "sequence_id": getattr(seq, 'sequence_id', None),
                            "relative_position": "before" if offset < 0 else "after",
                            "distance": abs(offset)
                        })
                        break

        # Sort by distance
        nearby.sort(key=lambda x: x["distance"])

        return nearby[:6]  # Limit to 6 nearby scenes

    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def is_spine_available(self, film_id: str) -> bool:
        """Check if spine exists for film."""
        return self._spine_service.get_spine(film_id) is not None
    
    def is_structure_available(self, film_id: str) -> bool:
        """Check if film structure is registered."""
        return film_id in self._structures
    
    def is_memory_available(self, film_id: str) -> bool:
        """Check if film memory is registered."""
        return film_id in self._memories
    
    def get_availability_summary(self, film_id: str) -> Dict[str, bool]:
        """Get summary of what's available for a film."""
        return {
            "spine": self.is_spine_available(film_id),
            "structure": self.is_structure_available(film_id),
            "memory": self.is_memory_available(film_id),
        }
    
    def clear_film(self, film_id: str) -> None:
        """Clear all registered data for a film."""
        if film_id in self._structures:
            del self._structures[film_id]
        if film_id in self._memories:
            del self._memories[film_id]
        # Note: We don't clear spine service data as it may be shared


# Global instance for convenience
spine_consumption_service = SpineConsumptionService()

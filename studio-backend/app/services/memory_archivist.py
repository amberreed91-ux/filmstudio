"""
Memory Archivist - Phase 3.4

Long-form continuity protection service.
Monitors narrative threads across the film lifecycle and ensures proper payoff.

This is a READ-ONLY service - it does NOT modify FilmLevelMemory or any persistent state.
It derives continuity analysis from existing structure and memory only.

Key Responsibilities:
1. Track tension resolution health
2. Monitor motif callback schedules
3. Maintain character state history
4. Verify act transition continuity
5. Identify missing payoffs

Integration:
- Does NOT override Director decisions
- Does NOT block execution
- Returns structured continuity reports only
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger("studio-memory-archivist")


class AlertSeverity(str, Enum):
    """Severity levels for continuity alerts"""
    CRITICAL = "critical"  # Must be addressed before proceeding
    WARNING = "warning"    # Should be addressed
    INFO = "info"          # FYI only


class AlertType(str, Enum):
    """Types of continuity alerts"""
    TENSION_OVERDUE = "tension_overdue"
    MOTIF_MISSED = "motif_missed"
    CHARACTER_INCONSISTENT = "character_inconsistent"
    PAYOFF_MISSING = "payoff_missing"
    ACT_TRANSITION_BROKEN = "act_transition_broken"
    EMOTIONAL_CONTRACT_VIOLATION = "emotional_contract_violation"


@dataclass
class ContinuityAlert:
    """A single continuity issue that needs attention"""
    alert_type: AlertType
    severity: AlertSeverity
    description: str
    affected_elements: List[str] = field(default_factory=list)
    recommended_action: str = ""


@dataclass
class TensionHealth:
    """Health status of a dramatic tension"""
    tension_id: str
    description: str
    introduced_scene: str
    expected_resolution_act: int
    actual_resolution_scene: Optional[str] = None
    is_overdue: bool = False
    is_resolved: bool = False
    health_score: float = 1.0  # 0.0 - 1.0


@dataclass
class MotifCallbackStatus:
    """Status of a motif callback"""
    motif_id: str
    motif_name: str
    motif_type: str
    last_seen_scene: Optional[str] = None
    expected_callback_scene: Optional[str] = None
    actual_callback_scene: Optional[str] = None
    is_fulfilled: bool = False
    is_overdue: bool = False
    callback_count: int = 0


@dataclass
class CharacterState:
    """Character state at a point in time"""
    character_id: str
    character_name: str
    scene_id: str
    emotional_state: str = ""
    physical_state: str = ""
    key_actions: List[str] = field(default_factory=list)


@dataclass
class CharacterConsistencyIssue:
    """An inconsistency in character state across scenes"""
    character_id: str
    character_name: str
    previous_scene: str
    current_scene: str
    previous_state: str
    current_state: str
    issue_description: str


@dataclass
class SceneContinuityReport:
    """Continuity report for a specific scene"""
    scene_id: str
    film_id: str
    passed: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    alerts: List[ContinuityAlert] = field(default_factory=list)
    tension_updates: List[str] = field(default_factory=list)  # tensions introduced/resolved
    motif_references: List[str] = field(default_factory=list)
    character_states: Dict[str, str] = field(default_factory=dict)  # character_id -> state
    missing_payoffs: List[str] = field(default_factory=list)
    inconsistent_states: List[CharacterConsistencyIssue] = field(default_factory=list)
    debug_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContinuityHealthReport:
    """Comprehensive continuity health report for entire film"""
    film_id: str
    overall_health: float = 1.0  # 0.0 - 1.0
    tension_health: float = 1.0
    motif_health: float = 1.0
    character_health: float = 1.0
    act_transition_health: float = 1.0
    alerts: List[ContinuityAlert] = field(default_factory=list)
    tension_statuses: List[TensionHealth] = field(default_factory=list)
    motif_statuses: List[MotifCallbackStatus] = field(default_factory=list)
    character_states: List[CharacterState] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    debug_metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryArchivistEvaluator:
    """
    Evaluates continuity health for films and scenes.
    
    This is a READ-ONLY service that analyzes existing FilmLevelMemory
    and FilmStructure to provide continuity insights.
    
    It does NOT:
    - Modify any persistent state
    - Override Director decisions
    - Block execution
    
    It DOES:
    - Return structured continuity reports
    - Identify issues and warnings
    - Track tension and motif health
    - Detect character state inconsistencies
    """

    # Thresholds
    TENSION_OVERDUE_THRESHOLD = 0.2  # Tension is overdue if past expected act and < 20% scenes remain
    MOTIF_CALLBACK_EXPECTED_ACTS = [2, 3]  # Motifs should callback in acts 2 and 3
    CHARACTER_STATE_CONSISTENCY_THRESHOLD = 0.7  # Character states should be consistent

    def __init__(self):
        """Initialize the Memory Archivist evaluator."""
        # Internal state tracking (not persisted)
        self._character_states: Dict[str, List[CharacterState]] = {}
        self._motif_tracking: Dict[str, Dict[str, Any]] = {}

    def evaluate_film_continuity(
        self,
        film_id: str,
        spine: Optional[Dict[str, Any]] = None,
        structure: Optional[Dict[str, Any]] = None,
        memory: Optional[Dict[str, Any]] = None,
        film_intelligence: Optional[Dict[str, Any]] = None,
    ) -> ContinuityHealthReport:
        """
        Evaluate overall continuity health for a film.

        Args:
            film_id: Film identifier
            spine: Spine context from SpineConsumptionService
            structure: Film structure context from SpineConsumptionService
            memory: Film memory context from SpineConsumptionService

        Returns:
            ContinuityHealthReport with overall film continuity assessment
        """
        report = ContinuityHealthReport(film_id=film_id)

        # Handle empty/partial inputs safely
        if not memory or not memory.get("available"):
            report.alerts.append(ContinuityAlert(
                alert_type=AlertType.TENSION_OVERDUE,
                severity=AlertSeverity.INFO,
                description="No film memory available for continuity analysis",
                recommended_action="Continue with limited continuity tracking"
            ))
            return report

        # Check tension health
        report.tension_statuses = self._check_tension_health(memory, structure)
        report.tension_health = self._calculate_tension_health(report.tension_statuses)

        # Check motif callbacks
        report.motif_statuses = self._check_motif_callbacks(memory, structure)
        report.motif_health = self._calculate_motif_health(report.motif_statuses)

        # Track character states from memory
        report.character_states = self._extract_character_states(memory)

        # Calculate overall health
        report.overall_health = (
            report.tension_health * 0.35 +
            report.motif_health * 0.25 +
            report.character_health * 0.25 +
            report.act_transition_health * 0.15
        )

        # Generate alerts and recommendations
        self._populate_alerts_and_recommendations(report, structure)
        self._apply_film_intelligence_to_film_report(report, film_intelligence)

        return report

    def evaluate_scene_continuity(
        self,
        scene_id: str,
        scene_data: Dict[str, Any],
        spine: Optional[Dict[str, Any]] = None,
        structure: Optional[Dict[str, Any]] = None,
        memory: Optional[Dict[str, Any]] = None,
        film_intelligence: Optional[Dict[str, Any]] = None,
    ) -> SceneContinuityReport:
        """
        Evaluate continuity for a specific scene.

        Args:
            scene_id: Scene identifier
            scene_data: Scene data to evaluate
            spine: Spine context from SpineConsumptionService
            structure: Film structure context from SpineConsumptionService
            memory: Film memory context from SpineConsumptionService

        Returns:
            SceneContinuityReport for the specific scene
        """
        film_id = scene_data.get("film_id", "unknown")
        report = SceneContinuityReport(
            scene_id=scene_id,
            film_id=film_id,
            passed=True  # Will be set to False if issues found
        )

        # Handle empty inputs
        if not scene_data:
            report.passed = False
            report.issues.append("No scene data provided")
            return report

        # Extract character states from scene
        character_appearances = scene_data.get("character_appearances", [])
        for char_id in character_appearances:
            emotional_state = scene_data.get(f"{char_id}_emotional_state", "")
            physical_state = scene_data.get(f"{char_id}_physical_state", "")
            report.character_states[char_id] = emotional_state or "unknown"

            # Track for consistency checking
            self._track_character_state(char_id, scene_id, emotional_state, physical_state, scene_data.get("actions", []))

        # Check for tension updates in this scene
        report.tension_updates = self._check_tension_updates(scene_id, scene_data, memory)

        # Check for motif references in this scene
        report.motif_references = self._check_motif_references(scene_id, scene_data, memory)

        # Check for missing payoffs
        report.missing_payoffs = self._check_missing_payoffs(scene_id, memory, structure)

        # Check character consistency
        report.inconsistent_states = self._check_character_consistency(
            scene_id, character_appearances, memory
        )
        if report.inconsistent_states:
            report.passed = False
            for issue in report.inconsistent_states:
                report.issues.append(issue.issue_description)

        # Populate warnings
        self._populate_scene_warnings(report, scene_data, memory, film_intelligence)

        return report

    def _check_tension_health(
        self,
        memory: Dict[str, Any],
        structure: Optional[Dict[str, Any]] = None,
    ) -> List[TensionHealth]:
        """Check health of all unresolved tensions."""
        tensions = []

        # Get current act from structure
        current_act = 1
        if structure and structure.get("current_act"):
            current_act = structure["current_act"].get("act_number", 1)

        # Get total acts
        total_acts = 3  # Default
        if structure and structure.get("available"):
            # Could derive from structure if available
            pass

        # Get unresolved tensions from memory
        unresolved_tensions = memory.get("unresolved_tensions", [])
        if not isinstance(unresolved_tensions, list):
            unresolved_tensions = []

        for tension in unresolved_tensions:
            if isinstance(tension, dict):
                tension_health = TensionHealth(
                    tension_id=tension.get("tension_id", "unknown"),
                    description=tension.get("description", ""),
                    introduced_scene=tension.get("introduced_scene", ""),
                    expected_resolution_act=tension.get("expected_resolution_act", 0),
                )

                # Check if resolved (has resolution scene)
                if tension.get("resolution_scene"):
                    tension_health.is_resolved = True
                    tension_health.actual_resolution_scene = tension["resolution_scene"]
                # Check if overdue
                elif tension_health.expected_resolution_act > 0:
                    if current_act > tension_health.expected_resolution_act:
                        tension_health.is_overdue = True
                        tension_health.health_score = 0.0
                    elif current_act == tension_health.expected_resolution_act:
                        tension_health.health_score = 0.5

                tensions.append(tension_health)
            elif hasattr(tension, 'tension_id'):  # Pydantic model
                tensions.append(TensionHealth(
                    tension_id=tension.tension_id,
                    description=tension.description,
                    introduced_scene=tension.introduced_scene,
                    expected_resolution_act=tension.expected_resolution_act,
                ))

        return tensions

    def _check_motif_callbacks(
        self,
        memory: Dict[str, Any],
        structure: Optional[Dict[str, Any]] = None,
    ) -> List[MotifCallbackStatus]:
        """Check if motifs are being called back appropriately."""
        motif_statuses = []

        # Get current scene/act from structure
        current_scene = 0
        current_act = 1
        if structure and structure.get("available"):
            current_scene = structure.get("scene_id", "scene_0")
            if structure.get("current_act"):
                current_act = structure["current_act"].get("act_number", 1)

        # Get motifs from memory
        motifs = memory.get("motifs", [])
        if not isinstance(motifs, list):
            motifs = []

        for motif in motifs:
            if isinstance(motif, dict):
                motif_status = MotifCallbackStatus(
                    motif_id=motif.get("motif_id", "unknown"),
                    motif_name=motif.get("name", motif.get("motif_id", "unknown")),
                    motif_type=motif.get("motif_type", "visual"),
                    last_seen_scene=motif.get("firstAppearance", motif.get("last_seen_scene")),
                )
                # Check for callback scene (the motif reappeared)
                callback_scene = motif.get("callbackScene", motif.get("last_seen_scene"))
                if callback_scene and callback_scene != motif_status.last_seen_scene:
                    motif_status.actual_callback_scene = callback_scene
                    motif_status.is_fulfilled = True
                    motif_status.callback_count = 1
            elif hasattr(motif, 'motif_id'):  # Pydantic model
                motif_status = MotifCallbackStatus(
                    motif_id=motif.motif_id,
                    motif_name=getattr(motif, 'name', motif.motif_id),
                    motif_type=getattr(motif, 'motif_type', 'visual'),
                    last_seen_scene=getattr(motif, 'firstAppearance', None),
                )
                # Check for callback scene
                callback_scene = getattr(motif, 'callbackScene', getattr(motif, 'last_seen_scene', None))
                if callback_scene and callback_scene != motif_status.last_seen_scene:
                    motif_status.actual_callback_scene = callback_scene
                    motif_status.is_fulfilled = True
                    motif_status.callback_count = 1
            else:
                continue
    
            # Check if callback is expected (in acts 2 or 3) but not yet fulfilled
            if current_act in self.MOTIF_CALLBACK_EXPECTED_ACTS:
                if motif_status.callback_count == 0:
                    motif_status.is_overdue = True
    
            motif_statuses.append(motif_status)

        return motif_statuses

    def _track_character_state(
        self,
        character_id: str,
        scene_id: str,
        emotional_state: str,
        physical_state: str,
        actions: Any,
    ) -> None:
        """
        Track character state across scenes.
        
        This is internal tracking only - not persisted.
        """
        if character_id not in self._character_states:
            self._character_states[character_id] = []

        state = CharacterState(
            character_id=character_id,
            character_name=character_id,  # Would be resolved from memory
            scene_id=scene_id,
            emotional_state=emotional_state,
            physical_state=physical_state,
            key_actions=actions if isinstance(actions, list) else [],
        )

        self._character_states[character_id].append(state)

    def _extract_character_states(
        self,
        memory: Dict[str, Any],
    ) -> List[CharacterState]:
        """Extract character states from film memory."""
        states = []

        # Get characters from memory
        characters = memory.get("characters", {})
        if not isinstance(characters, dict):
            characters = {}

        for char_id, char_data in characters.items():
            if isinstance(char_data, dict):
                # Extract latest known state
                emotional = char_data.get("last_emotional_state", "")
                physical = char_data.get("last_physical_state", "")
                last_scene = char_data.get("last_scene_id", "")

                states.append(CharacterState(
                    character_id=char_id,
                    character_name=char_data.get("name", char_id),
                    scene_id=last_scene,
                    emotional_state=emotional,
                    physical_state=physical,
                ))
            elif hasattr(char_data, 'character_id'):  # Pydantic model
                states.append(CharacterState(
                    character_id=char_data.character_id,
                    character_name=getattr(char_data, 'name', char_id),
                    scene_id=getattr(char_data, 'last_scene_id', ''),
                    emotional_state=getattr(char_data, 'last_emotional_state', ''),
                    physical_state=getattr(char_data, 'last_physical_state', ''),
                ))

        return states

    def _check_tension_updates(
        self,
        scene_id: str,
        scene_data: Dict[str, Any],
        memory: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Check if this scene introduces or resolves tensions."""
        updates = []

        # Check if scene introduces new tension
        new_tensions = scene_data.get("new_tensions", [])
        if new_tensions:
            for tension in new_tensions:
                updates.append(f"Introduced tension: {tension}")

        # Check if scene resolves tension
        resolved_tensions = scene_data.get("resolved_tensions", [])
        if resolved_tensions:
            for tension in resolved_tensions:
                updates.append(f"Resolved tension: {tension}")

        return updates

    def _check_motif_references(
        self,
        scene_id: str,
        scene_data: Dict[str, Any],
        memory: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Check if this scene references any motifs."""
        references = []

        # Check scene data for motif references
        visual_desc = scene_data.get("visual_description", "").lower()
        dialogue = scene_data.get("dialogue", "").lower()

        # Get motifs from memory
        if memory:
            motifs = memory.get("motifs", [])
            if isinstance(motifs, list):
                for motif in motifs:
                    motif_name = motif.get("name", "") if isinstance(motif, dict) else getattr(motif, 'name', '')
                    scene_text = f"{visual_desc} {dialogue}"
                    if not motif_name:
                        continue

                    motif_name_lower = motif_name.lower()
                    if motif_name_lower in scene_text:
                        references.append(motif_name)
                        continue

                    motif_tokens = [
                        token for token in motif_name_lower.replace("-", " ").split()
                        if len(token) > 3 and token not in {"with", "from"}
                    ]
                    if motif_tokens and sum(1 for token in motif_tokens if token in scene_text) >= 2:
                        references.append(motif_name)

        return references

    def _check_missing_payoffs(
        self,
        scene_id: str,
        memory: Optional[Dict[str, Any]],
        structure: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Check for setups that haven't been paid off."""
        missing_payoffs = []

        if not memory:
            return missing_payoffs

        # Get current act
        current_act = 3  # Default to act 3 (payoff act)
        if structure and structure.get("current_act"):
            current_act = structure["current_act"].get("act_number", 3)

        # If we're in act 3, check for unresolved setups from act 1
        if current_act == 3:
            setups = memory.get("act1_setups", [])
            if isinstance(setups, list):
                for setup in setups:
                    # Check if it was paid off
                    paid_off = False
                    resolutions = memory.get("resolutions", [])
                    if isinstance(resolutions, list):
                        for res in resolutions:
                            if setup in res:
                                paid_off = True
                                break

                    if not paid_off:
                        missing_payoffs.append(f"Unpaid setup from act 1: {setup}")

        return missing_payoffs

    def _check_character_consistency(
        self,
        scene_id: str,
        character_appearances: List[str],
        memory: Optional[Dict[str, Any]],
    ) -> List[CharacterConsistencyIssue]:
        """Check for character state inconsistencies."""
        issues = []

        for char_id in character_appearances:
            if char_id not in self._character_states:
                continue

            states = self._character_states[char_id]
            if len(states) < 2:
                continue

            # Compare current state to previous
            current_state = states[-1]
            previous_state = states[-2]

            # Check for emotional inconsistency
            if previous_state.emotional_state and current_state.emotional_state:
                if previous_state.emotional_state != current_state.emotional_state:
                    # Check if transition is justified
                    justified = self._is_emotional_transition_justified(
                        previous_state.emotional_state,
                        current_state.emotional_state,
                        current_state.key_actions
                    )

                    if not justified:
                        issues.append(CharacterConsistencyIssue(
                            character_id=char_id,
                            character_name=char_id,
                            previous_scene=previous_state.scene_id,
                            current_scene=current_state.scene_id,
                            previous_state=previous_state.emotional_state,
                            current_state=current_state.emotional_state,
                            issue_description=f"Character {char_id} emotional state changed from '{previous_state.emotional_state}' to '{current_state.emotional_state}' without clear justification"
                        ))

        return issues

    def _is_emotional_transition_justified(
        self,
        from_state: str,
        to_state: str,
        actions: List[str],
    ) -> bool:
        """Check if an emotional state transition is justified by actions."""
        if not actions:
            return False

        actions_text = " ".join(actions).lower()

        # Define some common justified transitions
        justified_transitions = {
            ("happy", "sad"): ["lost", "died", "left", "betrayed", "cried", "grief", "tragedy"],
            ("calm", "angry"): ["provoked", "insulted", "threatened", "attacked"],
            ("scared", "brave"): ["faced", "overcame", "conquered", "defeated"],
        }

        key = (from_state.lower(), to_state.lower())
        if key in justified_transitions:
            triggers = justified_transitions[key]
            return any(trigger in actions_text for trigger in triggers)

        return True  # Default to justified if no rule matches

    def _populate_scene_warnings(
        self,
        report: SceneContinuityReport,
        scene_data: Dict[str, Any],
        memory: Optional[Dict[str, Any]],
        film_intelligence: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Populate warnings for a scene report."""
        # Check for generic dialogue
        dialogue = scene_data.get("dialogue", "")
        if len(dialogue) > 500:
            report.warnings.append("Long dialogue - consider subtext")

        # Check for missing visual description
        if not scene_data.get("visual_description"):
            report.warnings.append("No visual description provided")

        if not isinstance(memory, dict):
            return

        actions = scene_data.get("actions", [])
        if isinstance(actions, list):
            actions_text = " ".join(str(action) for action in actions)
        else:
            actions_text = str(actions)

        scene_text = " ".join(
            str(part).lower() for part in [
                dialogue,
                actions_text,
                scene_data.get("intent", ""),
                scene_data.get("visual_description", ""),
                scene_data.get("emotional_tone", ""),
                scene_data.get("tone", ""),
            ] if part
        )

        unresolved_tensions = memory.get("unresolved_tensions", [])
        if not isinstance(unresolved_tensions, list):
            unresolved_tensions = []

        resolved_tensions = scene_data.get("resolved_tensions", [])
        if not isinstance(resolved_tensions, list):
            resolved_tensions = []

        if unresolved_tensions and not resolved_tensions:
            tension_flattening_markers = [
                "figured that out",
                "like nothing",
                "joking easily",
                "sit comfortably",
                "laughs as",
                "nothing has been building",
            ]
            if any(marker in scene_text for marker in tension_flattening_markers):
                report.warnings.append(
                    "Scene treats an unresolved tension as settled without an explicit payoff"
                )
                report.alerts.append(ContinuityAlert(
                    alert_type=AlertType.PAYOFF_MISSING,
                    severity=AlertSeverity.WARNING,
                    description="Unresolved tension reads as prematurely settled in-scene",
                    affected_elements=[
                        tension.get("tension_id", "unknown")
                        if isinstance(tension, dict)
                        else getattr(tension, "tension_id", "unknown")
                        for tension in unresolved_tensions
                    ],
                    recommended_action="Preserve the unresolved tension on the page or mark a clear payoff"
                ))

            emotional_contract = str(memory.get("emotional_contract", "")).lower()
            light_tone_markers = {"light", "casual", "playful", "easy"}
            scene_emotional_tone = str(scene_data.get("emotional_tone", "")).lower()
            scene_tone = str(scene_data.get("tone", "")).lower()
            if emotional_contract in {"tension", "conflict", "urgency"} and (
                scene_emotional_tone in light_tone_markers or scene_tone in light_tone_markers
            ):
                report.warnings.append(
                    "Scene flattens the established emotional contract while core tensions remain unresolved"
                )
                report.alerts.append(ContinuityAlert(
                    alert_type=AlertType.EMOTIONAL_CONTRACT_VIOLATION,
                    severity=AlertSeverity.WARNING,
                    description="Scene tone softens an active emotional contract without support from continuity context",
                    affected_elements=[report.scene_id],
                    recommended_action="Keep the scene emotionally aligned with the unresolved tension or show the transition on-screen"
                ))

        if report.motif_references:
            motif_flattening_markers = [
                "neither character reacts",
                "no one reacts",
                "without reacting",
                "ignored",
                "unnoticed",
            ]
            if any(marker in scene_text for marker in motif_flattening_markers):
                report.warnings.append(
                    "Established motif appears without carrying its prior dramatic meaning"
                )
                report.alerts.append(ContinuityAlert(
                    alert_type=AlertType.MOTIF_MISSED,
                    severity=AlertSeverity.WARNING,
                    description="Referenced motif is present but dramatically flattened in-scene",
                    affected_elements=report.motif_references,
                    recommended_action="Reconnect the motif to its established meaning or remove the callback"
                ))

        self._apply_film_intelligence_to_scene_report(
            report=report,
            film_intelligence=film_intelligence,
        )

    def _calculate_tension_health(self, tensions: List[TensionHealth]) -> float:
        """Calculate overall tension health score."""
        if not tensions:
            return 1.0

        total_score = 0.0
        for tension in tensions:
            total_score += tension.health_score

        return total_score / len(tensions)

    def _calculate_motif_health(self, motifs: List[MotifCallbackStatus]) -> float:
        """Calculate overall motif callback health score."""
        if not motifs:
            return 1.0

        fulfilled_count = sum(1 for m in motifs if m.is_fulfilled)
        overdue_count = sum(1 for m in motifs if m.is_overdue)

        # Score: fulfilled = good, overdue = bad
        if len(motifs) == 0:
            return 1.0

        score = (fulfilled_count - overdue_count) / len(motifs)
        return max(0.0, min(1.0, score))

    def _populate_alerts_and_recommendations(
        self,
        report: ContinuityHealthReport,
        structure: Optional[Dict[str, Any]],
    ) -> None:
        """Populate alerts and recommendations from health report."""
        # Tension alerts
        for tension in report.tension_statuses:
            if tension.is_overdue:
                report.alerts.append(ContinuityAlert(
                    alert_type=AlertType.TENSION_OVERDUE,
                    severity=AlertSeverity.WARNING,
                    description=f"Tension '{tension.description}' is overdue for resolution",
                    affected_elements=[tension.introduced_scene],
                    recommended_action=f"Resolve tension by act {tension.expected_resolution_act}"
                ))

        # Motif alerts
        for motif in report.motif_statuses:
            if motif.is_overdue:
                report.alerts.append(ContinuityAlert(
                    alert_type=AlertType.MOTIF_MISSED,
                    severity=AlertSeverity.WARNING,
                    description=f"Motif '{motif.motif_name}' has not been called back",
                    affected_elements=[motif.last_seen_scene] if motif.last_seen_scene else [],
                    recommended_action="Include motif callback in current act"
                ))

        # Generate recommendations
        if report.tension_health < 0.7:
            report.recommendations.append("Address overdue tensions before proceeding")

        if report.motif_health < 0.7:
            report.recommendations.append("Include motif callbacks in upcoming scenes")

        if report.character_health < 0.7:
            report.recommendations.append("Review character emotional consistency")

    def _build_film_intelligence_provenance(
        self,
        film_intelligence: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build a compact bounded provenance summary for continuity influence."""
        if not isinstance(film_intelligence, dict):
            return {
                "applied": False,
                "available": False,
                "affected_areas": [],
                "signal_strength": "sparse",
                "support": {},
            }

        canonical_sources = film_intelligence.get("canonical_sources") or {}
        support = {
            "canonical_sources": canonical_sources,
            "scope": film_intelligence.get("derived", {}).get("scope"),
            "debt_payoff_arc_summary": (
                (film_intelligence.get("derived") or {}).get("debt_payoff_arc_summary") or {}
            ),
        }
        signal_strength = "grounded" if (
            isinstance(canonical_sources, dict)
            and canonical_sources.get("structure")
            and canonical_sources.get("memory")
        ) else "sparse"
        return {
            "applied": False,
            "available": True,
            "affected_areas": [],
            "signal_strength": signal_strength,
            "support": support,
        }

    def _apply_film_intelligence_to_scene_report(
        self,
        report: SceneContinuityReport,
        film_intelligence: Optional[Dict[str, Any]],
    ) -> None:
        """Use derived film intelligence to improve scene warning specificity."""
        provenance = self._build_film_intelligence_provenance(film_intelligence)
        report.debug_metadata["film_intelligence_influence"] = provenance
        if not provenance["available"]:
            return

        derived = (film_intelligence or {}).get("derived") or {}
        sequence_summary = derived.get("sequence") or {}
        act_summary = derived.get("act") or {}
        debt_summary = derived.get("debt_payoff_arc_summary") or {}

        if debt_summary.get("open_tension_count", 0) >= 2:
            report.warnings.append(
                "Film-scale continuity shows multiple unresolved tensions still open; this scene may be extending stagnation without payoff."
            )
            report.alerts.append(ContinuityAlert(
                alert_type=AlertType.TENSION_OVERDUE,
                severity=AlertSeverity.WARNING,
                description="Film-scale tension tracking suggests unresolved tensions are stagnating across the current scope",
                affected_elements=[report.scene_id],
                recommended_action="Advance, complicate, or explicitly pay off a tracked unresolved tension"
            ))
            provenance["applied"] = True
            provenance["affected_areas"].append("tension_stagnation")

        if debt_summary.get("setup_payoff_count", 0) >= 2 and not report.missing_payoffs:
            report.warnings.append(
                "Derived setup/payoff tracking suggests payoff chains may be weakening at this point in the film."
            )
            report.alerts.append(ContinuityAlert(
                alert_type=AlertType.PAYOFF_MISSING,
                severity=AlertSeverity.WARNING,
                description="Film intelligence indicates setup/payoff obligations remain active without clear reinforcement here",
                affected_elements=[report.scene_id],
                recommended_action="Reinforce an established setup or provide a clearer payoff beat"
            ))
            provenance["applied"] = True
            provenance["affected_areas"].append("setup_payoff_weakness")

        arc_summaries = (sequence_summary.get("arc_progression_summaries") or act_summary.get("arc_progression_summaries") or [])
        if any(
            isinstance(summary, dict) and summary.get("progression_status") == "tracked_across_scope"
            for summary in arc_summaries
        ) and report.inconsistent_states:
            report.warnings.append(
                "Character inconsistency is more concerning because the active sequence/act has ongoing tracked arc movement."
            )
            provenance["applied"] = True
            provenance["affected_areas"].append("arc_discontinuity")

        motif_summaries = (sequence_summary.get("motif_summaries") or act_summary.get("motif_summaries") or [])
        if report.motif_references and any(
            isinstance(summary, dict) and summary.get("status") in {"tracked", "recurred_in_scope"}
            for summary in motif_summaries
        ):
            report.warnings.append(
                "Film-scale motif tracking suggests this callback needs clearer dramatic weight to avoid flattening."
            )
            provenance["applied"] = True
            provenance["affected_areas"].append("motif_callback_weakness")

        if isinstance(act_summary, dict) and act_summary.get("progression_status") == "scaffolded":
            report.warnings.append(
                "Act progression context is thin here, so continuity interpretation should remain conservative."
            )

        if provenance["affected_areas"]:
            provenance["affected_areas"] = sorted(set(provenance["affected_areas"]))

    def _apply_film_intelligence_to_film_report(
        self,
        report: ContinuityHealthReport,
        film_intelligence: Optional[Dict[str, Any]],
    ) -> None:
        """Use derived film intelligence to improve film-scale continuity alerts."""
        provenance = self._build_film_intelligence_provenance(film_intelligence)
        report.debug_metadata["film_intelligence_influence"] = provenance
        if not provenance["available"]:
            return

        derived = (film_intelligence or {}).get("derived") or {}
        debt_summary = derived.get("debt_payoff_arc_summary") or {}
        film_summary = derived.get("film") or {}

        if debt_summary.get("open_tension_count", 0) >= 2 and not any(
            alert.alert_type == AlertType.TENSION_OVERDUE for alert in report.alerts
        ):
            report.alerts.append(ContinuityAlert(
                alert_type=AlertType.TENSION_OVERDUE,
                severity=AlertSeverity.WARNING,
                description="Derived film intelligence indicates multiple unresolved tensions remain active across the film",
                affected_elements=[report.film_id],
                recommended_action="Audit which tensions need escalation, payoff, or explicit carry-forward"
            ))
            report.recommendations.append("Audit unresolved tensions that are stagnating across sequences or acts")
            provenance["applied"] = True
            provenance["affected_areas"].append("tension_stagnation")

        if debt_summary.get("setup_payoff_count", 0) >= 3:
            report.alerts.append(ContinuityAlert(
                alert_type=AlertType.PAYOFF_MISSING,
                severity=AlertSeverity.WARNING,
                description="Setup/payoff tracking suggests multiple active obligations may be weakening or drifting",
                affected_elements=[report.film_id],
                recommended_action="Review whether major setups are being reinforced or paid off on time"
            ))
            provenance["applied"] = True
            provenance["affected_areas"].append("setup_payoff_weakness")

        if film_summary.get("progression_status") == "partially_tracked":
            report.recommendations.append("Film progression is only partially tracked; continuity findings should be reviewed with structural context")

        if provenance["affected_areas"]:
            provenance["affected_areas"] = sorted(set(provenance["affected_areas"]))


# Global instance
memory_archivist_evaluator = MemoryArchivistEvaluator()

"""
Conflict Resolution Service - Handles agent disagreements

This service provides:
- Conflict detection between agent outputs
- Priority-based automatic resolution
- Escalation to System Orchestrator or user
- Prevention of silent overwrites
- Complete audit logging
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import uuid4
from enum import Enum

from pydantic import BaseModel
from app.models.crew import AgentRole, CrewTask, TaskOutput

logger = logging.getLogger("studio-conflicts")


class ConflictType(str, Enum):
       CREATIVE = "creative"
       TECHNICAL = "technical"
       QUALITY = "quality"


class ConflictSeverity(str, Enum):
       LOW = "low"
       MEDIUM = "medium"
       HIGH = "high"


class Conflict(BaseModel):
       id: str
       timestamp: str
       conflict_type: ConflictType
       severity: ConflictSeverity
       conflicting_agents: List[str]
       conflicting_task_ids: List[str]
       proposed_outputs: List[Dict]
       resolution: Optional[str] = None
       resolved_by: Optional[str] = None
       escalated: bool = False
       escalated_to: Optional[str] = None
       audit_log_id: Optional[str] = None


class DecisionLog(BaseModel):
       """Immutable record of any decision"""
       id: str
       timestamp: str
       field_changed: str
       previous_value: Optional[Any]
       new_value: Any
       changed_by: str
       reason: str
       conflict_id: Optional[str] = None
       user_override: bool = False


class CrewRolePriority:
       """
       Priority hierarchy for conflict resolution.
       Higher roles can overrule lower roles, with constraints.
       """
       
       PRIORITY = {
           "creative_director": 1,
           "system_orchestrator": 2,
           
           "cinematographer": 11,
           "editor": 15,
           
           "script_analyst": 16,
           "storyboard_artist": 17,
           "prompt_engineer": 18,
           "render_coordinator": 19,
           
           "producer": 22,
           "continuity_supervisor": 23,
           "quality_reviewer": 30,
       }
       
       REQUIRES_ORCHESTRATOR = {
           (AgentRole.CINEMATOGRAPHER, AgentRole.PROMPT_ENGINEER): ["prompt_style"],
       }
       
       REQUIRES_USER = {
           ConflictType.CREATIVE: ["vision_mismatch", "unresolvable_styles"],
           ConflictType.QUALITY: ["rejected_by_qa", "quality_below_threshold"],
       }


class ConflictDetector:
       """Detect conflicts between agent outputs"""
       
       CREATIVE_FIELDS = {"style", "tone", "mood", "aesthetic", "vision", "color_palette", "lighting_style"}
       TECHNICAL_FIELDS = {"resolution", "codec", "framerate", "bitrate", "format", "pipeline_stage"}
       QUALITY_FIELDS = {"quality_score", "rejected", "rejection_reason", "quality_issues"}
       
       def detect(
           self, 
           task_outputs: List[Dict], 
           memory_service=None
       ) -> List[Conflict]:
           """Detect all conflicts in agent outputs"""
           conflicts = []
           
           for i, out_a in enumerate(task_outputs):
               for out_b in task_outputs[i+1:]:
                   conflict = self._compare_outputs(out_a, out_b)
                   if conflict:
                       conflicts.append(conflict)
           
           if memory_service:
               memory_conflicts = self._check_memory_contradictions(task_outputs, memory_service)
               conflicts.extend(memory_conflicts)
           
           quality_conflicts = self._detect_quality_rejections(task_outputs)
           conflicts.extend(quality_conflicts)
           
           return conflicts
       
       def _compare_outputs(self, a: Dict, b: Dict) -> Optional[Conflict]:
           role_a = a.get("agent_role", "unknown")
           role_b = b.get("agent_role", "unknown")
           output_a = a.get("output", {}).get("data", {})
           output_b = b.get("output", {}).get("data", {})
           
           creative_conflict = self._check_field_conflict(
               output_a, output_b, self.CREATIVE_FIELDS, 
               ConflictType.CREATIVE, ConflictSeverity.MEDIUM,
               role_a, role_b, a.get("task_id"), b.get("task_id")
           )
           if creative_conflict:
               return creative_conflict
           
           technical_conflict = self._check_field_conflict(
               output_a, output_b, self.TECHNICAL_FIELDS,
               ConflictType.TECHNICAL, ConflictSeverity.LOW,
               role_a, role_b, a.get("task_id"), b.get("task_id")
           )
           if technical_conflict:
               return technical_conflict
           
           return None
       
       def _check_field_conflict(
           self, 
           output_a: Dict, 
           output_b: Dict, 
           fields: set,
           conflict_type: ConflictType,
           severity: ConflictSeverity,
           role_a: str,
           role_b: str,
           task_id_a: str,
           task_id_b: str
       ) -> Optional[Conflict]:
           for field in fields:
               if field in output_a and field in output_b:
                   val_a, val_b = output_a[field], output_b[field]
                   if val_a and val_b and val_a != val_b:
                       return Conflict(
                           id=f"conflict-{uuid4().hex[:12]}",
                           timestamp=datetime.now().isoformat(),
                           conflict_type=conflict_type,
                           severity=severity,
                           conflicting_agents=[role_a, role_b],
                           conflicting_task_ids=[task_id_a, task_id_b],
                           proposed_outputs=[output_a, output_b]
                       )
           return None
       
       def _check_memory_contradictions(
           self, 
           outputs: List[Dict],
           memory_service
       ) -> List[Conflict]:
           conflicts = []
           
           for output in outputs:
               task_id = output.get("task_id")
               data = output.get("output", {}).get("data", {})
               
               contradictions = memory_service.detect_contradictions(
                   output.get("project_id"),
                   data
               )
               
               for contradiction in contradictions:
                   conflicts.append(Conflict(
                       id=f"conflict-{uuid4().hex[:12]}",
                       timestamp=datetime.now().isoformat(),
                       conflict_type=ConflictType.CREATIVE,
                       severity=ConflictSeverity.HIGH,
                       conflicting_agents=[output.get("agent_role"), "memory"],
                       conflicting_task_ids=[task_id],
                       proposed_outputs=[data, contradiction.get("memory_value")],
                       resolution=f"Contradicts memory: {contradiction.get('field')}"
                   ))
           
           return conflicts
       
       def _detect_quality_rejections(self, outputs: List[Dict]) -> List[Conflict]:
           conflicts = []
           
           for output in outputs:
               quality_metrics = output.get("output", {}).get("quality_metrics", {})
               
               if quality_metrics.get("rejected") or quality_metrics.get("quality_score", 100) < 70:
                   conflicts.append(Conflict(
                       id=f"conflict-{uuid4().hex[:12]}",
                       timestamp=datetime.now().isoformat(),
                       conflict_type=ConflictType.QUALITY,
                       severity=ConflictSeverity.HIGH,
                       conflicting_agents=[output.get("agent_role"), "quality_reviewer"],
                       conflicting_task_ids=[output.get("task_id")],
                       proposed_outputs=[output.get("output", {}).get("data", {})],
                       resolution=quality_metrics.get("rejection_reason", "Quality below threshold")
                   ))
           
           return conflicts


class EscalationManager:
       """Determine when to escalate conflicts"""
       
       def should_escalate_to_orchestrator(self, conflict: Conflict) -> bool:
           if conflict.severity == ConflictSeverity.HIGH:
               return True
           
           if conflict.conflict_type == ConflictType.TECHNICAL:
               return True
           
           if conflict.conflict_type == ConflictType.CREATIVE:
               if not self._can_priority_resolve(conflict):
                   return True
           
           return False
       
       def should_escalate_to_user(self, conflict: Conflict) -> bool:
           if conflict.severity == ConflictSeverity.HIGH:
               return True
           
           role_pair = tuple(conflict.conflicting_agents)
           if conflict.conflict_type == ConflictType.CREATIVE:
               if role_pair in [
                   (AgentRole.DIRECTOR.value, AgentRole.CINEMATOGRAPHER.value),
                   (AgentRole.DIRECTOR.value, AgentRole.STORYBOARD_ARTIST.value),
               ]:
                   return True
           
           if conflict.conflict_type == ConflictType.QUALITY:
               return True
           
           return False
       
       def _can_priority_resolve(self, conflict: Conflict) -> bool:
           if len(conflict.conflicting_agents) != 2:
               return False
           
           role_a = conflict.conflicting_agents[0]
           role_b = conflict.conflicting_agents[1]
           
           priority_a = CrewRolePriority.PRIORITY.get(role_a, 100)
           priority_b = CrewRolePriority.PRIORITY.get(role_b, 100)
           
           return abs(priority_a - priority_b) >= 10


class ConflictResolver:
       """Resolve conflicts using priority rules"""
       
       def __init__(self):
           self.detector = ConflictDetector()
           self.escalation_manager = EscalationManager()
       
       def resolve(self, conflict: Conflict) -> Dict:
           """Attempt to resolve conflict automatically"""
           
           if self.escalation_manager.should_escalate_to_user(conflict):
               conflict.escalated = True
               conflict.escalated_to = "creative_director"
               return {
                   "resolved": False,
                   "action": "escalate_to_user",
                   "reason": "Requires creative decision"
               }
           
           if self.escalation_manager.should_escalate_to_orchestrator(conflict):
               conflict.escalated = True
               conflict.escalated_to = "system_orchestrator"
               return {
                   "resolved": False,
                   "action": "escalate_to_orchestrator",
                   "reason": "Cannot resolve automatically"
               }
           
           winner = self._resolve_by_priority(conflict)
           conflict.resolution = f"Resolved: {winner['role']} wins"
           conflict.resolved_by = winner["role"]
           
           return {
               "resolved": True,
               "action": "auto_resolved",
               "winner": winner["role"],
               "reason": winner["reason"]
           }
       
       def _resolve_by_priority(self, conflict: Conflict) -> Dict:
           role_a = conflict.conflicting_agents[0]
           role_b = conflict.conflicting_agents[1]
           
           priority_a = CrewRolePriority.PRIORITY.get(role_a, 100)
           priority_b = CrewRolePriority.PRIORITY.get(role_b, 100)
           
           if priority_a < priority_b:
               return {"role": role_a, "reason": "higher_priority"}
           else:
               return {"role": role_b, "reason": "higher_priority"}


class DecisionLogService:
       """Immutable audit trail - prevent silent overwrites"""
       
       def __init__(self):
           self._decisions: List[DecisionLog] = []
           self._conflicts: List[Conflict] = []
       
       async def log_decision(self, decision: DecisionLog):
           self._decisions.append(decision)
           logger.info(f"Decision logged: {decision.field_changed} = {decision.new_value}")
       
       async def log_conflict(self, conflict: Conflict):
           self._conflicts.append(conflict)
           logger.warning(f"Conflict logged: {conflict.conflict_type.value} between {conflict.conflicting_agents}")
       
       def check_overwrite(self, field: str, new_value: Any) -> Optional[Dict]:
           """Check if overwriting this field requires conflict resolution"""
           
           recent_decisions = [
               d for d in self._decisions[-10:] 
               if d.field_changed == field and d.new_value != new_value
           ]
           
           if recent_decisions:
               last = recent_decisions[-1]
               return {
                   "would_overwrite": True,
                   "previous_value": last.new_value,
                   "previous_decision_id": last.id,
                   "changed_by": last.changed_by,
                   "conflict_created": True
               }
           
           return None
       
       def get_audit_trail(self, field: str = None, task_id: str = None) -> List[Dict]:
           results = []
           
           for decision in self._decisions:
               if field and decision.field_changed != field:
                   continue
               results.append(decision.model_dump())
           
           return results
       
       def get_conflict_history(self, project_id: str = None) -> List[Dict]:
           return [c.model_dump() for c in self._conflicts]


class ConflictService:
       """Main conflict resolution service"""
       
       def __init__(self, memory_service=None):
           self.resolver = ConflictResolver()
           self.decision_log = DecisionLogService()
           self.memory_service = memory_service
       
       def check_and_resolve(
           self, 
           task_outputs: List[Dict], 
           project_id: str
       ) -> Dict:
           """Check for conflicts and attempt resolution"""
           
           conflicts = self.resolver.detector.detect(task_outputs, self.memory_service)
           
           if not conflicts:
               return {"has_conflicts": False, "conflicts": []}
           
           resolutions = []
           
           for conflict in conflicts:
               self.decision_log.log_conflict(conflict)
               resolution = self.resolver.resolve(conflict)
               resolutions.append({
                   "conflict_id": conflict.id,
                   "type": conflict.conflict_type.value,
                   "resolution": resolution
               })
           
           return {
               "has_conflicts": True,
               "conflicts": resolutions,
               "escalated": any(c.escalated for c in conflicts)
           }
       
       def get_conflicts(self, project_id: str = None) -> List[Dict]:
           return self.decision_log.get_conflict_history(project_id)
       
       def get_audit_trail(self, field: str = None) -> List[Dict]:
           return self.decision_log.get_audit_trail(field)


conflict_service = ConflictService()


class FilmContinuityTracker:
    """
    Tracks film-level continuity debt across all scenes.

    Used for film-level health scoring beyond per-scene evaluation.
    This enables tracking of accumulated continuity issues that may
    not be severe enough to block individual scenes but affect
    overall film quality.

    Phase 3.5: Director-Memory Archivist Conflict Resolution
    """

    def __init__(self):
        """Initialize the film continuity tracker."""
        self._film_debt: Dict[str, List[Dict]] = {} # film_id -> list of alerts
        self._scene_decisions: Dict[str, Dict] = {} # (film_id, scene_id) -> decision

    def record_scene_decision(
        self,
        film_id: str,
        scene_id: str,
        decision_output: Dict
    ) -> None:
        """
        Record a scene's decision and continuity status for film-level tracking.

        Args:
            film_id: The film identifier
            scene_id: The scene identifier
            decision_output: The merged DirectorContinuityDecision output
        """
        key = (film_id, scene_id)
        self._scene_decisions[key] = decision_output

        # Extract alerts from continuity context
        continuity_context = decision_output.get("continuity_context", {})
        alerts = continuity_context.get("alerts", [])

        if alerts:
            if film_id not in self._film_debt:
                self._film_debt[film_id] = []
            self._film_debt[film_id].extend(alerts)

    def get_film_continuity_debt(self, film_id: str) -> Dict:
        """
        Get film-level continuity debt summary.

        Args:
            film_id: The film identifier

        Returns:
            Dictionary with debt summary:
            - total_alerts: int
            - critical_count: int
            - warning_count: int
            - by_type: Dict[str, int]
            - scene_count: int
        """
        alerts = self._film_debt.get(film_id, [])

        # Count by severity
        critical_count = len([
            a for a in alerts
            if isinstance(a, dict) and a.get("severity") == "CRITICAL"
        ])
        warning_count = len([
            a for a in alerts
            if isinstance(a, dict) and a.get("severity") == "WARNING"
        ])

        # Group by type
        by_type: Dict[str, int] = {}
        for alert in alerts:
            if isinstance(alert, dict):
                alert_type = alert.get("type", "unknown")
                by_type[alert_type] = by_type.get(alert_type, 0) + 1

        # Count scenes for this film
        scene_count = sum(
            1 for (f, s) in self._scene_decisions.keys() if f == film_id
        )

        return {
            "total_alerts": len(alerts),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "by_type": by_type,
            "scene_count": scene_count
        }

    def get_film_health_score(self, film_id: str) -> float:
        """
        Calculate film-level health score based on continuity debt.

        Args:
            film_id: The film identifier

        Returns:
            Health score between 0.0 (poor) and 1.0 (excellent)
        """
        debt = self.get_film_continuity_debt(film_id)
        total = debt["total_alerts"]
        critical = debt["critical_count"]
        warning = debt["warning_count"]

        if total == 0:
            return 1.0

        # Penalize heavily for critical alerts
        # Each critical = 0.1, each warning = 0.02
        penalty = (critical * 0.1) + (warning * 0.02)
        score = max(0.0, 1.0 - penalty)

        return score

    def get_scene_decision(
        self,
        film_id: str,
        scene_id: str
    ) -> Optional[Dict]:
        """
        Get the decision for a specific scene.

        Args:
            film_id: The film identifier
            scene_id: The scene identifier

        Returns:
            The scene decision dict or None if not found
        """
        key = (film_id, scene_id)
        return self._scene_decisions.get(key)

    def get_all_scene_decisions(self, film_id: str) -> List[Dict]:
        """
        Get all scene decisions for a film.

        Args:
            film_id: The film identifier

        Returns:
            List of scene decision dicts
        """
        return [
            decision for (f, s), decision in self._scene_decisions.items()
            if f == film_id
        ]

    def clear_film(self, film_id: str) -> None:
        """
        Clear all data for a film.

        Args:
            film_id: The film identifier
        """
        # Remove from debt tracking
        if film_id in self._film_debt:
            del self._film_debt[film_id]

        # Remove scene decisions
        keys_to_remove = [
            (f, s) for (f, s) in self._scene_decisions.keys()
            if f == film_id
        ]
        for key in keys_to_remove:
            del self._scene_decisions[key]

    def get_film_summary(self, film_id: str) -> Dict:
        """
        Get a complete summary of film continuity status.

        Args:
            film_id: The film identifier

        Returns:
            Dictionary with complete film summary
        """
        debt = self.get_film_continuity_debt(film_id)
        health = self.get_film_health_score(film_id)
        scenes = self.get_all_scene_decisions(film_id)

        return {
            "film_id": film_id,
            "health_score": health,
            "total_alerts": debt["total_alerts"],
            "critical_count": debt["critical_count"],
            "warning_count": debt["warning_count"],
            "alerts_by_type": debt["by_type"],
            "scene_count": debt["scene_count"],
            "scenes": scenes
        }
def get_film_health_score(self, film_id: str) -> float:
       """
       Calculate a film-level health score based on accumulated debt.
    
       Score is 1.0 (perfect) minus penalties for critical and warning alerts.
    
       Args:
           film_id: The film identifier
        
       Returns:
           Health score between 0.0 and 1.0
       """
       debt = self.get_film_continuity_debt(film_id)
       scene_count = max(debt["scene_count"], 1)  # Avoid division by zero
    
       # Penalty calculation
       # Critical: 0.05 per occurrence, max 0.3
       # Warning: 0.01 per occurrence, max 0.2
       # Normalized by scene count to avoid penalizing longer films unfairly
       critical_penalty = min(0.05 * debt["critical_count"], 0.3) / scene_count
       warning_penalty = min(0.01 * debt["warning_count"], 0.2) / scene_count
    
       health_score = 1.0 - critical_penalty - warning_penalty
       return max(0.0, min(1.0, health_score))

def get_scene_decision(
       self,
       film_id: str,
       scene_id: str
) -> Optional[Dict]:
       """
       Get the recorded decision for a specific scene.
    
       Args:
           film_id: The film identifier
           scene_id: The scene identifier
        
       Returns:
           The decision output dict or None if not found
       """
       return self._scene_decisions.get((film_id, scene_id))

def get_all_scene_decisions(self, film_id: str) -> List[Dict]:
       """
       Get all recorded decisions for a film.
    
       Args:
           film_id: The film identifier
        
       Returns:
           List of decision output dicts
       """
       return [
           decision
           for (f, s), decision in self._scene_decisions.items()
           if f == film_id
       ]

def clear_film(self, film_id: str) -> None:
       """
       Clear all tracking data for a film.
    
       Args:
           film_id: The film identifier
       """
       if film_id in self._film_debt:
           del self._film_debt[film_id]
    
       # Remove scene decisions for this film
       keys_to_remove = [
           key for key in self._scene_decisions.keys() if key[0] == film_id
       ]
       for key in keys_to_remove:
           del self._scene_decisions[key]

def get_film_summary(self, film_id: str) -> Dict:
       """
       Get a comprehensive summary of film continuity status.
    
       Args:
           film_id: The film identifier
        
       Returns:
           Dictionary with debt, health score, and scene count
       """
       debt = self.get_film_continuity_debt(film_id)
       health_score = self.get_film_health_score(film_id)
    
       return {
           "film_id": film_id,
           "health_score": health_score,
           "scene_count": debt["scene_count"],
           "total_alerts": debt["total_alerts"],
           "critical_count": debt["critical_count"],
           "warning_count": debt["warning_count"],
           "alerts_by_type": debt["by_type"]
       }


# Global instance for film continuity tracking
film_continuity_tracker = FilmContinuityTracker()
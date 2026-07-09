"""
Director-Memory Archivist Conflict Resolution Service - Phase 3.5

This service provides conflict resolution between Director (creative authority)
and Memory Archivist (continuity advisor).

Key Design Principles:
1. Director remains authoritative - creative decisions are final
2. Memory Archivist is advisory only - continuity reports attach to decisions
3. CRITICAL alerts require acknowledgment but don't block
4. Film-level tracking enables continuity debt accumulation

This module provides:
- merge_director_memory_archivist(): Combines Director and Memory Archivist outputs
- get_alert_severity_level(): Maps alert severity to conflict severity
- should_escalate_decision(): Determines if decision needs escalation
"""

from typing import Dict, List, Optional, Any
from datetime import datetime

from app.models.crew import DirectorContinuityDecision


class AlertSeverity:
    """Alert severity levels from Memory Archivist."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "info"


class ConflictSeverity:
    """Conflict severity for escalation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKING = "blocking"


def merge_director_memory_archivist(
    director_output: Dict[str, Any],
    memory_archivist_output: Dict[str, Any],
    scene_id: Optional[str] = None,
    film_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Merge Director decision with Memory Archivist continuity report.
    
    This is NOT a conflict in the traditional sense - it's an attachment
    of advisory continuity data to the authoritative creative decision.
    The Director's decision is preserved; Memory Archivist data is attached.
    
    Args:
        director_output: Output from DirectorEvaluator containing:
            - decision: APPROVE/REVISE/REJECT
            - score: float
            - revision_notes: List[str]
            - (other Director fields)
        memory_archivist_output: Output from MemoryArchivistEvaluator containing:
            - health_scores: Dict with overall, tension, motif, character, act_transition
            - alerts: List of alert dicts with type, severity, description, etc.
            - continuity_report: Dict with film/scene continuity data
        scene_id: Optional scene identifier
        film_id: Optional film identifier
    
    Returns:
        Merged output dict containing:
        - All Director fields preserved
        - continuity_context: Attached Memory Archivist analysis
        - has_continuity_debt: bool
        - has_critical_alerts: bool
        - escalation_flag: bool
        - alerts_acknowledged: bool (True unless CRITICAL alerts exist)
    """
    # Start with Director output as base
    merged = director_output.copy()
    
    # Extract Memory Archivist data
    health_scores = memory_archivist_output.get("health_scores", {})
    alerts = memory_archivist_output.get("alerts", [])
    continuity_report = memory_archivist_output.get("continuity_report")
    
    # Count alerts by severity
    critical_count = len([
        a for a in alerts
        if isinstance(a, dict) and a.get("severity") == AlertSeverity.CRITICAL
    ])
    warning_count = len([
        a for a in alerts
        if isinstance(a, dict) and a.get("severity") == AlertSeverity.WARNING
    ])
    
    # Attach continuity context
    merged["continuity_context"] = {
        "health_scores": health_scores,
        "alerts": alerts,
        "continuity_report": continuity_report,
        "critical_count": critical_count,
        "warning_count": warning_count
    }
    
    # Set conflict flags
    merged["has_continuity_debt"] = warning_count > 0
    merged["has_critical_alerts"] = critical_count > 0
    
    # Determine if acknowledgment is required
    # CRITICAL alerts require acknowledgment before proceeding
    merged["alerts_acknowledged"] = critical_count == 0
    
    # Set escalation flag for film-level review
    # Escalate if 2+ CRITICAL alerts exist
    merged["escalation_flag"] = critical_count >= 2
    
    # Add CRITICAL alerts to revision notes (informational)
    revision_notes = merged.get("revision_notes", [])
    if critical_count > 0:
        for alert in alerts:
            if isinstance(alert, dict) and alert.get("severity") == AlertSeverity.CRITICAL:
                revision_notes.append(
                    f"Continuity Critical: {alert.get('description', 'See alert')}"
                )
        merged["revision_notes"] = revision_notes
    
    # Add scene/film context if provided
    if scene_id:
        merged["scene_id"] = scene_id
    if film_id:
        merged["film_id"] = film_id
    
    # Add timestamp
    merged["timestamp"] = datetime.utcnow().isoformat()
    
    return merged


def get_alert_severity_level(alerts: List[Dict]) -> str:
    """
    Map alert severities to conflict severity level.
    
    Args:
        alerts: List of alert dicts
        
    Returns:
        ConflictSeverity level: LOW, MEDIUM, HIGH, or BLOCKING
    """
    if not alerts:
        return ConflictSeverity.LOW
    
    critical_count = len([
        a for a in alerts
        if isinstance(a, dict) and a.get("severity") == AlertSeverity.CRITICAL
    ])
    warning_count = len([
        a for a in alerts
        if isinstance(a, dict) and a.get("severity") == AlertSeverity.WARNING
    ])
    
    # Blocking: Reserved for future user override scenarios
    # For now, we don't return BLOCKING from alerts
    if critical_count >= 3:
        return ConflictSeverity.HIGH
    elif critical_count >= 1:
        return ConflictSeverity.MEDIUM
    elif warning_count >= 3:
        return ConflictSeverity.MEDIUM
    elif warning_count >= 1:
        return ConflictSeverity.LOW
    
    return ConflictSeverity.LOW


def should_escalate_decision(merged_output: Dict[str, Any]) -> bool:
    """
    Determine if a merged decision should be escalated for review.
    
    Args:
        merged_output: Output from merge_director_memory_archivist()
        
    Returns:
        True if decision should be escalated
    """
    # Check explicit escalation flag
    if merged_output.get("escalation_flag", False):
        return True
    
    # Check for high conflict severity
    conflict_severity = merged_output.get("conflict_severity")
    if conflict_severity == ConflictSeverity.HIGH:
        return True
    
    # Check for blocking severity
    if conflict_severity == ConflictSeverity.BLOCKING:
        return True
    
    return False


def create_director_continuity_decision(
    merged_output: Dict[str, Any]
) -> DirectorContinuityDecision:
    """
    Create a DirectorContinuityDecision model from merged output.
    
    Args:
        merged_output: Output from merge_director_memory_archivist()
        
    Returns:
        DirectorContinuityDecision instance
    """
    continuity_context = merged_output.get("continuity_context", {})
    
    return DirectorContinuityDecision(
        decision=merged_output.get("decision", "REVISE"),
        score=merged_output.get("score", 0.0),
        revision_notes=merged_output.get("revision_notes", []),
        continuity_report=continuity_context.get("continuity_report"),
        alerts=continuity_context.get("alerts", []),
        has_conflicts=merged_output.get("has_continuity_debt", False),
        conflict_severity=merged_output.get("conflict_severity"),
        critical_alert_count=continuity_context.get("critical_count", 0),
        warning_alert_count=continuity_context.get("warning_count", 0),
        alerts_acknowledged=merged_output.get("alerts_acknowledged", True),
        escalation_flag=merged_output.get("escalation_flag", False),
        scene_id=merged_output.get("scene_id"),
        film_id=merged_output.get("film_id"),
        timestamp=merged_output.get("timestamp", datetime.utcnow().isoformat())
    )


def get_resolution_summary(merged_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a human-readable summary of the resolution.
    
    Args:
        merged_output: Output from merge_director_memory_archivist()
        
    Returns:
        Summary dict with key information
    """
    continuity_context = merged_output.get("continuity_context", {})
    decision = merged_output.get("decision", "UNKNOWN")
    
    summary = {
        "decision": decision,
        "score": merged_output.get("score", 0.0),
        "has_continuity_issues": continuity_context.get("critical_count", 0) > 0 or 
                                continuity_context.get("warning_count", 0) > 0,
        "critical_alerts": continuity_context.get("critical_count", 0),
        "warning_alerts": continuity_context.get("warning_count", 0),
        "requires_acknowledgment": not merged_output.get("alerts_acknowledged", True),
        "escalation_flag": merged_output.get("escalation_flag", False),
        "health_scores": continuity_context.get("health_scores", {})
    }
    
    return summary


# Global instance for convenience
director_memory_resolver = {
    "merge": merge_director_memory_archivist,
    "get_severity": get_alert_severity_level,
    "should_escalate": should_escalate_decision,
    "create_decision": create_director_continuity_decision,
    "get_summary": get_resolution_summary
}
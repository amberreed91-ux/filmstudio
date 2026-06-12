from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime

Severity = Literal["note", "warning", "blocker"]
ReadinessLevel = Literal["ready", "minor_issues", "major_issues"]

class ProductionScanFlag(BaseModel):
    flag_type: str
    severity: Severity
    description: str
    affected_scenes: List[str] = Field(default_factory=list)
    co_director_note: str

class ProductionScanReport(BaseModel):
    scan_id: str
    project_id: str
    readiness_level: ReadinessLevel
    flags: List[ProductionScanFlag] = Field(default_factory=list)
    clear_to_shoot: bool
    summary: str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

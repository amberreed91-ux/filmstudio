from __future__ import annotations

from pydantic import BaseModel


class SymbolismNode(BaseModel):
    motif: str = ""
    object: str = ""
    color: str = ""
    emotional_meaning: str = ""
    recurrence_frequency: int = 0


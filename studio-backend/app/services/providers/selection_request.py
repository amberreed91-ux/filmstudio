from __future__ import annotations

from typing import Optional, Dict, Any


def normalize_selection_request(requested_provider: Optional[str]) -> Dict[str, Any]:
    """
    Normalize provider selection request shape.

    Returns a non-throwing, deterministic dict:
    - invalid input -> {"requested_provider": None}
    - valid input -> {"requested_provider": "<normalized>"}
    """
    if not isinstance(requested_provider, str):
        return {"requested_provider": None}

    normalized = requested_provider.strip().lower()
    if not normalized:
        return {"requested_provider": None}

    return {"requested_provider": normalized}


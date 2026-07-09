from __future__ import annotations

import copy
from typing import Any, Dict


_MANUAL_PROVIDER_SELECTION_CONTRACT: Dict[str, Any] = {
    "selection_mode": "manual_only",
    "auto_execution": False,
    "execution_on_select": False,
    "reason": "Provider selection does not trigger execution",
}


def build_manual_provider_selection_contract() -> Dict[str, Any]:
    """Return deterministic, non-mutable manual provider selection contract."""
    return copy.deepcopy(_MANUAL_PROVIDER_SELECTION_CONTRACT)

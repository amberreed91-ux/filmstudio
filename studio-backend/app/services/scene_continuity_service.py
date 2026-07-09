# Re-export shim — SceneContinuityService logic now lives in
# continuity_intelligence_service.py.  This file is kept so that all
# existing imports continue to resolve without modification.
from app.services.continuity_intelligence_service import (  # noqa: F401
    ContinuityIntelligenceService as SceneContinuityService,
    continuity_intelligence_service as scene_continuity_service,
)

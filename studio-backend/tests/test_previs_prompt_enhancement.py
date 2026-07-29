from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.previs_prompt_enhancement_service import (
    PrevisPromptEnhancementService,
    is_material_enhancement,
)
from app.services.stability import ProviderError
from main import app


PROJECT_ID = "project_3dba9330f43a"
ORIGINAL = (
    "Over-the-shoulder or two-shot framing for conversation. "
    "DOWNTOWN CHICAGO — GOLDEN HOUR. MAYA (V.O.) People think the end "
    "of the world is fire. Buildings. Cinematic, film quality, single continuous shot."
)
MATERIAL = (
    "A restrained 40mm shoulder-height track holds Maya in the right third as she moves "
    "through the living Chicago crowd, families crossing the near foreground while the L "
    "train cuts the skyline behind her. Low golden-hour backlight rims her worn locs; warm "
    "storefront practicals fall into cooler concrete shadow. Keep shallow focus breathing "
    "between Maya and the ordinary life she watches as her voice-over remembers the fire, "
    "one continuous observant move with no editorial flourish."
)

REAL_SHOT_CASES = (
    (
        "scene_001",
        ORIGINAL,
        MATERIAL,
        ("MAYA", "People think the end of the world is fire"),
    ),
    (
        "scene_002",
        "Wide establishing shot. Downtown Chicago after the apocalypse. Maya walks "
        "through the ruins toward the Chicago River. Cinematic, film quality, single continuous shot.",
        "A low 28mm wide track follows Maya along the right edge of the reclaimed avenue, "
        "the frozen L train and cracked towers stacking behind her as she approaches the "
        "Chicago River. Flat winter daylight catches wet concrete and vine-choked steel; "
        "her lean figure passes from open gray light into bridge shadow. Let the camera lag "
        "half a step, observing rather than chasing, with deep focus holding the graveyard "
        "city and the place where she died in one continuous move.",
        ("Chicago River", "Dre"),
    ),
    (
        "scene_003",
        "Medium two-shot in Dre's warm apartment at night. Maya watches Dre cooking before "
        "he notices her. Cinematic, film quality, single continuous shot.",
        "From the dark doorway, a patient 50mm frame keeps Maya soft in the near-left "
        "foreground while Dre cooks in warm kitchen practicals beyond her. Drift focus from "
        "his hands splitting the meal to her held expression; amber light reaches him but "
        "falls off before touching her face. He crosses toward the stove as she stays rooted, "
        "then the camera makes one restrained push when he finally notices her, preserving "
        "the apartment's lived-in warmth in a continuous shot.",
        ("Dre", "cooking"),
    ),
)


def test_material_enhancement_rejects_repunctuation_and_accepts_craft_detail() -> None:
    repunctuated = ORIGINAL.replace("MAYA (V.O.)", "MAYA (V.O.).").replace(
        "Buildings.", "Buildings.."
    )
    assert not is_material_enhancement(ORIGINAL, repunctuated)
    assert is_material_enhancement(ORIGINAL, MATERIAL)


def test_prompt_contains_real_scene_memory_and_character_context() -> None:
    service = PrevisPromptEnhancementService()
    system_prompt, user_message, context = service.build_prompt(
        project_id=PROJECT_ID,
        scene_id="scene_001",
        prompt_text=ORIGINAL,
    )

    assert context.memory_entries_supplied == 8
    assert context.scene_content_included is True
    assert context.character_count >= 0
    assert "People think the end of the world is fire" in system_prompt
    assert "MAYA" in system_prompt
    assert "Visual Language" in system_prompt
    assert "punctuation pass" in system_prompt
    assert ORIGINAL in user_message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scene_id", "original", "enhanced", "scene_evidence"),
    REAL_SHOT_CASES,
)
async def test_three_real_shots_receive_material_scene_grounded_enhancements(
    scene_id: str,
    original: str,
    enhanced: str,
    scene_evidence: tuple[str, str],
) -> None:
    service = PrevisPromptEnhancementService()
    llm = AsyncMock(return_value=enhanced)

    result = await service.enhance(
        project_id=PROJECT_ID,
        scene_id=scene_id,
        prompt_text=original,
        llm=llm,
    )

    assert is_material_enhancement(original, result.enhanced_prompt)
    system_prompt = llm.await_args.args[0]
    for detail in scene_evidence:
        assert " ".join(detail.lower().split()) in " ".join(system_prompt.lower().split())
    assert result.memory_entries_supplied == 8


@pytest.mark.asyncio
async def test_near_noop_is_retried_and_only_material_result_is_returned() -> None:
    service = PrevisPromptEnhancementService()
    llm = AsyncMock(side_effect=[ORIGINAL + ".", MATERIAL])

    result = await service.enhance(
        project_id=PROJECT_ID,
        scene_id="scene_001",
        prompt_text=ORIGINAL,
        llm=llm,
    )

    assert result.enhanced_prompt == MATERIAL
    assert result.attempts == 2
    assert result.memory_entries_supplied == 8
    assert llm.await_count == 2
    assert "previous draft was too close" in llm.await_args.args[1]


@pytest.mark.asyncio
async def test_two_near_noops_use_scene_grounded_local_fallback() -> None:
    service = PrevisPromptEnhancementService()
    llm = AsyncMock(return_value=ORIGINAL + ".")

    result = await service.enhance(
        project_id=PROJECT_ID,
        scene_id="scene_001",
        prompt_text=ORIGINAL,
        llm=llm,
    )

    assert is_material_enhancement(ORIGINAL, result.enhanced_prompt)
    assert "40mm observational shot" in result.enhanced_prompt
    assert result.attempts == 2


def test_http_contract_reports_only_context_supplied_to_successful_generation() -> None:
    client = TestClient(app)
    with patch("app.routes.previs_routes._get_llm") as get_llm:
        get_llm.return_value = AsyncMock(return_value=MATERIAL)
        response = client.post(
            f"/api/f51/studio/projects/{PROJECT_ID}/previs/enhance-prompt",
            json={"scene_id": "scene_001", "prompt_text": ORIGINAL},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["enhanced_prompt"] == MATERIAL
    assert data["study_memories_used"] == 8
    assert data["scene_context_used"] is True
    assert isinstance(data["character_profiles_used"], int)
    assert data["enhancement_attempts"] == 1


def test_http_contract_returns_local_enhancement_on_provider_failure() -> None:
    client = TestClient(app)
    with patch("app.routes.previs_routes._get_llm") as get_llm:
        get_llm.return_value = AsyncMock(side_effect=RuntimeError("provider down"))
        response = client.post(
            f"/api/f51/studio/projects/{PROJECT_ID}/previs/enhance-prompt",
            json={"scene_id": "scene_001", "prompt_text": ORIGINAL},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["enhanced_prompt"] != ORIGINAL
    assert "40mm observational shot" in data["enhanced_prompt"]


def test_http_contract_returns_error_only_when_service_cannot_build_fallback() -> None:
    client = TestClient(app)
    with patch("app.routes.previs_routes._get_prompt_enhancement_service") as get_service:
        service = AsyncMock()
        service.enhance.side_effect = ProviderError(
            "Both prompt enhancement providers failed",
            stage="previs_prompt_enhancement",
            metadata={"qwen_error": "blocked", "openrouter_error": "timeout"},
        )
        get_service.return_value = service
        response = client.post(
            f"/api/f51/studio/projects/{PROJECT_ID}/previs/enhance-prompt",
            json={"scene_id": "scene_001", "prompt_text": ORIGINAL},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["error_type"] == "provider_error"

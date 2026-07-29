import pytest

from app.services.project_store import ProjectStore
from app.services.writers_intelligence_service import WritersIntelligenceService


class _Storage:
    def get_characters(self, project_id):
        return [
            {
                "name": "Mara",
                "age": "34",
                "look": "rain-dark coat",
                "energy": "held breath",
                "core_wound": "abandonment",
                "core_desire": "to trust again",
            }
        ]


def _state_store(tmp_path):
    store = ProjectStore(str(tmp_path / "projects.json"))
    store.save_project(
        {
            "project_id": "project-1",
            "title": "Test",
            "execution_summary": {
                "scenes": [{"scene_id": "scene-1", "text": "Mara waits beside the last train."}]
            },
        }
    )
    return store


@pytest.mark.asyncio
async def test_character_mind_uses_grounded_character_and_scene_context(tmp_path):
    prompts = []

    async def complete(system_prompt, user_prompt):
        prompts.append((system_prompt, user_prompt))
        return "I stay because leaving would repeat the wound.", "test-provider"

    service = WritersIntelligenceService(
        state_store=_state_store(tmp_path),
        storage=_Storage(),
        completion=complete,
    )

    result = await service.simulate_character_mind("project-1", "scene-1", "Mara")

    assert result["character"] == "Mara"
    assert "abandonment" in prompts[0][1]
    assert "Mara waits beside the last train." in prompts[0][1]


@pytest.mark.asyncio
async def test_debate_generates_both_perspectives_without_provider_calls(tmp_path):
    prompts = []

    async def complete(system_prompt, user_prompt):
        prompts.append(system_prompt)
        return f"Perspective {len(prompts)}", "test-provider"

    service = WritersIntelligenceService(
        state_store=_state_store(tmp_path),
        storage=_Storage(),
        completion=complete,
    )

    result = await service.debate_scene("project-1", "scene-1")

    assert {result["restraint"], result["urgency"]} == {"Perspective 1", "Perspective 2"}
    assert len(prompts) == 2


@pytest.mark.asyncio
async def test_missing_scene_is_a_domain_lookup_error(tmp_path):
    service = WritersIntelligenceService(
        state_store=_state_store(tmp_path),
        storage=_Storage(),
    )

    with pytest.raises(LookupError, match="Scene not found"):
        await service.debate_scene("project-1", "missing")

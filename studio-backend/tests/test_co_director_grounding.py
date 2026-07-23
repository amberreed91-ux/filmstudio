from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.co_director_chat_service import (
    CoDirectorChatService,
    classify_request,
)
from app.services.project_store import project_store
from app.services.stability import ProviderError


REAL_PROJECT_ID = "project_3dba9330f43a"


def test_clear_craft_question_is_not_classified_as_ambiguous() -> None:
    assert classify_request("how can I make scenes more emotionally triggering") == "CLEAR"
    assert classify_request("Where does Maya's ending release tension too early?") == "CLEAR"
    assert classify_request("Which opening image should return at the end?") == "CLEAR"
    assert classify_request("help") == "AMBIGUOUS"
    assert classify_request("What do you think?") == "AMBIGUOUS"


@pytest.mark.parametrize(
    ("specialist", "question", "context_type", "expected_details"),
    [
        (
            "writer",
            "how can I make scenes more emotionally triggering",
            "full_script",
            ("Maya", "Chicago", "MOM"),
        ),
        (
            "director",
            "Where does Maya's ending release tension too early?",
            "project_overview",
            ("Maya", "rooftop", "world ended"),
        ),
        (
            "memory_archivist",
            "Which images or lines echo from the opening into the ending?",
            "full_script",
            ("Maya", "Chicago", "rooftop"),
        ),
    ],
)
def test_real_project_questions_send_actual_scene_text_to_llm(
    specialist: str,
    question: str,
    context_type: str,
    expected_details: tuple[str, ...],
) -> None:
    project = project_store.get_project(REAL_PROJECT_ID)
    assert project is not None, "The checked-in real project fixture is required"

    service = CoDirectorChatService(project_store)
    prompt = service.build_prompt(
        project_id=REAL_PROJECT_ID,
        specialist=specialist,
        message=question,
        context_type=context_type,
    )

    assert prompt.request_classification == "CLEAR"
    assert prompt.scene_excerpts_used > 0
    assert "Request classification: CLEAR" in prompt.system_prompt
    assert "Answer them directly" in prompt.system_prompt
    assert "GROUNDING SCENE EXCERPTS" in prompt.system_prompt or "SCREENPLAY SCENES" in prompt.system_prompt
    for detail in expected_details:
        assert detail.lower() in prompt.system_prompt.lower()


@pytest.mark.asyncio
async def test_writer_llm_receives_canonical_text_field_from_real_scene() -> None:
    service = CoDirectorChatService(project_store)
    llm = AsyncMock(
        return_value=(
            "Maya's Chicago walk needs a sharper emotional reversal: let the passing "
            "families and Lake Michigan sunset remain beautiful long enough for her "
            "voice-over about fire to feel like grief interrupting ordinary life, not "
            "a summary of apocalypse stakes."
        )
    )

    reply, prompt = await service.chat(
        project_id=REAL_PROJECT_ID,
        specialist="writer",
        message="How can I make scenes more emotionally triggering?",
        context_type="current_scene",
        frontend_system_prompt="You are the Writer.",
        scene_id="scene_001",
        llm=llm,
    )

    assert "Lake Michigan" in reply
    assert prompt.request_classification == "CLEAR"
    system_prompt, user_message = llm.await_args.args
    assert "DOWNTOWN CHICAGO" in system_prompt
    assert "People think the end of the world is fire" in system_prompt
    assert "How can I make scenes more emotionally triggering?" in user_message


def test_writer_receives_schema_aware_director_notes_not_a_zero_memory_placeholder() -> None:
    service = CoDirectorChatService(project_store)
    prompt = service.build_prompt(
        project_id=REAL_PROJECT_ID,
        specialist="writer",
        message="How should Maya's opening carry the film's exhausted grief?",
        context_type="current_scene",
        scene_id="scene_001",
    )

    assert prompt.memory_entries_used == 8
    assert "Director's explicitly saved rules" in prompt.system_prompt
    assert "Studio pattern:" in prompt.system_prompt
    assert "no more than one meaningful disagreement" in prompt.system_prompt


@pytest.mark.asyncio
async def test_writer_retries_numeric_or_generic_evaluation_and_returns_grounded_note() -> None:
    service = CoDirectorChatService(project_store)
    llm = AsyncMock(
        side_effect=[
            "Great job! Score: 8/10.",
            (
                "In Maya's downtown Chicago golden-hour walk, hold on the families and Lake Michigan before "
                "the voice-over names fire; that delay lets ordinary beauty become the "
                "emotional cost rather than decoration."
            ),
        ]
    )

    reply, _ = await service.chat(
        project_id=REAL_PROJECT_ID,
        specialist="writer",
        message="How should the opening carry more grief?",
        context_type="current_scene",
        frontend_system_prompt="",
        scene_id="scene_001",
        llm=llm,
    )

    assert llm.await_count == 2
    assert "Lake Michigan" in reply
    assert "score" not in reply.lower()


@pytest.mark.asyncio
async def test_writer_fails_closed_after_two_noncompliant_replies() -> None:
    service = CoDirectorChatService(project_store)
    llm = AsyncMock(return_value="This looks good overall. Rating: 9/10.")

    with pytest.raises(ProviderError, match="quality policy"):
        await service.chat(
            project_id=REAL_PROJECT_ID,
            specialist="writer",
            message="How should the opening carry more grief?",
            context_type="current_scene",
            frontend_system_prompt="",
            scene_id="scene_001",
            llm=llm,
        )


@pytest.mark.asyncio
async def test_clear_question_retries_a_clarifying_deflection_with_real_context() -> None:
    service = CoDirectorChatService(project_store)
    llm = AsyncMock(
        side_effect=[
            "Could you clarify what emotional effect you want?",
            (
                "In Maya's Chicago walk, let the remembered beauty cost her something "
                "in the present before the rooftop turns survival into a choice."
            ),
        ]
    )

    reply, prompt = await service.chat(
        project_id=REAL_PROJECT_ID,
        specialist="writer",
        message="How can I make scenes more emotionally triggering?",
        context_type="full_script",
        frontend_system_prompt="You are the Writer.",
        scene_id=None,
        llm=llm,
    )

    assert prompt.request_classification == "CLEAR"
    assert llm.await_count == 2
    assert "Maya" in reply
    assert "Chicago" in reply
    assert "Answer directly now" in llm.await_args.args[1]


@pytest.mark.asyncio
async def test_ambiguous_input_is_allowed_to_ask_one_question() -> None:
    service = CoDirectorChatService(project_store)
    llm = AsyncMock(return_value="Which scene or relationship should we examine first?")

    reply, prompt = await service.chat(
        project_id=REAL_PROJECT_ID,
        specialist="writer",
        message="help",
        context_type="full_script",
        frontend_system_prompt="You are the Writer.",
        scene_id=None,
        llm=llm,
    )

    assert prompt.request_classification == "AMBIGUOUS"
    assert llm.await_count == 1
    assert reply.endswith("?")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("specialist", "question", "context_type", "grounded_reply", "details"),
    [
        (
            "writer",
            "How can I make the scenes more emotionally triggering?",
            "full_script",
            (
                "Make Maya's Chicago walk cost her a present-tense choice: let one "
                "ordinary family image collide with what she knows the city becomes."
            ),
            ("Maya", "Chicago"),
        ),
        (
            "director",
            "Where does Maya's ending release tension too early?",
            "project_overview",
            (
                "On the rooftop, Maya explains revenge, survival, and choice before "
                "the dark Chicago image can carry that turn; protect one beat of silence."
            ),
            ("Maya", "rooftop", "Chicago"),
        ),
        (
            "memory_archivist",
            "Which images or lines echo from the opening into the ending?",
            "full_script",
            (
                "The opening's beautiful Chicago returns as the dark city beneath "
                "Maya on the rooftop, turning remembered beauty into chosen survival."
            ),
            ("Chicago", "Maya", "rooftop"),
        ),
    ],
)
async def test_three_real_scene_questions_finish_with_specific_responses(
    specialist: str,
    question: str,
    context_type: str,
    grounded_reply: str,
    details: tuple[str, ...],
) -> None:
    service = CoDirectorChatService(project_store)
    llm = AsyncMock(
        side_effect=[
            "I can help. Could you clarify your intent?",
            grounded_reply,
        ]
    )

    reply, prompt = await service.chat(
        project_id=REAL_PROJECT_ID,
        specialist=specialist,
        message=question,
        context_type=context_type,
        frontend_system_prompt="",
        scene_id=None,
        llm=llm,
    )

    assert prompt.request_classification == "CLEAR"
    assert llm.await_count == 2
    for detail in details:
        assert detail.lower() in reply.lower()

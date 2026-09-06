from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Awaitable, Callable

from app.services.creative_generation_quality import co_director_response_issue
from app.services.project_store import ProjectStore, project_store
from app.services.stability import ProviderError


LLMCallable = Callable[[str, str], Awaitable[str]]
logger = logging.getLogger("co-director-chat-service")


SPECIALIST_PERSONAS: dict[str, str] = {
    "director": (
        "You are the A24 Co-Director. Speak in cinematic language. "
        "No scores or percentages. No generic advice. Push the work toward "
        "something specific and unexpected. Advisory only."
    ),
    "writer": (
        "You are the Script Supervisor and Story Architect. Focus on structure, "
        "character voice, scene economy, and what is not being said. Offer precise, "
        "reversible changes and explain their emotional consequence. Advisory only."
    ),
    "memory_archivist": (
        "You are the Memory Archivist. Track continuity, motifs, and recurring "
        "patterns across the film. Flag contradictions and surface connections "
        "the director may have missed. Advisory only."
    ),
    "evaluator": (
        "You are the Evaluator. Assess the work honestly. Identify what is working "
        "and what is not. Be specific. No flattery, scores, or percentages."
    ),
    "provider_router": (
        "You are the Provider Router. Identify which generation model, tool, or "
        "service best suits each task. Think in capabilities and constraints."
    ),
}


RESPONSE_POLICY = """
Response policy:
- First decide whether the user's request is clear or genuinely ambiguous, using
  the request classification supplied below.
- A request is clear when it names a goal, problem, craft area, scene, character,
  or desired analysis. Broad craft questions such as "how can I make the scenes
  more emotionally triggering?" are clear. Answer them directly.
- Do not ask for intent merely because the request is open-ended, informal, or
  missing a preferred solution. Make a reasonable, reversible assumption and proceed.
- Ask one concise clarifying question only when the input has no discernible task
  or target, or when incompatible interpretations would materially change the answer.
- When scene excerpts are supplied, ground substantive advice in their actual
  headings, characters, actions, dialogue, or recurring images. Name at least two
  concrete details when the supplied context contains them.
- Never pretend context is present. If no screenplay text is supplied, say what
  is missing and give the most useful bounded answer available.
- Be advisory. Do not use scores, ratings, percentages, generic praise, or
  deterministic claims about creative quality.
- Surface no more than one meaningful disagreement. Tie it to a concrete risk
  in tension, continuity, theme, pacing, or visual language.
""".strip()


_AMBIGUOUS_ONLY = {
    "help",
    "thoughts",
    "ideas",
    "advice",
    "feedback",
    "what do you think",
    "what do you think?",
    "can you help",
    "can you help?",
}


def classify_request(message: str) -> str:
    """Classify only plainly content-free requests as ambiguous."""
    normalized = re.sub(r"\s+", " ", str(message or "").strip().lower())
    normalized_words = re.sub(r"[^a-z0-9' ]", "", normalized).strip()
    if not normalized_words or normalized in _AMBIGUOUS_ONLY or normalized_words in _AMBIGUOUS_ONLY:
        return "AMBIGUOUS"
    if len(normalized_words.split()) <= 2 and normalized_words in {
        "this",
        "that",
        "it",
        "scene",
        "script",
    }:
        return "AMBIGUOUS"
    return "CLEAR"


def _scene_list(project: dict[str, Any]) -> list[dict[str, Any]]:
    summary = project.get("execution_summary")
    if isinstance(summary, dict) and isinstance(summary.get("scenes"), list):
        scenes = summary["scenes"]
    else:
        scenes = project.get("scenes") or []
    return [scene for scene in scenes if isinstance(scene, dict)]


def _scene_id(scene: dict[str, Any]) -> str:
    return str(scene.get("scene_id") or scene.get("id") or "").strip()


def _scene_body(scene: dict[str, Any]) -> str:
    # `text` is the canonical field produced by the screenplay parser.
    for key in ("text", "script", "content", "description"):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _scene_heading(scene: dict[str, Any], index: int) -> str:
    return str(
        scene.get("heading")
        or scene.get("scene_name")
        or scene.get("title")
        or _scene_id(scene)
        or f"Scene {index + 1}"
    ).strip()


def _format_scene(scene: dict[str, Any], index: int, body_limit: int = 2400) -> str:
    lines = [f"=== {_scene_heading(scene, index)} [{_scene_id(scene) or f'scene-{index + 1}'}] ==="]
    characters = scene.get("characters")
    if isinstance(characters, list):
        names = [str(name).strip() for name in characters if str(name).strip()]
        if names:
            lines.append(f"Characters: {', '.join(names)}")
    tone = str(scene.get("emotional_tone") or "").strip()
    if tone:
        lines.append(f"Emotional tone: {tone}")
    body = _scene_body(scene)
    if body:
        lines.append(body[:body_limit])
    return "\n".join(lines)


def _scene_anchors(scene: dict[str, Any], index: int) -> set[str]:
    anchors: set[str] = set()
    characters = scene.get("characters")
    if isinstance(characters, list):
        anchors.update(
            str(name).strip().lower()
            for name in characters
            if len(str(name).strip()) >= 3
        )
    heading = _scene_heading(scene, index)
    anchors.update(
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z'-]+", heading)
        if len(token) >= 4 and token.lower() not in {"scene", "interior", "exterior"}
    )
    # Parsed scenes do not always populate the `characters` array. Recover
    # names, places, and recurring images from capitalized screenplay text so
    # grounding validation reflects the evidence the model actually saw.
    anchors.update(
        token.lower()
        for token in re.findall(r"\b[A-Z][A-Za-z'-]{3,}\b", _scene_body(scene))
        if token.lower() not in {"people", "buildings", "scene", "cut", "fade"}
    )
    return anchors


def _keyword_score(scene: dict[str, Any], message: str) -> int:
    haystack = " ".join(
        (
            _scene_heading(scene, 0),
            " ".join(str(v) for v in (scene.get("characters") or [])),
            _scene_body(scene),
        )
    ).lower()
    words = {
        word
        for word in re.findall(r"[a-z0-9']+", message.lower())
        if len(word) > 3
    }
    return sum(1 for word in words if word in haystack)


def _representative_scenes(
    scenes: list[dict[str, Any]],
    message: str,
    limit: int = 3,
) -> list[tuple[int, dict[str, Any]]]:
    if len(scenes) <= limit:
        return list(enumerate(scenes))

    message_lower = message.lower()
    required_indices: set[int] = set()
    if any(word in message_lower for word in ("opening", "beginning", "first scene", "start")):
        required_indices.add(0)
    if any(word in message_lower for word in ("ending", "finale", "last scene", "end", "payoff")):
        required_indices.add(len(scenes) - 1)

    scored = sorted(
        enumerate(scenes),
        key=lambda item: (_keyword_score(item[1], message), -item[0]),
        reverse=True,
    )
    if scored and _keyword_score(scored[0][1], message) > 0:
        selected = [(index, scenes[index]) for index in sorted(required_indices)]
        for item in scored:
            if item[0] not in required_indices:
                selected.append(item)
            if len(selected) >= limit:
                break
    else:
        indices = sorted(required_indices | {0, len(scenes) // 2, len(scenes) - 1})
        selected = [(index, scenes[index]) for index in indices[:limit]]
    return sorted(selected, key=lambda item: item[0])


@dataclass(frozen=True)
class ChatPrompt:
    system_prompt: str
    user_message: str
    memory_entries_used: int
    references_used: int
    scene_excerpts_used: int
    request_classification: str
    grounding_terms: tuple[str, ...] = ()


class CoDirectorChatService:
    def __init__(self, store: ProjectStore = project_store) -> None:
        self._store = store

    def _memory_entries(
        self,
        project_id: str,
        message: str,
        max_entries: int = 8,
    ) -> list[str]:
        # Use the same schema-aware serializer and relevance selection as
        # Previs enhancement. Director notes store their prose in `note`, not
        # `content`; the previous bespoke reader therefore reported memory in
        # the UI while silently supplying none of those records to Writer.
        from app.services.study_context import select_relevant_memory_entries

        return [
            text
            for _category, text in select_relevant_memory_entries(
                project_id,
                message,
                max_entries=max_entries,
            )
        ]

    def _study_references(
        self,
        project: dict[str, Any],
        message: str,
        max_studies: int = 5,
    ) -> list[str]:
        library = project.get("reference_study_library")
        studies = library.get("studies") if isinstance(library, dict) else []
        if not isinstance(studies, list):
            return []

        valid = [
            study
            for study in studies
            if isinstance(study, dict)
            and (study.get("notes") or study.get("summary") or study.get("content") or study.get("filename"))
        ]
        words = [word for word in message.lower().split() if len(word) > 3]

        def score(study: dict[str, Any]) -> int:
            text = " ".join(
                str(study.get(key) or "")
                for key in ("title", "filename", "notes", "summary", "content")
            ).lower()
            return sum(1 for word in words if word in text)

        valid.sort(key=score, reverse=True)
        references: list[str] = []
        for study in valid[:max_studies]:
            title = study.get("title") or study.get("filename") or "Untitled"
            body = study.get("notes") or study.get("summary") or study.get("content") or ""
            references.append(f"REFERENCE: {title}\n{str(body)[:300]}")
        return references

    def _context(
        self,
        project: dict[str, Any],
        context_type: str,
        message: str,
        scene_id: str | None,
    ) -> tuple[str, int, tuple[str, ...]]:
        if context_type == "custom":
            return "", 0, ()

        scenes = _scene_list(project)
        title = str(project.get("title") or "Untitled Project")
        if not scenes:
            script_text = str(project.get("script_text") or "").strip()
            return (
                f"Project: {title}\n\nSCREENPLAY:\n{script_text[:16000]}"
                if script_text
                else f"Project: {title}\nNo screenplay scene text is available.",
                0,
                (),
            )

        if context_type == "current_scene":
            requested_id = str(scene_id or project.get("active_scene_id") or "").strip()
            match = next(
                ((index, scene) for index, scene in enumerate(scenes) if _scene_id(scene) == requested_id),
                None,
            )
            if requested_id and match is None:
                return (
                    f"Project: {title}\nThe selected scene [{requested_id}] is unavailable in this project. "
                    "Do not substitute another scene or claim to have reviewed it. Ask the creator to select an available scene for scene-specific advice.",
                    0,
                    (),
                )
            # Match the frontend chip, which presents the first scene when no
            # explicit active scene has been supplied.
            index, selected = match or (0, scenes[0])
            return (
                f"Project: {title}\n\n{_format_scene(selected, index, 6000)}",
                1,
                tuple(sorted(_scene_anchors(selected, index))),
            )

        if context_type == "full_script":
            formatted_parts: list[str] = []
            included_scenes: list[tuple[int, dict[str, Any]]] = []
            remaining = 20000
            for index, scene in enumerate(scenes):
                part = _format_scene(scene, index, 1800)
                if len(part) > remaining:
                    break
                formatted_parts.append(part)
                included_scenes.append((index, scene))
                remaining -= len(part) + 2
            formatted = "\n\n".join(formatted_parts)
            anchors = set().union(
                *(_scene_anchors(scene, index) for index, scene in included_scenes)
            )
            return (
                f"Project: {title}\n\nSCREENPLAY SCENES:\n{formatted}",
                len(included_scenes),
                tuple(sorted(anchors)),
            )

        # A project overview still needs real screenplay evidence for creative
        # specialists; a title and scene count alone cannot ground advice.
        excerpts = _representative_scenes(scenes, message)
        excerpt_text = "\n\n".join(
            _format_scene(scene, index, 2200) for index, scene in excerpts
        )
        logline = str(project.get("logline") or project.get("description") or "").strip()
        overview = f"Project: {title}\nScene count: {len(scenes)}"
        if logline:
            overview += f"\nLogline: {logline}"
        anchors = set().union(
            *(_scene_anchors(scene, index) for index, scene in excerpts)
        )
        return (
            f"{overview}\n\nGROUNDING SCENE EXCERPTS:\n{excerpt_text}",
            len(excerpts),
            tuple(sorted(anchors)),
        )

    def build_prompt(
        self,
        *,
        project_id: str,
        specialist: str,
        message: str,
        context_type: str,
        frontend_system_prompt: str = "",
        scene_id: str | None = None,
    ) -> ChatPrompt:
        project = self._store.get_project(project_id) or {}
        persona = SPECIALIST_PERSONAS[specialist]
        prompt_parts = [persona]
        if frontend_system_prompt.strip():
            prompt_parts.append(frontend_system_prompt.strip())
        prompt_parts.append(RESPONSE_POLICY)

        classification = classify_request(message)
        prompt_parts.append(f"Request classification: {classification}")

        context, scene_count, grounding_terms = self._context(
            project, context_type, message, scene_id
        )
        if context:
            prompt_parts.append(f"Current project context:\n{context}")

        memories = self._memory_entries(project_id, message)
        if memories:
            prompt_parts.append(
                "Director's explicitly saved rules:\n"
                + "\n".join(f"- {entry}" for entry in memories)
            )

        references = self._study_references(project, message)
        if references:
            prompt_parts.append("Director's reference library:\n" + "\n\n".join(references))

        return ChatPrompt(
            system_prompt="\n\n".join(prompt_parts),
            user_message=f"User request:\n{message.strip()}",
            memory_entries_used=len(memories),
            references_used=len(references),
            scene_excerpts_used=scene_count,
            request_classification=classification,
            grounding_terms=grounding_terms,
        )

    async def chat(
        self,
        *,
        project_id: str,
        specialist: str,
        message: str,
        context_type: str,
        frontend_system_prompt: str,
        scene_id: str | None,
        llm: LLMCallable,
    ) -> tuple[str, ChatPrompt]:
        prompt = self.build_prompt(
            project_id=project_id,
            specialist=specialist,
            message=message,
            context_type=context_type,
            frontend_system_prompt=frontend_system_prompt,
            scene_id=scene_id,
        )
        started = perf_counter()
        retried = False
        try:
            reply = await llm(prompt.system_prompt, prompt.user_message)
            issue = self._response_issue(reply, prompt, specialist)
            if issue:
                retried = True
                retry_message = (
                    f"{prompt.user_message}\n\n"
                    f"Your previous draft was rejected ({issue}). Answer directly now. "
                    "Name at least two specific supplied details—characters, headings, "
                    "actions, dialogue, or recurring images—and explain why the proposed "
                    "change matters emotionally. Keep the note advisory; use no score, "
                    "rating, percentage, generic praise, or deterministic claim."
                )
                reply = await llm(prompt.system_prompt, retry_message)
                remaining_issue = self._response_issue(reply, prompt, specialist)
                if remaining_issue:
                    raise ProviderError(
                        "Co-Director response failed quality policy after retry",
                        stage="co_director_chat",
                        metadata={
                            "project_id": project_id,
                            "specialist": specialist,
                            "scene_excerpts_used": prompt.scene_excerpts_used,
                            "quality_issue": remaining_issue,
                        },
                    )
        finally:
            logger.info(
                "project_id=%s job_id=- provider=qwen "
                "stage=co_director_chat duration_ms=%d specialist=%s retried=%s",
                project_id,
                int((perf_counter() - started) * 1000),
                specialist,
                retried,
            )
        return reply, prompt

    @staticmethod
    def _response_issue(
        reply: str,
        prompt: ChatPrompt,
        specialist: str,
    ) -> str | None:
        if specialist not in {"writer", "director", "memory_archivist"}:
            return None
        return co_director_response_issue(
            reply,
            request_is_clear=prompt.request_classification == "CLEAR",
            requires_grounding=prompt.scene_excerpts_used > 0,
            grounding_terms=prompt.grounding_terms,
        )

    @staticmethod
    def _needs_grounding_retry(
        reply: str,
        prompt: ChatPrompt,
        specialist: str,
    ) -> bool:
        """Compatibility wrapper for focused service tests."""
        return bool(CoDirectorChatService._response_issue(reply, prompt, specialist))


co_director_chat_service = CoDirectorChatService()

import uuid
import logging
from typing import List, Dict, Any, Optional

from app.models.production_scan import ProductionScanReport, ProductionScanFlag, Severity, ReadinessLevel
from app.services.project_store import project_store
from app.services.render import render_service

logger = logging.getLogger("studio-production-scan")


def _get_llm():
    from app.llm_client import call_llm
    return call_llm


def _count_words(text: str) -> int:
    return len(text.split()) if text else 0


def _scene_has_dialogue(text: str) -> bool:
    if not text:
        return False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == stripped.upper() and len(stripped) > 1 and not stripped.startswith("("):
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if next_line and not next_line == next_line.upper() and not next_line.startswith("("):
                return True
    return False


def _job_has_valid_output(job: Any) -> bool:
    """A render counts as complete only if status is 'complete' AND it has a valid video URL."""
    if job.status != "complete":
        return False
    url = None
    if job.output_payload:
        url = getattr(job.output_payload, 'asset_url', None)
    if not url:
        url = getattr(job, 'output_url', None)
    if not url or not url.strip():
        return False
    url_lower = url.strip().lower()
    if "error" in url_lower or "placeholder" in url_lower or url_lower == "null":
        return False
    return True


def _count_valid_renders(render_jobs: List[Any]) -> int:
    """Count unique scene_ids that have at least one valid rendered output."""
    scene_ids = set()
    for job in render_jobs:
        if not _job_has_valid_output(job):
            continue
        shot_id = job.shot_id or ""
        parts = shot_id.split("_shot_")
        scene_id = parts[0].strip() if parts else shot_id.strip()
        if scene_id:
            scene_ids.add(scene_id)
    return len(scene_ids)


def _build_stats_line(total_scenes: int, rendered_count: int, flags: List[ProductionScanFlag], content_complete: int) -> str:
    blockers = sum(1 for f in flags if f.severity == "blocker")
    warnings = sum(1 for f in flags if f.severity == "warning")
    script_status = "Script complete" if content_complete == total_scenes else f"{content_complete}/{total_scenes} scenes with content"
    return f"{total_scenes} scenes · {rendered_count} rendered · {warnings} warnings · {script_status}"


class ProductionScanService:
    def __init__(self):
        pass

    async def run_scan(self, project_id: str) -> ProductionScanReport:
        logger.info(f"Running production readiness scan for project {project_id}")

        project_data = project_store.get_project(project_id)
        if not project_data:
            return ProductionScanReport(
                scan_id=f"scan-{uuid.uuid4().hex[:8]}",
                project_id=project_id,
                readiness_level="major_issues",
                flags=[
                    ProductionScanFlag(
                        flag_type="Project not found",
                        severity="blocker",
                        description=f"Project {project_id} not found",
                        affected_scenes=[],
                        co_director_note="No project data available to scan.",
                    )
                ],
                clear_to_shoot=False,
                summary="Project data not found. Cannot run readiness scan.",
                co_director_quote="",
                stats_line="",
            )

        scenes: List[Dict[str, Any]] = []
        summary = project_data.get("execution_summary") or {}
        raw_scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        for s in raw_scenes:
            if isinstance(s, dict):
                scenes.append(s)

        render_jobs = render_service.list_jobs(project_id=project_id)

        flags: List[ProductionScanFlag] = []

        self._scan_scene_content(scenes, flags)
        self._scan_render_coverage(scenes, render_jobs, flags)
        self._scan_character_presence(scenes, flags)
        self._scan_short_scenes(scenes, flags)
        self._scan_shot_complexity(scenes, flags)

        readiness_level: ReadinessLevel = "ready"
        clear_to_shoot = True

        if any(f.severity == "blocker" for f in flags):
            readiness_level = "major_issues"
            clear_to_shoot = False
        elif any(f.severity == "warning" for f in flags):
            readiness_level = "minor_issues"

        summary, co_director_quote, stats_line = await self._generate_summary(
            project_data, scenes, render_jobs, flags, readiness_level
        )

        report = ProductionScanReport(
            scan_id=f"scan-{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            readiness_level=readiness_level,
            flags=flags,
            clear_to_shoot=clear_to_shoot,
            summary=summary,
            co_director_quote=co_director_quote,
            stats_line=stats_line,
        )

        return report

    def _scan_scene_content(self, scenes: List[Dict[str, Any]], flags: List[ProductionScanFlag]):
        for scene in scenes:
            scene_id = scene.get("scene_id", "?")
            text = scene.get("text") or scene.get("script") or ""
            heading = scene.get("heading") or ""

            if not text:
                flags.append(ProductionScanFlag(
                    flag_type="Missing script content",
                    severity="blocker",
                    description=f"Scene {scene_id} ({heading}) has no script content.",
                    affected_scenes=[scene_id],
                    co_director_note="A scene without script content cannot be visualized or blocked. Add the screenplay text.",
                ))
            elif _count_words(text) < 20:
                flags.append(ProductionScanFlag(
                    flag_type="Incomplete script",
                    severity="warning",
                    description=f"Scene {scene_id} ({heading}) has very little content ({_count_words(text)} words).",
                    affected_scenes=[scene_id],
                    co_director_note="This scene reads more like a note than a scripted scene. Expand the action and dialogue.",
                ))

    def _scan_render_coverage(self, scenes: List[Dict[str, Any]], render_jobs: List[Any], flags: List[ProductionScanFlag]):
        rendered_scene_ids = set()
        for job in render_jobs:
            if not _job_has_valid_output(job):
                continue
            shot_id = job.shot_id or ""
            parts = shot_id.split("_scene_")
            if len(parts) > 1:
                scene_part = parts[1].split("_")[0]
                rendered_scene_ids.add(f"scene_{scene_part}")
            else:
                parts2 = shot_id.split("_shot_")
                if parts2:
                    rendered_scene_ids.add(parts2[0].strip())

        for scene in scenes:
            scene_id = scene.get("scene_id", "?")
            heading = scene.get("heading") or ""
            if scene_id not in rendered_scene_ids:
                flags.append(ProductionScanFlag(
                    flag_type="Unrendered scene",
                    severity="warning",
                    description=f"Scene {scene_id} ({heading}) has no completed render.",
                    affected_scenes=[scene_id],
                    co_director_note="Without a visual reference, this scene's tone and framing remain abstract. Consider a previs pass.",
                ))

    def _scan_character_presence(self, scenes: List[Dict[str, Any]], flags: List[ProductionScanFlag]):
        for scene in scenes:
            scene_id = scene.get("scene_id", "?")
            heading = scene.get("heading") or ""
            characters = scene.get("characters") or []
            real_chars = [c for c in characters if isinstance(c, str) and c.strip() and not c.startswith("TITLE")]
            if not real_chars:
                flags.append(ProductionScanFlag(
                    flag_type="No characters",
                    severity="note",
                    description=f"Scene {scene_id} ({heading}) has no identified speaking characters.",
                    affected_scenes=[scene_id],
                    co_director_note="Empty scenes may indicate missing dialogue cues or that this is a transitional/atmospheric beat.",
                ))

    def _scan_short_scenes(self, scenes: List[Dict[str, Any]], flags: List[ProductionScanFlag]):
        for scene in scenes:
            scene_id = scene.get("scene_id", "?")
            heading = scene.get("heading") or ""
            text = scene.get("text") or scene.get("script") or ""
            wc = _count_words(text)
            if 0 < wc < 20:
                flags.append(ProductionScanFlag(
                    flag_type="Very short scene",
                    severity="note",
                    description=f"Scene {scene_id} ({heading}) is only {wc} words.",
                    affected_scenes=[scene_id],
                    co_director_note="Brief scenes can work as transition beats, but verify the intent is clear.",
                ))

    def _scan_shot_complexity(self, scenes: List[Dict[str, Any]], flags: List[ProductionScanFlag]):
        for scene in scenes:
            scene_id = scene.get("scene_id", "?")
            heading = scene.get("heading") or ""
            text = scene.get("text") or scene.get("script") or ""

            has_dialogue = _scene_has_dialogue(text)
            char_count = len(scene.get("characters") or [])
            wc = _count_words(text)

            complexity_score = 0
            if wc > 100:
                complexity_score += 1
            if char_count >= 3:
                complexity_score += 1
            if has_dialogue:
                complexity_score += 1

            if complexity_score >= 2:
                flags.append(ProductionScanFlag(
                    flag_type="Multiple shots likely needed",
                    severity="note",
                    description=f"Scene {scene_id} ({heading}) has {wc} words, {char_count} characters, and {'dialogue' if has_dialogue else 'no dialogue'} — likely needs multiple shots.",
                    affected_scenes=[scene_id],
                    co_director_note="Scenes with dialogue and multiple characters typically require coverage: wide, medium, closeup. Plan at least 3 shots.",
                ))

    async def _generate_summary(
        self,
        project_data: Dict[str, Any],
        scenes: List[Dict[str, Any]],
        render_jobs: List[Any],
        flags: List[ProductionScanFlag],
        level: ReadinessLevel,
    ) -> tuple[str, str, str]:
        total_scenes = len(scenes)
        rendered_count = _count_valid_renders(render_jobs)
        content_complete = sum(
            1 for s in scenes
            if _count_words(s.get("text") or s.get("script") or "") >= 20
        )

        stats_line = _build_stats_line(total_scenes, rendered_count, flags, content_complete)

        # ── Co-Director LLM summary ──────────────────────────────────────
        project_id = project_data.get("project_id", "")
        co_director_quote = ""
        try:
            from app.services.study_context import build_study_context_block
            context_block = build_study_context_block(project_id)

            blocker_items = [f for f in flags if f.severity == "blocker"]
            warning_items = [f for f in flags if f.severity == "warning"]
            flag_summary = ""
            if blocker_items:
                flag_summary += "BLOCKERS:\n" + "\n".join(f"- {f.description}" for f in blocker_items[:3]) + "\n"
            if warning_items:
                flag_summary += "WARNINGS:\n" + "\n".join(f"- {f.description}" for f in warning_items[:3]) + "\n"

            system_prompt = (
                "You are the A24 Co-Director reviewing a production readiness scan. "
                "Provide a concise, cinematic assessment of the project's readiness.\n\n"
                f"{context_block}\n\n"
                f"Scan results:\n"
                f"{flag_summary}"
                f"Readiness: {level}\n\n"
                "Rules:\n"
                "- Return ONLY your assessment paragraph — no labels, no prefixes, no JSON, no field names\n"
                "- No scores or percentages\n"
                "- One paragraph, 2-4 sentences\n"
                "- Reference specific issues or strengths\n"
                "- Advisory only"
            )

            call_llm = _get_llm()
            co_director_quote = await call_llm(
                system_prompt,
                "What is your assessment of production readiness?",
                max_tokens=512,
            )
            if co_director_quote:
                co_director_quote = co_director_quote.strip()
        except Exception as exc:
            logger.warning("CO_DIRECTOR_SUMMARY_FAILED | project=%s | %s", project_id, exc)

        # The summary is the co-director quote for backward compatibility
        summary = co_director_quote or "Scan complete. See flags for details."

        return summary, co_director_quote, stats_line


production_scan_service = ProductionScanService()

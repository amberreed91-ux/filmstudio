import logging
import urllib.parse

from app.data import get_storage

logger = logging.getLogger(__name__)


def generate_poster(project_id: str) -> dict:
    storage = get_storage("sqlite")
    if storage is None:
        raise ValueError("Storage not available")

    project = storage.get_project(project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")

    title = project.title or "Untitled Film"

    scenes = project.scenes or []
    scene_text = ""
    if scenes:
        scene = scenes[0]
        if isinstance(scene, dict):
            scene_text = scene.get("description", "") or scene.get("script_text", "") or ""
        else:
            scene_text = getattr(scene, "description", "") or getattr(scene, "script_text", "") or ""

    scene_text = scene_text[:300]

    prompt = (
        f"Movie poster for '{title}': cinematic wide shot, dramatic lighting, "
        f"one central figure, moody atmosphere, {scene_text}, "
        f"title treatment at bottom, film grain texture, professional movie poster design"
    )

    encoded = urllib.parse.quote(prompt)
    poster_url = (
        f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=1200&nologo=true"
    )

    storage.set_project_poster_url(project_id, poster_url)

    return {"poster_url": poster_url, "prompt_used": prompt}

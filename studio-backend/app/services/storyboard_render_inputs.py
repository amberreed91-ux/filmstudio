"""One translation of an approved storyboard shot into provider-neutral inputs."""
from app.models.storyboard_blueprint import StoryboardShot


def append_shot_handoff(prompt: str, handoff: dict) -> str:
    notes = [f"{label}: {handoff[key]}" for key, label in (("opening_state", "Opening state"), ("action_change", "Action and change"), ("ending_state", "Ending state")) if handoff.get(key)]
    block = "\n".join(notes)
    return "\n".join([prompt, block]) if block and block not in prompt else prompt


def storyboard_render_inputs(shot: StoryboardShot) -> dict:
    contract = shot.render_contract
    parameters = dict(contract.structured_parameters or {})
    parameters.update(duration=contract.duration_seconds, ratio=contract.aspect_ratio)
    parameters["strict_render_settings"] = True
    parameters["preserve_shot_prompt"] = True
    if contract.seed is not None:
        parameters["seed"] = contract.seed
    frame = str(shot.storyboard_image_url or "").strip()
    references = list(dict.fromkeys([*([frame] if frame else []), *contract.reference_assets]))
    if frame:
        # Composition is a first-frame constraint, distinct from identity refs.
        parameters["storyboard_frame_url"] = frame
    plan = shot.continuity_plan
    handoff = {key: getattr(plan, key) for key in ("opening_state", "action_change", "ending_state")}
    prompt = contract.provider_neutral_prompt
    if any(handoff.values()):
        parameters["continuity_handoff"] = {**handoff, "reference_frame_url": shot.metadata.get("handoff_frame_url")}
        prompt = append_shot_handoff(prompt, handoff)
    return {"prompt": prompt, "reference_assets": references, "parameters": parameters}

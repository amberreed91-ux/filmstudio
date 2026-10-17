"""Camera intentions for creator selection, independent of generation providers."""
from app.models.camera_presets import CameraPresetCatalog

# Descriptions are original planning instructions; effects express intent, not
# provider capability promises. Keep optical changes separate from camera travel.
_PRESETS = [
    ('locked', 'Locked-off hold', 'Essentials', 'Let performance and stillness carry the beat.', 'Hold the camera stationary; no pan, tilt, zoom, or drift.'),
    ('push-in', 'Slow push-in', 'Essentials', 'Gradually bring the audience closer.', 'Dolly slowly toward the subject; maintain focus and a steady camera height.'),
    ('pull-back', 'Slow pull-back', 'Essentials', 'Reveal space around the subject.', 'Dolly slowly backward from the subject, revealing the surrounding space.'),
    ('pan-left', 'Pan left', 'Essentials', 'Survey the scene from one position.', 'Rotate the camera left from a fixed position; do not translate sideways.'),
    ('pan-right', 'Pan right', 'Essentials', 'Follow attention across the scene.', 'Rotate the camera right from a fixed position; do not translate sideways.'),
    ('tilt-up', 'Tilt up', 'Essentials', 'Reveal the subject from bottom to top.', 'Pivot the camera upward from a fixed position, revealing the subject from bottom to top.'),
    ('tilt-down', 'Tilt down', 'Essentials', 'Direct attention from above to below.', 'Pivot the camera downward from a fixed position, revealing the scene from top to bottom.'),
    ('truck-left', 'Truck left', 'Tracking', 'Reveal depth through sideways travel.', 'Move the camera laterally left while keeping its viewing direction steady.'),
    ('truck-right', 'Truck right', 'Tracking', 'Slide across foreground and background.', 'Move the camera laterally right while keeping its viewing direction steady.'),
    ('leading', 'Leading shot', 'Tracking', 'Stay with an approaching performance.', 'Track backward in front of the moving subject, matching their speed and keeping their face framed.'),
    ('following', 'Following shot', 'Tracking', 'Travel behind the subject.', 'Track forward behind the subject, matching their speed and maintaining distance.'),
    ('side-tracking', 'Side tracking', 'Tracking', 'Observe movement in profile.', 'Track alongside the moving subject at matching speed, maintaining their side profile.'),
    ('pov-walk', 'POV walk', 'Tracking', 'Experience movement through a character’s eyes.', 'Move forward at walking speed from first-person eye level with gentle natural footstep bob.'),
    ('worms-eye', 'Worm’s-eye tracking', 'Tracking', 'Make ground-level action prominent.', 'Track at ground level looking upward; keep the subject’s feet and ground contact visible.'),
    ('handheld', 'Handheld observation', 'Tracking', 'Stay responsive to the performance.', 'Use restrained natural handheld movement; follow the subject with small human reframing adjustments.'),
    ('arc', 'Slow cinematic arc', 'Orbit', 'Reveal a new side of the subject.', 'Move slowly in a partial arc around the subject, keeping the subject as the focal point.'),
    ('orbit-180', '180° orbit', 'Orbit', 'Move to the opposite side in one shot.', 'Travel in a continuous half-circle around the subject, maintaining distance and keeping the subject centered.'),
    ('orbit-360', '360° orbit', 'Orbit', 'Explore the subject’s full surroundings.', 'Travel in a complete circle around the subject; maintain camera height, distance, and subject framing.'),
    ('fast-orbit', 'Fast 360° orbit', 'Orbit', 'Build energy around a central subject.', 'Orbit rapidly through a full circle around the subject, keeping the subject centered and the horizon level.'),
    ('pedestal-up', 'Pedestal up', 'Vertical & aerial', 'Raise the viewpoint without tilting.', 'Move the entire camera vertically upward, keeping its viewing angle fixed.'),
    ('pedestal-down', 'Pedestal down', 'Vertical & aerial', 'Lower the viewpoint without tilting.', 'Move the entire camera vertically downward, keeping its viewing angle fixed.'),
    ('crane-up', 'Crane up', 'Vertical & aerial', 'Open the scene into a wider context.', 'Lift the camera high above the subject in a smooth crane move, revealing the surrounding space.'),
    ('crane-down', 'Crane down', 'Vertical & aerial', 'Arrive gently at the subject.', 'Descend smoothly from a high viewpoint toward the subject, settling into the final composition.'),
    ('drone-flyover', 'Drone flyover', 'Vertical & aerial', 'Establish the landscape’s geography.', 'Fly forward high above the landscape on a smooth aerial path.'),
    ('drone-reveal', 'Rising drone reveal', 'Vertical & aerial', 'Reveal what lies beyond an obstruction.', 'Rise above the foreground obstruction while tilting down to reveal the landscape beyond.'),
    ('drone-orbit', 'Wide drone orbit', 'Vertical & aerial', 'Describe the scale of a location.', 'Fly a wide circular aerial path around the location, keeping it in view.'),
    ('top-down', 'Top-down view', 'Vertical & aerial', 'Show spatial patterns from directly above.', 'Point the camera straight down from above; hold its position for a clear overhead composition.'),
    ('drone-dive', 'FPV drone dive', 'Vertical & aerial', 'Descend through space with urgency.', 'Dive forward and downward alongside the vertical structure, then level out near its base.'),
    ('zoom-in', 'Smooth optical zoom in', 'Lens & focus', 'Tighten the frame from a fixed position.', 'Keep the camera stationary and smoothly increase focal length to tighten framing on the subject.'),
    ('zoom-out', 'Smooth optical zoom out', 'Lens & focus', 'Widen the frame from a fixed position.', 'Keep the camera stationary and smoothly decrease focal length to reveal a wider field of view.'),
    ('crash-zoom', 'Snap / crash zoom', 'Lens & focus', 'Punctuate a sudden realization.', 'Keep the camera stationary and rapidly zoom in on the subject’s reaction, settling sharply on the face.'),
    ('rack-focus', 'Rack focus', 'Lens & focus', 'Transfer attention between two subjects.', 'Hold the composition steady; smoothly shift focus from the foreground object to the background subject.'),
    ('blur-reveal', 'Reveal from blur', 'Lens & focus', 'Let a subject gradually become legible.', 'Begin out of focus, then slowly pull focus until the subject becomes sharp; hold the camera steady.'),
    ('dolly-zoom', 'Dolly zoom / vertigo', 'Lens & focus', 'Shift perspective around a steady subject.', 'Dolly backward while zooming in to keep the subject the same size; let background perspective change.'),
    ('fisheye', 'Fisheye / peephole', 'Lens & focus', 'Use a visibly distorted wide view.', 'Use an extreme wide-angle fisheye view with curved edge distortion; use a circular peephole border if requested.'),
    ('macro', 'Extreme macro', 'Lens & focus', 'Draw attention to a tiny physical detail.', 'Move into an extreme macro view of the selected surface detail, maintaining focus on that detail.'),
    ('foreground-reveal', 'Reveal from behind', 'Reveals', 'Uncover a scene from a concealed position.', 'Slide sideways from behind a foreground obstruction until the subject is revealed.'),
    ('through-shot', 'Through shot', 'Reveals', 'Enter a space through an opening.', 'Move forward through the open doorway or window into the scene, clearing its edges.'),
    ('whip-pan', 'Whip pan', 'Stylized', 'Redirect attention with a sudden sweep.', 'Pan rapidly toward the next subject with directional motion blur, then settle into a stable composition.'),
    ('barrel-roll', 'Barrel roll', 'Stylized', 'Rotate the horizon during forward travel.', 'Move forward while rolling the camera around its viewing axis through one full clockwise rotation.'),
    ('bullet-time', 'Bullet time', 'Stylized', 'Explore a suspended moment.', 'Show the action nearly frozen while the camera orbits right around the suspended moment.'),
    ('hyperlapse', 'Moving hyperlapse', 'Stylized', 'Compress a journey into a short passage.', 'Travel forward through the location with accelerated time and rapid environmental motion.'),
    ('cosmic-pullback', 'Cosmic pullback', 'Stylized', 'Expand from a local detail to vast scale.', 'Pull back continuously from the subject to the city, landscape, and finally a planetary view; treat this as a stylized scale transition.'),
    ('reaction', 'Patient reaction', 'Dialogue & detail', 'Let the listener’s response register.', 'Hold a steady eye-level close-up on the listening character; allow their reaction to unfold without camera movement.'),
    ('over-shoulder', 'Over-the-shoulder dialogue', 'Dialogue & detail', 'Keep the listener present while framing the speaker.', 'Frame the speaker at eye level over the listener’s shoulder; maintain established eyelines and screen direction.'),
    ('two-shot', 'Shared two-shot', 'Dialogue & detail', 'Let both performances share the frame.', 'Hold both characters in a steady eye-level medium two-shot, leaving room for their gestures.'),
    ('insert', 'Detail insert', 'Dialogue & detail', 'Make a story-relevant object legible.', 'Hold a steady close-up on the important object or hand action; keep the key detail in focus.'),
    ('negative-space', 'Negative-space hold', 'Dialogue & detail', 'Leave room for absence or anticipation.', 'Hold a static composition with the subject to one side and deliberate empty space in their direction of attention.'),
]


class CameraPresetService:
    def recommend_for_scene(self, scene: dict | None, total_shots: int = 3) -> dict:
        """Suggest one advisory package per shot, each from its own beat."""
        count = max(1, min(12, int(total_shots or 3)))
        return {
            "total_shots": count,
            "recommendations": [
                self.recommend_for_shot(scene, shot_number, count)
                for shot_number in range(1, count + 1)
            ],
        }

    def recommend_for_shot(
        self,
        scene: dict | None,
        shot_number: int = 1,
        total_shots: int | None = None,
    ) -> dict:
        """Suggest one advisory camera package for a shot.

        Deterministic rules from shot position + the shot's script segment —
        no model calls, no scores. The caller decides whether to use it;
        nothing here writes state or blocks generation.
        """
        from app.services.shot_prompt_builder import (
            _classify_script_line_tag,
            _segment_scene_text,
            get_shot_type_label,
            resolve_total_shots,
        )

        scene_dict = scene if isinstance(scene, dict) else {}
        shot = max(1, int(shot_number or 1))
        scene_text = str(
            scene_dict.get("text") or scene_dict.get("script") or scene_dict.get("description") or ""
        )
        resolved_total = resolve_total_shots(scene_dict, shot, total_shots)
        segments = _segment_scene_text(scene_text, resolved_total)
        segment = segments[shot - 1] if shot <= len(segments) else ""
        # The script tagger labels nearly all prose DLG, so beats are read
        # from stronger signals: CHR cues mean spoken dialogue, movement
        # verbs (or rare ACT tags) mean physical action.
        import re as _re

        _action_verbs = _re.compile(
            r"\b(run|runs|running|ran|chase|chases|chasing|flee|flees|fleeing|"
            r"fight|fights|fighting|pursue|vault|leap|leaps|sprint|dart|weave|"
            r"weaving|crash|burst|race|racing|hurry|stalk|march|dive|climb)\b",
            _re.IGNORECASE,
        )
        dialogue_cues = action_beats = 0
        for line in segment.split("\n"):
            if not line.strip():
                continue
            tag = _classify_script_line_tag(line)
            if tag == "CHR":
                dialogue_cues += 1
            elif tag == "ACT" or _action_verbs.search(line):
                action_beats += 1
        raw_cast = scene_dict.get("characters") or scene_dict.get("character_appearances") or []
        if isinstance(raw_cast, str):
            cast = [part.strip() for part in raw_cast.split(",") if part.strip()]
        elif isinstance(raw_cast, list):
            cast = [str(part).strip() for part in raw_cast if str(part).strip()]
        else:
            cast = []
        subject = cast[0] if cast else "the subject"

        catalog = self.catalog()
        presets = {preset.id: preset for preset in catalog.presets}
        views = {view.id: view for view in catalog.views}
        framings = {framing.id: framing for framing in catalog.framings}
        lenses = {lens.id: lens for lens in catalog.lenses}
        focals = {focal.id: focal for focal in catalog.focal_lengths}
        apertures = {aperture.id: aperture for aperture in catalog.apertures}

        def package(preset_id: str, view_id: str, framing_id: str, lens_id: str, focal_id: str, aperture_id: str, why: str) -> dict:
            preset = presets[preset_id]
            view = views[view_id]
            framing = framings[framing_id]
            lens = lenses[lens_id]
            focal = focals[focal_id]
            aperture = apertures[aperture_id]
            camera_text = preset.camera
            if view_id != "eye-level":
                camera_text = f"{view.camera} {preset.camera}"
            return {
                "preset_id": preset.id,
                "preset_label": preset.label,
                "view_id": view.id,
                "framing_id": framing.id,
                "lens_id": lens.id,
                "focal_length_id": focal.id,
                "aperture_id": aperture.id,
                "camera": camera_text,
                "framing": framing.framing,
                "lens_language": lens.lens_language,
                "focal_length": f"{focal.mm}mm",
                "aperture": aperture.f_stop,
                "shot_label": get_shot_type_label(shot),
                "why": why,
            }

        if shot == 1:
            return package(
                "pull-back", "eye-level", "wide", "wide-cinema", "24mm", "f5.6",
                f"A slow pull-back opens on the full space, so the audience learns the geography before {subject} fills it.",
            )
        if action_beats > 0 and action_beats >= dialogue_cues:
            return package(
                "side-tracking", "eye-level", "medium-wide", "wide-cinema", "35mm", "f4",
                f"Movement carries this beat, so travel with {subject} in profile and keep the space readable around the action.",
            )
        if dialogue_cues > 0:
            # Standard coverage: master the exchange wide-ish first, then go
            # close on the listener for later beats.
            if shot == 2:
                return package(
                    "two-shot", "eye-level", "medium", "compact-anamorphic", "50mm", "f2.8",
                    f"Lines carry this beat, so hold {subject} in a shared medium frame and let the performances trade the tension.",
                )
            return package(
                "reaction", "eye-level", "close", "vintage-prime", "85mm", "f2.8",
                f"The words are out — hold a patient close-up on {subject} and let the reaction register without movement competing with it.",
            )
        if shot == 2:
            return package(
                "push-in", "eye-level", "medium", "wide-cinema", "50mm", "f4",
                f"Move one step closer to {subject} here, so attention narrows from the location onto the person.",
            )
        if shot == 3:
            return package(
                "reaction", "eye-level", "close", "vintage-prime", "85mm", "f2.8",
                f"Hold a patient close-up on {subject} and let the reaction register without camera movement competing with it.",
            )
        return package(
            "insert", "eye-level", "insert", "macro", "50mm", "f4",
            f"Cut to the telling detail around {subject} — hands, object, trace of what just happened — so the beat lands physically.",
        )

    def catalog(self) -> CameraPresetCatalog:
        return CameraPresetCatalog(
            presets=[dict(zip(('id', 'label', 'category', 'description', 'camera'), row)) for row in _PRESETS],
            views=[{'id': key, 'label': label, 'camera': note} for key, label, note in [
                ('eye-level', 'Eye level', 'Position the camera at the subject’s eye level.'),
                ('low', 'Low angle', 'Position the camera below the subject and look upward.'),
                ('high', 'High angle', 'Position the camera above the subject and look downward.'),
                ('overhead', 'Overhead', 'Look straight down from directly above.'),
                ('ground', 'Ground level', 'Position the camera close to the ground.'),
                ('pov', 'First-person POV', 'Show the view through the character’s eyes.'),
                ('shoulder', 'Over the shoulder', 'Include the listener’s shoulder in the foreground.'),
                ('dutch', 'Dutch angle', 'Tilt the horizon diagonally in the composition.'),
            ]],
            framings=[{'id': key, 'label': label, 'framing': label} for key, label in [
                ('extreme-wide', 'Extreme wide'), ('wide', 'Wide'), ('full', 'Full body'),
                ('medium-wide', 'Medium wide'), ('medium', 'Medium'), ('medium-close', 'Medium close-up'),
                ('close', 'Close-up'), ('extreme-close', 'Extreme close-up'), ('two', 'Two-shot'), ('insert', 'Detail insert'),
            ]],
            lenses=[
                {'id': 'wide-cinema', 'label': 'Wide cinema prime', 'category': 'Spherical',
                 'description': 'Clean wide-to-normal field of view with minimal distortion.',
                 'lens_language': 'Use a wide cinema prime — minimal distortion, modern contrast, gentle flare under direct light.'},
                {'id': 'compact-anamorphic', 'label': 'Compact anamorphic', 'category': 'Anamorphic',
                 'description': 'Oval bokeh and gentle horizontal flare for cinematic texture.',
                 'lens_language': 'Use a compact anamorphic prime — oval bokeh, soft horizontal flare, mild edge stretch.'},
                {'id': 'vintage-prime', 'label': 'Vintage prime', 'category': 'Vintage',
                 'description': 'Warm halation, lower contrast, and a softer image overall.',
                 'lens_language': 'Use a vintage prime — warm halation, low contrast, gentle bloom on highlights, soft edges.'},
                {'id': 'clinical-sharp', 'label': 'Clinical sharp prime', 'category': 'Spherical',
                 'description': 'High resolution and contrast for documentary or observational shots.',
                 'lens_language': 'Use a clinical sharp prime — high micro-contrast, neutral color, minimal flare or halation.'},
                {'id': 'creative-tilt', 'label': 'Creative tilt-shift', 'category': 'Specialty',
                 'description': 'Selective focus and warped perspective planes for stylized imagery.',
                 'lens_language': 'Use a creative tilt-shift lens — narrow slice of focus, warped perspective planes, miniature-like depth control.'},
                {'id': 'macro', 'label': 'Macro probe', 'category': 'Specialty',
                 'description': 'Extreme close focus for tactile, almost microscopic detail.',
                 'lens_language': 'Use a macro probe lens — extreme close focus, high detail on small surfaces, shallow working distance.'},
            ],
            focal_lengths=[
                {'id': '14mm', 'label': '14mm', 'mm': 14, 'framing_hint': 'Ultra-wide — exaggerated depth, environmental context.'},
                {'id': '24mm', 'label': '24mm', 'mm': 24, 'framing_hint': 'Wide — strong perspective, room for movement.'},
                {'id': '35mm', 'label': '35mm', 'mm': 35, 'framing_hint': 'Wide-normal — documentary and intimate wide.'},
                {'id': '50mm', 'label': '50mm', 'mm': 50, 'framing_hint': 'Normal — neutral, natural perspective.'},
                {'id': '85mm', 'label': '85mm', 'mm': 85, 'framing_hint': 'Portrait — flattering compression, isolated subject.'},
                {'id': '135mm', 'label': '135mm', 'mm': 135, 'framing_hint': 'Telephoto — strong compression, distant subject.'},
            ],
            apertures=[
                {'id': 'f1.4', 'label': 'f/1.4', 'f_stop': 'f/1.4', 'depth_hint': 'Very shallow depth — subject pops, background dissolves.'},
                {'id': 'f2.8', 'label': 'f/2.8', 'f_stop': 'f/2.8', 'depth_hint': 'Shallow — soft background, cinematic separation.'},
                {'id': 'f4', 'label': 'f/4', 'f_stop': 'f/4', 'depth_hint': 'Light depth — subject separated, environment still readable.'},
                {'id': 'f5.6', 'label': 'f/5.6', 'f_stop': 'f/5.6', 'depth_hint': 'Medium depth — most of the frame sharp.'},
                {'id': 'f11', 'label': 'f/11', 'f_stop': 'f/11', 'depth_hint': 'Deep focus — landscape, architecture, deep staging.'},
            ],
        )

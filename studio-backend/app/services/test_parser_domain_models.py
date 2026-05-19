from app.models.ambient_audio_track import AmbientAudioTrack
from app.models.character_profile import CharacterProfile
from app.models.dialogue_line import DialogueLine
from app.models.editing_suggestion import EditingSuggestion
from app.models.emotional_arc_profile import EmotionalArcProfile
from app.models.film_assembly_timeline import FilmAssemblyTimeline
from app.models.film_visual_style_profile import FilmVisualStyleProfile
from app.models.scene_assembly import SceneAssembly
from app.models.shot_sequence_plan import ShotSequencePlan, ShotSequenceStep
from app.models.symbolism_node import SymbolismNode
from app.models.voice_direction_command import VoiceDirectionCommand


def test_parser_domain_models_import_and_minimal_instantiation():
    ambient = AmbientAudioTrack(track_id="track_1", scene_id="scene_1", ambience_type="rain")
    character = CharacterProfile(character_id="char_1", name="Mara")
    dialogue = DialogueLine(
        line_id="line_1",
        scene_id="scene_1",
        character_id="char_1",
        character_name="Mara",
        text="Keep moving.",
    )
    edit = EditingSuggestion(
        suggestion_type="cutaway",
        title="Add reaction insert",
        recommendation="Insert reaction shot after line.",
    )
    arc = EmotionalArcProfile(scene_id="scene_1")
    timeline = FilmAssemblyTimeline(timeline_id="timeline_1")
    style = FilmVisualStyleProfile(style_id="style_1", style_name="noir")
    assembly = SceneAssembly(assembly_id="assembly_1")
    plan = ShotSequencePlan(
        scene_id="scene_1",
        steps=[ShotSequenceStep(shot_type="wide", order=1)],
    )
    symbol = SymbolismNode(motif="rain")
    command = VoiceDirectionCommand(raw_command="increase tension")

    assert ambient.track_id == "track_1"
    assert character.character_id == "char_1"
    assert dialogue.line_id == "line_1"
    assert edit.suggestion_type == "cutaway"
    assert arc.scene_id == "scene_1"
    assert timeline.timeline_id == "timeline_1"
    assert style.style_name == "noir"
    assert assembly.assembly_id == "assembly_1"
    assert plan.steps[0].shot_type == "wide"
    assert symbol.motif == "rain"
    assert command.raw_command == "increase tension"

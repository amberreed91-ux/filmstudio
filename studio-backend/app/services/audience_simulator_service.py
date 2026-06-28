from __future__ import annotations
from typing import Any, Dict, List, Optional
from app.services.project_store import project_store
from app.services.director_memory_service import director_memory_service
from app.services.script_intelligence_service import script_intelligence_service
from app.models.audience_simulator import (
    AudienceReaction,
    SceneAudienceSimulation,
    ProjectAudienceSimulation,
)

class AudienceSimulatorService:
    """
    Predicts how different audience types will emotionally experience a scene or sequence.
    Co-director voice throughout — no scores or percentages.
    Integrates with Director's Memory Engine and Script Intelligence.
    """

    async def simulate_scene(self, project_id: str, scene_id: str) -> SceneAudienceSimulation:
        project = project_store.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        scene = next((s for s in scenes if str(s.get("scene_id")) == scene_id), None)
        if not scene:
            raise ValueError(f"Scene {scene_id} not found in project {project_id}")

        # Gather context
        memory_scan = director_memory_service.scan_scene(project_id, scene)
        sound_advisory = script_intelligence_service._generate_sound_advisory(scene)
        
        # Get preceding and succeeding scenes for transition context
        scene_index = scenes.index(scene)
        prev_scene = scenes[scene_index - 1] if scene_index > 0 else None
        next_scene = scenes[scene_index + 1] if scene_index < len(scenes) - 1 else None
        
        transition_to = script_intelligence_service._generate_transition_advisory(scene, next_scene) if next_scene else None
        transition_from = script_intelligence_service._generate_transition_advisory(prev_scene, scene) if prev_scene else None

        # Generate reactions
        reactions = []
        reactions.append(self._simulate_casual(scene, memory_scan, sound_advisory))
        reactions.append(self._simulate_cinephile(scene, memory_scan, sound_advisory))
        reactions.append(self._simulate_genre_fan(scene, memory_scan, sound_advisory))
        reactions.append(self._simulate_festival_jury(scene, memory_scan, sound_advisory))

        interpretation_variance = self._determine_variance(reactions)
        co_director_note = self._generate_synthesis(reactions, scene)

        return SceneAudienceSimulation(
            scene_id=scene_id,
            audience_reactions=reactions,
            interpretation_variance=interpretation_variance,
            co_director_note=co_director_note
        )

    async def simulate_project(self, project_id: str) -> ProjectAudienceSimulation:
        project = project_store.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        summary = project.get("execution_summary") if isinstance(project.get("execution_summary"), dict) else {}
        scenes = summary.get("scenes") if isinstance(summary.get("scenes"), list) else []
        scene_sims = []
        for scene in scenes:
            scene_id = str(scene.get("scene_id"))
            sim = await self.simulate_scene(project_id, scene_id)
            scene_sims.append(sim)

        co_director_note = "Across the full sequence, the emotional arc builds with deliberate rhythm. The early accessibility for casual viewers gives way to deeper thematic weight that will satisfy jury perspectives in the final act."

        # Aggregate reactions for the project
        audience_reactions = [
            AudienceReaction(
                audience_type="Casual audience",
                likely_reaction="The clear emotional beats provide a steady hook throughout the sequence.",
                reasoning="Consistent emotional grounding across all scenes keeps the narrative accessible.",
                watch_out="Some slower transitions might test patience if the payoff isn't clear."
            ),
            AudienceReaction(
                audience_type="Cinephiles",
                likely_reaction="Will appreciate the evolving visual motifs and structural rhymes.",
                reasoning="The deliberate repetition of thematic elements builds a strong cinematic language.",
                watch_out="Expectation of a non-conventional resolution increases as the sequence progresses."
            ),
            AudienceReaction(
                audience_type="Genre fans",
                likely_reaction="Satisfied by the confident handling of genre tropes.",
                reasoning="The sequence respects genre boundaries while allowing for stylistic flourishes.",
                watch_out="May predict the outcome if the subversions aren't bold enough."
            ),
            AudienceReaction(
                audience_type="Festival juries",
                likely_reaction="Will focus on the overarching thematic cohesion and cultural resonance.",
                reasoning="The sequence moves beyond individual moments to form a unified thematic statement.",
                watch_out="Needs to maintain formal rigor throughout to avoid feeling episodic."
            )
        ]

        return ProjectAudienceSimulation(
            project_id=project_id,
            audience_reactions=audience_reactions,
            scene_simulations=scene_sims,
            co_director_note=co_director_note
        )

    def _simulate_casual(self, scene: Dict, memory_scan: Dict, sound: Any) -> AudienceReaction:
        desc = scene.get("description", "").lower()
        has_dialogue = len(scene.get("dialogue_lines", [])) > 0
        
        likely_reaction = "Likely to engage with the immediate emotional stakes"
        if "action" in desc or "tense" in sound.mood:
            likely_reaction = "Will feel the tension and drive of the moment"
        elif "sad" in desc or "melancholic" in sound.mood:
            likely_reaction = "Will connect with the overt emotional vulnerability"
            
        reasoning = f"The scene uses clear {sound.mood} cues and focused action to ground the viewer."
        
        watch_out = "May lose interest if the subtextual silence lasts too long without a clear plot beat."
        if not has_dialogue:
            watch_out = "The lack of dialogue may cause confusion about the protagonist's specific intent."

        return AudienceReaction(
            audience_type="Casual audience",
            likely_reaction=likely_reaction,
            reasoning=reasoning,
            watch_out=watch_out
        )

    def _simulate_cinephile(self, scene: Dict, memory_scan: Dict, sound: Any) -> AudienceReaction:
        callbacks = memory_scan.get("callbacks", [])
        has_motifs = any(c.get("kind") in ["symbols", "motifs"] for c in callbacks)
        
        likely_reaction = "Will appreciate the visual composition and use of sound as a narrative tool"
        if has_motifs:
            likely_reaction = "Will register the thematic callbacks and visual rhymes surfacing here"
            
        reasoning = "Audiences attuned to film language will pick up on the deliberate pacing and atmospheric sound design."
        
        watch_out = "Might find the emotional beats too conventional if not supported by strong visual subtext."

        return AudienceReaction(
            audience_type="Cinephiles",
            likely_reaction=likely_reaction,
            reasoning=reasoning,
            watch_out=watch_out
        )

    def _simulate_genre_fan(self, scene: Dict, memory_scan: Dict, sound: Any) -> AudienceReaction:
        mood = sound.mood
        
        likely_reaction = f"Will appreciate the adherence to {mood} tropes while looking for a unique spin"
        reasoning = f"The {mood} atmosphere fulfills genre expectations for this type of sequence."
        
        watch_out = "Risk of feeling 'seen it before' if the resolution of the beat follows the most predictable path."

        return AudienceReaction(
            audience_type="Genre fans",
            likely_reaction=likely_reaction,
            reasoning=reasoning,
            watch_out=watch_out
        )

    def _simulate_festival_jury(self, scene: Dict, memory_scan: Dict, sound: Any) -> AudienceReaction:
        callbacks = memory_scan.get("callbacks", [])
        has_themes = any(c.get("kind") == "themes" for c in callbacks)
        
        likely_reaction = "Will look for the thematic weight and cultural resonance of the choice made here"
        if has_themes:
            likely_reaction = "Will appreciate the refusal to provide easy answers, favoring thematic ambiguity"
            
        reasoning = "The deliberate use of silence and thematic callbacks positions this as a work that trusts its audience."
        
        watch_out = "Might view overtly conventional pacing as a lack of formal ambition."

        return AudienceReaction(
            audience_type="Festival juries",
            likely_reaction=likely_reaction,
            reasoning=reasoning,
            watch_out=watch_out
        )

    def _determine_variance(self, reactions: List[AudienceReaction]) -> str:
        return "The primary variance lies between casual viewers seeking closure and juries who will value the intentional ambiguity."

    def _generate_synthesis(self, reactions: List[AudienceReaction], scene: Dict) -> str:
        return "The scene balances emotional accessibility with thematic depth, though we should be careful not to let the subtext become too opaque for casual viewers."

audience_simulator_service = AudienceSimulatorService()

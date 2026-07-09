"""
Pitch Deck Service.

Auto-drafts a visual pitch document by pulling from Film DNA, character maps,
and arc analysis.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("studio-pitch-deck")


class PitchDeckService:
    """Service for generating pitch decks."""

    def __init__(self, storage=None, llm_client=None):
        self._storage = storage
        self._llm_client = llm_client

    def _now_iso(self) -> str:
        """Return current time in ISO format."""
        return datetime.now().isoformat()

    async def generate_pitch_deck(
        self,
        project_id: str,
        target_audience: str = "general",
    ) -> dict:
        """
        Generate a pitch deck for a project.

        Args:
            project_id: The project identifier.
            target_audience: Target audience - "festival", "investor", or "general".

        Returns:
            Pitch deck dict with slides, logline, tone statement, and honest note.
        """
        deck_id = f"deck_{uuid.uuid4().hex[:12]}"
        generated_at = self._now_iso()
        uncertainty_notes = []

        if not self._storage:
            raise ValueError("Storage not configured")

        # Load project data
        project = self._storage.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Load Film DNA
        film_dna = None
        try:
            film_dna = self._storage.load_film_dna(project_id)
        except Exception as e:
            logger.debug(f"Could not load Film DNA: {e}")
            uncertainty_notes.append("Film DNA not available - some slides may be incomplete")

        # Load director intent
        director_intent = None
        try:
            director_intent = self._storage.load_director_intent(project_id)
        except Exception as e:
            logger.debug(f"Could not load director intent: {e}")

        # Load continuity graph for character data
        continuity_graph = None
        try:
            continuity_graph = self._storage.load_continuity_graph(project_id)
        except Exception as e:
            logger.debug(f"Could not load continuity graph: {e}")

        # Load arc completeness
        arc_completeness = None
        try:
            from app.services.continuity_intelligence_service import (
                continuity_intelligence_service,
            )
            arc_completeness = await continuity_intelligence_service.check_arc_completeness(
                project_id
            )
        except Exception as e:
            logger.debug(f"Could not load arc completeness: {e}")
            uncertainty_notes.append("Arc analysis not available")

        # Load latest export package for production note
        export_package = None
        try:
            packages = self._storage.list_export_packages(project_id, limit=1)
            if packages:
                export_package = self._storage.load_export_package(packages[0]["package_id"])
        except Exception as e:
            logger.debug(f"Could not load export package: {e}")

        # Synthesize logline
        logline = await self._synthesize_logline(
            project, film_dna, director_intent, uncertainty_notes
        )

        # Synthesize tone statement
        tone_statement = await self._synthesize_tone_statement(
            film_dna, director_intent, uncertainty_notes
        )

        # Generate slides
        slides = []
        slide_number = 1

        # Slide 1: Logline
        slides.append({
            "slide_number": slide_number,
            "title": "Logline",
            "type": "logline",
            "headline": logline,
            "body": "A one-sentence summary of the film's core story.",
            "visual_suggestion": "Opening frame or key visual that captures the film's essence",
            "data_source": "synthesized",
        })
        slide_number += 1

        # Slide 2: Concept
        concept_slide = await self._generate_concept_slide(
            slide_number, project, film_dna, director_intent
        )
        slides.append(concept_slide)
        slide_number += 1

        # Slide 3: Visual Language
        visual_language_slide = await self._generate_visual_language_slide(
            slide_number, film_dna, director_intent
        )
        slides.append(visual_language_slide)
        slide_number += 1

        # Character slides (one per major character with 3+ scenes)
        character_slides = await self._generate_character_slides(
            slide_number, continuity_graph, arc_completeness
        )
        slides.extend(character_slides)
        slide_number += len(character_slides)

        # Emotional Arc slide
        arc_slide = await self._generate_arc_slide(
            slide_number, arc_completeness, film_dna
        )
        slides.append(arc_slide)
        slide_number += 1

        # Tone slide
        tone_slide = await self._generate_tone_slide(
            slide_number, tone_statement, film_dna, director_intent
        )
        slides.append(tone_slide)
        slide_number += 1

        # Production Note slide
        production_slide = self._generate_production_note_slide(
            slide_number, export_package
        )
        slides.append(production_slide)

        # Generate advisory
        advisory = self._generate_advisory(target_audience, uncertainty_notes)

        # Generate honest note
        honest_note = "This is an AI-drafted starting point from available project data. Review and edit before sharing."

        deck = {
            "deck_id": deck_id,
            "project_id": project_id,
            "target_audience": target_audience,
            "slides": slides,
            "logline": logline,
            "tone_statement": tone_statement,
            "advisory": advisory,
            "uncertainty_notes": uncertainty_notes,
            "honest_note": honest_note,
            "generated_at": generated_at,
        }

        # Store deck
        self._storage.save_pitch_deck(project_id, deck)

        return deck

    async def _synthesize_logline(
        self,
        project: Any,
        film_dna: Optional[dict],
        director_intent: Optional[dict],
        uncertainty_notes: List[str],
    ) -> str:
        """Synthesize a one-sentence logline."""
        # Try to get from Film DNA first
        if film_dna and film_dna.get("logline"):
            return film_dna["logline"]

        # Try to get from director intent
        if director_intent and director_intent.get("logline"):
            return director_intent["logline"]

        # Try to synthesize from script text
        project_data = project.model_dump(mode='json')
        script_text = project_data.get("script_text", "")
        
        if script_text and len(script_text) > 20:
            # Use Claude to synthesize if available
            if self._llm_client:
                try:
                    prompt = f"Write a one-sentence logline for this film:\n\n{script_text[:500]}"
                    response = await self._llm_client.generate(prompt, max_tokens=100)
                    if response:
                        return response.strip()
                except Exception as e:
                    logger.debug(f"Could not synthesize logline with LLM: {e}")

            # Fallback: use first sentence of script
            first_sentence = script_text.split('.')[0].strip()
            if len(first_sentence) > 10:
                uncertainty_notes.append("Logline synthesized from script text - may need refinement")
                return first_sentence + "."

        # Last resort
        uncertainty_notes.append("No logline available - please add manually")
        return project_data.get("title", "Untitled Film")

    async def _synthesize_tone_statement(
        self,
        film_dna: Optional[dict],
        director_intent: Optional[dict],
        uncertainty_notes: List[str],
    ) -> str:
        """Synthesize a 1-2 sentence tone/feel description."""
        # Try to get from Film DNA
        if film_dna:
            primary_tone = film_dna.get("primary_tone")
            secondary_tone = film_dna.get("secondary_tone")
            if primary_tone:
                statement = f"The film has a {primary_tone} tone"
                if secondary_tone:
                    statement += f" with {secondary_tone} undertones"
                statement += "."
                return statement

        # Try to get from director intent
        if director_intent:
            tone_notes = director_intent.get("tone_notes", "")
            if tone_notes and len(tone_notes) > 10:
                # Take first 1-2 sentences
                sentences = tone_notes.split('.')[:2]
                return '. '.join(s.strip() for s in sentences if s.strip()) + '.'

        uncertainty_notes.append("Tone statement not available - please add manually")
        return "The film's tone and emotional feel are being developed."

    async def _generate_concept_slide(
        self,
        slide_number: int,
        project: Any,
        film_dna: Optional[dict],
        director_intent: Optional[dict],
    ) -> dict:
        """Generate the concept slide."""
        project_data = project.model_dump(mode='json')
        
        # Try to get concept from director intent
        body = ""
        data_source = "synthesized"
        
        if director_intent and director_intent.get("concept"):
            body = director_intent["concept"]
            data_source = "director_intent"
        elif film_dna and film_dna.get("concept"):
            body = film_dna["concept"]
            data_source = "film_dna"
        else:
            # Fallback to script text summary
            script_text = project_data.get("script_text", "")
            if script_text and len(script_text) > 50:
                # Take first few sentences
                sentences = script_text.split('.')[:3]
                body = '. '.join(s.strip() for s in sentences if s.strip()) + '.'
            else:
                body = "The film explores themes and emotions that are being developed during production."

        return {
            "slide_number": slide_number,
            "title": "Concept",
            "type": "concept",
            "headline": "What This Film Is About",
            "body": body[:300],  # Limit to ~2-4 sentences
            "visual_suggestion": "Key scene or moment that captures the emotional core",
            "data_source": data_source,
        }

    async def _generate_visual_language_slide(
        self,
        slide_number: int,
        film_dna: Optional[dict],
        director_intent: Optional[dict],
    ) -> dict:
        """Generate the visual language slide."""
        body_parts = []
        data_source = "synthesized"

        if film_dna:
            # Get dominant motifs
            motifs = film_dna.get("dominant_motifs", [])
            if motifs:
                motif_text = ", ".join(motifs[:3])
                body_parts.append(f"Dominant visual motifs: {motif_text}")
                data_source = "film_dna"

            # Get lighting character
            lighting = film_dna.get("lighting_character")
            if lighting:
                body_parts.append(f"Lighting: {lighting}")

        if director_intent:
            # Get visual references
            visual_refs = director_intent.get("visual_references", [])
            if visual_refs:
                refs_text = ", ".join(visual_refs[:3])
                body_parts.append(f"Visual references: {refs_text}")
                if data_source == "synthesized":
                    data_source = "director_intent"

        if not body_parts:
            body = "The visual language is being developed through production and will reflect the film's emotional journey."
        else:
            body = ". ".join(body_parts) + "."

        return {
            "slide_number": slide_number,
            "title": "Visual Language",
            "type": "visual_language",
            "headline": "How The Film Looks and Feels",
            "body": body,
            "visual_suggestion": "Montage of key frames showing visual style",
            "data_source": data_source,
        }

    async def _generate_character_slides(
        self,
        start_slide_number: int,
        continuity_graph: Optional[dict],
        arc_completeness: Optional[dict],
    ) -> List[dict]:
        """Generate character slides for major characters (3+ scenes)."""
        slides = []
        
        if not continuity_graph:
            return slides

        # Extract character presence from graph
        character_presence: Dict[str, int] = {}
        for node in continuity_graph.get("nodes", []):
            if isinstance(node, dict) and node.get("element_type") == "character":
                char_name = node.get("element_id", "")
                scene_id = node.get("scene_id", "")
                if char_name and scene_id:
                    character_presence[char_name] = character_presence.get(char_name, 0) + 1

        # Filter to major characters (3+ scenes)
        major_characters = {
            name: count for name, count in character_presence.items() if count >= 3
        }

        # Sort by scene count (descending)
        sorted_characters = sorted(
            major_characters.items(), key=lambda x: x[1], reverse=True
        )

        slide_number = start_slide_number
        for char_name, scene_count in sorted_characters:
            # Try to get arc summary from arc_completeness
            arc_summary = ""
            data_source = "character_journey"
            
            if arc_completeness:
                character_arcs = arc_completeness.get("character_arcs", [])
                for arc in character_arcs:
                    if isinstance(arc, dict) and arc.get("character_name") == char_name:
                        arc_summary = arc.get("arc_summary", "")
                        if arc_summary:
                            data_source = "arc_analysis"
                        break

            if not arc_summary:
                arc_summary = f"Appears in {scene_count} scenes. Character arc is being developed through production."

            slides.append({
                "slide_number": slide_number,
                "title": char_name,
                "type": "character",
                "headline": char_name,
                "body": arc_summary[:300],
                "visual_suggestion": f"Key frame featuring {char_name}",
                "data_source": data_source,
            })
            slide_number += 1

        return slides

    async def _generate_arc_slide(
        self,
        slide_number: int,
        arc_completeness: Optional[dict],
        film_dna: Optional[dict],
    ) -> dict:
        """Generate the emotional arc slide."""
        body_parts = []
        data_source = "arc_analysis"

        if arc_completeness:
            # Get arc shape
            arc_shape = arc_completeness.get("arc_shape", "")
            if arc_shape:
                body_parts.append(f"Arc shape: {arc_shape}")

            # Get resolution read
            resolution = arc_completeness.get("resolution_read", "")
            if resolution:
                body_parts.append(f"Resolution: {resolution}")

            # Get completeness assessment
            completeness = arc_completeness.get("completeness_assessment", "")
            if completeness:
                body_parts.append(completeness)

        if not body_parts and film_dna:
            # Fallback to Film DNA
            emotional_arc = film_dna.get("emotional_arc", "")
            if emotional_arc:
                body_parts.append(emotional_arc)
                data_source = "film_dna"

        if not body_parts:
            body = "The emotional arc is being shaped through production and will guide the audience's journey."
            data_source = "synthesized"
        else:
            body = ". ".join(body_parts) + "."

        return {
            "slide_number": slide_number,
            "title": "Emotional Arc",
            "type": "arc",
            "headline": "The Emotional Journey",
            "body": body[:300],
            "visual_suggestion": "Arc diagram or key emotional beats",
            "data_source": data_source,
        }

    async def _generate_tone_slide(
        self,
        slide_number: int,
        tone_statement: str,
        film_dna: Optional[dict],
        director_intent: Optional[dict],
    ) -> dict:
        """Generate the tone slide."""
        body_parts = [tone_statement]
        data_source = "synthesized"

        # Add references from director intent
        if director_intent:
            tone_refs = director_intent.get("tone_references", [])
            if tone_refs:
                refs_text = ", ".join(tone_refs[:3])
                body_parts.append(f"References: {refs_text}")
                data_source = "director_intent"

        body = " ".join(body_parts)

        return {
            "slide_number": slide_number,
            "title": "Tone",
            "type": "tone",
            "headline": "The Film's Emotional Feel",
            "body": body,
            "visual_suggestion": "Frame that captures the film's tone",
            "data_source": data_source,
        }

    def _generate_production_note_slide(
        self,
        slide_number: int,
        export_package: Optional[dict],
    ) -> dict:
        """Generate the production note slide."""
        if export_package:
            honest_assembly_note = export_package.get(
                "honest_assembly_note",
                "Production package available"
            )
            body = honest_assembly_note
            data_source = "export_package"
        else:
            body = "In production. Export package will be available upon completion."
            data_source = "synthesized"

        return {
            "slide_number": slide_number,
            "title": "Production Status",
            "type": "production_note",
            "headline": "Current Status",
            "body": body,
            "visual_suggestion": None,
            "data_source": data_source,
        }

    def _generate_advisory(
        self,
        target_audience: str,
        uncertainty_notes: List[str],
    ) -> str:
        """Generate advisory message."""
        if uncertainty_notes:
            return f"This pitch deck was generated for {target_audience} audience. Some data was unavailable and may need manual completion."
        else:
            return f"This pitch deck was generated for {target_audience} audience from available project data."


# Singleton instance
pitch_deck_service = PitchDeckService()

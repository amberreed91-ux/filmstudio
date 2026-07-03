import logging
import json
from typing import Dict, List, Optional, Any
from app.llm_client import call_llm
from app.data import get_storage

logger = logging.getLogger(__name__)


class CharacterExtractionService:
    """Extracts character details from script content using Groq LLM."""
    
    def __init__(self):
        self.storage = get_storage("sqlite")
    
    async def extract_and_update_characters(
        self, 
        project_id: str, 
        script_text: str, 
        scene_characters: List[str]
    ) -> Dict[str, Any]:
        """
        Extract character details from script and update character_memories table.
        Only updates fields that are currently empty - never overwrites existing content.
        
        Args:
            project_id: Project identifier
            script_text: Full script content
            scene_characters: List of character names found in scenes
            
        Returns:
            Dict with extraction results
        """
        if not script_text or not script_text.strip():
            logger.info(f"SCRIPT_EMPTY | project={project_id} | skipping character extraction")
            return {"updated": 0, "skipped": 0, "errors": []}
        
        if not scene_characters:
            logger.info(f"NO_CHARACTERS | project={project_id} | skipping character extraction")
            return {"updated": 0, "skipped": 0, "errors": []}
        
        # Get existing character memories for this project
        existing_chars = self.storage.get_all_character_memories(project_id)
        existing_by_name = {
            char.get("character_name", "").upper(): char 
            for char in existing_chars
        }
        
        results = {"updated": 0, "skipped": 0, "errors": []}
        
        for char_name in scene_characters:
            char_key = char_name.strip().upper()
            if not char_key:
                continue
            
            # Check if character already exists in memories
            existing = existing_by_name.get(char_key)
            
            # Generate character_id if new character
            if existing:
                character_id = existing.get("character_id")
            else:
                character_id = f"char_{char_key.lower()}"
            
            try:
                # Extract character details from script using Groq
                extracted = await self._extract_character_details(
                    script_text=script_text,
                    character_name=char_name
                )
                
                # Build update payload - only include fields that are empty in existing record
                update_payload = {
                    "project_id": project_id,
                    "character_id": character_id,
                    "character_name": char_name,
                }
                
                fields_to_update = [
                    "appearance_traits",
                    "personality_traits", 
                    "speech_patterns",
                    "mannerisms",
                    "physical_quirks",
                    "wardrobe",
                    "backstory_notes"
                ]
                
                has_updates = False
                for field in fields_to_update:
                    existing_value = existing.get(field) if existing else None
                    extracted_value = extracted.get(field)
                    
                    # Only update if existing is empty/None and extracted has content
                    if not existing_value and extracted_value:
                        update_payload[field] = extracted_value
                        has_updates = True
                    elif existing:
                        # Keep existing value
                        update_payload[field] = existing_value
                    else:
                        # No existing, no extracted - set to empty default
                        update_payload[field] = [] if field != "backstory_notes" else ""
                
                # Save to storage
                if has_updates or not existing:
                    self.storage.save_character_memory(update_payload)
                    results["updated"] += 1
                    logger.info(
                        f"CHARACTER_UPDATED | project={project_id} | character={char_name} | "
                        f"fields_updated={sum(1 for f in fields_to_update if update_payload.get(f) and (not existing or not existing.get(f)))}"
                    )
                else:
                    results["skipped"] += 1
                    logger.info(f"CHARACTER_SKIPPED | project={project_id} | character={char_name} | all_fields_populated")
                    
            except Exception as exc:
                error_msg = f"Failed to extract/update character {char_name}: {exc}"
                logger.error(f"CHARACTER_EXTRACTION_ERROR | project={project_id} | character={char_name} | error={exc}")
                results["errors"].append(error_msg)
        
        logger.info(
            f"CHARACTER_EXTRACTION_COMPLETE | project={project_id} | "
            f"updated={results['updated']} | skipped={results['skipped']} | errors={len(results['errors'])}"
        )
        return results
    
    async def _extract_character_details(
        self, 
        script_text: str, 
        character_name: str
    ) -> Dict[str, Any]:
        """
        Use Groq LLM to extract character details from script.
        
        Returns dict with fields: appearance_traits, personality_traits, speech_patterns,
        mannerisms, physical_quirks, wardrobe, backstory_notes
        """
        system_prompt = """You are a script analysis assistant. Extract character details from screenplay text.
Focus on physical descriptions, personality notes, and behavioral details mentioned in the script.
Return ONLY valid JSON with these exact fields:
- appearance_traits: list of strings describing physical appearance
- personality_traits: list of strings describing personality
- speech_patterns: list of strings describing how they speak
- mannerisms: list of strings describing behavioral habits
- physical_quirks: list of strings describing unique physical behaviors
- wardrobe: list of strings describing clothing/style
- backstory_notes: string summarizing any backstory revealed
If a detail is not mentioned in the script, return empty array/string for that field.
Be concise and specific. Do not invent details not supported by the text."""

        user_message = f"""Extract character details for "{character_name}" from this script:

{script_text}

Return only the JSON object with the specified fields."""

        try:
            response = await call_llm(
                system_prompt=system_prompt,
                message=user_message,
                max_tokens=1024
            )
            
            # Parse JSON response
            extracted = json.loads(response)
            
            # Validate and normalize structure
            result = {
                "appearance_traits": self._ensure_list(extracted.get("appearance_traits")),
                "personality_traits": self._ensure_list(extracted.get("personality_traits")),
                "speech_patterns": self._ensure_list(extracted.get("speech_patterns")),
                "mannerisms": self._ensure_list(extracted.get("mannerisms")),
                "physical_quirks": self._ensure_list(extracted.get("physical_quirks")),
                "wardrobe": self._ensure_list(extracted.get("wardrobe")),
                "backstory_notes": str(extracted.get("backstory_notes", "")) if extracted.get("backstory_notes") else ""
            }
            
            return result
            
        except json.JSONDecodeError as exc:
            logger.warning(f"JSON_PARSE_ERROR | character={character_name} | error={exc}")
            return self._empty_extraction()
        except Exception as exc:
            logger.warning(f"LLM_EXTRACTION_ERROR | character={character_name} | error={exc}")
            return self._empty_extraction()
    
    def _ensure_list(self, value: Any) -> List[str]:
        """Ensure value is a list of strings."""
        if isinstance(value, list):
            return [str(item).strip() for item in value if item and str(item).strip()]
        return []
    
    def _empty_extraction(self) -> Dict[str, Any]:
        """Return empty extraction structure."""
        return {
            "appearance_traits": [],
            "personality_traits": [],
            "speech_patterns": [],
            "mannerisms": [],
            "physical_quirks": [],
            "wardrobe": [],
            "backstory_notes": ""
        }


character_extraction_service = CharacterExtractionService()

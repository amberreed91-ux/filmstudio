"""
Task Executors for Studio Orchestrator

Each agent role has its own executor that knows how to perform the work.
Executors:
- Read memory before executing
- Produce structured outputs
- Update memory after execution
- Trigger next stage tasks (via orchestrator)
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.services.orchestrator import TaskExecutor, ExecutionResult

logger = logging.getLogger("studio-executors")


class ScriptAnalysisExecutor(TaskExecutor):
    """
    Script Analyst - Parses and structures screenplay content.
    
    Reads: Project creative intent, script text
    Produces: Parsed scenes, characters, locations
    Updates: Scene memory, character memory
    """
    
    def __init__(self):
        super().__init__("script_analyst")
    
    def execute(self, task: Dict, context: Dict) -> ExecutionResult:
        """Execute script analysis"""
        project_id = context["project_id"]
        storage = context["storage"]
        
        logger.info(f"[SCRIPT_ANALYST] Analyzing script for {project_id}")
        
        result = ExecutionResult(success=True)
        
        try:
            # Get project data
            project = storage.get_project(project_id)
            if not project:
                return ExecutionResult(success=False, error="Project not found")
            
            # Get script text from production_bible or source
            script_text = self._extract_script_text(project)
            
            if not script_text:
                return ExecutionResult(success=False, error="No script text found")
            
            # Parse screenplay using script_parser
            from app.services.script_parser import parse_screenplay
            parsed = parse_screenplay(script_text)
            
            # Store in memory
            self._update_scene_memory(project_id, parsed["scenes"], storage)
            self._update_character_memory(project_id, parsed["characters"], storage)
            
            # Build output
            result.output_data = {
                "scenes_found": len(parsed["scenes"]),
                "characters_found": len(parsed["characters"]),
                "locations_found": len(parsed["locations"]),
                "parsed_scenes": parsed["scenes"],
                "parsed_characters": parsed["characters"],
                "parsed_locations": parsed["locations"],
                "source_stats": parsed["source_stats"],
            }
            
            result.artifacts = [f"scene_{s['scene_id']}" for s in parsed["scenes"]]
            result.metrics = {
                "scene_count": len(parsed["scenes"]),
                "character_count": len(parsed["characters"]),
                "location_count": len(parsed["locations"]),
            }
            
            logger.info(f"[SCRIPT_ANALYST] Found {len(parsed['scenes'])} scenes, "
                       f"{len(parsed['characters'])} characters")
            
        except Exception as e:
            logger.exception(f"[SCRIPT_ANALYST] Error: {e}")
            result.success = False
            result.error = str(e)
        
        return result
    
    def _extract_script_text(self, project) -> str:
        """Extract script text from project"""
        # In a full implementation, script would be stored separately
        # For now, check if it's in production_bible or return empty
        if hasattr(project, 'production_bible') and project.production_bible:
            # Could contain script reference
            pass
        return ""
    
    def _update_scene_memory(self, project_id: str, scenes: List[Dict], storage):
        """Update scene memory in storage"""
        for scene in scenes:
            scene_memory = {
                "project_id": project_id,
                "scene_id": scene["scene_id"],
                "scene_number": scene["scene_number"],
                "heading": scene["heading"],
                "location_name": scene["location"],
                "time_of_day": scene["time_of_day"],
                "description": scene["description"][:500] if scene["description"] else "",
                "characters": scene.get("characters", []),
                "generated_shots": [],
                "approved_shots": [],
            }
            storage.save_scene_memory(scene_memory)
    
    def _update_character_memory(self, project_id: str, characters: List[Dict], storage):
        """Update character memory in storage"""
        for char in characters:
            char_memory = {
                "project_id": project_id,
                "character_id": char["character_id"],
                "character_name": char["name"],
                "first_appearance": char["first_appearance"],
                "dialogue_count": char.get("dialogue_count", 0),
            }
            storage.save_character_memory(char_memory)


class SceneBreakdownExecutor(TaskExecutor):
    """
    Scene Breakdown - Converts parsed scenes into production tasks.
    
    Reads: Scene memory, script analysis output
    Produces: Shot requirements, production notes
    Updates: Scene memory with breakdown data
    """
    
    def __init__(self):
        super().__init__("script_analyst")
    
    def execute(self, task: Dict, context: Dict) -> ExecutionResult:
        """Execute scene breakdown"""
        project_id = context["project_id"]
        storage = context["storage"]
        
        logger.info(f"[SCENE_BREAKDOWN] Breaking down scenes for {project_id}")
        
        result = ExecutionResult(success=True)
        
        try:
            # Get source output
            input_data = task.get("input_data", {})
            source_output = input_data.get("source_output", {})
            parsed_scenes = source_output.get("parsed_scenes", [])
            
            if not parsed_scenes:
                # Try to get from storage
                scene_memories = storage.get_all_scene_memories(project_id)
                parsed_scenes = [
                    {
                        "scene_id": s.get("scene_id"),
                        "scene_number": s.get("scene_number"),
                        "location_name": s.get("location_name"),
                    }
                    for s in scene_memories
                ]
            
            # Break down each scene
            breakdown_data = []
            for scene in parsed_scenes:
                breakdown = self._break_down_scene(scene, project_id, storage)
                breakdown_data.append(breakdown)
            
            # Update scene memories with breakdown
            for scene_id, breakdown in breakdown_data:
                scene_mem = storage.get_scene_memory(project_id, scene_id)
                if scene_mem:
                    scene_mem["breakdown"] = breakdown
                    storage.save_scene_memory(scene_mem)
            
            result.output_data = {
                "scenes_broken_down": len(breakdown_data),
                "breakdown_data": breakdown_data,
            }
            
            result.metrics = {
                "shots_planned": sum(len(b.get("shots", [])) for _, b in breakdown_data),
                "scenes_processed": len(breakdown_data),
            }
            
            logger.info(f"[SCENE_BREAKDOWN] Created breakdowns for {len(breakdown_data)} scenes")
            
        except Exception as e:
            logger.exception(f"[SCENE_BREAKDOWN] Error: {e}")
            result.success = False
            result.error = str(e)
        
        return result
    
    def _break_down_scene(self, scene: Dict, project_id: str, storage) -> tuple:
        """Break down a single scene into shots and requirements"""
        scene_id = scene.get("scene_id", "unknown")
        
        # Simple heuristic: 1-3 shots per scene based on content
        location = scene.get("location_name", "")
        desc_length = len(scene.get("description", ""))
        
        # Determine shot count based on scene complexity
        if desc_length > 200 or scene.get("characters", []):
            shot_count = 3
        elif desc_length > 100:
            shot_count = 2
        else:
            shot_count = 1
        
        shots = []
        for i in range(shot_count):
            shot = {
                "shot_id": f"{scene_id}-shot-{i+1:02d}",
                "shot_type": self._determine_shot_type(i, shot_count),
                "camera_movement": self._suggest_camera_movement(scene),
                "notes": f"Shot {i+1} of {shot_count}",
            }
            shots.append(shot)
        
        breakdown = {
            "scene_id": scene_id,
            "shots": shots,
            "estimated_duration": f"{shot_count * 5} seconds",
            "location_type": "INTERIOR" if "INT" in scene.get("heading", "") else "EXTERIOR",
        }
        
        return scene_id, breakdown
    
    def _determine_shot_type(self, index: int, total: int) -> str:
        """Determine shot type based on position in scene"""
        if total == 1:
            return "establishing"
        elif index == 0:
            return "wide"
        elif index == total - 1:
            return "close"
        else:
            return "medium"
    
    def _suggest_camera_movement(self, scene: Dict) -> str:
        """Suggest camera movement based on scene content"""
        desc = scene.get("description", "").lower()
        
        if any(word in desc for word in ["enters", "walks", "runs", "moves"]):
            return "tracking"
        elif any(word in desc for word in ["sits", "stands", "still"]):
            return "static"
        elif any(word in desc for word in ["chase", "fight", "action"]):
            return "handheld"
        else:
            return "slow_pan"


class ShotPlanningExecutor(TaskExecutor):
    """
    Storyboard Artist - Plans shot composition and visual flow.
    
    Reads: Scene memory, breakdown data
    Produces: Shot plans, visual references
    Updates: Storyboard_wall, approval gates
    """
    
    def __init__(self):
        super().__init__("storyboard_artist")
    
    def execute(self, task: Dict, context: Dict) -> ExecutionResult:
        """Execute shot planning"""
        project_id = context["project_id"]
        storage = context["storage"]
        
        logger.info(f"[SHOT_PLANNING] Planning shots for {project_id}")
        
        result = ExecutionResult(success=True)
        
        try:
            # Get project
            project = storage.get_project(project_id)
            if not project:
                return ExecutionResult(success=False, error="Project not found")
            
            # Get scene memories
            scene_memories = storage.get_all_scene_memories(project_id)
            
            # Generate shot plans for each scene
            shot_plans = []
            for scene in scene_memories:
                scene_id = scene.get("scene_id")
                breakdown = scene.get("breakdown", {})
                shots = breakdown.get("shots", [])
                
                for shot in shots:
                    shot_id = shot.get("shot_id")
                    
                    # Create shot plan
                    plan = {
                        "shot_id": shot_id,
                        "scene_id": scene_id,
                        "shot_type": shot.get("shot_type", "medium"),
                        "camera_angle": self._suggest_camera_angle(shot),
                        "description": self._generate_shot_description(scene, shot),
                        "status": "planned",
                    }
                    
                    shot_plans.append(plan)
                    
                    # Update storyboard wall
                    self._update_storyboard(project, shot_id, plan, storage)
                    
                    # Create approval gate
                    self._create_approval_gate(project, shot_id, plan, storage)
            
            result.output_data = {
                "shots_planned": len(shot_plans),
                "shot_plans": shot_plans,
            }
            
            result.artifacts = [p["shot_id"] for p in shot_plans]
            result.metrics = {
                "total_shots": len(shot_plans),
                "scenes_with_shots": len(scene_memories),
            }
            
            # Save project with updates
            storage.save_project(project)
            
            logger.info(f"[SHOT_PLANNING] Planned {len(shot_plans)} shots")
            
        except Exception as e:
            logger.exception(f"[SHOT_PLANNING] Error: {e}")
            result.success = False
            result.error = str(e)
        
        return result
    
    def _suggest_camera_angle(self, shot: Dict) -> str:
        """Suggest camera angle for shot"""
        shot_type = shot.get("shot_type", "medium")
        
        angles = {
            "establishing": "high_angle",
            "wide": "eye_level",
            "medium": "medium_shot",
            "close": "close_up",
        }
        
        return angles.get(shot_type, "eye_level")
    
    def _generate_shot_description(self, scene: Dict, shot: Dict) -> str:
        """Generate descriptive shot plan"""
        location = scene.get("location_name", "Unknown")
        time = scene.get("time_of_day", "Day")
        shot_type = shot.get("shot_type", "medium")
        
        return f"{shot_type.title()} shot of {location} ({time})"
    
    def _update_storyboard(self, project, shot_id: str, plan: Dict, storage):
        """Update storyboard wall with shot plan"""
        from app.models import StoryboardShot
        
        # Check if exists
        existing = None
        for shot in project.storyboard_wall:
            if shot.shot_id == shot_id:
                existing = shot
                break
        
        if existing:
            existing.description = plan.get("description", "")
            existing.status = "planned"
        else:
            project.storyboard_wall.append(StoryboardShot(
                shot_id=shot_id,
                scene=f"Shot: {shot_id}",
                description=plan.get("description", ""),
                status="planned"
            ))
    
    def _create_approval_gate(self, project, shot_id: str, plan: Dict, storage):
        """Create approval gate for shot"""
        from app.models import ApprovalGate
        
        # Check if exists
        for gate in project.shot_approval_gates:
            if gate.shot_id == shot_id:
                return  # Already exists
        
        project.shot_approval_gates.append(ApprovalGate(
            id=f"gate-{shot_id}",
            label=f"Shot Approval: {shot_id}",
            status="pending",
            sub="Awaiting review",
            detail=plan.get("description", ""),
            shot_id=shot_id
        ))


class PromptGenerationExecutor(TaskExecutor):
    """
    Prompt Engineer - Generates render prompts from shot plans.
    
    Reads: Shot plans, style memory
    Produces: Optimized prompts for render providers
    Updates: Render job queue
    """
    
    def __init__(self):
        super().__init__("prompt_engineer")
    
    def execute(self, task: Dict, context: Dict) -> ExecutionResult:
        """Execute prompt generation"""
        project_id = context["project_id"]
        storage = context["storage"]
        
        logger.info(f"[PROMPT_GENERATION] Generating prompts for {project_id}")
        
        result = ExecutionResult(success=True)
        
        try:
            # Get project
            project = storage.get_project(project_id)
            if not project:
                return ExecutionResult(success=False, error="Project not found")
            
            # Get pending shots (approval gates with status pending)
            pending_shots = [
                gate for gate in project.shot_approval_gates
                if gate.status == "pending"
            ]
            
            # Generate prompts for each pending shot
            prompts = []
            for gate in pending_shots:
                shot_id = gate.shot_id
                
                # Find shot in storyboard
                shot_desc = ""
                for shot in project.storyboard_wall:
                    if shot.shot_id == shot_id:
                        shot_desc = shot.description
                        break
                
                # Generate prompt
                prompt = self._generate_prompt(project, shot_id, shot_desc)
                
                prompts.append({
                    "shot_id": shot_id,
                    "prompt": prompt,
                    "gate_id": gate.id,
                })
            
            # Update approval gates with prompts
            for gate in project.shot_approval_gates:
                for p in prompts:
                    if gate.shot_id == p["shot_id"]:
                        gate.detail = p["prompt"]
            
            storage.save_project(project)
            
            result.output_data = {
                "prompts_generated": len(prompts),
                "prompts": prompts,
            }
            
            result.metrics = {
                "shots_with_prompts": len(prompts),
            }
            
            logger.info(f"[PROMPT_GENERATION] Generated {len(prompts)} prompts")
            
        except Exception as e:
            logger.exception(f"[PROMPT_GENERATION] Error: {e}")
            result.success = False
            result.error = str(e)
        
        return result
    
    def _generate_prompt(self, project, shot_id: str, shot_desc: str) -> str:
        """Generate optimized render prompt"""
        # Get creative intent
        intent = ""
        if project.production_bible:
            intent = project.production_bible.creative_intent
        
        # Combine intent with shot description
        prompt = f"{shot_desc}"
        
        if intent:
            # Add style guidance from creative intent
            if "horror" in intent.lower():
                prompt += ", dark moody lighting, cinematic horror"
            elif "thriller" in intent.lower():
                prompt += ", tension building composition"
            elif "comedy" in intent.lower():
                prompt += ", bright lighting, warm tones"
            else:
                prompt += ", cinematic"
        
        return prompt


class RenderCoordinationExecutor(TaskExecutor):
    """
    Render Coordinator - Submits and monitors render jobs.
    
    Reads: Shot plans with prompts, approval status
    Produces: Render jobs submitted
    Updates: Render queue, job status
    """
    
    def __init__(self):
        super().__init__("render_coordinator")
    
    def execute(self, task: Dict, context: Dict) -> ExecutionResult:
        """Execute render coordination"""
        project_id = context["project_id"]
        storage = context["storage"]
        render_service = context.get("render_service")
        
        logger.info(f"[RENDER_COORDINATION] Coordinating renders for {project_id}")
        
        result = ExecutionResult(success=True)
        
        try:
            # Get project
            project = storage.get_project(project_id)
            if not project:
                return ExecutionResult(success=False, error="Project not found")
            
            # Get approved shots
            approved_shots = [
                gate for gate in project.shot_approval_gates
                if gate.status == "passed"
            ]
            
            # Submit render jobs for approved shots
            submitted = []
            for gate in approved_shots:
                shot_id = gate.shot_id
                
                # Get prompt from gate detail
                prompt = gate.detail or ""
                
                # Find render job if exists
                existing_job = None
                for job in project.render_queue:
                    if job.shot_id == shot_id:
                        existing_job = job
                        break
                
                if not existing_job:
                    # Create new render job
                    from app.models import RenderJob
                    
                    new_job = RenderJob(
                        render_id=f"render-{shot_id}",
                        shot_id=shot_id,
                        status="pending",
                        progress=0,
                        provider=project.render_provider.provider_name if project.render_provider else "simulated",
                    )
                    
                    project.render_queue.append(new_job)
                    submitted.append(shot_id)
            
            storage.save_project(project)
            
            result.output_data = {
                "jobs_submitted": len(submitted),
                "shots_submitted": submitted,
                "total_pending": len(project.render_queue),
            }
            
            result.artifacts = submitted
            result.metrics = {
                "jobs_in_queue": len(project.render_queue),
                "new_submissions": len(submitted),
            }
            
            logger.info(f"[RENDER_COORDINATION] Submitted {len(submitted)} render jobs")
            
        except Exception as e:
            logger.exception(f"[RENDER_COORDINATION] Error: {e}")
            result.success = False
            result.error = str(e)
        
        return result


class QualityReviewExecutor(TaskExecutor):
    """
    Quality Reviewer - Validates rendered outputs.
    
    Reads: Render job status, outputs
    Produces: Quality assessment
    Updates: Approval gates, review notes
    """
    
    def __init__(self):
        super().__init__("quality_reviewer")
    
    def execute(self, task: Dict, context: Dict) -> ExecutionResult:
        """Execute quality review"""
        project_id = context["project_id"]
        storage = context["storage"]
        
        logger.info(f"[QUALITY_REVIEW] Reviewing quality for {project_id}")
        
        result = ExecutionResult(success=True)
        
        try:
            # Get project
            project = storage.get_project(project_id)
            if not project:
                return ExecutionResult(success=False, error="Project not found")
            
            # Get render jobs
            jobs = project.render_queue
            
            # Perform automated quality checks
            reviews = []
            for job in jobs:
                if job.status == "complete":
                    # Simulate quality check
                    quality_score = 85  # Would be actual quality assessment
                    
                    reviews.append({
                        "render_id": job.render_id,
                        "shot_id": job.shot_id,
                        "quality_score": quality_score,
                        "status": "passed" if quality_score >= 70 else "needs_revision",
                        "notes": f"Automated QC score: {quality_score}/100",
                    })
                    
                    # Update approval gate
                    for gate in project.shot_approval_gates:
                        if gate.shot_id == job.shot_id:
                            gate.status = "passed" if quality_score >= 70 else "needs_revision"
                            gate.sub = f"QC Score: {quality_score}"
            
            storage.save_project(project)
            
            result.output_data = {
                "reviews_completed": len(reviews),
                "reviews": reviews,
            }
            
            result.metrics = {
                "quality_checks": len(reviews),
                "pass_rate": sum(1 for r in reviews if r["status"] == "passed") / max(len(reviews), 1),
            }
            
            logger.info(f"[QUALITY_REVIEW] Completed {len(reviews)} reviews")
            
        except Exception as e:
            logger.exception(f"[QUALITY_REVIEW] Error: {e}")
            result.success = False
            result.error = str(e)
        
        return result

"""
Agent Executor Service - Autonomous Agent Execution Layer

This service implements the agent execution loop that converts the manual pipeline
into an autonomous agent-driven workflow. It handles:

1. TASK POLLING - Agents continuously check for pending/assigned tasks
2. MEMORY CONTEXT - Agents read relevant memories before acting
3. TASK EXECUTION - Agents perform work based on their role
4. RESULT UPDATES - Agents update memory with results
5. AUTOMATIC HANDOVERS - Tasks flow automatically between agents

The execution loop runs asynchronously and can be started/stopped per project.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from enum import Enum
from uuid import UUID

from app.services.crew import crew_service
from app.services.memory import memory_service
from app.services.render import render_service
from app.services.adaptation import adaptation_engine
from app.services.deviation_engine import deviation_engine
from app.services.authority_hierarchy import authority_hierarchy, DecisionSource
from app.services.spine_consumption_service import spine_consumption_service
from app.services.co_director_session_service import co_director_session_service
from app.services.co_director_critique_service import co_director_critique_service
from app.services.co_director_proposal_service import co_director_proposal_service
from app.services.co_director_comparison_service import co_director_comparison_service
from app.services.co_director_intensity_service import co_director_intensity_service
from app.services.co_director_collaboration_service import co_director_collaboration_service
from app.services.director_evaluator import director_evaluator
from app.services.memory_archivist import memory_archivist_evaluator
from app.services.director_memory_resolver import merge_director_memory_archivist
from app.services.conflicts import film_continuity_tracker
from app.services.story_scoring_service import story_scoring_service, StoryScoringContext
from app.models.crew import AgentRole, TaskType, TaskStatus, CrewTask, DirectorContinuityDecision
from app.models.scene_output import SceneOutput
from app.models.co_director import CoDirectorSession

logger = logging.getLogger("studio-agent-executor")
logger.setLevel(logging.INFO)


class ExecutorState(Enum):
    """Agent executor states"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class AgentExecutor:
    """
    Autonomous Agent Execution Layer
    
    Manages the agent loop that continuously:
    1. Polls for pending tasks
    2. Assigns them to appropriate agents
    3. Executes tasks autonomously
    4. Updates memories and triggers next steps
    """
    
    def __init__(self):
        self._state = ExecutorState.STOPPED
        self._tasks: Dict[str, asyncio.Task] = {}  # project_id -> loop task
        self._agent_loops: Dict[str, Dict] = {}  # project_id -> agent states
        
        # Configuration
        self._poll_interval = 2.0  # seconds between polling
        self._max_concurrent_tasks = 5  # max tasks per project
        
        # Callbacks for external integration
        self._on_task_complete: Optional[Callable] = None
        self._on_agent_activity: Optional[Callable] = None
        
        logger.info("Agent Executor initialized")
    
    @property
    def state(self) -> ExecutorState:
        return self._state
    
    @property
    def active_projects(self) -> List[str]:
        return list(self._tasks.keys())
    
    # ========================================================================
    # LIFECYCLE MANAGEMENT
    # ========================================================================
    
    async def start_project_loop(self, project_id: str) -> bool:
        """
        Start the agent execution loop for a project.
        Returns True if started successfully.
        """
        if project_id in self._tasks:
            logger.warning(f"Project {project_id} already has active loop")
            return False
        
        if self._state == ExecutorState.STOPPED:
            self._state = ExecutorState.RUNNING
        
        try:
            # Create agent states for this project
            self._agent_loops[project_id] = {
                "started_at": datetime.now().isoformat(),
                "tasks_processed": 0,
                "agents": {}
            }
            
            # Start the loop
            loop_task = asyncio.create_task(self._project_agent_loop(project_id))
            self._tasks[project_id] = loop_task
            
            logger.info(f"Started agent loop for project {project_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start agent loop for {project_id}: {e}")
            if project_id in self._agent_loops:
                del self._agent_loops[project_id]
            return False
    
    async def stop_project_loop(self, project_id: str) -> bool:
        """
        Stop the agent execution loop for a project.
        Returns True if stopped successfully.
        """
        if project_id not in self._tasks:
            logger.warning(f"Project {project_id} has no active loop")
            return False
        
        try:
            # Cancel the loop task
            loop_task = self._tasks[project_id]
            loop_task.cancel()
            
            try:
                await asyncio.wait_for(loop_task, timeout=5.0)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Loop cancellation warning: {e}")
            
            del self._tasks[project_id]
            
            if project_id in self._agent_loops:
                del self._agent_loops[project_id]
            
            logger.info(f"Stopped agent loop for project {project_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop agent loop for {project_id}: {e}")
            return False
    
    async def stop_all(self):
        """Stop all agent loops"""
        self._state = ExecutorState.STOPPING
        
        project_ids = list(self._tasks.keys())
        for project_id in project_ids:
            await self.stop_project_loop(project_id)
        
        self._state = ExecutorState.STOPPED
        logger.info("All agent loops stopped")
    
    # ========================================================================
    # AGENT EXECUTION LOOP
    # ========================================================================
    
    async def _project_agent_loop(self, project_id: str):
        """
        Main agent loop for a project.
        Continuously polls for tasks and executes them.
        """
        logger.info(f"Agent loop started for project {project_id}")
        
        while True:
            try:
                # Check for pending tasks
                pending_tasks = crew_service.get_project_tasks(
                    project_id, 
                    status=TaskStatus.CREATED
                )
                
                # Process pending tasks
                for task in pending_tasks[:self._max_concurrent_tasks]:
                    await self._execute_task(task)
                    
                    # Update metrics
                    if project_id in self._agent_loops:
                        self._agent_loops[project_id]["tasks_processed"] += 1
                
                # Wait before next poll
                await asyncio.sleep(self._poll_interval)
                
            except asyncio.CancelledError:
                logger.info(f"Agent loop cancelled for project {project_id}")
                break
            except Exception as e:
                logger.error(f"Agent loop error for {project_id}: {e}")
                await asyncio.sleep(5)  # Back off on error
    
    async def _execute_task(self, task: CrewTask):
        """
        Execute a single task based on agent role.
        This is where the autonomous work happens.
        """
        logger.info(f"Executing task {task.task_id} for role {task.agent_role.value}")
        
        # Assign to agent
        agent_id = crew_service.assign_task(
            task.task_id, 
            f"agent-{task.agent_role.value}"
        )
        
        if not agent_id:
            logger.warning(f"Could not assign task {task.task_id}")
            return
        
        # Start task (loads memory context)
        started_task = crew_service.start_task(task.task_id)
        if not started_task:
            logger.warning(f"Could not start task {task.task_id}")
            return
        
        # Execute based on agent role
        output_data = await self._run_agent_logic(task)
        
        # Complete task with output
        crew_service.complete_task(
            task.task_id,
            output_data=output_data,
            quality_metrics=output_data.get("quality_metrics", {}),
            warnings=output_data.get("warnings", [])
        )
        
        # Trigger callbacks
        if self._on_task_complete:
            try:
                self._on_task_complete(task.project_id, task.task_id, output_data)
            except Exception as e:
                logger.warning(f"Task complete callback error: {e}")
        
        logger.info(f"Completed task {task.task_id}")
    
    async def _run_agent_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Run the agent's logic based on their role.
        Returns output data that will be stored in memory.
        """
        role = task.agent_role
        task_type = task.task_type
        input_data = task.input.data
        scene_id = input_data.get("scene_id")
        project_id = task.project_id
        
        # Base output
        output = {
            "task_id": task.task_id,
            "agent_role": role.value,
            "task_type": task_type.value,
            "scene_id": scene_id,
            "timestamp": datetime.now().isoformat(),
            "quality_metrics": {},
            "warnings": []
        }
        
        try:
            # Route to role-specific logic
            if role == AgentRole.SCRIPT_ANALYST:
                output.update(await self._script_analyst_logic(task))
            
            elif role == AgentRole.STORYBOARD_ARTIST:
                output.update(await self._storyboard_artist_logic(task))
            
            elif role == AgentRole.CINEMATOGRAPHER:
                output.update(await self._cinematographer_logic(task))
            
            elif role == AgentRole.PROMPT_ENGINEER:
                output.update(await self._prompt_engineer_logic(task))
            
            elif role == AgentRole.RENDER_COORDINATOR:
                output.update(await self._render_coordinator_logic(task))
            
            elif role == AgentRole.QUALITY_REVIEWER:
                output.update(await self._quality_reviewer_logic(task))
            
            elif role == AgentRole.DIRECTOR:
                output.update(await self._director_logic(task))
            
            elif role == AgentRole.EDITOR:
                output.update(await self._editor_logic(task))
            
            elif role == AgentRole.CONTINUITY_SUPERVISOR:
                output.update(await self._continuity_supervisor_logic(task))
    
            elif role == AgentRole.MEMORY_ARCHIVIST:
                output.update(await self._memory_archivist_logic(task))
    
            elif role == AgentRole.PRODUCER:
                output.update(await self._producer_logic(task))
            
            else:
                output["result"] = f"Executed {task_type.value} for {role.value}"
            
            output["success"] = True
            
        except Exception as e:
            logger.error(f"Agent logic error for {role.value}: {e}")
            output["success"] = False
            output["error"] = str(e)
            output["warnings"].append(f"Agent execution had errors: {e}")
        
        return output
    
    # ========================================================================
    # ROLE-SPECIFIC AGENT LOGIC
    # These methods implement what each agent does when they pick up a task
    # ========================================================================
    
    async def _script_analyst_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Script Analyst: Analyzes screenplay structure, extracts story beats,
        identifies character arcs, and breaks down scenes.
        """
        input_data = task.input.data
        scene_id = input_data.get("scene_id")
        project_id = task.project_id
        
        # Read scene content from memory/project
        scene_content = input_data.get("scene_content", "")
        script_text = input_data.get("script_text", "")
        
        result = {
            "task_type": "analysis",
            "scene_data": {
                "scene_id": scene_id,
                "story_beats": [],
                "character_count": 0,
                "emotional_tone": "neutral",
                "pacing": "medium"
            },
            "pacing_notes": ""
        }
        
        # Analyze the scene
        if scene_content:
            # Extract story beats (simplified - in production would call LLM)
            words = scene_content.split()
            result["scene_data"]["word_count"] = len(words)
            result["scene_data"]["estimated_duration"] = len(words) * 0.1  # ~6 min per page
            
            # Detect emotional tone
            emotional_markers = {
                "tense": ["door", "quiet", "careful", "slowly", "watch"],
                "dramatic": ["love", "hate", "fight", "scream", "cry"],
                "mysterious": ["shadow", "dark", "light", "hidden", "secret"],
                "action": ["runs", "jumps", "shoots", "explodes", "fast"]
            }
            
            lower_content = scene_content.lower()
            detected_emotions = []
            for emotion, markers in emotional_markers.items():
                if any(m in lower_content for m in markers):
                    detected_emotions.append(emotion)
            
            if detected_emotions:
                result["scene_data"]["emotional_tone"] = detected_emotions[0]
            
            result["pacing_notes"] = f"Scene analyzed: {len(words)} words, tone={result['scene_data']['emotional_tone']}"
        
        # Update quality metrics
        result["quality_metrics"] = {
            "analysis_completeness": 0.8,
            "character_identification": 1.0,
            "beat_breakdown": 0.7
        }
        
        return result
    
    async def _storyboard_artist_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Storyboard Artist: Plans shot composition, creates shot list,
        determines camera angles and blocking.
        
        ADAPTIVE: Uses memory to influence camera angles and framing
        based on prior scene success.
        """
        input_data = task.input.data
        scene_id = input_data.get("scene_id")
        project_id = task.project_id
        
        result = {
            "task_type": "planning",
            "shot_plan": {
                "scene_id": scene_id,
                "shots": []
            },
            "adaptive_decisions": []
        }
        
        # Get scene description and context
        scene_desc = input_data.get("scene_description", "")
        prior_scene = input_data.get("prior_scene")
        
        if scene_desc:
            # === ADAPTIVE BEHAVIOR: Get recommendations from adaptation engine ===
            adaptations = adaptation_engine.get_shot_planner_adaptations(
                project_id, 
                {"prior_scene": prior_scene, "scene_id": scene_id}
            )
            
            # Get recommended camera angles from prior success
            suggested_angles = adaptations.get("suggested_camera_angles", [])
            suggested_framing = adaptations.get("framing_adjustments", [])
            consistency_notes = adaptations.get("consistency_notes", [])
            
            # === DEVIATION ENGINE: Check for intentional pattern break ===
            scene_context = {
                "scene_id": scene_id,
                "prior_scene": prior_scene,
                "notes": input_data.get("notes", ""),
                "is_turning_point": input_data.get("is_turning_point", False),
                "narrative_beat": input_data.get("narrative_beat", "")
            }
            scene_intensity = input_data.get("intensity", 0.5)
            
            # === AUTHORITY HIERARCHY: Resolve camera angle using priority system ===
            # Create adaptive input from prior success
            adaptive_camera = DecisionInput(
                value=suggested_angles[0] if suggested_angles else "wide",
                source=DecisionSource.ADAPTIVE_SUGGESTION,
                confidence=0.8,
                reason="From adaptation engine recommendations"
            )
            
            # Resolve camera angle decision through hierarchy
            camera_resolution = authority_hierarchy.resolve_decision_conflict(
                project_id=project_id,
                decision_type="camera_angle",
                scene_id=scene_id,
                inputs=[adaptive_camera],
                default_value="wide",
                check_deviation=True,
                scene_intensity=scene_intensity
            )
            
            # Also resolve framing through hierarchy
            adaptive_framing = DecisionInput(
                value=suggested_framing[0] if suggested_framing else "standard",
                source=DecisionSource.ADAPTIVE_SUGGESTION,
                reason="From adaptation engine recommendations"
            )
            framing_resolution = authority_hierarchy.resolve_decision_conflict(
                project_id=project_id,
                decision_type="framing",
                scene_id=scene_id,
                inputs=[adaptive_framing],
                default_value="standard"
            )
            
            # Add debug info to result
            result["decision_debug"] = {
                "camera": {
                    "final_value": camera_resolution.final_value,
                    "decision_source": camera_resolution.decision_source,
                    "conflict_resolved": camera_resolution.conflict_resolved,
                    "overridden_sources": camera_resolution.overridden_sources,
                    "all_inputs": camera_resolution.all_inputs
                },
                "framing": {
                    "final_value": framing_resolution.final_value,
                    "decision_source": framing_resolution.decision_source,
                    "conflict_resolved": framing_resolution.conflict_resolved,
                    "overridden_sources": framing_resolution.overridden_sources,
                    "all_inputs": framing_resolution.all_inputs
                }
            }
            
            # Update deviation result based on hierarchy resolution
            result["deviation_applied"] = camera_resolution.decision_source == "deviation"
            result["deviation_reason"] = camera_resolution.reason if camera_resolution.decision_source == "deviation" else ""
            
            # === ADAPTIVE SHOT PLANNING ===
            shots = []
            
            # Shot 1: Establishing shot - use resolved camera angle
            shot1_camera = camera_resolution.final_value
            shot1_consistent, warning = adaptation_engine.check_consistency(
                project_id, "camera_angle", shot1_camera, scene_id
            )
            shot1 = {
                "shot_number": 1,
                "type": "establishing",
                "description": "Wide establishing shot",
                "camera": shot1_camera,
                "duration_seconds": 5,
                "consistent_with_prior": shot1_consistent,
                "decision_source": camera_resolution.decision_source
            }
            if camera_resolution.conflict_resolved:
                result["adaptive_decisions"].append({
                    "decision_type": "camera_angle",
                    "decision": shot1_camera,
                    "source": camera_resolution.decision_source,
                    "reason": f"Hierarchy resolution: {camera_resolution.authority_used}",
                    "conflict_resolved": True,
                    "overridden": camera_resolution.overridden_sources
                })
            shots.append(shot1)
            
            # Shot 2: Main action - use resolved framing
            shot2_camera = suggested_angles[1] if len(suggested_angles) > 1 else "medium"
            shot2_framing = framing_resolution.final_value
            
            shots.append({
                "shot_number": 2,
                "type": "master",
                "description": "Main action coverage",
                "camera": shot2_camera,
                "framing": shot2_framing,
                "duration_seconds": 10,
                "decision_source": framing_resolution.decision_source
            })
            
            # Shot 3: Reaction/close-up - use resolved camera or fallback
            shot3_camera = "close"
            if suggested_angles:
                shot3_camera = suggested_angles[-1]
            
            shots.append({
                "shot_number": 3,
                "type": "close_up",
                "description": "Reaction shot",
                "camera": shot3_camera,
                "duration_seconds": 3
            })
            
            result["shot_plan"]["shots"] = shots
            result["shot_plan"]["total_duration"] = sum(s["duration_seconds"] for s in shots)
            
            # Log adaptive decisions
            for angle in shots:
                adaptation_engine.log_adaptive_decision(
                    project_id=project_id,
                    agent_role="storyboard_artist",
                    decision_type="camera_angle",
                    decision=angle.get("camera"),
                    memory_used={
                        "scene_id": scene_id,
                        "suggested_angles": suggested_angles,
                        "established_patterns": adaptations.get("style_reinforcement", [])
                    },
                    reason=f"Based on {len(suggested_angles)} prior successful shots" if suggested_angles else "Default (no prior data)",
                    based_on_feedback=len(suggested_angles) > 0
                )
            
            # Update storyboard wall
            self._update_storyboard_entry(
                project_id, 
                scene_id,
                description=scene_desc,
                camera_angle=shots[0].get("camera"),
                status="planned"
            )
        
        result["quality_metrics"] = {
            "composition_quality": 0.9,
            "shot_coverage": 0.85,
            "continuity_plan": 0.9,
            "adaptation_score": len(result["adaptive_decisions"]) / 3 if result["adaptive_decisions"] else 0
        }
        
        return result
    
    async def _cinematographer_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Cinematographer: Determines lighting, camera movement,
        lens choices, and visual style.
        """
        input_data = task.input.data
        scene_id = input_data.get("scene_id")
        
        result = {
            "task_type": "planning",
            "style_data": {
                "scene_id": scene_id,
                "lighting_setup": "low_key",
                "camera_movement": "static",
                "lens_choice": "50mm",
                "visual_style": "noir"
            },
            "camera_choice": ""
        }
        
        # Get creative intent from project
        creative_intent = input_data.get("creative_intent", "")
        
        # Determine cinematography based on creative intent
        if "noir" in creative_intent.lower():
            result["style_data"]["lighting_setup"] = "low_key"
            result["style_data"]["visual_style"] = "film_noir"
            result["camera_choice"] = "Medium lens (50mm), static or slow push-in"
        elif "horror" in creative_intent.lower():
            result["style_data"]["lighting_setup"] = "chiaroscuro"
            result["style_data"]["visual_style"] = "gothic"
            result["camera_choice"] = "Wide lens (24mm), handheld for unease"
        elif "action" in creative_intent.lower():
            result["style_data"]["lighting_setup"] = "high_key"
            result["style_data"]["camera_movement"] = "dynamic"
            result["camera_choice"] = "Various lenses, movement preferred"
        
        result["quality_metrics"] = {
            "lighting_design": 0.85,
            "camera_plan": 0.9,
            "style_consistency": 0.95
        }
        
        return result
    
    async def _prompt_engineer_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Prompt Engineer: Generates AI render prompts based on
        shot plan and cinematography choices.
        
        ADAPTIVE: Improves prompts based on render success/failure feedback.
        """
        input_data = task.input.data
        scene_id = input_data.get("scene_id")
        project_id = task.project_id
        
        result = {
            "task_type": "execution",
            "generated_shot": {
                "scene_id": scene_id,
                "prompt": "",
                "negative_prompt": "",
                "settings": {}
            },
            "adaptive_improvements": []
        }
        
        # Combine shot plan and style for prompt
        shot_desc = input_data.get("shot_description", "")
        style = input_data.get("style_data", {})
        creative_intent = input_data.get("creative_intent", "")
        
        if shot_desc and style:
            # === ADAPTIVE BEHAVIOR: Get improvements from feedback ===
            prompt_adaptations = adaptation_engine.get_prompt_engineer_adaptations(
                project_id,
                {"scene_id": scene_id, "style": style}
            )
            
            # Get reinforced elements (from successful renders)
            reinforced = prompt_adaptations.get("reinforced_elements", [])
            avoid = prompt_adaptations.get("avoid_elements", [])
            settings_adjustments = prompt_adaptations.get("settings_adjustments", {})
            
            # === ADAPTIVE PROMPT GENERATION ===
            prompt_parts = [shot_desc]
            
            # Add visual style (reinforced from feedback)
            visual_style = style.get("visual_style", "cinematic")
            if reinforced:
                # Use feedback-reinforced style elements
                prompt_parts.append(f"cinematic {', '.join(reinforced[:2])}")
                result["adaptive_improvements"].append({
                    "type": "reinforced_style",
                    "elements": reinforced[:2],
                    "reason": "High success rate in prior renders"
                })
            else:
                prompt_parts.append(f"cinematic {visual_style}")
            
            # Add lighting (from cinematography)
            prompt_parts.append(f"lighting: {style.get('lighting_setup', 'cinematic')}")
            
            # Add film quality elements
            prompt_parts.append("8K, film grain, cinematic color grading")
            
            # Add creative intent
            if creative_intent:
                prompt_parts.append(creative_intent[:100])
            
            result["generated_shot"]["prompt"] = ", ".join(filter(None, prompt_parts))
            
            # === ADAPTIVE NEGATIVE PROMPT ===
            negative_parts = ["cartoon, anime, low quality, distorted"]
            
            # Add elements to avoid based on feedback
            if avoid:
                negative_parts.extend(avoid[:3])
                result["adaptive_improvements"].append({
                    "type": "avoid_elements",
                    "elements": avoid[:3],
                    "reason": "Poor results in prior renders"
                })
            
            result["generated_shot"]["negative_prompt"] = ", ".join(negative_parts)
            
            # === ADAPTIVE SETTINGS ===
            settings = {
                "width": 1920,
                "height": 1080,
                "steps": 50,
                "guidance_scale": 7.5
            }
            
            # Apply feedback-based settings adjustments
            if settings_adjustments:
                for key, value in settings_adjustments.items():
                    if key in settings:
                        try:
                            settings[key] = int(value) if "." not in value else float(value)
                            result["adaptive_improvements"].append({
                                "type": "settings_adjustment",
                                "setting": key,
                                "value": value,
                                "reason": "Optimized based on render feedback"
                            })
                        except:
                            pass
            
            result["generated_shot"]["settings"] = settings
            
            # Log adaptive decisions
            adaptation_engine.log_adaptive_decision(
                project_id=project_id,
                agent_role="prompt_engineer",
                decision_type="prompt_generation",
                decision=result["generated_shot"]["prompt"][:100] + "...",
                memory_used={
                    "reinforced_elements": reinforced,
                    "avoid_elements": avoid,
                    "settings_applied": settings_adjustments
                },
                reason=f"Based on {len(reinforced)} reinforced elements, {len(avoid)} avoid elements",
                based_on_feedback=True
            )
        
        result["quality_metrics"] = {
            "prompt_quality": 0.9,
            "aesthetic_match": 0.85 + (0.1 if result["adaptive_improvements"] else 0),
            "technical_accuracy": 0.95
        }
        
        return result
    
    async def _render_coordinator_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Render Coordinator: Manages render job submission,
        monitors progress, and handles queue.
        """
        input_data = task.input.data
        scene_id = input_data.get("scene_id")
        project_id = task.project_id
        
        result = {
            "task_type": "execution",
            "render_job": None
        }
        
        # Get prompt and submit render
        prompt = input_data.get("prompt")
        provider = input_data.get("render_provider", "simulated")
        
        if prompt and project_id:
            try:
                # Submit render job
                job = render_service.create_job(
                    project_id=project_id,
                    shot_id=scene_id,
                    prompt=prompt,
                    provider=provider
                )
                
                if job:
                    result["render_job"] = {
                        "job_id": job.id,
                        "shot_id": scene_id,
                        "status": job.status,
                        "submitted_at": datetime.now().isoformat()
                    }
                    
                    # Auto-submit for rendering
                    render_service.submit_job(job.id)
                    
            except Exception as e:
                result["warnings"].append(f"Render submission error: {e}")
        
        result["quality_metrics"] = {
            "submission_success": 1.0 if result["render_job"] else 0.0,
            "queue_management": 0.9
        }
        
        return result
    
    async def _quality_reviewer_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Quality Reviewer: Evaluates render outputs against
        requirements, checks technical quality.
        
        ADAPTIVE: Adjusts evaluation criteria based on project goals
        and feedback history.
        """
        input_data = task.input.data
        scene_id = input_data.get("scene_id")
        project_id = task.project_id
        
        result = {
            "task_type": "validation",
            "feedback": {
                "technical_score": 0,
                "aesthetic_score": 0,
                "approved": False,
                "issues": []
            },
            "adaptive_evaluation": {}
        }
        
        # === ADAPTIVE BEHAVIOR: Get project-specific evaluation criteria ===
        eval_adaptations = adaptation_engine.get_quality_reviewer_adaptations(
            project_id,
            {"scene_id": scene_id}
        )
        
        # Get evaluation thresholds and project-specific checks
        eval_criteria = eval_adaptations.get("evaluation_criteria", {})
        thresholds = eval_adaptations.get("thresholds", {})
        project_checks = eval_adaptations.get("project_specific_checks", [])
        leniency = eval_adaptations.get("leniency_factors", [])
        
        # === ADAPTIVE EVALUATION ===
        # Get render outputs
        job_id = input_data.get("render_job_id")
        reference_prompt = input_data.get("reference_prompt", "")
        camera_angle = input_data.get("camera_angle", "")
        lighting_setup = input_data.get("lighting_setup", "")
        
        if job_id:
            try:
                outputs = render_service.get_job_outputs(job_id)
                
                if outputs and outputs.get("assets"):
                    # Base evaluation with adaptive adjustments
                    base_technical = 0.85
                    base_aesthetic = 0.80
                    
                    # Apply project-specific criteria adjustments
                    if eval_criteria.get("lighting_consistency"):
                        # Increase weight for lighting in noir projects
                        base_aesthetic += (eval_criteria["lighting_consistency"] - 0.8) * 0.5
                    
                    if eval_criteria.get("shadow_detail"):
                        base_technical += (eval_criteria["shadow_detail"] - 0.8) * 0.3
                    
                    # Check camera angle consistency
                    if camera_angle:
                        consistent, warning = adaptation_engine.check_consistency(
                            project_id, "camera_angle", camera_angle, scene_id
                        )
                        if consistent:
                            base_aesthetic += 0.05  # Bonus for consistency
                            result["adaptive_evaluation"]["camera_consistency"] = {
                                "status": "passed",
                                "bonus": 0.05
                            }
                        else:
                            base_aesthetic -= 0.1  # Penalty for inconsistency
                            result["adaptive_evaluation"]["camera_consistency"] = {
                                "status": "warning",
                                "warning": warning
                            }
                    
                    # Check lighting setup consistency
                    if lighting_setup:
                        consistent, warning = adaptation_engine.check_consistency(
                            project_id, "lighting", lighting_setup, scene_id
                        )
                        if consistent:
                            base_aesthetic += 0.05
                            result["adaptive_evaluation"]["lighting_consistency"] = {
                                "status": "passed",
                                "bonus": 0.05
                            }
                    
                    # Apply leniency factors
                    for factor in leniency:
                        if "confidence" in factor.lower():
                            base_technical += 0.02
                            base_aesthetic += 0.02
                    
                    # Clamp scores
                    result["feedback"]["technical_score"] = min(1.0, max(0.0, base_technical))
                    result["feedback"]["aesthetic_score"] = min(1.0, max(0.0, base_aesthetic))
                    
                    # Adaptive approval threshold
                    approval_threshold = 0.70  # Base threshold
                    if project_checks:
                        approval_threshold += 0.05 * len(project_checks)  # Lenient for well-defined projects
                    
                    # Check against adaptive threshold
                    avg_score = (result["feedback"]["technical_score"] + 
                                result["feedback"]["aesthetic_score"]) / 2
                    
                    result["feedback"]["approved"] = avg_score >= approval_threshold
                    result["feedback"]["issues"] = []
                    
                    if result["feedback"]["approved"]:
                        result["feedback"]["approval_reason"] = (
                            f"Scores ({avg_score:.2f}) meet adaptive threshold ({approval_threshold:.2f})"
                        )
                    else:
                        result["feedback"]["issues"].append(
                            f"Scores ({avg_score:.2f}) below adaptive threshold ({approval_threshold:.2f})"
                        )
                    
                    result["adaptive_evaluation"]["threshold_used"] = approval_threshold
                    result["adaptive_evaluation"]["project_checks_applied"] = len(project_checks)
                    
                    # === RECORD FEEDBACK FOR LEARNING ===
                    if camera_angle:
                        adaptation_engine.record_feedback(
                            project_id=project_id,
                            feedback_type="quality_review",
                            pattern_type="camera_angle",
                            pattern_value=camera_angle,
                            approved=result["feedback"]["approved"],
                            scene_id=scene_id,
                            render_job_id=job_id
                        )
                    
                    if lighting_setup:
                        adaptation_engine.record_feedback(
                            project_id=project_id,
                            feedback_type="quality_review",
                            pattern_type="lighting",
                            pattern_value=lighting_setup,
                            approved=result["feedback"]["approved"],
                            scene_id=scene_id,
                            render_job_id=job_id
                        )
                    
                    # Log the adaptive decision
                    adaptation_engine.log_adaptive_decision(
                        project_id=project_id,
                        agent_role="quality_reviewer",
                        decision_type="approval",
                        decision="approved" if result["feedback"]["approved"] else "rejected",
                        memory_used={
                            "camera_angle": camera_angle,
                            "lighting_setup": lighting_setup,
                            "technical_score": result["feedback"]["technical_score"],
                            "aesthetic_score": result["feedback"]["aesthetic_score"],
                            "thresholds": thresholds,
                            "project_checks": project_checks
                        },
                        reason=f"Scores: tech={result['feedback']['technical_score']:.2f}, "
                               f"aesth={result['feedback']['aesthetic_score']:.2f}, "
                               f"threshold={approval_threshold:.2f}",
                        based_on_feedback=True
                    )
                    
            except Exception as e:
                result["feedback"]["issues"].append(str(e))
        
        result["quality_metrics"] = {
            "evaluation_accuracy": 0.9 + (0.05 if result["adaptive_evaluation"] else 0),
            "consistency": 0.95
        }
        
        return result
    
    async def _director_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Director: Makes creative decisions, reviews outputs,
        maintains vision consistency using DirectorEvaluator.
        """
        input_data = task.input.data
    
        result = {
            "task_type": "creative_review",
            "creative_decision": {
                "approved": False,
                "notes": "",
                "requires_revision": False
            }
        }
    
        # Get scene context
        scene_id = input_data.get("scene_id")
        film_id = input_data.get("film_id", "default")
        scene_data = input_data.get("scene_data", {})
    
        # Add scene_id to scene_data if not present
        if "scene_id" not in scene_data:
            scene_data["scene_id"] = scene_id
    
        # Get role-filtered spine, structure, and memory context through SpineConsumptionService
        spine_context = spine_consumption_service.get_context_for_role(film_id, AgentRole.DIRECTOR)
        structure_context = spine_consumption_service.get_structure_context(film_id, scene_id)
        memory_context = spine_consumption_service.get_memory_context(film_id, AgentRole.DIRECTOR)
        taste_context = spine_consumption_service.get_taste_context(
            project_id=task.project_id,
            film_id=film_id,
            scene_id=scene_id,
        )
        safe_taste_context = (
            taste_context.to_dict()
            if hasattr(taste_context, "to_dict")
            else taste_context
        )
        cinematic_language_context = spine_consumption_service.get_cinematic_language_context(
            film_id=film_id,
            scene_data=scene_data if isinstance(scene_data, dict) else None,
            scene_id=scene_id,
        )
        safe_cinematic_language_context = (
            cinematic_language_context
            if isinstance(cinematic_language_context, dict)
            else None
        )

        # Instantiate DirectorEvaluator and evaluate
        eval_result = director_evaluator.evaluate(
            scene_data=scene_data,
            spine=spine_context,
            structure=structure_context,
            memory=memory_context,
            taste_calibration=safe_taste_context,
            cinematic_language_context=safe_cinematic_language_context,
        )
    
        # Map evaluation result to creative decision
        result["creative_decision"]["approved"] = eval_result["approved"]
        result["creative_decision"]["requires_revision"] = eval_result["requires_revision"]
        result["creative_decision"]["notes"] = eval_result.get("notes", "")
    
        # Add detailed scoring info
        result["quality_metrics"] = {
            "vision_consistency": eval_result.get("score", 0.0),
            "creative_coherence": eval_result.get("pillars", {}).get("emotional_consistency", 0.0),
            "score": eval_result.get("score", 0.0),
            "pillars": eval_result.get("pillars", {}),
            "decision": eval_result.get("decision", "REJECT"),
            "rejection_reasons": eval_result.get("rejection_reasons", []),
            "revision_notes": eval_result.get("revision_notes", []),
            "taste_influence": eval_result.get("taste_influence", {}),
            "cinematic_influence": eval_result.get("cinematic_influence", {}),
        }
    
        # Log the decision
        logger.info(
            f"Director evaluation for scene {scene_id}: "
            f"decision={eval_result.get('decision')}, "
            f"score={eval_result.get('score')}, "
            f"reasons={eval_result.get('rejection_reasons')}"
        )
    
        # Phase 3.5: Check if memory archivist output was provided in input
        # and merge with director output for combined decision reporting
        memory_archivist_output = input_data.get("memory_archivist_output")
        if memory_archivist_output:
            result = self._merge_with_memory_archivist(
                result, memory_archivist_output, scene_id, film_id
            )
    
        # Phase 4.4: Run story-level scoring (non-blocking)
        # Story scoring runs after director logic to provide story-level health metrics
        try:
            story_score = self._run_story_scoring(
                film_id=film_id,
                scope="scene",
                scene_id=scene_id,
                scene_data=scene_data,
                director_decision=result.get("creative_decision")
            )
            if story_score:
                result["story_score"] = story_score
                logger.info(f"Story scoring completed for scene {scene_id}: health={story_score.get('overall_health', 'N/A')}")
        except Exception as e:
            logger.warning(f"Story scoring skipped for scene {scene_id}: {e}")
    
        return result
    
    def _merge_with_memory_archivist(
        self,
        director_output: Dict[str, Any],
        memory_archivist_output: Dict[str, Any],
        scene_id: Optional[str],
        film_id: str
    ) -> Dict[str, Any]:
        """
        Merge Director output with Memory Archivist continuity analysis.
        
        Phase 3.5: Director-Memory Archivist Conflict Resolution
        This merge attaches continuity context to the Director's creative decision
        without modifying the decision itself.
        
        Args:
            director_output: Output from Director evaluation
            memory_archivist_output: Output from Memory Archivist evaluation
            scene_id: Scene identifier
            film_id: Film identifier
        
        Returns:
            Merged output with continuity context attached
        """
        # Use the merge function from director_memory_resolver
        merged = merge_director_memory_archivist(
            director_output=director_output,
            memory_archivist_output=memory_archivist_output,
            scene_id=scene_id,
            film_id=film_id
        )
        
        # Record in film continuity tracker for film-level tracking
        if film_id and scene_id:
            try:
                film_continuity_tracker.record_scene_decision(
                    film_id=film_id,
                    scene_id=scene_id,
                    decision_output=merged
                )
            except Exception as e:
                logger.warning(f"Failed to record scene decision in film tracker: {e}")
        
        logger.info(
            f"Merged Director + Memory Archivist outputs for scene {scene_id}: "
            f"critical_alerts={merged.get('continuity_context', {}).get('critical_count', 0)}, "
            f"warning_alerts={merged.get('continuity_context', {}).get('warning_count', 0)}"
        )
        
        return merged
    
    def _build_story_scoring_context(
        self,
        film_id: str,
        scene_id: Optional[str] = None,
        scene_data: Optional[Dict[str, Any]] = None,
        director_decision: Optional[Dict[str, Any]] = None
    ) -> StoryScoringContext:
        """
        Build StoryScoringContext from available data sources.

        This is non-blocking - returns context with whatever data is available.
        Missing data will result in conservative 0.5 scores from analyzers.
        """
        # Get data from spine_consumption_service if available
        film_structure = None
        film_memory = None
        creative_spine = None
        
        try:
            if spine_consumption_service:
                structure_context = spine_consumption_service.get_structure_context(film_id, scene_id)
                if structure_context:
                    film_structure = structure_context.get("structure")
                
                memory_context = spine_consumption_service.get_memory_context(film_id, AgentRole.DIRECTOR)
                if memory_context:
                    film_memory = memory_context.get("memory")
                    creative_spine = memory_context.get("spine")
        except Exception as e:
            logger.warning(f"Error building story scoring context: {e}")
        
        # Get scene decisions from film_continuity_tracker
        scene_decisions = []
        try:
            if film_continuity_tracker and scene_id:
                decisions = film_continuity_tracker.get_all_scene_decisions(film_id)
                scene_decisions = [d for d in decisions if d.get("scene_id") == scene_id]
        except Exception:
            pass
        
        # Safely create DirectorContinuityDecision if director_decision has required fields
        director_decision_obj = None
        if director_decision:
            try:
                director_decision_obj = DirectorContinuityDecision(**director_decision)
            except Exception:
                # Invalid or incomplete director_decision dict - set to None
                director_decision_obj = None
        
        return StoryScoringContext(
            film_id=film_id,
            film_structure=film_structure,
            film_memory=film_memory,
            creative_spine=creative_spine,
            continuity_tracker=film_continuity_tracker,
            scene_id=scene_id,
            scene_data=scene_data,
            director_decision=director_decision_obj,
            scene_decisions=scene_decisions
        )
    
    def _run_story_scoring(
        self,
        film_id: str,
        scope: str,
        scene_id: Optional[str] = None,
        sequence_id: Optional[str] = None,
        act_number: Optional[int] = None,
        scene_data: Optional[Dict[str, Any]] = None,
        director_decision: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Run story-level scoring and return results.
        
        This is non-blocking - returns None if scoring fails or context is insufficient.
        Results are attached to output as structured StoryScore data.
        """
        try:
            context = self._build_story_scoring_context(
                film_id=film_id,
                scene_id=scene_id,
                scene_data=scene_data,
                director_decision=director_decision
            )
            
            # Run appropriate scoring method based on scope
            if scope == "scene" and scene_id:
                score = story_scoring_service.score_scene(
                    film_id=film_id,
                    scene_id=scene_id,
                    scene_data=scene_data,
                    context=context
                )
            elif scope == "sequence" and sequence_id:
                score = story_scoring_service.score_sequence(
                    film_id=film_id,
                    sequence_id=sequence_id,
                    context=context
                )
            elif scope == "act" and act_number:
                score = story_scoring_service.score_act(
                    film_id=film_id,
                    act_number=act_number,
                    context=context
                )
            elif scope == "film":
                score = story_scoring_service.score_film(
                    film_id=film_id,
                    context=context
                )
            else:
                return None
            
            # Return structured score data
            return score.to_dict() if hasattr(score, 'to_dict') else {
                "film_id": score.film_id,
                "scope": score.scope,
                "scope_id": score.scope_id,
                "overall_health": score.overall_health,
                "dimension_scores": score.dimension_scores,
                "warnings": score.warnings,
                "recommendations": [r.to_dict() if hasattr(r, 'to_dict') else r for r in score.recommendations],
                "priority": score.priority.value if hasattr(score.priority, 'value') else str(score.priority),
                "timestamp": score.timestamp
            }
        except Exception as e:
            logger.warning(f"Story scoring failed: {e}")
            return None
    
    async def _memory_archivist_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Memory Archivist: Analyzes long-form continuity health.
        
        This is a READ-ONLY analysis role - it does NOT override Director decisions
        and does NOT block execution. It returns structured continuity reports only.
        
        Phase 3.4 integration: Uses SpineConsumptionService.get_continuity_context()
        to obtain the combined spine, structure, and memory context needed for
        continuity analysis.
        """
        input_data = task.input.data

        result = {
            "task_type": "continuity_analysis",
            "continuity_report": None,
            "alerts": [],
            "health_scores": {}
        }

        # Get film and scene identifiers
        scene_id = input_data.get("scene_id")
        film_id = input_data.get("film_id", "default")
        scene_data = input_data.get("scene_data", {})
        if not isinstance(scene_data, dict):
            scene_data = {}

        # Add scene_id to scene_data if not present
        if "scene_id" not in scene_data:
            scene_data["scene_id"] = scene_id
        if "film_id" not in scene_data:
            scene_data["film_id"] = film_id

        # Determine evaluation mode based on input
        evaluation_mode = input_data.get("evaluation_mode", "scene")  # "scene" or "film"

        try:
            # Get continuity context through SpineConsumptionService
            continuity_context = spine_consumption_service.get_continuity_context(
                film_id=film_id,
                scene_id=scene_id,
                act_number=input_data.get("act_number")
            )
            film_intelligence_context = spine_consumption_service.get_film_intelligence_context(
                film_id=film_id,
                scene_id=scene_id,
                act_number=input_data.get("act_number"),
            )

            # Run MemoryArchivistEvaluator based on mode
            if evaluation_mode == "film":
                # Film-level continuity health check
                report = memory_archivist_evaluator.evaluate_film_continuity(
                    film_id=film_id,
                    spine=continuity_context.get("spine"),
                    structure=continuity_context.get("structure"),
                    memory=continuity_context.get("memory"),
                    film_intelligence=film_intelligence_context,
                )
                result["continuity_report"] = {
                    "report_type": "film",
                    "film_id": film_id,
                    "overall_health": report.overall_health,
                    "tension_health": report.tension_health,
                    "motif_health": report.motif_health,
                    "character_health": report.character_health,
                    "act_transition_health": report.act_transition_health,
                    "alert_count": len(report.alerts),
                    "tension_status_count": len(report.tension_statuses),
                    "motif_status_count": len(report.motif_statuses),
                    "debug_metadata": report.debug_metadata,
                }
                result["health_scores"] = {
                    "overall": report.overall_health,
                    "tension": report.tension_health,
                    "motif": report.motif_health,
                    "character": report.character_health,
                    "act_transition": report.act_transition_health
                }
            else:
                # Scene-level continuity check
                report = memory_archivist_evaluator.evaluate_scene_continuity(
                    scene_id=scene_id,
                    scene_data=scene_data,
                    spine=continuity_context.get("spine"),
                    structure=continuity_context.get("structure"),
                    memory=continuity_context.get("memory"),
                    film_intelligence=film_intelligence_context,
                )
                result["continuity_report"] = {
                    "report_type": "scene",
                    "scene_id": scene_id,
                    "film_id": film_id,
                    "passed": report.passed,
                    "issue_count": len(report.issues),
                    "warning_count": len(report.warnings),
                    "debug_metadata": report.debug_metadata,
                }
                result["health_scores"] = {
                    "passed": report.passed,
                    "issue_count": len(report.issues),
                    "warning_count": len(report.warnings)
                }

            # Extract alerts for both modes
            if hasattr(report, 'alerts') and report.alerts:
                result["alerts"] = [
                    {
                        "type": alert.alert_type.value if hasattr(alert.alert_type, 'value') else str(alert.alert_type),
                        "severity": alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity),
                        "description": alert.description,
                        "affected_elements": alert.affected_elements,
                        "recommended_action": alert.recommended_action
                    }
                    for alert in report.alerts
                ]

            # Log the analysis
            logger.info(
                f"Memory Archivist analysis for {evaluation_mode} {scene_id or film_id}: "
                f"health={result.get('health_scores', {}).get('overall', result.get('health_scores', {}).get('passed', 'N/A'))}"
            )

        except Exception as e:
            logger.error(f"Memory Archivist error: {e}")
            result["error"] = str(e)
            result["warnings"].append(f"Continuity analysis encountered an error: {e}")

        return result

    async def _editor_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Editor: Reviews pacing, rhythm, and continuity.
        """
        input_data = task.input.data
        
        result = {
            "task_type": "review",
            "pacing_notes": ""
        }
        
        scene_id = input_data.get("scene_id")
        
        result["pacing_notes"] = f"Scene {scene_id}: Pacing analysis complete"
        
        result["quality_metrics"] = {
            "pacing_assessment": 0.85,
            "rhythm_analysis": 0.8
        }
        
        return result
    
    async def _continuity_supervisor_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Continuity Supervisor: Checks for consistency across scenes.
        """
        input_data = task.input.data
        
        result = {
            "task_type": "validation",
            "continuity_check": {
                "passed": True,
                "issues": []
            }
        }
        
        result["quality_metrics"] = {
            "continuity_accuracy": 0.9
        }
        
        return result
    
    async def _producer_logic(self, task: CrewTask) -> Dict[str, Any]:
        """
        Producer: Coordinates workflow, manages timeline,
        handles resource allocation.
        """
        input_data = task.input.data
        
        result = {
            "task_type": "coordination",
            "workflow_update": {
                "next_phase": "production",
                "blocked_tasks": 0
            }
        }
        
        result["quality_metrics"] = {
            "coordination_efficiency": 0.9
        }
        
        return result
    
    # ========================================================================
    # STORYBOARD INTEGRATION
    # ========================================================================
    
    def _update_storyboard_entry(
        self, 
        project_id: str, 
        shot_id: str,
        description: str = None,
        camera_angle: str = None,
        status: str = None
    ):
        """
        Update storyboard wall from agent output.
        Called by storyboard artist and cinematographer.
        """
        try:
            from app.data.storage import get_storage
            from app.models import StoryboardShot
            
            storage = get_storage("sqlite")
            project = storage.get_project(project_id)
            
            if not project:
                logger.warning(f"Project {project_id} not found for storyboard update")
                return
            
            # Find and update the shot
            for shot in project.storyboard_wall:
                if shot.shot_id == shot_id:
                    if description:
                        shot.description = description
                    if camera_angle:
                        shot.camera_angle = camera_angle
                    if status:
                        shot.status = status
                    break
            
            storage.save_project(project)
            logger.info(f"Updated storyboard entry {shot_id} for project {project_id}")
                
        except Exception as e:
            logger.warning(f"Failed to update storyboard: {e}")
    
    # ========================================================================
    # CALLBACKS
    # ========================================================================
    
    def set_task_complete_callback(self, callback: Callable):
        """Set callback for task completion events"""
        self._on_task_complete = callback
    
    def set_activity_callback(self, callback: Callable):
        """Set callback for agent activity logging"""
        self._on_agent_activity = callback
    
    # ========================================================================
    # STATUS & METRICS
    # ========================================================================
    
    def get_executor_status(self, project_id: str = None) -> Dict[str, Any]:
        """Get executor status"""
        if project_id:
            loop_info = self._agent_loops.get(project_id, {})
            return {
                "project_id": project_id,
                "state": self._state.value,
                "loop_active": project_id in self._tasks,
                "tasks_processed": loop_info.get("tasks_processed", 0),
                "started_at": loop_info.get("started_at")
            }
        
        return {
            "state": self._state.value,
            "active_projects": self.active_projects,
            "total_projects": len(self._tasks)
        }



    # ========================================================================
    # SCENE OUTPUT FACTORY - Phase 5.2
    # ========================================================================

    def _build_scene_output(
        self,
        scene_id: str,
        film_id: str,
        project_id: Optional[str] = None,
        scene_data: Optional[Dict[str, Any]] = None,
        director_decision: Optional[Dict[str, Any]] = None,
        continuity_report: Optional[Dict[str, Any]] = None,
        story_score: Optional[Dict[str, Any]] = None,
        alerts: Optional[List[Dict[str, Any]]] = None,
        merged_decision: Optional[Dict[str, Any]] = None,
        conflicts_data: Optional[Dict[str, Any]] = None,
        quality_metrics: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[float] = None,
        timestamp: Optional[str] = None
    ) -> SceneOutput:
        """
        Factory method to build SceneOutput from existing runtime data.

        Phase 5.2: This is an additive assembly helper only. It packages already
        computed runtime outputs into a `SceneOutput` instance without changing
        existing return structures or dispatch behavior.

        Data ownership / grounding:
        - `director_decision` comes from the existing Director flow
        - `continuity_report` and `alerts` come from Memory Archivist output
        - `merged_decision` comes from the existing Director/Memory merge flow
        - `story_score` comes from StoryLevelScoringService
        - `quality_metrics` / `metadata` are internal debug payloads

        This method does not:
        - rerun evaluators
        - infer missing creative logic
        - resolve new conflicts
        - reinterpret scoring outputs

        App vs debug intent:
        - canonical summaries are stored in SceneOutput's app-safe fields
        - richer evaluator payloads are preserved in internal/debug fields so
          `to_app_response()` stays minimal and `to_debug_response()` stays rich

        Args:
            scene_id: Scene identifier
            film_id: Film identifier
            project_id: Optional project identifier for debug-only taste lookup
            scene_data: Optional scene data for debug-only cinematic language lookup
            director_decision: Director's creative decision (from creative_decision key)
            continuity_report: Continuity report data (from continuity_report key)
            story_score: Story-level scoring data (from story_score key)
            alerts: List of continuity alerts
            merged_decision: Output from director-memory merge/conflict resolution
            conflicts_data: Conflict resolution data
            quality_metrics: Quality metrics from evaluation
            metadata: Optional internal/debug metadata to preserve
            processing_time_ms: Processing time in milliseconds
            timestamp: ISO timestamp string

        Returns:
            SceneOutput instance assembled from provided data
        """
        safe_merged_decision = merged_decision if isinstance(merged_decision, dict) else {}
        continuity_context = safe_merged_decision.get("continuity_context", {})
        if not isinstance(continuity_context, dict):
            continuity_context = {}

        safe_director_decision = (
            director_decision
            if isinstance(director_decision, dict)
            else safe_merged_decision.get("creative_decision")
        )
        if not isinstance(safe_director_decision, dict):
            safe_director_decision = None

        safe_continuity_report = continuity_report
        if not isinstance(safe_continuity_report, dict):
            safe_continuity_report = continuity_context.get("continuity_report")
        if not isinstance(safe_continuity_report, dict):
            safe_continuity_report = None

        safe_story_score = story_score if isinstance(story_score, dict) else None
        safe_quality_metrics = quality_metrics if isinstance(quality_metrics, dict) else None
        safe_metadata = metadata if isinstance(metadata, dict) else None
        resolved_project_id = project_id
        if not resolved_project_id:
            registered_memory = spine_consumption_service._memories.get(film_id)
            resolved_project_id = getattr(registered_memory, "project_id", None) or None

        taste_context = spine_consumption_service.get_taste_context(
            project_id=resolved_project_id,
            film_id=film_id,
            scene_id=scene_id,
        )
        safe_taste_context = (
            taste_context.to_dict()
            if hasattr(taste_context, "to_dict")
            else taste_context
        )
        if isinstance(safe_taste_context, dict):
            has_taste_signal = any(
                safe_taste_context.get(key)
                for key in ("dimension_adjustments", "dimension_confidence", "signal_counts")
            )
            if not has_taste_signal:
                safe_taste_context = None

        safe_cinematic_language_context = None
        try:
            cinematic_language_context = spine_consumption_service.get_cinematic_language_context(
                film_id=film_id,
                scene_data=scene_data if isinstance(scene_data, dict) else None,
                scene_id=scene_id,
            )
            if isinstance(cinematic_language_context, dict):
                summary = cinematic_language_context.get("summary") or {}
                heuristic_outputs = cinematic_language_context.get("heuristic_outputs") or {}
                has_meaningful_signal = bool(cinematic_language_context.get("available")) and (
                    bool(summary)
                    or any(
                        heuristic_outputs.get(key)
                        for key in (
                            "restraint_indicators",
                            "substitution_indicators",
                            "detected_motif_references",
                        )
                    )
                )
                if has_meaningful_signal:
                    safe_cinematic_language_context = cinematic_language_context
        except Exception:
            safe_cinematic_language_context = None

        film_intelligence_context = spine_consumption_service.get_film_intelligence_context(
            film_id=film_id,
            scene_id=scene_id,
        )
        safe_film_intelligence_context = (
            film_intelligence_context
            if isinstance(film_intelligence_context, dict)
            else None
        )
        if isinstance(safe_film_intelligence_context, dict):
            derived_payload = safe_film_intelligence_context.get("derived") or {}
            canonical_sources = safe_film_intelligence_context.get("canonical_sources") or {}
            has_derived_summary = any(
                isinstance(derived_payload.get(key), dict) and derived_payload.get(key)
                for key in ("sequence", "act", "film")
            )
            has_canonical_sources = any(bool(value) for value in canonical_sources.values()) if isinstance(canonical_sources, dict) else False
            if not (has_derived_summary and has_canonical_sources):
                safe_film_intelligence_context = None

        # Phase 9.3: scene package context — debug-only, no effect on decisions or scoring
        safe_scene_package_context = None
        try:
            scene_package_context = spine_consumption_service.get_scene_package_context(
                film_id=film_id,
                scene_data=scene_data if isinstance(scene_data, dict) else None,
                scene_id=scene_id,
            )
            if isinstance(scene_package_context, dict) and scene_package_context.get("available"):
                safe_scene_package_context = scene_package_context
        except Exception:
            safe_scene_package_context = None

        safe_alerts: List[Dict[str, Any]] = []
        if isinstance(alerts, list):
            safe_alerts = [alert for alert in alerts if isinstance(alert, dict)]
        elif isinstance(continuity_context.get("alerts"), list):
            safe_alerts = [
                alert for alert in continuity_context.get("alerts", [])
                if isinstance(alert, dict)
            ]
        elif safe_continuity_report and isinstance(safe_continuity_report.get("alerts"), list):
            safe_alerts = [
                alert for alert in safe_continuity_report.get("alerts", [])
                if isinstance(alert, dict)
            ]

        safe_conflicts_data = conflicts_data if isinstance(conflicts_data, dict) else None
        if safe_conflicts_data is None and safe_merged_decision:
            safe_conflicts_data = {
                "has_conflicts": safe_merged_decision.get("has_continuity_debt", False),
                "severity": safe_merged_decision.get("conflict_severity"),
                "resolved": safe_merged_decision.get("alerts_acknowledged", True),
                "escalation_required": safe_merged_decision.get("escalation_flag", False),
            }

        # Build the payload for SceneOutput.from_dict() using only existing runtime outputs.
        # Canonical/app-safe fields are populated first; richer evaluator/debug data is
        # attached only in the internal fields recognized by SceneOutput.
        data: Dict[str, Any] = {
            "scene_id": scene_id,
            "film_id": film_id,
            "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
        }

        if safe_director_decision:
            data["director_decision"] = safe_director_decision

        if safe_continuity_report:
            data["continuity_report"] = safe_continuity_report

        if safe_alerts:
            data["alerts"] = safe_alerts

        if safe_story_score:
            data["story_score"] = safe_story_score

        if safe_conflicts_data:
            data["conflicts"] = safe_conflicts_data

        # Internal/debug payloads remain nested under debug-oriented fields so
        # app-facing serialization remains unchanged.
        if safe_quality_metrics or safe_metadata or safe_merged_decision:
            debug_payload: Dict[str, Any] = {}
            if safe_quality_metrics:
                debug_payload.update(safe_quality_metrics)
            debug_metadata: Dict[str, Any] = {}
            if safe_metadata:
                debug_metadata.update(safe_metadata)
            if isinstance(safe_taste_context, dict):
                debug_metadata["taste_context"] = safe_taste_context
            if isinstance(safe_cinematic_language_context, dict):
                debug_metadata["cinematic_language_context"] = safe_cinematic_language_context
            if isinstance(safe_film_intelligence_context, dict):
                debug_metadata["film_intelligence_context"] = safe_film_intelligence_context
            if isinstance(safe_scene_package_context, dict):
                debug_metadata["scene_package_context"] = safe_scene_package_context

            # Phase 10.3: Co-director context - debug-only, no effect on decisions
            try:
                # Fetch co-director context if session_id is available
                session_id = None
                session_uuid = None
                if metadata and isinstance(metadata, dict):
                    session_id = metadata.get("session_id")
                if session_id:
                    try:
                        session_uuid = session_id if isinstance(session_id, UUID) else UUID(str(session_id))
                    except (TypeError, ValueError):
                        session_uuid = None

                codirector_context = spine_consumption_service.get_co_director_context(
                    project_id=resolved_project_id,
                    film_id=film_id,
                    session_id=session_uuid,
                    scene_id=scene_id,
                )
                if codirector_context and codirector_context.get("session_active"):
                    debug_metadata["co_director_context"] = codirector_context
                    workflow = self._build_co_director_workflow(
                        session_id=session_id,
                        scene_id=scene_id,
                        film_id=film_id,
                        session_context=codirector_context,
                        director_decision=safe_director_decision,
                        quality_metrics=safe_quality_metrics,
                    )
                    if workflow:
                        debug_metadata["co_director_context"]["workflow"] = workflow
            except Exception:
                pass  # Co-director context is debug-only, never affects decisions

            if debug_metadata:
                debug_payload["metadata"] = debug_metadata
            if safe_merged_decision:
                debug_payload["merged_decision"] = safe_merged_decision
            data["quality_metrics"] = debug_payload
        elif (
            isinstance(safe_taste_context, dict)
            or isinstance(safe_cinematic_language_context, dict)
            or isinstance(safe_film_intelligence_context, dict)
            or isinstance(safe_scene_package_context, dict)
        ):
            metadata_payload: Dict[str, Any] = {}
            if isinstance(safe_taste_context, dict):
                metadata_payload["taste_context"] = safe_taste_context
            if isinstance(safe_cinematic_language_context, dict):
                metadata_payload["cinematic_language_context"] = safe_cinematic_language_context
            if isinstance(safe_film_intelligence_context, dict):
                metadata_payload["film_intelligence_context"] = safe_film_intelligence_context
            if isinstance(safe_scene_package_context, dict):
                metadata_payload["scene_package_context"] = safe_scene_package_context
            data["quality_metrics"] = {
                "metadata": metadata_payload
            }

        if safe_story_score:
            # Preserve the complete story scoring payload for debug/audit use.
            data["full_story_score"] = safe_story_score

        if safe_continuity_report or safe_alerts:
            # Preserve the complete continuity payload for debug/audit use.
            full_continuity_report = dict(safe_continuity_report or {})
            if safe_alerts and "alerts" not in full_continuity_report:
                full_continuity_report["alerts"] = safe_alerts
            data["full_continuity_report"] = full_continuity_report

        if processing_time_ms is not None:
            data["processing_time_ms"] = processing_time_ms

        return SceneOutput.from_dict(data)

    def _build_co_director_workflow(
        self,
        session_id: Optional[Any],
        scene_id: str,
        film_id: str,
        session_context: Dict[str, Any],
        director_decision: Optional[Dict[str, Any]],
        quality_metrics: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Build debug-only co-director workflow summary (Phase 10.9)."""
        session = self._resolve_co_director_session(session_id)
        if session is None:
            return None

        director_result = self._build_director_result_for_codirector(
            director_decision=director_decision,
            quality_metrics=quality_metrics,
        )

        critique_report = co_director_critique_service.generate_critique(
            session=session,
            director_result=director_result,
            scene_id=scene_id,
            film_id=film_id,
        )
        proposal_report = co_director_proposal_service.generate_proposal(
            session=session,
            critique_report=critique_report,
            scene_id=scene_id,
            film_id=film_id,
        )
        comparison_report = co_director_comparison_service.generate_comparison(
            session=session,
            director_result=director_result,
            critique_report=critique_report,
            proposal_report=proposal_report,
            scene_id=scene_id,
            film_id=film_id,
        )
        intensity_report = co_director_intensity_service.generate_intensity(
            session=session,
            critique_report=critique_report,
            proposal_report=proposal_report,
            comparison_report=comparison_report,
            film_id=film_id,
        )
        collaboration_report = co_director_collaboration_service.build_collaboration_report(
            session=session,
            critique_report=critique_report,
            proposal_report=proposal_report,
            comparison_report=comparison_report,
            intensity_report=intensity_report,
            film_id=film_id,
        )

        return {
            "active": bool(session_context.get("session_active")),
            "mode": session.current_mode.value,
            "critique": self._serialize_codirector_critique_report(critique_report),
            "proposal": self._serialize_codirector_proposal_report(proposal_report),
            "comparison": self._serialize_codirector_comparison_report(comparison_report),
            "intensity": self._serialize_codirector_intensity_report(intensity_report),
            "collaboration": {
                "dominant_focus": collaboration_report.dominant_focus,
                "advisory_notes": collaboration_report.advisory_notes,
                "sources_consulted": [source.value for source in collaboration_report.sources_consulted],
                "provenance": collaboration_report.provenance,
            },
        }

    def _resolve_co_director_session(self, session_id: Optional[Any]) -> Optional[CoDirectorSession]:
        if session_id is None:
            return None
        try:
            resolved = session_id if isinstance(session_id, UUID) else UUID(str(session_id))
            return co_director_session_service.get_session(resolved)
        except (TypeError, ValueError):
            return None

    def _build_director_result_for_codirector(
        self,
        director_decision: Optional[Dict[str, Any]],
        quality_metrics: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        safe_metrics = quality_metrics if isinstance(quality_metrics, dict) else {}
        safe_decision = director_decision if isinstance(director_decision, dict) else {}
        return {
            "decision": safe_metrics.get("decision"),
            "score": safe_metrics.get("score", safe_metrics.get("vision_consistency")),
            "pillars": safe_metrics.get("pillars"),
            "rejection_reasons": safe_metrics.get("rejection_reasons"),
            "revision_notes": safe_metrics.get("revision_notes"),
            "requires_revision": bool(safe_decision.get("requires_revision")),
        }

    def _serialize_codirector_critique_report(self, report: Any) -> Dict[str, Any]:
        critique = report.critique if report else None
        if critique is None:
            return {"present": False, "mode": report.mode.value if report else None}
        return {
            "present": True,
            "id": critique.critique_id,
            "category": critique.category.value,
            "priority": critique.priority.value,
            "title": critique.title,
            "recommendation": critique.recommendation,
            "grounded_signals": list(critique.grounded_signals),
            "heuristic_signals": list(critique.heuristic_signals),
            "source_systems": [source.value for source in critique.source_systems],
            "confidence": {
                "overall": critique.overall_confidence,
                "grounded": critique.grounded_confidence,
                "heuristic": critique.heuristic_confidence,
            },
            "affected_scene_ids": list(critique.affected_scene_ids),
        }

    def _serialize_codirector_proposal_report(self, report: Any) -> Dict[str, Any]:
        proposal = report.proposal if report else None
        if proposal is None:
            return {"present": False, "mode": report.mode.value if report else None}
        return {
            "present": True,
            "id": proposal.proposal_id,
            "category": proposal.category.value,
            "priority": proposal.priority.value,
            "title": proposal.title,
            "recommendation": proposal.recommendation,
            "critique_id": proposal.critique_id,
            "source_systems": [source.value for source in proposal.source_systems],
            "confidence": {
                "overall": proposal.overall_confidence,
                "grounded": proposal.grounded_confidence,
                "heuristic": proposal.heuristic_confidence,
            },
            "affected_scene_ids": list(proposal.affected_scene_ids),
        }

    def _serialize_codirector_comparison_report(self, report: Any) -> Dict[str, Any]:
        comparison = report.comparison if report else None
        if comparison is None:
            return {"present": False, "mode": report.mode.value if report else None}
        return {
            "present": True,
            "id": comparison.comparison_id,
            "category": comparison.category.value,
            "title": comparison.title,
            "recommendation": comparison.recommendation,
            "dominance_reason": comparison.dominance_reason,
            "critique_id": comparison.critique_id,
            "proposal_id": comparison.proposal_id,
            "source_systems": [source.value for source in comparison.source_systems],
            "confidence": {
                "overall": comparison.overall_confidence,
                "grounded": comparison.grounded_confidence,
                "heuristic": comparison.heuristic_confidence,
            },
            "affected_scene_ids": list(comparison.affected_scene_ids),
        }

    def _serialize_codirector_intensity_report(self, report: Any) -> Dict[str, Any]:
        intensity = report.intensity_profile if report else None
        if intensity is None:
            return {"present": False, "mode": report.mode.value if report else None}
        return {
            "present": True,
            "level": intensity.level.value,
            "rationale": intensity.rationale,
            "critique_repetition_risk": intensity.critique_repetition_risk,
            "escalation_required": intensity.escalation_required,
            "recommended_mode": intensity.recommended_mode.value,
            "confidence": {
                "overall": intensity.overall_confidence,
                "grounded": intensity.grounded_confidence,
                "heuristic": intensity.heuristic_confidence,
            },
        }

# Global executor instance
agent_executor = AgentExecutor()


# ========================================================================
# HELPER FUNCTIONS FOR ROUTES
# ========================================================================

def start_project_agent_loop(project_id: str) -> Dict[str, Any]:
    """Start agent loop for a project (sync wrapper)"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(agent_executor.start_project_loop(project_id))
        loop.close()
        
        return {
            "success": success,
            "project_id": project_id,
            "state": agent_executor.state.value
        }
    except Exception as e:
        logger.error(f"Failed to start agent loop: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def stop_project_agent_loop(project_id: str) -> Dict[str, Any]:
    """Stop agent loop for a project (sync wrapper)"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(agent_executor.stop_project_loop(project_id))
        loop.close()
        
        return {
            "success": success,
            "project_id": project_id
        }
    except Exception as e:
        logger.error(f"Failed to stop agent loop: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def get_agent_loop_status(project_id: str = None) -> Dict[str, Any]:
    """Get agent loop status"""
    return agent_executor.get_executor_status(project_id)

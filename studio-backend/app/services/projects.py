from datetime import datetime
import logging
from typing import Optional, Dict, List, Any
from uuid import UUID

logger = logging.getLogger("studio-projects")
from app.models import (
    StudioProject, StudioOverview, BuildInfo, SourceStats, RenderProvider,
    ProductionBible, ProviderIntegration, CrewAgent, ApprovalGate, StoryboardShot,
    RenderJob, RightsSafetyBoard, ReferenceStudyLibrary, InteractiveModules,
    ProducerDashboard, ProjectDashboard, PipelineCard, AgentActivity,
    ContinuityRegister, ContinuityIssue, StudyReference, RenderJobModel
)
from app.data.storage import StorageInterface
from app.services.project_store import project_store
from app.services.render import render_service
from app.services.script_parser import parse_screenplay
from app.services.crew import crew_service
from app.models.crew import AgentRole, TaskType
from app.services.spine_consumption_service import spine_consumption_service


class ProjectService:
    """Business logic for project operations"""

    def __init__(self, storage: StorageInterface):
        self.storage = storage

    def get_overview(self) -> StudioOverview:
        projects_dict = self.storage.get_all_projects()
        if not projects_dict:
            # Ensure local QA has a real project to load (avoids UI falling back to mock data on 404).
            self.create_demo_project(demo_id="local_seed")
            projects_dict = self.storage.get_all_projects()

        projects_list = list(projects_dict.values())
        return StudioOverview(
            build=BuildInfo(name="studio-backend", version="1.0.0", status="healthy"),
            projects=projects_list,
            latest_project=projects_list[0] if projects_list else None
        )

    def get_project(self, project_id: str, session_id: Optional[str] = None) -> Optional[StudioProject]:
        project = self.storage.get_project(project_id)
        if not project:
            return None
        return self._attach_inspection_snapshots(project, session_id=session_id)

    def create_project(self, project: StudioProject) -> StudioProject:
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project)

    def update_project(self, project: StudioProject) -> StudioProject:
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project)

    def _attach_inspection_snapshots(
        self,
        project: StudioProject,
        session_id: Optional[str] = None,
    ) -> StudioProject:
        """
        Attach bounded, read-only inspection snapshots when available.

        This method is additive-only and observational:
        - no evaluator/scoring logic
        - no authority mutation
        - no control behavior changes
        """
        enriched = project.model_copy(deep=True)

        if enriched.co_director_workflow is None:
            existing_workflow = self._get_existing_co_director_workflow(enriched)
            if existing_workflow is not None:
                enriched.co_director_workflow = existing_workflow

        if enriched.co_director_workflow is None and session_id:
            co_director_snapshot = self._build_co_director_session_snapshot(
                project_id=enriched.project_id,
                session_id=session_id,
            )
            if co_director_snapshot is not None:
                enriched.co_director_workflow = co_director_snapshot

        if enriched.execution_summary is None:
            existing_execution_summary = self._get_existing_execution_summary(enriched)
            if existing_execution_summary is not None:
                enriched.execution_summary = existing_execution_summary

        if enriched.execution_summary is None:
            enriched.execution_summary = self._build_execution_summary_from_render_queue(enriched)

        return enriched

    def _get_existing_co_director_workflow(self, project: StudioProject) -> Optional[Dict[str, Any]]:
        if isinstance(project.co_director_workflow, dict):
            return dict(project.co_director_workflow)

        modules = project.interactive_modules
        if modules and isinstance(modules.co_director_workflow, dict):
            return dict(modules.co_director_workflow)
        if modules and isinstance(modules.co_director, dict):
            return dict(modules.co_director)

        if project.producer_dashboard and isinstance(project.producer_dashboard.co_director_workflow, dict):
            return dict(project.producer_dashboard.co_director_workflow)
        if project.producer_dashboard and isinstance(project.producer_dashboard.co_director, dict):
            return dict(project.producer_dashboard.co_director)

        if project.project_dashboard and isinstance(project.project_dashboard.co_director_workflow, dict):
            return dict(project.project_dashboard.co_director_workflow)
        if project.project_dashboard and isinstance(project.project_dashboard.co_director, dict):
            return dict(project.project_dashboard.co_director)

        return None

    def _get_existing_execution_summary(self, project: StudioProject) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        if isinstance(project.execution_summary, dict):
            candidates.append(dict(project.execution_summary))
        modules = project.interactive_modules
        if modules and isinstance(modules.execution_summary, dict):
            candidates.append(dict(modules.execution_summary))
        if modules and isinstance(modules.render_execution_summary, dict):
            candidates.append(dict(modules.render_execution_summary))

        if project.producer_dashboard and isinstance(project.producer_dashboard.execution_summary, dict):
            candidates.append(dict(project.producer_dashboard.execution_summary))
        if project.project_dashboard and isinstance(project.project_dashboard.execution_summary, dict):
            candidates.append(dict(project.project_dashboard.execution_summary))

        if not candidates:
            return None

        summary = dict(candidates[0])
        validation_inspection = self._extract_validation_inspection(candidates)
        if validation_inspection is not None and "validation_inspection" not in summary:
            summary["validation_inspection"] = validation_inspection
        return summary

    def _extract_validation_inspection(
        self,
        summaries: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Return the first existing validation report payload from summary surfaces.

        This is read-only wiring: it never computes validation and never mutates
        upstream records.
        """
        if not summaries:
            return None

        validation_keys = (
            "validation_inspection",
            "validation_report",
            "render_validation_report",
            "render_validation",
        )
        for summary in summaries:
            for key in validation_keys:
                value = summary.get(key)
                if isinstance(value, dict):
                    return dict(value)
        return None

    def _build_co_director_session_snapshot(
        self,
        project_id: str,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            resolved_session_id = UUID(session_id)
        except (TypeError, ValueError):
            # Invalid session id is intentionally harmless and non-fatal.
            return None

        context = spine_consumption_service.get_co_director_context(
            project_id=project_id,
            film_id=project_id,
            session_id=resolved_session_id,
            scene_id=None,
        )

        if not isinstance(context, dict):
            return None

        mode = context.get("current_mode")
        if not isinstance(mode, str):
            return None

        workflow: Dict[str, Any] = {}
        if isinstance(context.get("workflow"), dict):
            workflow = dict(context["workflow"])

        return {
            "mode": mode,
            "workflow_active": bool(context.get("session_active")) and mode != "passive",
            "critique": workflow.get("critique"),
            "proposal": workflow.get("proposal"),
            "comparison": workflow.get("comparison"),
            "intensity": workflow.get("intensity"),
            "session_id": str(resolved_session_id),
            "source": "spine_consumption_context",
            "notes": list(context.get("notes", [])) if isinstance(context.get("notes"), list) else [],
        }

    def _build_execution_summary_from_render_queue(self, project: StudioProject) -> Optional[Dict[str, Any]]:
        if not project.render_queue:
            return None

        normalized_jobs: List[Dict[str, str]] = []
        for job in project.render_queue:
            if isinstance(job, dict):
                provider = str(job.get("provider") or "").strip()
                status = str(job.get("status") or "").strip().lower()
            else:
                provider = str(getattr(job, "provider", "") or "").strip()
                status = str(getattr(job, "status", "") or "").strip().lower()
            if provider or status:
                normalized_jobs.append({"provider": provider, "status": status})

        if not normalized_jobs:
            return None

        active_statuses = {"rendering", "active", "running", "in_progress", "in-progress"}
        queued_statuses = {"pending", "queued"}
        error_statuses = {"failed", "error"}
        artifact_statuses = {"complete", "completed", "ready", "success", "succeeded"}

        statuses = [job["status"] for job in normalized_jobs if job["status"]]
        providers = [job["provider"] for job in normalized_jobs if job["provider"]]

        if any(status in active_statuses for status in statuses):
            lifecycle_state = "in_progress"
            provider_status = "rendering"
        elif any(status in queued_statuses for status in statuses):
            lifecycle_state = "pending"
            provider_status = "pending"
        elif any(status in error_statuses for status in statuses):
            lifecycle_state = "failed"
            provider_status = "failed"
        elif any(status in artifact_statuses for status in statuses):
            lifecycle_state = "complete"
            provider_status = "complete"
        else:
            lifecycle_state = statuses[0] if statuses else "unknown"
            provider_status = lifecycle_state

        provider_name = (
            providers[0]
            if providers
            else (
                project.render_provider.provider_name
                if project.render_provider and project.render_provider.provider_name
                else "unknown"
            )
        )

        return {
            "provider_name": provider_name,
            "lifecycle_state": lifecycle_state,
            "provider_status": provider_status,
            "has_output_artifacts": any(status in artifact_statuses for status in statuses),
            "has_error": any(status in error_statuses for status in statuses),
            "latest_updated_at": project.updated_at or None,
            "source": "derived_from_render_queue",
        }

    def create_demo_project(self, demo_id: Optional[str] = None) -> StudioProject:
        new_id = f"demo-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        project = StudioProject(
            project_id=new_id,
            title=f"Demo Project {new_id}",
            updated_at=datetime.now().isoformat(),
            source_stats=SourceStats(),
            render_provider=RenderProvider(provider_name="demo", provider_model="demo", status="ready", mode="demo"),
            production_bible=ProductionBible(),
        )
        return self.storage.save_project(project)

    def ingest_script(self, title: str, creative_intent: str, render_provider: str, script_text: str) -> StudioProject:
        """
        Ingest a screenplay and automatically:
        1. Parse scenes, characters, locations
        2. Initialize project memory
        3. Create initial storyboard wall entries
        4. Initialize crew agents
        """
        new_id = f"project-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Parse the screenplay
        parsed_data = parse_screenplay(script_text)
        
        # Create project with parsed stats
        project = StudioProject(
            project_id=new_id,
            title=title,
            updated_at=datetime.now().isoformat(),
            source_stats=SourceStats(
                scene_count=parsed_data["source_stats"]["scene_count"],
                character_count=parsed_data["source_stats"]["character_count"],
                word_count=len(script_text.split())
            ),
            render_provider=RenderProvider(provider_name=render_provider, provider_model="default", status="ready", mode="batch"),
            production_bible=ProductionBible(creative_intent=creative_intent),
        )
        
        # Initialize crew agents
        project.crew_agents = [
            CrewAgent(agent_id="director", name="Director Agent", task="Guard tone and character arc", status="pending", color="#f59e0b", department="Directing"),
            CrewAgent(agent_id="script_analyst", name="Script Analyst", task="Analyze screenplay structure", status="pending", color="#10b981", department="Development"),
            CrewAgent(agent_id="storyboard_artist", name="Storyboard Artist", task="Plan shot composition", status="pending", color="#8b5cf6", department="Pre-Production"),
        ]
        
        # Create storyboard wall entries from parsed scenes
        for scene in parsed_data["scenes"][:50]:  # Limit to first 50 scenes
            storyboard_shot = StoryboardShot(
                shot_id=scene["scene_id"],
                scene=f"Scene {scene['scene_number']}: {scene['location']}",
                description=scene["description"][:200] if scene["description"] else ""[:200],
                status="pending"
            )
            project.storyboard_wall.append(storyboard_shot)
            
            # Create initial approval gate for each scene
            approval_gate = ApprovalGate(
                id=f"gate-{scene['scene_id']}",
                label=f"Scene {scene['scene_number']} Approval",
                status="pending",
                sub="Awaiting storyboard",
                detail=f"{scene['int_ext']} - {scene['location']}",
                shot_id=scene["scene_id"]
            )
            project.shot_approval_gates.append(approval_gate)
        
        # Initialize memory with parsed data (stored in project for now)
        # Store parsed data in production_bible for reference
        project.production_bible = ProductionBible(
            creative_intent=creative_intent,
        )
        
        return self.storage.save_project(project)
    
    def initialize_project_crew(self, project_id: str) -> tuple[Optional[StudioProject], Optional[str]]:
        """
        Initialize crew for a project - create crew tasks from storyboard.
        
        This now automatically:
        1. Creates crew project ownership
        2. Creates crew tasks for each storyboard scene
        3. Starts the agent execution loop
        
        Returns tuple of (project, error_message).
        """
        project = self.storage.get_project(project_id)
        if not project:
            return None, "Project not found"
        
        if not project.storyboard_wall:
            return project, "No storyboard wall entries found. Run script ingestion first."
        
        # Update crew agent statuses
        for agent in project.crew_agents:
            if agent.status == "pending":
                agent.status = "active"
        
        # Create crew project ownership (for orchestrator)
        # Include user-demo for API access
        crew_service.create_project(
            project_id=project_id,
            owner_user_id="system",
            creative_director_ids=["system", "user-demo"]
        )
        
        # Create crew tasks for each storyboard scene
        created_tasks = []
        for shot in project.storyboard_wall:
            scene_id = shot.shot_id
            
            # Task 1: Script Analysis for this scene
            task, error = crew_service.create_task(
                project_id=project_id,
                agent_role=AgentRole.SCRIPT_ANALYST,
                task_type=TaskType.ANALYSIS,
                title=f"Analyze scene {scene_id}",
                description=f"Break down scene {scene_id} for story beats and pacing",
                input_data={
                    "scene_id": scene_id,
                    "scene_description": shot.description,
                    "scene_location": shot.scene,
                    "script_text": getattr(project, 'script_text', '')
                },
                priority=5
            )
            if task:
                created_tasks.append(task.task_id)
            
            # Task 2: Storyboard planning for this scene (after analysis completes)
            task_depends = [created_tasks[-1]] if created_tasks else None
            task, error = crew_service.create_task(
                project_id=project_id,
                agent_role=AgentRole.STORYBOARD_ARTIST,
                task_type=TaskType.PLANNING,
                title=f"Plan shots for {scene_id}",
                description=f"Create shot composition plan for scene {scene_id}",
                input_data={
                    "scene_id": scene_id,
                    "scene_description": shot.description,
                    "creative_intent": project.production_bible.creative_intent if project.production_bible else ""
                },
                depends_on=task_depends,
                priority=4
            )
            if task:
                created_tasks.append(task.task_id)
        
        # Initialize producer dashboard
        project.producer_dashboard = ProducerDashboard(
            last_updated=datetime.now().isoformat(),
            dailies_count=0,
            screening_status="pending",
            priority_focus=["Review scene breakdown"],
            blockers=[]
        )
        
        # Initialize project dashboard
        project.project_dashboard = ProjectDashboard(
            cards=[
                PipelineCard(id="development", label="Development", status="active", progress=100, detail="Script ingested"),
                PipelineCard(id="preproduction", label="Pre-Production", status="active", progress=25, detail=f"{len(project.storyboard_wall)} scenes to plan"),
                PipelineCard(id="production", label="Production", status="pending", progress=0, detail="Pending storyboard approval"),
                PipelineCard(id="postproduction", label="Post-Production", status="pending", progress=0, detail="Pending renders"),
            ]
        )
        
        project.updated_at = datetime.now().isoformat()
        saved_project = self.storage.save_project(project)
        
        # Start the agent execution loop
        try:
            from app.services.agent_executor import start_project_agent_loop
            start_project_agent_loop(project_id)
            logger.info(f"Started agent loop for project {project_id}")
        except Exception as e:
            logger.warning(f"Could not start agent loop: {e}")
        
        return saved_project, None

    def simulate_screening(self, project_id: str) -> Optional[StudioProject]:
        project = self.storage.get_project(project_id)
        if not project:
            return None
        
        # Update approval gates
        for gate in project.shot_approval_gates:
            if gate.id == "creative":
                gate.status = "passed"
                gate.sub = "Screening approved"
        
        project.producer_dashboard = ProducerDashboard(
            last_updated=datetime.now().isoformat(),
            dailies_count=3,
            screening_status="complete"
        )
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project)

    def review_shot(self, project_id: str, shot_id: str, decision: str, note: str = "", auto_create_gate: bool = True) -> tuple[Optional[StudioProject], Optional[str]]:
        """
        Review a shot with validation.
        
        When decision is 'approved':
        - Automatically creates a render job
        - Submits the render job to the configured provider
        - Updates render_queue and gate
        
        Returns tuple of (project, error_message).
        If error_message is not None, the review failed and should not be counted as success.
        
        If auto_create_gate is True (default), creates an approval gate if one doesn't exist.
        """
        project = self.storage.get_project(project_id)
        if not project:
            return None, "Project not found"
        
        # Validate decision value
        valid_decisions = ["approved", "rejected", "needs_revision"]
        if decision not in valid_decisions:
            return project, f"Invalid decision '{decision}'. Must be one of: {', '.join(valid_decisions)}"
        
        # Find and update the shot gate
        shot_found = False
        for gate in project.shot_approval_gates:
            if gate.shot_id == shot_id:
                gate.status = "passed" if decision == "approved" else "rejected"
                gate.sub = decision
                gate.detail = note
                shot_found = True
                break
        
        # Auto-create gate if not found and auto_create_gate is enabled
        if not shot_found and auto_create_gate:
            new_gate = ApprovalGate(
                id=f"gate-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                label=f"Shot Review: {shot_id}",
                status="passed" if decision == "approved" else "rejected",
                sub=decision,
                detail=note,
                shot_id=shot_id
            )
            project.shot_approval_gates.append(new_gate)
            shot_found = True
        
        if not shot_found:
            available = [g.shot_id for g in project.shot_approval_gates] if project.shot_approval_gates else []
            return project, f"Shot '{shot_id}' not found in approval gates. Available: {available if available else 'none'}"
        
        # AUTO-RENDER: When approved, create render job automatically
        if decision == "approved":
            logger.info(f"Shot {shot_id} approved - auto-creating render job")
            
            # Get scene description for prompt generation
            scene_desc = ""
            for shot in project.storyboard_wall:
                if shot.shot_id == shot_id:
                    scene_desc = shot.description or ""
                    break
            
            # Generate render prompt from scene
            creative_intent = project.production_bible.creative_intent if project.production_bible else ""
            render_prompt = f"{scene_desc}. {creative_intent}" if scene_desc else creative_intent
            
            # Get render provider
            provider_name = project.render_provider.provider_name if project.render_provider else "simulated"
            
            # Create render job via render service
            try:
                from app.services.render import render_service
                job = render_service.create_job(
                    project_id=project_id,
                    shot_id=shot_id,
                    prompt=render_prompt,
                    provider=provider_name
                )
                
                if job:
                    logger.info(f"Created render job {job.id} for shot {shot_id}")
                    
                    # Add to render queue
                    render_job = RenderJob(
                        render_id=job.id,
                        shot_id=shot_id,
                        status="pending",
                        progress=0,
                        eta="Queued",
                        cost_per_minute="0.00",
                        priority=True,
                        provider=provider_name,
                        selected=False,
                        score=0,
                        qc_note=""
                    )
                    project.render_queue.append(render_job)
                    
                    # Update gate with render job ID
                    for gate in project.shot_approval_gates:
                        if gate.shot_id == shot_id:
                            gate.render_id = job.id
                            break
                    
                    # Auto-submit for rendering (using sync wrapper for async method)
                    try:
                        import asyncio
                        # Run async submit in event loop
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # Create a new loop in a thread if we're already in an async context
                                import concurrent.futures
                                with concurrent.futures.ThreadPoolExecutor() as executor:
                                    future = executor.submit(asyncio.run, render_service.submit_job(job.id))
                                    submitted_job = future.result()
                            else:
                                submitted_job = loop.run_until_complete(render_service.submit_job(job.id))
                        except RuntimeError:
                            # No event loop, create one
                            submitted_job = asyncio.run(render_service.submit_job(job.id))
                        
                        logger.info(f"Submitted render job {job.id} for rendering")
                        
                        # Update status in queue
                        for rj in project.render_queue:
                            if rj.render_id == job.id:
                                rj.status = "rendering"
                                break
                    except Exception as e:
                        logger.warning(f"Could not auto-submit render job: {e}")
                        
            except Exception as e:
                logger.error(f"Failed to create render job: {e}")
        
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project), None
    
    def add_shot_to_approval_gates(self, project_id: str, shot_id: str, label: str = "") -> tuple[Optional[StudioProject], Optional[str]]:
        """
        Add a shot to approval gates.
        Returns tuple of (project, error_message).
        """
        project = self.storage.get_project(project_id)
        if not project:
            return None, "Project not found"
        
        # Check if shot already exists in gates
        for gate in project.shot_approval_gates:
            if gate.shot_id == shot_id:
                return project, f"Shot '{shot_id}' already exists in approval gates"
        
        # Add new gate
        new_gate = ApprovalGate(
            id=f"gate-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            label=label or f"Shot Review: {shot_id}",
            status="pending",
            sub="Awaiting review",
            detail="",
            shot_id=shot_id
        )
        project.shot_approval_gates.append(new_gate)
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project), None

    def record_dailies_select(self, project_id: str, render_id: str, selected: bool, score: int = 0, qc_note: str = "") -> Optional[StudioProject]:
        project = self.storage.get_project(project_id)
        if not project:
            return None
        
        for job in project.render_queue:
            if job.render_id == render_id:
                job.selected = selected
                job.qc_note = qc_note
                job.score = score
        
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project)

    async def retry_render(self, project_id: str, render_id: str) -> Optional[StudioProject]:
        project = self.storage.get_project(project_id)
        if not project:
            return None
        
        # Find the job in project render_queue
        queue_job = None
        for job in project.render_queue:
            if job.render_id == render_id:
                queue_job = job
                break
        
        if queue_job:
            provider_value = queue_job.provider if isinstance(queue_job.provider, str) else ""
            normalized_provider = provider_value.strip().lower()
            if normalized_provider == "simulated provider":
                normalized_provider = "simulated"

            # Create a new render job in the render service
            new_job = await render_service.create_and_submit_job(
                project_id=project_id,
                shot_id=queue_job.shot_id,
                provider=normalized_provider or None,
                prompt="",  # Could be stored in job metadata
                reference_assets=[],
                parameters={}
            )
            queue_job.status = "rendering"
            queue_job.progress = 0
        
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project)

    def set_render_mode(self, project_id: str, live_mode: bool, provider_name: str = "") -> Optional[StudioProject]:
        project = self.storage.get_project(project_id)
        if not project:
            return None
        
        if project.render_provider:
            project.render_provider.live_mode = live_mode
            if provider_name:
                project.render_provider.provider_name = provider_name
        
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project)

    def update_storyboard_from_shot_plan(self, project_id: str, shot_id: str, shot_plan: Dict) -> tuple[Optional[StudioProject], Optional[str]]:
        """
        Update storyboard_wall entry from a shot plan.
        Connects crew task output to storyboard_wall.
        
        Args:
            project_id: Project ID
            shot_id: Shot/scene ID to update
            shot_plan: Dict with shot details (description, camera_angle, etc.)
        
        Returns:
            tuple of (project, error_message)
        """
        project = self.storage.get_project(project_id)
        if not project:
            return None, "Project not found"
        
        # Find and update the storyboard entry
        shot_found = False
        for shot in project.storyboard_wall:
            if shot.shot_id == shot_id:
                # Update with shot plan data
                if "description" in shot_plan:
                    shot.description = shot_plan["description"]
                if "camera_angle" in shot_plan:
                    shot.description = f"{shot.description} | Camera: {shot_plan['camera_angle']}"
                if "status" in shot_plan:
                    shot.status = shot_plan["status"]
                shot_found = True
                break
        
        # Also update the corresponding approval gate
        for gate in project.shot_approval_gates:
            if gate.shot_id == shot_id:
                if "approved" in shot_plan.get("status", "").lower() or shot_plan.get("status") == "approved":
                    gate.status = "pending"  # Keep pending until final review
                    gate.sub = "Shot planned"
                break
        
        if not shot_found:
            # Auto-create storyboard entry if not found
            new_shot = StoryboardShot(
                shot_id=shot_id,
                scene=shot_plan.get("scene", f"Shot: {shot_id}"),
                description=shot_plan.get("description", ""),
                status=shot_plan.get("status", "planned")
            )
            project.storyboard_wall.append(new_shot)
        
        project.updated_at = datetime.now().isoformat()
        return self.storage.save_project(project), None

    def get_storyboard_wall(self, project_id: str) -> Optional[List[StoryboardShot]]:
        """Get storyboard wall entries for a project"""
        project = self.storage.get_project(project_id)
        if not project:
            return None
        return project.storyboard_wall

    def get_pending_shots(self, project_id: str) -> tuple[Optional[List[Dict]], Optional[str]]:
        """
        Get all pending shots that need approval.
        Used to connect crew tasks to approval workflow.
        """
        project = self.storage.get_project(project_id)
        if not project:
            return None, "Project not found"
        
        pending = []
        for gate in project.shot_approval_gates:
            if gate.status == "pending":
                # Find corresponding storyboard entry
                storyboard_entry = None
                for shot in project.storyboard_wall:
                    if shot.shot_id == gate.shot_id:
                        storyboard_entry = shot
                        break
                
                pending.append({
                    "shot_id": gate.shot_id,
                    "label": gate.label,
                    "status": gate.status,
                    "storyboard": storyboard_entry.model_dump() if storyboard_entry else None
                })
        
        return pending, None


class ReferenceStudyService:
    """Business logic for reference study operations"""

    def __init__(self, storage=None):
        self.storage = storage

    @staticmethod
    def _derive_title_from_filename(filename: str) -> str:
        import os
        base = os.path.splitext(os.path.basename(filename))[0]
        title = base.replace('_', ' ').replace('-', ' ').strip()
        return title.title() if title else "Untitled"

    def study_reference_prompt(
        self,
        project_id: str,
        reference_prompt: str,
        study_focus: str = "cinematography",
    ) -> tuple[StudyReference, Optional[str]]:
        """
        Create a study reference and link it to a project.
        Returns tuple of (study_reference, error_message).
        """
        study_ref = StudyReference(
            reference_id=f"study-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            filename="prompt_analysis",
            content_type="text",
            rights_status="analysis_only",
            allowed_use="study_only",
            study_focus=study_focus,
            source_stats={},
            extraction_status="complete",
            study_cards=[
                {
                    "agent": "director",
                    "department": "directing",
                    "study_focus": "visual_language",
                    "observations_to_make": ["framing", "composition"],
                    "reusable_principles": ["rule_of_thirds"],
                    "forbidden_uses": [],
                    "handoff_to": ["storyboard"]
                }
            ],
            risk_register=[],
            next_actions=["Review extracted study cards", "Save to memory library"]
        )
        
        # Link to project if storage is available
        if self.storage:
            project = self.storage.get_project(project_id)
            if project:
                # Initialize reference_study_library if needed
                if project.reference_study_library is None:
                    project.reference_study_library = ReferenceStudyLibrary(studies=[])
                project.reference_study_library.studies.append(study_ref)
                self.storage.save_project(project)
                try:
                    project_store.save_project(project.model_dump(mode='json'))
                except Exception:
                    pass
            else:
                return study_ref, f"Warning: Project '{project_id}' not found. Study created but not linked."
        
        return study_ref, None

    def reorganize_reference_library(self, project_id: str, derive_category) -> dict:
        project = self.storage.get_project(project_id) if self.storage else None
        if not project:
            raise LookupError("Project not found")
        library = project.reference_study_library
        if not library or not library.studies:
            return {"project_id": project_id, "reorganized": 0, "studies": []}
        count = 0
        for study in library.studies:
            new_focus = derive_category(study.filename or "", study.notes or "")
            if study.study_focus != new_focus:
                study.study_focus = new_focus
                count += 1
        self.storage.save_project(project)
        return {
            "project_id": project_id,
            "reorganized": count,
            "total": len(library.studies),
            "studies": [
                {
                    "reference_id": study.reference_id,
                    "filename": study.filename,
                    "study_focus": study.study_focus,
                }
                for study in library.studies
            ],
            "_project": project,
        }

    async def study_reference_upload(
        self,
        project_id: str,
        file,
        rights_status: str,
        study_focus: str,
        notes: str,
        derived_title: Optional[str] = None,
        derived_summary: Optional[str] = None,
    ) -> tuple[StudyReference, Optional[str]]:
        """
        Create a study reference from file upload and link it to a project.
        Returns tuple of (study_reference, error_message).

        For markdown files, derived_title/summary are extracted from H1 + first paragraph.
        When title is not provided, it is derived from the filename.
        """
        filename = file.filename or "untitled"
        content_type = file.content_type or "application/octet-stream"

        # Derive title: use markdown H1 if available, fall back to filename-based title
        title = derived_title if derived_title else self._derive_title_from_filename(filename)

        final_filename = title
        final_notes = derived_summary if derived_summary else notes
        final_content_type = "text/markdown" if derived_title or derived_summary else content_type

        study_ref = StudyReference(
            reference_id=f"study-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            filename=final_filename,
            content_type=final_content_type,
            rights_status=rights_status,
            allowed_use="study_only" if rights_status != "licensed" else "production",
            study_focus=study_focus,
            notes=final_notes,
            source_stats={},
            extraction_status="complete",
            study_cards=[],
            risk_register=[],
            next_actions=["Review extracted study cards", "Save to memory library"]
        )
        
        # Link to project's reference_study_library
        if self.storage:
            project = self.storage.get_project(project_id)
            if project:
                # Initialize reference_study_library if needed
                if project.reference_study_library is None:
                    project.reference_study_library = ReferenceStudyLibrary(studies=[])
                project.reference_study_library.studies.append(study_ref)
                self.storage.save_project(project)
                try:
                    project_store.save_project(project.model_dump(mode='json'))
                except Exception:
                    pass
            else:
                return study_ref, f"Warning: Project '{project_id}' not found. Study created but not linked."
        
        return study_ref, None

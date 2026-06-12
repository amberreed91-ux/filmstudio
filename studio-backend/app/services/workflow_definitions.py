"""Predefined workflow definitions for common Studio workflows."""

from app.models import WorkflowDefinition, WorkflowStep


# Quick Short Film Workflow
QUICK_SHORT_FILM_WORKFLOW = WorkflowDefinition(
    workflow_id="quick_short_film",
    title="Quick Short Film",
    description="Generate a complete short film from concept to final assembly in one workflow",
    category="quick_film",
    steps=[
        WorkflowStep(
            step_id="create_project",
            name="Create Project",
            description="Create a new project for the short film",
            step_type="create_project",
            required_inputs=["title"],
            optional_inputs=["description"],
            timeout_seconds=30,
        ),
        WorkflowStep(
            step_id="generate_scenes",
            name="Generate Scenes",
            description="Generate scene breakdown and shot candidates",
            step_type="generate_scenes",
            required_inputs=["concept"],
            optional_inputs=["manual_overrides"],
            depends_on=["create_project"],
            timeout_seconds=300,
        ),
        WorkflowStep(
            step_id="render_shots",
            name="Render Shots",
            description="Render all shots for the short film",
            step_type="render_shots",
            required_inputs=["concept", "manual_overrides"],
            optional_inputs=["provider", "ratio", "duration_per_shot_seconds"],
            depends_on=["generate_scenes"],
            timeout_seconds=1800,
        ),
        WorkflowStep(
            step_id="assemble_film",
            name="Assemble Film",
            description="Assemble rendered shots into final short film",
            step_type="assemble_film",
            required_inputs=["concept", "manual_overrides"],
            optional_inputs=["title_card", "end_card", "soundtrack"],
            depends_on=["render_shots"],
            timeout_seconds=600,
        ),
    ],
    required_inputs={
        "title": "Film title",
        "concept": "Film concept or script",
    },
    optional_inputs={
        "description": "Film description",
        "manual_overrides": "Manual workflow overrides",
        "provider": "Render provider (runway/simulated)",
        "ratio": "Video aspect ratio (1280:720)",
        "duration_per_shot_seconds": "Duration per shot in seconds",
        "title_card": "Title card configuration",
        "end_card": "End card configuration",
        "soundtrack": "Soundtrack configuration",
    },
    estimated_duration_minutes=45,
    tags=["quick", "automated", "beginner", "short_film"],
)


# Revision Workflow
REVISION_WORKFLOW = WorkflowDefinition(
    workflow_id="revision_workflow",
    title="Clip Revision Workflow",
    description="Create revisions for specific clips based on review feedback",
    category="revision",
    steps=[
        WorkflowStep(
            step_id="create_review",
            name="Create Review",
            description="Create a review for the existing output",
            step_type="create_review",
            required_inputs=["output_url"],
            optional_inputs=["reviewer", "notes"],
            timeout_seconds=60,
        ),
        WorkflowStep(
            step_id="create_revision",
            name="Create Revision",
            description="Create revision jobs based on review feedback",
            step_type="create_revision",
            required_inputs=["review_id", "original_job_id", "revision_prompt"],
            optional_inputs=["provider"],
            depends_on=["create_review"],
            timeout_seconds=900,
        ),
    ],
    required_inputs={
        "output_url": "URL of the output to review",
        "original_job_id": "ID of the original render job",
        "revision_prompt": "Prompt for the revision",
    },
    optional_inputs={
        "reviewer": "Name of the reviewer",
        "notes": "Review notes",
        "provider": "Render provider for revision",
    },
    estimated_duration_minutes=20,
    tags=["revision", "feedback", "improvement"],
)


# Final Package Workflow
FINAL_PACKAGE_WORKFLOW = WorkflowDefinition(
    workflow_id="final_package_workflow",
    title="Final Package Workflow",
    description="Create a final delivery package with all necessary assets",
    category="package",
    steps=[
        WorkflowStep(
            step_id="create_package",
            name="Create Package",
            description="Create final delivery package",
            step_type="create_package",
            required_inputs=["final_output_url", "film_title"],
            optional_inputs=[
                "final_output_path",
                "has_title_card",
                "has_end_card", 
                "has_soundtrack",
                "metadata",
            ],
            timeout_seconds=300,
        ),
    ],
    required_inputs={
        "final_output_url": "URL of the final video output",
        "film_title": "Title of the film",
    },
    optional_inputs={
        "final_output_path": "Local path to final output",
        "has_title_card": "Include title card",
        "has_end_card": "Include end card",
        "has_soundtrack": "Include soundtrack",
        "metadata": "Additional metadata",
    },
    estimated_duration_minutes=10,
    tags=["package", "delivery", "final"],
)


# Review Workflow
REVIEW_WORKFLOW = WorkflowDefinition(
    workflow_id="review_workflow",
    title="Review and Feedback Workflow",
    description="Create structured review process for film outputs",
    category="review",
    steps=[
        WorkflowStep(
            step_id="create_review",
            name="Create Review",
            description="Create a structured review of the output",
            step_type="create_review",
            required_inputs=["output_url"],
            optional_inputs=["reviewer", "notes", "metadata"],
            timeout_seconds=60,
        ),
    ],
    required_inputs={
        "output_url": "URL of the output to review",
    },
    optional_inputs={
        "reviewer": "Name of the reviewer",
        "notes": "Review notes and feedback",
        "metadata": "Additional review metadata",
    },
    estimated_duration_minutes=15,
    tags=["review", "feedback", "quality"],
)


# Workflow Registry
WORKFLOW_REGISTRY = {
    QUICK_SHORT_FILM_WORKFLOW.workflow_id: QUICK_SHORT_FILM_WORKFLOW,
    REVISION_WORKFLOW.workflow_id: REVISION_WORKFLOW,
    FINAL_PACKAGE_WORKFLOW.workflow_id: FINAL_PACKAGE_WORKFLOW,
    REVIEW_WORKFLOW.workflow_id: REVIEW_WORKFLOW,
}


def get_workflow(workflow_id: str) -> WorkflowDefinition | None:
    """Get a workflow definition by ID."""
    return WORKFLOW_REGISTRY.get(workflow_id)


def list_workflows(category: str | None = None) -> list[WorkflowDefinition]:
    """List all workflows, optionally filtered by category."""
    workflows = list(WORKFLOW_REGISTRY.values())
    if category:
        workflows = [w for w in workflows if w.category == category]
    return workflows


def list_workflow_categories() -> list[str]:
    """List all available workflow categories."""
    return list(set(w.category for w in WORKFLOW_REGISTRY.values()))

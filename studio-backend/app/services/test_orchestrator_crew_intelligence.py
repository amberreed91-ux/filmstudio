from app.data.storage import DatabaseStorage
from app.services.orchestrator import ExecutionResult, OrchestratorConfig, StudioOrchestrator, TaskExecutor


class PassingPromptExecutor(TaskExecutor):
    def __init__(self):
        super().__init__("prompt_engineer")

    def execute(self, task, context):
        return ExecutionResult(
            success=True,
            output_data={
                "scene_id": "scene-001",
                "observation": "The prompt package is ready for render coordination.",
                "recommendation_summary": "Move the prompt package into provider-neutral render coordination.",
            },
            metrics={"scene_count": 1},
        )


def test_studio_orchestrator_records_crew_reasoning_and_handoff(tmp_path):
    storage = DatabaseStorage(str(tmp_path / "studio-data"))
    orchestrator = StudioOrchestrator(
        storage=storage,
        config=OrchestratorConfig(log_every_step=False),
    )
    orchestrator._executors["prompt_engineer"] = PassingPromptExecutor()
    storage.create_crew_task(
        {
            "task_id": "task-prompt-1",
            "project_id": "project-orchestrator-crew",
            "agent_role": "prompt_engineer",
            "task_type": "prompt_generation",
            "title": "Prompt Generation",
            "description": "Prepare render prompts.",
            "priority": 5,
            "input_data": {},
        }
    )

    result = orchestrator.run_once("project-orchestrator-crew")

    reasoning = storage.list_crew_reasoning_records("project-orchestrator-crew")
    handoffs = storage.list_crew_handoff_packets("project-orchestrator-crew")
    assert result["tasks_succeeded"] == 1
    assert reasoning
    assert reasoning[0]["task_id"] == "task-prompt-1"
    assert handoffs
    assert handoffs[0]["source_role"] == "prompt_engineer"
    assert handoffs[0]["target_role"] == "render_coordinator"

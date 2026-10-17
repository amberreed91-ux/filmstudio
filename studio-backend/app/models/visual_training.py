from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VisualTrainingStatus = Literal[
    "empty",
    "insufficient",
    "ready",
    "training",
    "complete",
    "failed",
]

# Job-side lifecycle status used by VisualTrainingService. The visual_models
# table (migration 63) persists the job transition alongside the final model.
# "queued" means the provider accepted the job but has not started it yet;
# "training" means the provider reports it actively running.
VisualTrainingJobStatus = Literal[
    "pending",
    "queued",
    "training",
    "complete",
    "failed",
    "cancelled",
]


class VisualTrainingJob(BaseModel):
    id: str
    project_id: str

    target_type: Literal[
        "character",
        "scene",
        "location",
        "style",
    ]

    target_id: str

    trigger: str

    preset: Literal[
        "quick",
        "medium",
        "high",
    ]

    image_count: int

    provider_train_type: Literal[
        "character",
        "style",
    ]

    rank: int | None = None
    alpha: float | None = None
    steps: int | None = None
    learning_rate: float | None = None
    resolution: str | None = None

    # Job-side state owned by VisualTrainingService. These fields mirror the
    # columns of the visual_models table so an in-memory job round-trips to
    # and from persistent storage without a second schema.
    provider: str = ""
    provider_model: str = ""
    # Provider-side job identity (e.g. Phosphene's train_job_id). Empty until
    # the provider accepts the submission; persisted inside the visual_models
    # configuration JSON so restart recovery can re-poll the provider.
    provider_job_id: str = ""
    source_asset_ids: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    status: VisualTrainingJobStatus = "pending"
    trained_model_id: str | None = None
    updated_at: str = ""

    created_at: str = ""
    completed_at: str | None = None
    error: str | None = ""

    class Config:
        use_enum_values = False


class VisualModel(BaseModel):
    id: str
    project_id: str

    target_type: str
    target_id: str

    training_id: str

    provider: str
    base_model: str
    model_version: str

    trigger: str

    dataset_reference: str | None = None
    output_reference: str | None = None

    status: Literal[
        "pending",
        "training",
        "complete",
        "failed",
        "cancelled",
    ]

    configuration: dict

    created_at: str
    completed_at: str | None = None
    error: str | None = ""

    class Config:
        use_enum_values = False
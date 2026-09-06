from enum import Enum
from pydantic import BaseModel, Field


class PromptPriority(str, Enum):
    PROVIDER = 'provider_required'
    IDENTITY = 'identity'
    CONTINUITY = 'continuity'
    INTENT = 'shot_intent'
    CINEMATOGRAPHY = 'cinematography'
    ENVIRONMENT = 'environment'
    ENRICHMENT = 'enrichment'
    OPTIONAL = 'optional_detail'


class PromptFact(BaseModel):
    fact_id: str
    text: str
    priority: PromptPriority
    source: str


class PromptBudgetResult(BaseModel):
    policy_version: str = 'whole-facts-v1'
    provider: str
    model: str
    limit: int
    unit: str = 'weighted_characters'
    limit_source: str
    prompt: str
    included_ids: list[str] = Field(default_factory=list)
    omitted_ids: list[str] = Field(default_factory=list)
    required_overflow_ids: list[str] = Field(default_factory=list)
    source_facts: list[PromptFact] = Field(default_factory=list)
    ready: bool = True

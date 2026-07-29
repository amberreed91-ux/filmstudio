from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AudioPlanScope = Literal["project", "scene", "shot", "asset"]
AudioPlanStatus = Literal["draft", "ready", "needs_creator_review", "superseded", "stale"]
AudioTrackType = Literal[
    "dialogue",
    "voiceover",
    "score",
    "ambience",
    "room_tone",
    "sfx",
    "silence",
    "transition",
    "final_mix",
]
AudioEvidenceSourceType = Literal[
    "script_scene",
    "dialogue_line",
    "performance_brief",
    "character_profile",
    "voice_casting",
    "creative_memory",
    "director_memory",
    "film_memory",
    "continuity",
    "creative_spine",
    "render_job",
    "audio_asset",
    "video_asset",
    "ffprobe",
    "provider_metadata",
    "manual_note",
]
AudioUncertaintyLabel = Literal["insufficient_context", "emerging", "supported", "conflicted"]
AudioReadinessLabel = Literal["ready", "needs_review", "blocked", "not_requested"]


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class AudioEvidenceRef(BaseModel):
    evidence_id: str
    source_type: AudioEvidenceSourceType
    source_id: str
    field_path: str = ""
    scene_id: str | None = None
    shot_id: str | None = None
    character_id: str | None = None
    asset_id: str | None = None
    excerpt: str = ""
    relevance: str = ""
    reliability_label: AudioUncertaintyLabel = "emerging"


class AudioMemoryRef(BaseModel):
    memory_id: str
    memory_type: str
    scope: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    summary: str = ""
    source_service: str = ""


class AudioSpineRef(BaseModel):
    constraint_id: str = ""
    field_name: str = ""
    summary: str = ""
    applied: bool = True
    risk_if_ignored: str = ""


class VoiceProviderBinding(BaseModel):
    binding_id: str
    provider: str
    voice_id: str = ""
    voice_name: str = ""
    voice_source_type: str = "unknown"
    voice_style_prompt: str = ""
    reference_asset_id: str | None = None
    configured: bool = False
    requires_network: bool = False
    last_verified_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CharacterVoiceProfile(BaseModel):
    profile_id: str
    project_id: str
    character_id: str
    character_name: str
    vocal_identity: str = ""
    cadence: str = ""
    emotional_range: list[str] = Field(default_factory=list)
    restraint_rules: list[str] = Field(default_factory=list)
    speech_patterns: list[str] = Field(default_factory=list)
    continuity_notes: str = ""
    provider_bindings: list[VoiceProviderBinding] = Field(default_factory=list)
    evidence_refs: list[AudioEvidenceRef] = Field(default_factory=list)
    memory_refs: list[AudioMemoryRef] = Field(default_factory=list)
    source_signature: str = ""
    status: AudioPlanStatus = "ready"
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True


class DialoguePerformanceCue(BaseModel):
    cue_id: str
    project_id: str
    plan_id: str
    scene_id: str
    shot_id: str | None = None
    line_id: str
    character_id: str
    character_name: str
    text: str
    spoken_intent: str = ""
    hidden_intent: str = ""
    delivery: str = ""
    pacing: str = "balanced"
    breath: str = ""
    pause_before_seconds: float = 0.0
    pause_after_seconds: float = 0.0
    overlap_behavior: str = "none"
    volume_intent: str = "natural"
    mix_priority: str = "dialogue_first"
    voice_profile_id: str | None = None
    performance_brief_id: str | None = None
    performance_beat_id: str | None = None
    evidence_refs: list[AudioEvidenceRef] = Field(default_factory=list)
    uncertainty_label: AudioUncertaintyLabel = "emerging"
    advisory_only: bool = True


class SoundscapeLayerPlan(BaseModel):
    layer_id: str
    project_id: str
    plan_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    track_type: AudioTrackType
    label: str
    intent: str = ""
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    intensity_label: str = "restrained"
    duck_under_dialogue: bool = False
    motif_refs: list[str] = Field(default_factory=list)
    provider_requirement: str = "provider_neutral"
    evidence_refs: list[AudioEvidenceRef] = Field(default_factory=list)
    memory_refs: list[AudioMemoryRef] = Field(default_factory=list)
    spine_refs: list[AudioSpineRef] = Field(default_factory=list)
    advisory_only: bool = True


class AudioMixRequirement(BaseModel):
    dialogue_priority: str = "foreground"
    score_position: str = "under_dialogue"
    ambience_position: str = "bed"
    sfx_position: str = "motivated_only"
    ducking_strategy: str = "duck music and ambience under dialogue"
    silence_strategy: str = ""
    final_container: str = "mp4"
    requires_audio_stream: bool = True
    preserve_existing_dialogue: bool = True
    notes: str = ""


class PerformanceAudioPlan(BaseModel):
    plan_id: str
    project_id: str
    scope: AudioPlanScope = "scene"
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    status: AudioPlanStatus = "ready"
    generated_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    model_version: str = "performance-audio-v1"
    source_signature: str = ""
    summary: str = ""
    voice_profiles: list[CharacterVoiceProfile] = Field(default_factory=list)
    dialogue_cues: list[DialoguePerformanceCue] = Field(default_factory=list)
    soundscape_layers: list[SoundscapeLayerPlan] = Field(default_factory=list)
    mix_requirements: AudioMixRequirement = Field(default_factory=AudioMixRequirement)
    provider_requirements: list[str] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[AudioEvidenceRef] = Field(default_factory=list)
    memory_refs: list[AudioMemoryRef] = Field(default_factory=list)
    spine_refs: list[AudioSpineRef] = Field(default_factory=list)
    crew_reasoning_id: str | None = None
    readiness_label: AudioReadinessLabel = "needs_review"
    blockers: list[str] = Field(default_factory=list)
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True


class AudioIntelligenceAssessment(BaseModel):
    assessment_id: str
    project_id: str
    plan_id: str
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    render_job_id: str | None = None
    generated_at: str = Field(default_factory=_now)
    source_signature: str = ""
    observed_audio_stream: bool = False
    observed_dialogue_presence: str = "unknown"
    observed_music_presence: str = "unknown"
    observed_ambience_presence: str = "unknown"
    voice_continuity_read: str = ""
    emotional_alignment_read: str = ""
    mix_read: str = ""
    missing_evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_refs: list[AudioEvidenceRef] = Field(default_factory=list)
    crew_reasoning_id: str | None = None
    readiness_label: AudioReadinessLabel = "needs_review"
    stale: bool = False
    stale_reason: str = ""
    advisory_only: bool = True


class PerformanceAudioPlanRequest(BaseModel):
    scene_id: str | None = None
    shot_id: str | None = None
    asset_id: str | None = None
    scope: AudioPlanScope = "scene"
    scene_context: dict[str, Any] = Field(default_factory=dict)
    force_refresh: bool = False
    persist: bool = True
    include_performance_context: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioIntelligenceAssessmentRequest(BaseModel):
    plan_id: str
    asset_id: str | None = None
    render_job_id: str | None = None
    audio_url: str | None = None
    local_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioExecutionRequest(BaseModel):
    plan_id: str
    project_id: str
    scene_id: str | None = None
    dialogue_lines: list[dict[str, Any]] = Field(default_factory=list)
    mood: str = ""
    score_notes: str = ""
    ambient_notes: str = ""
    instrumentation: str = ""
    tempo: str = ""
    silence_flag: bool = False
    estimated_duration_seconds: float | None = None
    provider_requirements: list[str] = Field(default_factory=list)
    advisory_only: bool = True


class PerformanceAudioDecisionRequest(BaseModel):
    decision_text: str
    inferred_tradeoff: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    plan_id: str | None = None
    cue_id: str | None = None
    layer_id: str | None = None
    profile_id: str | None = None
    assessment_id: str | None = None
    saved_by: str = "creator"
    save_to_project_memory: bool = False


class PerformanceAudioDecisionUpdateRequest(BaseModel):
    decision_text: str | None = None
    inferred_tradeoff: str | None = None


class PerformanceAudioDecisionProjection(BaseModel):
    decision_id: str
    project_id: str
    decision_text: str
    inferred_tradeoff: str = ""
    scene_id: str | None = None
    character_id: str | None = None
    plan_id: str | None = None
    cue_id: str | None = None
    layer_id: str | None = None
    profile_id: str | None = None
    assessment_id: str | None = None
    saved_by: str = "creator"
    saved_at: str = Field(default_factory=_now)
    memory_entry_id: str | None = None
    editable: bool = True
    forgotten_at: str | None = None


class PerformanceAudioDepartmentSignal(BaseModel):
    role: str = "Performance Audio"
    status: Literal["active", "standby"] = "standby"
    signal: str = "audio intelligence pending"
    plan_count: int = 0
    assessment_count: int = 0
    blocked_count: int = 0
    evidence_count: int = 0
    advisory: str = ""
    advisory_only: bool = True


class PerformanceAudioPlanResponse(BaseModel):
    plan: PerformanceAudioPlan
    reasoning_record_id: str = ""
    stale_existing_plan_ids: list[str] = Field(default_factory=list)
    advisory_only: bool = True

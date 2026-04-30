import { describe, expect, it } from 'vitest'
import type { StudioProject } from './studioApi'
import { extractExecutionSummaryInspection } from './executionSummaryInspection'

describe('extractExecutionSummaryInspection', () => {
  it('returns null when summary is absent', () => {
    const project = { project_id: 'p-absent' } satisfies StudioProject
    expect(extractExecutionSummaryInspection(project)).toBeNull()
  })

  it('uses safe defaults when provider_name and lifecycle_state are missing', () => {
    const project = {
      project_id: 'p-defaults',
      execution_summary: {
        studio_safety_state: {
          studio_state: 'safe_for_control_phase',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      providerName: 'unknown',
      lifecycleState: 'unknown',
      studioSafetyState: {
        studioState: 'safe_for_control_phase',
      },
    })
  })

  it('parses provider control visibility fields when present', () => {
    const project = {
      project_id: 'p-provider-control',
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        provider_config_snapshot: {
          default_provider: 'mock',
          enabled_providers: ['mock'],
          quality_priority: 'cinematic_quality',
          real_providers_enabled: false,
        },
        provider_credential_state: {
          provider: 'mock',
          enabled: true,
          credential_present: true,
          credential_source: 'none',
          reason: 'Mock provider does not require credentials',
        },
        provider_selection_state: {
          requested_provider: null,
          selected_provider: 'mock',
          allowed: true,
          fallback_used: false,
          reason: 'Default provider selected',
        },
        provider_readiness_summary: {
          provider: 'mock',
          enabled: true,
          credential_present: true,
          can_execute: false,
          reason: 'Execution not enabled',
        },
        provider_capability: {
          provider: 'mock',
          enabled: true,
          network_required: false,
          supports_render: true,
          supports_streaming: false,
          supports_sync: true,
          supports_multi_shot: false,
          requires_credentials: false,
        },
        provider_control_contract: {
          selection_mode: 'manual_only',
          auto_execution: false,
          execution_on_select: false,
          reason: 'Provider selection does not trigger execution',
        },
        provider_safety_contract: {
          real_provider_execution_enabled: false,
          reason: 'Real provider execution is disabled by safety boundary',
        },
        provider_payload_v2: {
          provider: 'mock',
          shot_id: 'shot_scene_001_001',
          prompt: {
            base_intent: 'Opening line',
            visual_tokens: [],
            shot_tokens: [],
          },
        },
        handoff_envelope: {
          request_id: 'handoff_mock_shot_scene_001_001',
          provider: 'mock',
          enabled: false,
        },
        handoff_audit: {
          requested: true,
          allowed: false,
          blocked_reason: 'Execution permission denied',
          timestamp: null,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      providerConfigSnapshot: {
        defaultProvider: 'mock',
        enabledProviders: ['mock'],
        qualityPriority: 'cinematic_quality',
        realProvidersEnabled: false,
      },
      providerCredentialState: {
        provider: 'mock',
        enabled: true,
        credentialPresent: true,
        credentialSource: 'none',
      },
      providerSelectionState: {
        requestedProvider: null,
        selectedProvider: 'mock',
        allowed: true,
        fallbackUsed: false,
      },
      providerReadinessSummary: {
        provider: 'mock',
        enabled: true,
        credentialPresent: true,
        canExecute: false,
      },
      providerCapability: {
        provider: 'mock',
        enabled: true,
        networkRequired: false,
        supportsRender: true,
        supportsStreaming: false,
        supportsSync: true,
        supportsMultiShot: false,
        requiresCredentials: false,
      },
      providerControlContract: {
        selectionMode: 'manual_only',
        autoExecution: false,
        executionOnSelect: false,
      },
      providerSafetyContract: {
        realProviderExecutionEnabled: false,
      },
      providerPayloadV2: {
        provider: 'mock',
        shotId: 'shot_scene_001_001',
      },
      handoffEnvelope: {
        requestId: 'handoff_mock_shot_scene_001_001',
        provider: 'mock',
        enabled: false,
      },
      handoffAudit: {
        requested: true,
        allowed: false,
        blockedReason: 'Execution permission denied',
        timestamp: null,
      },
    })
  })

  it('returns null provider control fields for invalid payload shapes', () => {
    const project = {
      project_id: 'p-provider-control-invalid',
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        provider_config_snapshot: {
          default_provider: null,
          enabled_providers: 'mock',
          quality_priority: 'cinematic_quality',
          real_providers_enabled: false,
        },
        provider_credential_state: {
          provider: 'mock',
          enabled: true,
          credential_present: true,
          credential_source: 'invalid_source',
          reason: 'bad',
        },
        provider_selection_state: {
          requested_provider: null,
          selected_provider: null,
          allowed: true,
          fallback_used: false,
          reason: 'bad',
        },
        provider_readiness_summary: {
          provider: 'mock',
          enabled: true,
          credential_present: true,
          can_execute: 'no',
          reason: 'bad',
        },
        provider_capability: {
          provider: 'mock',
          enabled: true,
        },
        provider_control_contract: {
          selection_mode: 'auto',
          auto_execution: false,
          execution_on_select: false,
          reason: 'bad',
        },
        provider_safety_contract: {
          real_provider_execution_enabled: null,
          reason: 'bad',
        },
        provider_payload_v2: {
          provider: null,
          shot_id: {},
          prompt: 'bad',
        },
        handoff_envelope: {
          request_id: null,
          provider: null,
          enabled: 'no',
        },
        handoff_audit: {
          requested: 'yes',
          allowed: 'no',
          blocked_reason: {},
          timestamp: 'now',
        },
      },
    } as unknown as StudioProject

    const extracted = extractExecutionSummaryInspection(project)
    expect(extracted).not.toBeNull()
    expect(extracted).not.toHaveProperty('providerConfigSnapshot')
    expect(extracted).not.toHaveProperty('providerCredentialState')
    expect(extracted).not.toHaveProperty('providerSelectionState')
    expect(extracted).not.toHaveProperty('providerReadinessSummary')
    expect(extracted).not.toHaveProperty('providerCapability')
    expect(extracted).not.toHaveProperty('providerControlContract')
    expect(extracted).not.toHaveProperty('providerSafetyContract')
    expect(extracted).not.toHaveProperty('providerPayloadV2')
    expect(extracted).not.toHaveProperty('handoffEnvelope')
    expect(extracted).not.toHaveProperty('handoffAudit')
  })

  it('parses take review fields when present', () => {
    const project = {
      project_id: 'p-take-review',
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        take_artifacts: [
          {
            iteration: 1,
            render_id: 'render_001',
            status: 'complete',
          },
        ],
        take_comparison_v2: {
          comparable: false,
          differences: [],
        },
        take_preference_contract: {
          auto_select: false,
          authority: 'manual_only',
        },
        output_review_matrix: [
          {
            take_id: 1,
            alignment: 'none',
            coverage: '3/3',
            valid_structure: true,
          },
        ],
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      takeArtifacts: [
        {
          iteration: 1,
          renderId: 'render_001',
          status: 'complete',
        },
      ],
      takeComparisonV2: {
        comparable: false,
        differences: [],
      },
      takePreferenceContract: {
        autoSelect: false,
        authority: 'manual_only',
      },
      outputReviewMatrix: [
        {
          takeId: 1,
          alignment: 'none',
          coverage: '3/3',
          validStructure: true,
        },
      ],
    })
  })

  it('suppresses malformed take review fields safely', () => {
    const project = {
      project_id: 'p-take-review-invalid',
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        take_artifacts: 'bad',
        take_comparison_v2: {
          comparable: 'no',
          differences: {},
        },
        take_preference_contract: {
          auto_select: 'no',
          authority: 'auto',
        },
        output_review_matrix: [
          {
            take_id: 'bad',
            alignment: '',
            coverage: null,
            valid_structure: 'yes',
          },
        ],
      },
    } as unknown as StudioProject

    const extracted = extractExecutionSummaryInspection(project)
    expect(extracted).not.toBeNull()
    expect(extracted).not.toHaveProperty('takeArtifacts')
    expect(extracted).not.toHaveProperty('takeComparisonV2')
    expect(extracted).not.toHaveProperty('takePreferenceContract')
    expect(extracted).toHaveProperty('outputReviewMatrix')
    expect(extracted?.outputReviewMatrix).toEqual([])
  })

  it('extracts bounded fields when summary is present', () => {
    const project = {
      project_id: 'p-present',
      interactive_modules: {
        execution_summary: {
          provider_name: 'generic',
          lifecycle_state: 'submitted',
          provider_status: 'rendering',
          has_output_artifacts: false,
          has_error: false,
          latest_updated_at: '2026-04-23T02:00:00Z',
          render_behavior: 'retry_heavy',
          ignored_blob: { raw: true },
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'generic',
      lifecycleState: 'submitted',
      productionSignal: null,
      sceneIntent: null,
      intentSignal: null,
      intentOutputSignal: null,
      intentOutputRelation: null,
      providerStatus: 'rendering',
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: '2026-04-23T02:00:00Z',
      renderBehavior: 'retry_heavy',
      interventionSuggestion: null,
      recurringPattern: null,
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts intervention suggestion when present', () => {
    const project = {
      project_id: 'p-suggest',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        intervention_suggestion: {
          level: 'advisory',
          message: 'Multiple retries detected. Consider provider review or reducing batch size.',
          source: 'render_behavior_rule_v1',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'aws',
      lifecycleState: 'in_progress',
      productionSignal: null,
      sceneIntent: null,
      intentSignal: null,
      intentOutputSignal: null,
      intentOutputRelation: null,
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: {
        level: 'advisory',
        message: 'Multiple retries detected. Consider provider review or reducing batch size.',
        source: 'render_behavior_rule_v1',
      },
      recurringPattern: null,
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts recurring pattern when present', () => {
    const project = {
      project_id: 'p-recurring',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'failed',
        recurring_pattern: {
          type: 'provider_failure_pattern',
          count: 3,
          provider_name: 'aws',
          message: 'Repeated provider failures detected across recent render events.',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'aws',
      lifecycleState: 'failed',
      productionSignal: null,
      sceneIntent: null,
      intentSignal: null,
      intentOutputSignal: null,
      intentOutputRelation: null,
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: null,
      recurringPattern: {
        type: 'provider_failure_pattern',
        count: 3,
        providerName: 'aws',
        message: 'Repeated provider failures detected across recent render events.',
      },
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts stuck recurring pattern when present', () => {
    const project = {
      project_id: 'p-stuck-recurring',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        recurring_pattern: {
          type: 'stuck_pattern',
          count: 3,
          message: 'Repeated stuck render states detected across recent queue entries.',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'simulated',
      lifecycleState: 'queued',
      productionSignal: null,
      sceneIntent: null,
      intentSignal: null,
      intentOutputSignal: null,
      intentOutputRelation: null,
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: null,
      recurringPattern: {
        type: 'stuck_pattern',
        count: 3,
        providerName: null,
        message: 'Repeated stuck render states detected across recent queue entries.',
      },
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts production signal when present', () => {
    const project = {
      project_id: 'p-signal',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        production_signal: {
          type: 'production_signal',
          message: 'Render in progress',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'aws',
      lifecycleState: 'in_progress',
      productionSignal: {
        type: 'production_signal',
        message: 'Render in progress',
      },
      sceneIntent: null,
      intentSignal: null,
      intentOutputSignal: null,
      intentOutputRelation: null,
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: null,
      recurringPattern: null,
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts scene intent when present', () => {
    const project = {
      project_id: 'p-intent',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        scene_intent: {
          type: 'intent_label',
          label: 'quiet emotional moment',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'aws',
      lifecycleState: 'in_progress',
      productionSignal: null,
      sceneIntent: {
        type: 'intent_label',
        label: 'quiet emotional moment',
      },
      intentSignal: null,
      intentOutputSignal: null,
      intentOutputRelation: null,
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: null,
      recurringPattern: null,
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts intent signal when present', () => {
    const project = {
      project_id: 'p-intent-signal',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        intent_signal: {
          type: 'intent_presence',
          message: 'Scene intent present',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'aws',
      lifecycleState: 'in_progress',
      productionSignal: null,
      sceneIntent: null,
      intentSignal: {
        type: 'intent_presence',
        message: 'Scene intent present',
      },
      intentOutputSignal: null,
      intentOutputRelation: null,
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: null,
      recurringPattern: null,
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts intent output signal when present', () => {
    const project = {
      project_id: 'p-intent-output-signal',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'complete',
        intent_output_signal: {
          type: 'intent_output_presence',
          message: 'Intent and output present',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'aws',
      lifecycleState: 'complete',
      productionSignal: null,
      sceneIntent: null,
      intentSignal: null,
      intentOutputSignal: {
        type: 'intent_output_presence',
        message: 'Intent and output present',
      },
      intentOutputRelation: null,
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: null,
      recurringPattern: null,
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts intent output relation when present', () => {
    const project = {
      project_id: 'p-intent-output-relation',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'complete',
        intent_output_relation: {
          type: 'intent_output_relation',
          state: 'ready_for_review',
          message: 'Intent and output ready for review',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'aws',
      lifecycleState: 'complete',
      productionSignal: null,
      sceneIntent: null,
      intentSignal: null,
      intentOutputSignal: null,
      intentOutputRelation: {
        type: 'intent_output_relation',
        state: 'ready_for_review',
        message: 'Intent and output ready for review',
      },
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: null,
      recurringPattern: null,
      memoryAdvisoryProjection: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('extracts memory visibility fields when present', () => {
    const project = {
      project_id: 'p-memory',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        memory_advisory_projection: {
          status: 'available',
          message: 'Memory candidates available for future review',
        },
        memory_snapshot_summary: {
          candidate_count: 2,
          record_count: 0,
          aggregate_count: 0,
          advisory_status: 'available',
          influence_mode: 'disabled',
        },
        memory_state_rollup: {
          status: 'available',
          candidate_count: 2,
          influence_mode: 'disabled',
          advisory_status: 'available',
        },
        memory_consistency: {
          is_consistent: true,
          has_required_fields: true,
          gate_disabled: true,
          authority_none: true,
        },
        memory_category_presence: {
          character_pairs: false,
          locations: true,
          time_of_day: true,
        },
        co_director_memory_visibility: {
          has_memory_candidates: true,
          has_memory_records: false,
          has_memory_aggregate: false,
          influence_mode: 'disabled',
          advisory_status: 'available',
        },
        co_director_memory_advisory: {
          status: 'informational',
          message: 'Memory candidates visible for review; influence remains disabled.',
        },
        co_director_memory_authority_boundary: {
          authority: 'none',
          memory_influence: 'disabled',
          reason: 'Read-only visibility only',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toEqual({
      providerName: 'aws',
      lifecycleState: 'in_progress',
      productionSignal: null,
      sceneIntent: null,
      intentSignal: null,
      intentOutputSignal: null,
      intentOutputRelation: null,
      providerStatus: null,
      hasOutputArtifacts: false,
      hasError: false,
      latestUpdatedAt: null,
      renderBehavior: null,
      interventionSuggestion: null,
      recurringPattern: null,
      memoryAdvisoryProjection: {
        status: 'available',
        message: 'Memory candidates available for future review',
      },
      memorySnapshotSummary: {
        candidateCount: 2,
        recordCount: 0,
        aggregateCount: 0,
        advisoryStatus: 'available',
        influenceMode: 'disabled',
      },
      memoryStateRollup: {
        status: 'available',
        candidateCount: 2,
        influenceMode: 'disabled',
        advisoryStatus: 'available',
      },
      memoryConsistency: {
        isConsistent: true,
        hasRequiredFields: true,
        gateDisabled: true,
        authorityNone: true,
      },
      memoryCategoryPresence: {
        characterPairs: false,
        locations: true,
        timeOfDay: true,
      },
      coDirectorMemoryVisibility: {
        hasMemoryCandidates: true,
        hasMemoryRecords: false,
        hasMemoryAggregate: false,
        influenceMode: 'disabled',
        advisoryStatus: 'available',
      },
      coDirectorMemoryAdvisory: {
        status: 'informational',
        message: 'Memory candidates visible for review; influence remains disabled.',
      },
      coDirectorMemoryAuthorityBoundary: {
        authority: 'none',
        memoryInfluence: 'disabled',
        reason: 'Read-only visibility only',
      },
    })
  })

  it('returns null memory fields when memory visibility fields are absent', () => {
    const project = {
      project_id: 'p-memory-absent',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      memoryAdvisoryProjection: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
    })
  })

  it('returns null for invalid memory snapshot and category presence shapes', () => {
    const project = {
      project_id: 'p-memory-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        memory_snapshot_summary: {
          candidate_count: 'not-a-number',
          record_count: 0,
          aggregate_count: 0,
          advisory_status: 'available',
          influence_mode: 'disabled',
        },
        memory_category_presence: {
          character_pairs: 'yes',
          locations: false,
          time_of_day: true,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
    })
  })

  it('parses memory_state_rollup and memory_consistency when present', () => {
    const project = {
      project_id: 'p-memory-rollup-consistency',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        memory_state_rollup: {
          status: 'available',
          candidate_count: 3,
          influence_mode: 'disabled',
          advisory_status: 'available',
        },
        memory_consistency: {
          is_consistent: true,
          has_required_fields: true,
          gate_disabled: true,
          authority_none: true,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      memoryStateRollup: {
        status: 'available',
        candidateCount: 3,
        influenceMode: 'disabled',
        advisoryStatus: 'available',
      },
      memoryConsistency: {
        isConsistent: true,
        hasRequiredFields: true,
        gateDisabled: true,
        authorityNone: true,
      },
    })
  })

  it('returns null for invalid or missing memory_state_rollup and memory_consistency', () => {
    const invalid = {
      project_id: 'p-memory-rollup-consistency-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        memory_state_rollup: {
          status: 'available',
          candidate_count: -1,
          influence_mode: 7,
          advisory_status: null,
        },
        memory_consistency: {
          is_consistent: 'maybe',
          has_required_fields: true,
          gate_disabled: true,
          authority_none: true,
        },
      },
    } as unknown as StudioProject

    const missing = {
      project_id: 'p-memory-rollup-consistency-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(invalid)).toMatchObject({
      memoryStateRollup: null,
      memoryConsistency: null,
    })
    expect(extractExecutionSummaryInspection(missing)).toMatchObject({
      memoryStateRollup: null,
      memoryConsistency: null,
    })
  })

  it('keeps inconsistent but well-shaped memory fields as parsed values (no coercion)', () => {
    const project = {
      project_id: 'p-memory-inconsistent',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        memory_advisory_projection: {
          status: 'available',
          message: 'Memory candidates available for future review',
        },
        memory_snapshot_summary: {
          candidate_count: 1,
          record_count: 0,
          aggregate_count: 0,
          advisory_status: 'available',
          influence_mode: 'enabled',
        },
        co_director_memory_visibility: {
          has_memory_candidates: true,
          has_memory_records: false,
          has_memory_aggregate: false,
          influence_mode: 'enabled',
          advisory_status: 'available',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      memoryAdvisoryProjection: {
        status: 'available',
        message: 'Memory candidates available for future review',
      },
      memorySnapshotSummary: {
        candidateCount: 1,
        recordCount: 0,
        aggregateCount: 0,
        advisoryStatus: 'available',
        influenceMode: 'enabled',
      },
      coDirectorMemoryVisibility: {
        hasMemoryCandidates: true,
        hasMemoryRecords: false,
        hasMemoryAggregate: false,
        influenceMode: 'enabled',
        advisoryStatus: 'available',
      },
    })
  })

  it('returns null memory fields for corrupted malformed payloads', () => {
    const project = {
      project_id: 'p-memory-corrupted',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        memory_advisory_projection: 'available',
        memory_snapshot_summary: {
          candidate_count: -1,
          record_count: 'bad',
          aggregate_count: null,
          advisory_status: '',
          influence_mode: 123,
        },
        memory_category_presence: {
          character_pairs: 'yes',
          locations: 'no',
          time_of_day: null,
        },
        co_director_memory_visibility: {
          has_memory_candidates: 'true',
          has_memory_records: false,
          has_memory_aggregate: false,
          influence_mode: 5,
          advisory_status: '',
        },
        co_director_memory_advisory: {
          status: null,
          message: 99,
        },
        co_director_memory_authority_boundary: {
          authority: false,
          memory_influence: {},
          reason: [],
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      memoryAdvisoryProjection: null,
      memorySnapshotSummary: null,
      memoryStateRollup: null,
      memoryConsistency: null,
      memoryCategoryPresence: null,
      coDirectorMemoryVisibility: null,
      coDirectorMemoryAdvisory: null,
      coDirectorMemoryAuthorityBoundary: null,
    })
  })

  it('ignores malformed contract stubs while keeping bounded extraction stable', () => {
    const project = {
      project_id: 'p-memory-contract-malformed',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        memory_state_rollup: {
          status: 'available',
          candidate_count: 1,
          influence_mode: 'disabled',
          advisory_status: 'available',
        },
        memory_consistency: {
          is_consistent: true,
          has_required_fields: true,
          gate_disabled: true,
          authority_none: true,
        },
        memory_output_influence_contract: {
          permitted: true,
          scope: 'all',
          reason: 7,
        },
        co_director_memory_contract: {
          mode: 'authoritative',
          authority: 'all',
          memory_influence: 'enabled',
          reason: null,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      providerName: 'aws',
      lifecycleState: 'in_progress',
      memoryStateRollup: {
        status: 'available',
        candidateCount: 1,
        influenceMode: 'disabled',
        advisoryStatus: 'available',
      },
      memoryConsistency: {
        isConsistent: true,
        hasRequiredFields: true,
        gateDisabled: true,
        authorityNone: true,
      },
    })
  })

  it('extracts visual reference fields when present', () => {
    const project = {
      project_id: 'p-visual-references',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        visual_references: [
          {
            id: 'ref_001',
            type: 'image',
            source: 'manual',
            label: 'rainy apartment reference',
            scene_id: 'scene_001',
          },
        ],
        visual_reference_indexes: {
          by_reference_id: {
            ref_001: {
              id: 'ref_001',
              type: 'image',
              source: 'manual',
              label: 'rainy apartment reference',
              scene_id: 'scene_001',
            },
          },
          by_scene_id: {
            scene_001: ['ref_001'],
          },
          by_type: {
            image: ['ref_001'],
          },
        },
        visual_reference_summary: {
          reference_count: 1,
          linked_scene_count: 1,
          type_count: 1,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      visualReferences: [
        {
          id: 'ref_001',
          type: 'image',
          source: 'manual',
          label: 'rainy apartment reference',
          sceneId: 'scene_001',
        },
      ],
      visualReferenceIndexes: {
        byReferenceId: {
          ref_001: {
            id: 'ref_001',
            type: 'image',
            source: 'manual',
            label: 'rainy apartment reference',
            sceneId: 'scene_001',
          },
        },
        bySceneId: {
          scene_001: ['ref_001'],
        },
        byType: {
          image: ['ref_001'],
        },
      },
      visualReferenceSummary: {
        referenceCount: 1,
        linkedSceneCount: 1,
        typeCount: 1,
      },
    })
  })

  it('extracts visual signal summary fields when present', () => {
    const project = {
      project_id: 'p-visual-signals',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        visual_pattern_summary: {
          dominant_types: ['image'],
          type_counts: {
            image: 2,
            video: 1,
          },
        },
        scene_visual_identity: {
          scene_001: ['image', 'video'],
          scene_002: ['image'],
        },
        visual_consistency: {
          consistent: true,
          variance_level: 'low',
        },
        visual_tension: {
          tension_scenes: ['scene_001'],
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      visualPatternSummary: {
        dominantTypes: ['image'],
        typeCounts: {
          image: 2,
          video: 1,
        },
      },
      sceneVisualIdentity: {
        scene_001: ['image', 'video'],
        scene_002: ['image'],
      },
      visualConsistency: {
        consistent: true,
        varianceLevel: 'low',
      },
      visualTension: {
        tensionScenes: ['scene_001'],
      },
    })
  })

  it('returns no visual signal summary fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-visual-signals-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-visual-signals-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        visual_pattern_summary: {
          dominant_types: ['image'],
          type_counts: {
            image: -1,
          },
        },
        scene_visual_identity: {
          scene_001: ['image', 9],
        },
        visual_consistency: {
          consistent: true,
          variance_level: 'medium',
        },
        visual_tension: {
          tension_scenes: ['scene_001', 5],
        },
      },
    } as unknown as StudioProject

    const missingResult = extractExecutionSummaryInspection(missing)
    const invalidResult = extractExecutionSummaryInspection(invalid)
    expect(missingResult).not.toHaveProperty('visualPatternSummary')
    expect(missingResult).not.toHaveProperty('sceneVisualIdentity')
    expect(missingResult).not.toHaveProperty('visualConsistency')
    expect(missingResult).not.toHaveProperty('visualTension')
    expect(invalidResult).not.toHaveProperty('visualPatternSummary')
    expect(invalidResult).not.toHaveProperty('sceneVisualIdentity')
    expect(invalidResult).not.toHaveProperty('visualConsistency')
    expect(invalidResult).not.toHaveProperty('visualTension')
  })

  it('extracts co-director visual feed when present', () => {
    const project = {
      project_id: 'p-co-director-visual-feed',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        co_director_visual_feed: {
          reference_summary: {
            reference_count: 1,
            linked_scene_count: 1,
            type_count: 1,
          },
          frame_snapshot: {
            frame_metadata: [
              {
                frame_id: 'frame_001',
                artifact_id: 'artifact_001',
                timestamp: 0,
              },
            ],
            frame_stats: {
              frame_count: 1,
              artifact_count: 1,
            },
          },
          linkage: {
            linked_scenes: 1,
            total_scenes: 3,
          },
          alignment: {
            state: 'partial',
            note: 'Visual references partially cover scenes',
          },
          mode: 'read_only',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      coDirectorVisualFeed: {
        referenceSummary: {
          referenceCount: 1,
          linkedSceneCount: 1,
          typeCount: 1,
        },
        frameSnapshot: {
          frameMetadata: [
            {
              frameId: 'frame_001',
              artifactId: 'artifact_001',
              timestamp: 0,
            },
          ],
          frameStats: {
            frameCount: 1,
            artifactCount: 1,
          },
        },
        linkage: {
          linkedScenes: 1,
          totalScenes: 3,
        },
        alignment: {
          state: 'partial',
          note: 'Visual references partially cover scenes',
        },
        mode: 'read_only',
      },
    })
  })

  it('returns no co-director visual feed for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-co-director-visual-feed-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-co-director-visual-feed-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        co_director_visual_feed: {
          reference_summary: {
            reference_count: 1,
            linked_scene_count: 1,
            type_count: 1,
          },
          frame_snapshot: {
            frame_metadata: [],
            frame_stats: {
              frame_count: 0,
              artifact_count: 0,
            },
          },
          linkage: {
            linked_scenes: 1,
            total_scenes: 3,
          },
          alignment: {
            state: 'partial',
            note: 'x',
          },
          mode: 'read_write',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('coDirectorVisualFeed')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('coDirectorVisualFeed')
  })

  it('returns no visual reference fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-visual-references-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-visual-references-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        visual_references: [{ id: 'ref_001', type: 'image', source: 'manual' }],
        visual_reference_indexes: {
          by_reference_id: {
            ref_001: {
              id: 'ref_001',
              type: 'image',
              source: 'manual',
              label: 'rainy apartment reference',
            },
          },
          by_scene_id: {
            scene_001: ['ref_001', 99],
          },
          by_type: {
            image: ['ref_001'],
          },
        },
        visual_reference_summary: {
          reference_count: -1,
          linked_scene_count: 0,
          type_count: 0,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('visualReferences')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('visualReferenceIndexes')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('visualReferenceSummary')

    expect(extractExecutionSummaryInspection(invalid)).toMatchObject({
      visualReferences: [],
    })
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('visualReferenceIndexes')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('visualReferenceSummary')
  })

  it('extracts frame analysis fields when present', () => {
    const project = {
      project_id: 'p-frame-analysis',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        frame_metadata: [
          {
            frame_id: 'frame_001',
            artifact_id: 'artifact_001',
            timestamp: 0,
          },
        ],
        frame_stats: {
          frame_count: 1,
          artifact_count: 1,
        },
        frame_analysis_snapshot: {
          frame_metadata: [
            {
              frame_id: 'frame_001',
              artifact_id: 'artifact_001',
              timestamp: 0,
            },
          ],
          frame_stats: {
            frame_count: 1,
            artifact_count: 1,
          },
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      frameMetadata: [
        {
          frameId: 'frame_001',
          artifactId: 'artifact_001',
          timestamp: 0,
        },
      ],
      frameStats: {
        frameCount: 1,
        artifactCount: 1,
      },
      frameAnalysisSnapshot: {
        frameMetadata: [
          {
            frameId: 'frame_001',
            artifactId: 'artifact_001',
            timestamp: 0,
          },
        ],
        frameStats: {
          frameCount: 1,
          artifactCount: 1,
        },
      },
    })
  })

  it('returns no frame analysis fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-frame-analysis-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-frame-analysis-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        frame_metadata: [{ frame_id: 'frame_001', artifact_id: 'artifact_001', timestamp: -1 }],
        frame_stats: {
          frame_count: -1,
          artifact_count: 0,
        },
        frame_analysis_snapshot: {
          frame_metadata: [{ frame_id: 'frame_001', artifact_id: 'artifact_001', timestamp: 'bad' }],
          frame_stats: {
            frame_count: 1,
            artifact_count: 1,
          },
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('frameMetadata')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('frameStats')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('frameAnalysisSnapshot')
    expect(extractExecutionSummaryInspection(invalid)).toMatchObject({
      frameMetadata: [],
      frameAnalysisSnapshot: {
        frameMetadata: [],
        frameStats: {
          frameCount: 1,
          artifactCount: 1,
        },
      },
    })
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('frameStats')
  })

  it('extracts scene-visual linkage fields when present', () => {
    const project = {
      project_id: 'p-scene-visual-linkage',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        scene_visual_links: {
          scene_001: ['ref_001', 'ref_002'],
        },
        link_completeness: {
          linked_scenes: 1,
          total_scenes: 3,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      sceneVisualLinks: {
        scene_001: ['ref_001', 'ref_002'],
      },
      linkCompleteness: {
        linkedScenes: 1,
        totalScenes: 3,
      },
    })
  })

  it('returns no linkage fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-scene-visual-linkage-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-scene-visual-linkage-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        scene_visual_links: {
          scene_001: ['ref_001', 9],
        },
        link_completeness: {
          linked_scenes: -1,
          total_scenes: 3,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('sceneVisualLinks')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('linkCompleteness')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('sceneVisualLinks')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('linkCompleteness')
  })

  it('extracts shot planning fields when present', () => {
    const project = {
      project_id: 'p-shot-planning',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        shot_candidates: [
          {
            scene_id: 'scene_001',
            shot_id: 'shot_scene_001_001',
            source_refs: ['ref_001'],
          },
        ],
        shot_coverage: {
          scene_001: {
            candidate_count: 1,
          },
        },
        shot_plan_bundle: {
          shot_candidates: [
            {
              scene_id: 'scene_001',
              shot_id: 'shot_scene_001_001',
              source_refs: ['ref_001'],
            },
          ],
          shot_coverage: {
            scene_001: {
              candidate_count: 1,
            },
          },
          influence_mode: 'disabled',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      shotCandidates: [
        {
          sceneId: 'scene_001',
          shotId: 'shot_scene_001_001',
          sourceRefs: ['ref_001'],
        },
      ],
      shotCoverage: {
        scene_001: {
          candidateCount: 1,
        },
      },
      shotPlanBundle: {
        shotCandidates: [
          {
            sceneId: 'scene_001',
            shotId: 'shot_scene_001_001',
            sourceRefs: ['ref_001'],
          },
        ],
        shotCoverage: {
          scene_001: {
            candidateCount: 1,
          },
        },
        influenceMode: 'disabled',
      },
    })
  })

  it('returns no shot planning fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-shot-planning-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-shot-planning-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        shot_candidates: [
          {
            scene_id: 'scene_001',
            shot_id: 'shot_scene_001_001',
            source_refs: [9],
          },
        ],
        shot_coverage: {
          scene_001: {
            candidate_count: -1,
          },
        },
        shot_plan_bundle: {
          shot_candidates: [],
          shot_coverage: {},
          influence_mode: '',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('shotCandidates')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('shotCoverage')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('shotPlanBundle')
    expect(extractExecutionSummaryInspection(invalid)).toMatchObject({
      shotCandidates: [],
    })
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('shotCoverage')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('shotPlanBundle')
  })

  it('extracts shot thinking fields when present', () => {
    const project = {
      project_id: 'p-shot-thinking',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        shot_intent: {
          shot_scene_001_001: 'dialogue_focus',
          shot_scene_002_001: 'establishing',
        },
        shot_variety: {
          diversity: 'low',
        },
        scene_coverage: {
          scene_001: 'covered',
          scene_002: 'partial',
        },
        shot_planning_summary: {
          covered_scenes: 1,
          total_scenes: 2,
          variety: 'low',
        },
        shot_advisory_note: {
          note: 'Shot variety is limited',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      shotIntent: {
        shot_scene_001_001: 'dialogue_focus',
        shot_scene_002_001: 'establishing',
      },
      shotVariety: {
        diversity: 'low',
      },
      sceneCoverage: {
        scene_001: 'covered',
        scene_002: 'partial',
      },
      shotPlanningSummary: {
        coveredScenes: 1,
        totalScenes: 2,
        variety: 'low',
      },
      shotAdvisoryNote: {
        note: 'Shot variety is limited',
      },
    })
  })

  it('returns no shot thinking fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-shot-thinking-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-shot-thinking-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        shot_intent: {
          shot_scene_001_001: 'unknown',
        },
        shot_variety: {
          diversity: 'unsupported',
        },
        scene_coverage: {
          scene_001: 'invalid',
        },
        shot_planning_summary: {
          covered_scenes: -1,
          total_scenes: 2,
          variety: 'low',
        },
        shot_advisory_note: {
          note: 123,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('shotIntent')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('shotVariety')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('sceneCoverage')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('shotPlanningSummary')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('shotAdvisoryNote')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('shotIntent')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('shotVariety')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('sceneCoverage')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('shotPlanningSummary')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('shotAdvisoryNote')
  })

  it('extracts co-director observation fields when present', () => {
    const project = {
      project_id: 'p-co-director-observations',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        co_director_visual_observation: {
          note: 'Visual style is mostly consistent with minor variation',
        },
        co_director_shot_observation: {
          note: 'Shot variety is somewhat limited',
        },
        co_director_observation_summary: {
          notes: [
            'Visual style is mostly consistent with minor variation',
            'Shot variety is somewhat limited',
          ],
        },
        co_director_observation_contract: {
          mode: 'read_only',
          authority: 'none',
          influence: 'disabled',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      coDirectorVisualObservation: {
        note: 'Visual style is mostly consistent with minor variation',
      },
      coDirectorShotObservation: {
        note: 'Shot variety is somewhat limited',
      },
      coDirectorObservationSummary: {
        notes: [
          'Visual style is mostly consistent with minor variation',
          'Shot variety is somewhat limited',
        ],
      },
      coDirectorObservationContract: {
        mode: 'read_only',
        authority: 'none',
        influence: 'disabled',
      },
    })
  })

  it('returns no co-director observation fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-co-director-observations-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-co-director-observations-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        co_director_visual_observation: {
          note: 123,
        },
        co_director_shot_observation: {
          note: null,
        },
        co_director_observation_summary: {
          notes: [false],
        },
        co_director_observation_contract: {
          mode: 'active',
          authority: 'partial',
          influence: 'enabled',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('coDirectorVisualObservation')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('coDirectorShotObservation')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('coDirectorObservationSummary')
    expect(extractExecutionSummaryInspection(missing)).not.toHaveProperty('coDirectorObservationContract')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('coDirectorVisualObservation')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('coDirectorShotObservation')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('coDirectorObservationSummary')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('coDirectorObservationContract')
  })

  it('extracts studio safety boundary fields when present', () => {
    const project = {
      project_id: 'p-studio-safety-fields',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        output_influence_guard_v2: {
          output_influence: false,
          reason: 'No system component is permitted to influence output',
        },
        visual_decision_boundary: {
          visual_decision_authority: 'none',
          reason: 'Visual decisions are not enabled',
        },
        shot_execution_lock: {
          shot_execution_enabled: false,
          reason: 'Shot execution is disabled',
        },
        boundary_audit: {
          memory_safe: true,
          visual_safe: true,
          shot_safe: true,
          render_safe: true,
          co_director_safe: true,
          overall_safe: true,
        },
        studio_safety_state: {
          studio_state: 'safe_for_control_phase',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      outputInfluenceGuardV2: {
        outputInfluence: false,
        reason: 'No system component is permitted to influence output',
      },
      visualDecisionBoundary: {
        visualDecisionAuthority: 'none',
        reason: 'Visual decisions are not enabled',
      },
      shotExecutionLock: {
        shotExecutionEnabled: false,
        reason: 'Shot execution is disabled',
      },
      boundaryAudit: {
        memorySafe: true,
        visualSafe: true,
        shotSafe: true,
        renderSafe: true,
        coDirectorSafe: true,
        overallSafe: true,
      },
      studioSafetyState: {
        studioState: 'safe_for_control_phase',
      },
    })
  })

  it('returns no studio safety boundary fields for invalid payloads', () => {
    const invalid = {
      project_id: 'p-studio-safety-fields-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        output_influence_guard_v2: {
          output_influence: 'false',
          reason: '',
        },
        visual_decision_boundary: {
          visual_decision_authority: '',
          reason: '',
        },
        shot_execution_lock: {
          shot_execution_enabled: 'no',
          reason: 9,
        },
        boundary_audit: {
          memory_safe: 'yes',
          visual_safe: true,
          shot_safe: true,
          render_safe: true,
          co_director_safe: true,
          overall_safe: true,
        },
        studio_safety_state: {
          studio_state: 'unsafe',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('outputInfluenceGuardV2')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('visualDecisionBoundary')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('shotExecutionLock')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('boundaryAudit')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('studioSafetyState')
  })

  it('extracts prompt influence fields when present', () => {
    const project = {
      project_id: 'p-prompt-influence-fields',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        prompt_influence_gate_v1: {
          prompt_influence_enabled: true,
          scope: 'advisory_only',
          reason: 'Prompt influence enabled in advisory mode',
        },
        visual_prompt_tokens: ['image', 'video'],
        shot_prompt_tokens: ['wide establishing shot', 'tight dialogue framing'],
        prompt_envelope: {
          base_intent: 'Opening scene mood',
          visual_tokens: ['image', 'video'],
          shot_tokens: ['wide establishing shot'],
        },
        prompt_safety_contract: {
          prompt_override: false,
          structure_locked: true,
          token_injection_only: true,
          reason: 'Prompt structure is protected',
        },
        render_activation_gate_v1: {
          render_enabled: true,
          mode: 'single_shot',
          reason: 'Render activation allowed in controlled single-shot mode',
        },
        render_request: {
          shot_id: 'shot_scene_001_001',
          scene_id: 'scene_001',
          prompt: {
            base_intent: 'Opening scene mood',
            visual_tokens: ['image', 'video'],
            shot_tokens: ['wide establishing shot'],
          },
        },
        render_output: {
          render_id: 'render_stub_shot_scene_001_001',
          shot_id: 'shot_scene_001_001',
          status: 'pending',
          prompt_snapshot: {
            base_intent: 'Opening scene mood',
            visual_tokens: ['image', 'video'],
            shot_tokens: ['wide establishing shot'],
          },
        },
        output_review: {
          render_id: 'render_stub_shot_scene_001_001',
          alignment: 'partial',
          coverage: '1/2',
          status: 'pending',
        },
        output_evaluation: {
          has_output: true,
          valid_structure: true,
          render_id_present: true,
          status: 'valid',
        },
        retry_gate: {
          retry_allowed: false,
          reason: 'Valid output achieved',
        },
        execution_snapshot: {
          iteration: 1,
          max_iterations: 3,
          status: 'complete',
          render_attempted: true,
          retry_allowed: false,
          finalized: true,
        },
        iteration_record: {
          iteration: 1,
          status: 'complete',
          render_id: 'render_stub_shot_scene_001_001',
          coverage: '1/2',
          alignment: 'partial',
        },
        take_history: {
          takes: [
            {
              iteration: 1,
              status: 'complete',
              render_id: 'render_stub_shot_scene_001_001',
              coverage: '1/2',
              alignment: 'partial',
            },
          ],
        },
        retry_snapshot: {
          allowed: false,
          iteration: 1,
          status: 'complete',
        },
        take_comparison: {
          best_take: null,
          comparison_ready: false,
        },
        take_advisory_note: {
          note: 'Take is usable',
        },
        loop_readiness: {
          ready: false,
          reason: 'Retry not allowed',
        },
        next_take_preview: {
          next_iteration: 2,
          will_retry: false,
        },
        loop_constraint: {
          max_iterations: 3,
          remaining: 2,
        },
        loop_advisory: {
          note: '',
        },
        loop_contract: {
          auto_loop: false,
          execution_mode: 'manual_only',
          reason: 'Loop execution is controlled',
        },
        loop_execution_plan: {
          execute: false,
          next_iteration: 2,
          reason: 'Retry not allowed',
        },
        simulated_iteration: {
          iteration: 1,
          status: 'complete',
        },
        simulated_output: {
          render_id: 'render_stub_shot_scene_001_001',
          status: 'pending',
        },
        loop_result_snapshot: {
          iteration: 1,
          output_status: 'pending',
        },
        loop_execution_contract: {
          mode: 'safe_simulation',
          real_execution: false,
          reason: 'Loop execution is simulated only',
        },
        execution_permission: {
          allowed: false,
          mode: 'blocked',
          reason: 'Retry not allowed',
        },
        execution_request: {
          enabled: false,
          shot_id: null,
          prompt: null,
        },
        execution_status: {
          state: 'blocked',
          reason: 'Execution not enabled',
        },
        execution_result: {
          executed: false,
          render_id: null,
          status: 'not_executed',
        },
        provider_payload: {
          shot_id: null,
          prompt: null,
        },
        execution_result_v2: {
          executed: false,
          render_id: null,
          status: 'not_executed',
        },
        output_sync: {
          synced: false,
          render_id: null,
        },
        execution_monitor: {
          state: 'blocked',
          result: 'not_executed',
        },
        execution_contract: {
          mode: 'single_shot_only',
          auto_execution: false,
          looping: false,
          reason: 'Execution is manually controlled',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      promptInfluenceGateV1: {
        promptInfluenceEnabled: true,
        scope: 'advisory_only',
        reason: 'Prompt influence enabled in advisory mode',
      },
      visualPromptTokens: ['image', 'video'],
      shotPromptTokens: ['wide establishing shot', 'tight dialogue framing'],
      promptEnvelope: {
        baseIntent: 'Opening scene mood',
        visualTokens: ['image', 'video'],
        shotTokens: ['wide establishing shot'],
      },
      promptSafetyContract: {
        promptOverride: false,
        structureLocked: true,
        tokenInjectionOnly: true,
        reason: 'Prompt structure is protected',
      },
      renderActivationGateV1: {
        renderEnabled: true,
        mode: 'single_shot',
        reason: 'Render activation allowed in controlled single-shot mode',
      },
      renderRequest: {
        shotId: 'shot_scene_001_001',
        sceneId: 'scene_001',
        prompt: {
          baseIntent: 'Opening scene mood',
          visualTokens: ['image', 'video'],
          shotTokens: ['wide establishing shot'],
        },
      },
      renderOutput: {
        renderId: 'render_stub_shot_scene_001_001',
        shotId: 'shot_scene_001_001',
        status: 'pending',
        promptSnapshot: {
          baseIntent: 'Opening scene mood',
          visualTokens: ['image', 'video'],
          shotTokens: ['wide establishing shot'],
        },
      },
      outputReview: {
        renderId: 'render_stub_shot_scene_001_001',
        alignment: 'partial',
        coverage: '1/2',
        status: 'pending',
      },
      outputEvaluation: {
        hasOutput: true,
        validStructure: true,
        renderIdPresent: true,
        status: 'valid',
      },
      retryGate: {
        retryAllowed: false,
        reason: 'Valid output achieved',
      },
      executionSnapshot: {
        iteration: 1,
        maxIterations: 3,
        status: 'complete',
        renderAttempted: true,
        retryAllowed: false,
        finalized: true,
      },
      iterationRecord: {
        iteration: 1,
        status: 'complete',
        renderId: 'render_stub_shot_scene_001_001',
        coverage: '1/2',
        alignment: 'partial',
      },
      takeHistory: {
        takes: [
          {
            iteration: 1,
            status: 'complete',
            renderId: 'render_stub_shot_scene_001_001',
            coverage: '1/2',
            alignment: 'partial',
          },
        ],
      },
      retrySnapshot: {
        allowed: false,
        iteration: 1,
        status: 'complete',
      },
      takeComparison: {
        bestTake: null,
        comparisonReady: false,
      },
      takeAdvisoryNote: {
        note: 'Take is usable',
      },
      loopReadiness: {
        ready: false,
        reason: 'Retry not allowed',
      },
      nextTakePreview: {
        nextIteration: 2,
        willRetry: false,
      },
      loopConstraint: {
        maxIterations: 3,
        remaining: 2,
      },
      loopAdvisory: {
        note: '',
      },
      loopContract: {
        autoLoop: false,
        executionMode: 'manual_only',
        reason: 'Loop execution is controlled',
      },
      loopExecutionPlan: {
        execute: false,
        nextIteration: 2,
        reason: 'Retry not allowed',
      },
      simulatedIteration: {
        iteration: 1,
        status: 'complete',
      },
      simulatedOutput: {
        renderId: 'render_stub_shot_scene_001_001',
        status: 'pending',
      },
      loopResultSnapshot: {
        iteration: 1,
        outputStatus: 'pending',
      },
      loopExecutionContract: {
        mode: 'safe_simulation',
        realExecution: false,
        reason: 'Loop execution is simulated only',
      },
      executionPermission: {
        allowed: false,
        mode: 'blocked',
        reason: 'Retry not allowed',
      },
      executionRequest: {
        enabled: false,
        shotId: null,
        prompt: null,
      },
      executionStatus: {
        state: 'blocked',
        reason: 'Execution not enabled',
      },
      executionResult: {
        executed: false,
        renderId: null,
        status: 'not_executed',
      },
      providerPayload: {
        shotId: null,
        prompt: null,
      },
      executionResultV2: {
        executed: false,
        renderId: null,
        status: 'not_executed',
      },
      outputSync: {
        synced: false,
        renderId: null,
      },
      executionMonitor: {
        state: 'blocked',
        result: 'not_executed',
      },
      executionContract: {
        mode: 'single_shot_only',
        autoExecution: false,
        looping: false,
        reason: 'Execution is manually controlled',
      },
    })
  })

  it('returns no prompt influence fields for invalid payloads', () => {
    const invalid = {
      project_id: 'p-prompt-influence-fields-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        prompt_influence_gate_v1: {
          prompt_influence_enabled: 'true',
          scope: 'full',
          reason: '',
        },
        visual_prompt_tokens: [1, 2],
        shot_prompt_tokens: [false],
        prompt_envelope: {
          base_intent: 9,
          visual_tokens: ['ok'],
          shot_tokens: ['ok'],
        },
        prompt_safety_contract: {
          prompt_override: 'false',
          structure_locked: true,
          token_injection_only: true,
          reason: '',
        },
        render_activation_gate_v1: {
          render_enabled: 'true',
          mode: 'multi_shot',
          reason: '',
        },
        render_request: {
          shot_id: 5,
          scene_id: 'scene_001',
          prompt: {
            base_intent: 'x',
            visual_tokens: ['a'],
            shot_tokens: ['b'],
          },
        },
        render_output: {
          render_id: 'render_stub_a',
          shot_id: 'shot_scene_001_001',
          status: 'done',
          prompt_snapshot: {
            base_intent: 'x',
            visual_tokens: ['a'],
            shot_tokens: ['b'],
          },
        },
        output_review: {
          render_id: 'render_stub_a',
          alignment: 8,
          coverage: '',
          status: 'pending',
        },
        output_evaluation: {
          has_output: 'true',
          valid_structure: true,
          render_id_present: true,
          status: 'unknown',
        },
        retry_gate: {
          retry_allowed: 'false',
          reason: '',
        },
        execution_snapshot: {
          iteration: '1',
          max_iterations: 3,
          status: 'running',
          render_attempted: true,
          retry_allowed: false,
          finalized: false,
        },
        iteration_record: {
          iteration: -1,
          status: '',
          render_id: 9,
          coverage: 1,
          alignment: null,
        },
        take_history: {
          takes: [
            {
              iteration: 'x',
              status: 'complete',
              render_id: 'render_stub',
              coverage: '1/1',
              alignment: 'none',
            },
          ],
        },
        retry_snapshot: {
          allowed: 'false',
          iteration: 1,
          status: '',
        },
        take_comparison: {
          best_take: 'take_1',
          comparison_ready: 'false',
        },
        take_advisory_note: {
          note: null,
        },
        loop_readiness: {
          ready: 'false',
          reason: '',
        },
        next_take_preview: {
          next_iteration: 'x',
          will_retry: 'false',
        },
        loop_constraint: {
          max_iterations: '3',
          remaining: -1,
        },
        loop_advisory: {
          note: null,
        },
        loop_contract: {
          auto_loop: 'false',
          execution_mode: 'auto',
          reason: '',
        },
        loop_execution_plan: {
          execute: 'false',
          next_iteration: -1,
          reason: '',
        },
        simulated_iteration: {
          iteration: 'one',
          status: '',
        },
        simulated_output: {
          render_id: 9,
          status: 'done',
        },
        loop_result_snapshot: {
          iteration: '1',
          output_status: 'done',
        },
        loop_execution_contract: {
          mode: 'unsafe',
          real_execution: 'false',
          reason: '',
        },
        execution_permission: {
          allowed: 'false',
          mode: 'manual',
          reason: '',
        },
        execution_request: {
          enabled: 'false',
          shot_id: 'shot_scene_001_001',
          prompt: {},
        },
        execution_status: {
          state: 'running',
          reason: '',
        },
        execution_result: {
          executed: 'false',
          render_id: 'render_1',
          status: 'done',
        },
        provider_payload: {
          shot_id: 5,
          prompt: {},
        },
        execution_result_v2: {
          executed: 'false',
          render_id: 'render_1',
          status: 'done',
        },
        output_sync: {
          synced: 'maybe',
          render_id: 5,
        },
        execution_monitor: {
          state: '',
          result: null,
        },
        execution_contract: {
          mode: 'auto',
          auto_execution: 'false',
          looping: 'false',
          reason: '',
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('promptInfluenceGateV1')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('visualPromptTokens')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('shotPromptTokens')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('promptEnvelope')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('promptSafetyContract')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('renderActivationGateV1')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('renderRequest')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('renderOutput')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('outputReview')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('outputEvaluation')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('retryGate')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('executionSnapshot')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('iterationRecord')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('takeHistory')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('retrySnapshot')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('takeComparison')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('takeAdvisoryNote')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('loopReadiness')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('nextTakePreview')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('loopConstraint')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('loopAdvisory')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('loopContract')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('loopExecutionPlan')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('simulatedIteration')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('simulatedOutput')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('loopResultSnapshot')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('loopExecutionContract')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('executionPermission')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('executionRequest')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('executionStatus')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('executionResult')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('providerPayload')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('executionResultV2')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('outputSync')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('executionMonitor')
    expect(extractExecutionSummaryInspection(invalid)).not.toHaveProperty('executionContract')
  })

  it('extracts sequence fields when present', () => {
    const project = {
      project_id: 'p-sequence',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        scene_sequence: [
          { scene_id: 'scene_001', shots: ['shot_001_a', 'shot_001_b'] },
          { scene_id: 'scene_002', shots: ['shot_002_a'] },
        ],
        scene_assembly: {
          scene_count: 2,
          assembled: false,
          shots_available: 3,
        },
        sequence_status: {
          scenes: 2,
          shots: 3,
          assembled: false,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      sceneSequence: [
        { sceneId: 'scene_001', shots: ['shot_001_a', 'shot_001_b'] },
        { sceneId: 'scene_002', shots: ['shot_002_a'] },
      ],
      sceneAssembly: {
        sceneCount: 2,
        assembled: false,
        shotsAvailable: 3,
      },
      sequenceStatus: {
        scenes: 2,
        shots: 3,
        assembled: false,
      },
    })
  })

  it('extracts sequenceStatus with assembled true when render output exists', () => {
    const project = {
      project_id: 'p-sequence-assembled',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'complete',
        scene_sequence: [
          { scene_id: 'scene_001', shots: ['shot_001_a'] },
        ],
        scene_assembly: {
          scene_count: 1,
          assembled: true,
          shots_available: 1,
        },
        sequence_status: {
          scenes: 1,
          shots: 1,
          assembled: true,
        },
      },
    } as unknown as StudioProject

    expect(extractExecutionSummaryInspection(project)).toMatchObject({
      sequenceStatus: {
        scenes: 1,
        shots: 1,
        assembled: true,
      },
    })
  })

  it('returns no sequence fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-sequence-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-sequence-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        scene_sequence: [{ scene_id: 123, shots: 'bad' }],
        scene_assembly: {
          scene_count: -1,
          assembled: 'yes',
          shots_available: null,
        },
        sequence_status: {
          scenes: 'two',
          shots: 3,
          assembled: 1,
        },
      },
    } as unknown as StudioProject

    const missingResult = extractExecutionSummaryInspection(missing)
    const invalidResult = extractExecutionSummaryInspection(invalid)

    expect(missingResult).not.toHaveProperty('sceneSequence')
    expect(missingResult).not.toHaveProperty('sceneAssembly')
    expect(missingResult).not.toHaveProperty('sequenceStatus')
    expect(invalidResult).not.toHaveProperty('sceneSequence')
    expect(invalidResult).not.toHaveProperty('sceneAssembly')
    expect(invalidResult).not.toHaveProperty('sequenceStatus')
  })

  it('handles partial sequence fields safely', () => {
    const partial = {
      project_id: 'p-sequence-partial',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        sequence_status: {
          scenes: 2,
          shots: 3,
          assembled: false,
        },
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(partial)
    expect(result).not.toHaveProperty('sceneSequence')
    expect(result).not.toHaveProperty('sceneAssembly')
    expect(result).toMatchObject({
      sequenceStatus: {
        scenes: 2,
        shots: 3,
        assembled: false,
      },
    })
  })
  it('extracts sceneContinuityCheck when present', () => {
    const withContinuityCheck = {
      project_id: 'p-continuity-check',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        scene_continuity_check: {
          visual_consistency: 'high',
          shot_variety: 'balanced',
          assembled: true,
          status: 'ready',
        },
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(withContinuityCheck)
    expect(result).not.toBeNull()
    if (result) {
      expect(result.sceneContinuityCheck).toMatchObject({
        visualConsistency: 'high',
        shotVariety: 'balanced',
        assembled: true,
        status: 'ready',
      })
    }
  })
  it('extracts scenePlaybackStatus when present', () => {
    const withPlaybackStatus = {
      project_id: 'p-playback-status',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        scene_playback_status: {
          playback_ready: true,
          scene_count: 5,
          shots_available: 12,
          status: 'ready',
        },
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(withPlaybackStatus)
    expect(result).not.toBeNull()
    if (result) {
      expect(result.scenePlaybackStatus).toMatchObject({
        playbackReady: true,
        sceneCount: 5,
        shotsAvailable: 12,
        status: 'ready',
      })
    }
  })
  it('returns no continuity/playback fields for missing or invalid payloads', () => {
    const missing = {
      project_id: 'p-missing',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
      },
    } as unknown as StudioProject

    const invalid = {
      project_id: 'p-invalid',
      execution_summary: {
        provider_name: 'aws',
        lifecycle_state: 'in_progress',
        scene_continuity_check: 'not-an-object',
        scene_playback_status: null,
      },
    } as unknown as StudioProject

    const missingResult = extractExecutionSummaryInspection(missing)
    const invalidResult = extractExecutionSummaryInspection(invalid)
    expect(missingResult).not.toHaveProperty('sceneContinuityCheck')
    expect(missingResult).not.toHaveProperty('scenePlaybackStatus')
    expect(invalidResult).not.toHaveProperty('sceneContinuityCheck')
    expect(invalidResult).not.toHaveProperty('scenePlaybackStatus')
  })
})

describe('Previs field extraction', () => {
  it('extracts valid previs scene board entries', () => {
    const project = {
      project_id: 'p-previs-valid',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_scene_board: [
          { scene_id: 'scene_001', shot_count: 3, linked_refs: ['ref_1', 'ref_2'] },
          { scene_id: 'scene_002', shot_count: 5, linked_refs: ['ref_3'] },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    expect(result).toHaveProperty('previsSceneBoard')
    expect(result!.previsSceneBoard).toHaveLength(2)
    expect(result!.previsSceneBoard?.[0].sceneId).toBe('scene_001')
    expect(result!.previsSceneBoard?.[0].shotCount).toBe(3)
    expect(result!.previsSceneBoard?.[0].linkedRefs).toEqual(['ref_1', 'ref_2'])
  })

  it('extracts valid previs beat shot map', () => {
    const project = {
      project_id: 'p-previs-beat',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_beat_shot_map: [
          { beat_id: 'beat_001', scene_id: 'scene_001', shots: ['shot_1', 'shot_2'] },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    expect(result).toHaveProperty('previsBeatShotMap')
    expect(result!.previsBeatShotMap).toHaveLength(1)
    expect(result!.previsBeatShotMap?.[0].beatId).toBe('beat_001')
    expect(result!.previsBeatShotMap?.[0].sceneId).toBe('scene_001')
    expect(result!.previsBeatShotMap?.[0].shots).toEqual(['shot_1', 'shot_2'])
  })

  it('extracts valid previs asset map', () => {
    const project = {
      project_id: 'p-previs-asset',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_asset_map: [
          { asset_id: 'asset_001', scenes: ['scene_001', 'scene_002'] },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    expect(result).toHaveProperty('previsAssetMap')
    expect(result!.previsAssetMap).toHaveLength(1)
    expect(result!.previsAssetMap?.[0].assetId).toBe('asset_001')
    expect(result!.previsAssetMap?.[0].scenes).toEqual(['scene_001', 'scene_002'])
  })

  it('extracts valid previs contract with strict defaults', () => {
    const project = {
      project_id: 'p-previs-contract',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        // asPrevisContract only accepts { mode: 'read_only', authority: 'none', execution_enabled: boolean }
        previs_contract: {
          mode: 'read_only',
          authority: 'none',
          execution_enabled: false,
        },
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result).toHaveProperty('previsContract')
    expect(result.previsContract?.mode).toBe('read_only')
    expect(result.previsContract?.authority).toBe('none')
  })

  it('extracts valid previs continuity map', () => {
    const project = {
      project_id: 'p-previs-continuity',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_continuity_map: [
          { scene_id: 'scene_001', checks: ['check_1', 'check_2'] },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result).toHaveProperty('previsContinuityMap')
    expect(result.previsContinuityMap).toHaveLength(1)
    expect(result.previsContinuityMap?.[0].sceneId).toBe('scene_001')
    expect(result.previsContinuityMap?.[0].checks).toEqual(['check_1', 'check_2'])
  })

  it('suppresses malformed previs scene board entries', () => {
    const project = {
      project_id: 'p-previs-bad',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_scene_board: [
          null,
          'not-an-object',
          { scene_id: 'scene_001' },
          { scene_id: 123, shot_count: 2, linked_refs: [] },
          { shot_count: -1, linked_refs: [] },
          {},
          { scene_id: 'scene_002', shot_count: 3, linked_refs: 'bad' },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result).toHaveProperty('previsSceneBoard')
    expect(result.previsSceneBoard).toHaveLength(0)
  })

  it('suppresses malformed previs beat shot map entries', () => {
    const project = {
      project_id: 'p-previs-beat-bad',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_beat_shot_map: [
          null,
          'string-not-object',
          { beat_id: 'beat_001' },
          { scene_id: 'scene_001' },
          { beat_id: 123, scene_id: 'scene_001', shots: ['shot_1'] },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result).toHaveProperty('previsBeatShotMap')
    expect(result.previsBeatShotMap).toHaveLength(0)
  })

  it('suppresses malformed previs asset map entries', () => {
    const project = {
      project_id: 'p-previs-asset-bad',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_asset_map: [
          null,
          'string',
          { asset_id: 'asset_001' },
          { scenes: ['scene_001'] },
          { asset_id: 99, scenes: ['scene_002'] },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result).toHaveProperty('previsAssetMap')
    expect(result.previsAssetMap).toHaveLength(0)
  })

  it('suppresses malformed previs contract', () => {
    const project = {
      project_id: 'p-previs-contract-bad',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_contract: {
          mode: 'strict',
          authority: 123,
          execution_enabled: 'yes',
        },
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result).not.toHaveProperty('previsContract')
  })

  it('suppresses malformed previs continuity map entries', () => {
    const project = {
      project_id: 'p-previs-continuity-bad',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_continuity_map: [
          null,
          'string',
          { scene_id: 'scene_001' },
          { checks: ['check_1'] },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result).toHaveProperty('previsContinuityMap')
    expect(result.previsContinuityMap).toHaveLength(0)
  })

  it('returns null fields when previs data is absent', () => {
    const project = {
      project_id: 'p-previs-absent',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result).not.toHaveProperty('previsSceneBoard')
    expect(result).not.toHaveProperty('previsBeatShotMap')
    expect(result).not.toHaveProperty('previsAssetMap')
    expect(result).not.toHaveProperty('previsContract')
    expect(result).not.toHaveProperty('previsContinuityMap')
  })

  it('keeps extraction stable with malformed partial payloads across protected sections', () => {
    const project = {
      project_id: 'p-phase199-malformed-partial',
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        provider_selection_state: {
          requested_provider: null,
          selected_provider: 'mock',
          allowed: true,
          fallback_used: false,
          reason: 'Default provider selected',
        },
        handoff_audit: {
          requested: true,
          allowed: false,
          blocked_reason: 'Execution permission denied',
          timestamp: null,
        },
        take_comparison_v2: {
          comparable: false,
          differences: [],
        },
        take_preference_contract: {
          auto_select: false,
          authority: 'manual_only',
        },
        output_review_matrix: [
          { take_id: 'bad', alignment: '', coverage: null, valid_structure: 'bad' },
        ],
        previs_scene_board: [
          { scene_id: 1, shot_count: -1, linked_refs: 'bad' },
        ],
      },
    } as unknown as StudioProject

    const result = extractExecutionSummaryInspection(project)
    expect(result).not.toBeNull()
    if (!result) throw new Error('Expected extraction result')
    expect(result.providerName).toBe('mock')
    expect(result.lifecycleState).toBe('ready')
    expect(result.providerSelectionState?.selectedProvider).toBe('mock')
    expect(result.handoffAudit?.allowed).toBe(false)
    expect(result.takeComparisonV2?.comparable).toBe(false)
    expect(result.takePreferenceContract?.authority).toBe('manual_only')
    expect(result.outputReviewMatrix).toEqual([])
    expect(result.previsSceneBoard).toEqual([])
  })
})

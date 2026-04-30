import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { extractExecutionSummaryInspection, resolveRenderSource } from '../lib/executionSummaryInspection'
import ExecutionSummaryInspectionPanel, { safeImageSrc, safeReadFile } from './ExecutionSummaryInspectionPanel'

describe('ExecutionSummaryInspectionPanel', () => {
  it('renders nothing when execution summary is absent', () => {
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={null} />)
    expect(html).toBe('')
  })

  it('renders bounded execution summary fields when present and stays read-only', () => {
    const project = {
      project_id: 'p-summary',
      interactive_modules: {
        execution_summary: {
          provider_name: 'openai',
          lifecycle_state: 'completed',
          production_signal: {
            type: 'production_signal',
            message: 'Provider failure pattern detected',
          },
          scene_intent: {
            type: 'intent_label',
            label: 'quiet emotional moment',
          },
          intent_signal: {
            type: 'intent_presence',
            message: 'Scene intent present',
          },
          intent_output_signal: {
            type: 'intent_output_presence',
            message: 'Intent and output present',
          },
          intent_output_relation: {
            type: 'intent_output_relation',
            state: 'ready_for_review',
            message: 'Intent and output ready for review',
          },
          provider_status: 'complete',
          has_output_artifacts: true,
          has_error: false,
          latest_updated_at: '2026-04-23T02:30:00Z',
          render_behavior: 'in_progress',
          intervention_suggestion: {
            level: 'advisory',
            message: 'Render appears stuck. Consider manual queue review before further submissions.',
            source: 'render_behavior_rule_v1',
          },
          recurring_pattern: {
            type: 'provider_failure_pattern',
            count: 3,
            provider_name: 'aws',
            message: 'Repeated provider failures detected across recent render events.',
          },
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
          scene_visual_links: {
            scene_001: ['ref_001'],
          },
          link_completeness: {
            linked_scenes: 1,
            total_scenes: 3,
          },
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
          shot_intent: {
            shot_scene_001_001: 'general',
          },
          shot_variety: {
            diversity: 'none',
          },
          scene_coverage: {
            scene_001: 'covered',
          },
          shot_planning_summary: {
            covered_scenes: 1,
            total_scenes: 1,
            variety: 'none',
          },
          shot_advisory_note: {
            note: 'Shot variety is minimal',
          },
          co_director_visual_observation: {
            note: 'Visual style is consistent across all scenes',
          },
          co_director_shot_observation: {
            note: 'Shot variety is minimal',
          },
          co_director_observation_summary: {
            notes: [
              'Visual style is consistent across all scenes',
              'Shot variety is minimal',
            ],
          },
          co_director_observation_contract: {
            mode: 'read_only',
            authority: 'none',
            influence: 'disabled',
          },
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
          prompt_influence_gate_v1: {
            prompt_influence_enabled: true,
            scope: 'advisory_only',
            reason: 'Prompt influence enabled in advisory mode',
          },
          visual_prompt_tokens: ['image'],
          shot_prompt_tokens: ['wide establishing shot'],
          prompt_envelope: {
            base_intent: 'Opening intent line',
            visual_tokens: ['image'],
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
              base_intent: 'Opening intent line',
              visual_tokens: ['image'],
              shot_tokens: ['wide establishing shot'],
            },
          },
          render_output: {
            render_id: 'render_stub_shot_scene_001_001',
            shot_id: 'shot_scene_001_001',
            status: 'pending',
            prompt_snapshot: {
              base_intent: 'Opening intent line',
              visual_tokens: ['image'],
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
          take_artifacts: [
            {
              iteration: 1,
              render_id: 'render_stub_shot_scene_001_001',
              status: 'complete',
            },
          ],
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
              alignment: 'partial',
              coverage: '1/2',
              valid_structure: true,
            },
          ],
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
          provider_adapter_status: {
            provider: 'openai',
            enabled: false,
          },
          provider_adapter_readiness_gate: {
            ready: false,
          },
          execution_unlock_state: {
            locked: true,
          },
          execution_eligibility: {
            eligible: false,
          },
          execution_request_envelope: {
            request: 'blocked',
          },
          request_schema_validation: {
            valid: false,
          },
          provider_validation: {
            valid: false,
          },
          payload_sanitization: {
            safe: false,
          },
          shot_queue: [
            { shot_id: 'shot_scene_001_001', scene_id: 'scene_001', status: 'queued' },
          ],
          multi_shot_readiness: {
            ready: 0,
          },
          shot_execution_ledger: [
            { shot_id: 'shot_scene_001_001', scene_id: 'scene_001', status: 'not_executed' },
          ],
          previs_scene_board: [
            { scene_id: 'scene_001', shot_count: 2, linked_refs: ['ref_001'] },
          ],
          previs_asset_map: [
            { asset_id: 'asset_001', scenes: ['scene_001', 'scene_002'] },
          ],
          validation_inspection: {
            advisory_disposition: 'review',
            advisory_confidence: 0.71,
            package_fidelity: 0.82,
            issues: [{ severity: 'warning' }, { severity: 'critical' }],
          },
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Execution Summary Inspection')
    expect(html).toContain('Provider</span>')
    expect(html).toContain('openai')
    expect(html).toContain('Enabled false')
    expect(html).toContain('Ready false')
    expect(html).toContain('Execution</span>')
    expect(html).toContain('Locked')
    expect(html).toContain('Eligible false')
    expect(html).toContain('Request blocked')
    expect(html).toContain('Validation</span>')
    expect(html).toContain('Schema invalid')
    expect(html).toContain('Provider invalid')
    expect(html).toContain('Payload unsafe')
    expect(html).toContain('Shots</span>')
    expect(html).toContain('Queue 1')
    expect(html).toContain('Ready 0')
    expect(html).toContain('Takes</span>')
    expect(html).toContain('Comparable false')
    expect(html).toContain('Auto Select false')
    expect(html).toContain('Render</span>')
    expect(html).toContain('Source mock')
    expect(html).toContain('Output no')
    expect(html).toContain('Ready to Render: NO')
    expect(html).toContain('Execution Path')
    expect(html).toContain('intent_present: true')
    expect(html).toContain('request_valid: false')
    expect(html).toContain('eligible: false')
    expect(html).toContain('blocked: true')
    expect(html).toContain('Render Output')
    expect(html).toContain('Output Available: No')
    expect(html).toContain('Shot Result Panel')
    expect(html).toContain('shot_id shot_scene_001_001')
    expect(html).toContain('status not_executed')
    expect(html).toContain('Take Result Card')
    expect(html).toContain('iteration 1')
    expect(html).toContain('render_id render_stub_shot_scene_001_001')
    expect(html).toContain('Mock render output available')
    expect(html).toContain('Studio Dashboard')
    expect(html).toContain('Provider Card')
    expect(html).toContain('Execution Card')
    expect(html).toContain('Validation Card')
    expect(html).toContain('Shot Pipeline Card')
    expect(html).toContain('Take Pipeline Card')
    expect(html).toContain('Previs Overview')
    expect(html).toContain('Scene Count: 1')
    expect(html).toContain('Total Shots: 2')
    expect(html).toContain('Reference Count: 1')
    expect(html).toContain('Frame Count: 2')
    expect(html).toContain('Shot Preview')
    expect(html).toContain('shot_id')
    expect(html).toContain('scene_id')
    expect(html).toContain('not_executed')
    expect(html).toContain('Take Table')
    expect(html).toContain('iteration')
    expect(html).toContain('render_id')
    expect(html).toContain('Studio Safety')
    expect(html).toContain('Overall: safe_for_control_phase')
    expect(html).toContain('Memory: true')
    expect(html).toContain('Visual: true')
    expect(html).toContain('Shot: true')
    expect(html).toContain('Render: true')
    expect(html).toContain('Co-Director: true')
    expect(html).toContain('Prompt Influence')
    expect(html).toContain('Enabled: true')
    expect(html).toContain('Scope: advisory_only')
    expect(html).toContain('Visual Tokens: image')
    expect(html).toContain('Shot Tokens: wide establishing shot')
    expect(html).toContain('Prompt Envelope')
    expect(html).toContain('Base Intent: Opening intent line')
    expect(html).toContain('Visual Tokens: image')
    expect(html).toContain('Shot Tokens: wide establishing shot')
    expect(html).toContain('Locked: true')
    expect(html).toContain('Render Control')
    expect(html).toContain('Enabled: true')
    expect(html).toContain('Mode: single_shot')
    expect(html).toContain('Shot: shot_scene_001_001')
    expect(html).toContain('Status: pending')
    expect(html).toContain('Render Output')
    expect(html).toContain('Render ID: render_stub_shot_scene_001_001')
    expect(html).toContain('Shot: shot_scene_001_001')
    expect(html).toContain('Status: pending')
    expect(html).toContain('Alignment: partial')
    expect(html).toContain('Coverage: 1/2')
    expect(html).toContain('Prompt Preview: Opening intent line')
    expect(html).toContain('Output Evaluation')
    expect(html).toContain('Has Output: true')
    expect(html).toContain('Valid Structure: true')
    expect(html).toContain('Render ID Present: true')
    expect(html).toContain('Status: valid')
    expect(html).toContain('Retry Gate')
    expect(html).toContain('Retry Allowed: false')
    expect(html).toContain('Reason: Valid output achieved')
    expect(html).toContain('Execution Snapshot')
    expect(html).toContain('Iteration: 1 / 3')
    expect(html).toContain('Status: complete')
    expect(html).toContain('Render Attempted: true')
    expect(html).toContain('Retry Allowed: false')
    expect(html).toContain('Finalized: true')
    expect(html).toContain('Take Analysis')
    expect(html).toContain('Iteration: 1')
    expect(html).toContain('Status: complete')
    expect(html).toContain('Render ID: render_stub_shot_scene_001_001')
    expect(html).toContain('Retry Allowed: false')
    expect(html).toContain('Advisory Note: Take is usable')
    expect(html).toContain('Take Review')
    expect(html).toContain('Comparable: false')
    expect(html).toContain('Differences: 0')
    expect(html).toContain('Auto Select: false')
    expect(html).toContain('Authority: manual_only')
    expect(html).toContain('Take ID 1 · Alignment partial · Coverage 1/2 · Valid Structure true')
    expect(html).toContain('Loop Planning')
    expect(html).toContain('Ready: false')
    expect(html).toContain('Reason: Retry not allowed')
    expect(html).toContain('Next Iteration: 2')
    expect(html).toContain('Remaining: 2')
    expect(html).toContain('Advisory: None')
    expect(html).toContain('Loop Execution')
    expect(html).toContain('Execute: false')
    expect(html).toContain('Next Iteration: 2')
    expect(html).toContain('Simulated Iteration: 1')
    expect(html).toContain('Output Status: pending')
    expect(html).toContain('Execution Control')
    expect(html).toContain('Allowed: false')
    expect(html).toContain('Mode: blocked')
    expect(html).toContain('State: blocked')
    expect(html).toContain('Shot ID: None')
    expect(html).toContain('Status: not_executed')
    expect(html).toContain('Execution Monitor')
    expect(html).toContain('State: blocked')
    expect(html).toContain('Result: not_executed')
    expect(html).toContain('Synced: false')
    expect(html).toContain('Render ID: None')
    expect(html).toContain('Provider Selection')
    expect(html).toContain('Requested: none')
    expect(html).toContain('Selected: mock')
    expect(html).toContain('Allowed: true')
    expect(html).toContain('Fallback Used: false')
    expect(html).toContain('Reason: Default provider selected')
    expect(html).toContain('Provider Control')
    expect(html).toContain('Default Provider: mock')
    expect(html).toContain('Selected Provider: mock')
    expect(html).toContain('Provider Enabled: true')
    expect(html).toContain('Credentials Present: true')
    expect(html).toContain('Can Execute: false')
    expect(html).toContain('Selection Mode: manual_only')
    expect(html).toContain('Provider Capability')
    expect(html).toContain('Supports Render: true')
    expect(html).toContain('Requires Credentials: false')
    expect(html).toContain('Supports Multi-Shot: false')
    expect(html).toContain('Provider Safety')
    expect(html).toContain('Execution Enabled: false')
    expect(html).toContain('Reason: Real provider execution is disabled by safety boundary')
    expect(html).toContain('Provider Handoff')
    expect(html).toContain('Provider: mock')
    expect(html).toContain('Enabled: false')
    expect(html).toContain('Request ID: handoff_mock_none')
    expect(html).toContain('Allowed: false')
    expect(html).toContain('Blocked Reason: Execution permission denied')
    expect(html).toContain('Production Signal')
    expect(html).toContain('Provider failure pattern detected')
    expect(html).toContain('Scene Intent')
    expect(html).toContain('quiet emotional moment')
    expect(html).toContain('Intent Signal')
    expect(html).toContain('Scene intent present')
    expect(html).toContain('Intent Output Signal')
    expect(html).toContain('Intent and output present')
    expect(html).toContain('Intent Output Relation')
    expect(html).toContain('Intent and output ready for review')
    expect(html).toContain('Provider')
    expect(html).toContain('Lifecycle State')
    expect(html).toContain('Provider Status')
    expect(html).toContain('Output Artifacts')
    expect(html).toContain('Error Present')
    expect(html).toContain('Latest Updated')
    expect(html).toContain('Render Behavior')
    expect(html).toContain('Intervention Suggestion')
    expect(html).toContain('Recurring Pattern')
    expect(html).toContain('openai')
    expect(html).toContain('completed')
    expect(html).toContain('complete')
    expect(html).toContain('In progress')
    expect(html).toContain('Render appears stuck. Consider manual queue review before further submissions.')
    expect(html).toContain('Provider failure pattern')
    expect(html).toContain('Provider:')
    expect(html).toContain('Count:')
    expect(html).toContain('aws')
    expect(html).toContain('3')
    expect(html).toContain('Repeated provider failures detected across recent render events.')
    expect(html).toContain('Visual References')
    expect(html).toContain('References 1')
    expect(html).toContain('Linked scenes 1')
    expect(html).toContain('Types 1')
    expect(html).toContain('Frame Analysis')
    expect(html).toContain('Frames 1')
    expect(html).toContain('Artifacts 1')
    expect(html).toContain('Scene-Visual Linkage')
    expect(html).toContain('Linked 1 / 3 scenes')
    expect(html).toContain('Shot Planning')
    expect(html).toContain('Scenes 1')
    expect(html).toContain('Candidates 1')
    expect(html).toContain('Shot Thinking')
    expect(html).toContain('Scenes Covered: 1 / 1')
    expect(html).toContain('Variety: none')
    expect(html).toContain('Advisory: Shot variety is minimal')
    expect(html).toContain('Co-Director Notes')
    expect(html).toContain('Visual style is consistent across all scenes')
    expect(html).toContain('Visual Summary')
    expect(html).toContain('Dominant Types: image')
    expect(html).toContain('Consistency: low')
    expect(html).toContain('Tension Scenes: 1')
    expect(html).toContain('Memory Advisory')
    expect(html).toContain('Memory Summary')
    expect(html).toContain('Memory Review State')
    expect(html).toContain('Ready')
    expect(html).toContain('Memory Visibility')
    expect(html).toContain('Co-Director Memory Advisory')
    expect(html).toContain('Memory Authority Boundary')
    expect(html).toContain('Candidates 2')
    expect(html).toContain('Records 0')
    expect(html).toContain('Aggregate 0')
    expect(html).toContain('Categories')
    expect(html).toContain('Character pairs: No')
    expect(html).toContain('Locations: Yes')
    expect(html).toContain('Time of day: Yes')
    expect(html).toContain('Influence disabled')
    expect(html).toContain('Authority none')
    expect(html).toContain('Memory influence disabled')
    expect(html).toContain('Yes')
    expect(html).toContain('No')
    expect(html).toContain('Validation Disposition')
    expect(html).toContain('Validation Confidence')
    expect(html).toContain('Validation Issues')
    expect(html).toContain('Critical Issues')
    expect(html).toContain('Warnings')
    expect(html).toContain('Package Fidelity')
    expect(html).toContain('review')
    expect(html).toContain('0.71')
    expect(html).toContain('0.82')

    // Read-only: no interactive control widgets implying authority.
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a')

    // QA automation: stable data-testid selector exists
    expect(html).toContain('data-testid="execution-summary-inspection"')
    expect(html).toContain('data-testid="studio-provider-status-strip"')
    expect(html).toContain('data-testid="studio-execution-status-strip"')
    expect(html).toContain('data-testid="studio-validation-status-strip"')
    expect(html).toContain('data-testid="studio-shot-pipeline-strip"')
    expect(html).toContain('data-testid="studio-take-pipeline-strip"')
    expect(html).toContain('data-testid="studio-render-status-strip"')
    expect(html).toContain('data-testid="studio-dashboard-section"')
    expect(html).toContain('data-testid="mock-render-output-card"')
    expect(html).toContain('data-testid="render-readiness-indicator"')
    expect(html).toContain('data-testid="shot-result-panel"')
    expect(html).toContain('data-testid="take-result-card"')
    expect(html).toContain('data-testid="preview-content-panel"')
    expect(html).toContain('data-testid="execution-path-trace"')
    expect(html).toContain('data-testid="previs-overview-section"')
    expect(html).toContain('data-testid="shot-preview-table-section"')
    expect(html).toContain('data-testid="take-table-section"')
    expect(html).toContain('data-testid="studio-safety-section"')
    expect(html).toContain('data-testid="prompt-influence-section"')
    expect(html).toContain('data-testid="prompt-envelope-section"')
    expect(html).toContain('data-testid="render-control-section"')
    expect(html).toContain('data-testid="render-output-section"')
    expect(html).toContain('data-testid="output-evaluation-section"')
    expect(html).toContain('data-testid="retry-gate-section"')
    expect(html).toContain('data-testid="execution-snapshot-section"')
    expect(html).toContain('data-testid="take-analysis-section"')
    expect(html).toContain('data-testid="take-review-section"')
    expect(html).toContain('data-testid="loop-planning-section"')
    expect(html).toContain('data-testid="loop-execution-section"')
    expect(html).toContain('data-testid="execution-control-section"')
    expect(html).toContain('data-testid="provider-selection-section"')
    expect(html).toContain('data-testid="provider-control-section"')
    expect(html).toContain('data-testid="provider-capability-section"')
    expect(html).toContain('data-testid="provider-safety-section"')
    expect(html).toContain('data-testid="provider-handoff-section"')
    expect(html).toContain('data-testid="visual-references-section"')
    expect(html).toContain('data-testid="frame-analysis-section"')
    expect(html).toContain('data-testid="scene-visual-linkage-section"')
    expect(html).toContain('data-testid="shot-planning-section"')
    expect(html).toContain('data-testid="shot-thinking-section"')
    expect(html).toContain('data-testid="co-director-notes-section"')
    expect(html).toContain('data-testid="visual-summary-section"')
    expect(html).toContain('data-testid="validation-inspection-section"')
  })

  it('always renders studio safety section with safe defaults when safety fields are missing', () => {
    const project = {
      project_id: 'p-studio-safety-defaults',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Provider</span>')
    expect(html).toContain('mock')
    expect(html).toContain('Enabled false')
    expect(html).toContain('Ready false')
    expect(html).toContain('Execution</span>')
    expect(html).toContain('Locked')
    expect(html).toContain('Eligible false')
    expect(html).toContain('Request blocked')
    expect(html).toContain('Validation</span>')
    expect(html).toContain('Schema invalid')
    expect(html).toContain('Provider invalid')
    expect(html).toContain('Payload unsafe')
    expect(html).toContain('Shots</span>')
    expect(html).toContain('Queue 0')
    expect(html).toContain('Ready 0')
    expect(html).toContain('Takes</span>')
    expect(html).toContain('Comparable false')
    expect(html).toContain('Auto Select false')
    expect(html).toContain('Render</span>')
    expect(html).toContain('Source none')
    expect(html).toContain('Output no')
    expect(html).toContain('Studio Dashboard')
    expect(html).toContain('Render Output')
    expect(html).toContain('Output Available: No')
    expect(html).toContain('Ready to Render: NO')
    expect(html).toContain('Execution Path')
    expect(html).toContain('intent_present: false')
    expect(html).toContain('request_valid: false')
    expect(html).toContain('eligible: false')
    expect(html).toContain('blocked: true')
    expect(html).toContain('Shot Result Panel')
    expect(html).toContain('Take Result Card')
    expect(html).toContain('No render output yet')
    expect(html).toContain('Previs Overview')
    expect(html).toContain('Scene Count: 0')
    expect(html).toContain('Total Shots: 0')
    expect(html).toContain('Reference Count: 0')
    expect(html).toContain('Frame Count: 0')
    expect(html).toContain('Shot Preview')
    expect(html).toContain('Take Table')
    expect(html).toContain('No data available')
    expect(html).toContain('Studio Safety')
    expect(html).toContain('Overall: not_ready')
    expect(html).toContain('Memory: false')
    expect(html).toContain('Visual: false')
    expect(html).toContain('Shot: false')
    expect(html).toContain('Render: false')
    expect(html).toContain('Co-Director: false')
    expect(html).toContain('data-testid="studio-safety-section"')
    expect(html).toContain('Prompt Influence')
    expect(html).toContain('Enabled: false')
    expect(html).toContain('Scope: advisory_only')
    expect(html).toContain('Visual Tokens: None')
    expect(html).toContain('Shot Tokens: None')
    expect(html).toContain('Prompt Envelope')
    expect(html).toContain('Base Intent: None')
    expect(html).toContain('Locked: true')
    expect(html).toContain('Render Control')
    expect(html).toContain('Enabled: false')
    expect(html).toContain('Mode: single_shot')
    expect(html).toContain('Shot: None')
    expect(html).toContain('Status: None')
    expect(html).toContain('Render Output')
    expect(html).toContain('Render ID: None')
    expect(html).toContain('Alignment: None')
    expect(html).toContain('Coverage: None')
    expect(html).toContain('Prompt Preview: None')
    expect(html).toContain('Output Evaluation')
    expect(html).toContain('Has Output: false')
    expect(html).toContain('Valid Structure: false')
    expect(html).toContain('Render ID Present: false')
    expect(html).toContain('Status: none')
    expect(html).toContain('Retry Gate')
    expect(html).toContain('Retry Allowed: false')
    expect(html).toContain('Reason: Execution not ready')
    expect(html).toContain('Execution Snapshot')
    expect(html).toContain('Iteration: 0 / 3')
    expect(html).toContain('Status: idle')
    expect(html).toContain('Render Attempted: false')
    expect(html).toContain('Finalized: false')
    expect(html).not.toContain('Take Analysis')
    expect(html).toContain('Take Review')
    expect(html).toContain('Comparable: false')
    expect(html).toContain('Differences: 0')
    expect(html).toContain('Auto Select: false')
    expect(html).toContain('Authority: manual_only')
    expect(html).toContain('No takes')
    expect(html).toContain('Loop Planning')
    expect(html).toContain('Ready: false')
    expect(html).toContain('Reason: Retry not allowed')
    expect(html).toContain('Next Iteration: 1')
    expect(html).toContain('Remaining: 3')
    expect(html).toContain('Advisory: None')
    expect(html).toContain('Loop Execution')
    expect(html).toContain('Execute: false')
    expect(html).toContain('Simulated Iteration: 0')
    expect(html).toContain('Output Status: none')
    expect(html).toContain('Execution Control')
    expect(html).toContain('Allowed: false')
    expect(html).toContain('Mode: blocked')
    expect(html).toContain('State: blocked')
    expect(html).toContain('Shot ID: None')
    expect(html).toContain('Status: not_executed')
    expect(html).toContain('Execution Monitor')
    expect(html).toContain('Result: not_executed')
    expect(html).toContain('Synced: false')
    expect(html).toContain('Render ID: None')
    expect(html).toContain('Provider Selection')
    expect(html).toContain('Requested: none')
    expect(html).toContain('Selected: mock')
    expect(html).toContain('Allowed: true')
    expect(html).toContain('Fallback Used: false')
    expect(html).toContain('Reason: Default provider selected')
    expect(html).toContain('Provider Control')
    expect(html).toContain('Default Provider: mock')
    expect(html).toContain('Selected Provider: mock')
    expect(html).toContain('Provider Enabled: true')
    expect(html).toContain('Credentials Present: true')
    expect(html).toContain('Can Execute: false')
    expect(html).toContain('Selection Mode: manual_only')
    expect(html).toContain('Provider Capability')
    expect(html).toContain('Supports Render: true')
    expect(html).toContain('Requires Credentials: false')
    expect(html).toContain('Supports Multi-Shot: false')
    expect(html).toContain('Provider Safety')
    expect(html).toContain('Execution Enabled: false')
    expect(html).toContain('Reason: Real provider execution is disabled by safety boundary')
    expect(html).toContain('Provider Handoff')
    expect(html).toContain('Provider: mock')
    expect(html).toContain('Enabled: false')
    expect(html).toContain('Request ID: handoff_mock_none')
    expect(html).toContain('Allowed: false')
    expect(html).toContain('Blocked Reason: Execution permission denied')
    expect(html).toContain('data-testid="prompt-influence-section"')
    expect(html).toContain('data-testid="prompt-envelope-section"')
    expect(html).toContain('data-testid="render-control-section"')
    expect(html).toContain('data-testid="render-output-section"')
    expect(html).toContain('data-testid="output-evaluation-section"')
    expect(html).toContain('data-testid="retry-gate-section"')
    expect(html).toContain('data-testid="execution-snapshot-section"')
    expect(html).not.toContain('data-testid="take-analysis-section"')
    expect(html).toContain('data-testid="take-review-section"')
    expect(html).toContain('data-testid="loop-planning-section"')
    expect(html).toContain('data-testid="loop-execution-section"')
    expect(html).toContain('data-testid="execution-control-section"')
    expect(html).toContain('data-testid="execution-monitor-section"')
    expect(html).toContain('data-testid="provider-selection-section"')
    expect(html).toContain('data-testid="provider-control-section"')
    expect(html).toContain('data-testid="provider-capability-section"')
    expect(html).toContain('data-testid="provider-safety-section"')
    expect(html).toContain('data-testid="provider-handoff-section"')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('hides validation inspection section when validation data is absent', () => {
    const project = {
      project_id: 'p-no-validation',
      execution_summary: {
        provider_name: 'generic',
        lifecycle_state: 'submitted',
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Execution Summary Inspection')
    expect(html).not.toContain('Production Signal')
    expect(html).not.toContain('Scene Intent')
    expect(html).not.toContain('Intent Signal')
    expect(html).not.toContain('Intent Output Signal')
    expect(html).not.toContain('Intent Output Relation')
    expect(html).not.toContain('Render Behavior')
    expect(html).not.toContain('Intervention Suggestion')
    expect(html).not.toContain('Recurring Pattern')
    expect(html).not.toContain('Validation Disposition')
    expect(html).not.toContain('data-testid="validation-inspection-section"')
  })

  it('hides malformed take review rows safely', () => {
    const project = {
      project_id: 'p-take-review-malformed',
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        take_comparison_v2: {
          comparable: true,
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
            coverage: '1/1',
            valid_structure: true,
          },
          {
            take_id: 'bad',
            alignment: '',
            coverage: null,
            valid_structure: 'yes',
          },
        ],
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Take Review')
    expect(html).toContain('Comparable: true')
    expect(html).toContain('Differences: 0')
    expect(html).toContain('Take ID 1 · Alignment none · Coverage 1/1 · Valid Structure true')
    expect(html).not.toContain('Take ID bad')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('renders stuck recurring pattern without provider and remains read-only', () => {
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
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Recurring Pattern')
    expect(html).toContain('Stuck pattern')
    expect(html).toContain('Count:')
    expect(html).toContain('Repeated stuck render states detected across recent queue entries.')
    expect(html).not.toContain('Provider: <span')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
  })

  it('renders visual references section only when summary has reference_count > 0', () => {
    const withReferences = {
      project_id: 'p-with-visual-references',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        visual_reference_summary: {
          reference_count: 2,
          linked_scene_count: 1,
          type_count: 1,
        },
      },
    } as never
    const withoutReferences = {
      project_id: 'p-without-visual-references',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        visual_reference_summary: {
          reference_count: 0,
          linked_scene_count: 0,
          type_count: 0,
        },
      },
    } as never

    const withHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withReferences} />)
    const withoutHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withoutReferences} />)

    expect(withHtml).toContain('Visual References')
    expect(withHtml).toContain('References 2')
    expect(withHtml).toContain('Linked scenes 1')
    expect(withHtml).toContain('Types 1')
    expect(withoutHtml).not.toContain('Visual References')
    expect(withHtml).not.toContain('<button')
    expect(withHtml).not.toContain('<input')
    expect(withHtml).not.toContain('<select')
    expect(withHtml).not.toContain('<textarea')
    expect(withHtml).not.toContain('<a ')
  })

  it('hides visual references section for invalid or missing summary payload', () => {
    const invalidSummary = {
      project_id: 'p-invalid-visual-summary',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        visual_reference_summary: {
          reference_count: -1,
          linked_scene_count: 0,
          type_count: 0,
        },
      },
    } as never
    const missingSummary = {
      project_id: 'p-missing-visual-summary',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never

    const invalidHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={invalidSummary} />)
    const missingHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={missingSummary} />)

    expect(invalidHtml).not.toContain('Visual References')
    expect(missingHtml).not.toContain('Visual References')
    expect(invalidHtml).not.toContain('data-testid="visual-references-section"')
    expect(missingHtml).not.toContain('data-testid="visual-references-section"')
  })

  it('renders frame analysis section when frame_count > 0', () => {
    const project = {
      project_id: 'p-frame-analysis-visible',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        frame_stats: {
          frame_count: 2,
          artifact_count: 1,
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Frame Analysis')
    expect(html).toContain('Frames 2')
    expect(html).toContain('Artifacts 1')
    expect(html).toContain('data-testid="frame-analysis-section"')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('hides frame analysis section when frame stats are missing/invalid/empty', () => {
    const emptyStats = {
      project_id: 'p-frame-analysis-empty',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        frame_stats: {
          frame_count: 0,
          artifact_count: 0,
        },
      },
    } as never
    const invalidStats = {
      project_id: 'p-frame-analysis-invalid',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        frame_stats: {
          frame_count: -1,
          artifact_count: 1,
        },
      },
    } as never
    const missingStats = {
      project_id: 'p-frame-analysis-missing',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never

    const emptyHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={emptyStats} />)
    const invalidHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={invalidStats} />)
    const missingHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={missingStats} />)

    expect(emptyHtml).not.toContain('Frame Analysis')
    expect(invalidHtml).not.toContain('Frame Analysis')
    expect(missingHtml).not.toContain('Frame Analysis')
    expect(emptyHtml).not.toContain('data-testid="frame-analysis-section"')
    expect(invalidHtml).not.toContain('data-testid="frame-analysis-section"')
    expect(missingHtml).not.toContain('data-testid="frame-analysis-section"')
  })

  it('renders scene-visual linkage section when total_scenes > 0', () => {
    const project = {
      project_id: 'p-scene-visual-linkage-visible',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        link_completeness: {
          linked_scenes: 2,
          total_scenes: 5,
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Scene-Visual Linkage')
    expect(html).toContain('Linked 2 / 5 scenes')
    expect(html).toContain('data-testid="scene-visual-linkage-section"')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('hides scene-visual linkage section when missing or invalid or total_scenes is zero', () => {
    const zeroTotal = {
      project_id: 'p-scene-visual-linkage-zero',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        link_completeness: {
          linked_scenes: 0,
          total_scenes: 0,
        },
      },
    } as never
    const invalid = {
      project_id: 'p-scene-visual-linkage-invalid',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        link_completeness: {
          linked_scenes: -1,
          total_scenes: 2,
        },
      },
    } as never
    const missing = {
      project_id: 'p-scene-visual-linkage-missing',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never

    const zeroHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={zeroTotal} />)
    const invalidHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={invalid} />)
    const missingHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={missing} />)

    expect(zeroHtml).not.toContain('Scene-Visual Linkage')
    expect(invalidHtml).not.toContain('Scene-Visual Linkage')
    expect(missingHtml).not.toContain('Scene-Visual Linkage')
    expect(zeroHtml).not.toContain('data-testid="scene-visual-linkage-section"')
    expect(invalidHtml).not.toContain('data-testid="scene-visual-linkage-section"')
    expect(missingHtml).not.toContain('data-testid="scene-visual-linkage-section"')
  })

  it('renders shot planning section when shot candidates exist', () => {
    const project = {
      project_id: 'p-shot-planning-visible',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        shot_candidates: [
          {
            scene_id: 'scene_001',
            shot_id: 'shot_scene_001_001',
            source_refs: ['ref_001'],
          },
          {
            scene_id: 'scene_002',
            shot_id: 'shot_scene_002_001',
            source_refs: [],
          },
        ],
        shot_coverage: {
          scene_001: { candidate_count: 1 },
          scene_002: { candidate_count: 1 },
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Shot Planning')
    expect(html).toContain('Scenes 2')
    expect(html).toContain('Candidates 2')
    expect(html).toContain('data-testid="shot-planning-section"')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('hides shot planning section when candidates missing or invalid', () => {
    const missing = {
      project_id: 'p-shot-planning-missing',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never
    const invalid = {
      project_id: 'p-shot-planning-invalid',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        shot_candidates: [
          {
            scene_id: 'scene_001',
            shot_id: 'shot_scene_001_001',
            source_refs: [9],
          },
        ],
      },
    } as never
    const empty = {
      project_id: 'p-shot-planning-empty',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        shot_candidates: [],
      },
    } as never

    const missingHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={missing} />)
    const invalidHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={invalid} />)
    const emptyHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={empty} />)

    expect(missingHtml).not.toContain('Shot Planning')
    expect(invalidHtml).not.toContain('Shot Planning')
    expect(emptyHtml).not.toContain('Shot Planning')
    expect(missingHtml).not.toContain('data-testid="shot-planning-section"')
    expect(invalidHtml).not.toContain('data-testid="shot-planning-section"')
    expect(emptyHtml).not.toContain('data-testid="shot-planning-section"')
  })

  it('renders shot thinking section only when total scenes is greater than zero', () => {
    const visible = {
      project_id: 'p-shot-thinking-visible',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        shot_planning_summary: {
          covered_scenes: 2,
          total_scenes: 3,
          variety: 'low',
        },
        shot_advisory_note: {
          note: 'Shot variety is limited',
        },
      },
    } as never
    const hidden = {
      project_id: 'p-shot-thinking-hidden',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        shot_planning_summary: {
          covered_scenes: 0,
          total_scenes: 0,
          variety: 'none',
        },
        shot_advisory_note: {
          note: '',
        },
      },
    } as never

    const visibleHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={visible} />)
    const hiddenHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={hidden} />)

    expect(visibleHtml).toContain('Shot Thinking')
    expect(visibleHtml).toContain('Scenes Covered: 2 / 3')
    expect(visibleHtml).toContain('Variety: low')
    expect(visibleHtml).toContain('Advisory: Shot variety is limited')
    expect(visibleHtml).toContain('data-testid="shot-thinking-section"')
    expect(hiddenHtml).not.toContain('Shot Thinking')
    expect(hiddenHtml).not.toContain('data-testid="shot-thinking-section"')
    expect(visibleHtml).not.toContain('<button')
    expect(visibleHtml).not.toContain('<input')
    expect(visibleHtml).not.toContain('<select')
    expect(visibleHtml).not.toContain('<textarea')
    expect(visibleHtml).not.toContain('<a ')
  })

  it('renders co-director notes section only when notes are present', () => {
    const visible = {
      project_id: 'p-co-director-notes-visible',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        co_director_observation_summary: {
          notes: [
            'Visual style varies significantly across scenes with notable variation in some scenes',
            'Shot variety is somewhat limited',
          ],
        },
      },
    } as never
    const hidden = {
      project_id: 'p-co-director-notes-hidden',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        co_director_observation_summary: {
          notes: [],
        },
      },
    } as never

    const visibleHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={visible} />)
    const hiddenHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={hidden} />)

    expect(visibleHtml).toContain('Co-Director Notes')
    expect(visibleHtml).toContain('Shot variety is somewhat limited')
    expect(visibleHtml).toContain('data-testid="co-director-notes-section"')
    expect(hiddenHtml).not.toContain('Co-Director Notes')
    expect(hiddenHtml).not.toContain('data-testid="co-director-notes-section"')
    expect(visibleHtml).not.toContain('<button')
    expect(visibleHtml).not.toContain('<input')
    expect(visibleHtml).not.toContain('<select')
    expect(visibleHtml).not.toContain('<textarea')
    expect(visibleHtml).not.toContain('<a ')
  })

  it('renders visual summary only when visual pattern type counts are non-empty', () => {
    const withSummary = {
      project_id: 'p-visual-summary-visible',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        visual_pattern_summary: {
          dominant_types: ['image', 'video'],
          type_counts: {
            image: 2,
            video: 2,
          },
        },
        visual_consistency: {
          consistent: true,
          variance_level: 'low',
        },
        visual_tension: {
          tension_scenes: ['scene_003'],
        },
      },
    } as never
    const withoutSummary = {
      project_id: 'p-visual-summary-hidden',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        visual_pattern_summary: {
          dominant_types: [],
          type_counts: {},
        },
      },
    } as never

    const withHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withSummary} />)
    const withoutHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withoutSummary} />)

    expect(withHtml).toContain('Visual Summary')
    expect(withHtml).toContain('Dominant Types: image, video')
    expect(withHtml).toContain('Consistency: low')
    expect(withHtml).toContain('Tension Scenes: 1')
    expect(withHtml).toContain('data-testid="visual-summary-section"')
    expect(withoutHtml).not.toContain('Visual Summary')
    expect(withoutHtml).not.toContain('data-testid="visual-summary-section"')
    expect(withHtml).not.toContain('<button')
    expect(withHtml).not.toContain('<input')
    expect(withHtml).not.toContain('<select')
    expect(withHtml).not.toContain('<textarea')
    expect(withHtml).not.toContain('<a ')
  })

  it('renders scene intent only when present', () => {
    const withIntent = {
      project_id: 'p-with-intent',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        scene_intent: {
          type: 'intent_label',
          label: 'high-tension standoff',
        },
      },
    } as never

    const withoutIntent = {
      project_id: 'p-without-intent',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never

    const withIntentHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withIntent} />)
    const withoutIntentHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withoutIntent} />)

    expect(withIntentHtml).toContain('Scene Intent')
    expect(withIntentHtml).toContain('high-tension standoff')
    expect(withoutIntentHtml).not.toContain('Scene Intent')
    expect(withIntentHtml).not.toContain('<button')
    expect(withIntentHtml).not.toContain('<input')
    expect(withIntentHtml).not.toContain('<select')
    expect(withIntentHtml).not.toContain('<textarea')
  })

  it('renders intent signal only when present', () => {
    const withIntentSignal = {
      project_id: 'p-with-intent-signal',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        intent_signal: {
          type: 'intent_presence',
          message: 'Scene intent present',
        },
      },
    } as never

    const withoutIntentSignal = {
      project_id: 'p-without-intent-signal',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never

    const withIntentSignalHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withIntentSignal} />)
    const withoutIntentSignalHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withoutIntentSignal} />)

    expect(withIntentSignalHtml).toContain('Intent Signal')
    expect(withIntentSignalHtml).toContain('Scene intent present')
    expect(withoutIntentSignalHtml).not.toContain('Intent Signal')
    expect(withIntentSignalHtml).not.toContain('<button')
    expect(withIntentSignalHtml).not.toContain('<input')
    expect(withIntentSignalHtml).not.toContain('<select')
    expect(withIntentSignalHtml).not.toContain('<textarea')
  })

  it('renders intent output signal only when present', () => {
    const withIntentOutputSignal = {
      project_id: 'p-with-intent-output-signal',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'complete',
        intent_output_signal: {
          type: 'intent_output_presence',
          message: 'Intent and output present',
        },
      },
    } as never

    const withoutIntentOutputSignal = {
      project_id: 'p-without-intent-output-signal',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'complete',
      },
    } as never

    const withIntentOutputSignalHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withIntentOutputSignal} />)
    const withoutIntentOutputSignalHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withoutIntentOutputSignal} />)

    expect(withIntentOutputSignalHtml).toContain('Intent Output Signal')
    expect(withIntentOutputSignalHtml).toContain('Intent and output present')
    expect(withoutIntentOutputSignalHtml).not.toContain('Intent Output Signal')
    expect(withIntentOutputSignalHtml).not.toContain('<button')
    expect(withIntentOutputSignalHtml).not.toContain('<input')
    expect(withIntentOutputSignalHtml).not.toContain('<select')
    expect(withIntentOutputSignalHtml).not.toContain('<textarea')
  })

  it('renders intent output relation only when present', () => {
    const withIntentOutputRelation = {
      project_id: 'p-with-intent-output-relation',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'complete',
        intent_output_relation: {
          type: 'intent_output_relation',
          state: 'ready_for_review',
          message: 'Intent and output ready for review',
        },
      },
    } as never

    const withoutIntentOutputRelation = {
      project_id: 'p-without-intent-output-relation',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'complete',
      },
    } as never

    const withIntentOutputRelationHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withIntentOutputRelation} />)
    const withoutIntentOutputRelationHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={withoutIntentOutputRelation} />)

    expect(withIntentOutputRelationHtml).toContain('Intent Output Relation')
    expect(withIntentOutputRelationHtml).toContain('Intent and output ready for review')
    expect(withoutIntentOutputRelationHtml).not.toContain('Intent Output Relation')
    expect(withIntentOutputRelationHtml).not.toContain('<button')
    expect(withIntentOutputRelationHtml).not.toContain('<input')
    expect(withIntentOutputRelationHtml).not.toContain('<select')
    expect(withIntentOutputRelationHtml).not.toContain('<textarea')
  })

  it('hides memory inspection section when memory fields are absent', () => {
    const project = {
      project_id: 'p-no-memory-section',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Memory Advisory')
    expect(html).not.toContain('Memory Snapshot')
    expect(html).not.toContain('Categories')
    expect(html).not.toContain('Memory Visibility')
    expect(html).not.toContain('Co-Director Memory Advisory')
    expect(html).not.toContain('Memory Authority Boundary')
    expect(html).not.toContain('data-testid="memory-inspection-section"')
  })

  it('hides memory inspection section when memory data is partial or inconsistent', () => {
    const partialMemory = {
      project_id: 'p-partial-memory',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_advisory_projection: {
          status: 'available',
          message: 'Memory candidates available for future review',
        },
        co_director_memory_visibility: {
          has_memory_candidates: true,
          has_memory_records: false,
          has_memory_aggregate: false,
          influence_mode: 'enabled',
          advisory_status: 'available',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={partialMemory} />)
    expect(html).not.toContain('Memory Advisory')
    expect(html).not.toContain('Memory Snapshot')
    expect(html).not.toContain('Categories')
    expect(html).not.toContain('Memory Visibility')
    expect(html).not.toContain('Co-Director Memory Advisory')
    expect(html).not.toContain('Memory Authority Boundary')
    expect(html).not.toContain('data-testid="memory-inspection-section"')
  })

  it('hides memory snapshot row when memory snapshot summary is invalid/absent', () => {
    const invalidSnapshot = {
      project_id: 'p-invalid-memory-snapshot',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_advisory_projection: {
          status: 'available',
          message: 'Memory candidates available for future review',
        },
        memory_snapshot_summary: {
          candidate_count: 'bad',
          record_count: 0,
          aggregate_count: 0,
          advisory_status: 'available',
          influence_mode: 'disabled',
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
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={invalidSnapshot} />)
    expect(html).not.toContain('Memory Snapshot')
    expect(html).not.toContain('Candidates ')
    expect(html).not.toContain('data-testid="memory-inspection-section"')
  })

  it('renders Memory Summary row when snapshot is valid and influence mode is disabled', () => {
    const project = {
      project_id: 'p-memory-summary-row',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_snapshot_summary: {
          candidate_count: 4,
          record_count: 1,
          aggregate_count: 0,
          advisory_status: 'available',
          influence_mode: 'disabled',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Memory Summary')
    expect(html).toContain('Candidates 4')
    expect(html).toContain('Records 1')
    expect(html).toContain('Aggregate 0')
    expect(html).toContain('Influence disabled')
  })

  it('hides Memory Summary row when influence mode is not disabled', () => {
    const project = {
      project_id: 'p-memory-summary-row-disabled-only',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_snapshot_summary: {
          candidate_count: 4,
          record_count: 1,
          aggregate_count: 0,
          advisory_status: 'available',
          influence_mode: 'enabled',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Memory Summary')
    expect(html).not.toContain('Candidates 4')
  })

  it('renders Memory Review State Ready when available + consistent + disabled', () => {
    const project = {
      project_id: 'p-memory-review-ready',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
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
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Memory Review State')
    expect(html).toContain('Ready')
  })

  it('hides Memory Review State when unavailable or inconsistent', () => {
    const unavailable = {
      project_id: 'p-memory-review-unavailable',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_state_rollup: {
          status: 'unavailable',
          candidate_count: 0,
          influence_mode: 'disabled',
          advisory_status: 'unavailable',
        },
        memory_consistency: {
          is_consistent: true,
          has_required_fields: true,
          gate_disabled: true,
          authority_none: true,
        },
      },
    } as never
    const inconsistent = {
      project_id: 'p-memory-review-inconsistent',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_state_rollup: {
          status: 'available',
          candidate_count: 2,
          influence_mode: 'disabled',
          advisory_status: 'available',
        },
        memory_consistency: {
          is_consistent: false,
          has_required_fields: true,
          gate_disabled: true,
          authority_none: true,
        },
      },
    } as never

    const unavailableHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={unavailable} />)
    const inconsistentHtml = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={inconsistent} />)
    expect(unavailableHtml).not.toContain('Memory Review State')
    expect(inconsistentHtml).not.toContain('Memory Review State')
  })

  it('keeps memory wording neutral and non-interpretive in visible memory state', () => {
    const project = {
      project_id: 'p-memory-neutral-wording',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_advisory_projection: {
          status: 'available',
          message: 'Memory candidates available for future review',
        },
        memory_snapshot_summary: {
          candidate_count: 1,
          record_count: 0,
          aggregate_count: 0,
          advisory_status: 'available',
          influence_mode: 'disabled',
        },
        memory_category_presence: {
          character_pairs: true,
          locations: false,
          time_of_day: false,
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
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Influence disabled')
    expect(html).toContain('Authority none')
    expect(html).toContain('Memory influence disabled')

    // Guardrails: memory UI must not imply ranking/decision/interpretation authority.
    expect(html).not.toContain('important')
    expect(html).not.toContain('rank')
    expect(html).not.toContain('decision')
    expect(html).not.toContain('interpret')
  })

  it('hides memory section for corrupted malformed memory data', () => {
    const project = {
      project_id: 'p-corrupted-memory',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_advisory_projection: {
          status: 'available',
          message: 'Memory candidates available for future review',
        },
        memory_snapshot_summary: {
          candidate_count: 'bad',
          record_count: -1,
          aggregate_count: null,
          advisory_status: '',
          influence_mode: 7,
        },
        memory_category_presence: {
          character_pairs: 'true',
          locations: false,
          time_of_day: false,
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
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Memory Advisory')
    expect(html).not.toContain('Memory Snapshot')
    expect(html).not.toContain('Memory Visibility')
    expect(html).not.toContain('Memory Authority Boundary')
    expect(html).not.toContain('data-testid="memory-inspection-section"')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('safely ignores malformed co-director visual feed payloads without adding UI surfaces', () => {
    const project = {
      project_id: 'p-malformed-visual-feed',
      execution_summary: {
        provider_name: 'openai',
        lifecycle_state: 'in_progress',
        co_director_visual_feed: {
          reference_summary: 'bad',
          frame_snapshot: {
            frame_metadata: 'bad',
            frame_stats: {
              frame_count: 'x',
              artifact_count: 1,
            },
          },
          linkage: {
            linked_scenes: -1,
            total_scenes: 2,
          },
          alignment: {
            state: null,
            note: 7,
          },
          mode: 'read_write',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Co-Director Visual Feed')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('suppresses memory summary and Ready state for inconsistent boundary contracts', () => {
    const project = {
      project_id: 'p-inconsistent-memory-boundaries',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
        memory_snapshot_summary: {
          candidate_count: 2,
          record_count: 1,
          aggregate_count: 0,
          advisory_status: 'available',
          influence_mode: 'enabled',
        },
        memory_state_rollup: {
          status: 'available',
          candidate_count: 2,
          influence_mode: 'enabled',
          advisory_status: 'available',
        },
        memory_consistency: {
          is_consistent: false,
          has_required_fields: true,
          gate_disabled: false,
          authority_none: false,
        },
        memory_output_influence_contract: {
          permitted: true,
          scope: 'all',
          reason: 'bad',
        },
        co_director_memory_contract: {
          mode: 'authoritative',
          authority: 'all',
          memory_influence: 'enabled',
          reason: 'bad',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Memory Summary')
    expect(html).not.toContain('Memory Review State')
    expect(html).not.toContain('data-testid="memory-inspection-section"')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('renders Sequence section when sequenceStatus is present', () => {
    const project = {
      project_id: 'p-sequence',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        sequence_status: {
          scenes: 3,
          shots: 5,
          assembled: false,
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Sequence')
    expect(html).toContain('Scenes: 3')
    expect(html).toContain('Shots: 5')
    expect(html).toContain('Assembled: false')
    expect(html).toContain('data-testid="sequence-section"')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('renders Sequence section with assembled true', () => {
    const project = {
      project_id: 'p-sequence-assembled',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'complete',
        sequence_status: {
          scenes: 2,
          shots: 4,
          assembled: true,
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Sequence')
    expect(html).toContain('Scenes: 2')
    expect(html).toContain('Shots: 4')
    expect(html).toContain('Assembled: true')
  })

  it('hides Sequence section when sequenceStatus is absent', () => {
    const project = {
      project_id: 'p-sequence-missing',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Sequence')
    expect(html).not.toContain('data-testid="sequence-section"')
  })
  it('renders Scene Playback section when present', () => {
    const project = {
      project_id: 'p-playback-present',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'complete',
        scene_playback_status: {
          playback_ready: true,
          scene_count: 5,
          shots_available: 12,
          status: 'ready',
        },
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Scene Playback')
    expect(html).toContain('Playback Ready: true')
    expect(html).toContain('Scenes: 5')
    expect(html).toContain('Shots Available: 12')
    expect(html).toContain('Status: ready')
  })
  it('hides Scene Playback section when absent', () => {
    const project = {
      project_id: 'p-playback-missing',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Scene Playback')
    expect(html).not.toContain('data-testid="scene-playback-section"')
  })

  it('renders Previs Room section when any previs data exists', () => {
    const project = {
      project_id: 'p-previs-room-present',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_scene_board: [
          { scene_id: 'scene_001', shot_count: 3, linked_refs: ['ref_1'] },
        ],
        previs_beat_shot_map: [
          { beat_id: 'beat_001', scene_id: 'scene_001', shots: ['shot_1', 'shot_2'] },
        ],
        previs_asset_map: [
          { asset_id: 'asset_001', scenes: ['scene_001'] },
        ],
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Previs Room')
    expect(html).toContain('data-testid="previs-room-section"')
    expect(html).toContain('Scenes: 1')
    expect(html).toContain('Beats: 1')
    expect(html).toContain('Asset Scenes: 1')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('renders Previs Room with scene board entries', () => {
    const project = {
      project_id: 'p-previs-scenes',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_scene_board: [
          { scene_id: 'scene_001', shot_count: 3, linked_refs: ['ref_1', 'ref_2'] },
          { scene_id: 'scene_002', shot_count: 5, linked_refs: ['ref_3'] },
        ],
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Previs Room')
    expect(html).toContain('Scenes: 2')
    expect(html).toContain('scene_id: scene_001 · shot_count: 3 · linked_refs: 2')
    expect(html).toContain('scene_id: scene_002 · shot_count: 5 · linked_refs: 1')
  })

  it('renders Previs Room with contract defaults when present', () => {
    const project = {
      project_id: 'p-previs-contract',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_scene_board: [
          { scene_id: 'scene_001', shot_count: 1, linked_refs: [] },
        ],
        previs_contract: {},
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Previs Room')
    expect(html).toContain('Mode: read_only')
    expect(html).toContain('Authority: none')
    expect(html).toContain('Execution: false')
  })

  it('hides Previs Room section when all previs data is absent', () => {
    const project = {
      project_id: 'p-previs-missing',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'queued',
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Previs Room')
    expect(html).not.toContain('data-testid="previs-room-section"')
  })

  it('hides Previs Room when only continuity map present (no scene board)', () => {
    const project = {
      project_id: 'p-previs-continuity-only',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_continuity_map: [
          { from_scene_id: 'scene_001', to_scene_id: 'scene_002', transition: 'cut' },
        ],
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('Previs Room')
  })

  it('is read-only with no interactive elements', () => {
    const project = {
      project_id: 'p-previs-readonly',
      execution_summary: {
        provider_name: 'simulated',
        lifecycle_state: 'in_progress',
        previs_scene_board: [
          { scene_id: 'scene_001', shot_count: 2, linked_refs: ['ref_1'] },
        ],
        previs_beat_shot_map: [
          { beat: 'setup', shot_count: 1, scene_id: 'scene_001' },
        ],
        previs_asset_map: [
          { asset_name: 'car', scene_ids: ['scene_001'] },
        ],
        previs_contract: {
          mode: 'flexible',
          authority: 'co-director',
          execution_enabled: false,
          scope: 'partial',
        },
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('keeps protected sections read-only in boundary regression payload', () => {
    const project = {
      project_id: 'p-phase199-protected-readonly',
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        provider_config_snapshot: {
          default_provider: 'mock',
          enabled_providers: ['mock'],
          quality_priority: 'cinematic_quality',
          real_providers_enabled: false,
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
        provider_credential_state: {
          provider: 'mock',
          enabled: true,
          credential_present: true,
          credential_source: 'none',
          reason: 'Mock provider does not require credentials',
        },
        provider_control_contract: {
          selection_mode: 'manual_only',
          auto_execution: false,
          execution_on_select: false,
          reason: 'Provider selection does not trigger execution',
        },
        provider_payload_v2: { provider: 'mock', shot_id: null, prompt: null },
        handoff_envelope: { request_id: 'handoff_mock_none', provider: 'mock', enabled: false },
        handoff_audit: {
          requested: true,
          allowed: false,
          blocked_reason: 'Execution permission denied',
          timestamp: null,
        },
        take_comparison_v2: { comparable: false, differences: [] },
        take_preference_contract: { auto_select: false, authority: 'manual_only' },
        output_review_matrix: [{ take_id: 1, alignment: 'none', coverage: '1/1', valid_structure: true }],
        previs_scene_board: [{ scene_id: 'scene_001', shot_count: 1, linked_refs: [] }],
        previs_contract: { mode: 'read_only', authority: 'none', execution_enabled: false },
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Provider Control')
    expect(html).toContain('Provider Handoff')
    expect(html).toContain('Take Review')
    expect(html).toContain('Previs Room')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('phase200 protected sections remain fully read-only', () => {
    const project = {
      project_id: 'p-phase200-protected-readonly',
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        provider_config_snapshot: {
          default_provider: 'mock',
          enabled_providers: ['mock'],
          quality_priority: 'cinematic_quality',
          real_providers_enabled: false,
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
        provider_control_contract: {
          selection_mode: 'manual_only',
          auto_execution: false,
          execution_on_select: false,
          reason: 'Provider selection does not trigger execution',
        },
        handoff_gate: {
          handoff_allowed: false,
          reason: 'Execution permission denied',
        },
        take_preference_contract: { auto_select: false, authority: 'manual_only' },
        output_review_matrix: [{ take_id: 1, alignment: 'none', coverage: '1/1', valid_structure: true }],
        previs_scene_board: [{ scene_id: 'scene_001', shot_count: 1, linked_refs: [] }],
        previs_contract: { mode: 'read_only', authority: 'none', execution_enabled: false },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Provider Control')
    expect(html).toContain('Provider Handoff')
    expect(html).toContain('Take Review')
    expect(html).toContain('Previs Room')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('derives mock_render_output from execution_result_v2 with safe defaults', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        provider_selection_state: {
          requested_provider: null,
          selected_provider: 'mock',
          allowed: true,
          fallback_used: false,
          reason: 'Default provider selected',
        },
        execution_result_v2: {
          executed: true,
          render_id: 'render_900',
          status: 'success',
        },
      },
    } as never
    const summary = extractExecutionSummaryInspection(project)
    expect(summary).not.toBeNull()
    expect(summary?.mockRenderOutput).toEqual({
      renderId: 'render_900',
      status: 'success',
      provider: 'mock',
      hasOutput: true,
    })
  })

  it('extracts local_render_output and local_artifact_log with null-safe defaults', () => {
    const withLocal = {
      execution_summary: {
        local_render_output: {
          has_output: true,
          render_id: 'local_shot_1',
          file_path: 'output/renders/local_shot_1.txt',
          artifact_type: 'text_preview',
          status: 'success',
        },
        local_artifact_log: {
          executed: true,
          shot_id: 'shot_1',
          file_path: 'output/renders/local_shot_1.txt',
          timestamp: null,
        },
      },
    } as never
    const malformed = {
      execution_summary: {
        local_render_output: {
          has_output: 'bad',
          render_id: 1,
          file_path: {},
        },
        local_artifact_log: {
          executed: 'bad',
          shot_id: {},
          file_path: [],
        },
      },
    } as never

    const parsed = extractExecutionSummaryInspection(withLocal)
    const malformedParsed = extractExecutionSummaryInspection(malformed)
    expect(parsed?.localRenderOutput).toEqual({
      hasOutput: true,
      renderId: 'local_shot_1',
      filePath: 'output/renders/local_shot_1.txt',
      artifactType: 'text_preview',
      status: 'success',
    })
    expect(parsed?.localArtifactLog).toEqual({
      executed: true,
      shotId: 'shot_1',
      filePath: 'output/renders/local_shot_1.txt',
      timestamp: null,
    })
    expect(malformedParsed?.localRenderOutput).toEqual({
      hasOutput: false,
      renderId: null,
      filePath: null,
      artifactType: null,
      status: 'not_executed',
    })
    expect(malformedParsed?.localArtifactLog).toEqual({
      executed: false,
      shotId: null,
      filePath: null,
      timestamp: null,
    })
  })

  it('safeReadFile reads text and handles missing files safely', async () => {
    const fetchMock = vi.fn()
    fetchMock.mockResolvedValueOnce({
      ok: true,
      text: async () => 'Local render preview for shot_1',
    })
    fetchMock.mockResolvedValueOnce({
      ok: false,
      text: async () => '',
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(safeReadFile('/output/renders/local_shot_1.txt')).resolves.toBe('Local render preview for shot_1')
    await expect(safeReadFile('/output/renders/missing.txt')).resolves.toBeNull()
    vi.unstubAllGlobals()
  })

  it('renders local artifact path, source strip, and file_path table columns', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: true,
          render_id: 'local_shot_1',
          status: 'success',
          provider: 'mock',
          meta: {
            file_path: null,
            url: null,
          },
        },
        local_render_output: {
          has_output: true,
          render_id: 'local_shot_1',
          file_path: 'output/renders/local_shot_1.txt',
          artifact_type: 'text_preview',
          status: 'success',
        },
        local_artifact_log: {
          executed: true,
          shot_id: 'shot_1',
          file_path: 'output/renders/local_shot_1.txt',
          timestamp: null,
        },
        shot_execution_ledger: [
          { shot_id: 'shot_1', scene_id: 'scene_1', status: 'complete', render_id: 'local_shot_1', file_path: 'output/renders/local_shot_1.txt' },
        ],
        take_artifacts: [
          { iteration: 1, render_id: 'local_shot_1', status: 'success', file_path: 'output/renders/local_shot_1.txt' },
        ],
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Source local')
    expect(html).toContain('Local Artifact: output/renders/local_shot_1.txt')
    expect(html).toContain('Render Label: Local Render')
    expect(html).toContain('Preview Content')
    expect(html).toContain('file_path')
    expect(html).toContain('output/renders/local_shot_1.txt')
    expect(html).toContain('Scene Preview Available')
    expect(html).toContain('Artifacts: 1')
  })

  it('shows preview placeholder when mock output is available', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        scene_intent: { type: 'intent_label', label: 'intent exists' },
        request_schema_validation: { valid: true },
        execution_eligibility: { eligible: true },
        provider_adapter_readiness_gate: { ready: true },
        provider_selection_state: {
          requested_provider: null,
          selected_provider: 'mock',
          allowed: true,
          fallback_used: false,
          reason: 'Default provider selected',
        },
        execution_result_v2: {
          executed: true,
          render_id: 'render_success',
          status: 'success',
        },
      },
    } as never
    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('No preview available')
    expect(html).toContain('Output Available: Yes')
    expect(html).toContain('Ready to Render: YES')
    expect(html).toContain('intent_present: true')
    expect(html).toContain('request_valid: true')
    expect(html).toContain('eligible: true')
    expect(html).toContain('blocked: false')
  })

  it('does not trigger provider execution or network calls while rendering', () => {
    const fetchSpy = vi.fn()
    ;(globalThis as { fetch?: unknown }).fetch = fetchSpy
    const project = {
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: false,
          render_id: null,
          status: 'not_executed',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Render Output')
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('ExecutionSummaryInspectionPanel Scene Generation', () => {
  it('extracts multi-shot scene generation fields safely', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        multi_shot_results: [
          {
            shot_id: 'shot_scene_001_001',
            scene_id: 'scene_001',
            render_id: 'mock_shot_scene_001_001',
            status: 'success',
            provider: 'mock',
          },
        ],
        multi_shot_execution_ledger: [
          { shot_id: 'shot_scene_001_001', status: 'complete', render_id: 'mock_shot_scene_001_001' },
        ],
        multi_shot_take_artifacts: [
          { iteration: 1, shot_id: 'shot_scene_001_001', render_id: 'mock_shot_scene_001_001', status: 'success' },
        ],
        scene_generation_summary: {
          planned_shots: 1,
          completed_shots: 1,
          provider: 'mock',
          status: 'complete',
        },
        scene_playback_preview: {
          available: true,
          shot_count: 1,
          render_ids: ['mock_shot_scene_001_001'],
          status: 'complete',
        },
        multi_shot_execution_contract: {
          provider: 'mock_only',
          max_shots_per_run: 3,
          real_providers_enabled: false,
          retries_enabled: false,
          async_enabled: false,
          reason: 'Multi-shot execution is mock-only and bounded',
        },
      },
    } as never

    const inspection = extractExecutionSummaryInspection(project)
    expect(inspection?.multiShotResults?.length).toBe(1)
    expect(inspection?.multiShotExecutionLedger?.length).toBe(1)
    expect(inspection?.multiShotTakeArtifacts?.length).toBe(1)
    expect(inspection?.sceneGenerationSummary?.status).toBe('complete')
    expect(inspection?.scenePlaybackPreview?.available).toBe(true)
    expect(inspection?.multiShotExecutionContract?.provider).toBe('mock_only')
  })

  it('suppresses malformed multi-shot scene generation fields safely', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        multi_shot_results: [{ shot_id: 1, scene_id: null, render_id: {}, status: [], provider: false }],
        multi_shot_execution_ledger: [{ shot_id: 1, status: null, render_id: {} }],
        multi_shot_take_artifacts: [{ iteration: 'x', shot_id: 1, render_id: null, status: false }],
        scene_generation_summary: { planned_shots: 'x', completed_shots: -1, provider: null, status: 'bad' },
        scene_playback_preview: { available: 'yes', shot_count: 'x', render_ids: [1], status: null },
        multi_shot_execution_contract: {
          provider: 'bad',
          max_shots_per_run: 'x',
          real_providers_enabled: 'false',
          retries_enabled: null,
          async_enabled: [],
          reason: null,
        },
      },
    } as never

    const inspection = extractExecutionSummaryInspection(project)
    expect(inspection?.multiShotResults).toEqual([])
    expect(inspection?.multiShotExecutionLedger).toEqual([])
    expect(inspection?.multiShotTakeArtifacts).toEqual([])
    expect(inspection?.sceneGenerationSummary).toBeUndefined()
    expect(inspection?.scenePlaybackPreview).toBeUndefined()
    expect(inspection?.multiShotExecutionContract).toBeUndefined()
  })

  it('renders scene generation section, playback table, and preview box states in read-only mode', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        scene_generation_summary: {
          planned_shots: 2,
          completed_shots: 2,
          provider: 'mock',
          status: 'complete',
        },
        scene_playback_preview: {
          available: true,
          shot_count: 2,
          render_ids: ['mock_shot_1', 'mock_shot_2'],
          status: 'complete',
        },
        multi_shot_results: [
          { shot_id: 'shot_1', scene_id: 'scene_1', render_id: 'mock_shot_1', status: 'success', provider: 'mock' },
          { shot_id: 'shot_2', scene_id: 'scene_1', render_id: 'mock_shot_2', status: 'success', provider: 'mock' },
        ],
        multi_shot_execution_ledger: [
          { shot_id: 'shot_1', status: 'complete', render_id: 'mock_shot_1' },
          { shot_id: 'shot_2', status: 'complete', render_id: 'mock_shot_2' },
        ],
        multi_shot_take_artifacts: [
          { iteration: 1, shot_id: 'shot_1', render_id: 'mock_shot_1', status: 'success' },
          { iteration: 2, shot_id: 'shot_2', render_id: 'mock_shot_2', status: 'success' },
        ],
        multi_shot_execution_contract: {
          provider: 'mock_only',
          max_shots_per_run: 3,
          real_providers_enabled: false,
          retries_enabled: false,
          async_enabled: false,
          reason: 'Multi-shot execution is mock-only and bounded',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('data-testid="studio-scene-status-strip"')
    expect(html).toContain('>Scene</span>')
    expect(html).toContain('Shots 2/2')
    expect(html).toContain('Preview yes')
    expect(html).toContain('Scene Generation')
    expect(html).toContain('Planned Shots: 2')
    expect(html).toContain('Completed Shots: 2')
    expect(html).toContain('Render IDs Count: 2')
    expect(html).toContain('data-testid="shot-playback-table-section"')
    expect(html).toContain('shot_id')
    expect(html).toContain('render_id')
    expect(html).toContain('provider')
    expect(html).toContain('mock_shot_1')
    expect(html).toContain('data-testid="scene-playback-preview-box"')
    expect(html).toContain('No scene preview available')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('renders unavailable preview and empty playback table safely', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        lifecycle_state: 'ready',
        scene_generation_summary: {
          planned_shots: 0,
          completed_shots: 0,
          provider: 'mock',
          status: 'not_started',
        },
        scene_playback_preview: {
          available: false,
          shot_count: 0,
          render_ids: [],
          status: 'not_started',
        },
        multi_shot_results: [],
        multi_shot_execution_contract: {
          provider: 'mock_only',
          max_shots_per_run: 3,
          real_providers_enabled: false,
          retries_enabled: false,
          async_enabled: false,
          reason: 'Multi-shot execution is mock-only and bounded',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Scene Generation')
    expect(html).toContain('No scene preview available')
    expect(html).toContain('No data available')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })

  it('renders real image when execution_result_v2 meta file_path is present', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: true,
          render_id: 'render_real_1',
          status: 'success',
          provider: 'real_stub',
          meta: {
            file_path: '/renders/real/output-1.png',
            url: '/renders/real/output-1.png',
          },
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Render Label: Real Render')
    expect(html).toContain('alt="render preview"')
    expect(html).toContain('source: real')
  })

  it('falls back to local render path when real image is absent', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: false,
          render_id: null,
          status: 'not_executed',
        },
        local_render_output: {
          has_output: true,
          render_id: 'local_1',
          file_path: '/renders/local/output-1.txt',
          artifact_type: 'text',
          status: 'complete',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Render Label: Local Render')
    expect(html).toContain('Local Artifact: /renders/local/output-1.txt')
    expect(html).toContain('Local preview path: /renders/local/output-1.txt')
  })

  it('falls back to mock render when no real or local output exists', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: false,
          render_id: null,
          status: 'not_executed',
          provider: 'mock',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Render Label: Mock Render')
    expect(html).toContain('Mock render output available')
  })

  it('renders certification panel and failed error text safely', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: true,
          render_id: 'render_failed_1',
          status: 'failed',
          provider: 'real_stub',
          meta: {
            file_path: '/renders/real/failed.png',
            url: '/renders/real/failed.png',
          },
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).toContain('Render Certification')
    expect(html).toContain('executed: true')
    expect(html).toContain('provider: real_stub')
    expect(html).toContain('Error: Render failed')
  })

  it('resolveRenderSource prioritizes real then local then mock', () => {
    const realSummary = extractExecutionSummaryInspection({
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: true,
          render_id: 'render_real',
          status: 'success',
          meta: { file_path: '/real/path.png', url: '/real/path.png' },
        },
        local_render_output: {
          has_output: true,
          render_id: 'render_local',
          file_path: '/local/path.png',
          artifact_type: 'image',
          status: 'complete',
        },
      },
    } as never)
    const localSummary = extractExecutionSummaryInspection({
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: false,
          render_id: null,
          status: 'not_executed',
        },
        local_render_output: {
          has_output: true,
          render_id: 'render_local',
          file_path: '/local/path.png',
          artifact_type: 'image',
          status: 'complete',
        },
      },
    } as never)
    const mockSummary = extractExecutionSummaryInspection({
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: false,
          render_id: null,
          status: 'not_executed',
          provider: 'mock',
        },
      },
    } as never)

    expect(resolveRenderSource(realSummary).source).toBe('real')
    expect(resolveRenderSource(localSummary).source).toBe('local')
    expect(resolveRenderSource(mockSummary).source).toBe('mock')
  })

  it('safeImageSrc rejects invalid inputs and stays null-safe', () => {
    expect(safeImageSrc(null)).toBeNull()
    expect(safeImageSrc('')).toBeNull()
    expect(safeImageSrc('javascript:alert(1)')).toBeNull()
    expect(safeImageSrc('/renders/real/image.png')).toBe('/renders/real/image.png')
  })

  it('keeps panel read-only with no interactive elements', () => {
    const project = {
      execution_summary: {
        provider_name: 'mock',
        execution_result_v2: {
          executed: false,
          render_id: null,
          status: 'not_executed',
        },
      },
    } as never

    const html = renderToStaticMarkup(<ExecutionSummaryInspectionPanel project={project} />)
    expect(html).not.toContain('<button')
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<select')
    expect(html).not.toContain('<textarea')
    expect(html).not.toContain('<a ')
  })
})

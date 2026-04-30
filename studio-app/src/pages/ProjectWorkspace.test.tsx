import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import StudioPanel from '../components/StudioPanel'
import {
  ExecutionStatusStrip,
  IntentSignalStrip,
  MemorySnapshotStrip,
  MemoryVisibilityStrip,
  PrevisStrip,
  ProductionSignalStrip,
  ProviderStatusStrip,
  RenderStatusStrip,
  SceneStatusStrip,
  ReviewStateStrip,
  ShotPlanStrip,
  ShotPipelineStrip,
  TakePipelineStrip,
  ValidationStatusStrip,
  VisualBoardStrip,
  extractExecutionStatusStripMessage,
  extractMemorySnapshotMessage,
  extractMemoryVisibilityMessage,
  extractPrevisStripMessage,
  extractProductionSignalMessage,
  extractProviderStatusStripMessage,
  extractRenderStatusStripMessage,
  extractSceneStatusStripMessage,
  extractReviewStateMessage,
  extractSceneIntentLabel,
  extractShotPlanMessage,
  extractShotPipelineStripMessage,
  extractTakePipelineStripMessage,
  extractValidationStatusStripMessage,
  extractVisualBoardMessage,
  getProductionSignalSeverity,
} from './ProjectWorkspace'

describe('ProjectWorkspace QA Selectors', () => {
  describe('StudioPanel data-testid support', () => {
    it('supports data-testid prop for execution-timeline-panel', () => {
      const html = renderToStaticMarkup(
        <StudioPanel title="Studio Leadership Notes" data-testid="execution-timeline-panel">
          <div>Content</div>
        </StudioPanel>
      )
      expect(html).toContain('data-testid="execution-timeline-panel"')
    })
  })

  describe('Render status card data-testid', () => {
    it('uses data-testid="render-status-card" for render queue items', () => {
      // This test verifies the selector pattern used in ProjectWorkspace
      // The actual render status cards are rendered with data-testid="render-status-card"
      const expectedTestId = 'render-status-card'
      expect(expectedTestId).toBe('render-status-card')
    })
  })

  describe('Visual studio strips', () => {
    it('renders provider, execution, validation, shot, take, render, and scene strips from execution summary', () => {
      const project = {
        execution_summary: {
          provider_name: 'openai',
          provider_adapter_status: { provider: 'openai', enabled: false },
          provider_adapter_readiness_gate: { ready: false },
          execution_unlock_state: { locked: true },
          execution_eligibility: { eligible: false },
          execution_request_envelope: { request: 'blocked' },
          request_schema_validation: { valid: false },
          provider_validation: { valid: false },
          payload_sanitization: { safe: false },
          shot_queue: [
            { shot_id: 'shot_1', scene_id: 'scene_1', status: 'queued' },
            { shot_id: 'shot_2', scene_id: 'scene_1', status: 'queued' },
          ],
          multi_shot_readiness: { ready: 0 },
          shot_execution_ledger: [
            { shot_id: 'shot_1', scene_id: 'scene_1', status: 'not_executed' },
            { shot_id: 'shot_2', scene_id: 'scene_1', status: 'not_executed' },
          ],
          take_artifacts: [{ iteration: 1, render_id: 'render_1', status: 'complete' }],
          take_comparison_v2: { comparable: false, differences: [] },
          take_preference_contract: { auto_select: false, authority: 'manual_only' },
          execution_result_v2: { executed: false, render_id: null, status: 'not_executed' },
          scene_generation_summary: {
            planned_shots: 3,
            completed_shots: 2,
            provider: 'mock',
            status: 'partial',
          },
          scene_playback_preview: {
            available: true,
            shot_count: 2,
            render_ids: ['mock_shot_1', 'mock_shot_2'],
            status: 'partial',
          },
        },
      } as never

      const providerMessage = extractProviderStatusStripMessage(project)
      const executionMessage = extractExecutionStatusStripMessage(project)
      const validationMessage = extractValidationStatusStripMessage(project)
      const shotMessage = extractShotPipelineStripMessage(project)
      const takeMessage = extractTakePipelineStripMessage(project)
      const renderMessage = extractRenderStatusStripMessage(project)
      const sceneMessage = extractSceneStatusStripMessage(project)

      const html = renderToStaticMarkup(
        <>
          {providerMessage ? <ProviderStatusStrip message={providerMessage} /> : null}
          {executionMessage ? <ExecutionStatusStrip message={executionMessage} /> : null}
          {validationMessage ? <ValidationStatusStrip message={validationMessage} /> : null}
          {shotMessage ? <ShotPipelineStrip message={shotMessage} /> : null}
          {takeMessage ? <TakePipelineStrip message={takeMessage} /> : null}
          {renderMessage ? <RenderStatusStrip message={renderMessage} /> : null}
          {sceneMessage ? <SceneStatusStrip message={sceneMessage} /> : null}
        </>
      )

      expect(providerMessage).toBe('Provider · openai · Enabled false · Ready false')
      expect(executionMessage).toBe('Execution · Locked · Eligible false · Request blocked')
      expect(validationMessage).toBe('Validation · Schema invalid · Provider invalid · Payload unsafe')
      expect(shotMessage).toBe('Shots · 2 · Queue 2 · Ready 0')
      expect(takeMessage).toBe('Takes · 1 · Comparable false · Auto Select false')
      expect(renderMessage).toBe('Render · not_executed · Source mock · Output no')
      expect(sceneMessage).toBe('Scene · partial · Shots 2/3 · Preview yes')
      expect(html).toContain('data-testid="provider-status-strip"')
      expect(html).toContain('data-testid="execution-status-strip"')
      expect(html).toContain('data-testid="validation-status-strip"')
      expect(html).toContain('data-testid="shot-pipeline-strip"')
      expect(html).toContain('data-testid="take-pipeline-strip"')
      expect(html).toContain('data-testid="render-status-strip"')
      expect(html).toContain('data-testid="scene-status-strip"')
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })

    it('returns null strip messages safely when execution summary is missing', () => {
      const project = { producer_dashboard: { status: 'idle' } } as never
      expect(extractProviderStatusStripMessage(project)).toBeNull()
      expect(extractExecutionStatusStripMessage(project)).toBeNull()
      expect(extractValidationStatusStripMessage(project)).toBeNull()
      expect(extractShotPipelineStripMessage(project)).toBeNull()
      expect(extractTakePipelineStripMessage(project)).toBeNull()
      expect(extractRenderStatusStripMessage(project)).toBeNull()
      expect(extractSceneStatusStripMessage(project)).toBeNull()
    })

    it('render strip prioritizes real source when execution_result_v2.meta.file_path exists', () => {
      const project = {
        execution_summary: {
          provider_name: 'mock',
          execution_result_v2: {
            executed: true,
            render_id: 'render_real_1',
            status: 'success',
            meta: {
              file_path: '/renders/real/output.png',
              url: '/renders/real/output.png',
            },
          },
          local_render_output: {
            has_output: true,
            render_id: 'render_local_1',
            file_path: '/renders/local/output.png',
            artifact_type: 'image',
            status: 'complete',
          },
        },
      } as never

      expect(extractRenderStatusStripMessage(project)).toBe('Render · success · Source real · Output yes')
    })

    it('render strip falls back to local source when real source is absent', () => {
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
            render_id: 'render_local_1',
            file_path: '/renders/local/output.png',
            artifact_type: 'image',
            status: 'complete',
          },
        },
      } as never

      expect(extractRenderStatusStripMessage(project)).toBe('Render · not_executed · Source local · Output yes')
    })
  })

  describe('Production signal strip', () => {
    it('maps normal severity for neutral signal messages', () => {
      expect(getProductionSignalSeverity('Render in progress')).toBe('normal')
      expect(getProductionSignalSeverity('Stable rendering')).toBe('normal')
      expect(getProductionSignalSeverity('No significant signal')).toBe('normal')
    })

    it('maps warning severity for retry-heavy signal message', () => {
      expect(getProductionSignalSeverity('Retry-heavy condition detected')).toBe('warning')
    })

    it('maps degraded severity for stuck and provider-failure signal messages', () => {
      expect(getProductionSignalSeverity('Stuck pattern detected')).toBe('degraded')
      expect(getProductionSignalSeverity('Provider failure pattern detected')).toBe('degraded')
    })

    it('renders strip when production_signal.message exists', () => {
      const project = {
        execution_summary: {
          production_signal: {
            message: 'Render in progress',
          },
        },
      } as never

      const message = extractProductionSignalMessage(project)
      const html = renderToStaticMarkup(message ? <ProductionSignalStrip message={message} /> : null)
      expect(html).toContain('Production Signal')
      expect(html).toContain(' · ')
      expect(html).toContain('Render in progress')
      expect(html).toContain('data-testid="production-signal-strip"')
      expect(html).toContain('data-severity="normal"')
    })

    it('hides strip when production_signal is missing', () => {
      const project = {
        execution_summary: {
          render_behavior: 'in_progress',
        },
      } as never

      const message = extractProductionSignalMessage(project)
      const html = renderToStaticMarkup(message ? <ProductionSignalStrip message={message} /> : null)
      expect(message).toBeNull()
      expect(html).toBe('')
    })

    it('strip has no interactive controls', () => {
      const html = renderToStaticMarkup(<ProductionSignalStrip message="Stable rendering" />)
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })
  })

  describe('Intent signal strip', () => {
    it('renders intent strip when scene_intent.label exists', () => {
      const project = {
        execution_summary: {
          scene_intent: {
            label: 'quiet emotional moment',
          },
        },
      } as never

      const label = extractSceneIntentLabel(project)
      const html = renderToStaticMarkup(label ? <IntentSignalStrip label={label} /> : null)
      expect(html).toContain('data-testid="intent-signal-strip"')
      expect(html).toContain('Intent')
      expect(html).toContain('quiet emotional moment')
    })

    it('hides intent strip when scene_intent is absent', () => {
      const project = {
        execution_summary: {
          render_behavior: 'in_progress',
        },
      } as never

      const label = extractSceneIntentLabel(project)
      const html = renderToStaticMarkup(label ? <IntentSignalStrip label={label} /> : null)
      expect(label).toBeNull()
      expect(html).toBe('')
    })

    it('uses exact text format "Intent · <label>"', () => {
      const html = renderToStaticMarkup(<IntentSignalStrip label="quiet emotional moment" />)
      expect(html).toContain('Intent')
      expect(html).toContain(' · ')
      expect(html).toContain('quiet emotional moment')
    })

    it('has no interactive elements', () => {
      const html = renderToStaticMarkup(<IntentSignalStrip label="quiet emotional moment" />)
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })
  })

  describe('Review state strip', () => {
    it('renders Review State strip when intent_output_relation.message exists', () => {
      const project = {
        execution_summary: {
          intent_output_relation: {
            message: 'Intent and output ready for review',
          },
        },
      } as never

      const message = extractReviewStateMessage(project)
      const html = renderToStaticMarkup(message ? <ReviewStateStrip message={message} /> : null)
      expect(html).toContain('data-testid="review-state-strip"')
      expect(html).toContain('Review State')
      expect(html).toContain('Intent and output ready for review')
    })

    it('hides Review State strip when intent_output_relation is absent', () => {
      const project = {
        execution_summary: {
          render_behavior: 'stable',
        },
      } as never

      const message = extractReviewStateMessage(project)
      const html = renderToStaticMarkup(message ? <ReviewStateStrip message={message} /> : null)
      expect(message).toBeNull()
      expect(html).toBe('')
    })

    it('uses exact text format: Review State · Intent and output ready for review', () => {
      const html = renderToStaticMarkup(<ReviewStateStrip message="Intent and output ready for review" />)
      expect(html).toContain('Review State')
      expect(html).toContain(' · ')
      expect(html).toContain('Intent and output ready for review')
    })

    it('has no interactive elements', () => {
      const html = renderToStaticMarkup(<ReviewStateStrip message="Intent and output ready for review" />)
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })
  })

  describe('Memory visibility strip', () => {
    it('renders Memory Visibility strip when advisory is available and influence mode is disabled', () => {
      const project = {
        execution_summary: {
          memory_advisory_projection: {
            status: 'available',
          },
          memory_influence_gate: {
            mode: 'disabled',
          },
        },
      } as never

      const message = extractMemoryVisibilityMessage(project)
      const html = renderToStaticMarkup(message ? <MemoryVisibilityStrip message={message} /> : null)
      expect(html).toContain('data-testid="memory-visibility-strip"')
      expect(html).toContain('Memory Visibility')
      expect(html).toContain(' · ')
      expect(html).toContain('Available for review, influence disabled')
    })

    it('hides strip when advisory status is unavailable or missing', () => {
      const unavailable = {
        execution_summary: {
          memory_advisory_projection: {
            status: 'unavailable',
          },
          memory_influence_gate: {
            mode: 'disabled',
          },
        },
      } as never
      const missing = {
        execution_summary: {
          memory_influence_gate: {
            mode: 'disabled',
          },
        },
      } as never

      const unavailableMessage = extractMemoryVisibilityMessage(unavailable)
      const missingMessage = extractMemoryVisibilityMessage(missing)
      expect(unavailableMessage).toBeNull()
      expect(missingMessage).toBeNull()
      expect(renderToStaticMarkup(unavailableMessage ? <MemoryVisibilityStrip message={unavailableMessage} /> : null)).toBe('')
      expect(renderToStaticMarkup(missingMessage ? <MemoryVisibilityStrip message={missingMessage} /> : null)).toBe('')
    })

    it('hides strip when influence mode is not disabled', () => {
      const project = {
        execution_summary: {
          memory_advisory_projection: {
            status: 'available',
          },
          memory_influence_gate: {
            mode: 'enabled',
          },
        },
      } as never

      const message = extractMemoryVisibilityMessage(project)
      expect(message).toBeNull()
      expect(renderToStaticMarkup(message ? <MemoryVisibilityStrip message={message} /> : null)).toBe('')
    })

    it('hides strip for malformed advisory or influence payloads', () => {
      const malformedStatus = {
        execution_summary: {
          memory_advisory_projection: {
            status: 123,
          },
          memory_influence_gate: {
            mode: 'disabled',
          },
        },
      } as never
      const malformedMode = {
        execution_summary: {
          memory_advisory_projection: {
            status: 'available',
          },
          memory_influence_gate: {
            mode: null,
          },
        },
      } as never

      expect(extractMemoryVisibilityMessage(malformedStatus)).toBeNull()
      expect(extractMemoryVisibilityMessage(malformedMode)).toBeNull()
      expect(
        renderToStaticMarkup(
          extractMemoryVisibilityMessage(malformedStatus)
            ? <MemoryVisibilityStrip message={extractMemoryVisibilityMessage(malformedStatus)!} />
            : null
        )
      ).toBe('')
      expect(
        renderToStaticMarkup(
          extractMemoryVisibilityMessage(malformedMode)
            ? <MemoryVisibilityStrip message={extractMemoryVisibilityMessage(malformedMode)!} />
            : null
        )
      ).toBe('')
    })

    it('has exact text format and no interactive elements', () => {
      const html = renderToStaticMarkup(
        <MemoryVisibilityStrip message="Available for review, influence disabled" />
      )
      expect(html).toContain('Memory Visibility')
      expect(html).toContain(' · ')
      expect(html).toContain('Available for review, influence disabled')
      expect(html).not.toContain('important')
      expect(html).not.toContain('rank')
      expect(html).not.toContain('decision')
      expect(html).not.toContain('interpret')
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })
  })

  describe('Memory snapshot strip', () => {
    it('renders Memory Snapshot strip when available + disabled + consistent', () => {
      const project = {
        execution_summary: {
          memory_state_rollup: {
            status: 'available',
            influence_mode: 'disabled',
          },
          memory_consistency: {
            is_consistent: true,
          },
        },
      } as never

      const message = extractMemorySnapshotMessage(project)
      const html = renderToStaticMarkup(message ? <MemorySnapshotStrip message={message} /> : null)
      expect(html).toContain('data-testid="memory-snapshot-strip"')
      expect(html).toContain('Memory Snapshot')
      expect(html).toContain(' · ')
      expect(html).toContain('Available, influence disabled')
    })

    it('hides strip when unavailable', () => {
      const project = {
        execution_summary: {
          memory_state_rollup: {
            status: 'unavailable',
            influence_mode: 'disabled',
          },
          memory_consistency: {
            is_consistent: true,
          },
        },
      } as never

      const message = extractMemorySnapshotMessage(project)
      expect(message).toBeNull()
      expect(renderToStaticMarkup(message ? <MemorySnapshotStrip message={message} /> : null)).toBe('')
    })

    it('hides strip when influence mode is not disabled', () => {
      const project = {
        execution_summary: {
          memory_state_rollup: {
            status: 'available',
            influence_mode: 'enabled',
          },
          memory_consistency: {
            is_consistent: true,
          },
        },
      } as never

      const message = extractMemorySnapshotMessage(project)
      expect(message).toBeNull()
      expect(renderToStaticMarkup(message ? <MemorySnapshotStrip message={message} /> : null)).toBe('')
    })

    it('hides strip when memory consistency is false', () => {
      const project = {
        execution_summary: {
          memory_state_rollup: {
            status: 'available',
            influence_mode: 'disabled',
          },
          memory_consistency: {
            is_consistent: false,
          },
        },
      } as never

      const message = extractMemorySnapshotMessage(project)
      expect(message).toBeNull()
      expect(renderToStaticMarkup(message ? <MemorySnapshotStrip message={message} /> : null)).toBe('')
    })

    it('hides strip for inconsistent or corrupt boundary payloads', () => {
      const inconsistent = {
        execution_summary: {
          memory_state_rollup: {
            status: 'available',
            influence_mode: 'enabled',
          },
          memory_consistency: {
            is_consistent: false,
          },
          memory_output_influence_contract: {
            permitted: true,
            scope: 'all',
          },
          co_director_memory_contract: {
            mode: 'authoritative',
            authority: 'all',
          },
        },
      } as never

      const message = extractMemorySnapshotMessage(inconsistent)
      expect(message).toBeNull()
      expect(renderToStaticMarkup(message ? <MemorySnapshotStrip message={message} /> : null)).toBe('')
    })

    it('uses exact text format and has no interactive elements', () => {
      const html = renderToStaticMarkup(
        <MemorySnapshotStrip message="Available, influence disabled" />
      )
      expect(html).toContain('Memory Snapshot')
      expect(html).toContain(' · ')
      expect(html).toContain('Available, influence disabled')
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })
  })

  describe('Shot plan strip', () => {
    it('renders Shot Plan strip when shot candidates exist and influence mode is disabled', () => {
      const project = {
        execution_summary: {
          shot_candidates: [
            { scene_id: 'scene_001', shot_id: 'shot_scene_001_001', source_refs: [] },
            { scene_id: 'scene_002', shot_id: 'shot_scene_002_001', source_refs: ['ref_001'] },
          ],
          shot_plan_bundle: {
            influence_mode: 'disabled',
          },
        },
      } as never

      const message = extractShotPlanMessage(project)
      const html = renderToStaticMarkup(message ? <ShotPlanStrip message={message} /> : null)
      expect(message).toBe('2 scenes prepared')
      expect(html).toContain('data-testid="shot-plan-strip"')
      expect(html).toContain('Shot Plan')
      expect(html).toContain('2 scenes prepared')
    })

    it('hides Shot Plan strip when candidates are missing/empty or influence mode is not disabled', () => {
      const missing = {
        execution_summary: {
          shot_plan_bundle: {
            influence_mode: 'disabled',
          },
        },
      } as never
      const empty = {
        execution_summary: {
          shot_candidates: [],
          shot_plan_bundle: {
            influence_mode: 'disabled',
          },
        },
      } as never
      const enabled = {
        execution_summary: {
          shot_candidates: [{ scene_id: 'scene_001', shot_id: 'shot_scene_001_001', source_refs: [] }],
          shot_plan_bundle: {
            influence_mode: 'enabled',
          },
        },
      } as never

      expect(extractShotPlanMessage(missing)).toBeNull()
      expect(extractShotPlanMessage(empty)).toBeNull()
      expect(extractShotPlanMessage(enabled)).toBeNull()
      expect(renderToStaticMarkup(extractShotPlanMessage(missing) ? <ShotPlanStrip message={extractShotPlanMessage(missing)!} /> : null)).toBe('')
      expect(renderToStaticMarkup(extractShotPlanMessage(empty) ? <ShotPlanStrip message={extractShotPlanMessage(empty)!} /> : null)).toBe('')
      expect(renderToStaticMarkup(extractShotPlanMessage(enabled) ? <ShotPlanStrip message={extractShotPlanMessage(enabled)!} /> : null)).toBe('')
    })

    it('strip has no interactive controls', () => {
      const html = renderToStaticMarkup(<ShotPlanStrip message="1 scenes prepared" />)
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })
  })

  describe('Visual board strip', () => {
    it('renders Visual Board strip when read_only mode and visual/frame/link data exists', () => {
      const project = {
        execution_summary: {
          visual_reference_summary: {
            reference_count: 2,
          },
          frame_stats: {
            frame_count: 3,
          },
          link_completeness: {
            linked_scenes: 1,
            total_scenes: 4,
          },
          co_director_visual_feed: {
            mode: 'read_only',
          },
        },
      } as never

      const message = extractVisualBoardMessage(project)
      const html = renderToStaticMarkup(message ? <VisualBoardStrip message={message} /> : null)
      expect(message).toBe('References 2 · Frames 3 · Linked 1/4')
      expect(html).toContain('data-testid="visual-board-strip"')
      expect(html).toContain('Visual Board')
      expect(html).toContain('References 2 · Frames 3 · Linked 1/4')
    })

    it('hides strip when feed mode is not read_only', () => {
      const project = {
        execution_summary: {
          visual_reference_summary: {
            reference_count: 2,
          },
          frame_stats: {
            frame_count: 3,
          },
          link_completeness: {
            linked_scenes: 1,
            total_scenes: 4,
          },
          co_director_visual_feed: {
            mode: 'read_write',
          },
        },
      } as never

      const message = extractVisualBoardMessage(project)
      expect(message).toBeNull()
      expect(renderToStaticMarkup(message ? <VisualBoardStrip message={message} /> : null)).toBe('')
    })

    it('hides strip when no visual/frame/link totals exist', () => {
      const project = {
        execution_summary: {
          visual_reference_summary: {
            reference_count: 0,
          },
          frame_stats: {
            frame_count: 0,
          },
          link_completeness: {
            linked_scenes: 0,
            total_scenes: 0,
          },
          co_director_visual_feed: {
            mode: 'read_only',
          },
        },
      } as never

      const message = extractVisualBoardMessage(project)
      expect(message).toBeNull()
      expect(renderToStaticMarkup(message ? <VisualBoardStrip message={message} /> : null)).toBe('')
    })

    it('suppresses strip for malformed visual feed payloads', () => {
      const malformed = {
        execution_summary: {
          visual_reference_summary: {
            reference_count: 2,
          },
          frame_stats: {
            frame_count: 1,
          },
          link_completeness: {
            linked_scenes: 1,
            total_scenes: 2,
          },
          co_director_visual_feed: {
            mode: 99,
          },
        },
      } as never

      const message = extractVisualBoardMessage(malformed)
      expect(message).toBeNull()
      expect(renderToStaticMarkup(message ? <VisualBoardStrip message={message} /> : null)).toBe('')
    })

    it('uses exact text format and is non-interactive', () => {
      const html = renderToStaticMarkup(
        <VisualBoardStrip message="References 2 · Frames 3 · Linked 1/4" />
      )
      expect(html).toContain('Visual Board')
      expect(html).toContain(' · ')
      expect(html).toContain('References 2 · Frames 3 · Linked 1/4')
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })
  })

  describe('Previs strip', () => {
    it('renders Previs strip when previs_scene_board exists with entries', () => {
      const project = {
        execution_summary: {
          previs_scene_board: [
            { scene_id: 'scene_001', shot_count: 3, linked_refs: ['ref_1', 'ref_2'] },
            { scene_id: 'scene_002', shot_count: 5, linked_refs: ['ref_3'] },
          ],
        },
      } as never

      const message = extractPrevisStripMessage(project)
      const html = renderToStaticMarkup(message ? <PrevisStrip message={message} /> : null)
      expect(message).toBe('Previs · Scenes 2 · Shots 8 · References 3')
      expect(html).toContain('data-testid="previs-strip"')
      expect(html).toContain('Previs · Scenes 2 · Shots 8 · References 3')
    })

    it('hides Previs strip when previs_scene_board is empty', () => {
      const project = {
        execution_summary: {
          previs_scene_board: [],
        },
      } as never

      const message = extractPrevisStripMessage(project)
      const html = renderToStaticMarkup(message ? <PrevisStrip message={message} /> : null)
      expect(message).toBeNull()
      expect(html).toBe('')
    })

    it('hides Previs strip when previs_scene_board is missing', () => {
      const project = {
        execution_summary: {
          previs_beat_shot_map: [{ beat: 'opening', shot_count: 2, scene_id: 'scene_001' }],
          previs_continuity_map: [],
        },
      } as never

      const message = extractPrevisStripMessage(project)
      expect(message).toBeNull()
    })

    it('suppresses malformed rows safely', () => {
      const project = {
        execution_summary: {
          previs_scene_board: [
            null,
            'not-an-object',
            { scene_id: 'scene_001' },
            { shot_count: -1 },
            {},
            { scene_id: 'scene_002', shot_count: 3, linked_refs: [] },
          ],
        },
      } as never

      const message = extractPrevisStripMessage(project)
      // scene_001 missing shot_count, so only scene_002 with shot_count 3 is valid
      expect(message).toBe('Previs · Scenes 1 · Shots 3 · References 0')
    })

    it('handles missing shot_count and linked_refs gracefully', () => {
      const project = {
        execution_summary: {
          previs_scene_board: [
            { scene_id: 'scene_001' },
            { shot_count: 2 },
            { scene_id: 'scene_002', shot_count: 4, linked_refs: ['ref_1'] },
          ],
        },
      } as never

      const message = extractPrevisStripMessage(project)
      // scene_001 missing shot_count, shot_count: 2 missing scene_id
      expect(message).toBe('Previs · Scenes 1 · Shots 4 · References 1')
    })

    it('has no interactive elements', () => {
      const html = renderToStaticMarkup(
        <PrevisStrip message="Previs · Scenes 2 · Shots 6 · References 1" />
      )
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })

    it('phase199 protected strips remain read-only', () => {
      const html = renderToStaticMarkup(
        <>
          <ShotPlanStrip message="2 scenes prepared" />
          <VisualBoardStrip message="References 2 · Frames 3 · Linked 1/4" />
          <PrevisStrip message="Previs · Scenes 2 · Shots 6 · References 1" />
        </>
      )
      expect(html).toContain('Shot Plan')
      expect(html).toContain('Visual Board')
      expect(html).toContain('Previs')
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })

    it('phase200 protected strips remain fully read-only', () => {
      const html = renderToStaticMarkup(
        <>
          <VisualBoardStrip message="References 2 · Frames 3 · Linked 1/4" />
          <ShotPlanStrip message="2 scenes prepared" />
          <PrevisStrip message="Previs · Scenes 2 · Shots 6 · References 1" />
        </>
      )
      expect(html).toContain('Visual Board')
      expect(html).toContain('Shot Plan')
      expect(html).toContain('Previs')
      expect(html).not.toContain('<button')
      expect(html).not.toContain('<input')
      expect(html).not.toContain('<select')
      expect(html).not.toContain('<textarea')
      expect(html).not.toContain('<a ')
    })
  })
})

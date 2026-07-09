import { describe, expect, it } from 'vitest'

import { isProductionRecoveryContractError, shouldAutoRecoverProductionBoard } from './useProductionRecovery'

describe('isProductionRecoveryContractError', () => {
  it('detects known backend contract method gaps', () => {
    expect(isProductionRecoveryContractError("'DatabaseStorage' object has no attribute 'list_render_jobs'"))
      .toBe(true)
    expect(isProductionRecoveryContractError("'DatabaseStorage' object has no attribute 'list_reviews'"))
      .toBe(true)
  })

  it('does not flag unrelated errors', () => {
    expect(isProductionRecoveryContractError('Failed to fetch render jobs')).toBe(false)
    expect(isProductionRecoveryContractError('timeout while polling')).toBe(false)
  })
})

describe('shouldAutoRecoverProductionBoard', () => {
  it('does not auto-recover without project id', () => {
    expect(
      shouldAutoRecoverProductionBoard({
        enabled: true,
        projectId: '',
        autoRecover: true,
        isRecovering: false,
        status: 'idle',
        pollingDisabled: false,
      }),
    ).toBe(false)
  })

  it('does not auto-recover when polling is disabled after an error', () => {
    expect(
      shouldAutoRecoverProductionBoard({
        enabled: true,
        projectId: 'demo_studio_cinematic_001',
        autoRecover: true,
        isRecovering: false,
        status: 'idle',
        pollingDisabled: true,
      }),
    ).toBe(false)
  })

  it('does not auto-recover when autoRecover is disabled', () => {
    expect(
      shouldAutoRecoverProductionBoard({
        enabled: true,
        projectId: 'demo_studio_cinematic_001',
        autoRecover: false,
        isRecovering: false,
        status: 'idle',
        pollingDisabled: false,
      }),
    ).toBe(false)
  })

  it('auto-recovers only when idle and explicitly enabled', () => {
    expect(
      shouldAutoRecoverProductionBoard({
        enabled: true,
        projectId: 'demo_studio_cinematic_001',
        autoRecover: true,
        isRecovering: false,
        status: 'idle',
        pollingDisabled: false,
      }),
    ).toBe(true)
  })
})

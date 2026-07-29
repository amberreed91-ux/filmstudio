const STITCHABLE_EDITORIAL_DECISION_TYPES = new Set([
  'replace_transition',
  'hold',
  'compress_escalation',
  'trim',
])

export function isStitchableEditorialDecision(decisionType: string) {
  return STITCHABLE_EDITORIAL_DECISION_TYPES.has(decisionType)
}

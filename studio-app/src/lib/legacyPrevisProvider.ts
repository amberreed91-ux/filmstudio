// R4.3L (Policy A): the legacy non-canonical previs path never forwards a
// Runway-family picker value. When the picker holds one, the legacy previs
// call sends simulated instead. Production render and revision controls keep
// using the raw picker value unchanged.
const LEGACY_PREVIS_RUNWAY_FAMILY = new Set(['runway', 'runway_router', 'runway_direct'])

export function isLegacyPrevisRunwayPicker(value: string | undefined | null): boolean {
  if (!value) return false
  return LEGACY_PREVIS_RUNWAY_FAMILY.has(String(value).trim().toLowerCase())
}

export function resolveLegacyPrevisProvider(
  pickerValue: string | undefined | null,
): string | undefined {
  if (isLegacyPrevisRunwayPicker(pickerValue)) return 'simulated'
  return pickerValue || undefined
}

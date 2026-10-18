import { describe, expect, it } from 'vitest';
import { getShotIntentRationale, SHOT_INTENT_FALLBACK } from './shotIntentRationale';

describe('getShotIntentRationale', () => {
  it('prefers explicit shot.intent string', () => {
    expect(getShotIntentRationale({ intent: 'Holds on Maya as the room goes quiet.' })).toBe(
      'Holds on Maya as the room goes quiet.',
    );
  });

  it('prefers metadata.intent_rationale when intent is absent', () => {
    expect(
      getShotIntentRationale({ metadata: { intent_rationale: 'Bridges the argument into a fragile truce.' } }),
    ).toBe('Bridges the argument into a fragile truce.');
  });

  it('falls back to director_notes and narrative_function', () => {
    expect(getShotIntentRationale({ director_notes: 'Let silence hurt as much as dialogue' })).toBe(
      'Let silence hurt as much as dialogue.',
    );
    expect(getShotIntentRationale({ narrative_function: 'Maya commits to the harder cut' })).toBe(
      'Maya commits to the harder cut.',
    );
  });

  it('reads narrative_function from a nested intent object', () => {
    expect(
      getShotIntentRationale({ intent: { narrative_function: 'Maya holds one breath, then commits.' } }),
    ).toBe('Maya holds one breath, then commits.');
  });

  it('derives synthesis from prompt or camera action', () => {
    const fromPrompt = getShotIntentRationale({ prompt: 'Low-angle push-in through smoke' });
    expect(fromPrompt).toContain('Low-angle push-in through smoke');
    expect(fromPrompt.endsWith('.')).toBe(true);

    const fromCamera = getShotIntentRationale({ camera: 'slow dolly-in' });
    expect(fromCamera).toContain('slow dolly-in');
    expect(fromCamera.endsWith('.')).toBe(true);
  });

  it('returns the fallback for missing or null fields without throwing', () => {
    expect(getShotIntentRationale(null)).toBe(SHOT_INTENT_FALLBACK);
    expect(getShotIntentRationale(undefined)).toBe(SHOT_INTENT_FALLBACK);
    expect(getShotIntentRationale({})).toBe(SHOT_INTENT_FALLBACK);
    expect(getShotIntentRationale({ intent: null, metadata: null, prompt: 42 })).toBe(
      SHOT_INTENT_FALLBACK,
    );
    expect(getShotIntentRationale({ intent: '   ' })).toBe(SHOT_INTENT_FALLBACK);
  });

  it('always returns a single concise sentence', () => {
    const result = getShotIntentRationale({
      intent: 'First sentence here. Second sentence should be dropped. Third too.',
    });
    expect(result).toBe('First sentence here.');
  });
});

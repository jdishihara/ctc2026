// Event 2 of the mock scenario (real-speed drill 2026-10-24 12:03): "Crude oil: $106.10, IV 0.58" must read as 58%, not 0.58%.
import { describe, expect, it } from 'vitest';
import { parseHeadline } from '../../src/engine/headline';

describe('headline vol written as a fraction', () => {
  it('reads "IV 0.58" as 58% and "(IV: 60%)" as 60%', () => {
    const p = parseHeadline('Investigators find no mechanical fault in the NewAir crash. NewAir shares rise to 39.40 (IV: 60%). Crude oil: $106.10, IV 0.58');
    expect(p.underlyings.PLANE?.spot).toBe(39.4);
    expect(p.underlyings.PLANE?.iv).toBeCloseTo(0.6, 9);
    expect(p.underlyings.OIL?.spot).toBe(106.1);
    expect(p.underlyings.OIL?.iv).toBeCloseTo(0.58, 9);
  });
  it('other fraction spellings', () => {
    expect(parseHeadline('OIL at 100.00, implied vol 0.65').underlyings.OIL?.iv).toBeCloseTo(0.65, 9);
    expect(parseHeadline('OIL at 100.00, sigma .7').underlyings.OIL?.iv).toBeCloseTo(0.7, 9);
    expect(parseHeadline('OIL at 100.00, IV 65').underlyings.OIL?.iv).toBeCloseTo(0.65, 9);
  });
});

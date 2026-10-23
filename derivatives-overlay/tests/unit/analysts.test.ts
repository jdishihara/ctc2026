import { describe, expect, it } from 'vitest';
import { analystStats, analystWeights, AnalystRecord, blendAnalysts, DEFAULT_BLEND } from '../../src/engine/analysts';

describe('analyst blending and learning', () => {
  it('Analyst 2 (accurate) earns > 0.6 weight after 3 events', () => {
    const truth = [
      { OIL: 0.55, PLANE: 0.58 }, { OIL: 0.52, PLANE: 0.9 }, { OIL: 0.62, PLANE: 0.95 },
    ];
    const noise = [0.12, -0.15, 0.1, -0.13, 0.14, -0.11];
    const history: AnalystRecord[] = [];
    truth.forEach((tv, i) => {
      for (const [u, v] of Object.entries(tv)) {
        const k = i * 2 + (u === 'OIL' ? 0 : 1);
        history.push({ event: i + 4, underlying: u, trueVol: v, t: i, estimates: { 1: v + 0.08, 2: v + (k % 2 ? 0.005 : -0.005), 3: v + noise[k] } });
      }
    });
    for (const u of ['OIL', 'PLANE']) {
      const w = analystWeights(history, u, [1, 2, 3], DEFAULT_BLEND.lambda);
      expect(w[2] as number).toBeGreaterThan(0.6);
      expect((w[1] as number) + (w[2] as number) + (w[3] as number)).toBeCloseTo(1, 12);
    }
    const st = analystStats(history);
    expect(st[1].bias as number).toBeCloseTo(0.08, 9);
    expect(st[2].rmse as number).toBeLessThan(0.01);
    const b = blendAnalysts({ 1: 0.7, 2: 0.6, 3: 0.4 }, 'OIL', history, { ...DEFAULT_BLEND, mode: 'weighted' });
    expect(Math.abs((b.vol as number) - 0.6)).toBeLessThan(0.03);
    expect(b.low as number).toBeLessThan(b.vol as number);
    expect(b.high as number).toBeGreaterThan(b.vol as number);
  });
  it('median by default with a min/max band and no history', () => {
    const b = blendAnalysts({ 1: 0.5, 2: 0.6, 3: 0.9 }, 'OIL', []);
    expect(b.vol).toBeCloseTo(0.6, 12);
    expect(b.low).toBeCloseTo(0.5, 12);
    expect(b.high).toBeCloseTo(0.9, 12);
    expect(blendAnalysts({}, 'OIL', []).vol).toBeNull();
    expect(blendAnalysts({ 1: 0.5, 3: 0.7 }, 'OIL', [], { ...DEFAULT_BLEND, mode: 'single:3' }).vol).toBe(0.7);
  });
});

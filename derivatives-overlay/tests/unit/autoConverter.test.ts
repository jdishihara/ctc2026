import { describe, expect, it } from 'vitest';
import { identifyConverter } from '../../src/engine/autoConverter';
import { price } from '../../src/engine/blackScholes';

const T = 18 / 252;
const base = { marketIV: { OIL: 0.7, PLANE: 1.0 }, spot: { OIL: 100, PLANE: 40 }, T, strikes: { OIL: [60, 100, 140], PLANE: [30, 40, 50] }, tolPts: 12, tieMarginPts: 3 };

describe('Round 3 converter auto-identification', () => {
  it('annual variance quotes', () => {
    const r = identifyConverter({ ...base, text: 'Analyst 1: OIL variance 0.49, PLANE variance 1.0', samples: [{ underlying: 'OIL', raw: 0.49, rawStr: '0.49' }, { underlying: 'PLANE', raw: 1.0, rawStr: '1.0' }] });
    expect(r.id).toBe('variance');
    expect(r.reason).toMatch(/names it/);
  });
  it('variance without the keyword still wins on distance to the market IV', () => {
    const r = identifyConverter({ ...base, text: 'Analyst 2 sees OIL at 0.49 and PLANE at 1.0', samples: [{ underlying: 'OIL', raw: 0.49, rawStr: '0.49' }, { underlying: 'PLANE', raw: 1.0, rawStr: '1.0' }] });
    expect(r.id).toBe('variance');
    expect(r.ranked[0].id).toBe('variance');
  });
  it('does not reinterpret named variance as IV when the old market price is closer to the raw number', () => {
    const r = identifyConverter({
      ...base, tolPts: 8, marketIV: { OIL: 0.55, PLANE: 1.21 },
      text: 'Analyst 1: OIL variance 0.5625, PLANE variance 1.21',
      samples: [{ underlying: 'OIL', raw: 0.5625 }, { underlying: 'PLANE', raw: 1.21 }],
    });
    expect(r.ranked[0].id).toBe('iv');
    expect(r.ranked.find((c) => c.id === 'variance')!.errPts).toBeGreaterThan(8);
    expect(r.id).toBeNull();
    expect(r.reason).toMatch(/message names.*variance.*Pick the converter by hand/i);
  });
  it('daily move in percent', () => {
    // sigma 0.70 -> 0.70/sqrt(252) = 4.41% per day; 1.0 -> 6.30%
    const r = identifyConverter({ ...base, text: 'Analyst 1: OIL expected daily move 4.41%, PLANE 6.30%', samples: [{ underlying: 'OIL', raw: 4.41, rawStr: '4.41%' }, { underlying: 'PLANE', raw: 6.3, rawStr: '6.30%' }] });
    expect(r.id).toBe('dailyMovePct');
  });
  it('ATM straddle price in dollars', () => {
    const strad = (S: number, iv: number) => price('C', S, S, iv, T) + price('P', S, S, iv, T);
    const o = strad(100, 0.7);
    const p = strad(40, 1.0);
    const r = identifyConverter({ ...base, text: `Analyst 3: OIL straddle $${o.toFixed(2)}, PLANE straddle $${p.toFixed(2)}`, samples: [{ underlying: 'OIL', raw: Number(o.toFixed(2)), rawStr: `$${o.toFixed(2)}` }, { underlying: 'PLANE', raw: Number(p.toFixed(2)), rawStr: `$${p.toFixed(2)}` }] });
    expect(r.id).toBe('atmStraddle');
  });
  it('call and put price at the ATM strike coincide: ambiguous without a keyword, resolved by one', () => {
    const c = price('C', 100, 100, 0.7, T);
    const noWord = identifyConverter({ ...base, text: 'Analyst 1: OIL 5.9', samples: [{ underlying: 'OIL', raw: Number(c.toFixed(2)), rawStr: `$${c.toFixed(2)}` }] });
    expect(noWord.id).toBeNull();
    expect(noWord.reason).toMatch(/ambiguous/);
    const word = identifyConverter({ ...base, text: `Analyst 1: OIL call price $${c.toFixed(2)}`, samples: [{ underlying: 'OIL', raw: Number(c.toFixed(2)), rawStr: `$${c.toFixed(2)}` }] });
    expect(word.id).toBe('callPrice');
  });
  it('nothing inside the tolerance falls back to manual', () => {
    const r = identifyConverter({ ...base, marketIV: { OIL: 0.3, PLANE: 0.3 }, text: 'Analyst 1: OIL 3.0%, PLANE 3.0%', samples: [{ underlying: 'OIL', raw: 3.0, rawStr: '3.0%' }, { underlying: 'PLANE', raw: 3.0, rawStr: '3.0%' }] });
    expect(r.id).toBeNull();
    expect(r.reason).toMatch(/nothing within 12 vol pts/);
    expect(r.ranked.length).toBeGreaterThan(0);
  });
  it('no market IV: cannot evaluate', () => {
    const r = identifyConverter({ ...base, marketIV: {}, text: 'x', samples: [{ underlying: 'OIL', raw: 0.49 }] });
    expect(r.id).toBeNull();
    expect(r.reason).toMatch(/no converter could be evaluated/);
  });
});

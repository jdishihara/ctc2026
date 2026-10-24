import { describe, expect, it } from 'vitest';
import { extractStructured, parseHeadline } from '../../src/engine/headline';

describe('headline parser', () => {
  const cases: [string, Record<string, { spot?: number; iv?: number; changePct?: number }>][] = [
    ['OIL jumps to 104.20; implied vol now 62%', { OIL: { spot: 104.2, iv: 0.62 } }],
    ['Crude oil: $96.50, IV 0.48', { OIL: { spot: 96.5, iv: 0.48 } }],
    ['NewAir shares fall to 31.40 (IV: 90%)', { PLANE: { spot: 31.4, iv: 0.9 } }],
    ['President Oiler blocks crude exports to Newtonia. OIL jumps to 108.50; implied vol now 65%. NewAir (PLANE) slides to 36.20, IV 85%.', { OIL: { spot: 108.5, iv: 0.65 }, PLANE: { spot: 36.2, iv: 0.85 } }],
    ['Protests shut two Eulerian refineries; OIL climbs to 112.00, implied volatility 72%. PLANE dips to 37.80; PLANE IV 66%.', { OIL: { spot: 112, iv: 0.72 }, PLANE: { spot: 37.8, iv: 0.66 } }],
    ['PLANE: 33.20 | vol 70', { PLANE: { spot: 33.2, iv: 0.7 } }],
    ['Oil prices drop 5% on ceasefire news', { OIL: { changePct: -5 } }],
    ['OIL 101.5, PLANE 40.25', { OIL: { spot: 101.5 }, PLANE: { spot: 40.25 } }],
    ['The airline\'s stock slumps to 29.10 as volatility hits 1.2', { PLANE: { spot: 29.1, iv: 1.2 } }],
    ['Brent crude rallies to $110.25 with IV at 55.5%', { OIL: { spot: 110.25, iv: 0.555 } }],
    ['Oiler threatens exports. OIL steady at 100.00; implied vol now 65%. PLANE holds at 40.00, IV 70%.', { OIL: { spot: 100, iv: 0.65 }, PLANE: { spot: 40, iv: 0.7 } }],
  ];
  for (const [text, want] of cases) {
    it(`parses: ${text.slice(0, 60)}`, () => {
      const p = parseHeadline(text);
      for (const [u, w] of Object.entries(want)) {
        expect(p.underlyings[u], `${u} in ${JSON.stringify(p)}`).toBeDefined();
        if (w.spot != null) expect(p.underlyings[u].spot).toBeCloseTo(w.spot, 6);
        if (w.iv != null) expect(p.underlyings[u].iv).toBeCloseTo(w.iv, 6);
        if (w.changePct != null) expect(p.underlyings[u].changePct).toBeCloseTo(w.changePct, 6);
      }
      expect(Object.keys(p.underlyings).sort()).toEqual(Object.keys(want).sort());
    });
  }

  it('analyst estimates (Round 2 percent and decimal, Round 3 raw)', () => {
    const a = parseHeadline('Analyst 2 sees PLANE vol at 75%');
    expect(a.analysts).toEqual([expect.objectContaining({ analyst: 2, underlying: 'PLANE', value: 0.75, rawValue: 75, hasPct: true })]);
    const b = parseHeadline('Analyst 1: OIL vol 63.0%, PLANE vol 66.0%');
    expect(b.analysts.map((x) => [x.analyst, x.underlying, x.value])).toEqual([[1, 'OIL', 0.63], [1, 'PLANE', 0.66]]);
    const c = parseHeadline('Analyst 3: OIL variance 0.36, PLANE variance 0.81');
    expect(c.analysts.map((x) => [x.underlying, x.rawValue])).toEqual([['OIL', 0.36], ['PLANE', 0.81]]);
    const e = parseHeadline('Analyst 2: OIL one-day move 4.4%, PLANE one-day move 6.3%');
    expect(e.analysts.map((x) => [x.underlying, x.rawValue, x.hasPct])).toEqual([['OIL', 4.4, true], ['PLANE', 6.3, true]]);
    const d = parseHeadline('Analyst #1 expects crude IV of 0.52');
    expect(d.analysts[0]).toMatchObject({ analyst: 1, underlying: 'OIL', value: 0.52 });
    expect(Object.keys(d.underlyings)).toHaveLength(0);
  });

  it('negative cases: no numbers, no underlyings, irrelevant numbers', () => {
    expect(parseHeadline('Protests continue outside refineries in both countries').underlyings).toEqual({});
    expect(parseHeadline('Oiler imposes a 20% tariff on Newtonia').underlyings).toEqual({});
    expect(parseHeadline('NewAir crash investigation enters day 3').underlyings).toEqual({});
    expect(parseHeadline('').analysts).toEqual([]);
    expect(parseHeadline('Market opens at 09:30 on 2026-06-01').underlyings).toEqual({});
    expect(parseHeadline('OIL_0626_C100 trades heavily').underlyings).toEqual({});
  });

  it('structured news fields', () => {
    expect(extractStructured({ type: 'announcement', OIL: { price: 104.2, iv: 62 }, PLANE: 31.4 }, ['OIL', 'PLANE'])).toEqual({ OIL: { spot: 104.2, iv: 0.62 }, PLANE: { spot: 31.4 } });
    expect(extractStructured({ symbol: 'OIL', new_price: 99, vol: 0.5 }, ['OIL', 'PLANE'])).toEqual({ OIL: { spot: 99, iv: 0.5 } });
    expect(extractStructured({ prices: { OIL: 100 } }, ['OIL', 'PLANE'])).toEqual({ OIL: { spot: 100 } });
  });
});

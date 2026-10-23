import { describe, expect, it } from 'vitest';
import { vegaPerPoint } from '../../src/engine/blackScholes';
import { computeEdges, DEFAULT_EDGE_OPTS, rankRobust, roomFor } from '../../src/engine/fairValue';
import { straddles, syntheticForwards } from '../../src/engine/structures';
import { bsChain } from '../helpers/chain';

const T = 20 / 252;

describe('fair value and robust edge', () => {
  it('ranks the vol-driven ATM contract after a vol jump and decomposes spot vs vol', () => {
    const { chain } = bsChain('OIL', 100, 0.5, T, [60, 100, 140]);
    const rows = computeEdges(chain, { spot: 100, vol: 0.65, volLow: 0.65, volHigh: 0.65 }, { oldSpot: 100, oldVol: 0.5 }, T, {}, {});
    const top = rankRobust(rows)[0];
    expect(top.contract.strike).toBe(100);
    expect(top.robustSide).toBe('BUY');
    expect(top.spotComponent).toBeCloseTo(0, 9);
    expect(top.volComponent as number).toBeGreaterThan(1);
    // deep ITM after a spot jump is spot-driven
    const r2 = computeEdges(chain, { spot: 108, vol: 0.5, volLow: 0.5, volHigh: 0.5 }, { oldSpot: 100, oldVol: 0.5 }, T, {}, {});
    const c60 = r2.find((r) => r.contract.symbol === 'OIL_0626_C60')!;
    expect(c60.robustSide).toBe('BUY');
    expect(Math.abs(c60.spotComponent as number)).toBeGreaterThan(10 * Math.abs(c60.volComponent as number));
  });
  it('a ticket profitable at the blend but not at one band end is excluded', () => {
    const { chain } = bsChain('OIL', 100, 0.5, T, [100]);
    // blend says 55% (call looks cheap), band [45%, 65%] includes vols where buying loses
    const rows = computeEdges(chain, { spot: 100, vol: 0.55, volLow: 0.45, volHigh: 0.65 }, null, T, {}, {});
    const c = rows.find((r) => r.contract.kind === 'C')!;
    expect(c.edge).toBeGreaterThan(DEFAULT_EDGE_OPTS.minEdge);
    expect(c.robustEdge).toBeLessThan(DEFAULT_EDGE_OPTS.minEdge);
    expect(rankRobust(rows).map((r) => r.contract.symbol)).not.toContain(c.contract.symbol);
    // collapsing the band (announced IV) restores it
    const pt = computeEdges(chain, { spot: 100, vol: 0.55, volLow: 0.55, volHigh: 0.55 }, null, T, {}, {});
    expect(rankRobust(pt).map((r) => r.contract.symbol)).toContain('OIL_0626_C100');
  });
  it('room counts resting orders on the same side', () => {
    expect(roomFor('BUY', 250, { buy: 30, sell: 0 }, 300)).toBe(20);
    expect(roomFor('SELL', 250, { buy: 30, sell: 100 }, 300)).toBe(450);
    expect(roomFor('SELL', -280, { buy: 0, sell: 15 }, 300)).toBe(5);
    expect(roomFor('BUY', 320, undefined, 300)).toBe(0);
  });
});

describe('structures', () => {
  it('synthetic forward: edge vs S-K and vega exactly neutral', () => {
    const { chain } = bsChain('OIL', 100, 0.5, T, [80, 100, 120]);
    const syn = syntheticForwards(chain, 105, T, 0.5);
    const long100 = syn.find((s) => s.kind === 'synthLong' && s.strike === 100)!;
    const c = chain.rows[1].call!;
    const p = chain.rows[1].put!;
    expect(long100.edge).toBeCloseTo(105 - 100 - (c.ask! - p.bid!), 12);
    for (const s of syn) expect(Math.abs(s.vega)).toBeLessThan(1e-9);
    expect(long100.delta).toBeCloseTo(1, 9);
    expect(long100.legs.map((l) => l.side)).toEqual(['BUY', 'SELL']);
  });
  it('straddle is the vol trade', () => {
    const { chain } = bsChain('OIL', 100, 0.5, T, [100]);
    const st = straddles(chain, 100, 0.6, T);
    const buy = st.find((s) => s.kind === 'straddleBuy')!;
    expect(buy.edge).toBeGreaterThan(0);
    expect(buy.vega).toBeCloseTo(2 * vegaPerPoint(100, 100, 0.6, T), 12);
  });
});

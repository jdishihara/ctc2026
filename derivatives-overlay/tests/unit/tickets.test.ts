import { describe, expect, it } from 'vitest';
import { computeEdges } from '../../src/engine/fairValue';
import { contractsBySymbol } from '../../src/engine/risk';
import { syntheticForwards } from '../../src/engine/structures';
import { PlanInput, planTickets, ticketsFromArb } from '../../src/engine/tickets';
import { findArbs } from '../../src/engine/arbitrage';
import { isOrderAction, RateMeter } from '../../src/engine/rateLimit';
import { bsChain, metasFor, withQuote } from '../helpers/chain';

const T = 20 / 252;

function setup(positions: Record<string, number> = {}, resting = {}, over: Partial<PlanInput> = {}) {
  const { chain } = bsChain('OIL', 100, 0.5, T, [60, 100, 140], 0.05, 200);
  const target = { spot: 100, vol: 0.7, volLow: 0.7, volHigh: 0.7 };
  const edges = computeEdges(chain, target, { oldSpot: 100, oldVol: 0.5 }, T, positions, resting, { positionLimit: 300, perTicketCap: 300, minEdge: 0.05, multiplier: 1, tick: 0.01 });
  const input: PlanInput = {
    edges, structures: syntheticForwards(chain, 100, T, 0.7, positions, resting), contracts: contractsBySymbol({ OIL: chain }),
    targets: { OIL: { spot: 100, vol: 0.7 } }, T, positions, resting, bookGreeks: {},
    caps: { maxAbsDeltaPerUnderlying: 1e9, maxAbsVegaPts: 1e9 }, positionLimit: 300, perTicketCap: 300, minEdge: 0.05,
    rateRemaining: 40, round: 1, preferSynthForSpot: true, priceMode: 'touch', tick: 0.01, focus: null, ...over,
  };
  return { chain, input };
}

describe('ticket planner', () => {
  it('buys the vol-cheap options at the ask, best first', () => {
    const { input } = setup();
    const plan = planTickets(input);
    expect(plan.length).toBeGreaterThan(0);
    expect(plan[0].symbol).toMatch(/_[CP]100$/);
    expect(plan.every((t) => t.side === 'BUY')).toBe(true);
    const c = input.contracts[plan[0].symbol];
    expect(plan[0].price).toBe(c.ask);
  });
  it('respects the 300 limit including resting orders, and the per-ticket cap', () => {
    const { input } = setup({ OIL_0626_C100: 250 }, { OIL_0626_C100: { buy: 30, sell: 0 } });
    const c100 = planTickets(input).find((t) => t.symbol === 'OIL_0626_C100');
    expect(c100?.qty).toBe(20);
    const { input: i2 } = setup({}, {}, { perTicketCap: 25 });
    expect(Math.max(...planTickets(i2).map((t) => t.qty))).toBe(25);
    const { input: i3 } = setup({ OIL_0626_C100: 300 });
    expect(planTickets(i3).find((t) => t.symbol === 'OIL_0626_C100')).toBeUndefined();
  });
  it('marks risk-cap breaches red and puts them last', () => {
    const { input } = setup({}, {}, { caps: { maxAbsDeltaPerUnderlying: 1e9, maxAbsVegaPts: 20 } });
    const plan = planTickets(input);
    const red = plan.filter((t) => t.breach.length);
    expect(red.length).toBeGreaterThan(0);
    const firstRed = plan.findIndex((t) => t.breach.length);
    expect(plan.slice(firstRed).every((t) => t.breach.length)).toBe(true);
    expect(red[0].breach[0]).toMatch(/vega/);
  });
  it('flags tickets beyond the order-rate budget', () => {
    const { input } = setup({}, {}, { rateRemaining: 1 });
    const plan = planTickets(input);
    expect(plan[0].withinRateBudget).toBe(true);
    expect(plan.slice(1).every((t) => !t.withinRateBudget)).toBe(true);
  });
  it('rounds 2-3 prefer the vega-neutral synthetic for spot-driven edge', () => {
    const { chain } = bsChain('OIL', 100, 0.5, T, [60, 100, 140], 0.05, 200);
    const tgt = { spot: 108, vol: 0.5, volLow: 0.45, volHigh: 0.55 };
    const edges = computeEdges(chain, tgt, { oldSpot: 100, oldVol: 0.5 }, T, {}, {});
    const base = {
      edges, structures: syntheticForwards(chain, 108, T, 0.5), contracts: contractsBySymbol({ OIL: chain }), targets: { OIL: { spot: 108, vol: 0.5 } },
      T, positions: {}, resting: {}, bookGreeks: {}, caps: { maxAbsDeltaPerUnderlying: 1e9, maxAbsVegaPts: 1e9 }, positionLimit: 300, perTicketCap: 300,
      minEdge: 0.05, rateRemaining: 40, preferSynthForSpot: true, priceMode: 'touch' as const, tick: 0.01, focus: null,
    };
    const r2 = planTickets({ ...base, round: 2 });
    expect(r2[0].source).toBe('struct');
    expect(r2[0].groupId).toBeDefined();
    expect(r2[1].groupId).toBe(r2[0].groupId);
    const r1 = planTickets({ ...base, round: 1 });
    expect(r1.every((t) => t.source === 'edge')).toBe(true);
  });
  it('arbitrage flags become linked tickets', () => {
    const metas = metasFor('OIL', [80, 100, 120]);
    const { quotes } = bsChain('OIL', 100, 0.5, T, [80, 100, 120]);
    const ch = withQuote('OIL', quotes, metas, 'OIL_0626_C100', { bid: quotes.OIL_0626_C100.bid! + 6, ask: quotes.OIL_0626_C100.ask! + 6 });
    const fly = findArbs(ch, null, T).find((f) => f.kind === 'convexity')!;
    const ts = ticketsFromArb(fly, contractsBySymbol({ OIL: ch }), 300, 0.01);
    expect(ts.map((t) => t.qty)).toEqual([25, 50, 25]); // 50 lots at each touch; the 2x body leg binds
    expect(new Set(ts.map((t) => t.groupId)).size).toBe(1);
  });
});

describe('order-rate meter', () => {
  it('counts a sliding 60 s window with amber/red levels', () => {
    const m = new RateMeter();
    for (let i = 0; i < 30; i++) m.add(1000 + i);
    expect(m.status(2000).level).toBe('amber');
    for (let i = 0; i < 6; i++) m.add(2000);
    expect(m.status(2000)).toMatchObject({ used: 36, level: 'red', remaining: 4 });
    expect(m.count(61_500)).toBe(6);
  });
  it('recognizes order actions', () => {
    expect(isOrderAction('POST', 'https://x/api/v1/orders')).toBe(true);
    expect(isOrderAction('DELETE', '/api/v1/orders/all')).toBe(true);
    expect(isOrderAction('DELETE', '/api/v1/orders/abc')).toBe(true);
    expect(isOrderAction('GET', '/api/v1/orders/open?symbol=X')).toBe(false);
    expect(isOrderAction('POST', '/api/v1/etf/create')).toBe(true);
  });
});

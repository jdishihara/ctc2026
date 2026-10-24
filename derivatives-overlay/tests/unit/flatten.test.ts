import { describe, expect, it } from 'vitest';
import { buildChains, OptionMeta, Quote } from '../../src/engine/chain';
import { flattenOrders } from '../../src/engine/risk';

function chain(bidAsk: Record<string, [number, number]>) {
  const metas: OptionMeta[] = [];
  const quotes: Record<string, Quote> = {};
  for (const [sym, [bid, ask]] of Object.entries(bidAsk)) {
    const m = /^(OIL|PLANE)_(\d{4})_([CP])(\d+)$/.exec(sym)!;
    metas.push({ symbol: sym, underlying: m[1], expiry: m[2], kind: m[3] as 'C' | 'P', strike: Number(m[4]) });
    quotes[sym] = { symbol: sym, bid, ask, bidSize: 40, askSize: 40, t: 0, src: 'WS' };
  }
  return buildChains(metas, quotes);
}

describe('flatten tickets', () => {
  const chains = chain({ OIL_0626_C100: [10.0, 10.2], OIL_0626_P100: [0.8, 0.9] });
  const inputs = { OIL: { spot: 100, vol: 0.6 } };
  const T = 20 / 252;

  it('at the touch by default; spread cost is measured against the mid', () => {
    const { orders, totalSpreadCost } = flattenOrders(chains, { OIL_0626_C100: 120 }, inputs, T);
    expect(orders).toHaveLength(1);
    expect(orders[0]).toMatchObject({ symbol: 'OIL_0626_C100', side: 'SELL', qty: 120, price: 10.0 });
    expect(totalSpreadCost).toBeCloseTo(0.1 * 120, 6);
  });

  it('goes through the touch by max(pct of mid, ticks) so one order clears several levels', () => {
    const through = { pct: 2, ticks: 5, tick: 0.01 };
    const { orders, totalSpreadCost } = flattenOrders(chains, { OIL_0626_C100: 120, OIL_0626_P100: -50 }, inputs, T, undefined, 300, through);
    const sell = orders.find((o) => o.symbol === 'OIL_0626_C100')!;
    const buy = orders.find((o) => o.symbol === 'OIL_0626_P100')!;
    // mid 10.1: 2% = 0.202 beats 5 ticks -> sell limit 10.0 - 0.202
    expect(sell.price).toBeCloseTo(10.0 - 0.202, 9);
    // mid 0.85: 2% = 0.017 < 5 ticks = 0.05 -> buy limit 0.9 + 0.05
    expect(buy.price).toBeCloseTo(0.95, 9);
    // the displayed cost stays the half-spread at the touch (what a fill at the touch costs), not the limit distance
    expect(totalSpreadCost).toBeCloseTo(0.1 * 120 + 0.05 * 50, 6);
  });

  it('never prices a sell below one tick', () => {
    const ch = chain({ PLANE_0626_P30: [0.02, 0.04] });
    const { orders } = flattenOrders(ch, { PLANE_0626_P30: 10 }, { PLANE: { spot: 40, vol: 0.9 } }, T, undefined, 300, { pct: 2, ticks: 5, tick: 0.01 });
    expect(orders[0].price).toBeCloseTo(0.01, 9);
  });
});

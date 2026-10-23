import { describe, expect, it } from 'vitest';
import { findArbs } from '../../src/engine/arbitrage';
import { bsChain, metasFor, withQuote } from '../helpers/chain';

const T = 20 / 252;
const strikes = [80, 100, 120];
const metas = metasFor('OIL', strikes);

describe('arbitrage checks', () => {
  it('a consistent BS chain raises zero flags', () => {
    for (const [S, v] of [[100, 0.5], [99.89, 1.0], [112, 0.3]] as const) {
      const { chain } = bsChain('OIL', S, v, T, strikes);
      expect(findArbs(chain, S, T), `S=${S} v=${v}`).toEqual([]);
    }
    const wide = bsChain('OIL', 100, 0.5, T, [60, 100, 140]);
    expect(findArbs(wide.chain, 100, T)).toEqual([]);
  });
  it('box violation (spot-free) with 4 legs', () => {
    const { quotes } = bsChain('OIL', 100, 0.5, T, strikes);
    // make the 80/100 box cheap: lift P100 down hard (ask) so buying the box costs < 20
    const ch = withQuote('OIL', quotes, metas, 'OIL_0626_P100', { ask: quotes.OIL_0626_P100.ask! - 1, bid: quotes.OIL_0626_P100.bid! - 1 });
    const box = findArbs(ch, null, T).filter((f) => f.kind === 'box');
    expect(box.length).toBeGreaterThan(0);
    const b = box.find((x) => x.description.includes('80/100')) ?? box[0];
    expect(b.legs).toHaveLength(4);
    expect(b.riskless).toBe(true);
    expect(b.legs.map((l) => `${l.side} ${l.symbol}`)).toEqual(['BUY OIL_0626_C80', 'SELL OIL_0626_P80', 'SELL OIL_0626_C100', 'BUY OIL_0626_P100']);
  });
  it('parity violation against the live spot', () => {
    const { quotes } = bsChain('OIL', 100, 0.5, T, strikes);
    const ch = withQuote('OIL', quotes, metas, 'OIL_0626_C100', { bid: quotes.OIL_0626_C100.bid! + 0.6, ask: quotes.OIL_0626_C100.ask! + 0.6 });
    const par = findArbs(ch, 100, T).filter((f) => f.kind === 'parity');
    expect(par).toHaveLength(1);
    expect(par[0].spotDependent).toBe(true);
    expect(par[0].legs.map((l) => `${l.side} ${l.symbol}`)).toEqual(['SELL OIL_0626_C100', 'BUY OIL_0626_P100']);
  });
  it('monotonicity violation', () => {
    const { quotes } = bsChain('OIL', 100, 0.5, T, strikes);
    const c80 = quotes.OIL_0626_C80;
    const ch = withQuote('OIL', quotes, metas, 'OIL_0626_C100', { bid: c80.ask! + 0.5, ask: c80.ask! + 0.6 });
    const mono = findArbs(ch, null, T).filter((f) => f.kind === 'monotonicity');
    expect(mono).toHaveLength(1);
    expect(mono[0].legs.map((l) => `${l.side} ${l.symbol}`)).toEqual(['BUY OIL_0626_C80', 'SELL OIL_0626_C100']);
  });
  it('butterfly (convexity) violation with weights', () => {
    const { quotes } = bsChain('OIL', 100, 0.5, T, strikes);
    const q = quotes.OIL_0626_C100;
    const ch = withQuote('OIL', quotes, metas, 'OIL_0626_C100', { bid: q.bid! + 6, ask: q.ask! + 6 });
    const fly = findArbs(ch, null, T).filter((f) => f.kind === 'convexity');
    expect(fly).toHaveLength(1);
    expect(fly[0].legs.map((l) => `${l.side} ${l.ratio}×${l.symbol}`)).toEqual(['BUY 1×OIL_0626_C80', 'SELL 2×OIL_0626_C100', 'BUY 1×OIL_0626_C120']);
  });
  it('unequal spacing scales butterfly weights', () => {
    const s2 = [80, 90, 120];
    const m2 = metasFor('OIL', s2);
    const { quotes } = bsChain('OIL', 100, 0.5, T, s2);
    const q = quotes.OIL_0626_P90;
    const ch = withQuote('OIL', quotes, m2, 'OIL_0626_P90', { bid: q.bid! + 6, ask: q.ask! + 6 });
    const fly = findArbs(ch, null, T).filter((f) => f.kind === 'convexity');
    expect(fly[0].legs.map((l) => l.ratio)).toEqual([3, 4, 1]); // (120-90):(120-80):(90-80) = 30:40:10
  });
  it('flat-vol IV outlier with direction', () => {
    const { quotes } = bsChain('OIL', 100, 0.5, T, strikes);
    const q = quotes.OIL_0626_P100;
    const ch = withQuote('OIL', quotes, metas, 'OIL_0626_P100', { bid: q.bid! + 0.5, ask: q.ask! + 0.5 });
    const out = findArbs(ch, 100, T).filter((f) => f.kind === 'ivOutlier');
    expect(out).toHaveLength(1);
    expect(out[0].legs[0]).toMatchObject({ side: 'SELL', symbol: 'OIL_0626_P100' });
    expect(out[0].description).toMatch(/rich/);
  });
});

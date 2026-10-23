import { price } from '../../src/engine/blackScholes';
import { buildChains, Chain, OptionMeta, Quote } from '../../src/engine/chain';

export function metasFor(und: string, strikes: number[]): OptionMeta[] {
  return strikes.flatMap((K) => (['C', 'P'] as const).map((kind) => ({ symbol: `${und}_0626_${kind}${K}`, underlying: und, expiry: '0626', kind, strike: K })));
}

/** A BS-consistent chain quoted at fair ± half (rounded to cents), with sizes. */
export function bsChain(und: string, S: number, vol: number, T: number, strikes: number[], half = 0.05, size = 50): { chain: Chain; quotes: Record<string, Quote> } {
  const metas = metasFor(und, strikes);
  const quotes: Record<string, Quote> = {};
  for (const m of metas) {
    const f = price(m.kind, S, m.strike, vol, T);
    const r2 = (x: number) => Math.round(x * 100) / 100;
    quotes[m.symbol] = { symbol: m.symbol, bid: Math.max(r2(f - half), 0.01), ask: r2(f + half) + (r2(f - half) < 0.01 ? 0.01 : 0), bidSize: size, askSize: size, t: 0, src: 'WS' };
  }
  return { chain: buildChains(metas, quotes)[und], quotes };
}

export function withQuote(und: string, quotes: Record<string, Quote>, metas: OptionMeta[], sym: string, patch: Partial<Quote>): Chain {
  const q = { ...quotes, [sym]: { ...quotes[sym], ...patch } };
  return buildChains(metas, q)[und];
}

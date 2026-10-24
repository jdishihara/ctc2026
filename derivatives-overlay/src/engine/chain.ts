// Option chain model: discover contracts from symbols, attach quotes, derive market IV and parity spot.
import { Kind, getRate, vegaPerPoint } from './blackScholes';
import { impliedVol } from './impliedVol';

export type Side = 'BUY' | 'SELL';
export type QuoteSource = 'WS' | 'DOM' | 'BOOK' | 'REST';

export interface Quote {
  symbol: string;
  bid: number | null;
  ask: number | null;
  bidSize: number | null;
  askSize: number | null;
  last?: number | null;
  /** local receipt time, ms (Date.now()) */
  t: number;
  src: QuoteSource;
}

export interface OptionMeta {
  symbol: string;
  underlying: string;
  expiry: string;
  kind: Kind;
  strike: number;
}

export interface Contract extends OptionMeta {
  bid: number | null;
  ask: number | null;
  bidSize: number | null;
  askSize: number | null;
  t: number | null;
  src: QuoteSource | null;
}

export interface ChainRow {
  strike: number;
  call?: Contract;
  put?: Contract;
}

export interface Chain {
  underlying: string;
  strikes: number[];
  rows: ChainRow[];
  contracts: Contract[];
}

export const DEFAULT_OPTION_REGEX = '^(OIL|PLANE)_(\\d{4})_([CP])(\\d+(?:\\.\\d+)?)$';

export function compileSymbolRegex(src: string): RegExp {
  try {
    return new RegExp(src);
  } catch {
    return new RegExp(DEFAULT_OPTION_REGEX);
  }
}

/** Groups: 1 underlying, 2 expiry, 3 C|P, 4 strike. */
export function parseOptionSymbol(symbol: string, re: RegExp = new RegExp(DEFAULT_OPTION_REGEX)): OptionMeta | null {
  const m = re.exec(symbol);
  if (!m || m.length < 5) return null;
  const kind = m[3].toUpperCase().startsWith('C') ? 'C' : m[3].toUpperCase().startsWith('P') ? 'P' : null;
  const strike = Number(m[4]);
  if (!kind || !Number.isFinite(strike)) return null;
  return { symbol, underlying: m[1].toUpperCase(), expiry: m[2], kind, strike };
}

/** Defensive parse of one /api/v1/symbols entry (string or object of unknown shape). */
export function metaFromSymbolEntry(entry: unknown, re: RegExp): OptionMeta | null {
  if (typeof entry === 'string') return parseOptionSymbol(entry, re);
  if (!entry || typeof entry !== 'object') return null;
  const o = entry as Record<string, unknown>;
  const symbol = String(o.symbol ?? o.ticker ?? o.name ?? o.id ?? '');
  const fromName = symbol ? parseOptionSymbol(symbol, re) : null;
  // the live exchange (2026-10-24): symbol_type 'option', option_kind 'call'|'put', strike_price, underlying_symbol, expiry_fictional_time
  const kindRaw = String(o.option_kind ?? o.option_type ?? o.optionType ?? o.right ?? o.put_call ?? o.kind ?? o.type ?? '').toUpperCase();
  const kind: Kind | null = /^(C|CALL)/.test(kindRaw) ? 'C' : /^(P|PUT)/.test(kindRaw) ? 'P' : null;
  const strike = Number(o.strike ?? o.strike_price ?? o.strikePrice);
  const underlying = String(o.underlying ?? o.underlying_symbol ?? o.underlyingSymbol ?? o.root ?? '').toUpperCase();
  if (symbol && kind && Number.isFinite(strike) && strike > 0 && underlying) {
    return { symbol, underlying, kind, strike, expiry: String(o.expiry ?? o.expiration ?? o.expiry_fictional_time ?? fromName?.expiry ?? '') };
  }
  return fromName;
}

export function mid(c: { bid: number | null; ask: number | null }): number | null {
  if (c.bid != null && c.ask != null && c.bid > 0 && c.ask > 0 && c.ask >= c.bid) return (c.bid + c.ask) / 2;
  return null;
}

export function buildChains(metas: Iterable<OptionMeta>, quotes: Record<string, Quote | undefined>): Record<string, Chain> {
  const out: Record<string, Chain> = {};
  for (const m of metas) {
    const q = quotes[m.symbol];
    const c: Contract = {
      ...m,
      bid: q?.bid ?? null, ask: q?.ask ?? null, bidSize: q?.bidSize ?? null, askSize: q?.askSize ?? null,
      t: q?.t ?? null, src: q?.src ?? null,
    };
    const ch = (out[m.underlying] ??= { underlying: m.underlying, strikes: [], rows: [], contracts: [] });
    ch.contracts.push(c);
    let row = ch.rows.find((r) => r.strike === m.strike);
    if (!row) {
      row = { strike: m.strike };
      ch.rows.push(row);
    }
    if (m.kind === 'C') row.call = c;
    else row.put = c;
  }
  for (const ch of Object.values(out)) {
    ch.rows.sort((a, b) => a.strike - b.strike);
    ch.strikes = ch.rows.map((r) => r.strike);
    ch.contracts.sort((a, b) => a.strike - b.strike || a.kind.localeCompare(b.kind));
  }
  return out;
}

export interface ContractIV {
  mid: number | null;
  bid: number | null;
  ask: number | null;
  vegaAtMid: number;
}

export function contractIV(c: Contract, S: number, T: number): ContractIV {
  const m = mid(c);
  const ivMid = m != null ? impliedVol(c.kind, m, S, c.strike, T) : null;
  const ivBid = c.bid != null && c.bid > 0 ? impliedVol(c.kind, c.bid, S, c.strike, T) : null;
  const ivAsk = c.ask != null && c.ask > 0 ? impliedVol(c.kind, c.ask, S, c.strike, T) : null;
  return { mid: ivMid, bid: ivBid, ask: ivAsk, vegaAtMid: ivMid != null ? vegaPerPoint(S, c.strike, ivMid, T) : 0 };
}

export function median(xs: number[]): number | null {
  const a = xs.filter((x) => Number.isFinite(x)).sort((x, y) => x - y);
  if (!a.length) return null;
  const k = Math.floor(a.length / 2);
  return a.length % 2 ? a[k] : (a[k - 1] + a[k]) / 2;
}

/** Underlying's market IV: median of mid IVs over contracts with vega/1pt >= minVega. */
export function marketIV(chain: Chain, S: number, T: number, minVega = 0.02): number | null {
  if (!(S > 0) || !(T > 0)) return null;
  const ivs: number[] = [];
  for (const c of chain.contracts) {
    const iv = contractIV(c, S, T);
    if (iv.mid != null && iv.mid > 2e-4 && iv.vegaAtMid >= minVega) ivs.push(iv.mid);
  }
  return median(ivs);
}

/** Put-call parity spot: S = K e^{-rT} + C - P, median across strikes with both mids (r from the chain, 0 by default). */
export function parityImpliedSpot(chain: Chain, T = 0, r = getRate()): number | null {
  const xs: number[] = [];
  const disc = T > 0 ? Math.exp(-r * T) : 1;
  for (const row of chain.rows) {
    if (!row.call || !row.put) continue;
    const mc = mid(row.call);
    const mp = mid(row.put);
    if (mc != null && mp != null) xs.push(row.strike * disc + mc - mp);
  }
  return median(xs);
}

/** Tick inferred from the number of decimals seen in prices (default 0.01). */
export function inferTick(prices: number[], fallback = 0.01): number {
  let dec = 0;
  let seen = false;
  for (const p of prices) {
    if (!Number.isFinite(p)) continue;
    seen = true;
    const s = String(p);
    const i = s.indexOf('.');
    if (i >= 0) dec = Math.max(dec, Math.min(s.length - i - 1, 4));
  }
  if (!seen) return fallback;
  return dec === 0 ? Math.min(fallback, 1) : Math.pow(10, -dec);
}

export function roundToTick(px: number, tick: number, mode: 'nearest' | 'down' | 'up' = 'nearest'): number {
  if (!(tick > 0)) return px;
  const n = px / tick;
  const r = mode === 'down' ? Math.floor(n + 1e-9) : mode === 'up' ? Math.ceil(n - 1e-9) : Math.round(n);
  const dec = Math.max(0, Math.ceil(-Math.log10(tick) - 1e-9));
  return Number((r * tick).toFixed(dec));
}

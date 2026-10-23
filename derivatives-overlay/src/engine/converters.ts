// Round 3: convert an analyst's "quantity linked to IV" into sigma (decimal, 0.45 = 45%).
import { price, probItm, vegaPerPoint } from './blackScholes';
import { impliedVol, IV_HI, IV_LO } from './impliedVol';
import { compileExpr } from './safeExpr';

export type ConverterId =
  | 'iv' | 'variance' | 'dailyMoveAbs' | 'dailyMovePct' | 'expiryMovePct' | 'atmStraddle'
  | 'callPrice' | 'putPrice' | 'probItmCall' | 'probItmPut' | 'vegaPerPoint' | 'custom';

export interface ConvCtx {
  S: number;
  T: number;
  K?: number;
  /** ATM-nearest strike for straddles */
  strikes?: number[];
  formula?: string;
  /** branch preference for non-monotone inversions */
  prior?: number;
  varianceUnit?: 'auto' | 'decimal' | 'pct2';
}

export interface ConvResult {
  sigma: number | null;
  note?: string;
  approx?: number | null;
}

export const CONVERTERS: { id: ConverterId; label: string; needsK?: boolean }[] = [
  { id: 'iv', label: 'IV (%, or decimal)' },
  { id: 'variance', label: 'Annual variance (decimal or %²)' },
  { id: 'dailyMoveAbs', label: 'Daily move $' },
  { id: 'dailyMovePct', label: 'Daily move %' },
  { id: 'expiryMovePct', label: 'Move to expiry %' },
  { id: 'atmStraddle', label: 'ATM straddle $' },
  { id: 'callPrice', label: 'Call price @K', needsK: true },
  { id: 'putPrice', label: 'Put price @K', needsK: true },
  { id: 'probItmCall', label: 'P(call ITM) @K', needsK: true },
  { id: 'probItmPut', label: 'P(put ITM) @K', needsK: true },
  { id: 'vegaPerPoint', label: 'Vega per vol pt @K', needsK: true },
  { id: 'custom', label: 'Custom formula (x S T K)' },
];

/** Percent-vs-decimal rule shared with the headline parser: a value with % or above 3 is a percent. */
export function normalizeVol(value: number, hasPct = false): number {
  return hasPct || value > 3 ? value / 100 : value;
}

export function nearestStrike(S: number, strikes: number[] | undefined): number {
  if (!strikes?.length) return S;
  return strikes.reduce((b, k) => (Math.abs(k - S) < Math.abs(b - S) ? k : b), strikes[0]);
}

function bisect(f: (s: number) => number, target: number, lo: number, hi: number): number | null {
  let flo = f(lo) - target;
  const fhi = f(hi) - target;
  if (!Number.isFinite(flo) || !Number.isFinite(fhi) || flo * fhi > 0) return null;
  for (let i = 0; i < 200; i++) {
    const m = 0.5 * (lo + hi);
    const fm = f(m) - target;
    if (Math.abs(fm) < 1e-13 || hi - lo < 1e-13) return m;
    if (fm * flo > 0) { lo = m; flo = fm; } else hi = m;
  }
  return 0.5 * (lo + hi);
}

export function convertToSigma(id: ConverterId, x: number, ctx: ConvCtx): ConvResult {
  const { S, T } = ctx;
  if (!Number.isFinite(x)) return { sigma: null, note: 'no value' };
  const K = ctx.K ?? nearestStrike(S, ctx.strikes);
  switch (id) {
    case 'iv': return { sigma: normalizeVol(x) };
    case 'variance': {
      const unit = ctx.varianceUnit ?? 'auto';
      const pct2 = unit === 'pct2' || (unit === 'auto' && x > 9);
      if (x < 0) return { sigma: null, note: 'negative variance' };
      return { sigma: pct2 ? Math.sqrt(x) / 100 : Math.sqrt(x), note: pct2 ? 'read as %²' : 'read as decimal' };
    }
    case 'dailyMoveAbs': return S > 0 ? { sigma: (x / S) * Math.sqrt(252) } : { sigma: null };
    case 'dailyMovePct': return { sigma: (x / 100) * Math.sqrt(252) };
    case 'expiryMovePct': return T > 0 ? { sigma: x / 100 / Math.sqrt(T) } : { sigma: null };
    case 'atmStraddle': {
      if (!(T > 0) || !(S > 0)) return { sigma: null };
      const f = (s: number) => price('C', S, K, s, T) + price('P', S, K, s, T);
      const sigma = bisect(f, x, IV_LO, IV_HI);
      return { sigma, approx: x / (0.8 * S * Math.sqrt(T)), note: `exact BS straddle at K=${K}` };
    }
    case 'callPrice': return { sigma: impliedVol('C', x, S, K, T) };
    case 'putPrice': return { sigma: impliedVol('P', x, S, K, T) };
    case 'probItmCall':
    case 'probItmPut': {
      if (!(T > 0) || !(x > 0 && x < 1)) return { sigma: null, note: 'probability must be in (0,1)' };
      const kind = id === 'probItmCall' ? 'C' : 'P';
      const a = Math.log(S / K);
      // d2(s) is monotone decreasing in s=σ√T when a >= 0; when a < 0 it rises to a peak at s = √(2|a|).
      // Use the lower-vol branch, which contains the usual solution.
      const hi = a < 0 ? Math.min(Math.sqrt(2 * -a) / Math.sqrt(T), IV_HI) : IV_HI;
      const sigma = bisect((s) => probItm(kind, S, K, s, T), x, IV_LO, hi);
      return { sigma, note: sigma == null ? 'no solution on the low-vol branch' : undefined };
    }
    case 'vegaPerPoint': {
      if (!(T > 0) || !(x > 0)) return { sigma: null };
      const a = Math.abs(Math.log(S / K));
      const peak = Math.min(Math.max(Math.sqrt(2 * a) / Math.sqrt(T), IV_LO * 2), IV_HI);
      const f = (s: number) => vegaPerPoint(S, K, s, T);
      const roots = [bisect(f, x, IV_LO, peak), bisect(f, x, peak, IV_HI)].filter((r): r is number => r != null);
      if (!roots.length) return { sigma: null, note: 'vega out of range' };
      const prior = ctx.prior ?? 0.5;
      const sigma = roots.reduce((b, r) => (Math.abs(r - prior) < Math.abs(b - prior) ? r : b), roots[0]);
      return { sigma, note: roots.length > 1 ? `two roots (${roots.map((r) => (r * 100).toFixed(1)).join('%, ')}%); picked nearest ${(prior * 100).toFixed(0)}%` : undefined };
    }
    case 'custom': {
      const c = compileExpr(ctx.formula ?? 'x');
      if (!c.ok) return { sigma: null, note: c.error };
      try {
        const v = c.run({ x, S, T, K });
        return Number.isFinite(v) ? { sigma: v } : { sigma: null, note: 'formula gave a non-finite value' };
      } catch (e) {
        return { sigma: null, note: e instanceof Error ? e.message : String(e) };
      }
    }
  }
}

/** Forward map (sigma -> quantity), used for round-trip tests and the "what would analysts say" preview. */
export function sigmaToQuantity(id: ConverterId, sigma: number, ctx: ConvCtx): number | null {
  const { S, T } = ctx;
  const K = ctx.K ?? nearestStrike(S, ctx.strikes);
  switch (id) {
    case 'iv': return sigma;
    case 'variance': return ctx.varianceUnit === 'pct2' ? (sigma * 100) ** 2 : sigma * sigma;
    case 'dailyMoveAbs': return (sigma / Math.sqrt(252)) * S;
    case 'dailyMovePct': return (sigma / Math.sqrt(252)) * 100;
    case 'expiryMovePct': return sigma * Math.sqrt(T) * 100;
    case 'atmStraddle': return price('C', S, K, sigma, T) + price('P', S, K, sigma, T);
    case 'callPrice': return price('C', S, K, sigma, T);
    case 'putPrice': return price('P', S, K, sigma, T);
    case 'probItmCall': return probItm('C', S, K, sigma, T);
    case 'probItmPut': return probItm('P', S, K, sigma, T);
    case 'vegaPerPoint': return vegaPerPoint(S, K, sigma, T);
    case 'custom': return null;
  }
}

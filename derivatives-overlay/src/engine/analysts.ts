// Analyst blending and post-snap learning. Vols are decimals (0.45 = 45%).
import { median } from './chain';

export type AnalystId = 1 | 2 | 3;
export const ANALYSTS: AnalystId[] = [1, 2, 3];

export interface AnalystRecord {
  event: number;
  underlying: string;
  /** sigma estimates after any Round 3 conversion */
  estimates: Partial<Record<AnalystId, number>>;
  trueVol: number;
  t: number;
}

export interface AnalystStats {
  n: number;
  mse: number | null;
  rmse: number | null;
  bias: number | null;
  lastErr: number | null;
}

export type BlendMode = 'median' | 'weighted' | `single:${AnalystId}`;
export type BandMode = 'auto' | 'minmax' | 'dispersion';

export interface BlendOpts {
  mode: BlendMode;
  /** prior variance for shrinkage, decimal² (default (5 vol pts)² = 0.0025) */
  lambda: number;
  /** dispersion multiplier for the band */
  k: number;
  bandMode: BandMode;
}

export const DEFAULT_BLEND: BlendOpts = { mode: 'median', lambda: 0.0025, k: 1, bandMode: 'auto' };

export interface BlendResult {
  vol: number | null;
  low: number | null;
  high: number | null;
  weights: Partial<Record<AnalystId, number>>;
  mode: BlendMode;
  note: string;
}

function statsOf(errs: number[]): AnalystStats {
  if (!errs.length) return { n: 0, mse: null, rmse: null, bias: null, lastErr: null };
  const mse = errs.reduce((s, e) => s + e * e, 0) / errs.length;
  return { n: errs.length, mse, rmse: Math.sqrt(mse), bias: errs.reduce((s, e) => s + e, 0) / errs.length, lastErr: errs[errs.length - 1] };
}

/** Error = estimate - truth. `underlying` undefined = pooled across underlyings. */
export function analystStats(history: AnalystRecord[], underlying?: string): Record<AnalystId, AnalystStats> {
  const out = {} as Record<AnalystId, AnalystStats>;
  for (const a of ANALYSTS) {
    const errs = history
      .filter((r) => underlying == null || r.underlying === underlying)
      .sort((x, y) => x.event - y.event || x.t - y.t)
      .map((r) => (r.estimates[a] != null ? (r.estimates[a] as number) - r.trueVol : null))
      .filter((e): e is number => e != null && Number.isFinite(e));
    out[a] = statsOf(errs);
  }
  return out;
}

/** Effective MSE: per-underlying MSE shrunk toward the pooled MSE (pooled counts as one pseudo-observation). */
export function effectiveMse(history: AnalystRecord[], underlying: string, a: AnalystId): number | null {
  const u = analystStats(history, underlying)[a];
  const p = analystStats(history)[a];
  if (u.mse == null && p.mse == null) return null;
  if (u.mse == null) return p.mse;
  if (p.mse == null) return u.mse;
  return (u.n * u.mse + p.mse) / (u.n + 1);
}

/** w_i ∝ 1/(MSE_i + λ); analysts with no history get MSE = λ (prior). Only analysts present are weighted. */
export function analystWeights(history: AnalystRecord[], underlying: string, present: AnalystId[], lambda: number): Partial<Record<AnalystId, number>> {
  const raw: Partial<Record<AnalystId, number>> = {};
  let sum = 0;
  for (const a of present) {
    const m = effectiveMse(history, underlying, a) ?? lambda;
    const w = 1 / (m + lambda);
    raw[a] = w;
    sum += w;
  }
  for (const a of present) raw[a] = (raw[a] as number) / sum;
  return raw;
}

export function blendAnalysts(
  estimates: Partial<Record<AnalystId, number | null | undefined>>,
  underlying: string,
  history: AnalystRecord[],
  opts: BlendOpts = DEFAULT_BLEND,
): BlendResult {
  const present = ANALYSTS.filter((a) => estimates[a] != null && Number.isFinite(estimates[a] as number) && (estimates[a] as number) > 0);
  const vals = present.map((a) => estimates[a] as number);
  if (!present.length) return { vol: null, low: null, high: null, weights: {}, mode: opts.mode, note: 'no analyst values' };
  const weights = analystWeights(history, underlying, present, opts.lambda);
  let vol: number;
  let mode = opts.mode;
  if (mode.startsWith('single:')) {
    const a = Number(mode.slice(7)) as AnalystId;
    if (estimates[a] != null) vol = estimates[a] as number;
    else {
      mode = 'median';
      vol = median(vals) as number;
    }
  } else if (mode === 'weighted') {
    vol = present.reduce((s, a) => s + (weights[a] as number) * (estimates[a] as number), 0);
  } else {
    vol = median(vals) as number;
  }
  const hasHistory = history.some((r) => r.underlying === underlying) || history.length > 0;
  const bandMode = opts.bandMode === 'auto' ? (hasHistory && mode !== 'median' ? 'dispersion' : 'minmax') : opts.bandMode;
  let low: number;
  let high: number;
  let note: string;
  if (bandMode === 'minmax') {
    const disp = hasHistory ? Math.sqrt(present.reduce((s, a) => s + (weights[a] as number) * (effectiveMse(history, underlying, a) ?? 0), 0)) : 0;
    low = Math.min(...vals, vol - opts.k * disp);
    high = Math.max(...vals, vol + opts.k * disp);
    note = `band = analyst min/max${disp ? ` widened by ${opts.k}×${(disp * 100).toFixed(1)}pts` : ''}`;
  } else {
    let disp: number;
    if (mode.startsWith('single:')) {
      const a = Number(mode.slice(7)) as AnalystId;
      disp = Math.sqrt(effectiveMse(history, underlying, a) ?? opts.lambda);
    } else {
      disp = Math.sqrt(present.reduce((s, a) => s + (weights[a] as number) * (effectiveMse(history, underlying, a) ?? opts.lambda), 0));
    }
    low = vol - opts.k * disp;
    high = vol + opts.k * disp;
    note = `band = blend ± ${opts.k}×${(disp * 100).toFixed(1)}pts`;
  }
  return { vol, low: Math.max(low, 1e-4), high, weights, mode, note };
}

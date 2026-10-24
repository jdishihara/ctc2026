// Implied vol by safeguarded Newton with a bisection fallback on [1e-4, 10].
import { Kind, discountedIntrinsic, price, vegaPerPoint } from './blackScholes';

export const IV_LO = 1e-4;
export const IV_HI = 10;

export function impliedVol(kind: Kind, px: number, S: number, K: number, T: number, tol = 1e-8): number | null {
  if (!Number.isFinite(px) || !(S > 0) || !(K > 0) || !(T > 0)) return null;
  const intr = discountedIntrinsic(kind, S, K, T);
  const upper = kind === 'C' ? S : K;
  if (px < intr - 1e-9 || px > upper + 1e-9) return null;
  let lo = IV_LO;
  let hi = IV_HI;
  const fLo = price(kind, S, K, lo, T) - px;
  const fHi = price(kind, S, K, hi, T) - px;
  if (fLo >= 0) return lo; // at or below the lowest representable vol: effectively intrinsic
  if (fHi < 0) return null; // needs more than 1000% vol
  // Brenner-Subrahmanyam start, clamped into the bracket.
  let x = Math.min(Math.max((Math.sqrt((2 * Math.PI) / T) * px) / S, 0.05), 3);
  for (let i = 0; i < 100; i++) {
    const f = price(kind, S, K, x, T) - px;
    if (Math.abs(f) < tol) return x;
    if (f > 0) hi = x;
    else lo = x;
    const v = vegaPerPoint(S, K, x, T) * 100;
    let next = v > 1e-12 ? x - f / v : NaN;
    if (!(next > lo && next < hi)) next = 0.5 * (lo + hi);
    if (hi - lo < 1e-14) return next;
    x = next;
  }
  return x;
}

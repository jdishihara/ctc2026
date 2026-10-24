// Black-Scholes matching the exchange's own "Fair" calculator (read from the trading page's bundle, 2026-10-24):
// T in years (= trading days / 252), continuous rate r (the chain's risk_free_rate; 0 unless the exchange says
// otherwise), no dividends, vega per 1 vol point, theta per trading day.
import { normCdf, normPdf } from './normal';

export type Kind = 'C' | 'P';

export interface Greeks {
  price: number;
  delta: number;
  gamma: number;
  vegaPerPoint: number;
  thetaPerDay: number;
}

/** Module-wide risk-free rate. The store sets it from the chain endpoint; every pricing call reads it by default. */
let RATE = 0;
export function setRate(r: number): void {
  RATE = Number.isFinite(r) ? r : 0;
}
export function getRate(): number {
  return RATE;
}

export function intrinsic(kind: Kind, S: number, K: number): number {
  return kind === 'C' ? Math.max(S - K, 0) : Math.max(K - S, 0);
}

/** Intrinsic against the discounted strike (what the exchange shows when vol or T is zero). */
export function discountedIntrinsic(kind: Kind, S: number, K: number, T: number, r = RATE): number {
  const Kd = T > 0 ? K * Math.exp(-r * T) : K;
  return kind === 'C' ? Math.max(S - Kd, 0) : Math.max(Kd - S, 0);
}

function degenerate(S: number, K: number, sigma: number, T: number): boolean {
  return !(T > 0) || !(sigma > 0) || !(S > 0) || !(K > 0);
}

function d1d2(S: number, K: number, sigma: number, T: number, r: number): [number, number] {
  const sd = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sd;
  return [d1, d1 - sd];
}

export function price(kind: Kind, S: number, K: number, sigma: number, T: number, r = RATE): number {
  if (degenerate(S, K, sigma, T)) return discountedIntrinsic(kind, Math.max(S, 0), Math.max(K, 0), T, r);
  const [d1, d2] = d1d2(S, K, sigma, T, r);
  const Kd = K * Math.exp(-r * T);
  return kind === 'C' ? S * normCdf(d1) - Kd * normCdf(d2) : Kd * normCdf(-d2) - S * normCdf(-d1);
}

export function delta(kind: Kind, S: number, K: number, sigma: number, T: number, r = RATE): number {
  if (degenerate(S, K, sigma, T)) {
    if (kind === 'C') return S > K ? 1 : 0;
    return S < K ? -1 : 0;
  }
  const [d1] = d1d2(S, K, sigma, T, r);
  return kind === 'C' ? normCdf(d1) : normCdf(d1) - 1;
}

export function gamma(S: number, K: number, sigma: number, T: number, r = RATE): number {
  if (degenerate(S, K, sigma, T)) return 0;
  const [d1] = d1d2(S, K, sigma, T, r);
  return normPdf(d1) / (S * sigma * Math.sqrt(T));
}

export function vegaPerPoint(S: number, K: number, sigma: number, T: number, r = RATE): number {
  if (degenerate(S, K, sigma, T)) return 0;
  const [d1] = d1d2(S, K, sigma, T, r);
  return (S * normPdf(d1) * Math.sqrt(T)) / 100;
}

export function thetaPerDay(S: number, K: number, sigma: number, T: number, r = RATE, kind: Kind = 'C'): number {
  if (degenerate(S, K, sigma, T)) return 0;
  const [d1, d2] = d1d2(S, K, sigma, T, r);
  const o = kind === 'C' ? 1 : -1;
  const carry = r === 0 ? 0 : o * r * K * Math.exp(-r * T) * normCdf(o * d2);
  return (-(S * normPdf(d1) * sigma) / (2 * Math.sqrt(T)) - carry) / 252;
}

export function greeks(kind: Kind, S: number, K: number, sigma: number, T: number, r = RATE): Greeks {
  return {
    price: price(kind, S, K, sigma, T, r),
    delta: delta(kind, S, K, sigma, T, r),
    gamma: gamma(S, K, sigma, T, r),
    vegaPerPoint: vegaPerPoint(S, K, sigma, T, r),
    thetaPerDay: thetaPerDay(S, K, sigma, T, r, kind),
  };
}

/** P(option finishes in the money) under the pricing measure: N(d2) for calls, N(-d2) for puts. */
export function probItm(kind: Kind, S: number, K: number, sigma: number, T: number, r = RATE): number {
  if (degenerate(S, K, sigma, T)) return intrinsic(kind, S, K) > 0 ? 1 : 0;
  const [, d2] = d1d2(S, K, sigma, T, r);
  return kind === 'C' ? normCdf(d2) : normCdf(-d2);
}

// Black-Scholes with r = 0 and no dividends, matching the exchange "Fair" calculator:
// T in years (= trading days / 252), vega per 1 vol point, theta per trading day.
import { normCdf, normPdf } from './normal';

export type Kind = 'C' | 'P';

export interface Greeks {
  price: number;
  delta: number;
  gamma: number;
  vegaPerPoint: number;
  thetaPerDay: number;
}

export function intrinsic(kind: Kind, S: number, K: number): number {
  return kind === 'C' ? Math.max(S - K, 0) : Math.max(K - S, 0);
}

function degenerate(S: number, K: number, sigma: number, T: number): boolean {
  return !(T > 0) || !(sigma > 0) || !(S > 0) || !(K > 0);
}

function d1d2(S: number, K: number, sigma: number, T: number): [number, number] {
  const sd = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + 0.5 * sd * sd) / sd;
  return [d1, d1 - sd];
}

export function price(kind: Kind, S: number, K: number, sigma: number, T: number): number {
  if (degenerate(S, K, sigma, T)) return intrinsic(kind, Math.max(S, 0), Math.max(K, 0));
  const [d1, d2] = d1d2(S, K, sigma, T);
  return kind === 'C' ? S * normCdf(d1) - K * normCdf(d2) : K * normCdf(-d2) - S * normCdf(-d1);
}

export function delta(kind: Kind, S: number, K: number, sigma: number, T: number): number {
  if (degenerate(S, K, sigma, T)) {
    if (kind === 'C') return S > K ? 1 : 0;
    return S < K ? -1 : 0;
  }
  const [d1] = d1d2(S, K, sigma, T);
  return kind === 'C' ? normCdf(d1) : normCdf(d1) - 1;
}

export function gamma(S: number, K: number, sigma: number, T: number): number {
  if (degenerate(S, K, sigma, T)) return 0;
  const [d1] = d1d2(S, K, sigma, T);
  return normPdf(d1) / (S * sigma * Math.sqrt(T));
}

export function vegaPerPoint(S: number, K: number, sigma: number, T: number): number {
  if (degenerate(S, K, sigma, T)) return 0;
  const [d1] = d1d2(S, K, sigma, T);
  return (S * normPdf(d1) * Math.sqrt(T)) / 100;
}

export function thetaPerDay(S: number, K: number, sigma: number, T: number): number {
  if (degenerate(S, K, sigma, T)) return 0;
  const [d1] = d1d2(S, K, sigma, T);
  return -(S * normPdf(d1) * sigma) / (2 * Math.sqrt(T)) / 252;
}

export function greeks(kind: Kind, S: number, K: number, sigma: number, T: number): Greeks {
  return {
    price: price(kind, S, K, sigma, T),
    delta: delta(kind, S, K, sigma, T),
    gamma: gamma(S, K, sigma, T),
    vegaPerPoint: vegaPerPoint(S, K, sigma, T),
    thetaPerDay: thetaPerDay(S, K, sigma, T),
  };
}

/** P(option finishes in the money) under the pricing measure: N(d2) for calls, N(-d2) for puts. */
export function probItm(kind: Kind, S: number, K: number, sigma: number, T: number): number {
  if (degenerate(S, K, sigma, T)) return intrinsic(kind, S, K) > 0 ? 1 : 0;
  const [, d2] = d1d2(S, K, sigma, T);
  return kind === 'C' ? normCdf(d2) : normCdf(-d2);
}

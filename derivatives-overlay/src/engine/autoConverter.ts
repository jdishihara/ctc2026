// Round 3 auto-identification: which "quantity linked to IV" are the analysts quoting? Try every converter on the raw
// numbers and keep the one whose sigma lands nearest the market IV, preferring a converter the message names.
import { CONVERTERS, ConverterId, convertToSigma } from './converters';

export interface ConverterSample {
  underlying: string;
  raw: number;
  /** the number as written, e.g. "4.4%" or "$1.52" */
  rawStr?: string;
}

export interface IdentifyInput {
  samples: ConverterSample[];
  /** the analyst message text (keyword hints) */
  text: string;
  marketIV: Record<string, number | null | undefined>;
  spot: Record<string, number | null | undefined>;
  /** years to expiry */
  T: number;
  strikes?: Record<string, number[] | undefined>;
  tolPts: number;
  tieMarginPts: number;
}

export interface ConverterCandidate {
  id: ConverterId;
  /** median |sigma - market IV| over the samples, in vol points */
  errPts: number;
  /** median sigma over the samples */
  sigma: number;
  keyword: boolean;
}

export interface IdentifyResult {
  id: ConverterId | null;
  reason: string;
  ranked: ConverterCandidate[];
}

const KEYWORDS: Partial<Record<ConverterId, RegExp>> = {
  variance: /\bvarian/i,
  dailyMoveAbs: /\b(daily|one[- ]day|1[- ]day)\b[^.%]{0,30}\$|\$[^.]{0,20}\b(daily|per day|a day)\b|dollar (move|range)/i,
  dailyMovePct: /\b(daily|one[- ]day|1[- ]day)\b[^.$]{0,30}(%|percent|move|range|vol)|\bper[- ]day\b/i,
  expiryMovePct: /(expected|implied|typical)?\s*move\b[^.]{0,30}\b(to|by|at|through|until)\s+expir|\bexpiry move|\bmove to expiry|\bterminal\b/i,
  atmStraddle: /\bstraddle/i,
  callPrice: /\bcall\b[^.]{0,20}\b(price|premium|worth|trades?|quoted?)|\b(price|premium) of (the|a) call/i,
  putPrice: /\bput\b[^.]{0,20}\b(price|premium|worth|trades?|quoted?)|\b(price|premium) of (the|a) put/i,
  probItmCall: /\b(probab|chance|likelihood|odds)[^.]{0,40}\b(above|over|exceed|finish(es|ing)? above|call)|\bcall\b[^.]{0,20}\b(in[- ]the[- ]money|ITM)/i,
  probItmPut: /\b(probab|chance|likelihood|odds)[^.]{0,40}\b(below|under|finish(es|ing)? below|put)|\bput\b[^.]{0,20}\b(in[- ]the[- ]money|ITM)/i,
  vegaPerPoint: /\bvega\b/i,
  iv: /\b(implied vol(atility)?|IV|sigma|σ|volatility)\b/i,
};

const MONEY_IDS: ConverterId[] = ['dailyMoveAbs', 'atmStraddle', 'callPrice', 'putPrice', 'vegaPerPoint'];
const PCT_IDS: ConverterId[] = ['iv', 'dailyMovePct', 'expiryMovePct', 'variance'];

const median = (xs: number[]) => {
  const a = [...xs].sort((x, y) => x - y);
  return a.length ? (a.length % 2 ? a[(a.length - 1) / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2) : NaN;
};

/** Candidate converters ranked by distance to the market IV. Pure; no DOM, no store. */
export function identifyConverter(inp: IdentifyInput): IdentifyResult {
  const text = inp.text ?? '';
  const anyDollar = inp.samples.some((s) => /\$/.test(s.rawStr ?? ''));
  const anyPct = inp.samples.some((s) => /%/.test(s.rawStr ?? ''));
  const ranked: ConverterCandidate[] = [];
  for (const { id } of CONVERTERS) {
    if (id === 'custom') continue;
    if (anyDollar && !MONEY_IDS.includes(id)) continue;
    if (anyPct && !PCT_IDS.includes(id)) continue;
    const errs: number[] = [];
    const sigmas: number[] = [];
    for (const smp of inp.samples) {
      const S = inp.spot[smp.underlying];
      const iv = inp.marketIV[smp.underlying];
      if (S == null || iv == null || !(S > 0) || !(iv > 0)) continue;
      const r = convertToSigma(id, smp.raw, { S, T: inp.T, strikes: inp.strikes?.[smp.underlying], prior: iv });
      if (r.sigma == null || !Number.isFinite(r.sigma) || r.sigma <= 0) continue;
      sigmas.push(r.sigma);
      errs.push(Math.abs(r.sigma - iv) * 100);
    }
    if (!errs.length) continue;
    ranked.push({ id, errPts: median(errs), sigma: median(sigmas), keyword: !!KEYWORDS[id]?.test(text) });
  }
  ranked.sort((a, b) => a.errPts - b.errPts);
  if (!ranked.length) return { id: null, reason: 'no converter could be evaluated (need a spot and a market IV)', ranked };
  const within = ranked.filter((c) => c.errPts <= inp.tolPts);
  const fmt = (c: ConverterCandidate) => `${c.id} (σ ${(c.sigma * 100).toFixed(1)}%, off ${c.errPts.toFixed(1)} pts)`;
  if (!within.length) {
    return { id: null, reason: `nothing within ${inp.tolPts} vol pts of the market IV; closest ${fmt(ranked[0])}. Pick the converter by hand.`, ranked };
  }
  const named = within.filter((c) => c.keyword);
  if (named.length === 1) return { id: named[0].id, reason: `message names it and it matches the market IV: ${fmt(named[0])}`, ranked };
  if (named.length > 1 && named[1].errPts - named[0].errPts >= inp.tieMarginPts) {
    return { id: named[0].id, reason: `several named, nearest market IV: ${fmt(named[0])} vs ${fmt(named[1])}`, ranked };
  }
  const best = within[0];
  const second = ranked[1];
  if (second && second.errPts - best.errPts < inp.tieMarginPts) {
    return { id: null, reason: `ambiguous: ${fmt(best)} vs ${fmt(second)}. Pick the converter by hand.`, ranked };
  }
  return { id: best.id, reason: `nearest the market IV: ${fmt(best)}${second ? `; next ${fmt(second)}` : ''}`, ranked };
}

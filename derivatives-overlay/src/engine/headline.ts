// Tolerant headline parser. It only produces suggestions (shown amber); nothing is traded from a parse.
import { normalizeVol } from './converters';

export interface UnderlyingParse {
  spot?: number;
  spotRaw?: string;
  iv?: number;
  ivRaw?: string;
  changePct?: number; // signed % move when no absolute price is given
}

export interface AnalystParse {
  analyst: 1 | 2 | 3;
  underlying: string;
  value: number; // read as a vol: decimal via the % / >3 rule
  rawValue: number; // the number as written (Round 3 converters use this)
  raw: string;
  hasPct: boolean;
  isVol: boolean;
}

export interface HeadlineParse {
  underlyings: Record<string, UnderlyingParse>;
  analysts: AnalystParse[];
  mentions: string[];
}

export interface HeadlineConfig {
  aliases: Record<string, string[]>; // underlying -> regex sources
}

export const DEFAULT_HEADLINE_CONFIG: HeadlineConfig = {
  aliases: {
    OIL: ['\\boil\\b', '\\bcrude\\b', '\\bbrent\\b', '\\bOIL\\b', '\\bbarrel'],
    PLANE: ['\\bPLANE\\b', '\\bNew\\s?Air\\b', '\\bairline', '\\bplane\\b'],
  },
};

const VOL_RE = /\b(?:implied\s+vol(?:atility)?|IV|vol(?:atility)?|sigma|σ)\b/i;
const ANALYST_RE = /\banalyst\s*#?\s*(1|2|3|one|two|three)\b/i;
const WORD_NUM: Record<string, 1 | 2 | 3> = { '1': 1, '2': 2, '3': 3, one: 1, two: 2, three: 3 };
const UP_RE = /\b(?:rise[sn]?|rose|jump(?:s|ed)?|climb(?:s|ed)?|gain(?:s|ed)?|up|soar(?:s|ed)?|rall(?:y|ies|ied)|surge[sd]?|spike[sd]?)\b/i;
const DOWN_RE = /\b(?:fall(?:s|en)?|fell|drop(?:s|ped)?|down|plunge[sd]?|slide[sd]?|slid|sink(?:s)?|sank|decline[sd]?|tumble[sd]?|crash(?:es|ed)?|slump(?:s|ed)?)\b/i;

interface Marker {
  i: number;
  end: number;
  kind: 'und' | 'analyst' | 'num';
  und?: string;
  analyst?: 1 | 2 | 3;
  value?: number;
  raw?: string;
  pct?: boolean;
  dollar?: boolean;
}

export function parseHeadline(text: string, cfg: HeadlineConfig = DEFAULT_HEADLINE_CONFIG): HeadlineParse {
  const res: HeadlineParse = { underlyings: {}, analysts: [], mentions: [] };
  if (!text || typeof text !== 'string') return res;
  const markers: Marker[] = [];
  for (const [und, pats] of Object.entries(cfg.aliases)) {
    for (const p of pats) {
      let re: RegExp;
      try { re = new RegExp(p, 'gi'); } catch { continue; }
      for (const m of text.matchAll(re)) markers.push({ i: m.index ?? 0, end: (m.index ?? 0) + m[0].length, kind: 'und', und });
    }
  }
  for (const m of text.matchAll(new RegExp(ANALYST_RE.source, 'gi'))) {
    markers.push({ i: m.index ?? 0, end: (m.index ?? 0) + m[0].length, kind: 'analyst', analyst: WORD_NUM[m[1].toLowerCase()] });
  }
  // numbers: skip times (10:22), dates (2026-06-01), and digits glued to letters/underscores (OIL_0626_C100)
  const numRe = /(\$\s?)?(?<![\w.:\-/])(\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)(?![\w:]|\.\d|-\d)(\s?%)?/g;
  for (const m of text.matchAll(numRe)) {
    const i = m.index ?? 0;
    const inside = markers.some((k) => k.kind === 'analyst' && i >= k.i && i < k.end);
    if (inside) continue;
    const value = Number(m[2].replace(/,/g, ''));
    if (!Number.isFinite(value)) continue;
    markers.push({ i, end: i + m[0].length, kind: 'num', value, raw: m[0].trim(), pct: !!m[3], dollar: !!m[1] });
  }
  markers.sort((a, b) => a.i - b.i || (a.kind === 'num' ? 1 : -1));
  // de-duplicate overlapping underlying aliases
  const ms: Marker[] = [];
  for (const m of markers) {
    const prev = ms[ms.length - 1];
    if (prev && m.kind === 'und' && prev.kind === 'und' && m.i < prev.end) continue;
    ms.push(m);
  }

  let curUnd: string | null = null;
  let curAnalyst: 1 | 2 | 3 | null = null;
  let lastIdx = 0;
  const mentions = new Set<string>();
  for (const m of ms) {
    if (m.kind === 'und') {
      curUnd = m.und as string;
      mentions.add(curUnd);
      lastIdx = m.end;
      continue;
    }
    if (m.kind === 'analyst') {
      curAnalyst = m.analyst as 1 | 2 | 3;
      lastIdx = m.end;
      continue;
    }
    // a sentence boundary between the context and the number resets the analyst context
    const gap = text.slice(lastIdx, m.i);
    if (/[.;!?]\s|\n/.test(gap) && !/\banalyst/i.test(gap)) curAnalyst = null;
    let before = text.slice(Math.max(0, m.i - 28), m.i);
    // a vol cue does not carry across a sentence boundary ("... implied vol now 65%. PLANE holds at 40.00" -> 40 is a spot)
    const boundary = /^[\s\S]*[.;!?]\s+/.exec(before);
    if (boundary) before = before.slice(boundary[0].length);
    const after = text.slice(m.end, m.end + 16);
    lastIdx = m.end;
    if (!curUnd) continue;
    if (/\btariff|\bpercent of\b|\bday|\bweek|\bmonth|\byear|\bround|\bevent|\bdeaths?|\bkilled|\bpassengers?|\bflights?/i.test(before.slice(-16) + ' ' + after)) {
      // "one-day move 4.4%" is a quantity, not a date
      if (!VOL_RE.test(before) && !/\b(move|range|straddle|varian|premium|probab|chance)/i.test(before)) continue;
    }
    const volCue = VOL_RE.test(before) || /^\s*%?\s*(?:implied\s+)?vol/i.test(after);
    const value = m.value as number;
    if (curAnalyst != null) {
      res.analysts.push({
        analyst: curAnalyst, underlying: curUnd, raw: m.raw as string, hasPct: !!m.pct, isVol: volCue,
        value: normalizeVol(value, m.pct), rawValue: value,
      });
      continue;
    }
    const u = (res.underlyings[curUnd] ??= {});
    if (volCue) {
      if (u.iv == null) {
        u.iv = normalizeVol(value, m.pct);
        u.ivRaw = m.raw;
      }
    } else if (m.pct) {
      const ctx = text.slice(Math.max(0, m.i - 40), m.i);
      const sign = DOWN_RE.test(ctx) ? -1 : UP_RE.test(ctx) ? 1 : 0;
      if (sign && u.changePct == null) u.changePct = sign * value;
    } else if (u.spot == null && value > 0) {
      u.spot = value;
      u.spotRaw = m.raw;
    }
  }
  for (const [k, v] of Object.entries(res.underlyings)) if (!Object.keys(v).length) delete res.underlyings[k];
  res.mentions = [...mentions];
  return res;
}

/** Pull numbers out of a structured news message (unknown schema): keys named after underlyings with spot/iv-ish fields. */
export function extractStructured(msg: unknown, underlyings: string[]): Record<string, UnderlyingParse> {
  const out: Record<string, UnderlyingParse> = {};
  const seen = new Set<unknown>();
  const SPOT_KEYS = /^(spot|price|new_price|newprice|underlying_price|px|level|value)$/i;
  const IV_KEYS = /^(iv|vol|volatility|implied_vol|impliedvol|new_iv|sigma)$/i;
  const visit = (o: unknown, ctxUnd: string | null, depth: number) => {
    if (!o || typeof o !== 'object' || depth > 5 || seen.has(o)) return;
    seen.add(o);
    const rec = o as Record<string, unknown>;
    let und = ctxUnd;
    const symField = rec.symbol ?? rec.underlying ?? rec.asset;
    if (typeof symField === 'string' && underlyings.includes(symField.toUpperCase())) und = symField.toUpperCase();
    for (const [k, v] of Object.entries(rec)) {
      const ku = k.toUpperCase();
      if (underlyings.includes(ku)) {
        if (typeof v === 'number') (out[ku] ??= {}).spot = v;
        else visit(v, ku, depth + 1);
        continue;
      }
      const m = /^(OIL|PLANE)_(.+)$/i.exec(k);
      if (m && typeof v === 'number' && underlyings.includes(m[1].toUpperCase())) {
        const u = (out[m[1].toUpperCase()] ??= {});
        if (IV_KEYS.test(m[2])) u.iv = normalizeVol(v);
        else if (SPOT_KEYS.test(m[2])) u.spot = v;
        continue;
      }
      if (und && typeof v === 'number') {
        const u = (out[und] ??= {});
        if (IV_KEYS.test(k)) u.iv = normalizeVol(v);
        else if (SPOT_KEYS.test(k)) u.spot = v;
      } else if (typeof v === 'object') visit(v, und, depth + 1);
    }
  };
  visit(msg, null, 0);
  return out;
}

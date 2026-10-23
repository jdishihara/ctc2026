// Read-only DOM fallbacks. Everything is located by visible text, never by class names or ids.
import { DomHints } from './config';

export const norm = (s: string | null | undefined) => (s ?? '').replace(/\s+/g, ' ').trim();
export const textOf = (el: Element | null | undefined) => norm(el?.textContent);

export function isVisible(el: Element | null): boolean {
  let cur: Element | null = el;
  const win = el?.ownerDocument?.defaultView;
  while (cur) {
    if ((cur as HTMLElement).hidden) return false;
    try {
      const cs = win?.getComputedStyle(cur);
      if (cs && (cs.display === 'none' || cs.visibility === 'hidden')) return false;
    } catch {
      /* ignore */
    }
    cur = cur.parentElement;
  }
  return !!el;
}

function textNodes(root: ParentNode): Text[] {
  const doc = (root as Node).ownerDocument ?? (root as Document);
  const out: Text[] = [];
  try {
    const w = doc.createTreeWalker(root as Node, 4 /* NodeFilter.SHOW_TEXT */);
    for (let n = w.nextNode(); n; n = w.nextNode()) if ((n as Text).data.trim()) out.push(n as Text);
  } catch {
    /* ignore */
  }
  return out;
}

/**
 * Elements whose normalized text equals `text`, deepest only. Walks text nodes (not every element's textContent),
 * so it stays cheap on large pages.
 */
export function findByExactText(root: ParentNode, text: string, caseSensitive = true, skip?: (el: Element) => boolean): Element[] {
  const cmp = (s: string) => (caseSensitive ? s : s.toLowerCase());
  const want = cmp(norm(text));
  const out = new Set<Element>();
  for (const tn of textNodes(root)) {
    if (!cmp(norm(tn.data)).includes(want)) continue;
    let el = tn.parentElement;
    for (let up = 0; up < 3 && el; up++) {
      if (skip?.(el)) break;
      const t = cmp(textOf(el));
      if (t === want) {
        out.add(el);
        break;
      }
      if (t.length > want.length + 40) break;
      el = el.parentElement;
    }
  }
  return [...out];
}

/** Deepest elements (parent or up to 2 ancestors of a text node) whose text matches `re`, capped at maxLen. */
export function findByPattern(root: ParentNode, re: RegExp, maxLen = 80, skip?: (el: Element) => boolean): { el: Element; m: RegExpExecArray }[] {
  const out: { el: Element; m: RegExpExecArray }[] = [];
  const seen = new Set<Element>();
  for (const tn of textNodes(root)) {
    let el = tn.parentElement;
    for (let up = 0; up < 3 && el; up++) {
      if (seen.has(el) || skip?.(el)) break;
      const t = textOf(el);
      if (t.length > maxLen) break;
      const m = re.exec(t);
      if (m) {
        seen.add(el);
        out.push({ el, m });
        break;
      }
      el = el.parentElement;
    }
  }
  return out;
}

const parseNum = (s: string): number | null => {
  const t = s.replace(/[$,\s]/g, '');
  if (!/^-?\d*\.?\d+$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

export interface ChainCell {
  el: Element;
  value: number | null;
}

export interface DomChainRow {
  strike: number;
  rowEl: Element;
  C: { bid: ChainCell; ask: ChainCell; bidSize: ChainCell; askSize: ChainCell };
  P: { bid: ChainCell; ask: ChainCell; bidSize: ChainCell; askSize: ChainCell };
}

export interface DomChain {
  headerRow: Element;
  strikeIdx: number;
  rows: DomChainRow[];
}

function sideCols(labels: string[], from: number, to: number, positional: number[]): { bidSize: number; bid: number; ask: number; askSize: number } {
  const idx = (want: string) => {
    for (let i = from; i < to; i++) if (labels[i]?.toUpperCase() === want) return i;
    return -1;
  };
  const r = { bidSize: idx('BID SZ'), bid: idx('BID'), ask: idx('ASK'), askSize: idx('ASK SZ') };
  if (r.bid < 0 || r.ask < 0) return { bidSize: positional[0], bid: positional[1], ask: positional[2], askSize: positional[3] };
  if (r.bidSize < 0) r.bidSize = idx('BID SIZE');
  if (r.askSize < 0) r.askSize = idx('ASK SIZE');
  return r;
}

export function findChain(root: ParentNode, hints: DomHints, skip?: (el: Element) => boolean): DomChain | null {
  const strikeEls = findByExactText(root, hints.strikeHeader, false, skip);
  for (const sEl of strikeEls) {
    const headerRow = sEl.parentElement;
    if (!headerRow || headerRow.children.length < 5) continue;
    const kids = Array.from(headerRow.children);
    const strikeIdx = kids.indexOf(sEl);
    const labels = kids.map((k) => textOf(k));
    const n = kids.length;
    const C = sideCols(labels, 0, strikeIdx, [strikeIdx - 4, strikeIdx - 3, strikeIdx - 2, strikeIdx - 1]);
    const P = sideCols(labels, strikeIdx + 1, n, [strikeIdx + 1, strikeIdx + 2, strikeIdx + 3, strikeIdx + 4]);
    let container: Element | null = headerRow;
    for (let up = 0; up < 5 && container; up++) {
      container = container.parentElement;
      if (!container) break;
      const rows: DomChainRow[] = [];
      for (const r of Array.from(container.querySelectorAll('*'))) {
        if (r === headerRow || r.children.length !== n) continue;
        if (r.contains(headerRow) || headerRow.contains(r)) continue;
        const cells = Array.from(r.children);
        const strike = parseNum(textOf(cells[strikeIdx]));
        if (strike == null || strike <= 0) continue;
        const cell = (i: number): ChainCell => ({ el: cells[i], value: i >= 0 && cells[i] ? parseNum(textOf(cells[i])) : null });
        rows.push({
          strike, rowEl: r,
          C: { bid: cell(C.bid), ask: cell(C.ask), bidSize: cell(C.bidSize), askSize: cell(C.askSize) },
          P: { bid: cell(P.bid), ask: cell(P.ask), bidSize: cell(P.bidSize), askSize: cell(P.askSize) },
        });
      }
      if (rows.length) return { headerRow, strikeIdx, rows };
    }
  }
  return null;
}

export function readSpot(root: ParentNode, hints: DomHints, skip?: (el: Element) => boolean): number | null {
  let re: RegExp;
  try {
    re = new RegExp(hints.spotPattern, 'i');
  } catch {
    return null;
  }
  for (const { el, m } of findByPattern(root, re, 40, skip)) {
    if (!isVisible(el)) continue;
    const v = Number(m[1]);
    if (Number.isFinite(v) && v > 0) return v;
  }
  return null;
}

export function readFairT(root: ParentNode, hints: DomHints, skip?: (el: Element) => boolean): { years: number; days: number } | null {
  let re: RegExp;
  try {
    re = new RegExp(hints.tPattern, 'i');
  } catch {
    return null;
  }
  for (const { el, m } of findByPattern(root, re, 80, skip)) {
    if (!isVisible(el)) continue;
    const years = Number(m[1]);
    const days = Number(m[2]);
    if (Number.isFinite(years) && Number.isFinite(days)) return { years, days };
  }
  return null;
}

export function readHeaderClock(root: ParentNode, hints: DomHints, skip?: (el: Element) => boolean): number | null {
  let re: RegExp;
  try {
    re = new RegExp(hints.clockPattern);
  } catch {
    return null;
  }
  for (const { m } of findByPattern(root, re, 12, skip)) {
    const h = Number(m[1]);
    const mi = Number(m[2]);
    const s = Number(m[3]);
    if (h < 24 && mi < 60 && s < 60) return h * 3600 + mi * 60 + s;
  }
  return null;
}

/** The LATEST bar: label element's parent text minus the label, a leading time and a trailing "N earlier". */
export function readLatest(root: ParentNode, hints: DomHints, skip?: (el: Element) => boolean): string | null {
  const labels = findByExactText(root, hints.latestLabel, false, skip);
  for (const l of labels) {
    const bar = l.parentElement;
    if (!bar) continue;
    let t = textOf(bar);
    t = t.slice(t.toUpperCase().indexOf(hints.latestLabel.toUpperCase()) + hints.latestLabel.length);
    t = t.replace(/^\s*\d{1,2}:\d{2}(:\d{2})?\s*/, '').replace(/\s*\d+\s+earlier\s*$/i, '').trim();
    if (t) return t;
  }
  return null;
}

/** Best-effort positions list: items under the "Positions" heading containing a symbol and a signed integer. */
export function readPositions(root: ParentNode, hints: DomHints, symbolRe: RegExp, skip?: (el: Element) => boolean): Record<string, number> | null {
  const heads = findByExactText(root, hints.positionsLabel, false, skip);
  const unanchored = new RegExp(symbolRe.source.replace(/^\^/, '').replace(/\$$/, ''));
  for (const h of heads) {
    let box: Element | null = h.parentElement;
    for (let up = 0; up < 3 && box; up++) {
      const sib = box.nextElementSibling;
      if (sib) {
        const out: Record<string, number> = {};
        let found = false;
        for (const item of Array.from(sib.children)) {
          const t = textOf(item);
          const m = unanchored.exec(t);
          if (!m) continue;
          const rest = t.slice((m.index ?? 0) + m[0].length);
          const q = /([+-]?\d+)(?!\.\d)/.exec(rest);
          if (q) {
            out[m[0]] = Number(q[1]);
            found = true;
          }
        }
        if (found || sib.children.length) return found ? out : {};
      }
      box = box.parentElement;
    }
  }
  return null;
}

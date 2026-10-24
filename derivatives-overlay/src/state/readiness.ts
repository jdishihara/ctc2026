// Live-readiness checks: the "verify in the first live minutes" list (NOTES.md) as green/amber/red lines, each with the
// Config field or the keystroke that fixes it. Pure: reads the store's raw and derived state plus a DOM probe of the order
// form that the content script refreshes.
import { Config } from '../core/config';
import type { Derived, Raw } from './store';

export interface PanelProbe {
  found: boolean;
  symbol: string | null;
  qty: boolean;
  price: boolean;
  buy: boolean;
  sell: boolean;
  limit: boolean;
  submit: string | null;
  t: number;
}

export type CheckStatus = 'ok' | 'warn' | 'bad' | 'wait';

export interface Check {
  id: string;
  label: string;
  status: CheckStatus;
  detail: string;
  /** what to do when it is not ok */
  fix?: string;
}

const EXPECTED_RATE: Record<number, number> = { 1: 52, 2: 52, 3: 39 };

export function readiness(s: Raw, d: Derived, cfg: Config, now: number, panel: PanelProbe | null): Check[] {
  const out: Check[] = [];
  const th = cfg.thresholds;

  // 1. page / case
  out.push(d.mode === 'derivatives'
    ? { id: 'case', label: 'case', status: 'ok', detail: d.modeReason }
    : { id: 'case', label: 'case', status: 'bad', detail: `capture only (${d.modeReason})`, fix: 'Config caseNameRegex or underlyings' });

  // 2. feed
  const wsAge = s.ws.lastMsgAt ? (now - s.ws.lastMsgAt) / 1000 : null;
  out.push(!s.ws.lastMsgAt
    ? { id: 'feed', label: 'feed', status: 'bad', detail: 'no WebSocket frames seen', fix: 'hard-reload the exchange tab (hooks inject at document_start); Capture tab' }
    : wsAge != null && wsAge > 15
      ? { id: 'feed', label: 'feed', status: 'warn', detail: `last frame ${wsAge.toFixed(0)} s ago${s.ws.open ? '' : ' · socket closed'}`, fix: 'the page reconnects on its own; otherwise reload' }
      : { id: 'feed', label: 'feed', status: 'ok', detail: `frames flowing (${wsAge?.toFixed(1)} s)` });

  // 3. contracts per underlying
  for (const u of cfg.underlyings) {
    const ch = d.chains[u];
    const n = ch?.contracts.length ?? 0;
    const strikes = ch?.strikes ?? [];
    const complete = strikes.length >= 3 && strikes.every((k) => ch?.rows.find((r) => r.strike === k)?.call && ch?.rows.find((r) => r.strike === k)?.put);
    out.push(n === 0
      ? { id: `chain:${u}`, label: `${u} contracts`, status: 'bad', detail: `none parsed (${s.symbolsSeen.length} symbols seen)`, fix: 'Config symbolRegex: compare with Capture → ws:quote / GET /symbols' }
      : complete
        ? { id: `chain:${u}`, label: `${u} contracts`, status: 'ok', detail: `${n} (strikes ${strikes.join('/')})` }
        : { id: `chain:${u}`, label: `${u} contracts`, status: 'warn', detail: `${n} parsed, strikes ${strikes.join('/')}: incomplete`, fix: 'Config symbolRegex, or wait for the first quotes' });
  }

  // 4. quotes
  out.push(d.quoteAge == null
    ? { id: 'quotes', label: 'quotes', status: 'bad', detail: 'no option quotes', fix: 'Capture tab: frame kinds; Config fields.quote' }
    : d.quoteAge > th.staleQuoteSec
      ? { id: 'quotes', label: 'quotes', status: 'warn', detail: `stale ${d.quoteAge.toFixed(0)} s (normal between events if the makers do not re-quote)`, fix: 'if it never refreshes: Config fields.quote' }
      : { id: 'quotes', label: 'quotes', status: 'ok', detail: `${d.quoteAge.toFixed(1)} s old` });

  // 5. spot per underlying
  for (const u of cfg.underlyings) {
    const sp = d.spot[u];
    const src = sp?.src ?? 'none';
    out.push(sp?.value == null
      ? { id: `spot:${u}`, label: `${u} spot`, status: 'bad', detail: 'none', fix: `type it: Alt+S (Config dom.spotText if the chain header shows it)` }
      : src === 'WS' || src === 'DOM'
        ? { id: `spot:${u}`, label: `${u} spot`, status: 'ok', detail: `${sp.value.toFixed(2)} (${src})` }
        : { id: `spot:${u}`, label: `${u} spot`, status: 'warn', detail: `${sp.value.toFixed(2)} (${src})`, fix: 'parity/stale: check against the chain header, Alt+S to override' });
  }

  // 6. clock + rate
  const ph = d.phase;
  const rateExp = ph?.event ? EXPECTED_RATE[ph.event.round] : null;
  const rateOk = rateExp == null || !d.clockRate || Math.abs(d.clockRate - rateExp) / rateExp < 0.15;
  out.push(d.clockSrc === 'none'
    ? { id: 'clock', label: 'clock', status: 'bad', detail: 'no exchange clock', fix: 'GET /competitions/current not seen: Config fields.clock; or open the page header clock' }
    : d.clockStale && d.clockSrc === 'REST'
      ? { id: 'clock', label: 'clock', status: 'warn', detail: `REST clock stale; phase ${ph?.phase ?? '—'}`, fix: 'the page polls it; reload if it stays stale' }
      : !rateOk
        ? { id: 'clock', label: 'clock', status: 'warn', detail: `${d.clockSrc} rate ${d.clockRate.toFixed(0)}/min, expected ~${rateExp} in R${ph?.event?.round}`, fix: 'Config schedule / fallbackClockRate; check the header countdown against the exchange' }
        : { id: 'clock', label: 'clock', status: 'ok', detail: `${d.clockSrc} · rate ${d.clockRate ? d.clockRate.toFixed(0) : '?'}/min · ${ph ? `${ph.phase}${ph.event ? ` E${ph.event.n}` : ''}` : 'no phase'}` });

  // 7. T
  out.push(!(d.T.days > 0) || d.T.days > 30
    ? { id: 'T', label: 'T', status: 'warn', detail: `${d.T.days.toFixed(2)} d (${d.T.src})`, fix: 'Config T_mode: dom (open the Fair tab once) / computed / manual' }
    : { id: 'T', label: 'T', status: 'ok', detail: `${d.T.days.toFixed(2)} d (${d.T.src})` });

  // 8. positions
  const posAge = s.positionsAt ? (now - s.positionsAt) / 1000 : null;
  out.push(s.manualPositions
    ? { id: 'pos', label: 'positions', status: 'warn', detail: 'manual override in use (Risk tab)', fix: 'clear the manual positions once REST positions parse' }
    : s.positionsSrc === 'REST'
      ? { id: 'pos', label: 'positions', status: posAge != null && posAge > 60 ? 'warn' : 'ok', detail: `REST, ${Object.keys(s.positions).length} symbols, ${posAge?.toFixed(0)} s ago` }
      : s.positionsSrc === 'DOM'
        ? { id: 'pos', label: 'positions', status: 'warn', detail: 'read from the page, not the API', fix: 'Config fields.positions (Capture → http:GET /positions example)' }
        : { id: 'pos', label: 'positions', status: 'warn', detail: 'not seen yet (normal before the first poll)', fix: 'if it stays: Config fields.positions, or Risk tab → manual positions' });

  // 9. order form
  if (!panel || !panel.found) {
    out.push({ id: 'form', label: 'order form', status: 'bad', detail: 'not found on the page', fix: 'Config dom.qtyLabel / buyText / sellText (prefill and auto-submit need it)' });
  } else {
    const missing = [!panel.qty && 'QTY input', !panel.price && 'PRICE input', !panel.buy && 'BUY', !panel.sell && 'SELL', !panel.limit && 'Limit', !panel.submit && 'submit button'].filter(Boolean) as string[];
    out.push(missing.length
      ? { id: 'form', label: 'order form', status: 'warn', detail: `found, missing ${missing.join(', ')}`, fix: 'Config dom.*; the ticket card has a copy button as a fallback' }
      : { id: 'form', label: 'order form', status: 'ok', detail: `${panel.symbol ?? '?'} · "${panel.submit}"` });
  }

  // 10. news parse
  const last = s.news.length ? s.news[s.news.length - 1] : null;
  if (!last) {
    out.push({ id: 'news', label: 'news', status: 'wait', detail: 'none yet (normal before the first event)', fix: 'after the first headline this line shows what was parsed' });
  } else {
    const age = (now - last.t) / 1000;
    const parsed = Object.entries(last.parse.underlyings).map(([u, p]) => `${u}${p.spot != null ? ` spot ${p.spot}` : ''}${p.iv != null ? ` iv ${(p.iv * 100).toFixed(0)}%` : ''}`).join(', ');
    const analysts = last.parse.analysts.length ? `${last.parse.analysts.length} analyst value(s)` : '';
    const got = [parsed, analysts].filter(Boolean).join(' · ');
    const isHeadline = /head|news|event/i.test(last.kind) && !/analyst/i.test(last.kind);
    out.push(got
      ? { id: 'news', label: 'news', status: 'ok', detail: `${last.kind} ${age.toFixed(0)} s ago: ${got}` }
      : { id: 'news', label: 'news', status: isHeadline ? 'warn' : 'wait', detail: `${last.kind} ${age.toFixed(0)} s ago: nothing parsed from "${last.text.slice(0, 60)}"`, fix: 'type spot/vol (Alt+S / Alt+V); Config headline.aliases if the names differ' });
  }
  return out;
}

export function summarize(checks: Check[]): { ok: number; total: number; worst: CheckStatus } {
  const rank: Record<CheckStatus, number> = { ok: 0, wait: 1, warn: 2, bad: 3 };
  let worst: CheckStatus = 'ok';
  for (const c of checks) if (rank[c.status] > rank[worst]) worst = c.status;
  return { ok: checks.filter((c) => c.status === 'ok').length, total: checks.length, worst };
}

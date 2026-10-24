// Single store: raw observations in `s`, engine outputs in `d` (recomputed, debounced). Pure TS, DOM-free;
// DOM readings are pushed in by the content script.
import { AnalystId, AnalystRecord, ANALYSTS, analystStats, blendAnalysts, BlendResult } from '../engine/analysts';
import { ArbFlag, findArbs } from '../engine/arbitrage';
import { price as bsPrice, getRate, setRate } from '../engine/blackScholes';
import {
  buildChains, Chain, compileSymbolRegex, Contract, inferTick, marketIV, metaFromSymbolEntry, mid, OptionMeta,
  parityImpliedSpot, parseOptionSymbol, Quote,
} from '../engine/chain';
import { ConverterCandidate, ConverterSample, identifyConverter, mentionedConverters } from '../engine/autoConverter';
import { CONVERTERS, convertToSigma, ConverterId, normalizeVol } from '../engine/converters';
import { Baseline, computeEdges, EdgeRow, Resting } from '../engine/fairValue';
import { extractStructured, HeadlineParse, parseHeadline } from '../engine/headline';
import { Breach, capBreaches, contractsBySymbol, flattenOrders, needsFlatten, Portfolio, portfolio } from '../engine/risk';
import type { PanelProbe } from './readiness';
import { isOrderAction, RateMeter } from '../engine/rateLimit';
import { EventSpec, packetRateForDate, phaseAt, PhaseInfo, realSecondsToNext, rebaseSchedule, withLiveRate } from '../engine/schedule';
import { straddles, Structure, syntheticForwards } from '../engine/structures';
import { planTickets, Ticket, ticketsFromArb, ticketsFromFlatten } from '../engine/tickets';
import { dayStart, fmtDate, hmsToSec, parseNaiveSec, secOfDay, tradingDaysRemaining } from '../engine/tradingTime';
import { Config, pick, pickNum } from '../core/config';
import { FrameClassifier } from '../core/classify';
import { Capture } from '../core/capture';

export type Tab = 'Edge' | 'Arb' | 'Vol' | 'Risk' | 'Timeline' | 'Capture' | 'Config';
export const TABS: Tab[] = ['Edge', 'Arb', 'Vol', 'Risk', 'Timeline', 'Capture', 'Config'];

export interface TargetField {
  value: number | null;
  src: string;
  confirmed: boolean;
  suggestion?: { value: number; src: string } | null;
  /** event whose news/analysts (or typing) produced this value */
  event?: number | null;
}

export interface UndTargets {
  spot: TargetField;
  vol: TargetField;
  volLow: number | null;
  volHigh: number | null;
  bandNote: string;
}

export interface AnalystCell {
  raw: number | null;
  sigma: number | null;
  src: 'parsed' | 'typed';
  note?: string;
}

export interface NewsItem {
  seq: number | null;
  text: string;
  t: number;
  src: 'WS' | 'DOM' | 'REST';
  event: number | null;
  parse: HeadlineParse;
  kind: string;
}

export interface FillObs {
  id: string;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  bid: number | null;
  ask: number | null;
  atMid: boolean | null;
  event: number | null;
  t: number;
}

export interface EventLog {
  n: number;
  round: number;
  headline?: string;
  baseline?: Record<string, Baseline>;
  targets?: Record<string, { spot: number | null; vol: number | null; src: string }>;
  trueVol?: Record<string, number | null>;
  trueSpot?: Record<string, number | null>;
  analystErrors?: Record<string, Partial<Record<AnalystId, number>>>;
  captured?: number | null;
}

export interface ClockState {
  fictionalSec: number | null;
  receivedAt: number;
  rate: number | null;
  state: string | null;
  /** GET /competitions/current elapsed_active_seconds: real seconds the clock has run since the case started */
  elapsedActiveSec?: number | null;
}

export interface UiState {
  tab: Tab;
  pinned: boolean;
  collapsed: boolean;
  hidden: boolean;
  x: number | null;
  y: number | null;
  showCheat: boolean;
  focusField: 'spot' | 'vol' | null;
  focusUnd: string;
  /** capture-only pages show a badge until clicked */
  captureOpen: boolean;
}

export interface LoadedTicket {
  ticket: Ticket;
  t: number;
  ok: boolean | null;
  message: string;
}

export interface AutoTargetState {
  status: 'idle' | 'confirmed' | 'manual';
  reason: string;
  event: number | null;
  t: number;
}

export interface AutoConverterState {
  /** idle = not identified yet (retried on each analyst message); chosen = auto; manual = the trader picked, auto stays off */
  status: 'idle' | 'chosen' | 'manual';
  id: ConverterId | null;
  reason: string;
  event: number | null;
  ranked: ConverterCandidate[];
}

export interface AutoSubmitLog {
  t: number;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  source: string;
  event: number | null;
  result: string;
}

export interface AutoState {
  targets: Record<string, AutoTargetState>;
  converter: AutoConverterState;
  /** Alt+P: auto-submit paused by the trader */
  paused: boolean;
  log: AutoSubmitLog[];
  lastSubmitAt: number;
  /** auto.confirmEach: the order the auto-pilot wants to send next, waiting for the trader's Send or Skip */
  pending: PendingOrder | null;
}

export interface PendingOrder {
  ticket: Ticket;
  since: number;
  mode: 'edge' | 'flatten';
}

export interface Raw {
  caseName: string | null;
  competitionId: string | null;
  clock: ClockState;
  lastClockPollAt: number;
  domClock: { sec: number; t: number } | null;
  domSpot: { value: number; t: number } | null;
  domT: { years: number; days: number; t: number } | null;
  domChain: { strikes: number[]; t: number } | null;
  quotes: Record<string, Quote>;
  undQuotes: Record<string, { bid: number | null; ask: number | null; last: number | null; t: number }>;
  metas: Record<string, OptionMeta>;
  symbolsSeen: string[];
  /** GET /options/{u}/chain: the exchange's own spot, rate and time to expiry (polled through the session cookie) */
  restChain: Record<string, { spot: number | null; r: number; tDays: number | null; expiry: string | null; t: number }>;
  /** REST poller and own-feed health, refreshed by the content script */
  api: { polls: number; errors: number; lastOkAt: number; backoff: number; note: string };
  feed: { open: boolean; frames: number; lastAt: number; reconnects: number; symbols: number; url: string | null };
  /** what GET /symbols says about the instruments: the scheduled underlyings, the option tick and the position limit */
  exchange: { underlyings: string[]; tick: number | null; maxPosition: number | null; t: number };
  /** order_ids of orders this overlay posted itself (API submit path) */
  sentOrderIds: string[];
  /** open orders not posted by this overlay while it was armed (another bot or a human on the same account) */
  foreignOpenOrders: number;
  positions: Record<string, number>;
  positionsSrc: 'REST' | 'DOM' | 'manual' | null;
  positionsAt: number;
  restPositionsAt: number;
  manualPositions: Record<string, number> | null;
  resting: Record<string, Resting>;
  news: NewsItem[];
  lastLatestText: string | null;
  targets: Record<string, UndTargets>;
  baselines: Record<number, Record<string, Baseline>>;
  preNews: Record<string, { spot: number | null; vol: number | null; t: number }>;
  analystInputs: Record<number, Record<string, Partial<Record<AnalystId, AnalystCell>>>>;
  converter: { id: ConverterId; K: number | null; formula: string };
  history: AnalystRecord[];
  timeline: Record<number, EventLog>;
  manualQueue: Ticket[];
  loaded: LoadedTicket | null;
  recentLoads: { sig: string; t: number }[];
  fills: FillObs[];
  seenTradeIds: string[];
  ws: { open: boolean; url: string | null; lastMsgAt: number; subscribeSeen: unknown };
  /** last DOM probe of the order form (content script, every DOM read) */
  panelProbe: PanelProbe | null;
  ui: UiState;
  toast: { text: string; t: number; level: 'info' | 'warn' | 'error' } | null;
  phaseKey: string | null;
  learnAt: { event: number; at: number } | null;
  auto: AutoState;
}

export interface Derived {
  now: number;
  mode: 'derivatives' | 'capture-only';
  modeReason: string;
  simNow: number | null;
  clockSrc: 'REST' | 'DOM' | 'none';
  clockStale: boolean;
  clockRate: number;
  replay: boolean;
  /** the schedule in force: the packet dates, or the same layout rebased onto the exchange's dates */
  schedule: EventSpec[];
  scheduleNote: string | null;
  phase: PhaseInfo | null;
  realToNext: number | null;
  round: 1 | 2 | 3 | null;
  T: { years: number; days: number; src: string };
  /** risk-free rate used by every pricing call (the chain's risk_free_rate; 0 until seen) */
  r: number;
  chains: Record<string, Chain>;
  contracts: Record<string, Contract>;
  spot: Record<string, { value: number | null; src: string; age: number | null }>;
  marketIV: Record<string, number | null>;
  effTargets: Record<string, { spot: number; vol: number; volLow: number; volHigh: number } | undefined>;
  blends: Record<string, BlendResult | null>;
  edges: Record<string, EdgeRow[]>;
  synths: Record<string, Structure[]>;
  straddles: Record<string, Structure[]>;
  arbs: ArbFlag[];
  portfolio: Portfolio;
  breaches: Breach[];
  flattenNow: boolean;
  plan: Ticket[];
  flatten: Ticket[];
  flattenCost: number;
  rate: ReturnType<RateMeter['status']>;
  quoteAge: number | null;
  tick: number;
  targetsConfirmed: boolean;
  /** per underlying: spot and vol of the current event confirmed (edge tickets of one underlying do not wait for the other) */
  confirmedUnderlyings: Record<string, boolean>;
  /** the limits in force: Config thresholds capped by the exchange's own max_position when it lists one */
  positionLimit: number;
  perTicketCap: number;
  /** auto-submit is on in Config, not paused, and this is the derivatives page */
  autoArmed: boolean;
}

const emptyTarget = (): UndTargets => ({
  spot: { value: null, src: '—', confirmed: false, suggestion: null },
  vol: { value: null, src: '—', confirmed: false, suggestion: null },
  volLow: null, volHigh: null, bandNote: '',
});

export function defaultUi(): UiState {
  return { tab: 'Edge', pinned: false, collapsed: false, hidden: false, x: null, y: null, showCheat: false, focusField: null, focusUnd: 'OIL', captureOpen: false };
}

export class Store {
  s: Raw;
  d: Derived;
  cfg: Config;
  readonly capture = new Capture(5000);
  readonly classifier = new FrameClassifier();
  readonly rate: RateMeter;
  /** schedule rebased onto an exchange date that is not in Config (see compute) */
  private rebased: { today: string; schedule: EventSpec[] } | null = null;
  private listeners = new Set<() => void>();
  private recomputeTimer: ReturnType<typeof setTimeout> | null = null;
  private lastAutoJudgeAt = 0;
  private symbolRe: RegExp;
  version = 0;
  /** persistence hook, set by the content script */
  persist: (key: string, value: unknown) => void = () => undefined;

  constructor(cfg: Config, public nowFn: () => number = () => Date.now()) {
    this.cfg = cfg;
    this.symbolRe = compileSymbolRegex(cfg.symbolRegex);
    this.rate = new RateMeter(60_000, cfg.rate.limit, cfg.rate.amberAt, cfg.rate.redAt);
    this.s = {
      caseName: null, competitionId: null,
      clock: { fictionalSec: null, receivedAt: 0, rate: null, state: null }, lastClockPollAt: 0,
      domClock: null, domSpot: null, domT: null, domChain: null,
      quotes: {}, undQuotes: {}, metas: {}, symbolsSeen: [],
      restChain: {}, exchange: { underlyings: [], tick: null, maxPosition: null, t: 0 }, api: { polls: 0, errors: 0, lastOkAt: 0, backoff: 1, note: '' }, feed: { open: false, frames: 0, lastAt: 0, reconnects: 0, symbols: 0, url: null }, sentOrderIds: [], foreignOpenOrders: 0,
      positions: {}, positionsSrc: null, positionsAt: 0, restPositionsAt: 0, manualPositions: null, resting: {},
      news: [], lastLatestText: null,
      targets: Object.fromEntries(cfg.underlyings.map((u) => [u, emptyTarget()])),
      baselines: {}, preNews: {}, analystInputs: {},
      converter: { id: 'variance', K: null, formula: 'sqrt(x)' },
      history: [], timeline: {}, manualQueue: [], loaded: null, recentLoads: [], fills: [], seenTradeIds: [],
      ws: { open: false, url: null, lastMsgAt: 0, subscribeSeen: null },
      panelProbe: null,
      ui: defaultUi(), toast: null, phaseKey: null, learnAt: null,
      auto: { targets: {}, converter: { status: 'idle', id: null, reason: '', event: null, ranked: [] }, paused: false, log: [], lastSubmitAt: 0, pending: null },
    };
    this.d = this.compute();
  }

  // ---------------- subscription ----------------
  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  private emit() {
    this.version++;
    for (const f of this.listeners) {
      try {
        f();
      } catch {
        /* ignore */
      }
    }
  }
  /** Debounced recompute (100 ms) followed by emit. */
  changed(immediate = false) {
    if (immediate) {
      if (this.recomputeTimer) clearTimeout(this.recomputeTimer);
      this.recomputeTimer = null;
      this.d = this.compute();
      this.emit();
      return;
    }
    if (this.recomputeTimer) return;
    this.recomputeTimer = setTimeout(() => {
      this.recomputeTimer = null;
      try {
        this.d = this.compute();
      } catch (e) {
        console.warn('[deriv-overlay] compute failed', e);
      }
      this.emit();
    }, 100);
  }

  setConfig(cfg: Config) {
    this.cfg = cfg;
    this.symbolRe = compileSymbolRegex(cfg.symbolRegex);
    this.rate.limit = cfg.rate.limit;
    this.rate.amberAt = cfg.rate.amberAt;
    this.rate.redAt = cfg.rate.redAt;
    for (const u of cfg.underlyings) this.s.targets[u] ??= emptyTarget();
    // re-derive metas from the symbols seen so far
    for (const sym of this.s.symbolsSeen) this.noteSymbol(sym);
    this.changed(true);
  }

  toast(text: string, level: 'info' | 'warn' | 'error' = 'info') {
    this.s.toast = { text, level, t: this.nowFn() };
    this.changed();
  }

  // ---------------- ingestion ----------------
  private noteSymbol(sym: string) {
    if (typeof sym !== 'string' || !sym) return;
    if (!this.s.symbolsSeen.includes(sym)) this.s.symbolsSeen.push(sym);
    const m = parseOptionSymbol(sym, this.symbolRe);
    if (m && !this.s.metas[sym]) this.s.metas[sym] = m;
  }

  isUnderlying(sym: string): boolean {
    return this.cfg.underlyings.includes(sym.toUpperCase());
  }

  handleBridge(kind: string, p: { url?: string; data?: unknown; json?: unknown; method?: string; status?: number; body?: string | null; t?: number }) {
    const now = this.nowFn();
    try {
      if (kind === 'ws-in') {
        const c = this.classifier.classifyWs('in', p.data, p.json);
        this.capture.add({ t: now, key: c.key, dir: 'in', url: p.url, raw: typeof p.data === 'string' ? p.data : JSON.stringify(p.data), highlights: c.highlights });
        this.s.ws.lastMsgAt = now;
        this.s.ws.open = true;
        if (!c.dup && c.json !== undefined) this.handleWsJson(c.json, now);
      } else if (kind === 'ws-out') {
        const c = this.classifier.classifyWs('out', p.data, p.json);
        this.capture.add({ t: now, key: c.key, dir: 'out', url: p.url, raw: typeof p.data === 'string' ? p.data : JSON.stringify(p.data), highlights: c.highlights });
        const j = c.json as Record<string, unknown> | undefined;
        if (j && Array.isArray(j.symbols)) {
          this.s.ws.subscribeSeen = j;
          for (const s of j.symbols) this.noteSymbol(String(s));
        }
      } else if (kind === 'ws-open') {
        this.s.ws.open = true;
        this.s.ws.url = p.url ?? null;
        this.capture.add({ t: now, key: 'ws:open', dir: 'meta', url: p.url, raw: p.url ?? '', highlights: [] });
      } else if (kind === 'ws-close') {
        this.s.ws.open = false;
        this.capture.add({ t: now, key: 'ws:close', dir: 'meta', url: p.url, raw: p.url ?? '', highlights: [] });
      } else if (kind === 'http') {
        const c = this.classifier.classifyHttp(p.method ?? 'GET', p.url ?? '', p.json, p.body ?? '');
        this.capture.add({ t: now, key: c.key, dir: 'http', url: p.url, raw: p.body ?? '', highlights: c.highlights });
        if ((p.method ?? 'GET').toUpperCase() === 'POST' && /\/orders(\?|$)/.test(p.url ?? '')) {
          this.noteOrderResponse(p.status ?? 200, p.json, now);
          const oid = pick(p.json, ['order_id', 'id']);
          if (typeof oid === 'string' && !this.s.sentOrderIds.includes(oid)) {
            this.s.sentOrderIds.push(oid);
            if (this.s.sentOrderIds.length > 2000) this.s.sentOrderIds.shift();
          }
        }
        if ((p.status ?? 200) < 400 && p.json !== undefined) this.handleHttp(p.method ?? 'GET', p.url ?? '', p.json, now);
      } else if (kind === 'http-req') {
        const c = this.classifier.classifyHttp(p.method ?? 'POST', p.url ?? '', p.json, p.body ?? '', true);
        this.capture.add({ t: now, key: c.key, dir: 'req', url: p.url, raw: p.body ?? '', highlights: c.highlights });
        if (isOrderAction(p.method ?? 'POST', p.url ?? '')) this.rate.add(now);
      } else if (kind === 'hooks-ready') {
        this.capture.add({ t: now, key: 'meta:hooks-ready', dir: 'meta', raw: p.url ?? '', highlights: [] });
      }
    } catch (e) {
      console.warn('[deriv-overlay] ingest failed', e);
    }
    this.changed();
  }

  handleWsJson(j: unknown, now = this.nowFn()) {
    if (!j || typeof j !== 'object') return;
    const o = j as Record<string, unknown>;
    const type = String(o.type ?? '');
    const F = this.cfg.fields.quote;
    if (type === 'quote' || type === 'book' || type === 'orderbook') {
      const sym = String(pick(o, F.symbol) ?? '');
      if (!sym) return;
      this.noteSymbol(sym);
      let bid = pickNum(o, F.bid);
      let ask = pickNum(o, F.ask);
      let bidSize = pickNum(o, F.bidSize);
      let askSize = pickNum(o, F.askSize);
      if (type !== 'quote') {
        const lvl = (x: unknown) => (Array.isArray(x) && x.length ? x[0] : null);
        const b = lvl(o.bids);
        const a = lvl(o.asks);
        const px = (l: unknown) => (Array.isArray(l) ? Number(l[0]) : l && typeof l === 'object' ? pickNum(l, ['price', 'px']) : null);
        const sz = (l: unknown) => (Array.isArray(l) ? Number(l[1]) : l && typeof l === 'object' ? pickNum(l, ['size', 'quantity', 'qty']) : null);
        bid ??= px(b);
        ask ??= px(a);
        bidSize ??= sz(b);
        askSize ??= sz(a);
      }
      if (this.isUnderlying(sym)) {
        const prev = this.s.undQuotes[sym.toUpperCase()];
        this.s.undQuotes[sym.toUpperCase()] = { bid, ask, last: pickNum(o, F.last) ?? prev?.last ?? null, t: now };
      } else {
        this.s.quotes[sym] = { symbol: sym, bid, ask, bidSize, askSize, t: now, src: type === 'quote' ? 'WS' : 'BOOK' };
      }
    } else if (type === 'trade') {
      const sym = String(o.symbol ?? '');
      const px = pickNum(o, ['price', 'px']);
      if (sym && px != null && this.isUnderlying(sym)) {
        const u = sym.toUpperCase();
        const prev = this.s.undQuotes[u];
        this.s.undQuotes[u] = { bid: prev?.bid ?? null, ask: prev?.ask ?? null, last: px, t: now };
      } else if (sym) this.noteSymbol(sym);
    } else if (type === 'news') {
      const msg = (o.message && typeof o.message === 'object' ? o.message : o) as Record<string, unknown>;
      const text = [msg.headline, msg.text, msg.title, msg.body, msg.message].find((x) => typeof x === 'string') as string | undefined;
      const seq = typeof msg.seq === 'number' ? msg.seq : null;
      const kind = String(msg.type ?? 'news');
      const structured = extractStructured(msg, this.cfg.underlyings);
      if (text || Object.keys(structured).length) {
        this.ingestNews(text ?? '', 'WS', seq, kind, msg, structured, now);
      }
    } else if (type === 'subscription_ack') {
      if (Array.isArray(o.symbols)) for (const s of o.symbols) this.noteSymbol(String(s));
    }
  }

  handleHttp(method: string, url: string, j: unknown, now = this.nowFn()) {
    let path = url;
    let params = new URLSearchParams();
    try {
      const u = new URL(url, 'http://x');
      path = u.pathname;
      params = u.searchParams;
    } catch {
      /* ignore */
    }
    if (method !== 'GET') return;
    const C = this.cfg.fields.clock;
    if (/\/competitions\/current$/.test(path)) {
      const ft = pick(j, C.fictionalTime);
      const sec = typeof ft === 'string' ? parseNaiveSec(ft) : null;
      const rate = pickNum(j, C.clockRate);
      const state = pick(j, C.state);
      const name = pick(j, C.name);
      const id = pick(j, C.id);
      if (typeof name === 'string') this.s.caseName = name;
      if (typeof id === 'string' && id !== this.s.competitionId) {
        this.s.competitionId = id;
        this.onCompetition?.(id);
      }
      if (sec != null) this.s.clock = { fictionalSec: sec, receivedAt: now, rate, state: typeof state === 'string' ? state : null, elapsedActiveSec: pickNum(j, ['elapsed_active_seconds', 'elapsedActiveSeconds', 'elapsed_seconds']) };
      this.s.lastClockPollAt = now;
      return;
    }
    const chainM = /\/options\/([^/]+)\/chain$/.exec(path);
    if (chainM) {
      this.ingestChain(decodeURIComponent(chainM[1]).toUpperCase(), j, now);
      return;
    }
    if (/\/symbols$/.test(path)) {
      const list = Array.isArray(j) ? j : (pick(j, ['symbols', 'data', 'items', 'instruments']) as unknown[]);
      if (Array.isArray(list)) {
        const unds = new Set<string>();
        let tick: number | null = null;
        let maxPos: number | null = null;
        for (const e of list) {
          const m = metaFromSymbolEntry(e, this.symbolRe);
          const sym = typeof e === 'string' ? e : String((e as Record<string, unknown>)?.symbol ?? '');
          if (sym && !this.s.symbolsSeen.includes(sym)) this.s.symbolsSeen.push(sym);
          if (m) this.s.metas[m.symbol] = m;
          if (e && typeof e === 'object') {
            const o = e as Record<string, unknown>;
            const type = String(o.symbol_type ?? o.type ?? '').toLowerCase();
            if (m || type === 'option') {
              const u = String(o.underlying_symbol ?? o.underlying ?? m?.underlying ?? '').toUpperCase();
              if (u) unds.add(u);
              tick = pickNum(o, ['tick_size', 'tick', 'tickSize']) ?? tick;
              maxPos = pickNum(o, ['max_position', 'position_limit', 'maxPosition']) ?? maxPos;
            } else if (type === 'scheduled' || type === 'underlying') unds.add(sym.toUpperCase());
          }
        }
        if (unds.size || tick != null || maxPos != null) this.s.exchange = { underlyings: [...unds].sort(), tick, maxPosition: maxPos, t: now };
      }
      return;
    }
    if (/\/positions$/.test(path)) {
      const P = this.cfg.fields.positions;
      const out: Record<string, number> = {};
      const list = Array.isArray(j) ? j : (pick(j, P.list) as unknown);
      if (Array.isArray(list)) {
        for (const it of list) {
          const sym = pick(it, P.symbol);
          const q = pickNum(it, P.qty);
          if (typeof sym === 'string' && q != null) out[sym] = q;
        }
      } else if (j && typeof j === 'object') {
        for (const [k, v] of Object.entries(j as Record<string, unknown>)) {
          if (typeof v === 'number') out[k] = v;
          else if (v && typeof v === 'object') {
            const q = pickNum(v, P.qty);
            if (q != null) out[k] = q;
          }
        }
      }
      this.s.positions = out;
      this.s.positionsSrc = 'REST';
      this.s.positionsAt = now;
      this.s.restPositionsAt = now;
      return;
    }
    if (/\/orders\/open$/.test(path) || /\/orders$/.test(path)) {
      const O = this.cfg.fields.orders;
      const list = Array.isArray(j) ? j : (pick(j, O.list) as unknown);
      if (!Array.isArray(list)) return;
      const symParam = params.get('symbol');
      const seenIds: string[] = [];
      const fresh: Record<string, Resting> = {};
      if (symParam) fresh[symParam] = { buy: 0, sell: 0 };
      for (const it of list) {
        const sym = pick(it, O.symbol);
        if (typeof sym !== 'string') continue;
        const status = String(pick(it, O.status) ?? 'open').toLowerCase();
        if (/fill|cancel|reject|done|closed/.test(status) && !/partial/.test(status)) continue;
        const side = String(pick(it, O.side) ?? '').toLowerCase();
        // the live API gives quantity + filled_quantity (no remaining field): remaining = quantity - filled
        let rem = pickNum(it, O.remaining.filter((k) => !/^(quantity|qty)$/.test(k)));
        if (rem == null) {
          const q = pickNum(it, ['quantity', 'qty']) ?? 0;
          rem = q - (pickNum(it, ['filled_quantity', 'filled', 'executed_quantity']) ?? 0);
        }
        const oid = pick(it, ['order_id', 'id']);
        if (typeof oid === 'string') seenIds.push(oid);
        const r = (fresh[sym] ??= { buy: 0, sell: 0 });
        if (side.startsWith('b')) r.buy += rem;
        else if (side.startsWith('s')) r.sell += rem;
      }
      if (symParam) Object.assign(this.s.resting, fresh);
      else {
        this.s.resting = fresh;
        // another bot or a human on the same account? open orders we never posted while armed (the API path records its ids)
        this.s.foreignOpenOrders = this.d?.autoArmed && this.cfg.auto.submitVia === 'api' ? seenIds.filter((id) => !this.s.sentOrderIds.includes(id)).length : 0;
      }
      return;
    }
    if (/\/trades$/.test(path)) {
      // the user's own fills: log fill price vs the quote we had (tests the "executes at the midpoint" claim)
      const list = Array.isArray(j) ? j : (pick(j, ['trades', 'data', 'items']) as unknown);
      if (!Array.isArray(list)) return;
      for (const it of list) {
        const id = String(pick(it, ['trade_id', 'id', 'fill_id']) ?? '');
        if (!id || this.s.seenTradeIds.includes(id)) continue;
        this.s.seenTradeIds.push(id);
        if (this.s.seenTradeIds.length > 2000) this.s.seenTradeIds.shift();
        const symbol = String(pick(it, ['symbol']) ?? '');
        const px = pickNum(it, ['price', 'px', 'fill_price']);
        const qty = pickNum(it, ['quantity', 'qty', 'size']) ?? 0;
        if (!symbol || px == null) continue;
        const q = this.s.quotes[symbol];
        const m = q ? mid(q) : null;
        this.s.fills.push({
          id, symbol, side: String(pick(it, ['side', 'direction']) ?? ''), qty, price: px, bid: q?.bid ?? null, ask: q?.ask ?? null,
          atMid: m != null ? Math.abs(px - m) < 0.0051 : null, event: this.d?.phase?.event?.n ?? null, t: now,
        });
        if (this.s.fills.length > 500) this.s.fills.shift();
      }
    }
  }

  onCompetition?: (id: string) => void;

  /** GET /api/v1/options/{u}/chain (live shape, 2026-10-24): strikes, symbols, quotes, spot, rate and trading days in one call. */
  ingestChain(u: string, j: unknown, now = this.nowFn()) {
    if (!j || typeof j !== 'object') return;
    const o = j as Record<string, unknown>;
    const und = String(pick(o, ['underlying_symbol', 'underlying', 'symbol']) ?? u).toUpperCase() || u;
    const spot = pickNum(o, ['current_underlying_price', 'underlying_price', 'spot']);
    const r = pickNum(o, ['risk_free_rate', 'rate', 'r']) ?? 0;
    const expiries = (Array.isArray(o.expiries) ? o.expiries : []) as Record<string, unknown>[];
    // the packet has one expiry; if several, take the nearest one still in the future (the exchange sorts them)
    const exp = expiries.find((e) => (pickNum(e, ['trading_days_to_expiry']) ?? 1) > 0) ?? expiries[0];
    const tDays = exp ? pickNum(exp, ['trading_days_to_expiry', 'tradingDays', 'days']) : null;
    const expiry = exp ? String(pick(exp, ['expiry_fictional_time', 'expiry']) ?? '') : null;
    this.s.restChain[und] = { spot, r, tDays, expiry, t: now };
    if (!this.s.symbolsSeen.includes(und)) this.s.symbolsSeen.push(und);
    const rows = exp && Array.isArray(exp.rows) ? (exp.rows as Record<string, unknown>[]) : [];
    for (const row of rows) {
      const K = pickNum(row, ['strike', 'strike_price']);
      if (K == null) continue;
      for (const kind of ['C', 'P'] as const) {
        const q = row[kind === 'C' ? 'call' : 'put'];
        if (!q || typeof q !== 'object') continue;
        const sym = String(pick(q, ['symbol']) ?? '');
        if (!sym) continue;
        this.s.metas[sym] = { symbol: sym, underlying: und, expiry: expiry ?? '', kind, strike: K };
        if (!this.s.symbolsSeen.includes(sym)) this.s.symbolsSeen.push(sym);
        const F = this.cfg.fields.quote;
        const bid = pickNum(q, F.bid);
        const ask = pickNum(q, F.ask);
        const prev = this.s.quotes[sym];
        // the page's socket (or ours) is fresher when it is flowing; the chain fills gaps and the other product tab
        if (!prev || prev.src === 'REST' || prev.src === 'DOM' || now - prev.t > 1500) {
          if (bid != null || ask != null) this.s.quotes[sym] = { symbol: sym, bid, ask, bidSize: pickNum(q, F.bidSize), askSize: pickNum(q, F.askSize), last: pickNum(q, F.last), t: now, src: 'REST' };
        }
      }
    }
  }

  /** DOM fallbacks pushed by the content script. */
  handleDom(r: {
    clockSec?: number | null; spot?: number | null; T?: { years: number; days: number } | null;
    chain?: { strike: number; kind: 'C' | 'P'; bid: number | null; ask: number | null; bidSize: number | null; askSize: number | null }[] | null;
    latest?: string | null; positions?: Record<string, number> | null;
  }) {
    const now = this.nowFn();
    if (r.clockSec != null) this.s.domClock = { sec: r.clockSec, t: now };
    if (r.spot != null) this.s.domSpot = { value: r.spot, t: now };
    if (r.T) this.s.domT = { ...r.T, t: now };
    if (r.chain?.length) {
      const strikes = [...new Set(r.chain.map((x) => x.strike))].sort((a, b) => a - b);
      this.s.domChain = { strikes, t: now };
      const und = this.domChainUnderlying(strikes);
      if (und) {
        for (const row of r.chain) {
          const meta = Object.values(this.s.metas).find((m) => m.underlying === und && m.kind === row.kind && Math.abs(m.strike - row.strike) < 1e-9);
          if (!meta) continue;
          const ws = this.s.quotes[meta.symbol];
          const wsFresh = ws && ws.src !== 'DOM' && now - ws.t < this.cfg.thresholds.staleQuoteSec * 1000;
          if (!wsFresh && (row.bid != null || row.ask != null)) {
            this.s.quotes[meta.symbol] = { symbol: meta.symbol, bid: row.bid, ask: row.ask, bidSize: row.bidSize, askSize: row.askSize, t: now, src: 'DOM' };
          }
        }
      }
    }
    if (r.latest && r.latest !== this.s.lastLatestText) {
      this.s.lastLatestText = r.latest;
      // the WS copy (if any) usually arrives first; ingestNews de-duplicates by text
      this.ingestNews(r.latest, 'DOM', null, 'latest', null, {}, now);
    }
    if (r.positions && now - this.s.restPositionsAt > 10_000 && !this.s.manualPositions) {
      this.s.positions = r.positions;
      this.s.positionsSrc = 'DOM';
      this.s.positionsAt = now;
    }
    this.changed();
  }

  /** Which underlying does the visible DOM chain show? Match strikes, then spot proximity. */
  domChainUnderlying(strikes: number[]): string | null {
    const chains = buildChains(Object.values(this.s.metas), {});
    const cands = Object.values(chains).filter((c) => strikes.every((k) => c.strikes.some((x) => Math.abs(x - k) < 1e-9)));
    if (cands.length === 1) return cands[0].underlying;
    if (cands.length > 1 && this.s.domSpot) {
      const ds = this.s.domSpot.value;
      let best: string | null = null;
      let bestErr = Infinity;
      for (const c of cands) {
        const ref = this.d?.spot?.[c.underlying]?.value;
        if (ref != null && Math.abs(ref - ds) / ref < bestErr) {
          bestErr = Math.abs(ref - ds) / ref;
          best = c.underlying;
        }
      }
      return best;
    }
    return null;
  }

  // ---------------- news / targets ----------------
  private newsEvent(msg: Record<string, unknown> | null): number | null {
    const n = Number(msg?.event);
    if (Number.isInteger(n) && this.cfg.schedule.some((e) => e.n === n)) return n;
    const d = this.d;
    const ph = d?.phase;
    if (!ph) return null;
    if (ph.phase === 'NEWS' || ph.phase === 'UNDERLYING_MOVED') return ph.event?.n ?? null;
    // news slightly ahead of our interpolated clock belongs to the upcoming event
    if (ph.nextPhase === 'NEWS' && d.realToNext != null && d.realToNext < 15) {
      const cur = ph.event;
      if (ph.phase === 'CLOSED' || ph.phase === 'WAITING') return cur?.n ?? null;
      const sorted = [...this.cfg.schedule].sort((a, b) => a.n - b.n);
      const idx = sorted.findIndex((e) => e.n === cur?.n);
      return sorted[idx + 1]?.n ?? null;
    }
    if (ph.phase === 'SNAPPED') return ph.event?.n ?? null;
    return null;
  }

  ingestNews(text: string, src: NewsItem['src'], seq: number | null, kind: string, msg: Record<string, unknown> | null, structured: ReturnType<typeof extractStructured>, now = this.nowFn()) {
    const clean = text.replace(/\s+/g, ' ').trim();
    // the same headline from the socket and the DOM may differ in spacing/punctuation or carry a time prefix: compare loosely
    const key = (x: string) => x.toLowerCase().replace(/[^a-z0-9%$.]+/g, '');
    const k = key(clean);
    if (clean && this.s.news.some((n) => now - n.t < 10 * 60_000 && (n.text === clean || (k.length > 20 && (key(n.text).includes(k) || k.includes(key(n.text))))))) return;
    if (kind === 'snapshot' && !clean) return; // periodic price snapshot, nothing to suggest
    const event = this.newsEvent(msg);
    const parse = parseHeadline(clean, { aliases: this.cfg.headline.aliases });
    for (const [u, v] of Object.entries(structured)) parse.underlyings[u] = { ...v, ...parse.underlyings[u] };
    // an analyst message that names the analyst in a field rather than in the text
    const aField = Number(msg?.analyst);
    if (!parse.analysts.length && [1, 2, 3].includes(aField)) {
      for (const [u, v] of Object.entries(parse.underlyings)) {
        const val = v.iv ?? null;
        if (val != null) parse.analysts.push({ analyst: aField as AnalystId, underlying: u, value: normalizeVol(val), rawValue: val, raw: String(val), hasPct: false, isVol: true });
      }
      parse.underlyings = {};
    }
    const item: NewsItem = { seq, text: clean, t: now, src, event, parse, kind };
    this.s.news.unshift(item);
    if (this.s.news.length > 200) this.s.news.pop();
    if (event == null) return;
    const tl = this.timelineFor(event);
    if (!tl.headline && clean && !parse.analysts.length) tl.headline = clean;
    if (!this.s.baselines[event]) this.snapshotBaseline(event);
    const round = this.cfg.schedule.find((e) => e.n === event)?.round ?? null;
    for (const [u, v] of Object.entries(parse.underlyings)) {
      if (!this.s.targets[u]) continue;
      if (v.spot != null) this.suggest(u, 'spot', v.spot, `headline ("${v.spotRaw ?? v.spot}")`, event);
      else if (v.changePct != null) {
        const base = this.s.baselines[event]?.[u]?.oldSpot;
        if (base) this.suggest(u, 'spot', base * (1 + v.changePct / 100), `headline ${v.changePct > 0 ? '+' : ''}${v.changePct}%`, event);
      }
      // a vol outside the sane band when this event already has a sane reading for the underlying is a mis-read of a second
      // copy of the same news (a glued "0." from the DOM bar, 2026-10-24): drop it and keep what we had. With no sane
      // reading yet it is still shown, so the human sees "vol 400% outside bounds" instead of nothing.
      if (v.iv != null && !(v.iv >= this.cfg.auto.volMin && v.iv <= this.cfg.auto.volMax)) {
        const cur = this.s.targets[u].vol;
        const sane = (x: number | null | undefined) => x != null && x >= this.cfg.auto.volMin && x <= this.cfg.auto.volMax;
        if (cur.event === event && (sane(cur.suggestion?.value) || (cur.confirmed && sane(cur.value)))) {
          this.capture.add({ t: now, key: 'news:vol-ignored', dir: 'meta', raw: `${u} vol ${v.iv} (read "${v.ivRaw ?? v.iv}") outside ${this.cfg.auto.volMin}-${this.cfg.auto.volMax}, this event already has ${cur.suggestion?.value ?? cur.value}: ignored · ${clean.slice(0, 160)}`, highlights: [] });
          v.iv = undefined;
        }
      }
      if (v.iv != null) {
        this.suggest(u, 'vol', v.iv, `announced IV (read "${v.ivRaw ?? v.iv}")`, event);
        const t = this.s.targets[u];
        t.volLow = v.iv;
        t.volHigh = v.iv;
        t.bandNote = 'announced: band is a point';
      }
    }
    for (const a of parse.analysts) {
      if (!this.s.targets[a.underlying]) continue;
      const raw = round === 3 ? a.rawValue : a.value;
      this.setAnalyst(event, a.underlying, a.analyst, raw, 'parsed', false);
    }
    if (parse.analysts.length) {
      if (round === 3) this.tryAutoConverter(event, clean, parse);
      this.refreshBlend(event);
    }
    this.autoConfirm(event);
  }

  // ---------------- auto-pilot: targets ----------------
  /** Why a target cannot be auto-confirmed yet, or ok with a description of what will be accepted. */
  autoCheck(u: string, event: number): { ok: boolean; reason: string; done?: boolean } {
    const t = this.s.targets[u];
    if (!t) return { ok: false, reason: 'unknown underlying' };
    const a = this.cfg.auto;
    const round = this.roundOf(event);
    const cand = (f: TargetField): { value: number; src: string } | null =>
      f.suggestion ? f.suggestion : f.event === event && f.value != null && f.src !== 'pre-news' ? { value: f.value, src: f.src } : null;
    const spot = cand(t.spot);
    const vol = cand(t.vol);
    if (!t.spot.suggestion && !t.vol.suggestion && t.spot.confirmed && t.vol.confirmed && t.spot.event === event && t.vol.event === event) {
      return { ok: false, reason: 'confirmed', done: true };
    }
    if (!spot) return { ok: false, reason: 'waiting for the spot in the news' };
    if (round === 1) {
      if (!vol || !vol.src.startsWith('announced')) return { ok: false, reason: 'waiting for the announced IV' };
    } else {
      const row = this.s.analystInputs[event]?.[u];
      const have = ANALYSTS.filter((x) => row?.[x]?.sigma != null);
      if (round === 3 && a.converter && this.s.auto.converter.status === 'idle') {
        return { ok: false, reason: `Round 3 quantity not identified yet (${this.s.auto.converter.reason || 'waiting for an analyst message'})` };
      }
      if (have.length < ANALYSTS.length) {
        const missing = ANALYSTS.filter((x) => !have.includes(x)).map((x) => `A${x}`).join(', ');
        return { ok: false, reason: `waiting for analyst${have.length === 2 ? '' : 's'} ${missing} (${have.length}/3)` };
      }
      if (!vol) return { ok: false, reason: 'no blended vol yet' };
    }
    const ref = this.d?.spot[u]?.value ?? this.s.baselines[event]?.[u]?.oldSpot ?? null;
    if (ref != null && ref > 0) {
      const dev = (Math.abs(spot.value - ref) / ref) * 100;
      if (dev > a.spotBoundPct) return { ok: false, reason: `spot ${spot.value.toFixed(2)} is ${dev.toFixed(0)}% from live ${ref.toFixed(2)} (bound ${a.spotBoundPct}%): confirm by hand` };
    }
    if (!(spot.value > 0)) return { ok: false, reason: `spot ${spot.value} is not positive: confirm by hand` };
    if (vol.value < a.volMin || vol.value > a.volMax) {
      return { ok: false, reason: `vol ${(vol.value * 100).toFixed(1)}% outside ${(a.volMin * 100).toFixed(0)}–${(a.volMax * 100).toFixed(0)}%: confirm by hand` };
    }
    return { ok: true, reason: `spot ${spot.value.toFixed(2)} (${spot.src}) · vol ${(vol.value * 100).toFixed(1)}% (${vol.src})` };
  }

  /** Accept complete, sane targets for this event without Alt+A. Records why when it cannot. */
  autoConfirm(event: number | null | undefined) {
    if (!this.cfg.auto.confirm || event == null) return;
    const ph = this.d?.phase;
    if (!ph?.event || ph.event.n !== event || !(ph.phase === 'NEWS' || ph.phase === 'UNDERLYING_MOVED')) return;
    const now = this.nowFn();
    let accepted = false;
    for (const u of this.cfg.underlyings) {
      if (!this.s.targets[u]) continue;
      const chk = this.autoCheck(u, event);
      if (chk.done) continue;
      if (chk.ok) {
        this.confirmTargets(u);
        this.s.auto.targets[u] = { status: 'confirmed', reason: chk.reason, event, t: now };
        accepted = true;
      } else {
        const prev = this.s.auto.targets[u];
        if (prev?.status === 'confirmed' && prev.event === event && !this.s.targets[u].spot.suggestion && !this.s.targets[u].vol.suggestion) continue;
        // still collecting (analysts arriving, spot not yet in the news) is not a request for a human: show it as pending
        const pending = /^(waiting for|no blended|Round 3 quantity not identified yet \(waiting)/.test(chk.reason);
        this.s.auto.targets[u] = { status: pending ? 'idle' : 'manual', reason: chk.reason, event, t: now };
      }
    }
    if (accepted) {
      this.recordTargets(event);
      this.changed(true);
    }
  }

  private confirmTargets(u: string) {
    const t = this.s.targets[u];
    if (!t) return;
    for (const field of ['spot', 'vol'] as const) {
      const f = t[field];
      if (f.suggestion) {
        f.value = f.suggestion.value;
        f.src = f.suggestion.src;
        f.suggestion = null;
      }
      if (f.value != null) f.confirmed = true;
    }
  }

  private recordTargets(ev: number) {
    const tl = this.timelineFor(ev);
    tl.targets = Object.fromEntries(this.cfg.underlyings.map((u) => [u, { spot: this.s.targets[u]?.spot.value ?? null, vol: this.s.targets[u]?.vol.value ?? null, src: `${this.s.targets[u]?.spot.src} / ${this.s.targets[u]?.vol.src}` }]));
  }

  // ---------------- auto-pilot: Round 3 converter ----------------
  tryAutoConverter(event: number, text: string, parse: HeadlineParse) {
    const ac = this.s.auto.converter;
    if (!this.cfg.auto.converter || ac.status === 'manual') return;
    // Samples accumulate across analysts; their unit labels must accumulate too.
    const evidenceText = this.s.news.filter((n) => n.event === event && n.parse.analysts.length).map((n) => n.text).join(' ') || text;
    const named = mentionedConverters(evidenceText);
    // Keep an inferred choice stable across prices and unitless messages, but
    // reconsider it when later explicit unit evidence contradicts that choice.
    if (ac.status === 'chosen' && (!named.length || named.every((id) => id === ac.id))) return;
    const samples: ConverterSample[] = parse.analysts.filter((a) => this.s.targets[a.underlying]).map((a) => ({ underlying: a.underlying, raw: a.rawValue, rawStr: a.raw }));
    for (const [u, row] of Object.entries(this.s.analystInputs[event] ?? {})) {
      for (const a of ANALYSTS) {
        const raw = row[a]?.raw;
        if (raw != null && !samples.some((x) => x.underlying === u && x.raw === raw)) samples.push({ underlying: u, raw });
      }
    }
    if (!samples.length) return;
    const spot: Record<string, number | null> = {};
    const strikes: Record<string, number[] | undefined> = {};
    for (const u of this.cfg.underlyings) {
      spot[u] = this.d?.spot[u]?.value ?? this.s.baselines[event]?.[u]?.oldSpot ?? null;
      strikes[u] = this.d?.chains[u]?.strikes;
    }
    const res = identifyConverter({ samples, text: evidenceText, marketIV: this.d?.marketIV ?? {}, spot, T: this.d?.T.years ?? 20 / 252, strikes, tolPts: this.cfg.auto.converterTolPts, tieMarginPts: this.cfg.auto.converterTieMarginPts, namedTolPts: this.cfg.auto.converterNamedTolPts });
    ac.ranked = res.ranked;
    ac.event = event;
    ac.reason = res.reason;
    if (res.id) {
      ac.status = 'chosen';
      ac.id = res.id;
      this.setConverter({ id: res.id, K: null }, 'auto');
      this.toast(`Round 3 quantity identified: ${CONVERTERS.find((c) => c.id === res.id)?.label ?? res.id} (${res.reason})`, 'info');
    } else {
      ac.status = 'idle';
      ac.id = null;
      // A previously approved analyst target may depend on the revoked unit.
      // Literal targets typed by the trader retain their confirmation.
      for (const [u, target] of Object.entries(this.s.targets)) {
        if (target.vol.event === event && target.vol.src.startsWith('analysts')) {
          target.vol.confirmed = false;
          this.s.auto.targets[u] = { status: 'manual', reason: res.reason, event, t: this.nowFn() };
        }
      }
      this.toast(`Round 3 converter not identified: ${res.reason}`, 'warn');
      this.changed(true);
    }
  }

  /** Forget an automatic or manual pick so the next analyst message re-runs the identification. */
  resetAutoConverter() {
    this.s.auto.converter = { status: 'idle', id: null, reason: '', event: null, ranked: [] };
    const ev = this.d.phase?.event?.n;
    if (ev != null && this.roundOf(ev) === 3) {
      const text = this.s.news.filter((n) => n.event === ev && n.parse.analysts.length).map((n) => n.text).join(' ');
      const parse: HeadlineParse = { underlyings: {}, analysts: this.s.news.filter((n) => n.event === ev).flatMap((n) => n.parse.analysts), mentions: [] };
      if (parse.analysts.length) this.tryAutoConverter(ev, text, parse);
    }
    this.changed(true);
  }

  // ---------------- auto-pilot: submissions ----------------
  setAutoPaused(paused: boolean) {
    this.s.auto.paused = paused;
    this.changed(true);
  }

  logAutoSubmit(t: Ticket, result: string) {
    const now = this.nowFn();
    this.s.auto.log.push({ t: now, symbol: t.symbol, side: t.side, qty: t.qty, price: t.price, source: t.source, event: this.d.phase?.event?.n ?? null, result });
    if (this.s.auto.log.length > 300) this.s.auto.log.shift();
    this.s.auto.lastSubmitAt = now;
    this.capture.add({ t: now, key: 'auto:submit', dir: 'meta', raw: JSON.stringify({ symbol: t.symbol, side: t.side, qty: t.qty, price: t.price, result }), highlights: [] });
    this.changed(true);
  }

  /** The page's POST /orders response that follows an auto click: attach the exchange's answer to the log line. */
  private noteOrderResponse(status: number, json: unknown, now: number) {
    const pending = [...this.s.auto.log].reverse().find((l) => (l.result === 'clicked' || l.result === 'posted') && now - l.t < 8000);
    if (!pending) return;
    const j = (json && typeof json === 'object' ? json : {}) as Record<string, unknown>;
    const detail = [j.status, j.filled_quantity != null && j.quantity != null ? `${j.filled_quantity}/${j.quantity} filled` : null, j.detail].filter(Boolean).join(', ');
    pending.result = status < 400 ? `sent · HTTP ${status}${detail ? ` ${detail}` : ''}` : `REJECTED · HTTP ${status}${detail ? ` ${detail}` : ''}`;
    this.capture.add({ t: now, key: 'auto:result', dir: 'meta', raw: JSON.stringify({ symbol: pending.symbol, side: pending.side, qty: pending.qty, price: pending.price, result: pending.result }), highlights: status >= 400 ? ['rejected'] : [] });
  }

  suggest(u: string, field: 'spot' | 'vol', value: number, src: string, event: number | null = this.d?.phase?.event?.n ?? null) {
    const t = this.s.targets[u];
    if (!t || !Number.isFinite(value)) return;
    const f = t[field];
    if (f.confirmed && f.event === event) f.suggestion = { value, src };
    else {
      t[field] = { value, src, confirmed: false, suggestion: null, event };
    }
  }

  /** Type a target. Typed values are confirmed immediately. */
  setTarget(u: string, field: 'spot' | 'vol', value: number | null) {
    const t = this.s.targets[u];
    if (!t) return;
    if (value == null || !Number.isFinite(value)) {
      t[field] = { value: null, src: '—', confirmed: false, suggestion: null };
    } else {
      const v = field === 'vol' ? normalizeVol(value) : value;
      t[field] = { value: v, src: 'typed', confirmed: true, suggestion: null, event: this.d?.phase?.event?.n ?? null };
      if (field === 'vol') {
        const lo = t.volLow;
        const hi = t.volHigh;
        if (lo == null || hi == null || v < lo || v > hi) {
          t.volLow = v;
          t.volHigh = v;
          t.bandNote = 'typed: band is a point';
        }
      }
    }
    this.changed(true);
  }

  acceptSuggestions() {
    for (const u of this.cfg.underlyings) {
      const t = this.s.targets[u];
      if (!t) continue;
      const d = this.d.effTargets[u];
      for (const field of ['spot', 'vol'] as const) {
        const f = t[field];
        if (f.suggestion) {
          f.value = f.suggestion.value;
          f.src = f.suggestion.src;
          f.suggestion = null;
        }
        if (f.value == null && d) {
          f.value = field === 'spot' ? d.spot : d.vol;
          f.src = field === 'spot' ? `live (${this.d.spot[u]?.src})` : 'market IV';
        }
        if (f.value != null) f.confirmed = true;
      }
    }
    const ev = this.d.phase?.event?.n;
    if (ev != null) {
      this.recordTargets(ev);
      for (const u of this.cfg.underlyings) this.s.auto.targets[u] = { status: 'confirmed', reason: 'accepted by hand (Alt+A)', event: ev, t: this.nowFn() };
    }
    this.changed(true);
  }

  setAnalyst(event: number, u: string, a: AnalystId, raw: number | null, src: 'parsed' | 'typed', recompute = true) {
    const ev = (this.s.analystInputs[event] ??= {});
    const row = (ev[u] ??= {});
    const cell = row[a];
    if (src === 'parsed' && cell?.src === 'typed') return; // never overwrite what the trader typed
    const round = this.cfg.schedule.find((e) => e.n === event)?.round ?? 2;
    const conv = this.convert(round, u, raw);
    row[a] = { raw, sigma: conv.sigma, src, note: conv.note };
    if (recompute) {
      this.refreshBlend(event);
      this.autoConfirm(event);
      this.changed(true);
    }
  }

  convert(round: number, u: string, raw: number | null): { sigma: number | null; note?: string } {
    if (raw == null || !Number.isFinite(raw)) return { sigma: null };
    if (round !== 3) return { sigma: normalizeVol(raw), note: raw > 3 ? `read ${raw} as ${raw}%` : `read ${raw} as ${(raw * 100).toFixed(1)}%` };
    const S = this.d?.effTargets[u]?.spot ?? this.d?.spot[u]?.value ?? null;
    const T = this.d?.T.years ?? 20 / 252;
    if (S == null) return { sigma: null, note: 'no spot' };
    const r = convertToSigma(this.s.converter.id, raw, {
      S, T, K: this.s.converter.K ?? undefined, strikes: this.d?.chains[u]?.strikes, formula: this.s.converter.formula,
      prior: this.d?.marketIV[u] ?? 0.5,
    });
    return { sigma: r.sigma, note: r.note };
  }

  setConverter(c: Partial<Raw['converter']>, by: 'auto' | 'manual' = 'manual') {
    Object.assign(this.s.converter, c);
    if (by === 'manual') {
      const ac = this.s.auto.converter;
      ac.status = 'manual';
      ac.id = this.s.converter.id;
      ac.reason = 'picked by hand; automatic identification is off until "re-run"';
    }
    // re-convert every round-3 cell
    for (const [evS, byU] of Object.entries(this.s.analystInputs)) {
      const ev = Number(evS);
      const round = this.cfg.schedule.find((e) => e.n === ev)?.round;
      if (round !== 3) continue;
      for (const [u, row] of Object.entries(byU)) {
        for (const a of ANALYSTS) {
          const cell = row[a];
          if (!cell) continue;
          const conv = this.convert(3, u, cell.raw);
          cell.sigma = conv.sigma;
          cell.note = conv.note;
        }
      }
      this.refreshBlend(ev);
    }
    const cur = this.d?.phase?.event?.n;
    if (cur != null && this.roundOf(cur) === 3) this.autoConfirm(cur);
    this.changed(true);
  }

  refreshBlend(event: number) {
    const ev = this.s.analystInputs[event];
    if (!ev) return;
    for (const [u, row] of Object.entries(ev)) {
      const est: Partial<Record<AnalystId, number>> = {};
      for (const a of ANALYSTS) if (row[a]?.sigma != null) est[a] = row[a]?.sigma as number;
      const b = blendAnalysts(est, u, this.s.history, this.cfg.blend);
      const t = this.s.targets[u];
      if (!t || b.vol == null) continue;
      // an announced IV for this event wins over analysts
      if (t.vol.src.startsWith('announced') && !t.vol.confirmed) continue;
      // what the trader typed for this event stays (a converter change re-blends, but must not undo a typed number)
      if (t.vol.confirmed && t.vol.src === 'typed' && t.vol.event === event) continue;
      this.suggest(u, 'vol', b.vol, `analysts ${b.mode}`, event);
      if (!(t.vol.confirmed && t.vol.src === 'typed')) {
        t.volLow = b.low;
        t.volHigh = b.high;
        t.bandNote = b.note;
      }
    }
  }

  snapshotBaseline(event: number) {
    const b: Record<string, Baseline> = {};
    for (const u of this.cfg.underlyings) {
      const pn = this.s.preNews[u];
      const spot = pn?.spot ?? this.d?.spot[u]?.value ?? null;
      const vol = pn?.vol ?? this.d?.marketIV[u] ?? null;
      if (spot != null && vol != null) b[u] = { oldSpot: spot, oldVol: vol };
    }
    this.s.baselines[event] = b;
    this.timelineFor(event).baseline = b;
  }

  timelineFor(n: number): EventLog {
    const round = this.cfg.schedule.find((e) => e.n === n)?.round ?? 0;
    return (this.s.timeline[n] ??= { n, round });
  }

  // ---------------- clock / phases (called every ~200 ms) ----------------
  tick() {
    const now = this.nowFn();
    const d = this.compute();
    this.d = d;
    const ph = d.phase;
    // rolling pre-news snapshot while no event is active
    if (ph && !(ph.phase === 'NEWS' || ph.phase === 'UNDERLYING_MOVED')) {
      for (const u of this.cfg.underlyings) {
        const sp = d.spot[u]?.value ?? null;
        const iv = d.marketIV[u] ?? null;
        if (sp != null || iv != null) this.s.preNews[u] = { spot: sp ?? this.s.preNews[u]?.spot ?? null, vol: iv ?? this.s.preNews[u]?.vol ?? null, t: now };
      }
    }
    const key = ph?.event ? `${ph.event.n}:${ph.phase}` : ph?.phase ?? null;
    if (key !== this.s.phaseKey) {
      const prev = this.s.phaseKey;
      this.s.phaseKey = key;
      if (prev !== null && ph?.event) this.onPhaseChange(ph, d);
      else if (prev === null && ph?.event && (ph.phase === 'NEWS' || ph.phase === 'UNDERLYING_MOVED') && !this.s.baselines[ph.event.n]) {
        this.snapshotBaseline(ph.event.n); // loaded mid-event: best effort
      }
    }
    // while an event's targets are still unconfirmed, re-judge the suggestions about once a second (cheap; returns at once
    // when nothing changed), so a late phase flip or a late-arriving number never leaves them waiting
    if (ph?.event && (ph.phase === 'NEWS' || ph.phase === 'UNDERLYING_MOVED') && !d.targetsConfirmed && this.cfg.auto.confirm && now - this.lastAutoJudgeAt > 1000) {
      this.lastAutoJudgeAt = now;
      this.autoConfirm(ph.event.n);
    }
    if (this.s.learnAt && now >= this.s.learnAt.at) {
      const ev = this.s.learnAt.event;
      this.s.learnAt = null;
      this.learn(ev);
    }
    this.s.recentLoads = this.s.recentLoads.filter((r) => now - r.t < 6000);
    if (this.s.toast && now - this.s.toast.t > 6000) this.s.toast = null;
    this.emit();
  }

  private onPhaseChange(ph: PhaseInfo, d: Derived) {
    const ev = ph.event as EventSpec;
    if (ph.phase === 'NEWS') {
      if (!this.s.baselines[ev.n]) this.snapshotBaseline(ev.n);
      // new event: anything set for an earlier event becomes an unconfirmed pre-news value
      for (const u of this.cfg.underlyings) {
        const t = this.s.targets[u];
        const b = this.s.baselines[ev.n]?.[u];
        if (!t) continue;
        if (t.spot.event !== ev.n) t.spot = { value: b?.oldSpot ?? null, src: 'pre-news', confirmed: false, suggestion: null, event: null };
        if (t.vol.event !== ev.n) {
          t.vol = { value: b?.oldVol ?? null, src: 'pre-news', confirmed: false, suggestion: null, event: null };
          t.volLow = b?.oldVol ?? null;
          t.volHigh = b?.oldVol ?? null;
          t.bandNote = 'no news yet';
        }
      }
      this.s.manualQueue = [];
      this.timelineFor(ev.n);
      for (const u of this.cfg.underlyings) this.s.auto.targets[u] = { status: 'idle', reason: 'waiting for the news', event: ev.n, t: this.nowFn() };
      if (!this.s.ui.pinned) this.s.ui.tab = 'Edge';
      // the headline often lands a few hundred ms before our interpolated clock enters NEWS: its suggestions are already
      // here, so judge them now rather than at the +60 s move (Round 1 traded nothing before the move without this)
      this.autoConfirm(ev.n);
    } else if (ph.phase === 'UNDERLYING_MOVED') {
      for (const u of this.cfg.underlyings) {
        const t = this.s.targets[u];
        const live = d.spot[u]?.value;
        if (!t || live == null) continue;
        if (t.spot.src === 'pre-news' || t.spot.value == null) this.suggest(u, 'spot', live, 'live after move', ev.n);
        else if (t.spot.value && Math.abs(live - t.spot.value) / t.spot.value > 0.005) {
          this.toast(`${u} moved to ${live.toFixed(2)} vs target ${t.spot.value.toFixed(2)}: check the target spot`, 'warn');
          t.spot.suggestion = { value: live, src: 'live after move' };
        }
      }
      this.autoConfirm(ev.n);
    } else if (ph.phase === 'SNAPPED') {
      this.s.learnAt = { event: ev.n, at: this.nowFn() + this.cfg.thresholds.learnDelayRealSec * 1000 };
      this.s.manualQueue = [];
      if (!this.s.ui.pinned) this.s.ui.tab = 'Risk';
    }
  }

  /** Post-snap: record true vol per underlying, score analysts, estimate edge captured. */
  learn(event: number) {
    const d = this.compute();
    const tl = this.timelineFor(event);
    tl.trueVol = {};
    tl.trueSpot = {};
    tl.analystErrors = {};
    for (const u of this.cfg.underlyings) {
      const tv = d.marketIV[u] ?? null;
      tl.trueVol[u] = tv;
      tl.trueSpot[u] = d.spot[u]?.value ?? null;
      const row = this.s.analystInputs[event]?.[u];
      if (tv == null || !row) continue;
      const estimates: Partial<Record<AnalystId, number>> = {};
      const errs: Partial<Record<AnalystId, number>> = {};
      for (const a of ANALYSTS) {
        const sg = row[a]?.sigma;
        if (sg != null) {
          estimates[a] = sg;
          errs[a] = sg - tv;
        }
      }
      tl.analystErrors[u] = errs;
      if (Object.keys(estimates).length) {
        this.s.history = this.s.history.filter((r) => !(r.event === event && r.underlying === u));
        this.s.history.push({ event, underlying: u, estimates, trueVol: tv, t: this.nowFn() });
      }
    }
    // edge captured: our fills during this event valued at the post-snap spot/vol
    const fills = this.s.fills.filter((f) => f.event === event);
    if (fills.length) {
      let cap = 0;
      for (const f of fills) {
        const c = d.contracts[f.symbol];
        const sp = c ? tl.trueSpot[c.underlying] : null;
        const vol = c ? tl.trueVol[c.underlying] : null;
        if (!c || sp == null || vol == null) continue;
        const fair = bsPrice(c.kind, sp, c.strike, vol, d.T.years);
        cap += (f.side.toLowerCase().startsWith('b') ? 1 : -1) * (fair - f.price) * f.qty * this.cfg.multiplier;
      }
      tl.captured = cap;
    }
    this.persistHistory();
    this.changed(true);
  }

  persistHistory() {
    if (this.s.competitionId) this.persist(`history:${this.s.competitionId}`, { history: this.s.history, timeline: this.s.timeline });
  }

  resetHistory() {
    this.s.history = [];
    this.s.timeline = {};
    this.persistHistory();
    this.changed(true);
  }

  // ---------------- tickets ----------------
  /** Next ticket from the manual (arb) queue, else the live plan; skips what was just loaded. */
  pickNext(kind: 'edge' | 'flatten', opts: { quiet?: boolean; exclude?: (t: Ticket) => boolean } = {}): Ticket | null {
    const say = (text: string, level: 'info' | 'warn') => {
      if (!opts.quiet) this.toast(text, level);
    };
    const anyConfirmed = Object.entries(this.d.confirmedUnderlyings).some(([u, ok]) => ok && this.s.targets[u]);
    if (kind === 'edge' && !this.d.targetsConfirmed && !this.s.manualQueue.length && !anyConfirmed) {
      say('Targets not confirmed: press Alt+A (or Accept) first', 'warn');
      return null;
    }
    if (kind === 'edge' && this.s.manualQueue.length) {
      if (!opts.exclude) return this.s.manualQueue.shift() ?? null;
      const i = this.s.manualQueue.findIndex((t) => !opts.exclude?.(t));
      if (i >= 0) return this.s.manualQueue.splice(i, 1)[0];
      return null;
    }
    let list = kind === 'edge' ? this.d.plan.filter((t) => !t.breach.length) : this.d.flatten;
    // one underlying still waiting for its targets (a mis-read, analysts arriving) must not hold the other one's tickets
    if (kind === 'edge' && !this.d.targetsConfirmed) list = list.filter((t) => this.d.confirmedUnderlyings[t.underlying] !== false);
    if (opts.exclude) list = list.filter((t) => !opts.exclude?.(t));
    if (!list.length) {
      say(kind === 'edge' ? 'No tickets clear the robust edge threshold' : 'Nothing to flatten', 'info');
      return null;
    }
    const recent = new Set(this.s.recentLoads.map((r) => r.sig));
    const t = list.find((x) => !recent.has(`${x.symbol}:${x.side}`)) ?? (opts.exclude ? null : list[0]);
    if (t && !t.withinRateBudget) say('Order-rate budget is exhausted for this minute', 'warn');
    return t;
  }

  markLoaded(t: Ticket, ok: boolean | null, message: string) {
    this.s.loaded = { ticket: t, t: this.nowFn(), ok, message };
    this.s.recentLoads.push({ sig: `${t.symbol}:${t.side}`, t: this.nowFn() });
    this.changed(true);
  }

  queueArb(f: ArbFlag) {
    const tick = this.d.tick;
    this.s.manualQueue = ticketsFromArb(f, this.d.contracts, this.cfg.thresholds.perTicketCap, tick);
    this.toast(`${this.s.manualQueue.length} linked tickets queued: Alt+N loads them in order`, 'info');
    this.changed(true);
  }

  setManualPositions(p: Record<string, number> | null) {
    this.s.manualPositions = p;
    if (p) {
      this.s.positions = { ...p };
      this.s.positionsSrc = 'manual';
      this.s.positionsAt = this.nowFn();
    }
    this.changed(true);
  }

  // ---------------- derived ----------------
  compute(): Derived {
    const now = this.nowFn();
    const cfg = this.cfg;
    const s = this.s;
    const th = cfg.thresholds;

    // mode
    let mode: Derived['mode'] = 'capture-only';
    let modeReason = 'no derivatives signals yet';
    if (cfg.mode === 'derivatives') {
      mode = 'derivatives';
      modeReason = 'forced in Config';
    } else if (cfg.mode === 'auto') {
      let caseRe: RegExp | null = null;
      try {
        caseRe = new RegExp(cfg.caseNameRegex, 'i');
      } catch {
        caseRe = null;
      }
      if (s.caseName && caseRe?.test(s.caseName)) {
        mode = 'derivatives';
        modeReason = `case "${s.caseName}"`;
      } else if (cfg.underlyings.every((u) => s.symbolsSeen.some((x) => x.toUpperCase() === u))) {
        mode = 'derivatives';
        modeReason = `symbols include ${cfg.underlyings.join(' & ')}`;
      } else if (Object.keys(s.metas).length) {
        mode = 'derivatives';
        modeReason = 'option symbols seen';
      }
    }

    // clock
    let simNow: number | null = null;
    let clockSrc: Derived['clockSrc'] = 'none';
    const c = s.clock;
    const clockStale = !s.lastClockPollAt || now - s.lastClockPollAt > th.staleClockSec * 1000;
    let clockRate = c.rate ?? 0;
    if (c.fictionalSec != null && !clockStale) {
      const running = !c.state || /run|open|active|live/i.test(c.state);
      simNow = c.fictionalSec + (running ? ((now - c.receivedAt) * (c.rate ?? 0)) / 1000 : 0);
      clockSrc = 'REST';
    } else if (s.domClock && now - s.domClock.t < 5000) {
      const baseDate = c.fictionalSec != null ? dayStart(c.fictionalSec) : parseNaiveSec(`${cfg.schedule[0]?.date ?? '2026-06-01'}T00:00:00`) ?? 0;
      const ev = (this.rebased?.schedule ?? cfg.schedule).find((e) => e.date === fmtDate(baseDate));
      clockRate = c.rate ?? (ev?.round === 3 ? cfg.fallbackClockRate.round3 : cfg.fallbackClockRate.rounds12);
      simNow = baseDate + s.domClock.sec + ((now - s.domClock.t) * clockRate) / 1000;
      clockSrc = 'DOM';
    } else if (c.fictionalSec != null) {
      simNow = c.fictionalSec;
      clockSrc = 'REST';
    }
    // the exchange's fictional dates need not be the packet's: rebase the layout onto them (cached per date)
    let schedule = cfg.schedule;
    let scheduleNote: string | null = null;
    if (simNow != null && mode === 'derivatives') {
      const today = fmtDate(simNow);
      if (!cfg.schedule.some((e) => e.date === today) && today >= '2000-01-01') {
        if (this.rebased?.today !== today) {
          const lr = clockSrc === 'REST' && c.rate != null && c.rate > 0 ? c.rate : null;
          const rates = lr != null && Math.abs(lr / cfg.fallbackClockRate.rounds12 - 1) >= 0.05 && Math.abs(lr / cfg.fallbackClockRate.round3 - 1) >= 0.05 ? { rounds12: lr, round3: lr } : cfg.fallbackClockRate;
          const rb = rebaseSchedule(cfg.schedule, simNow, c.elapsedActiveSec ?? null, rates, { open: cfg.session.open, close: cfg.session.close });
          this.rebased = rb ? { today, schedule: rb } : null;
        }
        if (this.rebased) {
          schedule = this.rebased.schedule;
          const ds = [...new Set(schedule.map((e) => e.date))].sort();
          scheduleNote = `exchange date ${today} is not in the packet schedule: rebased to ${ds[0]}..${ds[ds.length - 1]} (day ${ds.indexOf(today) + 1}${c.elapsedActiveSec != null ? ` from ${Math.round(c.elapsedActiveSec)} s elapsed` : ', elapsed unknown: assumed day 1'})`;
        }
      }
    } else if (this.rebased) this.rebased = null;
    // the exchange's clock rate need not be the packet's either: today's move/snap boundaries follow the live rate
    const liveRate = clockSrc === 'REST' && c.rate != null && c.rate > 0 ? c.rate : null;
    if (simNow != null && liveRate != null && mode === 'derivatives') {
      const today = fmtDate(simNow);
      const offsets = cfg.eventOffsetsRealSec ?? { move: 60, snap: 120 };
      const adj = withLiveRate(schedule, liveRate, today, offsets, cfg.fallbackClockRate);
      if (adj !== schedule) {
        schedule = adj;
        const ev = adj.find((e) => e.date === today);
        const note = `clock ${liveRate.toFixed(1)}/min, packet ${packetRateForDate(adj, today, cfg.fallbackClockRate)}: today's move/snap set ${offsets.move}/${offsets.snap} real s after the news (E${ev?.n} ${ev?.news} → ${ev?.move} / ${ev?.snap})`;
        scheduleNote = scheduleNote ? `${scheduleNote}; ${note}` : note;
      }
    }
    const phase = simNow != null ? phaseAt(simNow, schedule, { open: cfg.session.open, close: cfg.session.close }) : null;
    const realToNext = phase ? realSecondsToNext(phase, clockRate) : null;
    const round = phase?.event?.round ?? null;

    // risk-free rate: the chain's risk_free_rate (every pricing call reads it); 0 until the exchange says otherwise
    const restFresh = (u: string) => {
      const rc = s.restChain[u];
      return rc && now - rc.t < 5000 ? rc : null;
    };
    let r = 0;
    for (const u of cfg.underlyings) {
      const rc = s.restChain[u];
      if (rc && Number.isFinite(rc.r)) r = rc.r;
    }
    if (r !== getRate()) setRate(r);

    // time to expiry
    let T: Derived['T'];
    const computed = () => {
      if (simNow == null) return { days: 20, src: 'computed (no clock: 20d)' };
      let t = simNow;
      if (phase?.replay) {
        const first = parseNaiveSec(`${schedule[0]?.date ?? '2026-06-01'}T00:00:00`) ?? 0;
        t = first + secOfDay(simNow);
      }
      // the chain's expiry_fictional_time beats the packet's date in Config
      const chainExpiry = cfg.underlyings.map((u) => s.restChain[u]?.expiry).find((e) => e && parseNaiveSec(e) != null);
      const session = chainExpiry ? { ...cfg.session, expiry: chainExpiry } : cfg.session;
      return { days: tradingDaysRemaining(t, session), src: phase?.replay ? 'computed (replay)' : chainExpiry ? 'computed (chain expiry)' : 'computed' };
    };
    const restT = cfg.underlyings.map((u) => restFresh(u)?.tDays ?? null).find((x) => x != null && x > 0) ?? null;
    if (cfg.T_mode === 'manual' && cfg.manualTDays != null) T = { days: cfg.manualTDays, years: cfg.manualTDays / 252, src: 'manual' };
    else if (cfg.T_mode === 'fixed20') T = { days: 20, years: 20 / 252, src: 'fixed 20d' };
    else if (restT != null) T = { days: restT, years: Math.round(restT * 1000) / 1000 / 252, src: 'REST chain' };
    else if (cfg.T_mode === 'dom' && s.domT && now - s.domT.t < 5000 && s.domT.days > 0) T = { days: s.domT.days, years: s.domT.days / 252, src: 'DOM Fair tab' };
    else {
      const x = computed();
      T = { days: x.days, years: x.days / 252, src: x.src };
    }

    // chains + spot
    const chains = buildChains(Object.values(s.metas), s.quotes);
    const contracts = contractsBySymbol(chains);
    const spot: Derived['spot'] = {};
    const mIV: Record<string, number | null> = {};
    const domUnd = s.domChain && s.domSpot && now - s.domSpot.t < 5000 ? this.domChainUnderlying(s.domChain.strikes) : null;
    for (const u of cfg.underlyings) {
      const q = s.undQuotes[u];
      const qMid = q ? (q.bid != null && q.ask != null ? (q.bid + q.ask) / 2 : q.last ?? q.bid ?? q.ask) : null;
      const ch = chains[u];
      const par = ch ? parityImpliedSpot(ch, T.years) : null;
      const rc = restFresh(u);
      if (rc && rc.spot != null && rc.spot > 0 && (!q || now - q.t > 1500 || now - rc.t <= now - q.t)) spot[u] = { value: rc.spot, src: 'REST', age: (now - rc.t) / 1000 };
      else if (q && qMid != null && now - q.t < 30_000) spot[u] = { value: qMid, src: 'WS', age: (now - q.t) / 1000 };
      else if (rc && rc.spot != null && rc.spot > 0) spot[u] = { value: rc.spot, src: 'REST', age: (now - rc.t) / 1000 };
      else if (domUnd === u && s.domSpot) spot[u] = { value: s.domSpot.value, src: 'DOM', age: (now - s.domSpot.t) / 1000 };
      else if (par != null) spot[u] = { value: par, src: 'parity', age: null };
      else if (qMid != null) spot[u] = { value: qMid, src: 'WS (stale)', age: q ? (now - q.t) / 1000 : null };
      else spot[u] = { value: null, src: 'none', age: null };
      const sv = spot[u].value;
      mIV[u] = ch && sv != null ? marketIV(ch, sv, T.years, th.minVegaForIV) : null;
    }

    // tick size
    const prices: number[] = [];
    for (const q of Object.values(s.quotes)) {
      if (q.bid != null) prices.push(q.bid);
      if (q.ask != null) prices.push(q.ask);
    }
    const tick = cfg.tick ?? s.exchange.tick ?? inferTick(prices.slice(0, 200), 0.01);

    // effective targets (fall back to live values so the tables always render)
    const effTargets: Derived['effTargets'] = {};
    const blends: Record<string, BlendResult | null> = {};
    let targetsConfirmed = true;
    const confirmedUnderlyings: Record<string, boolean> = {};
    for (const u of cfg.underlyings) {
      const t = s.targets[u];
      const sp = t?.spot.value ?? spot[u]?.value ?? null;
      const vol = t?.vol.value ?? mIV[u] ?? null;
      confirmedUnderlyings[u] = !t || (t.spot.confirmed && t.vol.confirmed);
      if (t && (!t.spot.confirmed || !t.vol.confirmed) && (!cfg.focus || cfg.focus === u)) targetsConfirmed = false;
      if (sp != null && vol != null && sp > 0 && vol > 0) {
        let lo = t?.volLow ?? vol;
        let hi = t?.volHigh ?? vol;
        if (lo > vol) lo = vol;
        if (hi < vol) hi = vol;
        effTargets[u] = { spot: sp, vol, volLow: lo, volHigh: hi };
      }
      const ev = phase?.event?.n;
      const row = ev != null ? s.analystInputs[ev]?.[u] : undefined;
      if (row) {
        const est: Partial<Record<AnalystId, number>> = {};
        for (const a of ANALYSTS) if (row[a]?.sigma != null) est[a] = row[a]?.sigma as number;
        blends[u] = blendAnalysts(est, u, s.history, cfg.blend);
      } else blends[u] = null;
    }

    // edges, structures, arbitrage
    const positions = s.manualPositions ?? s.positions;
    const edges: Record<string, EdgeRow[]> = {};
    const synths: Record<string, Structure[]> = {};
    const strads: Record<string, Structure[]> = {};
    const arbs: ArbFlag[] = [];
    const ev = phase?.event?.n;
    // the exchange's own max_position (GET /symbols) caps what Config allows: a limit breach is a rejected order or a penalty
    const exLimit = s.exchange.maxPosition != null && s.exchange.maxPosition > 0 ? s.exchange.maxPosition : null;
    const positionLimit = exLimit != null ? Math.min(th.positionLimit, exLimit) : th.positionLimit;
    const perTicketCap = Math.min(th.perTicketCap, positionLimit);
    const edgeOpts = { positionLimit, perTicketCap, minEdge: th.minEdge, multiplier: cfg.multiplier, tick };
    const structOpts = { positionLimit, perTicketCap };
    for (const u of cfg.underlyings) {
      const ch = chains[u];
      const tg = effTargets[u];
      if (!ch) continue;
      if (tg) {
        const base = ev != null ? s.baselines[ev]?.[u] ?? null : null;
        edges[u] = computeEdges(ch, tg, base, T.years, positions, s.resting, edgeOpts);
        synths[u] = syntheticForwards(ch, tg.spot, T.years, tg.vol, positions, s.resting, structOpts);
        strads[u] = straddles(ch, tg.spot, tg.vol, T.years, positions, s.resting, structOpts);
      }
      arbs.push(...findArbs(ch, spot[u]?.value ?? null, T.years, { eps: th.arbEps, ivOutlierPts: th.ivOutlierPts, minVega: th.minVegaForIV, cap: th.perTicketCap }));
    }

    // risk
    const riskInputs: Record<string, { spot: number; vol: number } | undefined> = {};
    for (const u of cfg.underlyings) {
      const tg = effTargets[u];
      if (tg) riskInputs[u] = { spot: tg.spot, vol: tg.vol };
    }
    const pf = portfolio(chains, positions, riskInputs, T.years, cfg.multiplier);
    const caps = { maxAbsDeltaPerUnderlying: th.maxAbsDeltaPerUnderlying, maxAbsVegaPts: th.maxAbsVegaPts };
    const breaches = capBreaches(pf, caps);
    const flattenNow = phase?.nextPhase === 'NEWS' && realToNext != null && realToNext <= th.flattenWarnRealSec && needsFlatten(pf, caps, th.flattenWarnFraction);
    const rate = this.rate.status(now);

    const allEdges = Object.values(edges).flat();
    const allSynths = Object.values(synths).flat();
    const plan = planTickets({
      edges: allEdges, structures: allSynths, contracts, targets: riskInputs, T: T.years, positions, resting: s.resting,
      bookGreeks: Object.fromEntries(Object.entries(pf.perUnderlying).map(([u, b]) => [u, { delta: b.delta, vega: b.vega }])),
      caps, positionLimit, perTicketCap, minEdge: th.minEdge, rateRemaining: rate.remaining,
      round, preferSynthForSpot: cfg.preferSynthForSpot, priceMode: cfg.priceMode, tick, focus: cfg.focus, multiplier: cfg.multiplier,
      edgeThroughFrac: th.edgeThroughFrac ?? 0, synthOnly: th.synthOnly ?? false,
    });
    const fl = flattenOrders(chains, positions, riskInputs, T.years, caps, perTicketCap, { pct: th.flattenThroughPct ?? 0, ticks: th.flattenThroughTicks ?? 0, tick }, s.resting);
    const flatten = ticketsFromFlatten(fl.orders, tick, rate.remaining, cfg.focus);

    let quoteAge: number | null = null;
    for (const q of Object.values(s.quotes)) {
      const age = (now - q.t) / 1000;
      if (quoteAge == null || age < quoteAge) quoteAge = age;
    }

    return {
      r,
      now, mode, modeReason, simNow, clockSrc, clockStale, clockRate, replay: !!phase?.replay, schedule, scheduleNote, phase, realToNext, round, T,
      chains, contracts, spot, marketIV: mIV, effTargets, blends, edges, synths, straddles: strads, arbs,
      portfolio: pf, breaches, flattenNow, plan, flatten, flattenCost: fl.totalSpreadCost, rate, quoteAge, tick, targetsConfirmed, confirmedUnderlyings, positionLimit, perTicketCap,
      autoArmed: cfg.auto.submit && !s.auto.paused && mode === 'derivatives',
    };
  }

  analystTable(u?: string) {
    return analystStats(this.s.history, u);
  }

  roundOf(event: number | null | undefined): number | null {
    return this.cfg.schedule.find((e) => e.n === event)?.round ?? null;
  }

  sessionOpenSec(): number {
    return hmsToSec(this.cfg.session.open);
  }
}

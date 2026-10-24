// Runtime configuration: everything game-day patchable lives here and is editable as JSON in the Config tab.
import { BandMode, BlendMode } from '../engine/analysts';
import { DEFAULT_OPTION_REGEX } from '../engine/chain';
import { DEFAULT_HEADLINE_CONFIG } from '../engine/headline';
import { DEFAULT_SCHEDULE, EventSpec } from '../engine/schedule';
import { DEFAULT_SESSION, SessionSpec } from '../engine/tradingTime';

export interface FieldMap {
  quote: { symbol: string[]; bid: string[]; ask: string[]; bidSize: string[]; askSize: string[]; last: string[] };
  positions: { list: string[]; symbol: string[]; qty: string[] };
  orders: { list: string[]; symbol: string[]; side: string[]; remaining: string[]; status: string[] };
  clock: { fictionalTime: string[]; clockRate: string[]; state: string[]; name: string[]; id: string[] };
}

export interface DomHints {
  qtyLabel: string;
  priceLabel: string;
  buyText: string;
  sellText: string;
  limitText: string;
  marketText: string;
  strikeHeader: string;
  callsHeader: string;
  putsHeader: string;
  latestLabel: string;
  positionsLabel: string;
  spotPattern: string;
  tPattern: string;
  clockPattern: string;
}

export interface Thresholds {
  minEdge: number;
  ivOutlierPts: number;
  arbEps: number;
  positionLimit: number;
  perTicketCap: number;
  maxAbsDeltaPerUnderlying: number;
  maxAbsVegaPts: number;
  staleQuoteSec: number;
  staleClockSec: number;
  minVegaForIV: number;
  flattenWarnFraction: number;
  flattenWarnRealSec: number;
  learnDelayRealSec: number;
  /** flatten tickets are priced this far through the touch so one order clears several levels (snap -> next news is 30 s) */
  flattenThroughPct: number;
  flattenThroughTicks: number;
}

/** Auto-pilot: what the overlay does on its own per event. autoSubmit stays OFF until the organisers allow a bot to click. */
export interface AutoConfig {
  /** accept parsed targets without Alt+A when the parse is complete and passes the sanity bounds */
  confirm: boolean;
  /** Round 3: identify the analysts' IV-linked quantity from the first message by matching the market IV */
  converter: boolean;
  /** a converter candidate must land within this many vol points of the market IV */
  converterTolPts: number;
  /** the best candidate must beat the runner-up by this many vol points, unless a keyword names it */
  converterTieMarginPts: number;
  /** Round 3: a quantity the analyst message names is trusted up to this many vol points from the (stale) market IV */
  converterNamedTolPts: number;
  /** load, verify and click the exchange's submit button for each ticket (Alt+P pauses) */
  submit: boolean;
  /** our own cap on observed order actions per minute while auto-submitting (packet: 40 from the browser) */
  submitRateCap: number;
  /** minimum real ms between two auto submissions */
  submitIntervalMs: number;
  /** do not resubmit the same contract/side within this many ms unless the position changed */
  resubmitAfterMs: number;
  /** flatten tickets may be re-sent for the same contract/side after this many ms (they are re-sized from the position) */
  flattenResubmitMs: number;
  /** edge tickets stop when the rolling-minute order count reaches submitRateCap - flattenReserve, so the snap always has orders left */
  flattenReserve: number;
  /** minimum real ms between two auto submissions while flattening (the snap-to-next-news window is 30 s) */
  flattenIntervalMs: number;
  /** a parsed spot must be within this % of the live (or pre-news) spot to auto-confirm */
  spotBoundPct: number;
  /** a parsed/blended vol must be inside [volMin, volMax] (decimals) to auto-confirm */
  volMin: number;
  volMax: number;
  /** also click the OIL/PLANE product tab when the chain shows the other underlying */
  switchTabs: boolean;
  /** 'api': POST /api/v1/orders through the session cookie (what the Buy button does); 'form': prefill the page's form and click */
  submitVia: 'api' | 'form';
  /** cancel every resting option order (per underlying) when the makers snap and when the next news arrives */
  cancelOnSnap: boolean;
  cancelOnNews: boolean;
  /** pause submissions this long after an HTTP 429 */
  backoffMs: number;
  /** after "Trading halted" / "not found" on a contract, leave it alone this long (ms) */
  haltedPauseMs: number;
}

/** REST polling through the session cookie (Config.api); 0 disables one endpoint */
export interface ApiConfig {
  enabled: boolean;
  clockMs: number;
  symbolsMs: number;
  chainMs: number;
  positionsMs: number;
  ordersMs: number;
  tradesMs: number;
}

/** the overlay's own market-data socket (Config.feed) */
export interface FeedConfig {
  enabled: boolean;
  channels: string[];
  path: string;
}

export interface Config {
  mode: 'auto' | 'derivatives' | 'capture-only';
  underlyings: string[];
  symbolRegex: string;
  caseNameRegex: string;
  fields: FieldMap;
  dom: DomHints;
  schedule: EventSpec[];
  session: SessionSpec;
  T_mode: 'dom' | 'computed' | 'fixed20' | 'manual';
  manualTDays: number | null;
  fallbackClockRate: { rounds12: number; round3: number };
  /** packet: the market bots move the underlying 1 real minute after the news and the options 2 real minutes after; with a live
   * clock rate other than the packet's the move/snap boundaries are recomputed from these */
  eventOffsetsRealSec: { move: number; snap: number };
  thresholds: Thresholds;
  blend: { mode: BlendMode; lambda: number; k: number; bandMode: BandMode };
  rate: { limit: number; amberAt: number; redAt: number };
  headline: { aliases: Record<string, string[]> };
  multiplier: number;
  tick: number | null;
  priceMode: 'touch' | 'passive';
  preferSynthForSpot: boolean;
  prefillEnabled: boolean;
  focus: string | null;
  auto: AutoConfig;
  api: ApiConfig;
  feed: FeedConfig;
}

export const DEFAULT_CONFIG: Config = {
  mode: 'auto',
  underlyings: ['OIL', 'PLANE'],
  symbolRegex: DEFAULT_OPTION_REGEX,
  caseNameRegex: 'euleria|newtonia|derivativ|option',
  fields: {
    quote: { symbol: ['symbol', 'sym', 'ticker'], bid: ['bid', 'bid_price', 'best_bid'], ask: ['ask', 'ask_price', 'best_ask'], bidSize: ['bid_size', 'bidSize', 'bid_qty'], askSize: ['ask_size', 'askSize', 'ask_qty'], last: ['last', 'price', 'last_price'] },
    positions: { list: ['positions', 'data', 'items', 'results'], symbol: ['symbol', 'sym', 'ticker', 'instrument'], qty: ['quantity', 'net_quantity', 'position', 'qty', 'net_position', 'size'] },
    orders: { list: ['orders', 'data', 'items', 'results'], symbol: ['symbol', 'sym', 'ticker'], side: ['side', 'direction'], remaining: ['remaining_quantity', 'remaining', 'leaves_quantity', 'open_quantity', 'quantity', 'qty'], status: ['status', 'state'] },
    clock: { fictionalTime: ['fictional_time', 'fictionalTime', 'sim_time'], clockRate: ['clock_rate', 'clockRate', 'rate'], state: ['state', 'status'], name: ['name', 'case', 'title'], id: ['competition_id', 'id'] },
  },
  dom: {
    qtyLabel: 'QTY',
    priceLabel: 'PRICE',
    buyText: 'BUY',
    sellText: 'SELL',
    limitText: 'Limit',
    marketText: 'Market',
    strikeHeader: 'STRIKE',
    callsHeader: 'CALLS',
    putsHeader: 'PUTS',
    latestLabel: 'LATEST',
    positionsLabel: 'Positions',
    spotPattern: 'Spot\\s*\\$?\\s*([0-9]+(?:\\.[0-9]+)?)',
    tPattern: 'T[^0-9]{0,8}([0-9]*\\.?[0-9]+)\\s*yr\\s*\\(\\s*([0-9]*\\.?[0-9]+)\\s*trading\\s*days?\\s*\\)',
    clockPattern: '^\\s*(\\d{1,2}):(\\d{2}):(\\d{2})\\s*$',
  },
  schedule: DEFAULT_SCHEDULE,
  session: DEFAULT_SESSION,
  T_mode: 'dom',
  manualTDays: null,
  fallbackClockRate: { rounds12: 52, round3: 39 },
  eventOffsetsRealSec: { move: 60, snap: 120 },
  thresholds: {
    minEdge: 0.05,
    ivOutlierPts: 1.5,
    arbEps: 0.02,
    positionLimit: 300,
    perTicketCap: 300,
    maxAbsDeltaPerUnderlying: 300,
    maxAbsVegaPts: 150,
    staleQuoteSec: 3,
    staleClockSec: 3,
    minVegaForIV: 0.02,
    flattenWarnFraction: 0.1,
    flattenWarnRealSec: 30,
    flattenThroughPct: 2,
    flattenThroughTicks: 5,
    learnDelayRealSec: 5,
  },
  blend: { mode: 'median', lambda: 0.0025, k: 1, bandMode: 'auto' },
  rate: { limit: 40, amberAt: 30, redAt: 36 },
  headline: DEFAULT_HEADLINE_CONFIG,
  multiplier: 1,
  tick: null,
  priceMode: 'touch',
  preferSynthForSpot: true,
  prefillEnabled: true,
  focus: null,
  auto: {
    confirm: true, converter: true, converterTolPts: 8, converterTieMarginPts: 2, converterNamedTolPts: 40,
    submit: false, submitRateCap: 12, submitIntervalMs: 5000, resubmitAfterMs: 20_000, flattenResubmitMs: 6_000, flattenReserve: 4, flattenIntervalMs: 5000,
    spotBoundPct: 40, volMin: 0.05, volMax: 3.0, switchTabs: true,
    submitVia: 'api', cancelOnSnap: true, cancelOnNews: true, backoffMs: 5000, haltedPauseMs: 30_000,
  },
  api: { enabled: true, clockMs: 1000, symbolsMs: 15_000, chainMs: 1000, positionsMs: 1000, ordersMs: 1500, tradesMs: 3000 },
  feed: { enabled: true, channels: ['quotes', 'trades', 'news'], path: '/ws/v1/market-data' },
};

const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);

export function deepMerge<T>(base: T, patch: unknown): T {
  if (!isObj(base) || !isObj(patch)) return (patch === undefined ? base : patch) as T;
  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) };
  for (const [k, v] of Object.entries(patch)) {
    const b = (base as Record<string, unknown>)[k];
    out[k] = isObj(b) && isObj(v) && k !== 'aliases' ? deepMerge(b, v) : v;
  }
  return out as T;
}

export function cloneDefaults(): Config {
  return JSON.parse(JSON.stringify(DEFAULT_CONFIG));
}

export interface Validation {
  ok: boolean;
  config: Config;
  errors: string[];
}

export function validateConfig(input: unknown): Validation {
  const errors: string[] = [];
  let parsed = input;
  if (typeof input === 'string') {
    try {
      parsed = JSON.parse(input);
    } catch (e) {
      return { ok: false, config: cloneDefaults(), errors: ['JSON: ' + (e instanceof Error ? e.message : String(e))] };
    }
  }
  if (!isObj(parsed)) return { ok: false, config: cloneDefaults(), errors: ['config must be a JSON object'] };
  const c = deepMerge(cloneDefaults(), parsed);
  const re = (name: string, src: unknown) => {
    if (typeof src !== 'string') return errors.push(`${name} must be a string`);
    try {
      new RegExp(src);
    } catch (e) {
      errors.push(`${name}: invalid regex (${e instanceof Error ? e.message : e})`);
    }
  };
  if (!['auto', 'derivatives', 'capture-only'].includes(c.mode)) errors.push('mode must be auto | derivatives | capture-only');
  if (!['dom', 'computed', 'fixed20', 'manual'].includes(c.T_mode)) errors.push('T_mode must be dom | computed | fixed20 | manual');
  if (!['touch', 'passive'].includes(c.priceMode)) errors.push('priceMode must be touch | passive');
  re('symbolRegex', c.symbolRegex);
  re('caseNameRegex', c.caseNameRegex);
  re('dom.spotPattern', c.dom.spotPattern);
  re('dom.tPattern', c.dom.tPattern);
  re('dom.clockPattern', c.dom.clockPattern);
  for (const [u, pats] of Object.entries(c.headline.aliases ?? {})) {
    if (!Array.isArray(pats)) errors.push(`headline.aliases.${u} must be an array`);
    else pats.forEach((p, i) => re(`headline.aliases.${u}[${i}]`, p));
  }
  if (!Array.isArray(c.underlyings) || !c.underlyings.every((u) => typeof u === 'string')) errors.push('underlyings must be a string array');
  if (!Array.isArray(c.schedule)) errors.push('schedule must be an array');
  else
    c.schedule.forEach((e, i) => {
      const hms = /^\d{1,2}:\d{2}(:\d{2})?$/;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(String(e.date))) errors.push(`schedule[${i}].date must be YYYY-MM-DD`);
      for (const k of ['news', 'move', 'snap'] as const) if (!hms.test(String(e[k]))) errors.push(`schedule[${i}].${k} must be HH:MM[:SS]`);
      if (![1, 2, 3].includes(Number(e.round))) errors.push(`schedule[${i}].round must be 1, 2 or 3`);
    });
  for (const [k, v] of Object.entries(c.thresholds)) if (typeof v !== 'number' || !Number.isFinite(v)) errors.push(`thresholds.${k} must be a number`);
  if (c.manualTDays != null && !(typeof c.manualTDays === 'number' && c.manualTDays >= 0)) errors.push('manualTDays must be null or a number >= 0');
  if (c.tick != null && !(typeof c.tick === 'number' && c.tick > 0)) errors.push('tick must be null (auto) or a positive number');
  if (!(typeof c.multiplier === 'number' && c.multiplier > 0)) errors.push('multiplier must be > 0');
  const a = c.auto as unknown as Record<string, unknown>;
  if (!isObj(a)) errors.push('auto must be an object');
  else {
    for (const k of ['confirm', 'converter', 'submit', 'switchTabs']) if (typeof a[k] !== 'boolean') errors.push(`auto.${k} must be true or false`);
    for (const k of ['converterTolPts', 'converterTieMarginPts', 'converterNamedTolPts', 'submitRateCap', 'submitIntervalMs', 'resubmitAfterMs', 'flattenResubmitMs', 'flattenReserve', 'flattenIntervalMs', 'spotBoundPct', 'volMin', 'volMax']) {
      if (typeof a[k] !== 'number' || !Number.isFinite(a[k] as number) || (a[k] as number) < 0) errors.push(`auto.${k} must be a number >= 0`);
    }
    if (typeof a.submitRateCap === 'number' && a.submitRateCap > 40) errors.push('auto.submitRateCap must not exceed the browser limit of 40');
    if (!['api', 'form'].includes(String(a.submitVia))) errors.push('auto.submitVia must be api | form');
    for (const k of ['cancelOnSnap', 'cancelOnNews']) if (typeof a[k] !== 'boolean') errors.push(`auto.${k} must be true or false`);
    if (typeof a.backoffMs !== 'number' || !(a.backoffMs >= 0)) errors.push('auto.backoffMs must be a number >= 0');
    if (typeof a.haltedPauseMs !== 'number' || !(a.haltedPauseMs >= 0)) errors.push('auto.haltedPauseMs must be a number >= 0');
    if (typeof a.volMin === 'number' && typeof a.volMax === 'number' && a.volMin >= a.volMax) errors.push('auto.volMin must be below auto.volMax');
  }
  const api = c.api as unknown as Record<string, unknown>;
  if (!isObj(api)) errors.push('api must be an object');
  else {
    if (typeof api.enabled !== 'boolean') errors.push('api.enabled must be true or false');
    for (const k of ['clockMs', 'symbolsMs', 'chainMs', 'positionsMs', 'ordersMs', 'tradesMs']) {
      if (typeof api[k] !== 'number' || !Number.isFinite(api[k] as number) || (api[k] as number) < 250) errors.push(`api.${k} must be a number >= 250 (ms)`);
    }
  }
  const feed = c.feed as unknown as Record<string, unknown>;
  if (!isObj(feed)) errors.push('feed must be an object');
  else {
    if (typeof feed.enabled !== 'boolean') errors.push('feed.enabled must be true or false');
    if (!Array.isArray(feed.channels) || !feed.channels.every((x) => typeof x === 'string')) errors.push('feed.channels must be a string array');
    if (typeof feed.path !== 'string' || !feed.path.startsWith('/')) errors.push('feed.path must start with /');
  }
  return { ok: errors.length === 0, config: c, errors };
}

/** First present field among candidate names (config field mapping). */
export function pick(o: unknown, names: string[]): unknown {
  if (!isObj(o)) return undefined;
  for (const n of names) if (o[n] !== undefined && o[n] !== null) return o[n];
  return undefined;
}

export function pickNum(o: unknown, names: string[]): number | null {
  const v = pick(o, names);
  const n = typeof v === 'string' ? Number(v) : v;
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

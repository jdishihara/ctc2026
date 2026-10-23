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

#!/usr/bin/env node
// Local mock of the CTC exchange for the Derivatives case: REST + WebSocket + a page that mimics the real layout.
// Usage: node mock-exchange/server.mjs [--port 5317] [--rate 52] [--fast 4] [--scenario file] [--seed 1]
//        [--start-event N] [--preroll 8] [--no-underlying-quotes] [--t-mode decay|fixed] [--glitch] [--quiet]
import http from 'node:http';
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSocketServer } from 'ws';

const here = dirname(fileURLToPath(import.meta.url));

// ---------- args ----------
const argv = process.argv.slice(2);
const arg = (name, def) => {
  const i = argv.indexOf('--' + name);
  if (i < 0) return def;
  const v = argv[i + 1];
  return v === undefined || v.startsWith('--') ? true : v;
};
const PORT = Number(arg('port', 5317));
const FAST = arg('fast', false) === true ? 4 : Number(arg('fast', 1)) || 1;
const RATE_OVERRIDE = arg('rate', null) == null ? null : Number(arg('rate'));
const SCENARIO_PATH = arg('scenario', join(here, 'scenario.default.json'));
const SEED = Number(arg('seed', 1));
const START_EVENT = Number(arg('start-event', 1));
const PREROLL = Number(arg('preroll', 8));
const UNDERLYING_QUOTES = !argv.includes('--no-underlying-quotes');
const T_MODE = arg('t-mode', 'decay');
const QUIET = argv.includes('--quiet');
// --glitch: quote OIL's top-strike call above the middle-strike call's ask (a riskless monotonicity arb) to practice the Arb tab
const GLITCH = argv.includes('--glitch');
const log = (...a) => { if (!QUIET) console.log('[mock]', ...a); };

const scenario = JSON.parse(readFileSync(SCENARIO_PATH, 'utf8'));

// ---------- deterministic RNG ----------
let rngState = SEED >>> 0 || 1;
const rand = () => {
  rngState ^= rngState << 13; rngState >>>= 0;
  rngState ^= rngState >>> 17;
  rngState ^= rngState << 5; rngState >>>= 0;
  return rngState / 4294967296;
};
const randInt = (a, b) => a + Math.floor(rand() * (b - a + 1));

// ---------- naive time ----------
const parseNaive = (s) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(s);
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) / 1000;
};
const hms = (s) => { const [h, m, x] = s.split(':').map(Number); return h * 3600 + m * 60 + (x || 0); };
const pad = (n) => String(Math.floor(n)).padStart(2, '0');
const fmtNaive = (sec) => {
  const d = new Date(Math.floor(sec) * 1000);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
};
const wallNaive = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, '0')}000`;
};

// ---------- Black-Scholes (r = 0) ----------
function ncdf(x) {
  const a = Math.abs(x);
  if (a > 37) return x > 0 ? 1 : 0;
  const e = Math.exp(-a * a / 2);
  let c;
  if (a < 7.07106781186547) {
    let b = 3.52624965998911e-2 * a + 0.700383064443688;
    b = b * a + 6.37396220353165; b = b * a + 33.912866078383; b = b * a + 112.079291497871; b = b * a + 221.213596169931; b = b * a + 220.206867912376;
    c = e * b;
    b = 8.83883476483184e-2 * a + 1.75566716318264;
    b = b * a + 16.064177579207; b = b * a + 86.7807322029461; b = b * a + 296.564248779674; b = b * a + 637.333633378831; b = b * a + 793.826512519948; b = b * a + 440.413735824752;
    c = c / b;
  } else {
    let b = a + 0.65; b = a + 4 / b; b = a + 3 / b; b = a + 2 / b; b = a + 1 / b;
    c = e / b / 2.506628274631;
  }
  return x > 0 ? 1 - c : c;
}
function bs(kind, S, K, v, T) {
  if (!(T > 0) || !(v > 0)) return Math.max(kind === 'C' ? S - K : K - S, 0);
  const sd = v * Math.sqrt(T);
  const d1 = (Math.log(S / K) + 0.5 * sd * sd) / sd;
  const d2 = d1 - sd;
  return kind === 'C' ? S * ncdf(d1) - K * ncdf(d2) : K * ncdf(-d2) - S * ncdf(-d1);
}

// ---------- schedule / clock ----------
const events = scenario.events;
const days = [...new Set(events.map((e) => e.date))].sort();
const roundOfDay = (date) => events.find((e) => e.date === date)?.round ?? 1;
const rateOfDay = (date) => (RATE_OVERRIDE ?? scenario.rates[String(roundOfDay(date))] ?? 52) * FAST;
const OPEN = hms('09:30:00');
const CLOSE = hms('16:00:00');
const EXPIRY = parseNaive(scenario.expiry);

const clock = {
  dayIdx: 0,
  fictional: 0, // naive seconds
  state: 'running',
  pausedUntil: 0,
  elapsedActive: 0,
};
{
  const ev = events.find((e) => e.n === START_EVENT) ?? events[0];
  clock.dayIdx = days.indexOf(ev.date);
  const evNews = parseNaive(`${ev.date}T${ev.news}`);
  clock.fictional = evNews - PREROLL * rateOfDay(ev.date);
}
const currentDate = () => days[clock.dayIdx];
const currentRate = () => rateOfDay(currentDate());

// ---------- market state ----------
const U = scenario.underlyings;
const und = {};
for (const [name, u] of Object.entries(U)) und[name] = { spot: u.spot, vol: u.vol, mmSpot: u.spot, mmVol: u.vol, strikes: u.strikes, pending: null };
// Apply the effects of events before the start event so a late start is consistent.
for (const e of events) {
  if (e.n >= START_EVENT) break;
  for (const [n, v] of Object.entries(e.new)) Object.assign(und[n], { spot: v.spot, vol: v.vol, mmSpot: v.spot, mmVol: v.vol });
}
const mmdd = scenario.expiry.slice(5, 7) + scenario.expiry.slice(8, 10);
const options = [];
for (const [name, u] of Object.entries(und)) {
  for (const K of u.strikes) for (const kind of ['C', 'P']) options.push({ symbol: `${name}_${mmdd}_${kind}${K}`, und: name, kind, K });
}
const optBySym = Object.fromEntries(options.map((o) => [o.symbol, o]));
// the underlyings are "scheduled" symbols on the live exchange: their price path is served by /symbols/{u}/scheduled-prices
const spotHistory = Object.fromEntries(Object.keys(und).map((u) => [u, []]));
const RISK_FREE_RATE = Number(scenario.risk_free_rate ?? 0);
for (const u of Object.keys(und)) spotHistory[u].push({ fictional_time: fmtNaive(clock.fictional), price: und[u].spot });
const allSymbols = [...Object.keys(und), ...options.map((o) => o.symbol)];

const tradingDaysLeft = (sec) => {
  if (T_MODE === 'fixed') return 20;
  if (sec >= EXPIRY) return 0;
  const dayStart = Math.floor(sec / 86400) * 86400;
  let d = 0;
  const wd = (s) => { const w = new Date(s * 1000).getUTCDay(); return w >= 1 && w <= 5; };
  if (wd(dayStart)) d += (CLOSE - Math.min(Math.max(sec - dayStart, OPEN), CLOSE)) / (CLOSE - OPEN);
  for (let s = dayStart + 86400; s <= Math.floor(EXPIRY / 86400) * 86400; s += 86400) if (wd(s)) d += 1;
  return d;
};
const Tyears = () => tradingDaysLeft(clock.fictional) / 252;

const mm = scenario.mm;
const books = {}; // symbol -> { bids: [[p,s]], asks: [[p,s]] }
const round2 = (x) => Math.round(x * 100) / 100;
function requote(sym) {
  let fair, hs;
  if (und[sym]) {
    fair = und[sym].spot;
    hs = 0.01;
  } else {
    const o = optBySym[sym];
    const u = und[o.und];
    fair = bs(o.kind, u.mmSpot, o.K, u.mmVol, Tyears());
    hs = mm.halfSpread + mm.halfSpreadPct * fair;
    fair += (rand() - 0.5) * 2 * mm.noise;
  }
  const bids = [];
  const asks = [];
  for (let i = 0; i < mm.levels; i++) {
    const b = round2(fair - hs - i * 0.05);
    const a = round2(fair + hs + i * 0.05);
    if (b >= 0.01) bids.push([b, randInt(mm.sizeMin, mm.sizeMax)]);
    asks.push([Math.max(a, 0.01 * (i + 1)), randInt(mm.sizeMin, mm.sizeMax)]);
  }
  books[sym] = { bids, asks };
  if (GLITCH && !und[sym]) {
    const o = optBySym[sym];
    const ks = und[o.und].strikes;
    if (o.und === 'OIL' && o.kind === 'C' && o.K === ks[ks.length - 1] && books[`OIL_${mmdd}_C${ks[1]}`]) {
      const ref = books[`OIL_${mmdd}_C${ks[1]}`].asks[0][0];
      books[sym] = { bids: [[round2(ref + 0.5), 20]], asks: [[round2(ref + 0.6), 20]] };
    }
  }
}
allSymbols.forEach(requote);

// ---------- accounts ----------
const positions = {}; // sym -> { qty, cost (signed), realized }
const orders = new Map(); // id -> order
const userTrades = [];
const marketTrades = {}; // sym -> []
let orderSeq = 0;
const stats = { orderPosts: 0, orderDeletes: 0, chainGets: 0, wsSubscribeFrames: 0, wsExtraFrames: 0 };
const posOf = (s) => (positions[s] ??= { qty: 0, cost: 0, realized: 0 });
const LIMIT = 300;

function applyFill(sym, side, qty, price) {
  const p = posOf(sym);
  const signed = side === 'buy' ? qty : -qty;
  // realized PnL on the closing part (average cost)
  if (p.qty !== 0 && Math.sign(p.qty) !== Math.sign(signed)) {
    const closing = Math.min(Math.abs(signed), Math.abs(p.qty));
    const avg = p.cost / p.qty;
    p.realized += (price - avg) * closing * Math.sign(p.qty);
    p.cost -= avg * closing * Math.sign(p.qty);
    p.qty += Math.sign(signed) * closing;
    const rest = Math.abs(signed) - closing;
    if (rest > 0) { p.qty += Math.sign(signed) * rest; p.cost += price * rest * Math.sign(signed); }
  } else {
    p.qty += signed;
    p.cost += price * signed;
  }
  if (p.qty === 0) p.cost = 0;
  const tr = { trade_id: `mt-${Date.now()}-${randInt(0, 1e9)}`, symbol: sym, side, price, quantity: qty, timestamp: wallNaive(), t_us: Date.now() * 1000 };
  userTrades.push(tr);
  (marketTrades[sym] ??= []).push(tr);
  broadcast({ type: 'trade', symbol: sym, price, quantity: qty, timestamp: tr.timestamp, trade_id: tr.trade_id }, 'trades', sym);
}

function restingSame(sym, side) {
  let n = 0;
  for (const o of orders.values()) if (o.symbol === sym && o.side === side && o.status === 'open') n += o.quantity - o.filled_quantity;
  return n;
}

function matchOrder(o) {
  const book = books[o.symbol];
  const levels = o.side === 'buy' ? book.asks : book.bids;
  for (const lvl of levels) {
    if (o.filled_quantity >= o.quantity) break;
    const [px, sz] = lvl;
    if (sz <= 0) continue;
    if (o.type === 'limit' && (o.side === 'buy' ? px > o.price + 1e-9 : px < o.price - 1e-9)) break;
    const q = Math.min(sz, o.quantity - o.filled_quantity);
    lvl[1] -= q;
    o.filled_quantity += q;
    applyFill(o.symbol, o.side, q, px);
  }
  if (o.filled_quantity >= o.quantity) o.status = 'filled';
  else if (o.type === 'market') o.status = o.filled_quantity > 0 ? 'partially_filled_cancelled' : 'cancelled';
}

function placeOrder(body) {
  const symbol = String(body.symbol ?? '');
  const side = String(body.side ?? '').toLowerCase();
  const type = String(body.type ?? body.order_type ?? 'limit').toLowerCase();
  const quantity = Math.floor(Number(body.quantity ?? body.qty));
  const price = body.price == null ? null : Number(body.price);
  if (!optBySym[symbol]) return [400, { detail: `unknown or non-tradable symbol ${symbol}` }];
  if (!['buy', 'sell'].includes(side)) return [400, { detail: 'side must be buy or sell' }];
  if (!(quantity > 0)) return [400, { detail: 'quantity must be positive' }];
  if (type === 'limit' && !(price > 0)) return [400, { detail: 'limit orders need a price' }];
  if (clock.state !== 'running') return [409, { detail: 'market closed' }];
  const pos = posOf(symbol).qty;
  const after = side === 'buy' ? pos + restingSame(symbol, 'buy') + quantity : pos - restingSame(symbol, 'sell') - quantity;
  if (Math.abs(after) > LIMIT) return [400, { detail: `position limit ${LIMIT} exceeded` }];
  const o = { order_id: `o-${++orderSeq}`, symbol, side, type, quantity, price, filled_quantity: 0, status: 'open', created_at: wallNaive() };
  orders.set(o.order_id, o);
  matchOrder(o);
  return [200, view(o)];
}
// the live API's order shape (2026-10-24): order_type, filled_quantity, status pending | partial | filled | cancelled
const view = (o) => ({
  order_id: o.order_id, symbol: o.symbol, side: o.side, order_type: o.type, quantity: o.quantity, filled_quantity: o.filled_quantity, price: o.price,
  status: o.status === 'open' ? (o.filled_quantity > 0 ? 'partial' : 'pending') : o.status, created_at: o.created_at,
  remaining_quantity: o.quantity - o.filled_quantity,
});
function symbolsView() {
  return [
    ...Object.keys(und).map((s) => ({ symbol: s, name: s, symbol_type: 'scheduled', trading_halted: false, settlement_active: false, max_position: 0, competition_id: scenario.competition_id })),
    ...options.map((o) => ({
      symbol: o.symbol, name: `${o.und} ${o.K} ${o.kind === 'C' ? 'Call' : 'Put'}`, symbol_type: 'option', underlying_symbol: o.und, option_kind: o.kind === 'C' ? 'call' : 'put',
      strike_price: o.K, expiry_fictional_time: scenario.expiry, trading_halted: false, settlement_active: false, settlement_price: null, max_position: LIMIT, tick_size: 0.01,
      competition_id: scenario.competition_id,
    })),
  ];
}
function quoteView(o) {
  const b = books[o.symbol];
  return { symbol: o.symbol, bid: b.bids[0]?.[0] ?? null, ask: b.asks[0]?.[0] ?? null, bid_size: b.bids[0]?.[1] ?? null, ask_size: b.asks[0]?.[1] ?? null, last: marketTrades[o.symbol]?.at(-1)?.price ?? null, settled: false };
}
function chainView(u) {
  const rows = und[u].strikes.map((K) => ({ strike: K, call: quoteView(optBySym[`${u}_${mmdd}_C${K}`]), put: quoteView(optBySym[`${u}_${mmdd}_P${K}`]) }));
  return {
    underlying_symbol: u, current_underlying_price: round2(und[u].spot), risk_free_rate: RISK_FREE_RATE,
    expiries: [{ expiry_fictional_time: scenario.expiry, trading_days_to_expiry: Math.round(tradingDaysLeft(clock.fictional) * 1000) / 1000, rows }],
  };
}

function markOf(sym) {
  const b = books[sym];
  const bid = b.bids[0]?.[0];
  const ask = b.asks[0]?.[0];
  return bid != null && ask != null ? (bid + ask) / 2 : ask ?? bid ?? 0;
}
function positionsView(includeZero) {
  return options
    .map((o) => {
      const p = posOf(o.symbol);
      const mark = round2(markOf(o.symbol));
      const avg = p.qty ? p.cost / p.qty : 0;
      return {
        symbol: o.symbol, quantity: p.qty, avg_price: round2(avg), mark_price: mark,
        unrealized_pnl: round2((mark - avg) * p.qty), realized_pnl: round2(p.realized),
      };
    })
    .filter((p) => includeZero || p.quantity !== 0);
}
const totalPnl = () => positionsView(true).reduce((s, p) => s + p.unrealized_pnl + p.realized_pnl, 0);

// ---------- websocket ----------
const clients = new Set(); // { ws, symbols:Set, channels:Set, subscribed }
let newsSeq = 100;
function send(c, obj) {
  try { c.ws.send(JSON.stringify(obj)); } catch { /* ignore */ }
}
function broadcast(obj, channel, symbol) {
  for (const c of clients) {
    if (!c.subscribed || !c.channels.has(channel)) continue;
    if (symbol && !c.symbols.has(symbol)) continue;
    send(c, obj);
  }
}
function quoteFrame(sym) {
  const b = books[sym];
  return { type: 'quote', symbol: sym, bid: b.bids[0]?.[0] ?? null, ask: b.asks[0]?.[0] ?? null, bid_size: b.bids[0]?.[1] ?? 0, ask_size: b.asks[0]?.[1] ?? 0, timestamp: wallNaive() };
}
function publishQuote(sym) {
  if (und[sym] && !UNDERLYING_QUOTES) return;
  broadcast(quoteFrame(sym), 'quotes', sym);
  for (const c of clients) {
    if (c.subscribed && c.channels.has('orderbook') && c.symbols.has(sym)) send(c, { type: 'orderbook', symbol: sym, bids: books[sym].bids.map(([price, quantity]) => ({ price, quantity })), asks: books[sym].asks.map(([price, quantity]) => ({ price, quantity })), timestamp: wallNaive() });
  }
}
const newsLog = [];
function publishNews(message) {
  const m = { seq: ++newsSeq, time: fmtNaive(clock.fictional), ...message };
  newsLog.push(m);
  broadcast({ type: 'news', message: m }, 'news');
}

// ---------- event engine ----------
const fired = new Set();
function eventTimes(e) {
  return { news: parseNaive(`${e.date}T${e.news}`), move: parseNaive(`${e.date}T${e.move}`), snap: parseNaive(`${e.date}T${e.snap}`) };
}
const pendingRealTimers = [];
function onBoundary(e, which) {
  const key = `${e.n}:${which}`;
  if (fired.has(key)) return;
  fired.add(key);
  if (which === 'news') {
    log(`event ${e.n} news: ${e.headline}`);
    publishNews({ type: 'headline', round: e.round, event: e.n, headline: e.headline });
    if (e.analysts) {
      const at = Date.now() + 1500;
      for (const [a, vals] of Object.entries(e.analysts)) {
        const parts = Object.entries(vals).map(([u, v]) => (e.round === 3 ? `${u} variance ${v}` : `${u} vol ${(v * 100).toFixed(1)}%`));
        pendingRealTimers.push({ at: at + Number(a) * 300, fn: () => publishNews({ type: 'analyst', round: e.round, event: e.n, analyst: Number(a), headline: `Analyst ${a}: ${parts.join(', ')}` }) });
      }
    }
  } else if (which === 'move') {
    for (const [n, v] of Object.entries(e.new)) { und[n].spot = v.spot; spotHistory[n].push({ fictional_time: fmtNaive(clock.fictional), price: v.spot }); }
    log(`event ${e.n}: underlyings move`);
    Object.keys(und).forEach((s) => { requote(s); publishQuote(s); });
  } else if (which === 'snap') {
    for (const [n, v] of Object.entries(e.new)) Object.assign(und[n], { mmSpot: v.spot, mmVol: v.vol });
    log(`event ${e.n}: option makers snap`);
    options.forEach((o) => { requote(o.symbol); publishQuote(o.symbol); });
  }
}

let lastReal = Date.now();
let lastSnapshot = Date.now();
function tick() {
  const now = Date.now();
  const dt = (now - lastReal) / 1000;
  lastReal = now;
  for (let i = pendingRealTimers.length - 1; i >= 0; i--) if (pendingRealTimers[i].at <= now) { pendingRealTimers[i].fn(); pendingRealTimers.splice(i, 1); }
  if (clock.state === 'paused') {
    if (now >= clock.pausedUntil) {
      clock.dayIdx++;
      clock.fictional = parseNaive(`${currentDate()}T09:30:00`) - 2 * currentRate();
      clock.state = 'running';
      log(`day ${currentDate()} opens (rate ${currentRate()})`);
    }
    return;
  }
  if (clock.state !== 'running') return;
  clock.fictional += dt * currentRate();
  clock.elapsedActive += dt;
  const date = currentDate();
  for (const e of events.filter((x) => x.date === date)) {
    const t = eventTimes(e);
    for (const w of ['news', 'move', 'snap']) if (clock.fictional >= t[w]) onBoundary(e, w);
  }
  const dayClose = parseNaive(`${date}T16:00:00`);
  if (clock.fictional >= dayClose) {
    clock.fictional = dayClose;
    if (clock.dayIdx >= days.length - 1) {
      clock.state = 'ended';
      log('competition ended');
    } else {
      clock.state = 'paused';
      clock.pausedUntil = now + (scenario.breakRealSeconds ?? 15) * 1000;
      log(`day ${date} closed; break ${scenario.breakRealSeconds}s`);
    }
  }
  // market maker: requote a few symbols each tick
  for (const s of allSymbols) {
    if (rand() < 0.35) {
      requote(s);
      publishQuote(s);
    }
  }
  // resting orders that became marketable
  for (const o of orders.values()) if (o.status === 'open') matchOrder(o);
  // background tape
  if (rand() < 0.3) {
    const o = options[randInt(0, options.length - 1)];
    const b = books[o.symbol];
    const buy = rand() < 0.5;
    const px = buy ? b.asks[0]?.[0] : b.bids[0]?.[0];
    if (px) {
      const tr = { trade_id: `bt-${now}-${randInt(0, 1e9)}`, symbol: o.symbol, price: px, quantity: randInt(1, 15), timestamp: wallNaive() };
      (marketTrades[o.symbol] ??= []).push(tr);
      if (marketTrades[o.symbol].length > 500) marketTrades[o.symbol].shift();
      broadcast({ type: 'trade', ...tr }, 'trades', o.symbol);
    }
  }
  if (now - lastSnapshot > 30_000) {
    lastSnapshot = now;
    publishNews({ type: 'snapshot', prices: Object.fromEntries(Object.entries(und).map(([n, u]) => [n, u.spot])) });
  }
}
setInterval(tick, 200);

// ---------- http ----------
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json' };
function json(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'content-type': 'application/json', 'cache-control': 'no-store' });
  res.end(body);
}
function readBody(req) {
  return new Promise((resolve) => {
    let s = '';
    req.on('data', (c) => (s += c));
    req.on('end', () => resolve(s));
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const p = url.pathname;
  try {
    if (req.method === 'GET' && (p === '/' || p === '/trading')) {
      if (p === '/') { res.writeHead(302, { location: '/trading' }); return res.end(); }
      res.writeHead(200, { 'content-type': MIME['.html'], 'cache-control': 'no-store' });
      return res.end(readFileSync(join(here, 'public/index.html')));
    }
    if (req.method === 'GET' && /^\/[\w.-]+\.(js|css)$/.test(p)) {
      const f = join(here, 'public', p.slice(1));
      if (existsSync(f)) {
        res.writeHead(200, { 'content-type': MIME[extname(f)], 'cache-control': 'no-store' });
        return res.end(readFileSync(f));
      }
    }
    if (p === '/api/v1/competitions/current') {
      return json(res, 200, {
        competition_id: scenario.competition_id, name: scenario.name, state: clock.state,
        fictional_time: fmtNaive(clock.fictional), elapsed_active_seconds: Math.floor(clock.elapsedActive), clock_rate: currentRate(),
      });
    }
    if (p === '/api/v1/auth/login') return json(res, 401, { detail: 'Not authenticated' });
    if (p.startsWith('/api/v1/admin/')) return json(res, 403, { detail: 'Forbidden' });
    if (p === '/api/v1/symbols') return json(res, 200, { symbols: symbolsView(), groups: [] });
    const chainM = /^\/api\/v1\/options\/([^/]+)\/chain$/.exec(p);
    if (chainM) {
      const u = decodeURIComponent(chainM[1]);
      if (!und[u]) return json(res, 404, { detail: `unknown underlying ${u}` });
      stats.chainGets++;
      return json(res, 200, chainView(u));
    }
    const schedM = /^\/api\/v1\/symbols\/([^/]+)\/scheduled-prices$/.exec(p);
    if (schedM) {
      const u = decodeURIComponent(schedM[1]);
      if (!und[u]) return json(res, 404, { detail: `unknown symbol ${u}` });
      const since = url.searchParams.get('since');
      return json(res, 200, { symbol: u, fictional_time: fmtNaive(clock.fictional), points: spotHistory[u].filter((pt) => !since || pt.fictional_time > since) });
    }
    if (p === '/api/v1/positions') return json(res, 200, { positions: positionsView(url.searchParams.get('include_zero') === 'true') });
    if (p === '/api/v1/orders/open') {
      const sym = url.searchParams.get('symbol');
      return json(res, 200, { orders: [...orders.values()].filter((o) => o.status === 'open' && (!sym || o.symbol === sym)).map(view) });
    }
    if (p === '/api/v1/orders' && req.method === 'GET') {
      const sym = url.searchParams.get('symbol');
      const lim = Number(url.searchParams.get('limit') ?? 200);
      return json(res, 200, { orders: [...orders.values()].filter((o) => !sym || o.symbol === sym).slice(-lim).map(view) });
    }
    if (p === '/api/v1/trades/market') {
      const sym = url.searchParams.get('symbol');
      const lim = Number(url.searchParams.get('limit') ?? 300);
      return json(res, 200, { trades: (marketTrades[sym] ?? []).slice(-lim).reverse() });
    }
    if (p === '/api/v1/trades') {
      const sym = url.searchParams.get('symbol');
      const since = Number(url.searchParams.get('since') ?? 0);
      const lim = Number(url.searchParams.get('limit') ?? 500);
      const list = userTrades.filter((t) => (!sym || t.symbol === sym) && t.t_us > since).slice(-lim);
      return json(res, 200, { trades: list.map((t, i) => ({ ...t, seq: i + 1 })), cursor: list.length });
    }
    if (p === '/api/v1/pnl') return json(res, 200, { total_pnl: round2(totalPnl()) });
    if (p === '/api/v1/orders' && req.method === 'POST') {
      stats.orderPosts++;
      let body = {};
      try { body = JSON.parse(await readBody(req)); } catch { return json(res, 400, { detail: 'bad json' }); }
      const [code, out] = placeOrder(body);
      log(`ORDER ${code} ${JSON.stringify(body)}${code === 200 ? ` -> ${out.status} ${out.filled_quantity}/${out.quantity}` : ` ${out.detail}`}`);
      return json(res, code, code === 200 ? { ...out, message: `Order ${out.status}`, message_type: 'success' } : out);
    }
    if (p === '/api/v1/orders/all' && req.method === 'DELETE') {
      stats.orderDeletes++;
      const sym = url.searchParams.get('symbol');
      const undq = url.searchParams.get('underlying');
      let n = 0;
      for (const o of orders.values()) {
        if (o.status !== 'open') continue;
        if (sym && o.symbol !== sym) continue;
        if (undq && optBySym[o.symbol]?.und !== undq) continue;
        o.status = 'cancelled'; n++;
      }
      log(`CANCEL ALL${sym ? ` ${sym}` : ''}${undq ? ` ${undq}` : ''}: ${n}`);
      return json(res, 200, { message: n ? `Cancelled ${n} orders` : "No open orders", cancelled_count: n });
    }
    if (p.startsWith('/api/v1/orders/') && req.method === 'DELETE') {
      stats.orderDeletes++;
      const o = orders.get(p.split('/').pop());
      if (!o) return json(res, 404, { detail: 'not found' });
      if (o.status === 'open') o.status = 'cancelled';
      return json(res, 200, view(o));
    }
    // test/inspection helpers (not part of the real API)
    if (p === '/__mock/stats') return json(res, 200, { ...stats, clients: clients.size, state: clock.state, fictional_time: fmtNaive(clock.fictional), positions: positionsView(false) });
    if (p === '/__mock/news') return json(res, 200, newsLog);
    json(res, 404, { detail: 'not found' });
  } catch (e) {
    json(res, 500, { detail: String(e) });
  }
});

const wss = new WebSocketServer({ noServer: true });
server.on('upgrade', (req, socket, head) => {
  const p = new URL(req.url, 'http://x').pathname;
  if (p !== '/ws/v1/market-data') return socket.destroy();
  wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
});
wss.on('connection', (ws) => {
  const c = { ws, symbols: new Set(), channels: new Set(), subscribed: false };
  clients.add(c);
  ws.on('message', (data) => {
    if (c.subscribed) {
      stats.wsExtraFrames++; // the real server only honors the first subscription frame
      return;
    }
    let m;
    try { m = JSON.parse(String(data)); } catch { return; }
    if (m?.action !== 'subscribe') return;
    stats.wsSubscribeFrames++;
    c.subscribed = true;
    for (const s of m.symbols ?? []) c.symbols.add(s);
    for (const ch of m.channels ?? []) c.channels.add(ch);
    send(c, { type: 'subscription_ack', symbols: [...c.symbols], channels: [...c.channels], timestamp: wallNaive() });
    if (c.channels.has('quotes')) for (const s of c.symbols) if (books[s] && (!und[s] || UNDERLYING_QUOTES)) send(c, quoteFrame(s));
    if (c.channels.has('news')) for (const n of newsLog.slice(-5)) send(c, { type: 'news', message: n });
  });
  ws.on('close', () => clients.delete(c));
});

server.listen(PORT, () => {
  console.log(`[mock] Newtonia vs Euleria mock exchange on http://localhost:${PORT}/trading (rate x${FAST}, start event ${START_EVENT}, preroll ${PREROLL}s)`);
});

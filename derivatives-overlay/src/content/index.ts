// Isolated-world entry: listens to the MAIN-world hooks, reads DOM fallbacks, runs the store and mounts the UI.
import { ExchangeApi, OrderBody, PATHS } from '../core/api';
import { BRIDGE_TAG, isBridgeMessage } from '../core/bus';
import { OwnFeed } from '../core/feed';
import { ApiPoller } from '../core/poller';
import { cloneDefaults, Config, deepMerge, validateConfig } from '../core/config';
import { findChain, readFairT, readHeaderClock, readLatest, readPositions, readSpot } from '../core/dom-readers';
import { installHotkeys, HotkeyAction } from '../core/hotkeys';
import * as storage from '../core/storage';
import { compileSymbolRegex } from '../engine/chain';
import { Ticket } from '../engine/tickets';
import { defaultUi, Store, UiState } from '../state/store';
import { Autopilot } from '../ticket/autopilot';
import { apiSubmitRefusal } from '../ticket/guard';
import { prefillTicket, PrefillResult } from '../ticket/prefill';
import { findOrderPanel } from '../ticket/selectors';
import { findByExactText, isVisible, textOf } from '../core/dom-readers';
import { mountApp } from '../ui/App';
import { Controller, ticketText } from '../ui/controller';
import css from '../ui/styles.css';

export interface OverlayHandle {
  store: Store;
  host: HTMLElement;
  shadow: ShadowRoot;
  controller: Controller;
  readDom: () => void;
  autopilot: Autopilot;
  api: ExchangeApi;
  poller: ApiPoller;
  feed: OwnFeed;
  stop: () => void;
}

export interface StartOpts {
  /** skip the async storage load (tests) */
  config?: Config;
  tickMs?: number;
  /** auto-pilot step period */
  autoMs?: number;
  /** REST poller scheduling period (tests) */
  pollMs?: number;
  /** disable the REST poller / own feed (tests of the DOM-only path) */
  noApi?: boolean;
}

export async function startOverlay(win: Window & typeof globalThis = window, opts: StartOpts = {}): Promise<OverlayHandle> {
  const doc = win.document;
  let cfg: Config = opts.config ?? cloneDefaults();
  if (!opts.config) {
    const saved = await storage.load<unknown>('config', null);
    if (saved) {
      const v = validateConfig(saved);
      cfg = v.config;
    }
  }
  const store = new Store(cfg);
  store.persist = (k, v) => void storage.save(k, v);
  const savedUi = await storage.load<Partial<UiState> | null>('ui', null);
  if (savedUi) store.s.ui = { ...defaultUi(), ...savedUi, focusField: null };

  store.onCompetition = (id) => {
    void storage.load<{ history?: unknown[]; timeline?: Record<string, unknown> } | null>(`history:${id}`, null).then((h) => {
      if (h?.history && Array.isArray(h.history)) store.s.history = h.history as Store['s']['history'];
      if (h?.timeline) store.s.timeline = { ...(h.timeline as Store['s']['timeline']), ...store.s.timeline };
      store.changed(true);
    });
  };

  // ---- bridge ----
  const seen = new Set<number>();
  const onMessage = (ev: MessageEvent) => {
    if (!isBridgeMessage(ev, win)) return;
    const m = ev.data;
    if (m.kind === 'overlay-ready') return;
    if (typeof m.n === 'number') {
      if (seen.has(m.n)) return;
      seen.add(m.n);
      if (seen.size > 20000) seen.clear();
    }
    store.handleBridge(m.kind, m.payload ?? {});
  };
  win.addEventListener('message', onMessage);
  win.postMessage({ [BRIDGE_TAG]: 1, kind: 'overlay-ready', payload: {} }, '*');

  // ---- the exchange's own API through the session cookie ----
  const api = new ExchangeApi('', (input, init) => win.fetch(input, init));
  const poller = new ApiPoller({
    api, cfg: () => store.cfg.api, isDerivatives: () => store.d.mode === 'derivatives', underlyings: () => store.cfg.underlyings,
    sink: (kind, p) => {
      store.handleBridge(kind, p);
      const st = poller.status;
      const worst = Math.max(1, ...Object.values(st.endpoints).map((e) => e.backoff));
      const bad = Object.entries(st.endpoints).filter(([, e]) => e.status && (e.status >= 400 || e.status === 0)).map(([k, e]) => `${k} ${e.status}`);
      store.s.api = { polls: st.polls, errors: st.errors, lastOkAt: st.lastOkAt, backoff: worst, note: bad.join(', ') };
      if (kind === 'http' && /\/symbols(\?|$)/.test(String(p.url ?? ''))) adoptExchangeUnderlyings();
    },
  });
  /** The Derivatives chain is first seen live (the testnet shows the earlier case). If GET /symbols lists option underlyings
   *  that differ from Config, adopt the exchange's names so chain polling, the feed and the tickets work at once; the headline
   *  aliases keep the old patterns (positionally, when the counts match) plus the new names themselves. */
  function adoptExchangeUnderlyings() {
    const ex = store.s.exchange;
    const got = ex.underlyings.filter((u) => /^[A-Z0-9._-]+$/i.test(u));
    if (!got.length || got.length > 4) return;
    const have = [...store.cfg.underlyings].sort();
    if (got.length === have.length && got.every((u) => have.includes(u))) return;
    // only when the exchange really has options on them (an equity-only case lists no option underlyings)
    const hasOptions = Object.values(store.s.metas).some((m) => got.includes(m.underlying));
    if (!hasOptions) return;
    const oldAliases = store.cfg.headline.aliases;
    const oldKeys = store.cfg.underlyings;
    const aliases: Record<string, string[]> = {};
    got.forEach((u, i) => {
      const inherited = got.length === oldKeys.length ? oldAliases[oldKeys[i]] ?? [] : [];
      const self = `\\b${u.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`;
      aliases[u] = [...new Set([self, ...inherited])];
    });
    controller.patchConfig({ underlyings: got, focus: null, headline: { aliases } });
    store.toast(`exchange lists underlyings ${got.join(', ')}: Config adopted them (was ${oldKeys.join(', ')}); check headline aliases`, 'warn');
    store.capture.add({ t: Date.now(), key: 'meta:underlyings-adopted', dir: 'meta', raw: `${oldKeys.join(',')} -> ${got.join(',')}`, highlights: [] });
  }
  const feed = new OwnFeed({
    url: () => `${win.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${win.location.host}${store.cfg.feed.path}`,
    symbols: () => [...store.cfg.underlyings, ...Object.keys(store.s.metas)],
    cfg: () => store.cfg.feed,
    enabled: () => store.d.mode === 'derivatives',
    WS: win.WebSocket,
    sink: (kind, p) => {
      store.handleBridge(kind, p);
      const st = feed.status;
      store.s.feed = { open: st.open, frames: st.frames, lastAt: st.lastAt, reconnects: st.reconnects, symbols: st.symbols.length, url: st.url };
    },
  });
  if (!opts.noApi) {
    poller.start(opts.pollMs ?? 100);
    feed.start(1000);
  }

  // ---- UI ----
  const host = doc.createElement('div');
  host.setAttribute('data-deriv-overlay', '');
  const shadow = host.attachShadow({ mode: 'open' });
  const style = doc.createElement('style');
  style.textContent = typeof css === 'string' ? css : '';
  shadow.appendChild(style);
  const container = doc.createElement('div');
  shadow.appendChild(container);
  (doc.body ?? doc.documentElement).appendChild(host);
  const skip = (el: Element) => el === host;

  let uiSaveTimer: ReturnType<typeof setTimeout> | null = null;
  let busy = false;
  const prefill = (t: Ticket): Promise<PrefillResult> =>
    prefillTicket(t, {
      doc, hints: store.cfg.dom, symbolRe: compileSymbolRegex(store.cfg.symbolRegex), skip,
      visibleUnderlying: (strikes) => store.domChainUnderlying(strikes),
      strikeOf: (sym) => {
        const c = store.d.contracts[sym] ?? store.s.metas[sym];
        return c ? { strike: c.strike, kind: c.kind } : null;
      },
    });
  const controller: Controller = {
    store,
    loadNext(kind) {
      const t = store.pickNext(kind);
      if (t) this.loadTicket(t);
    },
    loadTicket(t: Ticket) {
      if (!store.cfg.prefillEnabled) {
        store.markLoaded(t, null, 'Prefill is off: copy the ticket and enter it yourself');
        return;
      }
      if (busy) return;
      busy = true;
      store.markLoaded(t, null, 'prefilling…');
      prefill(t)
        .then((r) => store.markLoaded(t, r.ok, r.message))
        .catch((e) => store.markLoaded(t, false, `prefill error: ${e}`))
        .finally(() => (busy = false));
    },
    setAutoSubmit(on: boolean) {
      this.patchConfig({ auto: { submit: on } });
      if (on) store.setAutoPaused(false);
    },
    toggleAutoPause() {
      store.setAutoPaused(!store.s.auto.paused);
      store.toast(store.s.auto.paused ? 'Auto-submit PAUSED (Alt+P resumes)' : 'Auto-submit resumed', store.s.auto.paused ? 'warn' : 'info');
    },
    sendTicket(t: Ticket) {
      const now = Date.now();
      const th = store.cfg.thresholds;
      const pos = (store.s.manualPositions ?? store.s.positions)[t.symbol] ?? 0;
      const resting = store.s.resting[t.symbol];
      const sameSide = t.side === 'BUY' ? resting?.buy ?? 0 : resting?.sell ?? 0;
      const after = t.side === 'BUY' ? pos + sameSide + t.qty : pos - sameSide - t.qty;
      const refusal = apiSubmitRefusal({
        armed: store.d.mode === 'derivatives', ticket: { symbol: t.symbol, side: t.side, qty: t.qty, price: t.price }, known: !!store.d.contracts[t.symbol],
        tick: store.d.tick, perTicketCap: th.perTicketCap, positionLimit: th.positionLimit, positionAfter: after,
        rateUsed: store.rate.count(now), rateCap: store.cfg.rate.limit, backoffLeftMs: Math.max(0, autopilot.backoffUntil - now),
      });
      if (refusal) {
        store.markLoaded(t, false, `send refused: ${refusal}`);
        return;
      }
      const body: OrderBody = { symbol: t.symbol, side: t.side === 'BUY' ? 'buy' : 'sell', order_type: 'limit', quantity: t.qty, price: t.price };
      store.handleBridge('http-req', { method: 'POST', url: PATHS.orders, body: JSON.stringify(body), json: body, t: now });
      store.logAutoSubmit({ ...t, source: t.source }, 'posted');
      store.markLoaded(t, true, `sent ${t.side} ${t.qty} ${t.symbol} @ ${t.price}`);
      void api.post(PATHS.orders, body).then((res) => {
        store.handleBridge('http', { method: 'POST', url: PATHS.orders, status: res.status, json: res.json, body: res.text, t: res.t });
        if (!res.ok) store.toast(`exchange rejected ${t.side} ${t.qty} ${t.symbol}: HTTP ${res.status} ${res.text.slice(0, 100)}`, 'error');
      });
    },
    downloadCapture() {
      const name = store.capture.download(store.s.caseName ?? 'unknown', doc);
      store.toast(`Saved ${name}`, 'info');
    },
    saveConfig(json: string) {
      const v = validateConfig(json);
      if (v.ok) {
        store.setConfig(v.config);
        void storage.save('config', v.config);
      }
      return v;
    },
    resetConfig() {
      const d = cloneDefaults();
      store.setConfig(d);
      void storage.remove('config');
    },
    patchConfig(patch) {
      const v = validateConfig(deepMerge(JSON.parse(JSON.stringify(store.cfg)), patch));
      if (!v.ok) {
        store.toast(v.errors.join('; '), 'error');
        return;
      }
      store.setConfig(v.config);
      void storage.save('config', v.config);
    },
    saveUi() {
      if (uiSaveTimer) clearTimeout(uiSaveTimer);
      uiSaveTimer = setTimeout(() => void storage.save('ui', { ...store.s.ui, focusField: null }), 300);
    },
    copy(text: string) {
      try {
        void win.navigator.clipboard?.writeText(text).then(() => store.toast('Copied', 'info'), () => fallbackCopy(doc, text));
      } catch {
        fallbackCopy(doc, text);
      }
    },
  };
  mountApp(controller, container);

  // ---- DOM fallbacks ----
  const readDom = () => {
    try {
      const hints = store.cfg.dom;
      const deriv = store.d.mode === 'derivatives';
      const r: Parameters<Store['handleDom']>[0] = { clockSec: readHeaderClock(doc.body ?? doc, hints, skip), latest: readLatest(doc.body ?? doc, hints, skip) };
      if (deriv) {
        r.spot = readSpot(doc.body ?? doc, hints, skip);
        r.T = readFairT(doc.body ?? doc, hints, skip);
        const ch = findChain(doc.body ?? doc, hints, skip);
        if (ch) {
          r.chain = ch.rows.flatMap((row) => (['C', 'P'] as const).map((k) => ({
            strike: row.strike, kind: k, bid: row[k].bid.value, ask: row[k].ask.value, bidSize: row[k].bidSize.value, askSize: row[k].askSize.value,
          })));
        }
        r.positions = readPositions(doc.body ?? doc, hints, compileSymbolRegex(store.cfg.symbolRegex), skip);
        const panel = findOrderPanel(doc, hints, compileSymbolRegex(store.cfg.symbolRegex), skip);
        store.s.panelProbe = panel
          ? { found: true, symbol: panel.symbol, qty: !!panel.qtyInput, price: !!panel.priceInput, buy: !!panel.buy, sell: !!panel.sell, limit: !!panel.limit, submit: panel.submit ? textOf(panel.submit) || '' : null, t: Date.now() }
          : { found: false, symbol: null, qty: false, price: false, buy: false, sell: false, limit: false, submit: null, t: Date.now() };
      }
      store.handleDom(r);
    } catch (e) {
      console.warn('[deriv-overlay] DOM read failed', e);
    }
  };
  let domTimer: ReturnType<typeof setTimeout> | null = null;
  const scheduleDom = () => {
    if (domTimer) return;
    domTimer = setTimeout(() => {
      domTimer = null;
      readDom();
    }, 300);
  };
  const MO = (win as unknown as { MutationObserver?: typeof MutationObserver }).MutationObserver;
  const mo = MO ? new MO((muts) => {
    if (muts.every((m) => host.contains(m.target as Node) || m.target === host)) return;
    scheduleDom();
  }) : null;
  mo?.observe(doc.body ?? doc.documentElement, { subtree: true, childList: true, characterData: true });
  const domInterval = setInterval(readDom, 1000);

  // ---- clock / phase tick ----
  const tickInterval = setInterval(() => {
    try {
      store.tick();
    } catch (e) {
      console.warn('[deriv-overlay] tick failed', e);
    }
  }, opts.tickMs ?? 200);

  // ---- auto-pilot (off unless Config auto.submit is on) ----
  const findTab = (u: string): Element | null => {
    const els = findByExactText(doc.body ?? doc, u, true, skip).filter(isVisible);
    for (const e of els) {
      const b = e.closest('button,[role=tab],[role=button],a');
      if (b && !b.closest('form') && (b.textContent ?? '').replace(/\s+/g, ' ').trim() === u) return b;
    }
    return null;
  };
  const autopilot = new Autopilot({ store, doc, prefill, symbolRe: () => compileSymbolRegex(store.cfg.symbolRegex), skip, findTab, api });
  const autoInterval = setInterval(() => {
    if (!store.cfg.prefillEnabled || !store.d.autoArmed || busy) return;
    busy = true;
    autopilot.step().finally(() => (busy = false));
  }, opts.autoMs ?? 700);

  // ---- hotkeys ----
  const focusField = (field: 'spot' | 'vol') => {
    const u = store.cfg.focus ?? store.s.ui.focusUnd ?? store.cfg.underlyings[0];
    store.s.ui.tab = 'Edge';
    store.s.ui.collapsed = false;
    store.s.ui.hidden = false;
    store.changed(true);
    setTimeout(() => {
      const el = shadow.querySelector<HTMLInputElement>(`[data-field="${field}-${u}"]`);
      el?.focus();
      el?.select();
    }, 260);
  };
  const onHotkey = (a: HotkeyAction) => {
    const ui = store.s.ui;
    // on other cases' pages only the overlay toggle, the Capture tab and Esc are live
    if (store.d.mode !== 'derivatives' && a !== 'toggle' && a !== 'capture' && a !== 'blur') return;
    switch (a) {
      case 'nextTicket': return controller.loadNext('edge');
      case 'nextFlatten': return controller.loadNext('flatten');
      case 'accept': return store.acceptSuggestions();
      case 'focusOIL':
      case 'focusPLANE': {
        const u = store.cfg.underlyings[a === 'focusOIL' ? 0 : 1];
        if (!u) return;
        ui.focusUnd = u;
        controller.patchConfig({ focus: store.cfg.focus === u ? null : u });
        return;
      }
      case 'toggle':
        ui.hidden = !ui.hidden;
        controller.saveUi();
        return store.changed(true);
      case 'focusSpot': return focusField('spot');
      case 'focusVol': return focusField('vol');
      case 'autoPause':
        if (!store.cfg.auto.submit) return store.toast('Auto-submit is off (arm it in the header or Config auto.submit)', 'info');
        return controller.toggleAutoPause();
      case 'capture':
        ui.tab = 'Capture';
        ui.hidden = false;
        ui.collapsed = false;
        ui.captureOpen = true;
        return store.changed(true);
      case 'blur': {
        (shadow.activeElement as HTMLElement | null)?.blur?.();
        return;
      }
    }
  };
  const removeHotkeys = installHotkeys(win, host, onHotkey);

  store.changed(true);
  readDom();

  return {
    store, host, shadow, controller, readDom, autopilot, api, poller, feed,
    stop() {
      win.removeEventListener('message', onMessage);
      poller.stop();
      feed.stop();
      clearInterval(domInterval);
      clearInterval(tickInterval);
      clearInterval(autoInterval);
      mo?.disconnect();
      removeHotkeys();
      host.remove();
    },
  };
}

function fallbackCopy(doc: Document, text: string) {
  try {
    const ta = doc.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    doc.body.appendChild(ta);
    ta.select();
    doc.execCommand('copy');
    ta.remove();
  } catch {
    /* ignore */
  }
}

// Auto-start in the extension (not under test runners).
const underTest = typeof process !== 'undefined' && !!process.env?.VITEST;
if (typeof window !== 'undefined' && window.top === window && !underTest) {
  startOverlay().catch((e) => console.warn('[deriv-overlay] failed to start', e));
}

export { ticketText };

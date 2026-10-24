// Mock exchange front end. Deliberately written like a typical SPA: it polls REST with fetch, opens one WebSocket,
// sends exactly one subscribe frame, and keeps "controlled" inputs (state is updated only from input events).
(function () {
  'use strict';
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    product: 'OIL',
    symbols: [],
    options: [], // {symbol, underlying, kind, strike}
    quotes: {},
    selected: null,
    side: 'BUY',
    type: 'Limit',
    qty: '50',
    price: '',
    positions: [],
    openOrders: [],
    clock: null,
    news: [],
    tape: [],
    spotHist: { OIL: [], PLANE: [] },
    leftTab: 'OIL',
  };
  window.__mockSubmitCount = 0;

  const fmt = (x, d = 2) => (x == null || !Number.isFinite(Number(x)) ? '—' : Number(x).toFixed(d));

  // ---------- Black-Scholes for the Fair / IV tabs ----------
  function ncdf(x) {
    const t = 1 / (1 + 0.2316419 * Math.abs(x));
    const d = 0.3989422804014327 * Math.exp(-x * x / 2);
    const p = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
    return x >= 0 ? 1 - p : p;
  }
  function bs(kind, S, K, v, T) {
    if (!(T > 0) || !(v > 0)) return { price: Math.max(kind === 'C' ? S - K : K - S, 0), delta: 0, gamma: 0, vega: 0, theta: 0 };
    const sd = v * Math.sqrt(T);
    const d1 = (Math.log(S / K) + 0.5 * sd * sd) / sd;
    const d2 = d1 - sd;
    const pdf = Math.exp(-d1 * d1 / 2) / Math.sqrt(2 * Math.PI);
    const price = kind === 'C' ? S * ncdf(d1) - K * ncdf(d2) : K * ncdf(-d2) - S * ncdf(-d1);
    return { price, delta: kind === 'C' ? ncdf(d1) : ncdf(d1) - 1, gamma: pdf / (S * sd), vega: S * pdf * Math.sqrt(T) / 100, theta: -S * pdf * v / (2 * Math.sqrt(T)) / 252 };
  }
  function tradingDays(fict) {
    // fict: "YYYY-MM-DDTHH:MM:SS" naive
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(fict || '');
    if (!m) return 20;
    const now = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) / 1000;
    const exp = Date.UTC(2026, 5, 26, 16, 0, 0) / 1000;
    if (now >= exp) return 0;
    const open = 9.5 * 3600, close = 16 * 3600;
    const day = Math.floor(now / 86400) * 86400;
    const wd = (s) => { const w = new Date(s * 1000).getUTCDay(); return w >= 1 && w <= 5; };
    let d = wd(day) ? (close - Math.min(Math.max(now - day, open), close)) / (close - open) : 0;
    for (let s = day + 86400; s <= Math.floor(exp / 86400) * 86400; s += 86400) if (wd(s)) d += 1;
    return d;
  }

  // ---------- networking (same calls as the real app) ----------
  async function getJson(path) {
    try {
      const r = await fetch(path, { credentials: 'include' });
      if (!r.ok) return null;
      return await r.json();
    } catch {
      return null;
    }
  }

  async function loadSymbols() {
    const raw = await getJson('/api/v1/symbols');
    const s = Array.isArray(raw) ? raw : raw && Array.isArray(raw.symbols) ? raw.symbols : null;
    if (!s) return;
    state.symbols = s.map((x) => x.symbol);
    state.options = s.filter((x) => x.symbol_type === 'option' || x.type === 'option').map((x) => ({ symbol: x.symbol, underlying: x.underlying_symbol ?? x.underlying, kind: (x.option_kind ?? x.option_type) === 'call' ? 'C' : 'P', strike: x.strike_price ?? x.strike }));
    if (!state.selected) state.selected = state.options.find((o) => o.underlying === state.product && o.kind === 'C')?.symbol ?? null;
    connectWs();
    render();
  }

  let ws = null;
  function connectWs() {
    try {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${location.host}/ws/v1/market-data`);
      ws.addEventListener('open', () => {
        ws.send(JSON.stringify({ action: 'subscribe', symbols: state.symbols, channels: ['news', 'quotes', 'trades'] }));
      });
      ws.addEventListener('message', (ev) => {
        let m;
        try { m = JSON.parse(ev.data); } catch { return; }
        onFrame(m);
      });
      ws.addEventListener('close', () => setTimeout(connectWs, 1500));
    } catch {
      /* ignore */
    }
  }

  function onFrame(m) {
    if (m.type === 'quote') {
      state.quotes[m.symbol] = m;
      if (m.symbol === 'OIL' || m.symbol === 'PLANE') {
        const h = state.spotHist[m.symbol];
        h.push((m.bid + m.ask) / 2);
        if (h.length > 300) h.shift();
      }
      scheduleRender();
    } else if (m.type === 'trade') {
      state.tape.unshift(m);
      if (state.tape.length > 50) state.tape.pop();
    } else if (m.type === 'news' && m.message && m.message.headline) {
      if (!state.news.some((n) => n.seq === m.message.seq)) state.news.unshift(m.message);
      scheduleRender();
    }
  }

  async function poll() {
    const c = await getJson('/api/v1/competitions/current');
    if (c) state.clock = c;
    const p = await getJson('/api/v1/positions?include_zero=true');
    const pl = Array.isArray(p) ? p : p && Array.isArray(p.positions) ? p.positions : null;
    if (pl) state.positions = pl;
    if (state.selected) {
      const o = await getJson(`/api/v1/orders/open?symbol=${encodeURIComponent(state.selected)}`);
      const ol = Array.isArray(o) ? o : o && Array.isArray(o.orders) ? o.orders : null;
      if (ol) state.openOrders = ol;
    }
    scheduleRender();
  }
  async function pollSlow() {
    if (state.selected) await getJson(`/api/v1/trades/market?symbol=${encodeURIComponent(state.selected)}&limit=300`);
    await getJson('/api/v1/auth/login'); // the real app probes these and gets 401/403
    await getJson('/api/v1/admin/config');
  }

  async function submitOrder() {
    window.__mockSubmitCount++;
    const sym = state.selected;
    const qty = Math.floor(Number(state.qty));
    const body = { symbol: sym, side: state.side.toLowerCase(), type: state.type.toLowerCase(), quantity: qty };
    if (state.type === 'Limit') body.price = Number(state.price);
    const msg = $('.msg');
    try {
      const r = await fetch('/api/v1/orders', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json();
      msg.textContent = r.ok ? `Order ${j.status}: ${j.filled_quantity}/${j.quantity} filled` : `Rejected: ${j.detail}`;
    } catch (e) {
      msg.textContent = 'Network error';
    }
    poll();
  }

  // ---------- rendering ----------
  let renderPending = false;
  function scheduleRender() {
    if (renderPending) return;
    renderPending = true;
    setTimeout(() => { renderPending = false; render(); }, 100);
  }

  function selectedMeta() {
    return state.options.find((o) => o.symbol === state.selected) || null;
  }

  function render() {
    // header
    const c = state.clock;
    if (c) {
      $('.time').textContent = (c.fictional_time || '').slice(11, 19);
      const open = c.state === 'running';
      $('.dot').classList.toggle('open', open);
      $('.openlbl').textContent = open ? 'OPEN' : 'CLOSED';
    }
    const pnl = state.positions.reduce((s, p) => s + (p.unrealized_pnl || 0) + (p.realized_pnl || 0), 0);
    $('.pnl').textContent = `$${fmt(pnl)}`;
    $$('.prod').forEach((b) => b.classList.toggle('active', b.textContent === state.product));
    $$('.ltab')[0].textContent = state.product;

    // latest bar
    const n = state.news[0];
    if (n) {
      $('.ltime').textContent = (n.time || '').slice(11, 19);
      $('.ltext').textContent = n.headline;
      $('.learlier').textContent = state.news.length > 1 ? `${state.news.length - 1} earlier` : '';
    }

    // spot
    const uq = state.quotes[state.product];
    $('.spot').textContent = uq ? fmt((uq.bid + uq.ask) / 2) : '—';

    // chain
    const strikes = [...new Set(state.options.filter((o) => o.underlying === state.product).map((o) => o.strike))].sort((a, b) => a - b);
    const tbody = $('.chain tbody');
    const rowsHtml = strikes.map((K) => {
      const cs = state.options.find((o) => o.underlying === state.product && o.strike === K && o.kind === 'C');
      const ps = state.options.find((o) => o.underlying === state.product && o.strike === K && o.kind === 'P');
      const cq = (cs && state.quotes[cs.symbol]) || {};
      const pq = (ps && state.quotes[ps.symbol]) || {};
      const cell = (sym, side, v) => {
        const sel = state.selected === sym && state.selCell === side ? ' sel' : '';
        return `<td class="px ${side === 'bid' ? 'bidc' : 'askc'}${sel}" data-sym="${sym}" data-side="${side}">${fmt(v)}</td>`;
      };
      return `<tr><td>${cq.bid_size ?? ''}</td>${cell(cs?.symbol, 'bid', cq.bid)}${cell(cs?.symbol, 'ask', cq.ask)}<td>${cq.ask_size ?? ''}</td>` +
        `<td class="strike">${K}</td>` +
        `<td>${pq.bid_size ?? ''}</td>${cell(ps?.symbol, 'bid', pq.bid)}${cell(ps?.symbol, 'ask', pq.ask)}<td>${pq.ask_size ?? ''}</td></tr>`;
    }).join('');
    if (tbody.__html !== rowsHtml) {
      tbody.innerHTML = rowsHtml;
      tbody.__html = rowsHtml;
    }

    // book
    const sm = selectedMeta();
    if (sm) {
      const q = state.quotes[sm.symbol] || {};
      $('.booktitle').textContent = `${sm.symbol} book`;
      $('.bookba').textContent = `Bid ${fmt(q.bid)} · Ask ${fmt(q.ask)}`;
      const mine = (px, side) => state.openOrders.filter((o) => o.side === side && Math.abs(o.price - px) < 1e-9).reduce((s, o) => s + o.remaining_quantity, 0) || '';
      $('.book tbody').innerHTML =
        `<tr><td class="askc">${fmt(q.ask)}</td><td>${q.ask_size ?? ''}</td><td>${q.ask_size ?? ''}</td><td>${q.ask != null ? mine(q.ask, 'sell') : ''}</td></tr>` +
        `<tr><td colspan="2">SPREAD</td><td colspan="2">${q.bid != null && q.ask != null ? fmt(q.ask - q.bid) : '—'}</td></tr>` +
        `<tr><td colspan="2">MID</td><td colspan="2">${q.bid != null && q.ask != null ? fmt((q.ask + q.bid) / 2, 3) : '—'}</td></tr>` +
        `<tr><td class="bidc">${fmt(q.bid)}</td><td>${q.bid_size ?? ''}</td><td>${q.bid_size ?? ''}</td><td>${q.bid != null ? mine(q.bid, 'buy') : ''}</td></tr>`;
      $('.osym').textContent = sm.symbol;
      $('.odesc').textContent = `${sm.kind === 'C' ? 'CALL' : 'PUT'} $ ${fmt(sm.strike)} EXP JUN 26, 2026 16:00:00`;
    }

    // order form (controlled)
    $$('.sidebtn').forEach((b) => b.classList.toggle('active', b.textContent === state.side));
    $$('.typebtn').forEach((b) => b.classList.toggle('active', b.textContent === state.type));
    const qtyIn = $('.qty');
    if (qtyIn.value !== state.qty && document.activeElement !== qtyIn) qtyIn.value = state.qty;
    const pxIn = $('.price');
    if (pxIn.value !== state.price && document.activeElement !== pxIn) pxIn.value = state.price;
    pxIn.disabled = state.type === 'Market';
    const sub = $('.submit');
    sub.textContent = `${state.side === 'BUY' ? 'Buy' : 'Sell'} ${state.qty || 0} ${state.selected || ''}`;
    sub.className = `submit ${state.side === 'BUY' ? 'buy' : 'sell'}`;
    $('.notval').textContent = `$${fmt(Number(state.qty || 0) * Number(state.price || 0))}`;

    // lists
    $('.openorders').innerHTML = state.openOrders.map((o) => `<div class="item"><span>${o.symbol}</span><span>${o.side.toUpperCase()} ${o.remaining_quantity} @ ${fmt(o.price)}</span><button type="button" class="cancel" data-id="${o.order_id}">Cancel</button></div>`).join('') || '<div class="item"><span>No open orders</span></div>';
    $('.positions').innerHTML = state.positions.filter((p) => p.quantity !== 0).map((p) => `<div class="item"><span>${p.symbol}</span><span>${p.quantity > 0 ? '+' : ''}${p.quantity}</span><span>@ ${fmt(p.avg_price)}</span><span>uPnL ${fmt(p.unrealized_pnl)}</span></div>`).join('') || '<div class="item"><span>No positions</span></div>';

    // fair tab
    if (c) {
      const days = tradingDays(c.fictional_time);
      $('.ft').textContent = `${(days / 252).toFixed(4)} yr (${days.toFixed(2)} trading days)`;
      $('.fnow').textContent = c.fictional_time.replace('T', ' ');
      $('.fcount').textContent = `${days.toFixed(2)}d`;
      const S = Number($('.fspot').value), v = Number($('.fvol').value) / 100;
      const K = sm ? sm.strike : 100;
      const g = bs(sm ? sm.kind : 'C', S, K, v, days / 252);
      $('.fout').innerHTML = `<div class="row"><span>Fair</span><b>${fmt(g.price, 4)}</b></div><div class="row"><span>Delta</span><span>${fmt(g.delta, 4)}</span></div><div class="row"><span>Gamma</span><span>${fmt(g.gamma, 4)}</span></div><div class="row"><span>Vega/1pt</span><span>${fmt(g.vega, 4)}</span></div><div class="row"><span>Theta/day</span><span>${fmt(g.theta, 4)}</span></div>`;
    }
    // tape
    $('.tape').innerHTML = state.tape.slice(0, 20).map((t) => `<div class="item"><span>${t.symbol}</span><span>${fmt(t.price)}</span><span>${t.quantity}</span></div>`).join('');
    // chart
    const cv = $('canvas');
    const ctx = cv && cv.getContext ? (() => { try { return cv.getContext('2d'); } catch { return null; } })() : null;
    if (ctx) {
      const h = state.spotHist[state.product];
      ctx.clearRect(0, 0, cv.width, cv.height);
      if (h.length > 1) {
        const lo = Math.min(...h), hi = Math.max(...h), span = hi - lo || 1;
        ctx.strokeStyle = '#e8707a';
        ctx.beginPath();
        h.forEach((y, i) => { const X = (i / (h.length - 1)) * cv.width; const Y = cv.height - ((y - lo) / span) * (cv.height - 10) - 5; i ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); });
        ctx.stroke();
      }
    }
  }

  // ---------- events ----------
  document.addEventListener('click', (ev) => {
    const t = ev.target instanceof Element ? ev.target : null;
    if (!t) return;
    const px = t.closest('td.px');
    if (px && px.dataset.sym && px.dataset.sym !== 'undefined') {
      state.selected = px.dataset.sym;
      state.selCell = px.dataset.side;
      state.side = px.dataset.side === 'ask' ? 'BUY' : 'SELL';
      const q = state.quotes[state.selected] || {};
      const v = px.dataset.side === 'ask' ? q.ask : q.bid;
      if (v != null) state.price = String(v);
      render();
      return;
    }
    if (t.matches('.prod')) { state.product = t.textContent; state.selected = state.options.find((o) => o.underlying === state.product && o.kind === 'C')?.symbol ?? null; render(); return; }
    if (t.matches('.sidebtn')) { state.side = t.textContent; render(); return; }
    if (t.matches('.typebtn')) { state.type = t.textContent; render(); return; }
    if (t.matches('.qbtn')) { state.qty = t.textContent; render(); return; }
    if (t.matches('.ltab')) {
      const i = $$('.ltab').indexOf(t);
      $$('.ltab').forEach((b, j) => b.classList.toggle('active', i === j));
      $('.chartbody').classList.toggle('hidden', i !== 0);
      $('.fairbody').classList.toggle('hidden', i !== 1);
      $('.ivbody').classList.toggle('hidden', i !== 2);
      return;
    }
    if (t.matches('.ctab')) {
      const i = $$('.ctab').indexOf(t);
      $$('.ctab').forEach((b, j) => b.classList.toggle('active', i === j));
      $('.chain').classList.toggle('hidden', i !== 0);
      $('.tape').classList.toggle('hidden', i !== 1);
      return;
    }
    if (t.matches('.cancel')) {
      fetch(`/api/v1/orders/${t.dataset.id}`, { method: 'DELETE' }).then(poll, poll);
    }
  });
  $('.qty').addEventListener('input', (e) => { state.qty = e.target.value.replace(/[^0-9]/g, ''); render(); });
  $('.price').addEventListener('input', (e) => { state.price = e.target.value; render(); });
  $('.orderform').addEventListener('submit', (e) => {
    e.preventDefault();
    submitOrder();
  });

  loadSymbols();
  poll();
  setInterval(poll, 1000);
  setInterval(pollSlow, 2500);
})();

// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { installHooks } from '../../src/main-world/hooks';

function collect() {
  const msgs: { kind: string; payload: Record<string, unknown>; n: number }[] = [];
  window.addEventListener('message', (e) => {
    if (e.data?.__derivOverlay === 1 && e.data.kind !== 'overlay-ready') msgs.push(e.data);
  });
  return msgs;
}
const flush = () => new Promise((r) => setTimeout(r, 20));

class FakeWS extends EventTarget {
  static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
  static instances: FakeWS[] = [];
  sent: unknown[] = [];
  constructor(public url: string, public protocols?: string | string[]) {
    super();
    FakeWS.instances.push(this);
  }
  send(d: unknown) { this.sent.push(d); }
  emit(data: unknown) { this.dispatchEvent(Object.assign(new Event('message'), { data })); }
}

describe('main-world hooks', () => {
  const pageFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const u = String(input instanceof Request ? input.url : input);
    void init;
    return new Response(JSON.stringify({ ok: true, u }), { status: 200, headers: { 'content-type': 'application/json' } });
  });
  (window as unknown as { WebSocket: unknown }).WebSocket = FakeWS;
  window.fetch = pageFetch as unknown as typeof fetch;
  const msgs = collect();
  installHooks(window as Window & typeof globalThis);
  installHooks(window as Window & typeof globalThis); // double install is a no-op

  it('wraps WebSocket transparently and reports frames both ways', async () => {
    const ws = new window.WebSocket('wss://cornelltradingcompetition.org/ws/v1/market-data');
    expect(ws).toBeInstanceOf(FakeWS);
    expect(ws instanceof window.WebSocket).toBe(true);
    expect(window.WebSocket.OPEN).toBe(1);
    ws.send('{"action":"subscribe","symbols":["OIL"],"channels":["quotes"]}');
    expect((ws as unknown as FakeWS).sent).toHaveLength(1); // passes through, exactly once
    (ws as unknown as FakeWS).emit('{"type":"quote","symbol":"OIL","bid":1,"ask":2}');
    (ws as unknown as FakeWS).emit(new ArrayBuffer(8));
    await flush();
    const out = msgs.find((m) => m.kind === 'ws-out');
    expect(out?.payload.json).toMatchObject({ action: 'subscribe' });
    const ins = msgs.filter((m) => m.kind === 'ws-in');
    expect(ins[0].payload.json).toMatchObject({ type: 'quote' });
    expect(ins[1].payload.data).toEqual({ binary: true, size: 8 });
  });
  it('observes fetch without changing the response, skips auth/admin, reports request bodies', async () => {
    const r = await window.fetch('/api/v1/positions?include_zero=true');
    expect(await r.json()).toMatchObject({ ok: true });
    await window.fetch('/api/v1/auth/login');
    await window.fetch('/api/v1/admin/config');
    await window.fetch('/api/v1/orders', { method: 'POST', body: '{"symbol":"OIL_0626_C100"}' });
    await window.fetch(new Request('http://localhost/api/v1/orders/all', { method: 'DELETE' }));
    await flush();
    const http = msgs.filter((m) => m.kind === 'http').map((m) => String(m.payload.url));
    expect(http.some((u) => u.includes('/api/v1/positions'))).toBe(true);
    expect(http.some((u) => u.includes('/auth/') || u.includes('/admin/'))).toBe(false);
    const reqs = msgs.filter((m) => m.kind === 'http-req');
    expect(reqs.map((m) => m.payload.method)).toEqual(['POST', 'DELETE']);
    expect(reqs[0].payload.json).toEqual({ symbol: 'OIL_0626_C100' });
    expect(pageFetch).toHaveBeenCalledTimes(5); // never an extra call of our own
  });
  it('a throwing observer never breaks the page', async () => {
    const orig = window.postMessage;
    window.postMessage = () => { throw new Error('boom'); };
    try {
      const r = await window.fetch('/api/v1/symbols');
      expect(r.status).toBe(200);
      const ws = new window.WebSocket('wss://x/ws');
      expect(() => ws.send('x')).not.toThrow();
    } finally {
      window.postMessage = orig;
    }
  });
  it('buffers messages until the overlay is ready, then replays them with sequence numbers', async () => {
    window.postMessage({ __derivOverlay: 1, kind: 'overlay-ready', payload: {} }, '*');
    await flush();
    const replayed = msgs.filter((m) => typeof m.n === 'number');
    const ns = replayed.map((m) => m.n);
    expect(new Set(ns).size).toBeLessThan(ns.length); // live copies + replayed copies share n
  });
});

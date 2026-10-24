// Polls the exchange's REST API through the session cookie and hands every response to the store as if the page had
// fetched it (same bridge kind, same capture keys). Per-endpoint cadence from Config.api; 429/network errors back off
// that endpoint (x2 up to x16) and a 200 resets it.
import { ApiResponse, ExchangeApi, PATHS } from './api';

export interface ApiConfig {
  enabled: boolean;
  clockMs: number;
  symbolsMs: number;
  chainMs: number;
  positionsMs: number;
  ordersMs: number;
  tradesMs: number;
}

export interface EndpointStatus {
  lastAt: number;
  lastOkAt: number;
  status: number;
  backoff: number;
  inflight: boolean;
}

export interface PollerStatus {
  polls: number;
  errors: number;
  lastOkAt: number;
  endpoints: Record<string, EndpointStatus>;
}

export type Sink = (kind: 'http' | 'http-req', p: { url: string; method: string; status?: number; json?: unknown; body?: string | null; t: number }) => void;

export interface PollerDeps {
  api: ExchangeApi;
  sink: Sink;
  cfg: () => ApiConfig;
  /** chain/positions/orders/trades are polled only on the derivatives page */
  isDerivatives: () => boolean;
  underlyings: () => string[];
  now?: () => number;
}

export class ApiPoller {
  readonly status: PollerStatus = { polls: 0, errors: 0, lastOkAt: 0, endpoints: {} };
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private deps: PollerDeps) {}

  private now(): number {
    return this.deps.now ? this.deps.now() : Date.now();
  }

  start(periodMs = 100): void {
    if (this.timer) return;
    this.timer = setInterval(() => void this.tick(), periodMs);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private ep(key: string): EndpointStatus {
    return (this.status.endpoints[key] ??= { lastAt: 0, lastOkAt: 0, status: 0, backoff: 1, inflight: false });
  }

  private due(key: string, everyMs: number, now: number): boolean {
    const e = this.ep(key);
    return !e.inflight && now - e.lastAt >= everyMs * e.backoff;
  }

  /** One scheduling pass; safe to call directly (tests). */
  async tick(): Promise<void> {
    const cfg = this.deps.cfg();
    if (!cfg.enabled) return;
    const now = this.now();
    const jobs: Promise<void>[] = [];
    const deriv = this.deps.isDerivatives();
    // on another case's page (Hurricane, Mario) stay quiet: the clock every 5 s and the symbols list only, to notice a case change
    if (this.due('clock', deriv ? cfg.clockMs : Math.max(cfg.clockMs, 5000), now)) jobs.push(this.fetch('clock', PATHS.clock, now));
    if (this.due('symbols', cfg.symbolsMs, now)) jobs.push(this.fetch('symbols', PATHS.symbols, now));
    if (deriv) {
      for (const u of this.deps.underlyings()) if (this.due(`chain:${u}`, cfg.chainMs, now)) jobs.push(this.fetch(`chain:${u}`, PATHS.chain(u), now));
      if (this.due('positions', cfg.positionsMs, now)) jobs.push(this.fetch('positions', PATHS.positions, now));
      if (this.due('orders', cfg.ordersMs, now)) jobs.push(this.fetch('orders', PATHS.openOrders, now));
      if (this.due('trades', cfg.tradesMs, now)) jobs.push(this.fetch('trades', PATHS.trades(200), now));
    }
    await Promise.all(jobs);
  }

  private async fetch(key: string, path: string, now: number): Promise<void> {
    const e = this.ep(key);
    e.inflight = true;
    e.lastAt = now;
    this.status.polls++;
    let r: ApiResponse;
    try {
      r = await this.deps.api.get(path);
    } finally {
      e.inflight = false;
    }
    e.status = r.status;
    if (r.status === 429 || r.status === 0 || r.status >= 500) {
      // under a 429 storm shed the cheap endpoints first: the chain (prices) and positions (sizing) never slow past x4
      e.backoff = Math.min(e.backoff * 2, /^(chain:|positions$)/.test(key) ? 4 : 16);
      this.status.errors++;
    } else {
      e.backoff = 1;
      if (r.ok) {
        e.lastOkAt = r.t;
        this.status.lastOkAt = r.t;
      }
    }
    try {
      this.deps.sink('http', { method: 'GET', url: r.url, status: r.status, json: r.json, body: r.text, t: r.t });
    } catch {
      /* the store never throws, but never let a sink error kill the loop */
    }
  }
}

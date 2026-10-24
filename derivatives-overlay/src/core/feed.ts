// The overlay's own market-data WebSocket: the page subscribes only to the product tab it shows, so one socket of our
// own (same host, session cookie) carries both underlyings' quotes, trades and the news. The exchange honors only the
// first subscription frame per socket, so the symbol list is sent once and the socket is reopened when it grows.
import { Sink as HttpSink } from './poller';

export interface FeedConfig {
  enabled: boolean;
  channels: string[];
  path: string;
}

export interface FeedStatus {
  open: boolean;
  url: string | null;
  frames: number;
  lastAt: number;
  openedAt: number;
  reconnects: number;
  symbols: string[];
  lastClose: { code: number; t: number } | null;
}

export type WsSink = (kind: 'ws-in' | 'ws-open' | 'ws-close', p: { url: string; data?: string; json?: unknown; code?: number; t: number }) => void;

export interface FeedDeps {
  /** wss://host/ws/v1/market-data */
  url: () => string;
  symbols: () => string[];
  cfg: () => FeedConfig;
  enabled: () => boolean;
  sink: WsSink;
  WS?: typeof WebSocket;
  now?: () => number;
}

const REOPEN_MIN_MS = 10_000;

export class OwnFeed {
  readonly status: FeedStatus = { open: false, url: null, frames: 0, lastAt: 0, openedAt: 0, reconnects: 0, symbols: [], lastClose: null };
  private ws: WebSocket | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private nextOpenAt = 0;

  constructor(private deps: FeedDeps) {}

  private now(): number {
    return this.deps.now ? this.deps.now() : Date.now();
  }

  start(periodMs = 1000): void {
    if (this.timer) return;
    this.timer = setInterval(() => this.tick(), periodMs);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.close(1000);
  }

  private close(code: number): void {
    const ws = this.ws;
    this.ws = null;
    this.status.open = false;
    try {
      ws?.close(code);
    } catch {
      /* ignore */
    }
  }

  /** Open, reopen when the symbol set grew, reconnect after a close. Safe to call directly (tests). */
  tick(): void {
    const cfg = this.deps.cfg();
    if (!cfg.enabled || !this.deps.enabled()) {
      if (this.ws) this.close(1000);
      return;
    }
    const now = this.now();
    const symbols = [...new Set(this.deps.symbols())].sort();
    if (!symbols.length) return;
    if (this.ws) {
      const grew = symbols.some((s) => !this.status.symbols.includes(s));
      if (grew && now - this.status.openedAt > REOPEN_MIN_MS) {
        this.close(1000);
        this.status.reconnects++;
      } else return;
    }
    if (now < this.nextOpenAt) return;
    const WS = this.deps.WS ?? (typeof WebSocket !== 'undefined' ? WebSocket : null);
    if (!WS) return;
    const url = this.deps.url();
    let ws: WebSocket;
    try {
      ws = new WS(url);
    } catch {
      this.nextOpenAt = now + 5000;
      return;
    }
    this.ws = ws;
    this.status.url = url;
    this.status.symbols = symbols;
    this.status.openedAt = now;
    this.nextOpenAt = now + 2000;
    ws.addEventListener('open', () => {
      if (this.ws !== ws) return;
      this.status.open = true;
      try {
        ws.send(JSON.stringify({ action: 'subscribe', symbols, channels: cfg.channels }));
      } catch {
        /* ignore */
      }
      this.deps.sink('ws-open', { url, t: this.now() });
    });
    ws.addEventListener('message', (ev: MessageEvent) => {
      if (this.ws !== ws) return;
      const t = this.now();
      this.status.frames++;
      this.status.lastAt = t;
      const d = (ev as MessageEvent).data;
      if (typeof d !== 'string') return;
      let json: unknown;
      try {
        json = JSON.parse(d);
      } catch {
        json = undefined;
      }
      this.deps.sink('ws-in', { url, data: d, json, t });
    });
    ws.addEventListener('close', (ev) => {
      const code = (ev as CloseEvent).code;
      this.status.lastClose = { code, t: this.now() };
      if (this.ws === ws) {
        this.ws = null;
        this.status.open = false;
        this.status.reconnects++;
        this.nextOpenAt = this.now() + 2000 + Math.random() * 2000;
        this.deps.sink('ws-close', { url, code, t: this.now() });
      }
    });
    ws.addEventListener('error', () => {
      /* close follows */
    });
  }
}

export type { HttpSink };

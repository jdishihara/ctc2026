// Cookie-authenticated REST client for the exchange's own API (the calls the trading page itself makes). Runs in the
// content script, so requests go out with the page's session cookie and never need an API key. Never throws: network
// errors come back as status 0.

export interface ApiResponse {
  ok: boolean;
  status: number;
  json: unknown;
  text: string;
  /** request start, ms */
  t: number;
  url: string;
  method: string;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export class ExchangeApi {
  constructor(public base = '', private fetchFn: FetchLike = (i, init) => fetch(i, init)) {}

  private async req(method: string, path: string, body?: unknown): Promise<ApiResponse> {
    const url = this.base + path;
    const t = Date.now();
    try {
      const init: RequestInit = { method, credentials: 'same-origin', cache: 'no-store' };
      if (body !== undefined) {
        init.headers = { 'Content-Type': 'application/json' };
        init.body = JSON.stringify(body);
      }
      const res = await this.fetchFn(url, init);
      const text = await res.text();
      let json: unknown;
      try {
        json = text ? JSON.parse(text) : undefined;
      } catch {
        json = undefined;
      }
      return { ok: res.ok, status: res.status, json, text, t, url, method };
    } catch (e) {
      return { ok: false, status: 0, json: undefined, text: e instanceof Error ? e.message : String(e), t, url, method };
    }
  }

  get(path: string): Promise<ApiResponse> {
    return this.req('GET', path);
  }
  post(path: string, body: unknown): Promise<ApiResponse> {
    return this.req('POST', path, body);
  }
  del(path: string): Promise<ApiResponse> {
    return this.req('DELETE', path);
  }
}

/** The order body the trading page's Buy/Sell button sends. */
export interface OrderBody {
  symbol: string;
  side: 'buy' | 'sell';
  order_type: 'limit' | 'market';
  quantity: number;
  price?: number;
}

export const PATHS = {
  clock: '/api/v1/competitions/current',
  symbols: '/api/v1/symbols',
  chain: (u: string) => `/api/v1/options/${encodeURIComponent(u)}/chain`,
  positions: '/api/v1/positions?include_zero=true',
  openOrders: '/api/v1/orders/open',
  trades: (limit: number) => `/api/v1/trades?limit=${limit}`,
  orders: '/api/v1/orders',
  cancelAll: (u: string) => `/api/v1/orders/all?symbol_type=option&underlying=${encodeURIComponent(u)}`,
  cancelSymbol: (s: string) => `/api/v1/orders/all?symbol=${encodeURIComponent(s)}`,
};

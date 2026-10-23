// Sliding-window order-action meter (browser limit: 40 actions/min).

export interface RateLevel {
  used: number;
  limit: number;
  remaining: number;
  level: 'ok' | 'amber' | 'red';
}

export class RateMeter {
  private times: number[] = [];
  constructor(public windowMs = 60_000, public limit = 40, public amberAt = 30, public redAt = 36) {}

  add(t = Date.now(), n = 1): void {
    for (let i = 0; i < n; i++) this.times.push(t);
    if (this.times.length > 5000) this.times.splice(0, this.times.length - 5000);
  }

  count(now = Date.now()): number {
    const cut = now - this.windowMs;
    while (this.times.length && this.times[0] <= cut) this.times.shift();
    return this.times.length;
  }

  status(now = Date.now()): RateLevel {
    const used = this.count(now);
    return {
      used, limit: this.limit, remaining: Math.max(0, this.limit - used),
      level: used >= this.redAt ? 'red' : used >= this.amberAt ? 'amber' : 'ok',
    };
  }

  /** ms until the oldest action ages out (0 when there is spare capacity) */
  msUntilFree(now = Date.now()): number {
    if (this.count(now) < this.limit) return 0;
    return Math.max(0, this.times[0] + this.windowMs - now);
  }
}

/** Is this request an order action we should count? (POST/DELETE on /orders, cancel-all, ETF create/redeem) */
export function isOrderAction(method: string, url: string): boolean {
  const m = (method || 'GET').toUpperCase();
  if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') return false;
  return /\/api\/v\d+\/(orders|etf|create|redeem)/i.test(url) || /\/orders(\/|\?|$)/i.test(url);
}

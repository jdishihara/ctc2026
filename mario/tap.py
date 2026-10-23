"""Read the exchange the way the trading UI does. Two taps with the same `snapshot()`:

  BrowserTap  opens its own Chrome window (Playwright, persistent profile in ~/.ctc_mario_chrome) on the exchange; you
              log in there once (the login survives restarts). Every poll runs one fetch() batch inside that page, so
              the browser's session cookie authenticates it: no API key needed, which is the Mario Markets situation.
              `prefill()` types a symbol, side, quantity and price into the UI's order form; the human clicks the button.
  HttpTap     plain HTTP with an optional X-API-Key (the mock exchange, or a key if the organisers hand one out).

snapshot() -> {"t", "competition", "symbols", "books": {sym: {bids, asks}}, "positions": [...], "open_orders", "trades"}
"""
from __future__ import annotations
import json, os, threading, time, urllib.request

JS_POLL = """async (syms) => {
  const get = async (p) => { const r = await fetch(p, {credentials: 'include'}); if (!r.ok) throw new Error(p + ' ' + r.status); return r.json(); };
  const [symbols, positions, open_orders, trades, competition] = await Promise.all([
      get('/api/v1/symbols'), get('/api/v1/positions'), get('/api/v1/orders/open'), get('/api/v1/trades'), get('/api/v1/competitions/current')]);
  const want = syms && syms.length ? syms : symbols.symbols.filter(s => !s.settlement_active).map(s => s.symbol);
  const books = {};
  await Promise.all(want.map(async s => { try { books[s] = await get('/api/v1/orderbook/' + s); } catch (e) { books[s] = null; } }));
  return {symbols: symbols.symbols, positions: positions.positions || positions, open_orders: open_orders.orders || open_orders,
          trades: trades.trades || trades, competition, books};
}"""

JS_LOGGED_IN = "async () => { const r = await fetch('/api/v1/teams/me', {credentials: 'include'}); return r.status; }"


class HttpTap:
    def __init__(self, url: str, key: str | None = None, timeout: float = 5.0):
        self.url, self.key, self.timeout = url.rstrip("/"), key, timeout

    def _get(self, path: str):
        req = urllib.request.Request(self.url + path, headers={"X-API-Key": self.key} if self.key else {})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def post(self, path: str, body: dict):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"X-API-Key": self.key} if self.key else {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def ready(self) -> bool:
        try:
            self._get("/api/v1/competitions/current"); return True
        except Exception:
            return False

    def snapshot(self, symbols: list[str] | None = None) -> dict:
        syms = self._get("/api/v1/symbols")["symbols"]
        want = symbols or [s["symbol"] for s in syms if not s.get("settlement_active")]
        books = {}
        for s in want:
            try:
                books[s] = self._get(f"/api/v1/orderbook/{s}")
            except Exception:
                books[s] = None
        pos = self._get("/api/v1/positions"); oo = self._get("/api/v1/orders/open"); tr = self._get("/api/v1/trades")
        return {"t": time.time(), "symbols": syms, "books": books, "positions": pos.get("positions", pos), "open_orders": oo.get("orders", oo),
                "trades": tr.get("trades", tr), "competition": self._get("/api/v1/competitions/current")}


class BrowserTap:
    """Playwright must be used from the thread that created it: the desk calls every method from its tap thread."""

    def __init__(self, url: str, profile: str | None = None, headless: bool = False):
        self.url = url.rstrip("/"); self.profile = profile or os.path.expanduser("~/.ctc_mario_chrome"); self.headless = headless
        self.pw = self.ctx = self.page = None

    def start(self) -> None:
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.ctx = self.pw.chromium.launch_persistent_context(self.profile, channel="chrome", headless=self.headless,
                                                              viewport=None, args=["--window-size=1500,900"])
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.goto(self.url + "/trading", timeout=60_000)

    def ready(self) -> bool:
        try:
            return self.page.evaluate(JS_LOGGED_IN) == 200
        except Exception:
            return False

    def snapshot(self, symbols: list[str] | None = None) -> dict:
        d = self.page.evaluate(JS_POLL, symbols or [])
        d["t"] = time.time()
        return d

    def prefill(self, symbol: str, side: str, qty: int, price: float) -> str:
        """Select the symbol tab, the side, limit, and type qty and price. Nothing is submitted."""
        pg = self.page
        tab = pg.get_by_role("button", name=symbol, exact=True)
        if tab.count() == 0:
            return f"no tab for {symbol}"
        tab.first.click()
        pg.get_by_role("button", name=side.upper(), exact=True).first.click()
        pg.get_by_role("button", name="Limit", exact=True).first.click()
        pg.fill("#order-qty", str(int(qty))); pg.fill("#order-price", f"{price:.2f}")
        return f"prepared {side} {qty} {symbol} @ {price:.2f}: click the button in the Chrome window to send it"

    def stop(self) -> None:
        try:
            if self.ctx: self.ctx.close()
            if self.pw: self.pw.stop()
        except Exception:
            pass


def book_levels(book: dict | None) -> dict:
    """Normalise a book to {bids: [{price, quantity}], asks: [...]} sorted best first."""
    if not book:
        return {"bids": [], "asks": []}
    bids = sorted(({"price": float(x["price"]), "quantity": int(x["quantity"])} for x in book.get("bids", [])), key=lambda x: -x["price"])
    asks = sorted(({"price": float(x["price"]), "quantity": int(x["quantity"])} for x in book.get("asks", [])), key=lambda x: x["price"])
    return {"bids": bids, "asks": asks}

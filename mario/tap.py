"""Read the exchange the way the trading UI does. Two taps with the same `snapshot()`:

  BrowserTap  starts a plain Google Chrome with remote debugging on its own profile (~/.ctc_mario_chrome), attaches over
              CDP, and opens the exchange; you log in there once (the login survives restarts). Every poll runs one
              fetch() batch inside that tab, so the session cookie authenticates it: no API key needed (Mario Markets).
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

JS_BOOK = "async (sym) => { const r = await fetch('/api/v1/orderbook/' + sym, {credentials: 'include'}); if (!r.ok) throw new Error('orderbook ' + r.status); return r.json(); }"


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

    def book(self, symbol: str) -> dict:
        return book_levels(self._get(f"/api/v1/orderbook/{symbol}"))

    def submit(self, symbol: str, side: str, qty: int, price: float) -> str:
        """Send a limit order (the mock, or an API key if one exists)."""
        r = self.post("/api/v1/orders", {"symbol": symbol, "side": side, "order_type": "limit", "quantity": int(qty), "price": round(float(price), 2)})
        return json.dumps(r)[:160]

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
    """Starts a plain Google Chrome (no automation flags: Google sign-in refuses Playwright-launched windows with
    "browser not secure / unsupported") with remote debugging on a private profile, attaches to it over CDP, and runs the
    polling fetch() inside the exchange tab. Playwright objects are used only from the thread that created them."""

    CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    def __init__(self, url: str, profile: str | None = None, headless: bool = False, port: int = 9333):
        self.url = url.rstrip("/"); self.profile = profile or os.path.expanduser("~/.ctc_mario_chrome"); self.headless = headless
        self.port = port; self.proc = None; self.pw = self.browser = self.ctx = self.page = None

    def _cdp_alive(self) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=1) as r:
                return r.status == 200
        except Exception:
            return False

    def start(self) -> None:
        import subprocess
        if not self._cdp_alive():
            args = [self.CHROME, f"--remote-debugging-port={self.port}", f"--user-data-dir={self.profile}", "--no-first-run",
                    "--no-default-browser-check", "--window-size=1500,900", "--new-window"]
            if self.headless:
                args.append("--headless=new")
            args.append(self.url + "/trading")
            self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                if self._cdp_alive():
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("Chrome did not open its debugging port; is Google Chrome installed in /Applications?")
            self._wait_for_page()
        self._connect()

    def _wait_for_page(self, timeout: float = 15.0) -> None:
        """A freshly launched Chrome re-creates its first window while it starts; attaching during that tears the CDP
        session down after the first command or two (seen 2026-10-23 headless: 'Target page ... has been closed' right
        after the first click). Wait until the exchange tab is listed, then give the browser two more seconds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list", timeout=1) as r:
                    targets = json.loads(r.read())
                if any(t.get("type") == "page" and str(t.get("url", "")).startswith(self.url) for t in targets):
                    break
            except Exception:
                pass
            time.sleep(0.3)
        time.sleep(2.0)

    def _connect(self) -> None:
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        self.ctx = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        self._find_page()

    def _reconnect(self) -> None:
        """The Playwright session died (Chrome restarted its window, the connection dropped): attach again."""
        try:
            if self.browser: self.browser.close()
        except Exception:
            pass
        try:
            if self.pw: self.pw.stop()
        except Exception:
            pass
        self.pw = self.browser = self.ctx = self.page = None
        if not self._cdp_alive():
            raise RuntimeError("Chrome's debugging port is gone: restart the desk (it relaunches Chrome)")
        self._connect()

    def _recover(self) -> None:
        """After a failed page call: reopen the tab, or re-attach when the whole session is closed."""
        try:
            self._find_page()
        except Exception:
            self._reconnect()

    def _find_page(self) -> None:
        pages = [p for p in self.ctx.pages if p.url.startswith(self.url)]
        if pages:
            self.page = pages[0]
        else:
            self.page = self.ctx.new_page(); self.page.goto(self.url + "/trading", timeout=60_000)

    def ready(self) -> bool:
        try:
            return self.page.evaluate(JS_LOGGED_IN) == 200
        except Exception:
            try:
                self._recover()
            except Exception:
                pass
            return False

    def snapshot(self, symbols: list[str] | None = None) -> dict:
        try:
            d = self.page.evaluate(JS_POLL, symbols or [])
        except Exception:
            self._recover()                        # the tab was closed or navigated away, or the session dropped
            d = self.page.evaluate(JS_POLL, symbols or [])
        d["t"] = time.time()
        return d

    def book(self, symbol: str) -> dict:
        return book_levels(self.page.evaluate(JS_BOOK, symbol))

    def submit(self, symbol: str, side: str, qty: int, price: float) -> str:
        """prefill(), then click the UI's own submit button (its label is like "Buy 20 PORT": side, size, symbol). The
        button is found by that label, so a form that still shows another symbol or side is never submitted."""
        import re
        msg = self.prefill(symbol, side, qty, price)
        if not msg.startswith("prepared"):
            raise RuntimeError(msg)
        pg = self.page
        label = re.compile(rf"^\s*{side}\b.*\b{re.escape(symbol)}\b", re.I)
        btn = pg.get_by_role("button", name=label)
        if btn.count() == 0:
            raise RuntimeError(f"no submit button labelled '{side} ... {symbol}' in the UI (form not ready?)")
        text = btn.first.inner_text().strip()
        btn.first.click()
        return f"clicked '{text}'"

    def prefill(self, symbol: str, side: str, qty: int, price: float) -> str:
        """Select the symbol tab, the side, Limit, and type qty and price. Nothing is submitted."""
        pg = self.page
        tab = pg.get_by_role("button", name=symbol, exact=True)
        if tab.count() == 0:
            tab = pg.get_by_text(symbol, exact=True)
        if tab.count() == 0:
            return f"no tab for {symbol} in the UI"
        tab.first.click()
        pg.get_by_role("button", name=side.upper(), exact=True).first.click()
        pg.get_by_role("button", name="Limit", exact=True).first.click()
        pg.fill("#order-qty", str(int(qty))); pg.fill("#order-price", f"{price:.2f}")
        pg.bring_to_front()
        return f"prepared {side} {qty} {symbol} @ {price:.2f}: click the button in the Chrome window to send it"

    def stop(self) -> None:
        try:
            if self.browser: self.browser.close()
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

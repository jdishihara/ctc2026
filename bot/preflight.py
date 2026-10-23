"""Pre-trade checks for the live bot. Run before every start on competition day:

    python3 bot/preflight.py                 # testnet host, key from .botkey
    python3 bot/preflight.py --url https://cornelltradingcompetition.org --key-file .botkey

Each check prints PASS / WARN / FAIL with one line of detail; the exit code is 1 if anything FAILed. The checks cover
the mistakes that cost money on the testnet: key handling, wrong host, tick rounding, wrong strategy, stale code,
exchange reachability, leftover positions and orders, market-data flow, and a short simulator smoke run.
"""
from __future__ import annotations
import argparse, asyncio, json, math, os, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ctc.valuation import SYMS  # noqa: E402
ALLOWED_HOSTS = {"cornelltradingcompetition.org", "hurricane.cornelltradingcompetition.org"}
HEADERS = {"User-Agent": "ctc2026-bot/1.0"}

results: list[tuple[str, str, str]] = []


def report(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"{status:4} {name:34} {detail}", flush=True)


def get(url: str, key: str, path: str, api: bool = True):
    req = urllib.request.Request(url + ("/api/v1" if api else "") + path, headers={**HEADERS, "X-API-Key": key})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def check_key(key_file: Path) -> str | None:
    if not key_file.exists():
        report("FAIL", "bot key file", f"{key_file} missing")
        return None
    key = key_file.read_text().strip()
    if len(key) < 20:
        report("FAIL", "bot key file", "key looks too short")
        return None
    tracked = sh("git", "ls-files", str(key_file.relative_to(ROOT)))
    if tracked:
        report("FAIL", "bot key not tracked", f"{key_file.name} is tracked by git")
    else:
        report("PASS", "bot key not tracked", f"{key_file.name} is git-ignored")
    hits = subprocess.run(["git", "grep", "-l", key[:12], "--", "."], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if hits:
        report("FAIL", "key absent from tracked files", f"found in: {hits.replace(chr(10), ', ')}")
    else:
        report("PASS", "key absent from tracked files")
    return key


def check_host(url: str, allow_any: bool) -> bool:
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":")[0]
    if host in ALLOWED_HOSTS:
        report("PASS", "host", host)
        return True
    report("WARN" if allow_any else "FAIL", "host", f"{host} is not the competition host" + ("" if allow_any else " (use --allow-any-host for a mock)"))
    return allow_any


def check_tick() -> None:
    from bot.live import tick_price
    cases = [(57.654, "buy", 57.65), (57.654, "sell", 57.66), (57.65, "buy", 57.65), (57.65, "sell", 57.65), (0.1 + 0.2, "buy", 0.30)]
    bad = [(p, s, tick_price(p, s), want) for p, s, want in cases if abs(tick_price(p, s) - want) > 1e-9]
    if bad:
        report("FAIL", "tick rounding", str(bad))
    else:
        report("PASS", "tick rounding", "buys round down, sells round up, exact prices untouched")


def check_code() -> None:
    dirty = sh("git", "status", "--porcelain")
    head = sh("git", "rev-parse", "--short", "HEAD")
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    behind = sh("git", "rev-list", "--count", "HEAD..@{u}") if sh("git", "rev-parse", "--abbrev-ref", "@{u}") else "?"
    report("PASS" if not dirty else "WARN", "working tree", f"{branch} @ {head}" + (", uncommitted changes present" if dirty else ", clean") + (f", {behind} commits behind remote" if behind not in ("0", "?", "") else ""))
    for mod in ("websockets", "numpy"):
        try:
            __import__(mod)
            report("PASS", f"python module {mod}")
        except ImportError:
            report("FAIL", f"python module {mod}", "not installed")
    ladder = ROOT / "ctc" / "ladder.json"
    if ladder.exists():
        age_h = (time.time() - ladder.stat().st_mtime) / 3600
        report("PASS" if age_h < 72 else "WARN", "ladder file", f"ctc/ladder.json, {age_h:.0f} h old")
    else:
        report("FAIL", "ladder file", "ctc/ladder.json missing")


def check_strategy(args) -> None:
    try:
        from ctc.strategies import FairValueTrader
        st = FairValueTrader(min_edge=0.025, edge_full=0.03, analog=True, sd_mult=0.7, sigma=15.0, k=100, passive=0.75, warmup=20.0, max_cross=0.02, ent_cut=1.2, carry=0.5, cone_w=1.0, cone_s0=20.0,
                             basket_edge=args.basket_edge, basket_participation=args.basket_participation,
                             final_exact=True, final_edge=0.005, final_edge_full=0.005)
        report("PASS", "strategy constructs", f"analog={st.analog} min_edge={st.min_edge} edge_full={st.edge_full} sd_mult={st.sd_mult} passive={st.passive} warmup={st.warmup} max_cross={st.max_cross} carry={st.carry} ent_cut={st.ent_cut} cone_w={st.analog_kw.get('cone_w')} cone_s0={st.analog_kw.get('cone_s0')}")
        report("PASS", "final phase", f"exact={st.final_exact} entry={st.final_edge} full={st.final_edge_full}; requires all reports and complete weather")
        report('PASS', 'basket overlay', f'edge={st.basket_edge} participation={st.basket_participation}; max lot 10, requires fresh external depth')
    except Exception as exc:
        report("FAIL", "strategy constructs", repr(exc))


def check_exchange(url: str, key: str) -> dict | None:
    try:
        case = get(url, key, "/cases/hurricane.json", api=False)
        syms = list(case["limits"])
        report("PASS" if len(syms) == 12 else "WARN", "case file", f"{len(syms)} symbols, limits {min(case['limits'].values())}-{max(case['limits'].values())}")
    except Exception as exc:
        report("FAIL", "case file", repr(exc))
        return None
    try:
        tm = get(url, key, "/competitions/time")
        report("PASS", "exchange time", f"state={tm.get('state')} fictional={tm.get('fictional_time')} competition={str(tm.get('competition_id'))[:8]}")
    except urllib.error.HTTPError as exc:
        report("FAIL", "exchange time", f"HTTP {exc.code}: {exc.read().decode()[:120]} (bad key?)")
        return None
    except Exception as exc:
        report("FAIL", "exchange time", repr(exc))
        return None
    try:
        pos = get(url, key, "/positions")
        plist = pos if isinstance(pos, list) else pos.get("positions", pos)
        nonzero = {}
        if isinstance(plist, dict):
            nonzero = {k: v for k, v in plist.items() if isinstance(v, (int, float)) and v}
        elif isinstance(plist, list):
            nonzero = {p.get("symbol"): p.get("quantity", p.get("position")) for p in plist if p.get("quantity", p.get("position"))}
        report("PASS" if not nonzero else "WARN", "positions", "flat" if not nonzero else f"carrying {nonzero}")
    except Exception as exc:
        report("WARN", "positions", repr(exc))
    try:
        oo = get(url, key, "/orders/open")
        olist = oo if isinstance(oo, list) else oo.get("orders", [])
        report("PASS" if not olist else "WARN", "open orders", f"{len(olist)} resting" + ("" if not olist else " (bot/stop.sh cancels them)"))
    except Exception as exc:
        report("WARN", "open orders", repr(exc))
    return tm


async def check_marketdata(url: str, key: str, ws_override: str | None, seconds: float) -> None:
    try:
        import websockets
    except ImportError:
        return
    ws_url = (ws_override or url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)) + "/ws/v1/market-data"
    seen: dict[str, int] = {}
    t0 = time.time()
    try:
        async with websockets.connect(ws_url, additional_headers={"X-API-Key": key}, open_timeout=10) as ws:
            await ws.send(json.dumps({"action": "subscribe", "symbols": SYMS, "channels": ["news", "quotes"]}))
            while time.time() - t0 < seconds:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(0.5, seconds - (time.time() - t0)))
                except asyncio.TimeoutError:
                    break
                try:
                    m = json.loads(raw)
                except Exception:
                    continue
                t = m.get("type") or (m.get("data") or {}).get("type") or "?"
                seen[t] = seen.get(t, 0) + 1
    except Exception as exc:
        report("WARN", "market data", f"could not read {ws_url}: {exc!r} (the bot has its own subscribe logic; check bot/live.py --ws)")
        return
    if seen:
        report("PASS", "market data", f"{sum(seen.values())} messages in {seconds:.0f} s: {dict(sorted(seen.items(), key=lambda x: -x[1])[:4])}")
    else:
        report("WARN", "market data", f"no messages in {seconds:.0f} s (market halted?)")


def check_sim_smoke(basket_edge=0.01, basket_participation=0.5) -> None:
    try:
        out = subprocess.run([sys.executable, "scripts/backtest.py", "--strategy", "analog", "--seasons", "451-452", "--liquidity", "ladder", "--refill", "10",
                              '--basket-edge', str(basket_edge), '--basket-participation', str(basket_participation)],
                             cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
        line = next((l for l in out.splitlines() if l.startswith("analog:")), "")
        if "mean" in line and "nan" not in line:
            report("PASS", "simulator smoke run", line.split("|")[1].strip()[:60])
        else:
            report("FAIL", "simulator smoke run", (line or out[-200:]).strip())
    except Exception as exc:
        report("FAIL", "simulator smoke run", repr(exc))


def check_machine() -> None:
    caff = sh("pgrep", "-x", "caffeinate")
    report("PASS" if caff else "WARN", "sleep prevention", "caffeinate running" if caff else "no caffeinate: the Mac may sleep (run: caffeinate -i -t 36000 &)")
    running = sh("pgrep", "-f", "bot/live.py")
    report("WARN" if running else "PASS", "no bot already running", f"pids {running.split()}" if running else "")
    free_gb = os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize / 1e9
    report("PASS" if free_gb > 2 else "WARN", "disk", f"{free_gb:.0f} GB free")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="https://cornelltradingcompetition.org")
    ap.add_argument("--key-file", default=str(ROOT / ".botkey"))
    ap.add_argument("--ws", default=None, help="market-data host override (mock)")
    ap.add_argument("--allow-any-host", action="store_true")
    ap.add_argument("--listen", type=float, default=8.0, help="seconds to listen to market data")
    ap.add_argument("--no-sim", action="store_true", help="skip the simulator smoke run")
    ap.add_argument('--basket-edge', type=float, default=0.01)
    ap.add_argument('--basket-participation', type=float, default=0.5)
    a = ap.parse_args()
    print(f"preflight {time.strftime('%Y-%m-%d %H:%M:%S')} url={a.url}")
    key = check_key(Path(a.key_file))
    host_ok = check_host(a.url, a.allow_any_host)
    check_tick()
    check_code()
    check_strategy(a)
    check_machine()
    if key and host_ok:
        tm = check_exchange(a.url, key)
        if tm is not None:
            asyncio.run(check_marketdata(a.url, key, a.ws, a.listen))
    if not a.no_sim:
        check_sim_smoke(a.basket_edge, a.basket_participation)
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f"\n{len(results) - len(fails) - len(warns)} passed, {len(warns)} warnings, {len(fails)} failures")
    if fails:
        print("DO NOT START THE BOT until the failures above are fixed.")
        sys.exit(1)


if __name__ == "__main__":
    main()

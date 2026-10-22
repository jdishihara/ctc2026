"""Timed rehearsal of a Derivatives-case event (no bots allowed on the day, so the humans must be fast by hand).

    python3 derivs/drill.py                      # round 2 (analysts), 3 events, real timing: news t, S moves t+1:00, snap t+2:00
    python3 derivs/drill.py --round 1 --fast     # IV announced, 15 s phases
    python3 derivs/drill.py --round 3 --events 4 --seed 7
    python3 derivs/drill.py --auto               # self-test: scripted trades, no terminal input

What happens per event (mirrors the case packet and the Timeline sheet of derivs/desk.xlsx):
  t+0     headline; round 1 prints the new IV, round 2 three analyst IV estimates, round 3 an IV-linked quantity
          (expected 1-day move in % of spot, i.e. iv*sqrt(1/252)). The makers still quote at the OLD S and OLD IV.
          You set your view ("s OIL 83", "iv OIL 0.47") and trade ("buy OIL c80 5"); fills are at the quoted MIDPOINT.
  t+1:00  the underlying moves to the true S; the makers reprice with the new S but the OLD IV (delta, not vol).
  t+2:00  the makers snap to the true IV: everything is marked there, the event is scored, the best trades are shown.
Commands at the prompt: book | fair | s <U> <px> | iv <U> <vol> | buy|sell <U> <c|p><strike> <qty> | flat | help.
Scores: PnL per event in $, edge captured as a fraction of the best attainable with the same number of contracts,
and seconds to the first trade. A log goes to out/drill/.
"""
from __future__ import annotations
import argparse, json, math, random, select, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from derivs.bs import bs, implied_vol  # noqa: E402

UNDER = {"OIL": {"S": 80.0, "iv": 0.40}, "PLANE": {"S": 100.0, "iv": 0.50}}
STRIKES = {"OIL": (75, 80, 85), "PLANE": (90, 100, 110)}
DAYS = {1: 20, 2: 19, 3: 18}
MAX_PER_CONTRACT = 20
HEADLINES = {
    "OIL": [("OPEC+ surprises with a 1.2 mb/d cut", +1, +1), ("Strategic reserve release twice the expected size", -1, +1),
            ("Pipeline outage in the Gulf; restart date unknown", +1, +1), ("Inventories build for a sixth week; demand forecasts cut", -1, 0),
            ("Ceasefire talks resume; risk premium fades", -1, -1), ("Refinery fire; crack spreads jump", +1, +1)],
    "PLANE": [("Largest-ever order from a Gulf carrier", +1, -1), ("Regulator grounds the 7X series after a second incident", -1, +1),
              ("Quarterly deliveries miss by 20%", -1, +1), ("Engine supplier resolves the certification dispute", +1, -1),
              ("Guidance raised on strong defence backlog", +1, -1), ("Labour strike at the main assembly plant", -1, +1)],
}
ANALYSTS = [(+0.010, 0.020), (-0.005, 0.045), (+0.030, 0.030)]   # (bias, sd) in vol units: analyst 1 is best, 3 is biased high


def contracts(u: str) -> list[tuple[str, str, int]]:
    return [(u, kind, K) for kind in ("call", "put") for K in STRIKES[u]]


def quote(u: str, kind: str, K: int, S: float, iv: float, T: int) -> tuple[float, float, float]:
    f = bs(S, K, iv, T, 0.0, kind)["price"]
    half = max(0.04, 0.03 * f)
    return max(0.01, round(f - half, 2)), round(f + half, 2), f


class Event:
    def __init__(self, rnd: int, rng: random.Random, state: dict):
        self.rnd, self.T = rnd, DAYS[rnd]
        self.before = {u: dict(state[u]) for u in UNDER}
        self.after, self.news, self.analysts, self.quantity = {}, {}, {}, {}
        for u in UNDER:
            head, sdir, vdir = rng.choice(HEADLINES[u])
            move = sdir * rng.uniform(0.02, 0.07) * (1 if rng.random() < 0.85 else -0.4)   # 15% of headlines fake out
            dvol = vdir * rng.uniform(0.03, 0.10) + rng.gauss(0, 0.02)
            self.after[u] = {"S": round(self.before[u]["S"] * (1 + move), 2), "iv": round(max(0.12, self.before[u]["iv"] + dvol), 4)}
            self.news[u] = head
            self.analysts[u] = [round(self.after[u]["iv"] + b + rng.gauss(0, sd), 3) for b, sd in ANALYSTS]
            self.quantity[u] = round(self.after[u]["iv"] * math.sqrt(1 / 252) * 100, 2)   # expected 1-day move, % of spot

    def market(self, phase: int) -> dict[tuple[str, str, int], tuple[float, float, float]]:
        """phase 0: old S, old iv; 1: new S, old iv; 2: new S, new iv."""
        out = {}
        for u in UNDER:
            S = self.before[u]["S"] if phase == 0 else self.after[u]["S"]
            iv = self.after[u]["iv"] if phase == 2 else self.before[u]["iv"]
            for c in contracts(u):
                out[c] = quote(*c, S, iv, self.T)
        return out


def fmt_book(mkt: dict, fair: dict | None = None) -> str:
    lines = ["  contract        bid     ask     mid" + ("     your fair   edge$  edge(vol)" if fair else "")]
    for (u, kind, K), (b, a, _) in mkt.items():
        mid = (a + b) / 2
        row = f"  {u:5s} {kind[0]}{K:<4d}  {b:7.2f} {a:7.2f} {mid:7.2f}"
        if fair and (u, kind, K) in fair:
            f, vega = fair[(u, kind, K)]
            edge = f - mid
            row += f"   {f:9.2f} {edge:+7.2f} {edge / vega if vega > 1e-9 else 0:+8.1f}"
        lines.append(row)
    return "\n".join(lines)


def best_trades(ev: Event, n: int) -> list[tuple[tuple[str, str, int], str, float]]:
    """The n contracts with the largest |fair at the snap - opening mid|, i.e. what a perfect view would have traded."""
    open_m, snap_m = ev.market(0), ev.market(2)
    rows = []
    for c in open_m:
        edge = snap_m[c][2] - (open_m[c][0] + open_m[c][1]) / 2
        rows.append((c, "buy" if edge > 0 else "sell", abs(edge)))
    return sorted(rows, key=lambda r: -r[2])[:n]


def readline_timeout(deadline: float, prompt: str) -> str | None:
    rem = deadline - time.time()
    if rem <= 0:
        return None
    sys.stdout.write(prompt); sys.stdout.flush()
    r, _, _ = select.select([sys.stdin], [], [], rem)
    if not r:
        sys.stdout.write("\n")
        return None
    return sys.stdin.readline().strip()


def run_event(ev: Event, idx: int, phase_s: float, script: list[str] | None, log: list[dict]) -> dict:
    view = {u: dict(ev.before[u]) for u in UNDER}       # the trader's S and iv inputs (start at the pre-event values)
    trades: list[tuple[tuple[str, str, int], int, float]] = []     # contract, signed qty, price paid at midpoint
    t_start = time.time(); first_trade_t = None
    print(f"\n{'=' * 100}\nEVENT {idx}  round {ev.rnd}  T = {ev.T} days  (phases of {phase_s:.0f} s)")
    for u in UNDER:
        print(f"  {u:5s} spot {ev.before[u]['S']:.2f}  market IV {ev.before[u]['iv']:.3f}   NEWS: {ev.news[u]}")
        if ev.rnd == 1:
            print(f"        announced IV: {ev.after[u]['iv']:.3f}")
        elif ev.rnd == 2:
            print(f"        analysts' IV: {ev.analysts[u][0]:.3f}  {ev.analysts[u][1]:.3f}  {ev.analysts[u][2]:.3f}")
        else:
            print(f"        analysts' expected 1-day move: {ev.quantity[u]:.2f}% of spot   (IV = move% / 100 * sqrt(252))")
    pos: dict[tuple[str, str, int], int] = {}

    def fair_table() -> dict:
        out = {}
        for u in UNDER:
            for c in contracts(u):
                f = bs(view[u]["S"], c[2], view[u]["iv"], ev.T, 0.0, c[1])
                out[c] = (f["price"], f["vega"])
        return out

    def handle(cmd: str, phase: int) -> None:
        nonlocal first_trade_t
        mkt = ev.market(phase)
        p = cmd.split()
        if not p:
            return
        try:
            if p[0] == "book":
                print(fmt_book(mkt, fair_table()))
            elif p[0] == "fair":
                print(fmt_book(mkt, fair_table()))
            elif p[0] == "s" and len(p) == 3:
                view[p[1].upper()]["S"] = float(p[2]); print(f"  view {p[1].upper()} S = {float(p[2]):.2f}")
            elif p[0] == "iv" and len(p) == 3:
                view[p[1].upper()]["iv"] = float(p[2]); print(f"  view {p[1].upper()} iv = {float(p[2]):.3f}")
            elif p[0] in ("buy", "sell") and len(p) == 4:
                u = p[1].upper(); kind = "call" if p[2][0].lower() == "c" else "put"; K = int(p[2][1:]); q = int(p[3])
                c = (u, kind, K)
                if c not in mkt:
                    print("  no such contract"); return
                if abs(pos.get(c, 0) + (q if p[0] == "buy" else -q)) > MAX_PER_CONTRACT:
                    print(f"  limit {MAX_PER_CONTRACT} per contract"); return
                b, a, _ = mkt[c]; px = (a + b) / 2
                sq = q if p[0] == "buy" else -q
                trades.append((c, sq, px)); pos[c] = pos.get(c, 0) + sq
                if first_trade_t is None:
                    first_trade_t = time.time() - t_start
                print(f"  filled {p[0]} {q} {u} {kind} {K} @ {px:.2f} (midpoint)  position {pos[c]:+d}")
            elif p[0] == "flat":
                for c, q in list(pos.items()):
                    if q:
                        b, a, _ = mkt[c]; px = (a + b) / 2
                        trades.append((c, -q, px)); print(f"  closed {q:+d} {c[0]} {c[1]} {c[2]} @ {px:.2f}")
                        pos[c] = 0
            elif p[0] == "help":
                print(__doc__.split("Commands at the prompt:")[1].split("\n")[0])
            else:
                print("  ? (help)")
        except (ValueError, KeyError) as exc:
            print(f"  bad command ({exc})")

    labels = ["t+0 (makers at old S, old IV)", "t+1:00 (underlying moved; makers at new S, old IV)"]
    for phase in (0, 1):
        if phase == 1:
            print(f"\n--- t+{phase_s:.0f}s: underlying moves.  " + "  ".join(f"{u} {ev.before[u]['S']:.2f} -> {ev.after[u]['S']:.2f}" for u in UNDER))
            print(fmt_book(ev.market(1)))
        else:
            print(fmt_book(ev.market(0)))
        deadline = time.time() + phase_s
        if script is not None:
            for cmd in [c for c in script if c.startswith(f"{phase}:")]:
                handle(cmd[2:], phase)
            time.sleep(0.01)
        else:
            while True:
                line = readline_timeout(deadline, f"[{labels[phase]}] {max(0, deadline - time.time()):4.0f}s > ")
                if line is None:
                    break
                handle(line, phase)
    snap = ev.market(2)
    pnl = sum(q * ((snap[c][0] + snap[c][1]) / 2 - px) for c, q, px in trades)
    n_contracts = sum(abs(q) for _, q, _ in trades)
    best = best_trades(ev, 3)
    best_edge_per = sum(e for _, _, e in best) / 3 if best else 0.0
    captured = pnl / (best_edge_per * n_contracts) if n_contracts and best_edge_per > 0 else 0.0
    print(f"\n--- t+{2 * phase_s:.0f}s: makers snap to the true IV.  " + "  ".join(f"{u} IV {ev.before[u]['iv']:.3f} -> {ev.after[u]['iv']:.3f}" for u in UNDER))
    print(fmt_book(snap))
    print(f"\nEVENT {idx} RESULT: pnl {pnl:+.2f} on {n_contracts} contracts; first trade after {first_trade_t:.0f} s" if first_trade_t is not None
          else f"\nEVENT {idx} RESULT: no trades")
    print("  best three by edge at the snap vs the opening mid: " + ", ".join(f"{s} {c[0]} {c[1]} {c[2]} ({e:+.2f}/contract)" for c, s, e in best))
    print(f"  edge captured vs perfect foresight at your size: {captured:.0%}")
    if ev.rnd == 2:
        print("  analyst errors (vol pts): " + "  ".join(f"{u}: " + " ".join(f"{(a - ev.after[u]['iv']) * 100:+.1f}" for a in ev.analysts[u]) for u in UNDER))
    rec = {"event": idx, "round": ev.rnd, "pnl": round(pnl, 2), "contracts": n_contracts, "first_trade_s": first_trade_t,
           "captured": round(captured, 3), "truth": ev.after, "news": ev.news, "trades": [(list(c), q, px) for c, q, px in trades]}
    log.append(rec)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--events", type=int, default=3)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--fast", action="store_true", help="15 s phases instead of 60 s")
    ap.add_argument("--phase", type=float, default=None, help="seconds per phase (overrides --fast)")
    ap.add_argument("--auto", action="store_true", help="scripted self-test, no terminal input")
    a = ap.parse_args()
    phase_s = a.phase or (15.0 if a.fast else 60.0)
    rng = random.Random(a.seed)
    state = {u: dict(UNDER[u]) for u in UNDER}
    log: list[dict] = []
    script = None
    if a.auto:
        phase_s = 0.2
        script = ["0:book", "0:s OIL 84", "0:iv OIL 0.47", "0:fair", "0:buy OIL c80 5", "0:sell PLANE p90 3", "1:book", "1:flat"]
    for i in range(1, a.events + 1):
        ev = Event(a.round, rng, state)
        run_event(ev, i, phase_s, script, log)
        state = {u: dict(ev.after[u]) for u in UNDER}     # the next event starts where this one settled
    tot = sum(r["pnl"] for r in log)
    firsts = [r["first_trade_s"] for r in log if r["first_trade_s"] is not None]
    print(f"\n{'=' * 100}\nSESSION: {len(log)} events, pnl {tot:+.2f}, mean edge captured {sum(r['captured'] for r in log) / len(log):.0%}, "
          f"median first trade {sorted(firsts)[len(firsts) // 2]:.0f} s" if firsts else f"\nSESSION: {len(log)} events, no trades")
    out = Path(__file__).resolve().parents[1] / "out" / "drill"; out.mkdir(parents=True, exist_ok=True)
    f = out / f"drill_{time.strftime('%Y%m%d_%H%M%S')}.json"; f.write_text(json.dumps(log, indent=1))
    print("log:", f)


if __name__ == "__main__":
    main()

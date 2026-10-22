"""Derivatives case toolkit: Black-Scholes prices and greeks, implied vol, a mispricing scanner for the 12 contracts,
and an analyst scorecard. No bots are allowed in this case; this is a calculator for the humans at the desk.

    python3 derivs/bs.py price --S 80 --K 85 --iv 0.35 --T 20
    python3 derivs/bs.py iv --S 80 --K 85 --T 20 --price 2.1 --type call
    python3 derivs/bs.py scan --S 80 --iv 0.40 --T 20 --book OIL_book.csv
         book csv columns: type,strike,bid,ask   (one row per contract)
    python3 derivs/bs.py analysts --file analysts.csv
         columns: event,underlying,a1,a2,a3,truth   (truth = IV implied after the makers snap to fair)

T is in trading days (252 per year). Rate r defaults to 0; the exchange calculator fixes it, set --r to match.
"""
from __future__ import annotations
import argparse, csv, math, sys


def _N(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _n(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def bs(S: float, K: float, iv: float, T_days: float, r: float = 0.0, kind: str = "call") -> dict:
    T = T_days / 252.0
    if T <= 0 or iv <= 0:
        intrinsic = max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
        return {"price": intrinsic, "delta": float(S > K) if kind == "call" else -float(S < K), "vega": 0.0, "gamma": 0.0}
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T) / (iv * math.sqrt(T)); d2 = d1 - iv * math.sqrt(T)
    if kind == "call":
        price = S * _N(d1) - K * math.exp(-r * T) * _N(d2); delta = _N(d1)
    else:
        price = K * math.exp(-r * T) * _N(-d2) - S * _N(-d1); delta = _N(d1) - 1
    vega = S * _n(d1) * math.sqrt(T) / 100.0           # per 1 vol point
    gamma = _n(d1) / (S * iv * math.sqrt(T))
    return {"price": price, "delta": delta, "vega": vega, "gamma": gamma}


def implied_vol(price: float, S: float, K: float, T_days: float, r: float = 0.0, kind: str = "call") -> float | None:
    lo, hi = 1e-4, 5.0
    if price < bs(S, K, lo, T_days, r, kind)["price"] - 1e-9 or price > bs(S, K, hi, T_days, r, kind)["price"] + 1e-9:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if bs(S, K, mid, T_days, r, kind)["price"] > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def scan(S: float, iv: float, T_days: float, book: list[dict], r: float = 0.0) -> list[dict]:
    """Rank contracts by edge: fair minus the side we would trade, in dollars and in vol points."""
    rows = []
    for c in book:
        K, bid, ask, kind = float(c["strike"]), float(c["bid"]), float(c["ask"]), c["type"].lower()
        f = bs(S, K, iv, T_days, r, kind)
        if f["price"] > ask:
            edge, side, px = f["price"] - ask, "BUY", ask
        elif f["price"] < bid:
            edge, side, px = bid - f["price"], "SELL", bid
        else:
            edge, side, px = 0.0, "-", (bid + ask) / 2
        mkt_iv = implied_vol(px, S, K, T_days, r, kind)
        rows.append({"type": kind, "strike": K, "bid": bid, "ask": ask, "fair": f["price"], "side": side, "edge": edge,
                     "edge_vol": (edge / f["vega"]) if f["vega"] > 1e-9 else float("inf"), "mkt_iv": mkt_iv, "delta": f["delta"], "vega": f["vega"]})
    return sorted(rows, key=lambda x: -x["edge"])


def analysts(rows: list[dict]) -> None:
    import statistics as st
    names = [k for k in rows[0] if k.startswith("a")]
    print("analyst  n   mean abs error (vol pts)   bias   by underlying")
    for a in names:
        errs = [(float(r[a]) - float(r["truth"])) * 100 for r in rows if r.get(a) and r.get("truth")]
        byu = {}
        for r in rows:
            if r.get(a) and r.get("truth"):
                byu.setdefault(r["underlying"], []).append(abs(float(r[a]) - float(r["truth"])) * 100)
        print(f"{a:7s} {len(errs):2d}   {st.mean(map(abs, errs)) if errs else float('nan'):6.2f}                {st.mean(errs) if errs else float('nan'):+6.2f}   "
              + "  ".join(f"{u} {st.mean(v):.2f}" for u, v in byu.items()))
    print("weights (inverse mean-abs-error, normalised):")
    inv = {a: 1 / max(1e-6, st.mean(abs(float(r[a]) - float(r["truth"])) * 100 for r in rows if r.get(a) and r.get("truth"))) for a in names}
    tot = sum(inv.values())
    print("  " + "  ".join(f"{a} {v / tot:.2f}" for a, v in inv.items()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("price"); p.add_argument("--S", type=float, required=True); p.add_argument("--K", type=float, required=True); p.add_argument("--iv", type=float, required=True); p.add_argument("--T", type=float, required=True); p.add_argument("--r", type=float, default=0.0)
    p = sub.add_parser("iv"); p.add_argument("--S", type=float, required=True); p.add_argument("--K", type=float, required=True); p.add_argument("--T", type=float, required=True); p.add_argument("--price", type=float, required=True); p.add_argument("--type", default="call"); p.add_argument("--r", type=float, default=0.0)
    p = sub.add_parser("scan"); p.add_argument("--S", type=float, required=True); p.add_argument("--iv", type=float, required=True); p.add_argument("--T", type=float, required=True); p.add_argument("--book", required=True); p.add_argument("--r", type=float, default=0.0)
    p = sub.add_parser("analysts"); p.add_argument("--file", required=True)
    a = ap.parse_args()
    if a.cmd == "price":
        for kind in ("call", "put"):
            f = bs(a.S, a.K, a.iv, a.T, a.r, kind); print(f"{kind}: price {f['price']:.4f} delta {f['delta']:+.3f} vega {f['vega']:.4f}/volpt gamma {f['gamma']:.4f}")
    elif a.cmd == "iv":
        v = implied_vol(a.price, a.S, a.K, a.T, a.r, a.type); print("implied vol:", f"{v:.4f}" if v else "none (price outside no-arbitrage bounds)")
    elif a.cmd == "scan":
        rows = scan(a.S, a.iv, a.T, list(csv.DictReader(open(a.book))), a.r)
        print(f"{'type':5s} {'K':>7s} {'bid':>7s} {'ask':>7s} {'fair':>7s} side {'edge$':>6s} {'edge(vol)':>9s} {'mktIV':>6s} {'delta':>6s} {'vega':>6s}")
        for x in rows:
            print(f"{x['type']:5s} {x['strike']:7.2f} {x['bid']:7.2f} {x['ask']:7.2f} {x['fair']:7.2f} {x['side']:4s} {x['edge']:6.2f} {x['edge_vol']:9.2f} {(x['mkt_iv'] or 0):6.3f} {x['delta']:+6.2f} {x['vega']:6.3f}")
    else:
        analysts(list(csv.DictReader(open(a.file))))


if __name__ == "__main__":
    main()

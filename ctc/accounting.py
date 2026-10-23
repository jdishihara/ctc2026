"""Offline average-cost replay of an account's own fills.

Input must contain all fills since the supplied opening snapshot. Matching final
positions alone cannot establish completeness: omitted round trips leave no net
position. Fees explicitly present on a trade are charged to realized PnL.
"""
from datetime import datetime
from itertools import groupby
import math


def _number(value, label, integer=False):
    if isinstance(value, bool):
        raise ValueError(f"invalid {label}")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not math.isfinite(result) or (integer and result != int(result)):
        raise ValueError(f"invalid {label}")
    return int(result) if integer else result


def _positions(rows):
    result = {}
    for row in rows:
        symbol = row["symbol"]
        if symbol in result:
            raise ValueError(f"duplicate position for {symbol}")
        qty = _number(row["quantity"], "position quantity", integer=True)
        avg = _number(row.get("average_price") or 0, "average price")
        if qty and avg <= 0:
            raise ValueError(f"missing positive average price for {symbol}")
        result[symbol] = dict(quantity=qty, average_price=avg if qty else 0.0,
                              realized_pnl=_number(row.get("realized_pnl", 0), "realized pnl"))
    return result


def _fills(rows):
    unique = {}
    for row in rows:
        ident = row.get("trade_id", row.get("id"))
        if isinstance(ident, bool) or not isinstance(ident, (str, int)) or ident == "":
            raise ValueError("fill needs a stable trade id")
        side = row.get("side")
        if side not in ("buy", "sell"):
            # A trade's aggressor may be our counterparty; never infer from that.
            for field in ("buyer_is_me", "is_buyer"):
                if isinstance(row.get(field), bool):
                    side = "buy" if row[field] else "sell"
                    break
        if side not in ("buy", "sell"):
            raise ValueError("fill needs our side, not the aggressor's side")
        qty = _number(row["quantity"], "trade quantity", integer=True)
        price = _number(row["price"], "trade price")
        if qty <= 0 or price <= 0:
            raise ValueError("trade quantity and price must be positive")
        try:
            timestamp = datetime.fromisoformat(row.get("executed_at", row.get("timestamp")))
        except (TypeError, ValueError) as exc:
            raise ValueError("fill needs an ISO executed_at/timestamp") from exc
        if timestamp.tzinfo is None:
            raise ValueError("fill timestamp needs a timezone")
        sequence = row.get("sequence", row.get("seq"))
        if sequence is not None:
            sequence = _number(sequence, "sequence", integer=True)
        fill = dict(symbol=row["symbol"], side=side, quantity=qty, price=price,
                    timestamp=timestamp, sequence=sequence,
                    fee=_number(row.get("fee", 0), "fee"))
        ident = str(ident)
        if ident in unique and unique[ident] != fill:
            raise ValueError(f"conflicting duplicate trade id {ident}")
        unique[ident] = fill
    fills = sorted(unique.values(), key=lambda f: (f["timestamp"], f["symbol"]))
    ordered = []
    for _, group in groupby(fills, key=lambda f: (f["timestamp"], f["symbol"])):
        group = list(group)
        if len({f["side"] for f in group}) > 1:
            seq = [f["sequence"] for f in group]
            if None in seq or len(seq) != len(set(seq)):
                raise ValueError("ambiguous fill order; equal timestamps need unique sequence numbers")
            group.sort(key=lambda f: f["sequence"])
        ordered.extend(group)
    return ordered


def replay(trades, opening=()):
    """Return quantity, average entry price and realized PnL for each symbol."""
    states = _positions(opening)
    for fill in _fills(trades):
        state = states.setdefault(fill["symbol"], dict(quantity=0, average_price=0.0, realized_pnl=0.0))
        q, avg = state["quantity"], state["average_price"]
        delta = fill["quantity"] * (1 if fill["side"] == "buy" else -1)
        price, new = fill["price"], q + delta
        if q == 0 or q * delta > 0:
            avg = (abs(q) * avg + abs(delta) * price) / abs(new)
        else:
            closed = min(abs(q), abs(delta))
            state["realized_pnl"] += closed * (price - avg) * (1 if q > 0 else -1)
            if new == 0:
                avg = 0.0
            elif q * new < 0:
                avg = price
        state.update(quantity=new, average_price=avg)
        state["realized_pnl"] -= fill["fee"]
    return states


def audit(trades, positions, opening=()):
    """Compare exchange minus average-cost replay; do not infer a cause for gaps."""
    if any("realized_pnl" not in row for row in positions):
        raise ValueError("comparison snapshot needs realized_pnl for each row")
    expected, observed = replay(trades, opening), _positions(positions)
    empty = dict(quantity=0, average_price=0.0, realized_pnl=0.0)
    symbols = {}
    for symbol in sorted(expected.keys() | observed.keys()):
        ours, theirs = expected.get(symbol, empty), observed.get(symbol, empty)
        symbols[symbol] = dict(model=ours, exchange=theirs,
            quantity_difference=theirs["quantity"] - ours["quantity"],
            average_price_difference=(theirs["average_price"] - ours["average_price"]
                                      if theirs["quantity"] == ours["quantity"] and ours["quantity"] else None),
            realized_difference=theirs["realized_pnl"] - ours["realized_pnl"])
    return dict(positions_match=all(r["quantity_difference"] == 0 for r in symbols.values()),
                realized_difference=sum(r["realized_difference"] for r in symbols.values()),
                symbols=symbols,
                note="Requires all fills since opening; matching positions does not prove history completeness.")

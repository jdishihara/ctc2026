"""Mario desk auto-execution (mario/executor.py): rate limiter, re-check before submit, stop/go and UNMAPPED gates."""
import pytest

from mario.engine import Action
from mario.executor import Executor, RateLimiter, recheck_leg

ROLES = {f"R{r}_{h}": ("race", r, h) for r in (1, 2, 3) for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")}
ROLES["S1_NO1"] = ("s1", 1)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeExchange:
    """Books per symbol; records submissions; can be told to move a book before the re-check."""
    def __init__(self, books):
        self.books = books
        self.sent = []
        self.fail = set()

    def book(self, sym):
        return self.books[sym]

    def submit(self, sym, side, qty, px):
        if sym in self.fail:
            raise RuntimeError("HTTP 429")
        self.sent.append((sym, side, qty, px))
        return "ok"


def book(bid, bq, ask, aq):
    return {"bids": [{"price": bid, "quantity": bq}], "asks": [{"price": ask, "quantity": aq}]}


def make(ex, clock=None, **kw):
    log = []
    e = Executor(ex.submit, ex.book, ROLES, log.append, clock=clock or Clock(), **kw)
    return e, log


def test_rate_limiter_rolling_window():
    c = Clock(); rl = RateLimiter(3, clock=c)
    for _ in range(3):
        assert rl.allow(); rl.record(); c.t += 1.0           # recorded at 1000, 1001, 1002
    assert not rl.allow() and rl.used() == 3
    assert rl.wait_for() == pytest.approx(57.0)
    c.t = 1059.9
    assert not rl.allow()
    c.t = 1060.1
    assert rl.allow() and rl.used() == 2                      # only the first one has expired


def test_recheck_leg_resizes_to_fresh_book():
    leg = ("R1_BIRDO", "buy", 30, 40.0)
    assert recheck_leg(leg, book(38, 50, 39.5, 50)) == (30, 39.5)          # everything still there
    assert recheck_leg(leg, book(38, 50, 40.0, 12)) == (12, 40.0)          # thinner: smaller order
    assert recheck_leg(leg, book(38, 50, 40.1, 50)) == (0, None)           # touch moved past the limit: skip
    assert recheck_leg(("R1_BIRDO", "sell", 30, 38.0), book(37.9, 50, 39, 50)) == (0, None)
    assert recheck_leg(leg, {"bids": [], "asks": []}) == (0, None)


def test_edge_order_is_resized_or_skipped_when_the_book_moved():
    ex = FakeExchange({"R1_BIRDO": book(38, 50, 40.0, 12)})
    e, log = make(ex)
    acts = [Action("edge", [("R1_BIRDO", "buy", 30, 40.0)], 90.0, "cheap")]
    assert e.run(acts, {}, []) == 1
    assert ex.sent == [("R1_BIRDO", "buy", 12, 40.0)]
    ex.books["R1_BIRDO"] = book(38, 50, 41.0, 50); ex.sent.clear()
    assert e.run(acts, {}, []) == 0 and e.skipped == 1 and ex.sent == []
    assert any(line.startswith("skip edge") for line in log)


def test_position_limit_is_rechecked_at_submit():
    ex = FakeExchange({"R1_BIRDO": book(38, 50, 40.0, 50)})
    e, _ = make(ex)
    acts = [Action("edge", [("R1_BIRDO", "buy", 30, 40.0)], 90.0, "")]
    assert e.run(acts, {"R1_BIRDO": {"qty": 90}}, []) == 1
    assert ex.sent == [("R1_BIRDO", "buy", 10, 40.0)]                       # race limit 100
    ex.sent.clear()
    assert e.run(acts, {"R1_BIRDO": {"qty": 100}}, []) == 0 and ex.sent == []


def test_arb_is_all_or_nothing_and_equal_sized():
    books = {f"R1_{h}": book(20, 50, 24.0, 50) for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")}
    books["R1_YOSHI"] = book(20, 50, 24.0, 7)                               # one leg thinned
    ex = FakeExchange(books)
    e, log = make(ex)
    legs = [(f"R1_{h}", "buy", 20, 24.0) for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")]
    acts = [Action("arb", legs, 80.0, "race 1 set buys 96 vs 100"), Action("edge", [("S1_NO1", "buy", 10, 50.0)], 500.0, "")]
    ex.books["S1_NO1"] = book(48, 50, 49.0, 50)
    assert e.run(acts, {}, []) == 5
    assert ex.sent[:4] == [(f"R1_{h}", "buy", 7, 24.0) for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")]   # arb first, equal size
    assert ex.sent[4][0] == "S1_NO1"
    ex.books["R1_YOSHI"] = book(20, 50, 25.0, 50); ex.sent.clear()
    assert e.run(acts[:1], {}, []) == 0 and ex.sent == []                   # one leg gone: whole arb skipped


def test_stop_go_gate_and_unmapped_gate():
    ex = FakeExchange({"R1_BIRDO": book(38, 50, 40.0, 50)})
    e, _ = make(ex)
    acts = [Action("edge", [("R1_BIRDO", "buy", 10, 40.0)], 30.0, "")]
    e.enabled = False
    assert e.run(acts, {}, []) == 0 and ex.sent == []
    assert "stopped" in e.blocked([])
    e.enabled = True
    assert e.run(acts, {}, ["WEIRD_SYM"]) == 0 and ex.sent == []
    assert "UNMAPPED" in e.blocked(["WEIRD_SYM"])
    assert e.run(acts, {}, []) == 1 and len(ex.sent) == 1


def test_rate_cap_stops_mid_pass_and_resumes_later():
    c = Clock()
    ex = FakeExchange({f"R1_{h}": book(20, 50, 24.0, 50) for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")})
    e, log = make(ex, clock=c, max_per_min=2)
    acts = [Action("edge", [(f"R1_{h}", "buy", 5, 24.0)], 30.0, "") for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")]
    assert e.run(acts, {}, [], max_actions=10) == 2
    assert e.run(acts, {}, [], max_actions=10) == 0 and "budget" in e.blocked([])
    c.t += 61
    assert e.run(acts, {}, [], max_actions=10) == 2
    # a multi-leg action never starts when the budget cannot cover every leg
    c.t += 61
    arb = Action("arb", [(f"R1_{h}", "buy", 5, 24.0) for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")], 80.0, "")
    before = e.skipped
    assert e.run([arb], {}, [], max_actions=10) == 0 and e.skipped == before + 1


def test_verify_marks_filled_partial_and_unconfirmed():
    ex = FakeExchange({"R1_BIRDO": book(38, 50, 40.0, 50), "R1_DAISY": book(38, 50, 40.0, 50), "R1_PEACH": book(38, 50, 40.0, 50)})
    e, log = make(ex, confirm_polls=2)
    acts = [Action("edge", [("R1_BIRDO", "buy", 10, 40.0)], 30.0, ""), Action("edge", [("R1_DAISY", "buy", 10, 40.0)], 20.0, ""),
            Action("edge", [("R1_PEACH", "sell", 10, 38.0)], 10.0, "")]
    assert e.run(acts, {}, []) == 3 and len(e.pending) == 3
    snap = {"trades": [{"trade_id": "a", "symbol": "R1_BIRDO", "side": "buy", "quantity": 10},
                       {"trade_id": "b", "symbol": "R1_DAISY", "side": "buy", "quantity": 4}], "open_orders": []}
    e.verify(snap)
    assert [s.outcome for s in e.history] == ["filled"]
    e.verify({"trades": snap["trades"], "open_orders": []})                 # same trades again: not double counted
    outcomes = {s.symbol: s.outcome for s in e.history}
    assert outcomes["R1_DAISY"] == "partial 4/10" and outcomes["R1_PEACH"].startswith("unconfirmed")
    assert e.pending == []
    assert e.summary()["sent"] == 3 and e.summary()["filled"] == 1


def test_failed_submission_is_logged_and_counted():
    ex = FakeExchange({"R1_BIRDO": book(38, 50, 40.0, 50)}); ex.fail.add("R1_BIRDO")
    e, log = make(ex)
    assert e.run([Action("edge", [("R1_BIRDO", "buy", 10, 40.0)], 30.0, "")], {}, []) == 1
    assert e.history[0].outcome == "failed" and "FAILED" in log[-1] and e.limiter.used() == 1


def test_orders_per_poll_cap_spreads_the_budget():
    ex = FakeExchange({f"R{r}_{h}": book(20, 50, 24.0, 50) for r in (1, 2, 3) for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")})
    e, _ = make(ex, max_per_min=36)
    arbs = [Action("arb", [(f"R{r}_{h}", "buy", 5, 24.0) for h in ("BIRDO", "DAISY", "PEACH", "YOSHI")], 80.0, "") for r in (1, 2, 3)]
    assert e.run(arbs, {}, [], max_actions=10, max_orders=8) == 8          # two complete arbs, the third waits for the next poll
    assert e.run(arbs, {}, [], max_actions=10, max_orders=8) == 8
    assert e.limiter.used() == 16


def test_nonsense_prices_are_never_sent():
    ex = FakeExchange({"R1_BIRDO": book(-5, 50, -3.0, 50), "R1_DAISY": book(101, 50, 103.0, 50), "S1_NO1": book(-2, 50, -1.0, 50)})
    e, log = make(ex)
    acts = [Action("edge", [("R1_BIRDO", "buy", 10, -3.0)], 30.0, ""), Action("edge", [("R1_DAISY", "sell", 10, 101.0)], 30.0, ""),
            Action("edge", [("S1_NO1", "buy", 10, -1.0)], 30.0, "")]
    assert e.run(acts, {}, [], max_actions=10) == 0 and ex.sent == [] and e.skipped == 3

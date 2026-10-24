"""Live announcements: pause, automatic re-anchor to the house mid, and the human command file (bot/control.py)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.control import ControlFile, apply_control, parse_control
from ctc.strategies import FairValueTrader
from tests.test_execution import ScriptedExchange, order

CASE = json.loads((Path(__file__).resolve().parents[1] / "data/case.json").read_text())


def trader(exchange, **kw):
    strategy = FairValueTrader(min_edge=0.025, edge_full=0.03, **kw)
    strategy.on_start(exchange)
    strategy.model.round = 3
    strategy.model.storm_reported = True
    strategy.fair = strategy.compute_fair()
    exchange.mid = {s: strategy.fair[s] for s in strategy.fair}
    exchange.quotes = {s: (m * 0.999, m * 1.001) for s, m in exchange.mid.items()}
    return strategy


@pytest.fixture
def exchange():
    return ScriptedExchange()


def test_parse_commands():
    assert parse_control("HAVEN -6%") == {"op": "adjust", "symbol": "HAVEN", "mult": pytest.approx(0.94), "add": 0.0}
    assert parse_control("gen +3") == {"op": "adjust", "symbol": "GEN", "mult": 1.0, "add": 3.0}
    assert parse_control("PORT =61.5  # port reopened") == {"op": "anchor", "symbol": "PORT", "price": 61.5}
    assert parse_control("resume haven rein") == {"op": "resume", "symbols": ["HAVEN", "REIN"]}
    assert parse_control("pause MAT") == {"op": "pause", "symbols": ["MAT"]}
    assert parse_control("clear GEN") == {"op": "clear", "symbols": ["GEN"]}
    assert parse_control("status") == {"op": "status"}
    assert parse_control("   ") is None and parse_control("# note") is None
    for bad in ("FOO -5%", "HAVEN", "HAVEN -5% +3", "HAVEN =-1", "HAVEN -100%", "HAVEN abc", "resume", "pause FOO"):
        with pytest.raises(ValueError):
            parse_control(bad)


def test_adjust_moves_fair_and_etf_follows_basket(exchange):
    strategy = trader(exchange)
    base = dict(strategy.fair)
    strategy.pause(["HAVEN"])
    msg = apply_control(strategy, exchange, "HAVEN -10%")
    assert "resumed" in msg and "HAVEN" not in strategy.paused
    assert strategy.fair["HAVEN"] == pytest.approx(base["HAVEN"] * 0.9)
    arch = CASE["etfs"]["ARCH"]["basket"]
    assert strategy.fair["ARCH"] == pytest.approx(sum(n * strategy.fair[s] for s, n in arch.items()))
    assert strategy.fair["ARCH"] != pytest.approx(base["ARCH"])
    assert strategy.fair["REBLD"] == pytest.approx(base["REBLD"])     # HAVEN is not in REBLD
    # the adjustment survives a model recompute
    assert strategy.compute_fair()["HAVEN"] == pytest.approx(base["HAVEN"] * 0.9)
    apply_control(strategy, exchange, "clear HAVEN")
    assert strategy.compute_fair()["HAVEN"] == pytest.approx(base["HAVEN"])
    assert strategy.adjust == {}


def test_additive_and_anchor_commands(exchange):
    strategy = trader(exchange)
    base = dict(strategy.fair)
    apply_control(strategy, exchange, "GEN +3")
    assert strategy.fair["GEN"] == pytest.approx(base["GEN"] + 3)
    msg = apply_control(strategy, exchange, "PORT =61.5")
    assert "anchored" in msg
    assert strategy.fair["PORT"] == pytest.approx(61.5)
    assert strategy.adjust["PORT"] == (1.0, pytest.approx(61.5 - base["PORT"]))
    # anchoring twice does not compound
    apply_control(strategy, exchange, "PORT =70")
    assert strategy.fair["PORT"] == pytest.approx(70)
    assert "error" in apply_control(strategy, exchange, "PORT nonsense")
    status = apply_control(strategy, exchange, "status")
    assert "GEN" in status and "PORT" in status


def test_announcement_reanchors_to_house_mid_after_wait(exchange):
    strategy = trader(exchange, announce_wait=60)
    strategy.on_round(exchange)
    strategy.warmup = 0
    t0 = exchange.t
    strategy.announce(["HAVEN"], t0)
    assert "HAVEN" in strategy.paused
    exchange.open_orders = [{**order(), "symbol": "HAVEN"}]
    exchange.mid["HAVEN"] = 30.0
    exchange.quotes["HAVEN"] = (29.9, 30.1)
    with patch.object(exchange, "send", return_value={"cancelled": 1}):
        strategy.on_quotes(exchange)                    # too early: still paused, orders cancelled
    assert "HAVEN" in strategy.paused and exchange.resting("HAVEN", "buy") == 0
    logged = []
    strategy.log = lambda *a, **k: logged.append(a[0])
    with patch.object(type(exchange), "t", property(lambda self: t0 + 61)), \
            patch.object(exchange, "send", return_value={"order_id": "x", "filled_quantity": 0}):
        strategy.on_quotes(exchange)
    assert "HAVEN" not in strategy.paused
    assert strategy.fair["HAVEN"] == pytest.approx(30.0)
    assert any("anchored to house mid 30.00" in line for line in logged)


def test_announcement_waits_for_human_when_wait_is_zero(exchange):
    strategy = trader(exchange, announce_wait=0)
    strategy.on_round(exchange)
    t0 = exchange.t
    strategy.announce(["GEN"], t0)
    with patch.object(type(exchange), "t", property(lambda self: t0 + 3600)), \
            patch.object(exchange, "send", return_value={"cancelled": 1}):
        strategy.on_quotes(exchange)
    assert "GEN" in strategy.paused
    apply_control(strategy, exchange, "resume GEN")
    assert "GEN" not in strategy.paused and strategy.adjust == {}


def test_control_file_tails_new_lines_only(tmp_path, exchange):
    strategy = trader(exchange)
    path = tmp_path / "control.txt"
    path.write_text("HAVEN -50%\n")                    # from an earlier run: must be ignored
    ctl = ControlFile(str(path))
    assert ctl.poll(strategy, exchange) == []
    with path.open("a") as fh:
        fh.write("GEN +2\nbogus line\n# comment\nPORT =5")   # last line has no newline yet
    out = ctl.poll(strategy, exchange)
    assert len(out) == 2 and out[0].startswith("CONTROL GEN") and "error" in out[1]
    assert strategy.fair["PORT"] != pytest.approx(5)
    with path.open("a") as fh:
        fh.write("0\n")
    out = ctl.poll(strategy, exchange)
    assert len(out) == 1 and strategy.fair["PORT"] == pytest.approx(50)
    assert ctl.poll(strategy, exchange) == []
    missing = ControlFile(str(tmp_path / "none.txt"))
    assert missing.poll(strategy, exchange) == []

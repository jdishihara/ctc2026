import json
from pathlib import Path

import pytest

from ctc.strategies import FairValueTrader
from scripts.experiment_final_reports import FinalReportsTrader, summarize_pairs
from scripts.replay_captured_market import ReplayExchange, replay


CASE = json.loads((Path(__file__).resolve().parents[1] / 'data/case.json').read_text())


@pytest.mark.parametrize('rnd,reports,complete,reported,allowed', [
    (2, {1, 2}, True, True, False),
    (3, {1, 3}, True, True, False),
    (3, {1, 2, 3}, False, True, False),
    (3, {1, 2, 3}, True, False, False),
    (3, {1, 2, 3}, True, True, True),
])
def test_quotes_require_every_final_report_and_complete_weather(
        monkeypatch, rnd, reports, complete, reported, allowed):
    exchange = ReplayExchange(CASE)
    trader = FinalReportsTrader(final_exact=True)
    trader.on_start(exchange)
    trader.model.round, trader.model.reported_rounds = rnd, reports
    trader.model.outage_history_complete = complete
    trader.model.storm_reported = reported
    calls = []
    monkeypatch.setattr(FairValueTrader, 'on_quotes', lambda self, ex: calls.append(ex))
    trader.on_quotes(exchange)
    assert calls == ([exchange] if allowed else [])


def test_gated_strategy_still_consumes_news_before_it_can_trade():
    exchange = ReplayExchange(CASE)
    trader = FinalReportsTrader(final_exact=True)
    trader.on_start(exchange)
    trader.on_news(exchange, {'type': 'storm_formed', 'round': 1})
    assert trader.model.round == 1
    assert trader.model.storm_active
    assert not trader.model.final_exact_ready


def test_new_competition_resets_final_readiness_before_gating(monkeypatch):
    exchange = ReplayExchange(CASE)
    trader = FinalReportsTrader(final_exact=True)
    trader.on_start(exchange)
    trader.model.round = 3
    trader.model.reported_rounds = {1, 2, 3}
    trader.model.storm_reported = True
    exchange.competition_id = 'next-season'
    calls = []
    monkeypatch.setattr(FairValueTrader, 'on_quotes', lambda self, ex: calls.append(ex))
    trader.on_quotes(exchange)
    assert not calls
    assert trader.competition_id == 'next-season'
    assert not trader.model.final_exact_ready


def test_replay_uses_injected_strategy_without_changing_default():
    class Sentinel(Exception):
        pass

    class SentinelTrader(FairValueTrader):
        def on_start(self, exchange):
            raise Sentinel

    with pytest.raises(Sentinel):
        replay(CASE, [], '1786', {}, .1, .25, 1, False, False,
               strategy_type=SentinelTrader)


def test_summary_retains_losses_zero_trade_and_sacrificed_profit():
    rows = [
        dict(baseline_pnl=100, candidate_pnl=0, candidate_fills=0, candidate_conversions=0),
        dict(baseline_pnl=-5, candidate_pnl=-10, candidate_fills=2, candidate_conversions=0),
        dict(baseline_pnl=5, candidate_pnl=7, candidate_fills=1, candidate_conversions=1),
    ]
    summary = summarize_pairs(rows)
    assert summary['scenarios'] == 3
    assert summary['candidate_mean'] == -1
    assert summary['candidate_losses'] == 1
    assert summary['candidate_worst'] == -10
    assert summary['zero_trade_scenarios'] == 1
    assert summary['mean_pnl_change'] == pytest.approx(-103 / 3)
    assert summary['improved'] == 1
    assert summary['declined'] == 2


def test_summary_rejects_nonfinite_profits():
    with pytest.raises(ValueError, match='finite'):
        summarize_pairs([dict(baseline_pnl=0, candidate_pnl=float('nan'),
                              candidate_fills=0, candidate_conversions=0)])

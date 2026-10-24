import json

import pytest

from ctc.sim import Sim


class BuyOnce:
    def __init__(self, limit=300):
        self.limit = limit
        self.placed = False

    def on_start(self, sim):
        pass

    def on_round(self, sim):
        pass

    def on_news(self, sim, message):
        pass

    def on_quotes(self, sim):
        if not self.placed:
            sim.place('A', 'buy', 1, self.limit)
            self.placed = True

    def on_end(self, sim):
        pass


def simulator(tmp_path, events, latency):
    (tmp_path / 'market.csv').write_text('time,round,A\n')
    (tmp_path / 'feed.jsonl').write_text('')
    (tmp_path / 'settlement.json').write_text(json.dumps({'A': 100}))
    sim = Sim(tmp_path, {'limits': {'A': 10}, 'etfs': {}},
              half_spread=0, latency=latency)
    sim.events = [(t, 0, 'price', {'A': price}) for t, price in events]
    return sim


@pytest.mark.parametrize('latency', [.25, 1., 3.])
def test_orders_activate_at_their_deadline_between_recorded_events(tmp_path, latency):
    sim = simulator(tmp_path, [(0, 100), (2, 200), (4, 200)], latency)
    sim.run(BuyOnce())
    assert len(sim.fills) == 1
    assert sim.fills[0].t == latency
    assert sim.fills[0].price == (100 if latency < 2 else 200)


def test_order_due_before_round_close_executes_before_rollover(tmp_path):
    sim = simulator(tmp_path, [(778, 100), (780, 200)], .25)
    sim.run(BuyOnce())
    assert [(fill.t, fill.price) for fill in sim.fills] == [(778.25, 100)]


def test_late_order_does_not_execute_across_a_round_gap(tmp_path):
    sim = simulator(tmp_path, [(778, 100), (782, 200)], 3)
    sim.run(BuyOnce())
    assert not sim.fills
    assert not sim.pending and not sim.orders


def test_incoming_price_wins_a_timestamp_tie(tmp_path):
    sim = simulator(tmp_path, [(0, 100), (2, 200)], 2)
    sim.run(BuyOnce(limit=150))
    assert not sim.fills


def test_last_round_pending_order_executes_before_final_close(tmp_path):
    sim = simulator(tmp_path, [(2338, 100)], .25)
    sim.run(BuyOnce())
    assert [(fill.t, fill.price) for fill in sim.fills] == [(2338.25, 100)]
    assert sim.t == 2340
    assert not sim.pending and not sim.orders


def test_final_close_wins_an_order_deadline_tie(tmp_path):
    sim = simulator(tmp_path, [(2338, 100)], 2)
    sim.run(BuyOnce())
    assert not sim.fills
    assert not sim.pending and not sim.orders


@pytest.mark.parametrize('terminal_time', [2340, 2342])
def test_terminal_price_cannot_open_a_fourth_round(tmp_path, terminal_time):
    class BuyAfterClose(BuyOnce):
        def on_quotes(self, sim):
            if sim.t >= 2340:
                super().on_quotes(sim)

    sim = simulator(tmp_path, [(2338, 100), (terminal_time, 50)], .25)
    sim.run(BuyAfterClose())
    assert not sim.fills
    assert sim.round == 3
    assert sim.t == 2340
    assert not sim.market_open
    assert sim.pnl() == 0

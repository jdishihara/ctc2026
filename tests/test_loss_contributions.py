import json
from types import SimpleNamespace

from scripts.diagnose_loss_contributions import TraceSim, contributions


def test_trace_keeps_submission_state_and_defers_settlement_use(tmp_path):
    (tmp_path / 'settlement.json').write_text('{"PORT": 110}')
    (tmp_path / 'market.csv').write_text('time,round,PORT\n')
    (tmp_path / 'feed.jsonl').write_text('')
    sim = TraceSim(tmp_path, {'limits': {'PORT': 10}})
    sim.trader = SimpleNamespace(fair={'PORT': 101}, model=SimpleNamespace(
        final_exact_ready=False, round=1, storm_active=True,
        storm_reported=False, last_obs={'age': 30}))
    sim.market_open = True
    sim.t = 90
    sim.place('PORT', 'buy', 2, 100)
    sim.trader.fair['PORT'] = 105
    sim.trader.model.last_obs = {'age': 40}

    class UnavailableSettlement(dict):
        def __getitem__(self, key):
            raise AssertionError('settlement used before diagnostic aggregation')

    sim.settlement = UnavailableSettlement()
    sim.t = 93
    sim._fill(sim.pending[0], 2, 99, False)
    assert sim.detail[0]['fair_at_submission'] == 101
    assert sim.detail[0]['age_at_submission'] == 30
    assert sim.detail[0]['submitted_at'] == 90
    assert sim.detail[0]['filled_at'] == 93
    assert sim.cash == -198
    assert sim.position['PORT'] == 2
    result = contributions(sim.detail, {'PORT': 110}, 22)
    assert result['by_symbol'] == {'PORT': 22}
    assert result['unattributed_residual'] == 0


def test_trade_contributions_include_both_sides_and_report_conversion_residual():
    fills = [dict(symbol='PORT', side='buy', quantity=2, price=100, round=1, phase='storm'),
             dict(symbol='PORT', side='sell', quantity=1, price=105, round=2, phase='between_storms')]
    result = contributions(fills, {'PORT': 110}, 18)
    assert result['by_symbol'] == {'PORT': 15}
    assert result['by_order_round'] == {'1': 20, '2': -5}
    assert result['unattributed_residual'] == 3

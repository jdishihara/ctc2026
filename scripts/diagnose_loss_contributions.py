"""Trace already selected development losses without changing strategy behavior.

Trade cash flows are marked to final settlement after replay. Grouping by order
submission phase is an accounting attribution, not a strategy counterfactual.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ctc.ladder import Ladder
from ctc.sim import Sim
from ctc.strategies import FairValueTrader
from scripts.experiment_execution_costs import PARAMETERS


class TraceSim(Sim):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_details, self.detail = {}, []

    def place(self, symbol, side, quantity, price=None):
        oid = super().place(symbol, side, quantity, price)
        if oid is not None:
            model = self.trader.model
            phase = ('final_reports' if model.final_exact_ready else
                     'before_storm' if model.round < self.round else
                     'storm' if model.storm_active else
                     'between_storms' if model.storm_reported else 'aftermath')
            order = next(o for o in self.pending if o.id == oid)
            self.order_details[oid] = {'order_id': oid, 'submitted_at': self.t,
                'round': self.round, 'phase': phase,
                'fair_at_submission': self.trader.fair.get(symbol),
                'age_at_submission': model.last_obs.get('age') if model.last_obs else None,
                'position_at_submission': self.position[symbol],
                'accepted_quantity': order.qty, 'limit_price': order.price}
        return oid

    def _fill(self, order, quantity, price, passive):
        self.detail.append({**self.order_details[order.id], 'filled_at': self.t,
            'symbol': order.symbol, 'side': order.side, 'quantity': quantity,
            'price': price, 'passive': passive, 'position_before_fill': self.position[order.symbol]})
        super()._fill(order, quantity, price, passive)


def contributions(fills, settlement, pnl):
    symbols, phases, rounds = (collections.defaultdict(float) for _ in range(3))
    marked = []
    for fill in fills:
        sign = 1 if fill['side'] == 'buy' else -1
        value = sign * fill['quantity'] * (settlement[fill['symbol']] - fill['price'])
        symbols[fill['symbol']] += value
        phases[fill['phase']] += value
        rounds[str(fill['round'])] += value
        marked.append({**fill, 'settlement_contribution': value})
    return {'by_symbol': dict(symbols), 'by_order_phase': dict(phases),
            'by_order_round': dict(rounds), 'unattributed_residual': pnl - sum(symbols.values()),
            'fills': marked}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads((args.baseline.parent / 'metadata.json').read_text())
    if (metadata['evaluation'] != 'dev' or metadata['seasons'] != list(range(451, 526))
            or metadata['parameters'] != PARAMETERS or metadata['fraction'] != .1
            or metadata['refill_seconds'] != 10):
        parser.error('the fixed entry-corrected development baseline is required')
    for name, expected in metadata['source_sha256'].items():
        if file_hash(ROOT / name) != expected:
            parser.error(f'baseline source mismatch: {name}')
    rows = [json.loads(line) for line in args.baseline.read_text().splitlines()]
    expected = {(s, p, latency) for s in range(451, 526)
                for p in ('legacy', 'observed_spread', 'observed_touch') for latency in (.25, 1., 3.)}
    keys = {(r['season'], r['profile'], r['latency']) for r in rows}
    if len(rows) != 675 or keys != expected or not all(math.isfinite(r['pnl']) for r in rows):
        parser.error('the complete finite 675-row baseline is required')
    selected = [r for r in rows if r['profile'] == 'observed_touch'
                and r['pnl'] < 0 and r['latency'] in (.25, 3.)]
    case = json.loads((ROOT / 'data/case.json').read_text())
    case['limits'] = {s: max(1, math.floor(n * .1)) for s, n in case['limits'].items()}
    source_files = [*ROOT.glob('ctc/*.py'), *ROOT.glob('ctc/*.json'), *ROOT.glob('ctc/*.npz'),
        ROOT / 'data/case.json', Path(__file__), ROOT / 'scripts/experiment_execution_costs.py']
    run_metadata = {'selection': 'All negative observed-touch development outcomes at .25 and 3 seconds.',
        'selected_scenarios': len(selected), 'seasons': sorted({r['season'] for r in selected}),
        'baseline_sha256': file_hash(args.baseline),
        'baseline_metadata_sha256': file_hash(args.baseline.parent / 'metadata.json'),
        'parameters': PARAMETERS, 'fraction': .1,
        'source_sha256': {str(p.relative_to(ROOT)): file_hash(p) for p in source_files},
        'history_sha256': {f'season-{s:03d}/{name}': file_hash(ROOT / 'data/history' / f'season-{s:03d}' / name)
            for s in sorted({r['season'] for r in selected})
            for name in ('feed.jsonl', 'market.csv', 'settlement.json')},
        'limitations': [
            'Selected losing outcomes cannot estimate overall strategy performance.',
            'Attribution to order-submission phases does not measure removing those phases.',
            'Trade contributions include entries, reductions, basket legs, and partial fills.',
            'A model fair logged alongside an order is not necessarily the pricing rule for a basket leg.',
            'Unattributed residual is reported separately; cash-neutral conversions can redistribute symbol exposure.',
            'All development seasons have been repeatedly examined; this is not an untouched holdout.']}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'metadata.json').write_text(json.dumps(run_metadata, indent=2) + '\n')
    summaries = []
    with (args.out / 'traces.jsonl').open('x') as output:
        for expected_row in selected:
            season, latency = expected_row['season'], expected_row['latency']
            sim = TraceSim(ROOT / 'data/history' / f'season-{season:03d}', copy.deepcopy(case),
                half_spread=.0015, latency=latency, rate_limit=90,
                ladder=Ladder(refill_secs=10, scale=1, table=copy.deepcopy(metadata['profiles']['observed_touch'])))
            sim.trader = FairValueTrader(**PARAMETERS)
            pnl = sim.run(sim.trader)
            if (not math.isclose(pnl, expected_row['pnl'], abs_tol=1e-8, rel_tol=0)
                    or len(sim.fills) != expected_row['fills'] or sim.rejected != expected_row['rejected']
                    or {str(k): v for k, v in sim.round_pnl.items()} != expected_row['round_pnl']):
                raise ValueError(f'tracing changed or failed to reproduce baseline: {season}/{latency}')
            result = {'season': season, 'latency': latency, 'pnl': pnl,
                'fill_count': len(sim.fills), 'rejected': sim.rejected, 'round_pnl': sim.round_pnl,
                **contributions(sim.detail, sim.settlement, pnl)}
            output.write(json.dumps(result) + '\n')
            output.flush()
            summaries.append({k: v for k, v in result.items() if k != 'fills'})
            print(json.dumps({'season': season, 'latency': latency, 'pnl': pnl}), flush=True)
    (args.out / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')


if __name__ == '__main__':
    main()

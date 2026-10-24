"""Offline candidate enforcing the existing storm-uncertainty rule on targets.

Not imported by the live launcher. Parameters and the frozen worker are unchanged.
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
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ctc.strategies import FairValueTrader
from ctc.ladder import Ladder
from scripts.evaluate_observed_season import observed_capture
from scripts.experiment_execution_costs import PARAMETERS, calibrated_profiles
from scripts.experiment_final_reports import ResearchSim, historical_baseline, summarize_pairs
from scripts.replay_captured_market import completed_capture, replay


def uncertain(trader):
    posterior = trader.model.posterior
    entropy = -sum(p * math.log(p) for p in posterior.values() if p > 0) if posterior else 0.
    return trader.ent_cut > 0 and trader.model.storm_active and entropy > trader.ent_cut


class AuditedTrader(FairValueTrader):
    """Inspect accepted passive orders without changing their execution."""
    def on_start(self, sim):
        super().on_start(sim)
        self.uncertain_passive_orders = 0
        self.uncertain_passive_added_shares = 0
        self.uncertain_passive_by_symbol = collections.Counter()

    def quote_passive(self, sim, symbol, *args, **kwargs):
        first_id = sim.next_id
        active = uncertain(self)
        super().quote_passive(sim, symbol, *args, **kwargs)
        if active:
            for order in sim.pending:
                if order.id < first_id:
                    continue
                capacity = max(-sim.position[symbol], 0) if order.side == 'buy' else max(sim.position[symbol], 0)
                added = max(0, order.qty - order.filled - capacity)
                if added:
                    self.uncertain_passive_orders += 1
                    self.uncertain_passive_added_shares += added
                    self.uncertain_passive_by_symbol[symbol] += 1


class UncertaintyGuardTrader(AuditedTrader):
    """Allow only fundamental reductions while the existing entropy gate is active."""
    def on_start(self, sim):
        super().on_start(sim)
        self.uncertainty_cancel_t = {}

    @staticmethod
    def working_orders_add_risk(sim, symbol):
        orders = sim.working_orders(symbol)
        position = sim.position[symbol]
        return any(sum(o['remaining'] for o in orders if o['side'] == side) > capacity
                   for side, capacity in (('buy', max(-position, 0)), ('sell', max(position, 0))))

    def on_quotes(self, sim):
        if not self._same_competition(sim):
            return
        # Use the latest computed posterior. Check working fundamental orders
        # before basket/throttle/warm-up returns, without cancelling basket
        # hedges: a basket cancels its symbols before starting its target set.
        if uncertain(self) and getattr(sim, 'state_ready', True):
            hedge_symbols = set(self.basket.targets or ()) if self.basket is not None else set()
            for symbol in self.symbols:
                if symbol in hedge_symbols or not self.working_orders_add_risk(sim, symbol):
                    continue
                if sim.t - self.uncertainty_cancel_t.get(symbol, -math.inf) < 1:
                    return
                self.uncertainty_cancel_t[symbol] = sim.t
                cancelled = sim.cancel_all(symbol)
                if not self._same_competition(sim) or not getattr(sim, 'state_ready', True):
                    return
                if not cancelled:
                    return
                self.passive_order.pop(symbol, None)
        super().on_quotes(sim)

    def price_target(self, sim, symbol, target, position):
        target = super().price_target(sim, symbol, target, position)
        if not uncertain(self):
            return target
        if target * position <= 0:
            return 0
        return min(target, position) if position > 0 else max(target, position)

    def stale_risk_orders(self, sim, symbol, fair, confidence, floor):
        if uncertain(self) and self.working_orders_add_risk(sim, symbol):
            return True
        return super().stale_risk_orders(sim, symbol, fair, confidence, floor)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(trader):
    return {'uncertain_passive_orders': trader.uncertain_passive_orders,
            'uncertain_passive_added_shares': trader.uncertain_passive_added_shares,
            'uncertain_passive_by_symbol': dict(trader.uncertain_passive_by_symbol)}


def reference_capture(path, cid, frames):
    if path.suffix == '.jsonl':
        metadata = json.loads(path.with_name(path.name.replace('results.jsonl', 'metadata.json')).read_text())
        if (metadata['source_competition_id'] != cid
                or metadata['frames_sha256'] != hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest()):
            raise ValueError('captured baseline identity or frame hash mismatch')
        rows = [row for line in path.read_text().splitlines()
                if (row := json.loads(line)).get('strategy') == 'full']
    else:
        data = json.loads(path.read_text())
        if data['competition_id'] != cid:
            raise ValueError('captured baseline identity mismatch')
        rows = data['results']
    selected = {}
    for row in rows:
        if row['reset_warmup_each_snapshot']:
            continue
        key = row['latency_seconds'], row['displayed_depth_fraction'], row['basket_enabled']
        if key in selected:
            raise ValueError('duplicate captured baseline scenario')
        selected[key] = {k: v for k, v in row.items() if k != 'strategy'}
    if set(selected) != {(latency, depth, basket) for latency in (.25, 1., 3.)
                         for depth in (1., .5) for basket in (False, True)}:
        raise ValueError('all twelve current-snapshot baseline scenarios required')
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('dev', 'completed', 'observed'), required=True)
    parser.add_argument('--batch', type=Path)
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--competition-id', required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'observed' and args.observations is None:
        parser.error('--observations is required for observed mode')
    if args.mode != 'observed' and args.batch is None:
        parser.error('--batch is required for completed/dev mode')
    case = json.loads((ROOT / 'data/case.json').read_text())
    if args.mode == 'observed':
        receipt, frames, coverage = observed_capture(args.observations, args.feed, args.competition_id, case['limits'])
        year = receipt['year']
    else:
        _, trial, receipt, frames, count = completed_capture(args.batch, args.feed, args.competition_id, case['limits'])
        if receipt.get('clock', {}).get('state') != 'ready':
            raise ValueError('confirmed ready closed receipt required')
        year, coverage = trial['year'], {'news_count': count, 'quote_path_completeness_proven': False}
    profiles = None
    if args.mode == 'dev':
        profiles, calibration = calibrated_profiles(frames, json.loads((ROOT / 'ctc/ladder.json').read_text()))
        baseline = historical_baseline(args.baseline, profiles, args.competition_id)
    else:
        baseline = reference_capture(args.baseline, args.competition_id, frames)
    sources = [*ROOT.glob('ctc/*.py'), *ROOT.glob('ctc/*.json'), *ROOT.glob('ctc/*.npz'),
               ROOT / 'data/case.json', ROOT / 'bot/live.py', ROOT / 'bot/http_transport.py', Path(__file__),
               ROOT / 'scripts/experiment_final_reports.py', ROOT / 'scripts/experiment_execution_costs.py',
               ROOT / 'scripts/replay_captured_market.py', ROOT / 'scripts/evaluate_observed_season.py',
               ROOT / 'scripts/observe_market_seasons.py',
               ROOT / 'docs/uncertainty-guard-plan.md']
    metadata = {'mode': args.mode, 'source_competition_id': args.competition_id, 'year': year,
        'official_receipt': receipt, 'coverage': coverage, 'parameters': PARAMETERS,
        'fraction': .1, 'latencies': [.25, 1., 3.], 'frame_count': len(frames),
        'first_at': frames[0]['received_at'], 'last_at': frames[-1]['received_at'],
        'frames_sha256': hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest(),
        'baseline_sha256': digest(args.baseline),
        'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources},
        'limitations': ['Offline virtual fills do not establish actual account profit.',
            'Development and previously viewed captures are reused data, not untouched holdouts.',
            'The audit counts accepted passive risk additions, not every forecast error or later fill.',
            'The candidate also caps fundamental reversals and cancels risk-increasing working orders.',
            'Basket execution and its model-free hedges are outside this uncertainty gate.',
            'No parameter selection or live activation occurs in this script.']}
    if profiles is not None:
        metadata.update(seasons=list(range(451, 526)), profile='observed_touch', profile_table=profiles['observed_touch'],
            calibration=calibration, baseline_metadata_sha256=digest(args.baseline.parent / 'metadata.json'),
            history_sha256={f'season-{s:03d}/{name}': digest(ROOT / 'data/history' / f'season-{s:03d}' / name)
                for s in range(451, 526) for name in ('feed.jsonl', 'market.csv', 'settlement.json')})
    else:
        metadata.update(depth_fractions=[1., .5], basket_enabled=[False, True], reset_warmup_each_snapshot=False)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    pairs, runs, started = [], 0, time.monotonic()
    with (args.out / 'results.jsonl').open('x') as output:
        for key, expected in sorted(baseline.items()):
            results = {}
            for variant, strategy in (('baseline', AuditedTrader), ('candidate', UncertaintyGuardTrader)):
                if profiles is not None:
                    season, latency = key
                    bounded_case = copy.deepcopy(case)
                    bounded_case['limits'] = {s: max(1, math.floor(n * .1)) for s, n in case['limits'].items()}
                    sim = ResearchSim(ROOT / 'data/history' / f'season-{season:03d}', bounded_case,
                        half_spread=.0015, latency=latency, rate_limit=90,
                        ladder=Ladder(refill_secs=10, scale=1, table=copy.deepcopy(profiles['observed_touch'])))
                    trader = strategy(**PARAMETERS)
                    pnl = sim.run(trader)
                    row = {'season': season, 'latency_seconds': latency, 'simulated_settlement_pnl': pnl,
                           'fills': len(sim.fills), 'conversions': sim.conversions, 'rejected': sim.rejected,
                           'round_pnl': {str(k): v for k, v in sim.round_pnl.items()}}
                    if variant == 'baseline' and (pnl != expected['pnl'] or len(sim.fills) != expected['fills']
                            or sim.rejected != expected['rejected'] or row['round_pnl'] != expected['round_pnl']):
                        raise ValueError(f'audit changed historical baseline: {key}')
                else:
                    latency, depth, basket = key
                    holder = []
                    def construct(**kwargs):
                        trader = strategy(**kwargs)
                        holder.append(trader)
                        return trader
                    row = replay(case, frames, year, receipt['prices'], .1, latency, depth, basket, False,
                                 strategy_type=construct)
                    trader = holder[0]
                    if variant == 'baseline' and row != expected:
                        raise ValueError(f'audit changed captured baseline: {key}')
                if variant == 'candidate' and trader.uncertain_passive_orders:
                    raise ValueError(f'candidate accepted uncertain passive risk: {key}')
                row.update(audit= audit(trader))
                results[variant] = row
                output.write(json.dumps({'strategy': variant, **row}) + '\n')
                output.flush()
                runs += 1
            before, after = results['baseline'], results['candidate']
            pair = {k: before[k] for k in ('season', 'latency_seconds', 'displayed_depth_fraction', 'basket_enabled') if k in before}
            pair.update(baseline_pnl=before['simulated_settlement_pnl'], candidate_pnl=after['simulated_settlement_pnl'],
                        candidate_fills=after['fills'], candidate_conversions=after['conversions'],
                        baseline_audit=before['audit'], candidate_audit=after['audit'])
            summarize_pairs([pair])
            pairs.append(pair)
            print(json.dumps({'runs': runs, 'scenario': key}), flush=True)
    for name, expected in metadata['source_sha256'].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f'source changed during experiment: {name}')
    grouped = collections.defaultdict(list)
    for pair in pairs:
        grouped[pair['latency_seconds']].append(pair)
    summary = {'runs': runs, 'elapsed_seconds': time.monotonic() - started, 'overall': summarize_pairs(pairs),
        'by_latency': {str(latency): summarize_pairs(rows) for latency, rows in grouped.items()},
        'baseline_uncertain_passive_orders': sum(r['baseline_audit']['uncertain_passive_orders'] for r in pairs),
        'candidate_uncertain_passive_orders': sum(r['candidate_audit']['uncertain_passive_orders'] for r in pairs)}
    (args.out / 'pairs.json').write_text(json.dumps(pairs, indent=2) + '\n')
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()

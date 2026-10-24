"""Offline diagnostic: wait for all three final reports before quote-driven trading.

The eligibility flag requires complete recorded weather. It does not establish
that every settlement estimate is exact. This is not a live strategy setting.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ctc.ladder import Ladder
from ctc.sim import Sim
from ctc.strategies import FairValueTrader
from scripts.evaluate_observed_season import observed_capture
from scripts.experiment_execution_costs import PARAMETERS, calibrated_profiles
from scripts.replay_captured_market import completed_capture, replay


class FinalReportsTrader(FairValueTrader):
    def on_quotes(self, sim):
        if not self._same_competition(sim):
            return
        if self.model.final_exact_ready:
            super().on_quotes(sim)


class ResearchSim(Sim):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conversions = 0

    def _etf(self, etf, qty, sign):
        accepted = super()._etf(etf, qty, sign)
        self.conversions += int(accepted)
        return accepted


def summarize_pairs(rows):
    if not rows or not all(math.isfinite(r[k]) for r in rows
                           for k in ('baseline_pnl', 'candidate_pnl')):
        raise ValueError('nonempty finite paired profits required')
    baseline = [r['baseline_pnl'] for r in rows]
    candidate = [r['candidate_pnl'] for r in rows]
    delta = [b - a for a, b in zip(baseline, candidate)]
    return {'scenarios': len(rows), 'baseline_mean': statistics.mean(baseline),
        'candidate_mean': statistics.mean(candidate),
        'baseline_losses': sum(x < 0 for x in baseline),
        'candidate_losses': sum(x < 0 for x in candidate),
        'baseline_worst': min(baseline), 'candidate_worst': min(candidate),
        'candidate_best': max(candidate), 'mean_pnl_change': statistics.mean(delta),
        'improved': sum(x > 1e-8 for x in delta),
        'declined': sum(x < -1e-8 for x in delta),
        'zero_trade_scenarios': sum(r['candidate_fills'] == 0
                                    and r['candidate_conversions'] == 0 for r in rows)}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def historical_baseline(path, profiles, source_cid):
    metadata = json.loads((path.parent / 'metadata.json').read_text())
    if (metadata['evaluation'] != 'dev' or metadata['seasons'] != list(range(451, 526))
            or metadata['source_competition_id'] != source_cid
            or metadata['parameters'] != PARAMETERS or metadata['fraction'] != .1
            or metadata['latencies'] != [.25, 1., 3.]
            or metadata['refill_seconds'] != 10 or metadata['profiles'] != profiles):
        raise ValueError('baseline must use the identical development scenario grid')
    for name, expected in metadata['source_sha256'].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f'baseline source mismatch: {name}')
    selected = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row['profile'] != 'observed_touch':
            continue
        key = row['season'], row['latency']
        if key in selected or not math.isfinite(row['pnl']):
            raise ValueError('duplicate or nonfinite baseline result')
        selected[key] = row
    expected = {(s, latency) for s in range(451, 526) for latency in (.25, 1., 3.)}
    if set(selected) != expected:
        raise ValueError('all 225 paired baseline scenarios required')
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('dev', 'completed', 'observed'), required=True)
    parser.add_argument('--batch', type=Path)
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--competition-id', required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'observed' and args.observations is None:
        parser.error('--observations is required for observed mode')
    if args.mode != 'observed' and args.batch is None:
        parser.error('--batch is required for completed/dev mode')
    if args.mode == 'dev' and args.baseline is None:
        parser.error('--baseline is required for dev mode')
    case = json.loads((ROOT / 'data/case.json').read_text())
    if args.mode == 'observed':
        receipt, frames, coverage = observed_capture(args.observations, args.feed,
                                                     args.competition_id, case['limits'])
        year = receipt['year']
    else:
        _, trial, receipt, frames, news_count = completed_capture(
            args.batch, args.feed, args.competition_id, case['limits'])
        year = trial['year']
        coverage = {'news_count': news_count,
                    'quote_path_completeness_proven': False}
    profiles, baseline = None, None
    if args.mode == 'dev':
        if receipt['clock'].get('state') != 'ready':
            parser.error('calibration source must have a ready settlement receipt')
        original = json.loads((ROOT / 'ctc/ladder.json').read_text())
        profiles, calibration = calibrated_profiles(frames, original)
        baseline = historical_baseline(args.baseline, profiles, args.competition_id)
    source_files = [*ROOT.glob('ctc/*.py'), *ROOT.glob('ctc/*.json'), *ROOT.glob('ctc/*.npz'),
        ROOT / 'data/case.json', ROOT / 'bot/live.py', Path(__file__),
        ROOT / 'scripts/replay_captured_market.py', ROOT / 'scripts/evaluate_observed_season.py',
        ROOT / 'scripts/experiment_execution_costs.py']
    metadata = {'mode': args.mode, 'source_competition_id': args.competition_id,
        'year': year, 'official_receipt': receipt, 'coverage': coverage,
        'frame_count': len(frames), 'first_at': frames[0]['received_at'],
        'last_at': frames[-1]['received_at'],
        'frames_sha256': hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest(),
        'parameters': PARAMETERS, 'fraction': .1, 'latencies': [.25, 1., 3.],
        'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in source_files},
        'limitations': [
            'Offline counterfactual fills are not actual account profits.',
            'Development seasons and older captured markets have already been examined.',
            'Final reports reduce uncertainty but do not make all modeled prices exact.',
            'No live promotion is implied; all predeclared scenarios are retained.',
            'This is a strategy counterfactual, not an attribution of existing trade profits.']}
    if baseline is not None:
        metadata.update(seasons=list(range(451, 526)), profile='observed_touch',
            profile_table=profiles['observed_touch'], calibration=calibration,
            baseline_sha256=digest(args.baseline),
            baseline_metadata_sha256=digest(args.baseline.parent / 'metadata.json'))
    else:
        metadata.update(depth_fractions=[1., .5], basket_enabled=[False, True],
                        reset_warmup_each_snapshot=False)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    pairs, started, runs = [], time.monotonic(), 0
    with (args.out / 'results.jsonl').open('x') as output:
        if baseline is not None:
            case['limits'] = {s: max(1, math.floor(n * .1)) for s, n in case['limits'].items()}
            for season in range(451, 526):
                for latency in (.25, 1., 3.):
                    sim = ResearchSim(ROOT / 'data/history' / f'season-{season:03d}',
                        copy.deepcopy(case), half_spread=.0015, latency=latency,
                        rate_limit=90, ladder=Ladder(refill_secs=10, scale=1,
                            table=copy.deepcopy(profiles['observed_touch'])))
                    trader = FinalReportsTrader(**PARAMETERS)
                    pnl = sim.run(trader)
                    pair = {'season': season, 'latency_seconds': latency,
                        'baseline_pnl': baseline[season, latency]['pnl'], 'candidate_pnl': pnl,
                        'candidate_fills': len(sim.fills),
                        'candidate_conversions': sim.conversions,
                        'rate_rejections': sim.rejected, 'round_pnl': sim.round_pnl}
                    summarize_pairs([pair])
                    output.write(json.dumps(pair) + '\n')
                    output.flush()
                    pairs.append(pair)
                    runs += 1
                print(json.dumps({'season_finished': season, 'runs': runs}), flush=True)
        else:
            for latency in (.25, 1., 3.):
                for depth in (1., .5):
                    for basket in (False, True):
                        results = {}
                        for variant, strategy in (('full', FairValueTrader), ('final_reports', FinalReportsTrader)):
                            row = replay(case, frames, year, receipt['prices'], .1, latency,
                                depth, basket, False, strategy_type=strategy)
                            results[variant] = row
                            output.write(json.dumps({'strategy': variant, **row}) + '\n')
                            output.flush()
                            runs += 1
                        before, after = results['full'], results['final_reports']
                        pairs.append({'latency_seconds': latency, 'displayed_depth_fraction': depth,
                            'basket_enabled': basket, 'baseline_pnl': before['simulated_settlement_pnl'],
                            'candidate_pnl': after['simulated_settlement_pnl'],
                            'candidate_fills': after['fills'], 'candidate_conversions': after['conversions']})
                        print(json.dumps({'runs': runs, 'last_pair': pairs[-1]}), flush=True)
    grouped = collections.defaultdict(list)
    for pair in pairs:
        grouped[pair['latency_seconds']].append(pair)
    summary = {'runs': runs, 'elapsed_seconds': time.monotonic() - started,
        'overall': summarize_pairs(pairs),
        'by_latency': {str(latency): summarize_pairs(rows) for latency, rows in grouped.items()}}
    (args.out / 'pairs.json').write_text(json.dumps(pairs, indent=2) + '\n')
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()

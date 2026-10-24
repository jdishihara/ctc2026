"""Fixed-strategy historical cost stress, calibrated only from a completed capture.

No network or trading access. This does not replace historical price paths with
live ones, select new strategy parameters, or establish live profitability.
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
from scripts.replay_captured_market import completed_capture

PARAMETERS = dict(analog=True, min_edge=.025, edge_full=.03, sd_mult=.7,
    sigma=15, k=100, passive=.75, warmup=20, max_cross=.02, carry=.5, ent_cut=1.2,
    cone_w=1, cone_s0=20, cone_nu=0, isl_w=0, final_exact=True, final_edge=.005,
    final_edge_full=.005, basket_edge=.01, basket_participation=.5, announce_wait=60)


def calibrated_profiles(frames, original):
    samples = {symbol: [] for symbol in original}
    for frame in frames:
        symbol = frame.get('symbol')
        if frame.get('type') != 'quote' or symbol not in samples:
            continue
        bid, ask, bs, az = (frame.get(k) for k in ('bid', 'ask', 'bid_size', 'ask_size'))
        if (not all(type(x) in (int, float) and math.isfinite(x) for x in (bid, ask, bs, az))
                or not 0 < bid <= ask or min(bs, az) < 0):
            continue
        samples[symbol].append(((ask - bid) / ((ask + bid) / 2), bs, az))
    widened, touch, calibration = copy.deepcopy(original), {}, {}
    for symbol, values in samples.items():
        if not values:
            raise ValueError(f'no usable captured quotes for {symbol}')
        spread, bid, ask = (statistics.median(row[i] for row in values) for i in range(3))
        effective = max(original[symbol]['spread'], spread)
        delta = (effective - original[symbol]['spread']) / 2
        widened[symbol]['spread'] = effective
        widened[symbol]['bands'] = [band + delta for band in original[symbol]['bands']]
        touch[symbol] = {'spread': effective, 'bands': [effective / 2],
                         'bid': [math.floor(bid)], 'ask': [math.floor(ask)]}
        calibration[symbol] = {'usable_quotes': len(values), 'median_spread': spread,
            'effective_spread': effective, 'median_bid_size': bid, 'median_ask_size': ask}
    return {'legacy': copy.deepcopy(original), 'observed_spread': widened,
            'observed_touch': touch}, calibration


def summaries(rows):
    groups = collections.defaultdict(list)
    for row in rows:
        groups[(row['profile'], row['latency'])].append(row['pnl'])
    return [{'profile': profile, 'latency': latency, 'seasons': len(values),
             'mean': statistics.mean(values), 'median': statistics.median(values),
             'losing_seasons': sum(value < 0 for value in values),
             'worst': min(values), 'best': max(values)}
            for (profile, latency), values in groups.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--competition-id', required=True)
    parser.add_argument('--evaluation', choices=('completed', 'dev'), default='completed')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    case = json.loads((ROOT / 'data/case.json').read_text())
    _, trial, receipt, frames, _ = completed_capture(args.batch, args.feed,
                                                   args.competition_id, case['limits'])
    year = trial.get('year')
    if (receipt['clock'].get('state') != 'ready' or not isinstance(year, str)
            or len(year) != 4 or not year.isascii() or not year.isdigit()
            or not 1 <= 2027 - int(year) <= 600):
        parser.error('a verified closed source season with valid historical identity is required')
    source_season = 2027 - int(year)
    seasons = [source_season] if args.evaluation == 'completed' else list(range(451, 526))
    original = json.loads((ROOT / 'ctc/ladder.json').read_text())
    if set(original) != set(case['limits']):
        parser.error('ladder symbols must match the case')
    profiles, calibration = calibrated_profiles(frames, original)
    case['limits'] = {s: max(1, math.floor(n * .1)) for s, n in case['limits'].items()}
    args.out.mkdir(parents=True, exist_ok=False)
    metadata = {'source_competition_id': args.competition_id, 'source_season': source_season,
        'evaluation': args.evaluation, 'seasons': seasons, 'fraction': .1,
        'latencies': [.25, 1., 3.], 'refill_seconds': 10, 'parameters': PARAMETERS,
        'profiles': profiles, 'calibration': calibration,
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ('scripts/experiment_execution_costs.py', 'ctc/strategies.py',
                         'ctc/sim.py', 'ctc/ladder.py', 'ctc/ladder.json', 'data/case.json')},
        'limitations': ['Quote-update-weighted calibration from one completed season.',
            'Historical prices and news remain; this does not reconstruct the live market.',
            'Static spread and linear liquidity refill omit time-varying costs and queue competition.',
            'All scenarios retained; no live parameter selection or account profit attribution.']}
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    rows, started = [], time.time()
    with (args.out / 'results.jsonl').open('x') as output:
        for season in seasons:
            folder = ROOT / 'data/history' / f'season-{season:03d}'
            for profile, table in profiles.items():
                for latency in (.25, 1., 3.):
                    sim = Sim(folder, copy.deepcopy(case), half_spread=.0015,
                        latency=latency, rate_limit=90,
                        ladder=Ladder(refill_secs=10, scale=1, table=copy.deepcopy(table)))
                    pnl = sim.run(FairValueTrader(**PARAMETERS))
                    row = {'season': season, 'profile': profile, 'latency': latency,
                           'pnl': pnl, 'fills': len(sim.fills), 'rejected': sim.rejected,
                           'round_pnl': sim.round_pnl}
                    if not math.isfinite(pnl):
                        raise ValueError('nonfinite diagnostic P&L')
                    output.write(json.dumps(row) + '\n')
                    output.flush()
                    rows.append(row)
            print(json.dumps({'season_finished': season, 'completed_runs': len(rows),
                              'elapsed_seconds': time.time() - started}), flush=True)
    result = {'elapsed_seconds': time.time() - started, 'results': summaries(rows)}
    (args.out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

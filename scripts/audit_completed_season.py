"""Compare a completed live season with its historical replay at the same limits.

This is an execution/feed diagnostic, not an estimate of live counterfactual P&L.
No network requests are made. Trial completion and season identity are checked
before reading historical feeds or outcomes.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ctc.ladder import Ladder
from ctc.sim import Sim
from ctc.strategies import FairValueTrader


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--batch', type=Path, required=True)
    ap.add_argument('--feed', type=Path, required=True)
    ap.add_argument('--competition-id', required=True)
    ap.add_argument('--season', type=int, required=True)
    args = ap.parse_args()
    status = json.loads((args.batch / 'status.json').read_text())
    trial = status.get('trials', {}).get(args.competition_id, {})
    if not trial.get('completed'):
        ap.error('A verified completed trial is required before reading historical outcomes')
    year = trial.get('year')
    if not isinstance(year, str) or len(year) != 4 or not year.isascii() or not year.isdigit():
        ap.error('The completed trial has no valid fictional year')
    # The testnet mapping is documented in README.md. Bind the request before
    # opening even the manifest, which contains historical outcome metadata.
    if args.season != 2027 - int(year):
        ap.error('--season does not match the completed trial fictional year')
    receipt = next((row for line in (args.batch / 'actions.jsonl').open()
                    if (row := json.loads(line)).get('kind') == 'settlement'
                    and row.get('competition_id') == args.competition_id), None)
    if receipt is None:
        ap.error('The completed trial has no settlement receipt')
    clock = receipt.get('clock')
    if (not isinstance(clock, dict)
            or not str(clock.get('fictional_time') or '').startswith(year + '-')):
        ap.error('The settlement receipt fictional year does not match the completed trial')

    captured = {}
    started = False
    for line in args.feed.open():
        frame = json.loads(line)
        received = frame.get('received_at')
        if received is None or received < trial['started_at'] - 120:
            continue
        if received > trial['completed_at']:
            break
        message = frame.get('message', {}) if frame.get('type') == 'news' else {}
        if not (message.get('time') or '').startswith(trial['year']) or 'seq' not in message:
            continue
        if message['seq'] == 0:
            started = True
        if started:
            captured[message['seq']] = message

    manifest = json.loads((ROOT / 'data/history/manifest.json').read_text())
    if not 1 <= args.season <= len(manifest['seasons']):
        ap.error('--season is outside the historical manifest')
    folder = ROOT / 'data/history' / manifest['seasons'][args.season - 1]['dir']
    historical = {m['seq']: m for line in (folder / 'feed.jsonl').open()
                  if 'seq' in (m := json.loads(line))}
    if historical.keys() != captured.keys():
        ap.error('Historical and captured sequence coverage differs')
    differences = [{'seq': seq, 'type': captured[seq]['type'],
                    'fields': sorted(k for k in historical[seq].keys() | captured[seq].keys()
                                     if historical[seq].get(k) != captured[seq].get(k))}
                   for seq in sorted(historical) if historical[seq] != captured[seq]]
    if any(d['type'] != 'advisory' for d in differences):
        ap.error('Non-advisory news differs; verify the historical season match')
    published_settlement = json.loads((folder / 'settlement.json').read_text())
    case = json.loads((ROOT / 'data/case.json').read_text())
    fraction = status['fraction']
    case['limits'] = {s: max(1, int(n * fraction)) for s, n in case['limits'].items()}
    results = []
    scenarios = [(news, basket, False) for news in ('published', 'captured') for basket in (.01, 0)]
    scenarios.append(('captured', 0, True))
    for news, basket, history_gate in scenarios:
        sim = Sim(folder, copy.deepcopy(case), half_spread=.0015, latency=.25,
                  rate_limit=90, ladder=Ladder(refill_secs=10, scale=1))
        if news == 'captured':
            sim.events = [(t, priority, kind, captured[payload['seq']] if kind == 'news' else payload)
                          for t, priority, kind, payload in sim.events]
        strat = FairValueTrader(
            analog=True, min_edge=.025, edge_full=.03, sd_mult=.7, sigma=15, k=100,
            passive=.75, warmup=20, max_cross=.02, carry=.5, ent_cut=1.2,
            cone_w=1, cone_s0=20, cone_nu=0, isl_w=0, final_exact=True,
            final_edge=.005, final_edge_full=.005, basket_edge=basket,
            basket_participation=.5, announce_wait=60)
        if history_gate:
            original = strat.on_quotes
            strat.on_quotes = lambda ex: original(ex) if strat.model.live_history_ready else None
        pnl = sim.run(strat)
        results.append({'news': news, 'basket_enabled': bool(basket), 'pnl': pnl,
                        'history_gate': history_gate,
                        'fills': len(sim.fills), 'round_pnl': sim.round_pnl,
                        'basket_cycles': strat.basket.cycles if strat.basket else 0,
                        'rejected': sim.rejected})
    report = {
        'competition_id': args.competition_id, 'season': args.season,
        'limits_fraction': fraction, 'live_settlement_pnl': receipt['pnl'],
        'live_order_count': trial['order_count'], 'live_attempt_count': trial['attempt_count'],
        'lowest_observed_cumulative_pnl': trial['worst_pnl'],
        'news_count': len(historical), 'news_differences': differences,
        'max_settlement_difference': max(abs(v - receipt['prices'][s])
                                         for s, v in published_settlement.items()),
        'replays': results,
        'interpretation': 'All replays use historical market prices, static ladder liquidity, '
                          'and 0.25-second order latency. They do not recreate live quotes, '
                          'queue position, HTTP delays, or periodic snapshot processing. '
                          'Basket-disabled runs are diagnostic ablations, not a strategy selection.',
    }
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

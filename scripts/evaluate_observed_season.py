"""Offline, fixed-parameter replay of an officially closed observed season.

This consumes public-market recordings and makes no account-profit claim. It
has no network client, key access, order submission, or historical-outcome read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.observe_market_seasons import official_receipt
from scripts.replay_captured_market import replay


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def observed_capture(observations, feed, cid, symbols):
    receipts = []
    for line in Path(observations).open():
        if not line.endswith('\n'):
            break
        row = json.loads(line)
        if row.get('kind') == 'settlement' and row.get('competition_id') == cid:
            receipts.append(row)
    if len(receipts) != 1:
        raise ValueError('exactly one official observed settlement receipt required')
    receipt = receipts[0]
    prices, info = receipt.get('prices'), receipt.get('coverage')
    at = receipt.get('at')
    if (receipt.get('source') != 'read_only_market_observer' or not isinstance(prices, dict)
            or not isinstance(info, dict) or not number(at)):
        raise ValueError('invalid official observed settlement receipt')
    rows = [{'symbol': symbol, 'settlement_price': price, 'settlement_active': True}
            for symbol, price in prices.items()]
    validated = official_receipt(receipt.get('clock', {}), rows,
                                 receipt.get('end_clock', {}), info, symbols)
    if (validated is None or validated['year'] != receipt.get('year')
            or validated['competition_id'] != cid
            or not number(info.get('first_at')) or not number(info.get('last_at'))
            or not 0 < info['first_at'] <= info['last_at'] <= at):
        raise ValueError('matching complete closed receipt required before reading capture')

    year = receipt['year']
    frames, sequences, finals, pre_storm = [], {}, set(), set()
    quote_times = {str(r): {s: [] for s in symbols} for r in (1, 2, 3)}
    windows, last_at, advertised = {}, -math.inf, -1
    active, rnd, phase = False, None, None
    unusable, disconnects = 0, 0
    subscriptions = []
    for line in Path(feed).open():
        if not line.endswith('\n'):
            break
        frame = json.loads(line)
        timestamp = frame.get('received_at')
        if not number(timestamp):
            raise ValueError('finite recorded receive timestamps required')
        if timestamp < last_at:
            raise ValueError('capture receive time moved backwards')
        previous_at, last_at = last_at, timestamp
        if timestamp < info['first_at']:
            continue
        if timestamp > at:
            break
        kind = frame.get('type')
        if kind == 'news':
            message = frame.get('message', {})
            if not isinstance(message, dict):
                raise ValueError('invalid captured news')
            matching = str(message.get('time', '')).startswith(year + '-')
            if active and not matching:
                raise ValueError('season changed before its official receipt')
            active = matching
            if not active:
                continue
            if not frames and (timestamp != info['first_at']
                    or message.get('type') != 'snapshot' or message.get('round') != 1
                    or message.get('phase') != 'pre_storm' or message.get('last_seq') != -1):
                raise ValueError('capture must start before round-one news and trading')
            next_round = message.get('round', rnd)
            if next_round not in (1, 2, 3) or type(next_round) is not int:
                raise ValueError('invalid recorded round')
            if rnd is not None and next_round != rnd and next_round != rnd + 1:
                raise ValueError('capture skipped or reversed a round')
            rnd = next_round
            window = windows.setdefault(str(rnd), {'first_at': timestamp, 'closed_at': None})
            if message.get('type') == 'snapshot':
                phase = message.get('phase')
                checkpoint = message.get('last_seq')
                if type(checkpoint) is not int or checkpoint < -1:
                    raise ValueError('invalid advertised news sequence')
                advertised = max(advertised, checkpoint)
                if phase == 'pre_storm':
                    pre_storm.add(rnd)
                if phase == 'closed' and window['closed_at'] is None:
                    window['closed_at'] = timestamp
            if 'seq' in message:
                seq = message['seq']
                if type(seq) is not int or seq < 0:
                    raise ValueError('invalid captured news sequence')
                digest = hashlib.sha256(json.dumps(message, sort_keys=True).encode()).hexdigest()
                if seq in sequences and sequences[seq] != digest:
                    raise ValueError('conflicting captured news sequence')
                sequences[seq] = digest
                advertised = max(advertised, seq)
                if message.get('type') == 'damage_report' and message.get('stage') == 'final':
                    finals.add(rnd)
        if active and kind == 'subscription_ack':
            subscriptions.append({'at': timestamp, 'round': rnd,
                'seconds_since_previous_frame': timestamp - previous_at
                if math.isfinite(previous_at) else None})
        if not active or kind not in ('quote', 'news', 'disconnected'):
            continue
        frames.append(frame)
        if kind == 'disconnected':
            disconnects += 1
        elif kind == 'quote' and frame.get('symbol') in symbols:
            bid, ask, bs, az = (frame.get(k) for k in ('bid', 'ask', 'bid_size', 'ask_size'))
            valid = (all(number(x) for x in (bid, ask, bs, az))
                     and 0 < bid <= ask and min(bs, az) >= 0)
            if not valid:
                unusable += 1
            elif phase != 'closed':
                quote_times[str(rnd)][frame['symbol']].append(timestamp)

    if (not sequences or set(sequences) != set(range(advertised + 1))
            or len(sequences) != info.get('seq_count')
            or max(sequences) != info.get('last_seq')
            or advertised != info.get('advertised_last_seq')
            or finals != {1, 2, 3} or pre_storm != {1, 2, 3}):
        raise ValueError('capture does not independently reproduce complete receipt news coverage')
    missing = [(r, s) for r, rows in quote_times.items() for s, times in rows.items() if not times]
    if missing:
        raise ValueError(f'quotes missing for round/symbol pairs: {missing}')
    gap_summary = {}
    for r, quotes in quote_times.items():
        window = windows[r]
        if window['closed_at'] is None:
            if r != '3':
                raise ValueError('missing earlier round close observation')
            window['closed_at'] = at
            window['close_source'] = 'official_receipt'
        else:
            window['close_source'] = 'news_snapshot'
        gap_summary[r] = {}
        for symbol, times in quotes.items():
            checkpoints = [window['first_at'], *times, window['closed_at']]
            gaps = [right - left for left, right in zip(checkpoints, checkpoints[1:])]
            gap_summary[r][symbol] = {'max_seconds': max(gaps),
                                     'over_five_seconds': sum(gap > 5 for gap in gaps)}
    coverage = {'news_count': len(sequences), 'advertised_last_seq': advertised,
        'quote_count': sum(f['type'] == 'quote' for f in frames),
        'quote_count_by_round': {r: {s: len(v) for s, v in row.items()}
                                 for r, row in quote_times.items()},
        'observed_quote_gaps': gap_summary, 'round_windows': windows,
        'unusable_quotes': unusable, 'recorded_disconnect_frames': disconnects,
        'disconnect_count_known': False,
        'subscription_acknowledgements': subscriptions,
        'disconnect_note': ('The recorder may log disconnects only to its text log. '
            'Subscription acknowledgements may indicate reconnections but do not determine '
            'disconnect onset or reconstruct missed frames. Only explicit disconnect '
            'frames are applied to the replay.'),
        'quote_path_completeness_proven': False,
        'gap_note': 'Receive-time gaps include delays in observing round opens/closes; they do not prove missing server events.'}
    return receipt, frames, coverage


def evaluate(case, receipt, frames, coverage):
    results = [replay(case, frames, receipt['year'], receipt['prices'], .1,
                      latency, depth, basket, reset)
               for latency in (.25, 1., 3.) for depth in (1., .5)
               for basket in (False, True) for reset in (True, False)]
    return {'evaluation': 'fixed_observed_market_grid', 'competition_id': receipt['competition_id'],
        'year': receipt['year'], 'fraction': .1, 'official_receipt': receipt,
        'coverage': coverage, 'results': results,
        'limitations': [
            'Simulated fills are not actual account profits or guaranteed counterfactual profits.',
            'Every frozen scenario is reported; these outcomes are not used to select new parameters.',
            'Published historical seasons are not an untouched model holdout.',
            'Displayed liquidity replenishes on each quote; market impact and queue priority are omitted.',
            'HTTP serialization, cancellation races, conversion delays, and fees outside quotes are omitted.',
            'Receive-time gaps and disconnections limit conclusions about quote-path completeness.',
            'The snapshot ablation changes warm-up resets, not the entire earlier runtime.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--competition-id', required=True)
    args = parser.parse_args()
    case = json.loads((ROOT / 'data/case.json').read_text())
    receipt, frames, coverage = observed_capture(args.observations, args.feed,
                                               args.competition_id, case['limits'])
    result = evaluate(case, receipt, frames, coverage)
    source_files = [*ROOT.glob('ctc/*.py'), *ROOT.glob('ctc/*.json'), *ROOT.glob('ctc/*.npz'),
        ROOT / 'scripts/evaluate_observed_season.py', ROOT / 'scripts/replay_captured_market.py',
        ROOT / 'scripts/observe_market_seasons.py', ROOT / 'bot/live.py', ROOT / 'data/case.json']
    result['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in source_files}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

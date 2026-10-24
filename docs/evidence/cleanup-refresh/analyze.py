"""Derive all cleanup comparison tables from retained results and profiles."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import statistics

parser = argparse.ArgumentParser()
parser.add_argument('root', type=Path)
args = parser.parse_args()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return row['capture'], row['rtt_seconds'], row['displayed_depth_fraction'], row['basket_enabled']


def describe(root, row):
    capture, rtt, depth, basket = key(row)
    directory = root / f'capture-{capture}-{rtt}-{depth}-{int(basket)}'
    profile = json.loads((directory / 'cleanup-profile.json').read_text())
    books, ages, fills = {}, [], {}
    requests = collections.Counter()
    first_order = None
    start = row['cleanup_started_at']
    for item in profile:
        request = item['request']
        path = request['path'].split('?')[0]
        endpoint = '/orderbook/*' if path.startswith('/orderbook/') else path
        requests[request['method'] + ' ' + endpoint] += 1
        if path.startswith('/orderbook/'):
            books[path.split('/')[-1]] = request['executed_at']
        if request['method'] == 'POST':
            first_order = request['executed_at'] if first_order is None else first_order
            ages.append(request['executed_at'] - books[request['body']['symbol']])
        if path == '/trades' and request['method'] == 'GET':
            for fill in request['response']['trades']:
                if float(fill['executed_at']) >= start:
                    fills[fill['trade_id']] = fill
    return dict(pnl=row['terminal_settlement_pnl'], cleanup=row['cleanup']['state'],
                trial=row['trial_state'], stop=row['stop_reason'],
                duration=row['cleanup_completed_at'] - start, requests=len(profile),
                request_seconds=sum(x['request']['completed_at'] - x['request']['started_at'] for x in profile),
                request_counts=dict(requests), closing_orders=len(ages),
                min_book_age=min(ages) if ages else None, max_book_age=max(ages) if ages else None,
                first_closing_order_after=first_order - start if first_order is not None else None,
                observed_cleanup_fills=len(fills),
                last_observed_cleanup_fill_after=max(float(f['executed_at']) for f in fills.values()) - start if fills else None,
                positions_after_receipt={s: q for s, q in row['server_positions_after_final_receipt'].items() if q},
                orders_after_receipt=row['server_orders_after_final_receipt'])


phases, summaries = {}, {}
for name in ('baseline', 'candidate'):
    root = args.root / name
    rows = [json.loads(line) for line in (root / 'results.jsonl').read_text().splitlines()]
    summary = json.loads((root / 'summary.json').read_text())
    assert len(rows) == summary['runs'] == 80 and summary['errors'] == 0
    assert summary['changed_sources'] == summary['forbidden_attempts'] == []
    assert summary['results_sha256'] == sha(root / 'results.jsonl')
    indexed = {key(row): row for row in rows}
    assert len(indexed) == 80 and all(row['status'] == 'ok' for row in rows)
    phases[name] = indexed
    pnl = [row['terminal_settlement_pnl'] for row in rows]
    loss = [row for row in rows if 'loss' in row['stop_reason']]
    summaries[name] = dict(positive=sum(x > 0 for x in pnl), negative=sum(x < 0 for x in pnl),
        mean=statistics.mean(pnl), minimum=min(pnl), maximum=max(pnl),
        cleanup=dict(collections.Counter(row['cleanup']['state'] for row in rows)),
        trial=dict(collections.Counter(row['trial_state'] for row in rows)), loss_stops=len(loss),
        loss_cleanup_mean=statistics.mean(row['cleanup_completed_at'] - row['cleanup_started_at'] for row in loss),
        results_sha256=summary['results_sha256'], finished_at=summary['finished_at'])

pairs = []
for setting, baseline in phases['baseline'].items():
    candidate = phases['candidate'][setting]
    assert baseline['pre_cleanup_trace'] == candidate['pre_cleanup_trace']
    before = describe(args.root / 'baseline', baseline)
    after = describe(args.root / 'candidate', candidate)
    pairs.append(dict(setting=setting, baseline=before, candidate=after,
                      pnl_delta=after['pnl'] - before['pnl'],
                      duration_delta=after['duration'] - before['duration']))

print(json.dumps(dict(summaries=summaries, pre_cleanup_pairs_equal=len(pairs),
                      improved_pnl=sum(p['pnl_delta'] > 1e-7 for p in pairs),
                      worsened_pnl=sum(p['pnl_delta'] < -1e-7 for p in pairs),
                      unchanged_pnl=sum(abs(p['pnl_delta']) <= 1e-7 for p in pairs), pairs=pairs), indent=2))

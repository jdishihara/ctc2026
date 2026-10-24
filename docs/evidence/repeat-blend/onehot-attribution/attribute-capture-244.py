"""Accounting-only audit of four existing capture-244 traces; runs no strategy.

Uses closed, independently audited traces. Does not import the frozen runtime,
read history/credentials, connect to a network, or inspect another capture.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def near(a, b):
    assert math.isclose(a, b, rel_tol=0, abs_tol=1e-8), (a, b)


def cash(fills):
    return math.fsum((-1 if f['side'] == 'buy' else 1) * f['qty'] * f['price'] for f in fills)


def quantity(fills):
    return sum((1 if f['side'] == 'buy' else -1) * f['qty'] for f in fills)


def audit(directory, producer, variant, depth, settlement_prices):
    names = ['result.json', 'request-trace.json', 'fill-trace.json',
             'last-quote-observations.json', 'observations.json',
             'final-receipt.json', 'cleanup-profile.json', 'repeat-profile.json']
    data = {name: load(directory / name) for name in names}
    result, requests, fills = (data[name] for name in names[:3])
    assert result['status'] == 'ok' and not result['errors'] and result['conversions'] == 0
    assert result['final_receipt']['flat'] and result['final_receipt']['verified']
    assert not any(result['final_positions'].values())
    assert not result['fills_after_final_receipt_requests']
    original = load(producer / variant / directory.name / 'result.json')
    assert all(result[k] == value for k, value in original.items())
    assert len(fills) == result['fills']
    near(cash(fills), result['terminal_settlement_pnl'])
    assert all(quantity([f for f in fills if f['symbol'] == s]) == 0
               for s in result['final_positions'])
    start = result['cleanup_started_at']
    positions = [r for r in requests if r['path'] == '/positions?include_zero=true']
    before = [r for r in positions if r['executed_at'] < start][-1]
    anchor = [r for r in positions if r['executed_at'] >= start][0]
    before_rows = {r['symbol']: r for r in before['response']['positions']}
    anchor_rows = {r['symbol']: r for r in anchor['response']['positions']}
    final_rows = {r['symbol']: r for r in data['final-receipt.json']['positions']['positions']}
    assert not any(before['executed_at'] <= f['t'] <= anchor['executed_at'] for f in fills)
    pre = [f for f in fills if f['t'] < start]
    cleanup = [f for f in fills if f['t'] >= start]
    assert all(f['t'] > anchor['executed_at'] for f in cleanup)
    symbols = {}
    for symbol, row in anchor_rows.items():
        entry = [f for f in pre if f['symbol'] == symbol]
        exits = [f for f in cleanup if f['symbol'] == symbol]
        q = quantity(entry)
        assert q == row['quantity'] == before_rows[symbol]['quantity']
        assert quantity(exits) == -q
        if not entry and not exits:
            continue
        mark = row['average_price'] + row['unrealized_pnl'] / q
        before_pnl = before_rows[symbol]['realized_pnl'] + before_rows[symbol]['unrealized_pnl']
        anchor_pnl = row['realized_pnl'] + row['unrealized_pnl']
        final_cash = cash(entry + exits)
        near(cash(entry) + q * mark, anchor_pnl)
        near(final_cash, final_rows[symbol]['realized_pnl'])
        near(cash(exits) - q * mark, final_cash - anchor_pnl)
        terminal_inventory_value = q * settlement_prices[symbol]
        terminal_cash_plus_payoff = cash(entry) + terminal_inventory_value
        # These traces enter once and then liquidate; preserve that assumption explicitly.
        assert all(f['side'] == ('buy' if q > 0 else 'sell') for f in entry)
        assert all(f['side'] == ('sell' if q > 0 else 'buy') for f in exits)
        symbols[symbol] = {
            'quantity_at_first_cleanup_snapshot': q,
            'entry_vwap': math.fsum(f['qty'] * f['price'] for f in entry) / abs(q),
            'exit_vwap': math.fsum(f['qty'] * f['price'] for f in exits) / abs(q),
            'pre_cleanup_cash': cash(entry), 'cleanup_cash_flow': cash(exits),
            'first_cleanup_snapshot_midpoint': mark,
            'last_pre_cleanup_snapshot_pnl': before_pnl,
            'first_cleanup_snapshot_pnl': anchor_pnl,
            'mark_change_between_snapshots_no_fills': anchor_pnl - before_pnl,
            'inventory_mark_removed_at_flat': -q * mark,
            'pnl_change_first_cleanup_snapshot_to_flat': final_cash - anchor_pnl,
            'final_flat_pnl': final_cash,
            'ex_post_frozen_inventory_diagnostic': {
                'terminal_settlement_price': settlement_prices[symbol],
                'inventory_value_at_contemporaneous_mark': q * mark,
                'inventory_value_at_terminal_settlement': terminal_inventory_value,
                'pre_cleanup_cash_plus_terminal_payoff': terminal_cash_plus_payoff,
                'terminal_payoff_minus_contemporaneous_mark': q * (settlement_prices[symbol] - mark),
            },
            'entry_fills': len(entry), 'cleanup_fills': len(exits),
            'entry_first_at': min(f['t'] for f in entry),
            'entry_last_at': max(f['t'] for f in entry),
            'cleanup_first_fill_after_start_seconds': min(f['t'] for f in exits) - start,
            'cleanup_last_fill_after_start_seconds': max(f['t'] for f in exits) - start,
        }
    anchor_pnl = math.fsum(r['realized_pnl'] + r['unrealized_pnl'] for r in anchor_rows.values())
    before_pnl = math.fsum(r['realized_pnl'] + r['unrealized_pnl'] for r in before_rows.values())
    marked_inventory = math.fsum(r['quantity_at_first_cleanup_snapshot'] *
                                 r['first_cleanup_snapshot_midpoint'] for r in symbols.values())
    near(cash(pre) + marked_inventory, anchor_pnl)
    near(cash(cleanup) - marked_inventory, cash(fills) - anchor_pnl)
    terminal_inventory_value = math.fsum(r['ex_post_frozen_inventory_diagnostic'][
        'inventory_value_at_terminal_settlement'] for r in symbols.values())
    terminal_cash_plus_payoff = cash(pre) + terminal_inventory_value
    observations = data['observations.json']
    trigger = next(r for r in observations if r['stop_reason'] is not None)
    cached = data['last-quote-observations.json']['callbacks'][-1]['before']
    mutations = [{k: r[k] for k in ['method', 'path', 'body', 'started_at', 'executed_at', 'completed_at']}
                 for r in requests if r['started_at'] >= start and r['method'] != 'GET']
    return {
        'variant': variant, 'rtt_seconds': .25, 'displayed_depth_fraction': depth,
        'basket_enabled': True, 'source_directory': str(directory),
        'source_sha256': {name: sha(directory / name) for name in names},
        'producer_result_fields_match': True,
        'stop_at': result['stop_at'], 'first_loss_observation': trigger,
        'last_pre_cleanup_position_snapshot_at': before['executed_at'],
        'last_pre_cleanup_position_snapshot_pnl': before_pnl,
        'cleanup_started_at': start,
        'first_cleanup_position_snapshot_at': anchor['executed_at'],
        'first_cleanup_position_snapshot_pnl': anchor_pnl,
        'cleanup_completed_at': result['cleanup_completed_at'],
        'cleanup_duration_seconds': result['cleanup_completed_at'] - start,
        'pre_cleanup_fills': len(pre), 'cleanup_fills': len(cleanup), 'conversions': 0,
        'pre_cleanup_cash': cash(pre), 'cleanup_cash_flow': cash(cleanup),
        'inventory_mark_removed_at_flat': -marked_inventory,
        'pnl_change_first_cleanup_snapshot_to_flat': cash(fills) - anchor_pnl,
        'final_flat_cash_pnl': cash(fills),
        'ex_post_frozen_inventory_diagnostic': {
            'inventory_value_at_contemporaneous_mark': marked_inventory,
            'inventory_value_at_terminal_settlement': terminal_inventory_value,
            'pre_cleanup_cash_plus_terminal_payoff': terminal_cash_plus_payoff,
            'terminal_payoff_minus_contemporaneous_mark': terminal_inventory_value - marked_inventory,
            'terminal_cash_plus_payoff_minus_actual_flat_cash': terminal_cash_plus_payoff - cash(fills),
        },
        'lowest_marked_pnl': result['lowest_marked_pnl'],
        'cached_last_callback': {k: cached[k] for k in ['at', 'round', 'last_observed_age',
            'fair', 'fair_sd', 'future_sd', 'repeat_match', 'history_ready']},
        'repeat_profile': data['repeat-profile.json'], 'by_symbol': symbols,
        'cleanup_mutations': mutations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--closed-capture', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    spec = next(r for r in load(args.producer / 'spec.json')['captures'] if r['capture'] == 244)
    assert sha(args.closed_capture) == spec['input_sha256']
    receipt = load(args.closed_capture)['receipt']
    assert receipt['kind'] == 'settlement'
    assert receipt['competition_id'] == '2cf67e88-9081-4258-aa6a-3648c41925de'
    assert receipt['year'] == '1783'
    assert all(receipt[k]['state'] == 'ready' and
               receipt[k]['competition_id'] == receipt['competition_id'] for k in ['clock', 'end_clock'])
    assert receipt['clock'] == receipt['end_clock']
    assert receipt['coverage']['contiguous'] and not receipt['coverage']['conflicting_sequences']
    assert receipt['coverage']['final_rounds'] == [1, 2, 3]
    assert receipt['coverage']['last_seq'] == receipt['coverage']['advertised_last_seq'] == 870
    assert receipt['coverage']['seq_count'] == 871
    assert len(receipt['prices']) == 12 and all(math.isfinite(p) and p > 0 for p in receipt['prices'].values())
    scenarios = [audit(directory / f'capture-244-0.25-{depth:.1f}-1', args.producer, variant, depth,
                       receipt['prices'])
                 for variant, directory in [('baseline', args.baseline), ('candidate', args.candidate)]
                 for depth in [1., .5]]
    by_key = {(r['variant'], r['displayed_depth_fraction']): r for r in scenarios}
    comparisons = []
    for depth in [1., .5]:
        a, b = by_key['baseline', depth], by_key['candidate', depth]
        comparisons.append({'displayed_depth_fraction': depth,
            'candidate_minus_baseline_final_pnl': b['final_flat_cash_pnl'] - a['final_flat_cash_pnl'],
            'by_symbol_final_pnl_delta': {s: b['by_symbol'].get(s, {}).get('final_flat_pnl', 0)
                - a['by_symbol'].get(s, {}).get('final_flat_pnl', 0)
                for s in sorted(set(a['by_symbol']) | set(b['by_symbol']))}})
    full, half = by_key['candidate', 1.], by_key['candidate', .5]
    report = {'scope': 'Accounting of existing audited closed capture 244 traces only; no new performance run.',
        'frozen_source_commit': '357d9986babf2b21bd3bbdcc2e69550059f16154',
        'audit_script_sha256': sha(Path(__file__)), 'scenarios': scenarios,
        'closed_capture_source': {'path': str(args.closed_capture), 'sha256': sha(args.closed_capture),
            'matches_frozen_spec': True, 'receipt': receipt},
        'comparisons': comparisons,
        'candidate_half_minus_full': {
            'final_pnl': half['final_flat_cash_pnl'] - full['final_flat_cash_pnl'],
            'pre_cleanup_cash': half['pre_cleanup_cash'] - full['pre_cleanup_cash'],
            'cleanup_cash_flow': half['cleanup_cash_flow'] - full['cleanup_cash_flow'],
            'same_inventory_at_first_cleanup_snapshot': all(
                half['by_symbol'][s]['quantity_at_first_cleanup_snapshot'] ==
                full['by_symbol'][s]['quantity_at_first_cleanup_snapshot'] for s in full['by_symbol'])},
        'limitations': [
            'Position-response marks are stamped at request execution, not at response observation or cleanup entry.',
            'The first cleanup snapshot follows cleanup entry; its clock and the last pre-cleanup snapshot are explicit.',
            'Mark-to-flat changes combine intervening prices, spread, partial fills and serialized cleanup; they are not pure slippage.',
            'Baseline and candidate stops/cached forecasts occur at different times; these caches are not a same-time ablation.',
            'Fill traces have no order ID. This audit does not invent per-fill order associations.',
            'All four runs finish flat with zero conversions; symbol cashflows therefore reconcile without settlement prices.',
            'The separate ex-post frozen-inventory diagnostic values first-cleanup holdings at the existing closed receipt. It permits no later trading and is not a realizable alternative policy or a measured cleanup saving.',
            'A positive terminal payoff diagnostic does not establish feasible interim risk, forecast calibration, or future performance.',
            'These are modeled executions on one reused captured path, not actual account profits or proof of future performance.',
        ]}
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'scenarios': len(scenarios), 'all_reconciliations_passed': True,
        'comparisons': comparisons, 'candidate_half_minus_full': report['candidate_half_minus_full']}, indent=2))


if __name__ == '__main__':
    main()

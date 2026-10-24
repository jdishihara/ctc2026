"""Read-only clock and official-settlement recorder for overnight offline practice.

Uses only three fixed GET endpoints. No order/account mutations and no account
profit attribution. Requires the existing feed recorder for news coverage.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class FeedCoverage:
    def __init__(self, path):
        self.stream = Path(path).open()
        self.years = {}

    def poll(self):
        while True:
            offset = self.stream.tell()
            line = self.stream.readline()
            if not line:
                break
            if not line.endswith('\n'):
                self.stream.seek(offset)
                break
            frame = json.loads(line)
            if frame.get('type') != 'news' or not isinstance(frame.get('message'), dict):
                continue
            message = frame['message']
            year, at = str(message.get('time', ''))[:4], frame.get('received_at')
            if len(year) != 4 or not year.isdigit() or not isinstance(at, (int, float)):
                continue
            state = self.years.setdefault(year, {'first_at': at, 'last_at': at,
                'sequences': {}, 'advertised': -1, 'final_rounds': set(), 'conflicting_sequences': False})
            state['last_at'] = max(state['last_at'], at)
            seq = message.get('seq')
            checkpoint = message.get('last_seq') if message.get('type') == 'snapshot' else None
            if type(checkpoint) is int and checkpoint >= -1:
                state['advertised'] = max(state['advertised'], checkpoint)
            if type(seq) is int and seq >= 0:
                state['advertised'] = max(state['advertised'], seq)
                digest = hashlib.sha256(json.dumps(message, sort_keys=True).encode()).hexdigest()
                if seq in state['sequences'] and state['sequences'][seq] != digest:
                    state['conflicting_sequences'] = True
                state['sequences'][seq] = digest
                if (message.get('type') == 'damage_report' and message.get('stage') == 'final'
                        and type(message.get('round')) is int and message['round'] in (1, 2, 3)):
                    state['final_rounds'].add(message['round'])

    def summary(self, year):
        state = self.years.get(year)
        if state is None:
            return None
        seq = state['sequences']
        return {'first_at': state['first_at'], 'last_at': state['last_at'],
            'seq_count': len(seq), 'last_seq': max(seq, default=-1),
            'advertised_last_seq': state['advertised'],
            'contiguous': bool(seq) and set(seq) == set(range(state['advertised'] + 1)),
            'final_rounds': sorted(state['final_rounds']),
            'conflicting_sequences': state['conflicting_sequences']}


def official_receipt(clock, rows, end_clock, coverage, symbols):
    cid = clock.get('competition_id')
    year = str(clock.get('fictional_time', ''))[:4]
    if (not cid or cid != end_clock.get('competition_id')
            or len(year) != 4 or not year.isascii() or not year.isdigit()
            or clock.get('state') != 'ready' or end_clock.get('state') != 'ready'
            or str(end_clock.get('fictional_time', ''))[:4] != year
            or not coverage or not coverage['contiguous'] or coverage['conflicting_sequences']
            or coverage['final_rounds'] != [1, 2, 3] or not isinstance(rows, list)):
        return None
    prices = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        symbol, price = row.get('symbol'), row.get('settlement_price')
        if (symbol not in symbols or symbol in prices or not row.get('settlement_active')
                or isinstance(price, bool) or not isinstance(price, (int, float))
                or not math.isfinite(price) or price <= 0):
            return None
        prices[symbol] = price
    if set(prices) != set(symbols):
        return None
    return {'kind': 'settlement', 'source': 'read_only_market_observer',
        'competition_id': cid, 'year': year, 'clock': clock, 'end_clock': end_clock,
        'prices': prices, 'coverage': coverage}


class MarketReader:
    def __init__(self, url, key_file, deadline):
        self.url = url.rstrip('/')
        self.deadline = deadline
        self.headers = {'User-Agent': 'ctc2026-bot/1.0',
                        'X-API-Key': Path(key_file).read_text().strip()}

    def get(self, path):
        if path not in ('/competitions/time', '/competitions/current', '/symbols'):
            raise ValueError('endpoint is outside the read-only market recorder scope')
        remaining = self.deadline - time.time()
        if remaining <= 0:
            raise TimeoutError('market observer deadline reached')
        request = urllib.request.Request(self.url + '/api/v1' + path,
                                         headers=self.headers, method='GET')
        with urllib.request.urlopen(request, timeout=min(10, remaining)) as response:
            return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://cornelltradingcompetition.org')
    parser.add_argument('--key-file', type=Path, default=ROOT / '.botkey')
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--until', required=True, help='timezone-aware ISO timestamp')
    parser.add_argument('--interval', type=float, default=15)
    args = parser.parse_args()
    until = datetime.fromisoformat(args.until)
    if until.tzinfo is None or until.timestamp() <= time.time() or not 5 <= args.interval <= 60:
        parser.error('future timezone-aware deadline and interval from 5 to 60 seconds required')
    reader = MarketReader(args.url, args.key_file, until.timestamp())
    coverage = FeedCoverage(args.feed)
    symbols = list(json.loads((ROOT / 'data/case.json').read_text())['limits'])
    completed, confirmed = set(), set()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as output:
        def record(event):
            event = {'at': time.time(), **event}
            output.write(json.dumps(event) + '\n')
            output.flush()
            if event['kind'] != 'clock':
                print(json.dumps(event), flush=True)
        record({'kind': 'observer_started', 'until': until.isoformat(), 'interval': args.interval})
        while time.time() < until.timestamp():
            try:
                coverage.poll()
                clock = reader.get('/competitions/time')
                cid = clock.get('competition_id')
                record({'kind': 'clock', 'clock': clock})
                if cid not in confirmed:
                    current = reader.get('/competitions/current')
                    if current.get('competition_id') == cid and current.get('name') == 'Hurricane Season':
                        confirmed.add(cid)
                info = coverage.summary(str(clock.get('fictional_time', ''))[:4])
                if (cid in confirmed and cid not in completed and clock.get('state') != 'running'
                        and info and info['final_rounds'] == [1, 2, 3]):
                    rows = reader.get('/symbols').get('symbols')
                    end_clock = reader.get('/competitions/time')
                    receipt = official_receipt(clock, rows, end_clock, info, symbols)
                    if receipt:
                        record(receipt)
                        completed.add(cid)
            except Exception as exc:
                record({'kind': 'observer_error', 'error': f'{type(exc).__name__}: {exc}'})
            time.sleep(max(0, min(args.interval, until.timestamp() - time.time())))
        record({'kind': 'observer_finished', 'completed_seasons': len(completed)})


if __name__ == '__main__':
    main()

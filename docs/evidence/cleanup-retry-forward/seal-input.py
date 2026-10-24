"""Seal one independently validated closed capture for the fixed retry check."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/Users/arjunhans/Documents/ctc2026')
sys.path.insert(0, str(ROOT / '.worktrees/cleanup-retry-forward'))
from scripts.compare_cleanup_retry_forward import validate_forward_receipt
from scripts.evaluate_observed_season import observed_capture

parser = argparse.ArgumentParser()
parser.add_argument('--capture', type=int, choices=[248, 249], required=True)
parser.add_argument('--forward-spec', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()


def audit(event, values):
    if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo'):
        raise RuntimeError('sealing is offline')
    if event == 'open' and isinstance(values[0], (str, bytes)):
        name = str(values[0]).lower()
        if '.botkey' in name or '/.env' in name or '/data/history/' in name or 'credentials' in name:
            raise RuntimeError('sealing forbids credentials and downloaded history')


sys.addaudithook(audit)
spec = json.loads(args.forward_spec.read_text())
assert [i['capture'] for i in spec['captures']] == [args.capture]
item = spec['captures'][0]
assert item['mode'] == 'observed'
for field in ('observations', 'feed'):
    content = Path(item[field]).read_bytes()
    assert content.endswith(b'\n') and len(content) == item[field + '_bytes']
    assert hashlib.sha256(content).hexdigest() == item[field + '_sha256']
case = json.loads((ROOT / '.worktrees/cleanup-retry-forward/data/case.json').read_text())
receipt, frames, coverage = observed_capture(item['observations'], item['feed'],
                                           item['competition_id'], case['limits'])
validate_forward_receipt(receipt, capture=args.capture, symbols=case['limits'])
metadata = json.loads((args.forward_spec.parent / 'supervised/metadata.json').read_text())
selected = next(x for x in metadata['captures'] if x['capture'] == args.capture)
value_hash = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest()
assert selected['frames_sha256'] == value_hash(frames)
assert selected['receipt_sha256'] == value_hash(receipt)
payload = json.dumps(dict(receipt=receipt, frames=frames), separators=(',', ':')) + '\n'
with args.out.open('x') as target:
    target.write(payload)
print(json.dumps(dict(path=str(args.out), bytes=args.out.stat().st_size,
    sha256=hashlib.sha256(args.out.read_bytes()).hexdigest(),
    frames_sha256=value_hash(frames), receipt_sha256=value_hash(receipt),
    frame_count=len(frames), coverage=coverage)))

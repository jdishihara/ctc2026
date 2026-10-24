"""Archive local practice status updates without contacting the exchange."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--until', required=True, help='Timezone-aware ISO deadline')
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.until)
    if deadline.tzinfo is None or deadline <= datetime.now(timezone.utc):
        parser.error('--until must be a future time with a timezone')
    if not args.root.is_dir():
        parser.error('--root must be an existing practice recordings directory')

    seen: dict[Path, bytes] = {}
    # Exclusive creation prevents accidentally truncating an earlier audit.
    with args.out.open('x') as output:
        try:
            while datetime.now(timezone.utc) < deadline:
                paths = sorted(args.root.glob('batch-*/status.json'))
                paths += sorted(args.root.glob('batch-*/final-receipt.json'))
                for path in paths:
                    try:
                        raw = path.read_bytes()
                        if seen.get(path) == raw:
                            continue
                        payload = json.loads(raw)
                    except (OSError, ValueError):
                        # A writer may be between truncation and completion.
                        continue
                    output.write(json.dumps({
                        'observed_at': datetime.now(timezone.utc).isoformat(),
                        'source': str(path.relative_to(args.root)),
                        'payload': payload,
                    }, separators=(',', ':')) + '\n')
                    output.flush()
                    seen[path] = raw
                time.sleep(2)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()

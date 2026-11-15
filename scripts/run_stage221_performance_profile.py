#!/usr/bin/env python3
"""Stage 221: reproducible synthetic-only, side-effect-free local timings."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
from nexus_titan.diagnostics.stage221_profile import fixed_synthetic_cases, measure_case, measurement_to_dict


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--warmups', type=int, default=2)
    p.add_argument('--iterations', type=int, default=5)
    p.add_argument('--samples', type=int, default=7)
    p.add_argument('--json-out', type=Path, default=None)
    a = p.parse_args()
    try:
        rows = [measurement_to_dict(measure_case(c, warmups=a.warmups,
                                                iterations=a.iterations, samples=a.samples))
                for c in fixed_synthetic_cases()]
    except (RuntimeError, ValueError) as e:
        print(f'PROFILE NOT ACCEPTED: {e}', file=sys.stderr)
        return 2
    data = {
        'schema': 'titan.stage221.synthetic_python_bench.v1',
        'captured_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'python': platform.python_version(), 'implementation': platform.python_implementation(),
        'platform': platform.platform(), 'profile': rows,
        'real_market_latency_verified': False,
        'rust_rewrite_authorized': False,
        'live_trading_authorized': False,
        'notes': 'Offline synthetic microbenchmarks only. Uncalibrated host, no relative Rust speedup.'
    }
    raw = json.dumps(data, indent=2, sort_keys=True) + '\n'
    if a.json_out is not None:
        # Keep output outside the source tree if desired; no arbitrary file is read.
        a.json_out.parent.mkdir(parents=True, exist_ok=True)
        a.json_out.write_text(raw, encoding='utf-8')
    else:
        print(raw)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

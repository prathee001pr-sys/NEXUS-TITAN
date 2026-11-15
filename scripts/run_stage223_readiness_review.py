#!/usr/bin/env python3
"""Stage 223 standalone offline report consistency check; NO-GO for Rust/trading."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from nexus_titan.diagnostics.stage223_rust_readiness import review_rust_readiness


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage222-report', required=True, type=Path)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args(argv)
    try:
        if not args.stage222_report.is_file() or args.stage222_report.stat().st_size > 100_000:
            raise ValueError('missing or oversized Stage 222 report')
        report = json.loads(args.stage222_report.read_text(encoding='utf-8'),
                            parse_constant=lambda x: (_ for _ in ()).throw(ValueError('invalid numeric constant')))
        receipt = review_rust_readiness(report)
        if not receipt.accepted_for_offline_experiment_review:
            print('REJECTED: Stage 222 report does not pass strict evidence checks', file=sys.stderr)
            return 2
    except (OSError, ValueError, UnicodeError, TypeError, RecursionError) as exc:
        print(f'REJECTED: {exc}', file=sys.stderr)
        return 2
    output = {
        'schema': 'titan.stage223.offline_rust_readiness.v1',
        'input_report': str(args.stage222_report.name),
        'receipt': asdict(receipt),
        'note': 'Source hashes are local-byte checks, not provenance or production authorization.',
    }
    raw = json.dumps(output, sort_keys=True, indent=2, allow_nan=False) + '\n'
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(raw, encoding='utf-8')
    else:
        print(raw, end='')
    return 0 if receipt.accepted_for_offline_experiment_review else 2


if __name__ == '__main__':
    raise SystemExit(main())

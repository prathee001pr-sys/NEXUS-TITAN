#!/usr/bin/env python3
"""Opt-in bounded Stage 121 timeout variability triage; no production change."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import tempfile
from pathlib import Path
from nexus_titan.operations.stage121_research_supervisor import supervise_synthetic_research

H = hashlib.sha256(b'STAGE221_DIAGNOSTIC_OFFLINE_NO_LIVE').hexdigest()


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--explicit-opt-in', action='store_true')
    p.add_argument('--runs', type=int, default=3)
    p.add_argument('--timeout-seconds', type=float, default=1.2)
    a=p.parse_args()
    if not a.explicit_opt_in:
        print('REJECTED: explicit opt-in required')
        return 2
    if type(a.runs) is not int or not 1 <= a.runs <= 10 or not 0.5 <= a.timeout_seconds <= 10:
        print('REJECTED: bounded runs/timeout required')
        return 2
    results=[]
    with tempfile.TemporaryDirectory(prefix='titan-stage221-recovery-') as root:
        for i in range(a.runs):
            r=supervise_synthetic_research(Path(root)/f'case-{i}.sqlite',
                job_id=f'diagnostic-{i}',source_sha256=H,total_chunks=2,
                mode='hang_once',timeout_seconds=a.timeout_seconds)
            results.append(asdict(r))
    summary = {'schema': 'titan.stage221.recovery_variability.v1',
               'runs': len(results), 'observations': results,
               'unexpected_count': sum(not (r['state']=='COMPLETED' and r['attempts']==2
                                             and r['timeouts']==1 and r['checkpoint']==2)
                                       for r in results),
               'live_trading_authorized': False,
               'root_cause_proven': False}
    print(json.dumps(summary, indent=2, sort_keys=True))
    # Return nonzero if any unexpectedly timed out; diagnostic does not override quarantine.
    return 1 if summary['unexpected_count'] else 0

if __name__=='__main__':
    raise SystemExit(main())

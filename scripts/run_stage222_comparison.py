#!/usr/bin/env python3
"""Stage 222 offline A/B benchmark. No production modification or auto-promotion."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import platform
import statistics
import sys
import time

from nexus_titan.data.stage217_progress_journal import make_progress_event, audit_progress_journal
from nexus_titan.diagnostics.stage222_journal_candidate import audit_progress_journal_candidate


def synthetic_journal(count: int) -> tuple:
    if type(count) is not int or count not in (30, 300, 1000):
        raise ValueError('only fixed synthetic workload sizes are permitted')
    out = []
    prior = '0' * 64
    states = ('SUBMITTED_UNVERIFIED', 'LOCAL_TEST_REPORTED_UNVERIFIED', 'CI_REPORTED_UNVERIFIED')
    for i in range(count):
        evidence = sha256(f'220-experimental-fixed-{i}'.encode('ascii')).hexdigest()
        ev = make_progress_event(sequence=i+1, stage_number=216+(i % 5),
                                 state=states[i % 3], evidence_sha256=evidence,
                                 previous_event_sha256=prior)
        out.append(ev)
        prior = ev.event_sha256
    return tuple(out)


def _timed(fn, journal, reference, iterations: int) -> int:
    start = time.perf_counter_ns()
    for _ in range(iterations):
        receipt = fn(journal)
        if receipt != reference:
            raise RuntimeError('experiment output differs from production baseline')
    elapsed = time.perf_counter_ns() - start
    if elapsed <= 0:
        raise RuntimeError('invalid monotonic clock delta')
    return max(1, (elapsed + iterations - 1)//iterations)


def benchmark(*, samples=9, iterations=5) -> dict:
    if (type(samples) is not int or not 3 <= samples <= 31
            or type(iterations) is not int or not 1 <= iterations <= 100):
        raise ValueError('invalid benchmark limits')
    rows = []
    for count in (30, 300, 1000):
        journal = synthetic_journal(count)
        baseline = audit_progress_journal(journal)
        candidate = audit_progress_journal_candidate(journal)
        if baseline != candidate or not baseline.accepted or baseline.authoritative_git_verification:
            raise RuntimeError('candidate invalid or not equivalent')
        # Deterministic warmup, paired samples, reverse execution order to reduce order bias.
        for fn in (audit_progress_journal, audit_progress_journal_candidate):
            for _ in range(2):
                if fn(journal) != baseline:
                    raise RuntimeError('warmup equivalence failed')
        baseline_ns, candidate_ns = [], []
        for index in range(samples):
            ordered = ((audit_progress_journal, baseline_ns),
                       (audit_progress_journal_candidate, candidate_ns))
            if index % 2:
                ordered = tuple(reversed(ordered))
            for fn, durations in ordered:
                durations.append(_timed(fn, journal, baseline, iterations))
        bmed = int(statistics.median(baseline_ns))
        cmed = int(statistics.median(candidate_ns))
        rows.append({
            'case': f'offline_journal_{count}', 'event_count': count,
            'output_digest': baseline.head_sha256,
            'fixture_digest': sha256('|'.join(ev.event_sha256 for ev in journal).encode()).hexdigest(),
            'baseline_median_ns': bmed, 'candidate_median_ns': cmed,
            'observed_speedup_ratio': round(bmed/cmed, 3),
            'baseline_samples_ns': baseline_ns, 'candidate_samples_ns': candidate_ns,
            'equivalent_on_fixed_fixture': True,
        })
    return {
        'schema': 'titan.stage222.offline_python_candidate.v1',
        'implementation':platform.python_implementation(),
        'python_version':platform.python_version(),
        'system':platform.system(),
        'samples':samples,'iterations_per_sample':iterations,
        'stage217_production_modified': False,
        'production_replacement_authorized': False,
        'rust_rewrite_authorized': False,
        'real_market_latency_verified': False,
        'live_trading_authorized': False,
        'note':'Local synthetic journal hashing experiment; environment-dependent descriptive speed only, no latency SLA.',
        'results':rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=int,default=9)
    parser.add_argument('--iterations',type=int,default=5)
    parser.add_argument('--json-out',type=Path)
    args=parser.parse_args(argv)
    try:
        output=benchmark(samples=args.samples,iterations=args.iterations)
    except (ValueError,RuntimeError) as exc:
        print(f'REJECTED: {exc}',file=sys.stderr)
        return 2
    serialized=json.dumps(output,sort_keys=True,indent=2)+'\n'
    if args.json_out:
        args.json_out.parent.mkdir(parents=True,exist_ok=True)
        args.json_out.write_text(serialized,encoding='utf-8')
    else:
        print(serialized,end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

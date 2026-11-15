"""Stage 221: bounded, synthetic-only Python performance measurement.

Not an execution gateway, trading approval, latency SLA, or real market benchmark.
Only fixed, deterministic, read-only operations are profiled. This module makes
NO decision to port code to Rust or alter the risk veto.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import inspect
import math
import statistics
import time
from typing import Callable

from nexus_titan.data.stage190_e2e_paper_replay import E2EPaperReplayReceipt
from nexus_titan.data.stage191_portfolio_replay_ledger import ClosedReplay, audit_portfolio_replay_ledger
from nexus_titan.data.stage206_depth_snapshot import DepthLevel, DepthSnapshot, audit_depth_snapshot
from nexus_titan.data.stage207_liquidity_fill import audit_liquidity_fill
from nexus_titan.data.stage217_progress_journal import make_progress_event, audit_progress_journal

_NO_TRADE = False
_T0 = datetime(2024, 1, 2, 9, 15, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class ProfileCase:
    name: str
    size: int
    fixture_sha256: str
    callable_fn: Callable[[], str]
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ProfileMeasurement:
    name: str
    size: int
    fixture_sha256: str
    source_sha256: str
    output_sha256: str
    warmups: int
    iterations_per_sample: int
    samples: int
    min_ns_per_call: int
    median_ns_per_call: int
    p95_ns_per_call: int
    max_ns_per_call: int
    sample_ns_per_call: tuple[int, ...]
    live_trading_authorized: bool = _NO_TRADE
    rust_rewrite_authorized: bool = _NO_TRADE
    real_market_latency_verified: bool = _NO_TRADE


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _source(*functions: Callable) -> str:
    return _sha('\n'.join(inspect.getsource(fn) for fn in functions))


def _book() -> tuple[DepthSnapshot, datetime]:
    bids = tuple(DepthLevel(str(Decimal('99.95') - Decimal('0.05') * i), 100 + i) for i in range(10))
    asks = tuple(DepthLevel(str(Decimal('100.05') + Decimal('0.05') * i), 100 + i) for i in range(10))
    return (DepthSnapshot('profile221', 'NIFTY-SYNTHETIC-CE', 'a'*64, _T0,
                          _T0 + timedelta(milliseconds=50), bids, asks),
            _T0 + timedelta(milliseconds=300))


def fixed_synthetic_cases() -> tuple[ProfileCase, ...]:
    """Construct bounded fixtures. Caller input, network and plugins are excluded."""
    book, decision = _book()
    depth = audit_depth_snapshot(book, decision_at=decision, tick_size='0.05')
    if not depth.accepted or depth.live_trading_authorized:
        raise RuntimeError('invalid synthetic depth fixture')

    def depth_op() -> str:
        r = audit_depth_snapshot(book, decision_at=decision, tick_size='0.05')
        if not r.accepted or r.live_trading_authorized:
            raise RuntimeError('depth receipt rejected')
        return r.snapshot_sha256

    def fill_op() -> str:
        r = audit_liquidity_fill(book, depth=depth, side='BUY', quantity=750,
                                 tick_size='0.05', participation_bps=10000,
                                 max_adverse_slippage_bps=250, latency_ms=20)
        if not r.accepted or r.live_trading_authorized:
            raise RuntimeError('synthetic fill rejected')
        return r.fill_sha256

    trades = tuple(
        ClosedReplay(f'p221_{i:04}', _T0 + timedelta(seconds=i+1),
                     E2EPaperReplayReceipt(True, Decimal((i % 7) - 3) / Decimal('10'),
                                           hashlib.sha256(f'fixed-replay-{i}'.encode()).hexdigest(), ()))
        for i in range(1000)
    )

    def ledger_op() -> str:
        r = audit_portfolio_replay_ledger(trades)
        if not r.accepted or r.trade_count != 1000:
            raise RuntimeError('synthetic ledger rejected')
        return r.ledger_sha256

    events = []
    prior = '0'*64
    for i in range(300):
        record = make_progress_event(sequence=i+1, stage_number=216 + i % 5,
                                     state='SUBMITTED_UNVERIFIED', evidence_sha256='b'*64,
                                     previous_event_sha256=prior)
        events.append(record)
        prior = record.event_sha256
    journal = tuple(events)

    def journal_op() -> str:
        r = audit_progress_journal(journal)
        if not r.accepted or r.event_count != 300 or r.authoritative_git_verification:
            raise RuntimeError('offline journal rejected')
        return r.head_sha256

    return (
        ProfileCase('depth_10_levels_each_side', 20, _sha(repr((book, decision, '0.05'))),
                    depth_op, _source(audit_depth_snapshot)),
        ProfileCase('synthetic_partial_fill_10_levels', 20,
                    _sha(repr((book, depth.snapshot_sha256, 'BUY', 750, 20))),
                    fill_op, _source(audit_liquidity_fill, audit_depth_snapshot)),
        ProfileCase('synthetic_closed_trades_1000', 1000, _sha(repr(trades)),
                    ledger_op, _source(audit_portfolio_replay_ledger)),
        ProfileCase('offline_progress_journal_300', 300, _sha(repr(journal)),
                    journal_op, _source(audit_progress_journal, make_progress_event)),
    )


def measure_case(case: ProfileCase, *, warmups: int = 2, iterations: int = 5,
                 samples: int = 7, clock: Callable[[], int] = time.perf_counter_ns) -> ProfileMeasurement:
    """Time operations only, not fixture setup. Verify deterministic outputs.

    The speed result is descriptive, not an automated optimization trigger.
    p95 is the nearest-rank of the measured per-call batch latencies.
    """
    for name, value, lo, hi in [('warmups', warmups, 1, 50),
                                 ('iterations', iterations, 1, 1000),
                                 ('samples', samples, 3, 51)]:
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError(f'invalid {name} limit')
    if type(case) is not ProfileCase or not callable(case.callable_fn) or \
       type(case.name) is not str or type(case.size) is not int or case.size <= 0 or \
       any(type(d) is not str or len(d) != 64 or any(x not in '0123456789abcdef' for x in d)
           for d in (case.fixture_sha256, case.source_sha256)):
        raise ValueError('invalid benchmark case')
    reference = case.callable_fn()
    if type(reference) is not str or len(reference) != 64 or any(x not in '0123456789abcdef' for x in reference):
        raise ValueError('output must be a digest')
    for _ in range(warmups):
        if case.callable_fn() != reference:
            raise RuntimeError('warmup output mismatch')
    durations: list[int] = []
    for _ in range(samples):
        start = clock()
        for _ in range(iterations):
            if case.callable_fn() != reference:
                raise RuntimeError('non-deterministic benchmark output')
        elapsed = clock() - start
        if type(elapsed) is not int or elapsed <= 0:
            raise RuntimeError('invalid monotonic timing sample')
        durations.append(max(1, math.ceil(elapsed / iterations)))
    ordered = sorted(durations)
    p95_index = math.ceil(0.95 * samples) - 1
    return ProfileMeasurement(case.name, case.size, case.fixture_sha256,
                              case.source_sha256, reference, warmups, iterations,
                              samples, ordered[0], int(statistics.median(ordered)),
                              ordered[p95_index], ordered[-1], tuple(durations))


def measurement_to_dict(measurement: ProfileMeasurement) -> dict:
    return asdict(measurement)

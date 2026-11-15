"""Stage 159: fail-closed evidence gates before a research backtest."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ReadinessReceipt:
    ready: bool
    blockers: tuple[str, ...]

def assess_readiness(*, snapshot_valid: bool, candles_valid: bool,
                     session_complete: bool, provenance_valid: bool,
                     costs_configured: bool, lookahead_checked: bool) -> ReadinessReceipt:
    flags = {'snapshot': snapshot_valid, 'candles': candles_valid,
             'session completeness': session_complete, 'provenance': provenance_valid,
             'execution costs': costs_configured, 'lookahead': lookahead_checked}
    blockers = tuple(name for name, value in flags.items() if value is not True)
    return ReadinessReceipt(not blockers, blockers)

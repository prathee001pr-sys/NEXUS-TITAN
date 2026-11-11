"""Stage128: fail-closed orchestration; research inventory only, never trade/backtest feed."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .stage125_nse_option_chain_snapshot import inspect_stage125_snapshot
from .stage126_snapshot_provenance import Stage126CaptureDeclaration, review_stage126, Stage126Review
from .stage127_quote_quality import review_stage127, Stage127Quality

@dataclass(frozen=True, slots=True)
class Stage128Acceptance:
    underlying: str
    expiry_date: str
    raw_sha256: str
    provenance: Stage126Review
    quality: Stage127Quality
    historical_backtest_approved: bool = False
    paper_trading_approved: bool = False
    live_trading_enabled: bool = False
    verdict: str = 'RESEARCH_INVENTORY_ONLY_NO_GO'

def inspect_stage128(raw: bytes, *, underlying: str, expiry_date: str, declaration: Stage126CaptureDeclaration) -> Stage128Acceptance:
    snapshot=inspect_stage125_snapshot(raw,underlying=underlying,expiry_date=expiry_date)
    provenance=review_stage126(snapshot,raw,declaration)
    quality=review_stage127(snapshot,provenance)
    return Stage128Acceptance(snapshot.underlying,snapshot.expiry_date,sha256(raw).hexdigest(),provenance,quality)

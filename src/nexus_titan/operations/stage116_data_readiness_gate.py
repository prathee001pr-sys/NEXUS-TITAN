"""Stage116: full Phase02 offline provenance/as-of/coverage acceptance gate.

This is a structural data-quality report only. It never promotes a source to
licensed/authentic, a strategy to ready, or a market/broker order to executable.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .stage111_phase01_acceptance import Stage111Phase01Report
from .stage112_fo_contract_master import Stage112Contract,review_stage112_master
from .stage113_fo_source_provenance import Stage113SourceManifest,review_stage113_csv
from .stage114_option_asof_alignment import Stage114Clock,review_stage114_asof
from .stage115_session_coverage import Stage115Session,review_stage115_coverage


class Stage116Blocked(ValueError):
    pass

_HASH=re.compile(r"[0-9a-f]{64}\Z",re.ASCII)


@dataclass(frozen=True,slots=True)
class Stage116Phase02Report:
    underlying: str
    trading_date: str
    predecessor_phase01_sha256: str
    stage112_master_sha256: str
    stage113_dataset_sha256: str
    stage114_snapshot_sha256: str
    stage115_coverage_sha256: str
    source_kind: str
    selected_quote_count: int
    missing_quote_minutes: int
    outside_session_rows: int
    single_chunk_coverage_complete: bool
    phase02_sha256: str
    data_rights_verified: bool = False
    licensed_market_data_verified: bool = False
    official_contract_calendar_verified: bool = False
    fifteen_year_coverage_verified: bool = False
    real_quote_liquidity_verified: bool = False
    strategy_promotion_enabled: bool = False
    trade_authorized: bool = False
    live_trading_enabled: bool = False
    verdict: str = "PHASE02_UNVERIFIED_DATA_FOUNDATION_ONLY_NO_GO"


def review_stage116_pipeline(
    predecessor: Stage111Phase01Report,
    contracts: list[Stage112Contract] | tuple[Stage112Contract,...],
    *, trading_date: str,
    manifest: Stage113SourceManifest,
    raw_bytes: bytes,
    clock: Stage114Clock,
    session: Stage115Session,
) -> Stage116Phase02Report:
    if type(predecessor) is not Stage111Phase01Report:
        raise Stage116Blocked("Exact Stage111 predecessor report required")
    if (predecessor.verdict!="PHASE01_SYNTHETIC_INTEGRATION_ONLY_NO_GO"
        or predecessor.indian_currency!="INR" or predecessor.crypto_currency!="USDT"
        or predecessor.symbol not in ("NIFTY","BANKNIFTY")
        or not all(type(x) is str and _HASH.fullmatch(x) for x in (
            predecessor.report_sha256,predecessor.stage108_sha256,
            predecessor.stage109_sha256,predecessor.stage110_sha256))
        or any((predecessor.independent_market_data_verified,
            predecessor.real_market_execution_verified,
            predecessor.independent_risk_veto_runtime_certified,
            predecessor.exchange_fee_breakdown_verified,
            predecessor.strategy_promotion_enabled,predecessor.trade_authorized,
            predecessor.live_trading_enabled))):
        raise Stage116Blocked("Predecessor must remain synthetic NO-GO")
    # Recompute all intermediate objects, so caller cannot sneak in forged
    # positive verification flags or disconnected intermediary fingerprints.
    try:
        master=review_stage112_master(contracts,trading_date=trading_date)
        if master.underlying!=predecessor.symbol:
            raise Stage116Blocked("Mixed Phase01/Phase02 underlying")
        data=review_stage113_csv(master,manifest,raw_bytes)
        snapshot=review_stage114_asof(master,data,clock)
        coverage=review_stage115_coverage(master,data,session)
    except ValueError as exc:
        raise Stage116Blocked(f"Phase02 data lineage, coverage or timing failure: {exc}") from exc
    if not (snapshot.master_sha256==coverage.master_sha256==master.master_sha256
        and snapshot.dataset_sha256==coverage.dataset_sha256==data.dataset_sha256
        and coverage.trading_date==snapshot.trading_date==master.trading_date
        and snapshot.selected_quote_count==len(master.contracts)
        and coverage.missing_quote_minutes>=0 and coverage.outside_session_rows>=0):
        raise Stage116Blocked("Cross-stage data QA digest or count mismatch")
    payload=["STAGE116_PHASE02_NO_GO_V1",predecessor.report_sha256,master.master_sha256,
             data.dataset_sha256,snapshot.snapshot_sha256,coverage.coverage_sha256,
             data.source_kind,coverage.chunk_coverage_complete]
    digest=sha256(json.dumps(payload,separators=(",", ":")).encode()).hexdigest()
    return Stage116Phase02Report(master.underlying,master.trading_date,predecessor.report_sha256,
        master.master_sha256,data.dataset_sha256,snapshot.snapshot_sha256,
        coverage.coverage_sha256,data.source_kind,snapshot.selected_quote_count,
        coverage.missing_quote_minutes,coverage.outside_session_rows,
        coverage.chunk_coverage_complete,digest)

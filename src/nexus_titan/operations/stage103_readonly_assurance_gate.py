"""Stage103: strict read-only Stage100–102 + Stage98 source-boundary join.

This is a synthetic research and audit fingerprint, NOT a trading signal,
margin approval, verified valuation, exchange check or production release.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re

from .stage98_dual_market_review import DualMarketReview
from .stage100_fo_reconciliation_gate import Stage100FOReconciliation
from .stage101_historical_bar_preflight import Stage101DataWindow
from .stage102_option_chain_preflight import Stage102ChainReview


class Stage103Blocked(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Stage103AssuranceReport:
    indian_account_id: str
    indian_journal_revision: int
    indian_journal_sha256: str
    crypto_account_id: str
    indian_currency: str
    crypto_currency: str
    underlying: str
    chain_expiry_date: str
    historical_window_sha256: str
    synthetic_chain_sha256: str
    expiry_scenario_sha256: str
    review_sha256: str
    synthetic_inputs_consistent: bool
    source_authenticity_verified: bool = False
    expiry_to_account_linkage_verified: bool = False
    broker_fills_reconciled: bool = False
    real_market_shadow_verified: bool = False
    live_trading_enabled: bool = False
    trade_authorized: bool = False
    verdict: str = "CROSS_STAGE_SYNTHETIC_INTEGRITY_ONLY_NO_GO"


_HEX = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z", re.ASCII)


def _digest(value: object) -> str:
    if type(value) is not str or not _HEX.fullmatch(value):
        raise Stage103Blocked("Checked input digest must be lowercase 64-char SHA-256")
    return value


def verify_stage103_readonly_assurance(
    fo: Stage100FOReconciliation,
    bars: Stage101DataWindow,
    chain: Stage102ChainReview,
    dual: DualMarketReview,
) -> Stage103AssuranceReport:
    """Cross-stage synthetic boundary report without granting execution rights.

    Stage100 scenario rows must include the option-chain's underlying and expiry.
    The Stage98 independent crypto report is only read, never used to net INR/USDT.
    """
    if (type(fo) is not Stage100FOReconciliation
            or type(bars) is not Stage101DataWindow
            or type(chain) is not Stage102ChainReview
            or type(dual) is not DualMarketReview):
        raise Stage103Blocked("Expected exactly Stage98/100/101/102 immutable report types")
    if (fo.market != "INDIAN_FO" or fo.currency != "INR"
            or fo.expiry_to_journal_linkage_verified is not False
            or fo.exchange_settlement_verified is not False
            or fo.broker_contract_note_verified is not False
            or fo.official_margin_verified is not False
            or fo.live_trading_enabled is not False
            or fo.executable is not False
            or fo.verdict != "ACCOUNT_CONSERVED_EXPIRY_SCENARIOS_UNLINKED_NO_GO"):
        raise Stage103Blocked("Stage100 authority or evidence boundary promoted")
    if (bars.symbol not in ("NIFTY", "BANKNIFTY")
            or bars.currency != "INR" or bars.timeframe != "1m"
            or bars.contiguous_one_minute_bars is not True
            or bars.verified_trading_calendar is not False
            or bars.independent_market_source_verified is not False
            or bars.fifteen_year_history_verified is not False
            or bars.live_trading_enabled is not False
            or bars.verdict != "SYNTHETIC_ONE_SESSION_ONLY_NO_GO"):
        raise Stage103Blocked("Stage101 must remain synthetic no-go")
    if (chain.underlying != bars.symbol or chain.currency != "INR"
            or chain.source_window_sha256 != bars.content_sha256
            or chain.structural_chain_valid is not True
            or chain.official_option_chain_verified is not False
            or chain.official_expiry_calendar_verified is not False
            or chain.executable_liquidity_verified is not False
            or chain.broker_order_authorized is not False
            or chain.live_trading_enabled is not False
            or chain.verdict != "SYNTHETIC_OPTION_CHAIN_STRUCTURE_ONLY_NO_GO"
            or chain.quote_count != 2 * chain.paired_strike_count
            or not 1 <= chain.paired_strike_count <= 50
            or type(chain.paired_strikes_paise) is not tuple):
        raise Stage103Blocked("Stage102 chain source, pair counts or authority mismatch")
    if (type(fo.journal_revision) is not int or fo.journal_revision < 0
            or type(fo.scenario_count) is not int or not 1 <= fo.scenario_count <= 50
            or type(fo.scenario_instrument_ids) is not tuple
            or len(fo.scenario_instrument_ids) != fo.scenario_count):
        raise Stage103Blocked("Stage100 invalid journal revision or scenario count")
    for digest in (fo.journal_sha256, fo.scenario_sha256, bars.content_sha256,
                   chain.chain_sha256, chain.source_window_sha256):
        _digest(digest)
    if (type(fo.account_id) is not str or not _ID.fullmatch(fo.account_id)
            or type(chain.expiry_date) is not str
            or type(chain.observed_at_ist) is not str
            or type(bars.last_asof_ist) is not str
            or type(bars.trading_date) is not str
            or not chain.observed_at_ist.startswith(bars.trading_date)
            or not bars.last_asof_ist.startswith(bars.trading_date)):
        raise Stage103Blocked("Invalid cross-stage identity or clock lineage")
    prefix = f"{bars.symbol}-{chain.expiry_date}-"
    if not any(type(cid) is str and (cid.startswith(prefix + "CE-") or cid.startswith(prefix + "PE-"))
               for cid in fo.scenario_instrument_ids):
        raise Stage103Blocked("No Stage99 scenario for the supplied underlying/expiry")
    try:
        last_bar = datetime.fromisoformat(bars.last_asof_ist)
        observed = datetime.fromisoformat(chain.observed_at_ist)
    except (TypeError, ValueError) as exc:
        raise Stage103Blocked("Malformed cross-stage as-of clock") from exc
    delta = (last_bar - observed).total_seconds()
    if (last_bar.utcoffset() != timedelta(hours=5, minutes=30)
            or observed.utcoffset() != timedelta(hours=5, minutes=30)
            or not 0 <= delta <= 30
            or type(chain.quote_staleness_seconds) is not int
            or chain.quote_staleness_seconds != int(delta)):
        raise Stage103Blocked("Stale or inconsistent cross-stage option-chain timestamp")
    if (dual.live_trading_enabled is not False
            or dual.real_market_shadow_validated is not False
            or dual.cross_currency_conversion_verified is not False
            or dual.combined_pnl_cents is not None
            or dual.combined_cash_cents is not None
            or dual.verdict != "SYNTHETIC_DUAL_MARKET_REVIEW_ONLY_NO_LIVE"
            or type(dual.indian) is not dict or type(dual.crypto) is not dict):
        raise Stage103Blocked("Stage98 dual-market boundary invalid or bypassed")
    indian = dual.indian
    crypto = dual.crypto
    if (indian.get("market") != "INDIAN_FO" or indian.get("currency") != "INR"
            or indian.get("account_id") != fo.account_id
            or indian.get("journal_sha256") != fo.journal_sha256
            or type(indian.get("journal_revision")) is not int
            or indian.get("journal_revision") != fo.journal_revision
            or type(indian.get("cash_cents")) is not int
            or indian.get("cash_cents") != fo.account_cash_cents
            or type(indian.get("remaining_cost_basis_cents")) is not int
            or indian.get("remaining_cost_basis_cents") != fo.account_cost_basis_cents
            or type(indian.get("realized_net_pnl_cents")) is not int
            or indian.get("realized_net_pnl_cents") != fo.account_realized_net_pnl_cents
            or indian.get("live_trading_enabled") is not False
            or indian.get("market_evidence_verified") is not False
            or type(indian.get("broker_orders_transmitted")) is not int
            or indian.get("broker_orders_transmitted") != 0
            or crypto.get("market") != "CRYPTO_PAPER"
            or crypto.get("currency") != "USDT"
            or crypto.get("live_trading_enabled") is not False
            or crypto.get("real_market_evidence_verified") is not False
            or type(crypto.get("exchange_orders_transmitted")) is not int
            or crypto.get("exchange_orders_transmitted") != 0
            or type(crypto.get("account_id")) is not str
            or not _ID.fullmatch(crypto["account_id"])
            or crypto["account_id"] == fo.account_id
            or type(crypto.get("journal_tip")) is not str
            or not _HEX.fullmatch(crypto["journal_tip"])
            or type(crypto.get("initial_cents")) is not int
            or type(crypto.get("cash_cents")) is not int
            or type(crypto.get("remaining_cost_basis_cents")) is not int
            or type(crypto.get("realized_net_pnl_cents")) is not int
            or crypto["cash_cents"] + crypto["remaining_cost_basis_cents"]
                != crypto["initial_cents"] + crypto["realized_net_pnl_cents"]):
        raise Stage103Blocked("Indian/crypto account, journal head or currency isolation failed")
    message = [
        "STAGE103_SYNTHETIC_BOUNDARY_V1", fo.account_id, fo.journal_revision,
        fo.journal_sha256, fo.scenario_sha256, bars.symbol,
        bars.trading_date, bars.content_sha256, chain.expiry_date,
        chain.chain_sha256, crypto["account_id"], crypto["journal_tip"],
    ]
    fingerprint = hashlib.sha256(json.dumps(message, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return Stage103AssuranceReport(
        indian_account_id=fo.account_id, indian_journal_revision=fo.journal_revision,
        indian_journal_sha256=fo.journal_sha256,
        crypto_account_id=crypto["account_id"], indian_currency="INR", crypto_currency="USDT",
        underlying=bars.symbol, chain_expiry_date=chain.expiry_date,
        historical_window_sha256=bars.content_sha256, synthetic_chain_sha256=chain.chain_sha256,
        expiry_scenario_sha256=fo.scenario_sha256, review_sha256=fingerprint,
        synthetic_inputs_consistent=True,
    )

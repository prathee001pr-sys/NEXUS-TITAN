"""Stage100: selected F&O account vs synthetic expiry *review* boundary.

The Stage96 replay-checked account is the sole journal authority. Stage99
payoffs are unrelated unverified scenarios, not book entries or official NSE
settlement receipts. Never combine the two into realized P&L or permissions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re

from .stage96_accounting_review import FOAccountingReview
from .stage99_expiry_margin_review import Stage99BatchReview, Stage99SyntheticReview


class Stage100Blocked(ValueError):
    """A read-only reconciliation boundary must fail closed."""


_MAX_CENTS = 10**15
_HEX = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)


def _integer(value: object, *, positive: bool = False, signed: bool = False) -> int:
    if type(value) is not int or abs(value) > _MAX_CENTS or (positive and value <= 0) or (not signed and value < 0):
        raise Stage100Blocked("Invalid bounded integer-cent accounting")
    return value


@dataclass(frozen=True, slots=True)
class Stage100FOReconciliation:
    account_id: str
    market: str
    currency: str
    journal_revision: int
    journal_sha256: str
    account_cash_cents: int
    account_cost_basis_cents: int
    account_realized_net_pnl_cents: int
    scenario_count: int
    scenario_sha256: str
    scenario_instrument_ids: tuple[str, ...]
    synthetic_equity_cents: int | None
    open_valuation_available: bool
    expiry_to_journal_linkage_verified: bool = False
    exchange_settlement_verified: bool = False
    broker_contract_note_verified: bool = False
    official_margin_verified: bool = False
    live_trading_enabled: bool = False
    executable: bool = False
    verdict: str = "ACCOUNT_CONSERVED_EXPIRY_SCENARIOS_UNLINKED_NO_GO"


def reconcile_fo_with_expiry_scenarios(
    account: FOAccountingReview, batch: Stage99BatchReview
) -> Stage100FOReconciliation:
    """Check both inputs without inventing a cross-ledger settlement match.

    Neither this function nor its outputs open a broker connection or mutate a
    paper ledger. An independently anchored fill/contract-note join is absent.
    """
    if type(account) is not FOAccountingReview or type(batch) is not Stage99BatchReview:
        raise Stage100Blocked("Exact replay-checked account and synthetic batch types required")
    if (account.market != "INDIAN_FO" or account.currency != "INR"
            or account.live_trading_enabled is not False
            or account.market_evidence_verified is not False
            or type(account.broker_orders_transmitted) is not int
            or account.broker_orders_transmitted != 0):
        raise Stage100Blocked("Invalid Indian F&O market, currency, or authority boundary")
    if (type(account.account_id) is not str or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", account.account_id)
            or type(account.journal_sha256) is not str or not _HEX.fullmatch(account.journal_sha256)):
        raise Stage100Blocked("Invalid replay-checked account identity or journal digest")
    _integer(account.journal_revision)
    for name in ("initial_cents", "cash_cents", "remaining_cost_basis_cents", "total_paid_execution_fees_cents"):
        _integer(getattr(account, name))
    for name in ("realized_net_pnl_cents", "realized_gross_pnl_cents"):
        _integer(getattr(account, name), signed=True)
    for name in ("position_count", "closed_position_count"):
        _integer(getattr(account, name))
    if account.cash_cents + account.remaining_cost_basis_cents != account.initial_cents + account.realized_net_pnl_cents:
        raise Stage100Blocked("Cash, held basis and realized journal P&L do not conserve")
    if account.position_count == 0 and account.remaining_cost_basis_cents != 0:
        raise Stage100Blocked("Flat account cannot carry remaining position cost basis")
    if account.unrealized_net_pnl_cents is None:
        if account.synthetic_equity_cents is not None or account.net_pnl_cents is not None:
            raise Stage100Blocked("Unmarked open position cannot have fabricated synthetic equity/P&L")
    else:
        _integer(account.unrealized_net_pnl_cents, signed=True)
        if account.synthetic_equity_cents is None or account.net_pnl_cents is None:
            raise Stage100Blocked("Partial synthetic mark must fail closed")
        _integer(account.synthetic_equity_cents, signed=True)
        _integer(account.net_pnl_cents, signed=True)
        if (account.net_pnl_cents != account.realized_net_pnl_cents + account.unrealized_net_pnl_cents
                or account.synthetic_equity_cents != account.initial_cents + account.net_pnl_cents):
            raise Stage100Blocked("Synthetic MTM equity or net P&L identity broken")
    if (account.profit_factor is not None or account.expectancy_cents is not None
            or account.max_drawdown_percent is not None):
        raise Stage100Blocked("Official performance statistics not evidenced by synthetic snapshots")
    if (batch.market != "INDIAN_FO" or batch.currency != "INR"
            or batch.authentic_margin_verified is not False
            or batch.actual_settlement_verified is not False
            or batch.combined_live_execution_authorized is not False
            or batch.combined_realized_pnl is not None
            or batch.verdict != "SYNTHETIC_BATCH_PREVIEW_ONLY_NO_GO"
            or type(batch.cases) is not tuple or type(batch.count) is not int
            or not (1 <= batch.count == len(batch.cases) <= 50)):
        raise Stage100Blocked("Invalid or unexpectedly promoted expiry scenario batch")
    seen: set[str] = set()
    for item in batch.cases:
        if type(item) is not Stage99SyntheticReview:
            raise Stage100Blocked("Scenario row type must match Stage99 exactly")
        if (item.market != "INDIAN_FO" or item.currency != "INR"
                or item.official_margin_verified is not False
                or item.exchange_settlement_verified is not False
                or item.actual_broker_reconciled is not False
                or item.can_promote_or_execute is not False
                or item.live_trading_enabled is not False
                or item.verdict != "SYNTHETIC_PREVIEW_ONLY_NO_GO"
                or item.instrument_type not in ("OPTIONS_LONG", "OPTIONS_SHORT", "FUTURES")
                or type(item.contract_id) is not str
                or re.fullmatch(r"(NIFTY|BANKNIFTY)-\d{4}-\d{2}-\d{2}-(CE|PE|FUT)(?:-\d+(?:\.\d+)?)?", item.contract_id) is None
                or item.contract_id in seen or type(item.lots) is not int or item.lots <= 0):
            raise Stage100Blocked("Invalid or duplicate expiry scenario / authority boundary")
        if (type(item.indicative_margin_blocked) not in (int, float)
                or not math.isfinite(item.indicative_margin_blocked)
                or not 0 <= item.indicative_margin_blocked <= 10**12):
            raise Stage100Blocked("Invalid indicative synthetic margin")
        for estimate in (item.synthetic_gross_pnl, item.synthetic_net_pnl):
            if estimate is not None and (type(estimate) not in (int, float)
                    or not math.isfinite(estimate) or abs(estimate) > 10**12):
                raise Stage100Blocked("Invalid bounded synthetic settlement amount")
        if item.instrument_type == "FUTURES" and item.synthetic_net_pnl is not None:
            raise Stage100Blocked("Futures final net P&L not independently evidenced")
        seen.add(item.contract_id)
    payload = json.dumps([asdict(x) for x in batch.cases], sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return Stage100FOReconciliation(
        account_id=account.account_id, market="INDIAN_FO", currency="INR",
        journal_revision=account.journal_revision, journal_sha256=account.journal_sha256,
        account_cash_cents=account.cash_cents,
        account_cost_basis_cents=account.remaining_cost_basis_cents,
        account_realized_net_pnl_cents=account.realized_net_pnl_cents,
        scenario_count=batch.count, scenario_sha256=digest,
        scenario_instrument_ids=tuple(item.contract_id for item in batch.cases),
        synthetic_equity_cents=account.synthetic_equity_cents,
        open_valuation_available=account.unrealized_net_pnl_cents is not None,
    )

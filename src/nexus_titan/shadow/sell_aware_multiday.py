"""Stage 25: versioned SELL-aware, read-only research daily reconciliation.

Only Stage19 BUY events with explicit Stage25 premium/fee/time metadata,
and Stage24 audited long-option exits, can enter this journal. Legacy BUY
events without the needed timestamps are BLOCKED, never guessed.

Calendar, broker charges and evidence are user-supplied/synthetic. This
module makes no broker calls or strategy-promotion decisions.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.shadow.long_option_exit_research import (
    _fifo_consume, _replay_account,
)
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)

_INDIA = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class LongResearchDay:
    session_date: date
    opening_cash: float
    closing_cash: float
    cash_delta: float
    buy_premium: float
    buy_fees: float
    sell_proceeds: float
    sell_fees: float
    bought_quantity: int
    sold_quantity: int
    closing_long_quantity: int
    remaining_cost_basis: float
    realized_net_pnl_today: float
    cumulative_realized_net_pnl: float
    external_source_verified: bool = False


@dataclass(frozen=True, slots=True)
class LongResearchDailyJournal:
    account_id: str
    days: tuple[LongResearchDay, ...]
    ending_cash: float
    remaining_long_quantity: int
    remaining_cost_basis: float
    cumulative_realized_net_pnl: float
    incomplete_mark_to_market: bool
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


@dataclass(frozen=True, slots=True)
class LongResearchDayCloseClaim:
    session_date: date
    observed_at: datetime
    account_id: str
    closing_cash: float
    closing_long_quantity: int
    remaining_cost_basis: float
    cumulative_realized_net_pnl: float
    evidence_reference: str


@dataclass(frozen=True, slots=True)
class LongResearchDailyValidation:
    account_id: str
    day_count: int
    discrepancies: tuple[str, ...]
    data_source_authenticity_verified: bool = False
    independent_broker_reconciliation_verified: bool = False
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False

    @property
    def is_structurally_valid(self) -> bool:
        return not self.discrepancies


def _utc_session(raw: object, calendar: MarketCalendar, label: str) -> date:
    if not isinstance(raw, str):
        raise ResearchLedgerError(f"{label} lacks a timestamp; legacy source not supported")
    try:
        stamp = datetime.fromisoformat(raw)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
    except ValueError as exc:
        raise ResearchLedgerError(f"{label} timestamp invalid") from exc
    if not calendar.is_open(stamp):
        raise ResearchLedgerError(f"{label} outside reviewed market session")
    return stamp.astimezone(_INDIA).date()


def _integer(event: dict, name: str, *, positive: bool = False) -> int:
    val = event.get(name)
    if (isinstance(val, bool) or not isinstance(val, int)
            or val < (1 if positive else 0)):
        raise ResearchLedgerError(f"Invalid audited {name}")
    return val


def reconstruct_sell_aware_daily_journal(
    ledger: DurableResearchShadowLedger,
    *,
    calendar: MarketCalendar,
    max_calendar_days: int = 366,
) -> LongResearchDailyJournal:
    """Rebuild exact session cash/inventory/P&L from validated SQLite events.

    The **entire audit** must reconcile to the persisted Stage24 FIFO state.
    Daily time and fee split fields must exist; no inference for old records.
    No unrealized valuation is invented while options are still held.
    """
    if not isinstance(ledger, DurableResearchShadowLedger):
        raise ResearchLedgerError("Stage19 research ledger is required")
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise ResearchLedgerError("Asia/Kolkata reviewed exchange calendar required")
    if (isinstance(max_calendar_days, bool) or not isinstance(max_calendar_days, int)
            or not 1 <= max_calendar_days <= 3660):
        raise ResearchLedgerError("max_calendar_days must be 1 to 3660")
    with ledger._transaction() as con:
        _replay_account(ledger, con)
        account = con.execute(
            "SELECT initial_cents,cash_cents,reserved_cents FROM accounts WHERE account_id=?",
            (ledger.account_id,),
        ).fetchone()
        if account["reserved_cents"] or con.execute(
            "SELECT 1 FROM reservations WHERE account_id=? AND status='OPEN' LIMIT 1",
            (ledger.account_id,),
        ).fetchone():
            raise ResearchLedgerError("Unresolved research reservations block day-close reconciliation")
        cash = account["initial_cents"]
        realized_total = 0
        lots: dict[str, list[list[int]]] = {}
        events: list[tuple[date, str, dict]] = []
        previous: datetime | None = None
        for row in con.execute(
            "SELECT payload_json FROM audit WHERE account_id=? ORDER BY sequence ASC",
            (ledger.account_id,),
        ):
            event = json.loads(row["payload_json"])["event"]
            kind = event["type"]
            if kind not in ("SETTLE_BUY", "SETTLE_LONG_EXIT"):
                if kind not in ("INITIAL", "RESERVE_BUY", "CANCEL"):
                    raise ResearchLedgerError("Unknown audited event in long daily journal")
                continue
            field = "fill_observed_at_utc" if kind == "SETTLE_BUY" else "as_of_utc"
            day = _utc_session(event.get(field), calendar, kind)
            stamp = datetime.fromisoformat(event[field])
            if previous is not None and stamp < previous:
                raise ResearchLedgerError("Non-monotone executed event chronology")
            previous = stamp
            if kind == "SETTLE_BUY":
                premium = _integer(event, "buy_premium_cents")
                fee = _integer(event, "buy_fees_cents")
                debit = _integer(event, "debit_cents")
                if premium + fee != debit:
                    raise ResearchLedgerError("BUY event premium + fee does not equal debit")
            events.append((day, kind, event))

        if not events:
            if account["cash_cents"] != cash:
                raise ResearchLedgerError("Cash changed with no auditable trades")
            return LongResearchDailyJournal(
                ledger.account_id, (), cash / 100, 0, 0.0, 0.0, False,
            )
        start, end = events[0][0], events[-1][0]
        if (end - start).days + 1 > max_calendar_days:
            raise ResearchLedgerError("Daily research evidence exceeds calendar-span limit")

        grouped: dict[date, list[tuple[str, dict]]] = {}
        for day, kind, e in events:
            grouped.setdefault(day, []).append((kind, e))
        days: list[LongResearchDay] = []
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            if not calendar.is_trading_day(day):
                if day in grouped:
                    raise ResearchLedgerError("Research execution on non-trading calendar day")
                continue
            opening = cash
            buy_premium = buy_fee = sell_gross = sell_fee = bought = sold = today_pnl = 0
            for kind, e in grouped.get(day, ()):
                oid = e.get("order_id")
                res = con.execute(
                    "SELECT instrument_key,filled_quantity,status FROM reservations "
                    "WHERE account_id=? AND order_id=?",
                    (ledger.account_id, oid),
                ).fetchone()
                if res is None or res["status"] != "CLOSED":
                    raise ResearchLedgerError("Execution missing matching terminal order")
                key = res["instrument_key"]
                qty = _integer(e, "filled_quantity")
                if qty != res["filled_quantity"]:
                    raise ResearchLedgerError("Audited filled_quantity differs from stored order")
                if kind == "SETTLE_BUY":
                    premium = _integer(e, "buy_premium_cents")
                    fee = _integer(e, "buy_fees_cents")
                    debit = _integer(e, "debit_cents")
                    cash -= debit
                    buy_premium += premium
                    buy_fee += fee
                    bought += qty
                    if qty:
                        lots.setdefault(key, []).append([qty, debit])
                else:
                    if e.get("instrument_key") != key:
                        raise ResearchLedgerError("SELL instrument identity mismatch")
                    gross = _integer(e, "gross_proceeds_cents", positive=True)
                    fee = _integer(e, "sell_fees_cents")
                    net = e.get("net_proceeds_cents")
                    attributed = _integer(e, "attributed_buy_cost_cents")
                    pnl = e.get("realized_net_pnl_cents")
                    if (isinstance(net, bool) or not isinstance(net, int)
                            or isinstance(pnl, bool) or not isinstance(pnl, int)
                            or gross - fee != net or qty <= 0):
                        raise ResearchLedgerError("SELL audited net cashflow inconsistent")
                    basis = _fifo_consume(lots.setdefault(key, []), qty)
                    if basis != attributed or pnl != net - basis:
                        raise ResearchLedgerError("SELL FIFO cost attribution changed")
                    cash += net
                    sell_gross += gross
                    sell_fee += fee
                    sold += qty
                    today_pnl += pnl
                    realized_total += pnl
            if cash < 0:
                raise ResearchLedgerError("Negative virtual research cash during reconstruction")
            qty_left = sum(q for entries in lots.values() for q, _ in entries)
            basis_left = sum(c for entries in lots.values() for _, c in entries)
            days.append(LongResearchDay(
                day, opening / 100, cash / 100, (cash - opening) / 100,
                buy_premium / 100, buy_fee / 100,
                sell_gross / 100, sell_fee / 100,
                bought, sold, qty_left, basis_left / 100,
                today_pnl / 100, realized_total / 100,
            ))
        if cash != account["cash_cents"]:
            raise ResearchLedgerError("Daily event cashflow does not match SQLite account")
        # Use the same transaction to avoid nested transaction deadlocks.
        final_qty = sum(q for entries in lots.values() for q, _ in entries)
        final_basis = sum(c for entries in lots.values() for _, c in entries)
        inventory = {
            r["instrument_key"]: r["quantity"] for r in con.execute(
                "SELECT instrument_key,quantity FROM inventory WHERE account_id=?",
                (ledger.account_id,),
            )
        }
        if {k: sum(q for q, _ in v) for k, v in lots.items() if v} != {
            k: v for k, v in inventory.items() if v
        }:
            raise ResearchLedgerError("Daily replay inventory differs from SQLite inventory")
        return LongResearchDailyJournal(
            ledger.account_id, tuple(days), cash / 100, final_qty,
            final_basis / 100, realized_total / 100, final_qty > 0,
        )


def inspect_sell_aware_day_closes(
    ledger: DurableResearchShadowLedger,
    *,
    calendar: MarketCalendar,
    claims: list[LongResearchDayCloseClaim] | tuple[LongResearchDayCloseClaim, ...],
) -> LongResearchDailyValidation:
    """Compare operator day-close assertions with ledger-derived session closes.

    Requires **every configured trading day** in the entire audited range.
    Source authenticity and live/paper broker reconciliation remain unverified.
    """
    if not isinstance(claims, (list, tuple)):
        raise ResearchLedgerError("Day-close claims must be list or tuple")
    journal = reconstruct_sell_aware_daily_journal(ledger, calendar=calendar)
    issues: list[str] = []
    if not journal.days:
        issues.append("No audited BUY/SELL day-close evidence")
    if len(claims) != len(journal.days):
        issues.append("Missing or extra configured trading-session day-close claims")
    for index, day in enumerate(journal.days):
        if index >= len(claims):
            break
        c = claims[index]
        if not isinstance(c, LongResearchDayCloseClaim):
            issues.append(f"Day {index}: unsupported close claim")
            continue
        if c.session_date != day.session_date or c.account_id != ledger.account_id:
            issues.append(f"Day {index}: wrong date/account or out-of-order day-close")
        if (not isinstance(c.observed_at, datetime) or c.observed_at.tzinfo is None
                or c.observed_at.utcoffset() is None
                or c.observed_at.astimezone(_INDIA).date() != day.session_date):
            issues.append(f"Day {index}: invalid timezone-aware local observation")
        else:
            sessions = calendar.sessions_for_date(day.session_date)
            if sessions and c.observed_at.astimezone(_INDIA).time() < max(s.closes for s in sessions):
                issues.append(f"Day {index}: observation before exchange session close")
        if not isinstance(c.evidence_reference, str) or not c.evidence_reference.strip():
            issues.append(f"Day {index}: empty claimed evidence reference")
        if (isinstance(c.closing_long_quantity, bool)
                or not isinstance(c.closing_long_quantity, int)
                or c.closing_long_quantity != day.closing_long_quantity):
            issues.append(f"Day {index}: unmatched long inventory")
        for label, value, expected in (
            ("cash", c.closing_cash, day.closing_cash),
            ("FIFO cost basis", c.remaining_cost_basis, day.remaining_cost_basis),
            ("realized P&L", c.cumulative_realized_net_pnl, day.cumulative_realized_net_pnl),
        ):
            try:
                if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
                    raise ValueError
                actual = Decimal(str(value))
                target = Decimal(str(expected))
                same = (
                    actual.is_finite()
                    and (actual >= 0 or label == "realized P&L")
                    and actual * 100 == (actual * 100).to_integral_value()
                    and actual == target
                )
            except (ValueError, InvalidOperation):
                same = False
            if not same:
                issues.append(f"Day {index}: {label} mismatch")
    return LongResearchDailyValidation(
        ledger.account_id, len(journal.days), tuple(issues),
    )

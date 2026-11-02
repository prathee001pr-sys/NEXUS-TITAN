"""Stage 24: atomic SELL-to-close accounting for historical *long* option research.

This is an opt-in adapter on the isolated Stage19 SQLite research ledger.
It does not alter existing BUY code, the authoritative risk policy, brokers,
paper mode configuration, real trading or strategy permissions. Stage19 audit
BUY records provide original total purchase cost (including estimated fees).
All source prices/fees and evidence remain untrusted/synthetic research inputs.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from nexus_titan.core.permissions import Action, Decision, decide
from nexus_titan.cost.charges import IndianCostConfig
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_history import ResearchOptionChainHistory
from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError, _instrument_key,
    _money_cents, _valid_contract, _valid_id,
)
from nexus_titan.simulation.options_order_reconciliation import (
    ResearchFillEvent, reconcile_options_research_order,
)
from nexus_titan.simulation.options_research_execution import (
    OptionDisplayedDepth, simulate_historical_option_fill,
)


@dataclass(frozen=True, slots=True)
class ResearchLongPosition:
    instrument_key: str
    quantity: int
    remaining_cost_basis: float
    realized_net_pnl: float


@dataclass(frozen=True, slots=True)
class ResearchLongPortfolioReport:
    account_id: str
    cash_balance: float
    reserved_cash: float
    positions: tuple[ResearchLongPosition, ...]
    cumulative_realized_net_pnl: float
    completed_exit_count: int
    note: str = "Research-only FIFO; no unrealized MTM, tax, verified broker receipts or live trading."
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


@dataclass(frozen=True, slots=True)
class ResearchLongExitResult:
    order_id: str
    status: Literal["FILLED", "PARTIAL", "UNFILLED"]
    requested_quantity: int
    filled_quantity: int
    gross_proceeds: float
    sell_fees: float
    attributed_buy_cost: float
    realized_net_pnl: float
    cash_after: float
    remaining_inventory: int
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


def _fifo_consume(lots: list[list[int]], quantity: int) -> int:
    """Consume oldest cost-including-fee lots; keep cents exact on final slice."""
    remaining = quantity
    basis = 0
    while remaining > 0:
        if not lots:
            raise ResearchLedgerError("Insufficient long-option inventory / missing cost basis")
        qty, cents = lots[0]
        if qty <= 0 or cents < 0:
            raise ResearchLedgerError("Corrupt FIFO lot")
        taken = min(remaining, qty)
        allocated = cents if taken == qty else cents * taken // qty
        basis += allocated
        remaining -= taken
        if taken == qty:
            lots.pop(0)
        else:
            lots[0] = [qty - taken, cents - allocated]
    return basis


def _replay_account(ledger: DurableResearchShadowLedger, con) -> tuple[dict[str, list[list[int]]], dict[str, int], int]:
    """Reconcile original BUY debits and new SELL exits back to *actual* SQLite.

    Stage19's hash/post-state checks run first. This additionally checks that
    all remaining quantities have auditable purchased cost, every exit's
    recorded basis/net/P&L match FIFO replay and cash = initial + cashflows.
    Unsupported direct DB inventory or missing basis fails closed.
    """
    ledger._verify(con)
    account = con.execute(
        "SELECT initial_cents,cash_cents,reserved_cents FROM accounts WHERE account_id=?",
        (ledger.account_id,),
    ).fetchone()
    cash_expected = account["initial_cents"]
    lots: dict[str, list[list[int]]] = {}
    realized: dict[str, int] = {}
    exit_count = 0
    last_order_timestamp: datetime | None = None
    for row in con.execute(
        "SELECT payload_json FROM audit WHERE account_id=? ORDER BY sequence",
        (ledger.account_id,),
    ):
        try:
            event = json.loads(row["payload_json"])["event"]
            kind = event["type"]
        except (KeyError, ValueError, TypeError) as exc:
            raise ResearchLedgerError("Invalid research FIFO audit record") from exc
        if kind == "SETTLE_BUY":
            oid = event.get("order_id")
            entry = con.execute(
                "SELECT instrument_key,filled_quantity,status,as_of_utc FROM reservations "
                "WHERE account_id=? AND order_id=?", (ledger.account_id, oid),
            ).fetchone()
            if entry is None or entry["status"] != "CLOSED":
                raise ResearchLedgerError("BUY record not linked to a closed reservation")
            qty = event.get("filled_quantity")
            debit = event.get("debit_cents")
            if (isinstance(qty, bool) or not isinstance(qty, int) or qty < 0
                    or isinstance(debit, bool) or not isinstance(debit, int) or debit < 0
                    or qty != entry["filled_quantity"] or (qty == 0 and debit != 0)
                    or (qty > 0 and debit == 0)):
                raise ResearchLedgerError("BUY quantity/cost basis inconsistent")
            try:
                at = datetime.fromisoformat(entry["as_of_utc"])
                if at.tzinfo is None or at.utcoffset() is None:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ResearchLedgerError("BUY audit timestamp invalid") from exc
            if last_order_timestamp is not None and at < last_order_timestamp:
                raise ResearchLedgerError("BUY/SELL research executions out of chronological order")
            last_order_timestamp = at
            cash_expected -= debit
            if qty:
                lots.setdefault(entry["instrument_key"], []).append([qty, debit])
        elif kind == "SETTLE_LONG_EXIT":
            key = event.get("instrument_key")
            order_id = event.get("order_id")
            exit_row = con.execute(
                "SELECT filled_quantity,status,max_price_cents FROM reservations "
                "WHERE account_id=? AND order_id=?", (ledger.account_id, order_id),
            ).fetchone()
            qty = event.get("filled_quantity")
            gross = event.get("gross_proceeds_cents")
            fee = event.get("sell_fees_cents")
            net = event.get("net_proceeds_cents")
            charged_basis = event.get("attributed_buy_cost_cents")
            pnl = event.get("realized_net_pnl_cents")
            if (not isinstance(key, str) or not key
                    or exit_row is None or exit_row["status"] != "CLOSED"
                    or exit_row["max_price_cents"] != 0
                    or any(isinstance(v, bool) or not isinstance(v, int) for v in (qty, gross, fee, net, charged_basis, pnl))
                    or qty <= 0 or gross <= 0 or fee < 0 or qty != exit_row["filled_quantity"]):
                raise ResearchLedgerError("SELL research audit fields invalid")
            try:
                at = datetime.fromisoformat(event["as_of_utc"])
                if at.tzinfo is None or at.utcoffset() is None:
                    raise ValueError
            except (TypeError, KeyError, ValueError) as exc:
                raise ResearchLedgerError("SELL audit timestamp invalid") from exc
            if last_order_timestamp is not None and at < last_order_timestamp:
                raise ResearchLedgerError("BUY/SELL research executions out of chronological order")
            last_order_timestamp = at
            replay_cost = _fifo_consume(lots.setdefault(key, []), qty)
            if charged_basis != replay_cost or gross - fee != net or net - replay_cost != pnl:
                raise ResearchLedgerError("SELL FIFO cost / cash / net P&L does not reconcile")
            ids = event.get("event_ids")
            if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
                raise ResearchLedgerError("SELL audit missing unique event IDs")
            for event_id in ids:
                marker = con.execute(
                    "SELECT order_id FROM replay_ids WHERE account_id=? AND event_id=?",
                    (ledger.account_id, event_id),
                ).fetchone()
                if marker is None or marker["order_id"] != order_id:
                    raise ResearchLedgerError("SELL replay event not persisted")
            cash_expected += net
            realized[key] = realized.get(key, 0) + pnl
            exit_count += 1
        elif kind not in ("INITIAL", "RESERVE_BUY", "CANCEL"):
            raise ResearchLedgerError("Unknown research cash-affecting event; FIFO attribution blocked")

    db_inventory = {
        row["instrument_key"]: row["quantity"] for row in con.execute(
            "SELECT instrument_key,quantity FROM inventory WHERE account_id=?",
            (ledger.account_id,),
        )
    }
    rebuilt_inventory = {
        key: sum(q for q, _ in parts) for key, parts in lots.items() if parts
    }
    if (cash_expected != account["cash_cents"]
            or {k: v for k, v in db_inventory.items() if v != 0} != rebuilt_inventory):
        raise ResearchLedgerError("Historical cash or inventory cannot be reconciled to FIFO audit")
    return lots, realized, exit_count


def report_research_long_portfolio(ledger: DurableResearchShadowLedger) -> ResearchLongPortfolioReport:
    """Read-only, local research inventory/cost basis and *realized* net P&L.

    An open long option still has unknown market value. Do NOT interpret cash
    alone, or realized net P&L, as whole-account performance or net equity.
    """
    if not isinstance(ledger, DurableResearchShadowLedger):
        raise ResearchLedgerError("Durable research ledger required")
    with ledger._transaction() as con:
        lots, realized, count = _replay_account(ledger, con)
        row = con.execute(
            "SELECT cash_cents,reserved_cents FROM accounts WHERE account_id=?",
            (ledger.account_id,),
        ).fetchone()
        keys = sorted(set(lots) | set(realized))
        return ResearchLongPortfolioReport(
            account_id=ledger.account_id,
            cash_balance=row["cash_cents"] / 100,
            reserved_cash=row["reserved_cents"] / 100,
            positions=tuple(ResearchLongPosition(
                instrument_key=key, quantity=sum(q for q, _ in lots.get(key, [])),
                remaining_cost_basis=sum(c for _, c in lots.get(key, [])) / 100,
                realized_net_pnl=realized.get(key, 0) / 100,
            ) for key in keys),
            cumulative_realized_net_pnl=sum(realized.values()) / 100,
            completed_exit_count=count,
        )


def simulate_and_settle_long_exit(
    *,
    ledger: DurableResearchShadowLedger,
    order_id: str,
    event_id: str,
    history: ResearchOptionChainHistory,
    contract: PointInTimeContractSpec,
    calendar: MarketCalendar,
    observed_at: datetime,
    strike: float,
    option_type: Literal["CE", "PE"],
    lots: int,
    depth: OptionDisplayedDepth,
    paper_trading_enabled: bool = False,
    costs: IndianCostConfig | None = None,
) -> ResearchLongExitResult:
    """Simulate a SELL exit *only* of existing long option inventory.

    Precheck source/depth through Stage17, then atomically reconcile Stage18,
    consume FIFO buy costs, credit/debit net proceeds and journal the exit.
    No order is transmitted. An UNFILLED attempt does not mutate the ledger.
    """
    if not isinstance(paper_trading_enabled, bool) or decide(
        Action.PAPER_TRADE, paper_trading_enabled=paper_trading_enabled
    ) is not Decision.ALLOW:
        raise ResearchLedgerError("Paper research permission denied; explicit opt-in required")
    if not isinstance(ledger, DurableResearchShadowLedger):
        raise ResearchLedgerError("Durable research ledger required")
    oid = _valid_id(order_id, "order_id")
    eid = _valid_id(event_id, "event_id")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ResearchLedgerError("Timezone-aware exit observation required")
    _valid_contract(contract, observed_at)
    key = _instrument_key(contract, strike, option_type)
    if isinstance(lots, bool) or not isinstance(lots, int) or not 1 <= lots <= contract.max_lots_per_trade:
        raise ResearchLedgerError("Exit requested_lots invalid")
    requested = lots * contract.lot_size
    if requested > contract.freeze_quantity:
        raise ResearchLedgerError("Exit exceeds contract freeze quantity")
    if not isinstance(history, ResearchOptionChainHistory) or history.approved_for_strategy_promotion:
        raise ResearchLedgerError("Validated research-only history required")
    if not isinstance(depth, OptionDisplayedDepth) or not depth.source_declared_verified:
        raise ResearchLedgerError("Declared matched displayed-depth evidence required")
    if costs is not None and not isinstance(costs, IndianCostConfig):
        raise ResearchLedgerError("Invalid costs configuration")

    # Stage17 rechecks original snapshot history and displayed depth freshness
    # before any chance of persistent account mutation.
    fragment = simulate_historical_option_fill(
        history, contract=contract, calendar=calendar, observed_at=observed_at,
        strike=strike, option_type=option_type, side="SELL", lots=lots,
        depth=depth, costs=costs,
    )
    if fragment.live_orders_transmitted or fragment.approved_for_strategy_promotion:
        raise ResearchLedgerError("Live/promotion boundary violated")
    if fragment.filled_quantity == 0:
        # No fake SELL, no phantom fee, no replay ID consumed.
        with ledger._transaction() as con:
            fifo, _, _ = _replay_account(ledger, con)
            owned = sum(q for q, _ in fifo.get(key, []))
            if owned < requested:
                raise ResearchLedgerError("Insufficient long-option inventory for requested exit")
            if con.execute(
                "SELECT 1 FROM reservations WHERE account_id=? AND order_id=?",
                (ledger.account_id, oid),
            ).fetchone():
                raise ResearchLedgerError("Duplicate/replayed exit order_id")
        return ResearchLongExitResult(
            oid, "UNFILLED", requested, 0, 0.0, 0.0, 0.0, 0.0,
            ledger.status().cash_balance, owned,
        )

    event = ResearchFillEvent(event_id=eid, observed_at=observed_at, fragment=fragment)
    with ledger._transaction() as con:
        fifo, _, _ = _replay_account(ledger, con)
        owned = sum(q for q, _ in fifo.get(key, []))
        if owned < requested:
            raise ResearchLedgerError("Insufficient long-option inventory for requested exit")
        if con.execute(
            "SELECT 1 FROM reservations WHERE account_id=? AND order_id=?",
            (ledger.account_id, oid),
        ).fetchone():
            raise ResearchLedgerError("Duplicate/replayed exit order_id")
        if con.execute(
            "SELECT 1 FROM replay_ids WHERE account_id=? AND event_id=?",
            (ledger.account_id, eid),
        ).fetchone():
            raise ResearchLedgerError("Duplicate/replayed exit event_id")

        account = con.execute(
            "SELECT cash_cents,reserved_cents FROM accounts WHERE account_id=?",
            (ledger.account_id,),
        ).fetchone()
        statement = reconcile_options_research_order(
            [event], order_id=oid, contract=contract, strike=strike,
            option_type=option_type, side="SELL", requested_lots=lots,
            starting_cash=account["cash_cents"] / 100,
            starting_inventory_quantity=owned, cost_config=costs,
        )
        if statement.filled_quantity != fragment.filled_quantity or statement.live_orders_transmitted or statement.approved_for_strategy_promotion:
            raise ResearchLedgerError("Reconciled SELL execution mismatch or invalid permission")
        gross = _money_cents(statement.filled_notional, "gross_proceeds", allow_zero=False)
        fees = _money_cents(statement.conservative_fee_reserve, "sell_fees")
        net = gross - fees
        resulting_cash = account["cash_cents"] + net
        if resulting_cash < account["reserved_cents"] or resulting_cash > 9_000_000_000_000:
            raise ResearchLedgerError("Projected sell proceeds would violate cash reservations")
        used_basis = _fifo_consume(fifo[key], statement.filled_quantity)
        realized = net - used_basis
        con.execute(
            "INSERT INTO reservations(account_id,order_id,instrument_key,option_type,strike,"
            "lots,quantity,max_price_cents,fee_buffer_cents,held_cents,as_of_utc,status,filled_quantity)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,'CLOSED',?)",
            (ledger.account_id, oid, key, option_type, str(strike), lots, requested,
             0, 0, 0, observed_at.astimezone(timezone.utc).isoformat(), statement.filled_quantity),
        )
        try:
            con.execute(
                "INSERT INTO replay_ids(account_id,event_id,order_id) VALUES(?,?,?)",
                (ledger.account_id, eid, oid),
            )
        except sqlite3.IntegrityError as exc:
            raise ResearchLedgerError("Replay ID conflict on simulated exit") from exc
        con.execute(
            "UPDATE accounts SET cash_cents=? WHERE account_id=?",
            (resulting_cash, ledger.account_id),
        )
        new_qty = owned - statement.filled_quantity
        if new_qty:
            con.execute(
                "UPDATE inventory SET quantity=? WHERE account_id=? AND instrument_key=?",
                (new_qty, ledger.account_id, key),
            )
        else:
            con.execute(
                "DELETE FROM inventory WHERE account_id=? AND instrument_key=?",
                (ledger.account_id, key),
            )
        ledger._audit(con, {
            "type": "SETTLE_LONG_EXIT", "order_id": oid, "instrument_key": key,
            "filled_quantity": statement.filled_quantity,
            "gross_proceeds_cents": gross, "sell_fees_cents": fees,
            "net_proceeds_cents": net, "attributed_buy_cost_cents": used_basis,
            "realized_net_pnl_cents": realized, "event_ids": [eid],
            "as_of_utc": observed_at.astimezone(timezone.utc).isoformat(),
        })
        # Before transaction commit, replay *every* buy/exit and prove cash,
        # remaining inventory, attributed basis and recorded P&L consistent.
        _replay_account(ledger, con)
        return ResearchLongExitResult(
            order_id=oid, status=statement.status,
            requested_quantity=requested, filled_quantity=statement.filled_quantity,
            gross_proceeds=gross / 100, sell_fees=fees / 100,
            attributed_buy_cost=used_basis / 100, realized_net_pnl=realized / 100,
            cash_after=resulting_cash / 100, remaining_inventory=new_qty,
        )

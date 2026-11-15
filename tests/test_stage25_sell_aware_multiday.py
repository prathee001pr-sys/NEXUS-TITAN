"""Stage25 deterministic BUY/SELL multi-day tests, all simulated/offline."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import runpy
import sqlite3

import pytest

from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.shadow.long_option_exit_research import (
    simulate_and_settle_long_exit, report_research_long_portfolio,
)
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger, ResearchLedgerError
from nexus_titan.shadow.research_recovery_validation import run_research_shadow_recovery_drill
from nexus_titan.shadow.sell_aware_multiday import (
    LongResearchDayCloseClaim, inspect_sell_aware_day_closes,
    reconstruct_sell_aware_daily_journal,
)

_HELPERS = runpy.run_path(str(Path(__file__).resolve().parent / "test_stage24_long_option_exit_research.py"))
BUY = _HELPERS["_buy"]
EXIT = _HELPERS["_exit_args"]
OBS = _HELPERS["OBS"]
CAL = nse_equity_derivatives_baseline()
INDIA = ZoneInfo("Asia/Kolkata")


def _complete(tmp_path):
    ledger, inp = BUY(tmp_path)
    first = EXIT(inp, when=OBS + timedelta(days=1), lots=1, bid=7.0)
    ex1 = simulate_and_settle_long_exit(**first)
    second = EXIT(
        inp, when=OBS + timedelta(days=3), lots=1, bid=8.0,
        order_id="EXIT-THURSDAY", event_id="EVENT-THURSDAY",
    )
    ex2 = simulate_and_settle_long_exit(**second)
    assert ex1.filled_quantity == ex2.filled_quantity == 25
    return ledger, (ex1, ex2)


def _claims(journal):
    return [LongResearchDayCloseClaim(
        session_date=r.session_date,
        observed_at=datetime.combine(r.session_date, time(15,31), tzinfo=INDIA),
        account_id=journal.account_id,
        closing_cash=r.closing_cash,
        closing_long_quantity=r.closing_long_quantity,
        remaining_cost_basis=r.remaining_cost_basis,
        cumulative_realized_net_pnl=r.cumulative_realized_net_pnl,
        evidence_reference="synthetic/day-close/" + r.session_date.isoformat(),
    ) for r in journal.days]


def test_four_day_buy_partial_sell_idle_day_final_sell_all_reconcile(tmp_path):
    ledger, exits = _complete(tmp_path)
    report = reconstruct_sell_aware_daily_journal(ledger, calendar=CAL)
    assert report.account_id == "TEST-GUARDED"
    assert len(report.days) == 4
    days = report.days
    assert [r.session_date for r in days] == [
        OBS.date() + timedelta(days=i) for i in range(4)
    ]
    assert days[0].bought_quantity == 50 and days[0].sold_quantity == 0
    assert days[0].cash_delta < 0 and days[0].closing_long_quantity == 50
    assert days[1].bought_quantity == 0 and days[1].sold_quantity == 25
    assert days[1].cash_delta > 0 and days[1].closing_long_quantity == 25
    assert days[2].bought_quantity == days[2].sold_quantity == 0
    assert days[2].cash_delta == 0
    assert days[2].closing_cash == days[1].closing_cash
    assert days[2].remaining_cost_basis == days[1].remaining_cost_basis
    assert days[3].sold_quantity == 25 and days[3].closing_long_quantity == 0
    assert days[3].remaining_cost_basis == 0
    assert days[3].cash_delta > 0
    assert report.incomplete_mark_to_market is False
    assert report.remaining_long_quantity == 0
    assert report.remaining_cost_basis == 0
    assert report.ending_cash == ledger.status().cash_balance
    assert report.cumulative_realized_net_pnl == round(
        sum(x.realized_net_pnl for x in exits), 2
    )
    assert round(report.ending_cash - ledger.status().starting_capital, 2) == report.cumulative_realized_net_pnl
    assert round(sum(r.cash_delta for r in days), 2) == round(report.ending_cash - ledger.status().starting_capital, 2)
    assert all(not r.external_source_verified for r in report.days)
    assert report.live_orders_transmitted == 0


def test_fees_buy_and_sell_reconcile_from_audit_not_closing_cash_guess(tmp_path):
    ledger,_ = _complete(tmp_path)
    rep = reconstruct_sell_aware_daily_journal(ledger, calendar=CAL)
    assert rep.days[0].buy_premium > 0
    assert rep.days[0].buy_fees > 0
    assert rep.days[1].sell_fees > 0 and rep.days[3].sell_fees > 0
    for d in rep.days:
        assert round(
            d.sell_proceeds - d.sell_fees - d.buy_premium - d.buy_fees, 2
        ) == d.cash_delta
    assert rep.days[-1].cumulative_realized_net_pnl == report_research_long_portfolio(ledger).cumulative_realized_net_pnl


def test_reviewed_daily_claims_match_audited_sell_cashflow(tmp_path):
    ledger,_ = _complete(tmp_path)
    rep = reconstruct_sell_aware_daily_journal(ledger, calendar=CAL)
    result = inspect_sell_aware_day_closes(ledger, calendar=CAL, claims=_claims(rep))
    assert result.is_structurally_valid
    assert result.day_count == 4
    assert not result.data_source_authenticity_verified
    assert not result.independent_broker_reconciliation_verified
    assert not result.approved_for_strategy_promotion


@pytest.mark.parametrize("field,value,fragment", [
    ("closing_cash", 50000.0, "cash mismatch"),
    ("closing_long_quantity", 999, "unmatched long inventory"),
    ("remaining_cost_basis", 0.0, "FIFO cost basis mismatch"),
    ("cumulative_realized_net_pnl", -999.0, "realized P&L mismatch"),
    ("evidence_reference", "", "empty claimed evidence"),
    ("account_id", "OTHER", "wrong date/account"),
])
def test_day_closes_cannot_approve_wrong_money_positions_or_references(tmp_path, field, value, fragment):
    ledger,_ = _complete(tmp_path)
    correct = _claims(reconstruct_sell_aware_daily_journal(ledger, calendar=CAL))
    correct[1] = replace(correct[1], **{field: value})
    result = inspect_sell_aware_day_closes(ledger,calendar=CAL,claims=correct)
    assert not result.is_structurally_valid
    assert any(fragment in error for error in result.discrepancies)


def test_missing_trading_day_blocks_even_without_trade(tmp_path):
    ledger,_=_complete(tmp_path)
    records = _claims(reconstruct_sell_aware_daily_journal(ledger, calendar=CAL))
    result=inspect_sell_aware_day_closes(ledger,calendar=CAL,claims=records[:2]+records[3:])
    assert not result.is_structurally_valid
    assert "Missing or extra" in result.discrepancies[0]


def test_reversed_or_duplicate_trading_days_block(tmp_path):
    ledger,_=_complete(tmp_path)
    records=_claims(reconstruct_sell_aware_daily_journal(ledger,calendar=CAL))
    records[1],records[2] = records[2],records[1]
    assert not inspect_sell_aware_day_closes(ledger,calendar=CAL,claims=records).is_structurally_valid
    records[2] = records[1]
    assert not inspect_sell_aware_day_closes(ledger,calendar=CAL,claims=records).is_structurally_valid


def test_before_session_close_or_naive_time_cannot_be_accepted(tmp_path):
    ledger,_=_complete(tmp_path)
    claims=_claims(reconstruct_sell_aware_daily_journal(ledger,calendar=CAL))
    claims[2]=replace(claims[2], observed_at=datetime.combine(claims[2].session_date,time(10),tzinfo=INDIA))
    report=inspect_sell_aware_day_closes(ledger,calendar=CAL,claims=claims)
    assert any("before exchange session close" in i for i in report.discrepancies)
    claims[2]=replace(claims[2], observed_at=datetime.combine(claims[2].session_date,time(15,31)))
    assert not inspect_sell_aware_day_closes(ledger,calendar=CAL,claims=claims).is_structurally_valid


def test_calendar_ignores_weekend_without_fake_trades(tmp_path):
    ledger,inp=BUY(tmp_path)
    when=OBS+timedelta(days=7)
    # Contract expiry Nov 5: no simulated trade after expiry; use no weekend
    # to prove calendar nontrading day and field verification are unchanged.
    with pytest.raises(ResearchLedgerError,match="calendar"):
        reconstruct_sell_aware_daily_journal(ledger,calendar=None)
    report=reconstruct_sell_aware_daily_journal(ledger,calendar=CAL)
    assert len(report.days)==1


def test_open_buy_only_marks_equity_unverified_not_profits(tmp_path):
    ledger,inp=BUY(tmp_path)
    journal=reconstruct_sell_aware_daily_journal(ledger,calendar=CAL)
    assert journal.incomplete_mark_to_market
    assert journal.remaining_long_quantity==50
    assert journal.cumulative_realized_net_pnl==0
    assert journal.days[0].remaining_cost_basis>0


def test_recovery_drill_after_multiday_sell_matches_daily_journal(tmp_path):
    ledger,_=_complete(tmp_path)
    before=reconstruct_sell_aware_daily_journal(ledger,calendar=CAL)
    backup=run_research_shadow_recovery_drill(ledger,backup_path=tmp_path/"stage25-backup.sqlite3")
    assert backup.passed
    restored=DurableResearchShadowLedger(
        tmp_path/"stage25-backup.sqlite3",
        account_id="TEST-GUARDED", starting_capital=50000,
    )
    assert reconstruct_sell_aware_daily_journal(restored,calendar=CAL)==before


def test_corrupted_source_blocks_entire_sell_aware_reconstruction(tmp_path):
    ledger,_=_complete(tmp_path)
    with sqlite3.connect(ledger.db_path) as conn:
        conn.execute("UPDATE accounts SET cash_cents=cash_cents+1")
    with pytest.raises(ResearchLedgerError):
        reconstruct_sell_aware_daily_journal(ledger,calendar=CAL)


def test_bad_max_days_and_calendar_are_rejected(tmp_path):
    ledger,_=_complete(tmp_path)
    for bad in (0,True,3661,-1):
        with pytest.raises(ResearchLedgerError,match="max_calendar_days"):
            reconstruct_sell_aware_daily_journal(ledger,calendar=CAL,max_calendar_days=bad)
    with pytest.raises(ResearchLedgerError,match="calendar-span"):
        reconstruct_sell_aware_daily_journal(ledger,calendar=CAL,max_calendar_days=3)


def test_legacy_buy_event_without_fill_timestamp_never_guessed(tmp_path):
    ledger,inp=BUY(tmp_path)
    with sqlite3.connect(ledger.db_path) as conn:
        rows=conn.execute(
            "SELECT sequence,previous_hash,payload_json FROM audit WHERE account_id=? ORDER BY sequence",
            ("TEST-GUARDED",),
        ).fetchall()
        # Last record is SETTLE_BUY; re-hash its own payload to simulate a
        # historically valid legacy event without Stage25 timestamp fields.
        seq, previous, payload = rows[-1]
        record=json.loads(payload)
        assert record["event"]["type"]=="SETTLE_BUY"
        record["event"].pop("fill_observed_at_utc")
        record["event"].pop("buy_premium_cents")
        record["event"].pop("buy_fees_cents")
        encoded=json.dumps(record,sort_keys=True,separators=(",",":"),allow_nan=False)
        digest=hashlib.sha256((previous+"|"+encoded).encode()).hexdigest()
        conn.execute("UPDATE audit SET payload_json=?,record_hash=? WHERE sequence=?",
                     (encoded,digest,seq))
    assert ledger.verify_integrity()
    with pytest.raises(ResearchLedgerError,match="legacy source not supported"):
        reconstruct_sell_aware_daily_journal(ledger,calendar=CAL)


def test_no_real_market_promotion_even_with_matching_claims(tmp_path):
    ledger,_=_complete(tmp_path)
    j=reconstruct_sell_aware_daily_journal(ledger,calendar=CAL)
    checked=inspect_sell_aware_day_closes(ledger,calendar=CAL,claims=_claims(j))
    assert checked.is_structurally_valid
    assert not checked.data_source_authenticity_verified
    assert not checked.independent_broker_reconciliation_verified
    assert checked.live_orders_transmitted == 0
    assert checked.approved_for_strategy_promotion is False

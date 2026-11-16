"""Actual MarketState/Stage97 integration, with separate test-only signed permits."""
from dataclasses import replace
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from nexus_titan.intelligence.market_state import MarketStateBuilder
from nexus_titan.intelligence.specialist_roles import SpecialistEvidence
from nexus_titan.operations.crypto_spot_research_gate import (
    CryptoSpotResearchBlocked, assess_synthetic_crypto_spot,
)
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBlocked, CryptoPaperBook, CryptoPaperIntent, CryptoPaperLimits,
    seal_crypto_paper_permit,
)

_KEY = b"TITAN_QA_LOCAL_ONLY".ljust(32, b"Q")


def _fixture(tmp_path: Path, *, side="BUY", epoch=100, quote=5000000, qty=10000,
             action=None, ohlc=None, paper=True, exposure=150000, cash=200000):
    close = quote / 100
    pv = {"open": close, "high": close, "low": close, "close": close, "volume": 1}
    if ohlc is not None:
        pv.update(ohlc)
    state = MarketStateBuilder(max_age_seconds=30).build(
        exchange="CRYPTO_SYNTHETIC", symbol="BTC-USDT", interval="1m",
        event_time=datetime.fromtimestamp(epoch, timezone.utc),
        ingest_time=datetime.fromtimestamp(epoch+1, timezone.utc),
        price_volume=pv, regime={"label": "SYNTHETIC_QA"},
        options_flow={"status": "NOT_APPLICABLE"}, context={"events": []},
        provenance={"source_id": "LOCAL_SYNTHETIC_TEST_ONLY"},
    )
    direction = action or side
    evidence = tuple(SpecialistEvidence(role, direction, "bounded synthetic evidence",
                                        f"synthetic:{role}", "revoke synthetic claim")
                     for role in ("MARKET_STRUCTURE", "TREND_REGIME"))
    intent = CryptoPaperIntent(f"t-{side.lower()}-{epoch}", side, qty, quote, epoch)
    book = CryptoPaperBook(
        path=tmp_path/"crypto_spot.sqlite", account_id="spot-case",
        limits=CryptoPaperLimits(cash,100000,exposure,10000,paper_enabled=paper),
        verification_key=_KEY,
        indian_book_path=tmp_path/"indian-different.sqlite",
    )
    return dict(state=state, evidence=evidence, intent=intent, book=book, now_epoch=epoch+2)


def _paper_event(fixture, *, human_approved=True, permit=None):
    book, intent = fixture["book"], fixture["intent"]
    head = book.snapshot()
    if permit == "fresh":
        permit = seal_crypto_paper_permit(
            _KEY, account_id=book.account_id, revision=head.journal_revision,
            tip=head.journal_tip, intent=intent, expires_epoch=fixture["now_epoch"]+5,
        )
    return book.apply(intent, permit, now_epoch=fixture["now_epoch"],human_approved=human_approved)


def test_readonly_real_stage97_then_independently_permitted_full_closed_trade(tmp_path):
    f = _fixture(tmp_path)
    original = f["book"].snapshot()
    receipt = assess_synthetic_crypto_spot(**f)
    assert receipt.status == "SYNTHETIC_RESEARCH_ONLY_NO_EXECUTION"
    assert receipt.conservative_notional_cents == 50000
    assert (receipt.paper_order_submitted,receipt.signed_risk_permit_issued,
            receipt.exchange_order_submitted,receipt.live_trading_enabled,
            receipt.production_ready) == (False,)*5
    assert f["book"].snapshot() == original
    with pytest.raises(CryptoPaperBlocked):
        _paper_event(f, permit=None)
    with pytest.raises(CryptoPaperBlocked):
        _paper_event(f, permit="fresh", human_approved=False)
    assert f["book"].snapshot().journal_revision == 0
    bought, replay = _paper_event(f, permit="fresh")
    assert not replay and bought.position_microcoin == 10000 and bought.total_fees_cents > 0
    sell = _fixture(tmp_path, side="SELL", epoch=102, quote=6000000)
    sell_receipt = assess_synthetic_crypto_spot(**sell)
    assert sell_receipt.action == "SELL" and not sell_receipt.signed_risk_permit_issued
    closed, replay = _paper_event(sell, permit="fresh")
    assert not replay and closed.position_microcoin == 0 and closed.remaining_cost_basis_cents == 0
    assert closed.cash_cents == closed.initial_cents + closed.realized_net_pnl_cents
    assert closed.realized_net_pnl_cents > 0
    reopened = _fixture(tmp_path, side="SELL", epoch=103, quote=6000000)
    assert reopened["book"].snapshot() == closed


def test_no_permit_or_forged_permit_cannot_commit_after_positive_research(tmp_path):
    f = _fixture(tmp_path)
    assess_synthetic_crypto_spot(**f)
    with pytest.raises(CryptoPaperBlocked):
        _paper_event(f)
    state=f["book"].snapshot()
    good=seal_crypto_paper_permit(_KEY,account_id=state.account_id,revision=state.journal_revision,
                tip=state.journal_tip,intent=f["intent"],expires_epoch=110)
    with pytest.raises(CryptoPaperBlocked):
        _paper_event(f,permit=replace(good, signature_hex="0"*64))
    assert f["book"].snapshot() == state


@pytest.mark.parametrize("bad", ["stale", "future", "bad_price", "single_role", "conflict", "duplicate_role",
                                  "disabled_paper", "bad_ohlc", "not_real_state", "not_real_book", "bad_qty", "wrong_source"])
def test_fail_closed_real_component_precheck(tmp_path,bad):
    f = _fixture(tmp_path, paper=bad != "disabled_paper")
    if bad == "stale":f["now_epoch"] = 150
    elif bad == "future":f["now_epoch"] = 99
    elif bad == "bad_price":f["intent"] = replace(f["intent"],price_cents_per_coin=6000000)
    elif bad == "single_role":f["evidence"] = f["evidence"][:1]
    elif bad == "conflict":f["evidence"] = (f["evidence"][0],replace(f["evidence"][1],action="SELL"))
    elif bad == "duplicate_role":f["evidence"] = (f["evidence"][0],f["evidence"][0])
    elif bad == "bad_ohlc":
        f["state"] = replace(f["state"],price_volume={"open":50000,"high":40000,"low":30000,"close":50000,"volume":1})
    elif bad == "not_real_state":f["state"] = object()
    elif bad == "not_real_book":f["book"] = object()
    elif bad == "bad_qty":f["intent"] = replace(f["intent"],quantity_microcoin=30000)
    elif bad == "wrong_source":f["state"] = replace(f["state"],provenance={"source_id":"FAKE"})
    with pytest.raises((CryptoSpotResearchBlocked, CryptoPaperBlocked)):
        assess_synthetic_crypto_spot(**f)


def test_missing_independent_approval_never_granted_by_good_consensus(tmp_path):
    f=_fixture(tmp_path)
    receipt=assess_synthetic_crypto_spot(**f)
    assert not receipt.signed_risk_permit_issued
    with pytest.raises(CryptoPaperBlocked):_paper_event(f,permit="fresh",human_approved=False)
    assert f["book"].snapshot().journal_revision==0


def test_kill_blocks_buy_but_real_stage97_allows_independently_signed_protective_close(tmp_path):
    f=_fixture(tmp_path)
    _paper_event(f,permit="fresh")
    f["book"].stop("kill")
    newer=_fixture(tmp_path,epoch=102)
    with pytest.raises(CryptoSpotResearchBlocked):assess_synthetic_crypto_spot(**newer)
    with pytest.raises(CryptoPaperBlocked):_paper_event(newer,permit="fresh")
    sell=_fixture(tmp_path,side="SELL",epoch=103)
    r=assess_synthetic_crypto_spot(**sell)
    assert r.action=="SELL" and not r.paper_order_submitted
    done,_=_paper_event(sell,permit="fresh")
    assert done.position_microcoin==0 and done.kill_active


def test_replay_tamper_blocks_preflight(tmp_path):
    f=_fixture(tmp_path)
    _paper_event(f,permit="fresh")
    with closing(sqlite3.connect(f["book"].path)) as connection:
        with connection:
            connection.execute("UPDATE crypto_events SET payload='{}' WHERE seq=1")
    with pytest.raises(CryptoPaperBlocked):assess_synthetic_crypto_spot(**f)


def test_wrong_integer_units_are_never_lot_converted(tmp_path):
    f=_fixture(tmp_path)
    assert assess_synthetic_crypto_spot(**f).quantity_microcoin == 10000
    assert f["book"].snapshot().journal_revision==0
    # Mismatched generic whole-lot quantity is not a valid spot order permit.
    with pytest.raises(CryptoPaperBlocked):_paper_event(f,permit=None)


def test_independent_stale_signed_permit_rejected_after_other_permitted_commit(tmp_path):
    first=_fixture(tmp_path)
    old=first['book'].snapshot()
    different=replace(first['intent'],operation_id='other-research')
    stale=seal_crypto_paper_permit(
        _KEY,account_id=old.account_id,revision=old.journal_revision,
        tip=old.journal_tip,intent=different,expires_epoch=105,
    )
    assert not assess_synthetic_crypto_spot(**first).signed_risk_permit_issued
    before,_=_paper_event(first,permit='fresh')
    with pytest.raises(CryptoPaperBlocked):
        first['book'].apply(different,stale,now_epoch=102,human_approved=True)
    assert first['book'].snapshot()==before


def test_actual_crypto_partial_sell_and_dual_market_readonly_isolation(tmp_path):
    from types import SimpleNamespace
    from nexus_titan.operations.stage96_accounting_review import reconcile_fo_snapshot
    from nexus_titan.operations.stage98_dual_market_review import read_only_dual_market_review
    f=_fixture(tmp_path)
    _paper_event(f,permit='fresh')
    part=_fixture(tmp_path,side='SELL',epoch=102,quote=6000000,qty=4000)
    assert assess_synthetic_crypto_spot(**part).quantity_microcoin==4000
    partially_closed,_=_paper_event(part,permit='fresh')
    assert partially_closed.position_microcoin==6000
    rest=_fixture(tmp_path,side='SELL',epoch=104,quote=6000000,qty=6000)
    assert assess_synthetic_crypto_spot(**rest).quantity_microcoin==6000
    closed,_=_paper_event(rest,permit='fresh')
    assert closed.position_microcoin==0
    order=SimpleNamespace(filled_quantity=1,open_quantity=0,open_hold_cents=0,
        remaining_premium_cents=0,remaining_entry_fees_cents=0,realized_net_pnl_cents=100)
    india=SimpleNamespace(account_id='different-indian-book',journal_revision=7,journal_tip='a'*64,
        initial_cents=100000,cash_cents=100100,remaining_cost_basis_cents=0,
        realized_gross_pnl_cents=110,realized_net_pnl_cents=100,paid_fees_cents=10,
        orders=(order,))
    report=read_only_dual_market_review(reconcile_fo_snapshot(india),rest['book'])
    assert report.indian['currency']=='INR' and report.crypto['currency']=='USDT'
    assert report.combined_pnl_cents is None and report.combined_cash_cents is None
    assert report.indian['cash_cents']==100100 and report.crypto['position_microcoin']==0
    assert not report.live_trading_enabled


def test_forged_quality_flag_does_not_override_missing_market_data(tmp_path):
    from nexus_titan.intelligence.market_state import StateQuality
    f=_fixture(tmp_path)
    f['state']=replace(f['state'],quality=StateQuality(True,False,(),()),
        price_volume={'open':50000,'close':50000,'volume':1})
    with pytest.raises(CryptoSpotResearchBlocked):assess_synthetic_crypto_spot(**f)
    assert f['book'].snapshot().journal_revision==0


def test_generic_lot_engine_is_not_a_crypto_microcoin_authority(tmp_path):
    from nexus_titan.intelligence.pipeline import TradingIntelligencePipeline,RiskRequest,PipelineStatus
    from nexus_titan.intelligence.specialist_roles import adapt_specialist_evidence
    f=_fixture(tmp_path)
    generic=TradingIntelligencePipeline().evaluate(
        f['state'],adapt_specialist_evidence(f['evidence']),
        RiskRequest(capital=2000,entry_price=50000,stop_price=49900,
                    symbol='BTC-USDT',side='BUY',lot_size=1,tick_size=.01))
    # One whole $50k BTC 'lot' exceeds the $2k account; generic sizing rejects.
    # Stage97's permitted fraction remains microcoin-sized, never derived from
    # the generic lot engine's quantity or a claimed authorization.
    assert generic.status is PipelineStatus.RISK_REJECTED and generic.risk_quantity==0
    receipt=assess_synthetic_crypto_spot(**f)
    assert receipt.quantity_microcoin==10000 and not receipt.signed_risk_permit_issued
    assert f['book'].snapshot().journal_revision==0


def test_synthetic_mark_anomaly_and_ledger_rollback_do_not_create_permission(tmp_path):
    f=_fixture(tmp_path)
    before=f['book'].snapshot()
    with pytest.raises(CryptoSpotResearchBlocked):
        assess_synthetic_crypto_spot(**{**f,'intent':replace(f['intent'],price_cents_per_coin=5100000)})
    assert f['book'].snapshot()==before
    with pytest.raises(CryptoPaperBlocked):
        _paper_event(f,permit='fresh',human_approved=False)
    assert f['book'].snapshot()==before

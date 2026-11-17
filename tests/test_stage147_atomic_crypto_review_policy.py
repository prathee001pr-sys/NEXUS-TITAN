"""Stage147 optional metadata-pinned atomic synthetic risk policy acceptance.

Does not authorize market orders or replace independent human authentication.
Legacy account mode stays restricted to the existing local TEST permit controls.
"""
from dataclasses import asdict, replace

import pytest

from nexus_titan.operations.crypto_spot_independent_review import CryptoSpotReviewPolicy
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBook, CryptoPaperBlocked, CryptoPaperIntent, CryptoPaperLimits,
    seal_crypto_paper_permit,
)

TEST_KEY=b"STAGE147_ISOLATED_RESEARCH_TEST_KEY".ljust(32,b"Q")
LIMITS=CryptoPaperLimits(200_000,100_000,150_000,10_000,paper_enabled=True)
POLICY=CryptoSpotReviewPolicy(49_000,140_000,9_000,20,100)


def book(path, *, policy=POLICY, limits=LIMITS):
    return CryptoPaperBook(
        path=path, account_id="strict-synthetic-crypto",
        verification_key=TEST_KEY, limits=limits,
        atomic_review_policy=policy,
    )


def trade(b,side,qty,oid,*,price=5_000_000,epoch=100,now=None):
    intent=CryptoPaperIntent(oid,side,qty,price,epoch)
    s=b.snapshot()
    now=epoch+1 if now is None else now
    permit=seal_crypto_paper_permit(
        TEST_KEY,account_id=b.account_id,revision=s.journal_revision,
        tip=s.journal_tip,intent=intent,expires_epoch=now+5,
    )
    return b.apply(intent,permit,now_epoch=now,human_approved=(side=="BUY"))


def test_direct_public_apply_denies_intent_over_tighter_cap(tmp_path):
    b=book(tmp_path/"strict.sqlite")
    with pytest.raises(CryptoPaperBlocked,match="independent"):
        trade(b,"BUY",10_000,"over-strict",price=5_000_000)
    assert b.snapshot().journal_revision==0


def test_private_atomic_apply_cannot_bypass_stricter_cap(tmp_path):
    b=book(tmp_path/"strict.sqlite")
    intent=CryptoPaperIntent("private-over","BUY",10_000,5_000_000,100)
    state=b.snapshot()
    permit=seal_crypto_paper_permit(TEST_KEY,account_id=b.account_id,
        revision=state.journal_revision,tip=state.journal_tip,
        intent=intent,expires_epoch=110)
    notional=50_000
    event={"kind":"TRADE","operation_id":intent.operation_id,"intent":asdict(intent),
           "notional_cents":notional,"fee_cents":50}
    with pytest.raises(CryptoPaperBlocked,match="independent"):
        b._apply(intent.operation_id,event,permit=permit,now_epoch=101,human_approved=True)
    assert b.snapshot().journal_revision==0


def test_policy_is_pinned_across_restart_and_no_downgrade(tmp_path):
    path=tmp_path/"strict.sqlite"
    b=book(path)
    s,_=trade(b,"BUY",8_000,"valid-entry")
    assert s.journal_revision==1 and s.position_microcoin==8_000
    assert book(path).snapshot()==s
    with pytest.raises(CryptoPaperBlocked):
        book(path,policy=None)
    with pytest.raises(CryptoPaperBlocked):
        book(path,policy=replace(POLICY,max_order_cents=50_000))
    assert book(path).snapshot()==s


def test_old_legacy_book_cannot_reopen_as_strict_without_explicit_migration(tmp_path):
    path=tmp_path/"legacy.sqlite"
    b=book(path,policy=None)
    s,_=trade(b,"BUY",10_000,"legacy-test-only")
    assert s.journal_revision==1
    with pytest.raises(CryptoPaperBlocked):
        book(path,policy=POLICY)
    assert book(path,policy=None).snapshot()==s


@pytest.mark.parametrize("field,relaxed",[
    ("max_order_cents",100_001),
    ("max_total_exposure_cents",150_001),
    ("max_lifetime_realized_loss_cents",10_001),
    ("max_quote_age_seconds",31),
])
def test_atomic_policy_never_relaxes_book_limits(tmp_path,field,relaxed):
    with pytest.raises(CryptoPaperBlocked,match="cannot relax"):
        book(tmp_path/"bad.sqlite",policy=replace(POLICY,**{field:relaxed}))


def test_stricter_quote_age_blocks_inside_atomic_write(tmp_path):
    b=book(tmp_path/"strict.sqlite")
    with pytest.raises(CryptoPaperBlocked,match="quote-age"):
        trade(b,"BUY",8_000,"old-quote",now=125)
    assert b.snapshot().journal_revision==0


def test_fee_policy_is_checked_at_atomic_boundary(tmp_path):
    b=book(tmp_path/"strict.sqlite",policy=replace(POLICY,max_fee_bps=5))
    with pytest.raises(CryptoPaperBlocked,match="independent"):
        trade(b,"BUY",8_000,"fee-veto")
    assert b.snapshot().journal_revision==0


def test_strict_exposure_cap_is_checked_on_second_buy(tmp_path):
    b=book(tmp_path/"strict.sqlite",policy=replace(POLICY,max_total_exposure_cents=70_000))
    trade(b,"BUY",8_000,"first")
    before=b.snapshot()
    with pytest.raises(CryptoPaperBlocked,match="independent"):
        trade(b,"BUY",8_000,"second",epoch=101)
    assert b.snapshot()==before


def test_protective_sell_after_kill_is_not_blocked_by_entry_cap(tmp_path):
    b=book(tmp_path/"strict.sqlite")
    trade(b,"BUY",8_000,"entry")
    b.stop("one-way-stop")
    after,_=trade(b,"SELL",8_000,"protective",price=7_000_000,epoch=101)
    assert after.position_microcoin==0 and after.kill_active
    assert after.remaining_cost_basis_cents==0
    assert after.cash_cents==after.initial_cents+after.realized_net_pnl_cents
    assert not after.live_trading_enabled and after.exchange_orders_transmitted==0


def test_independent_loss_limit_stops_new_entry_before_local_loss_cap(tmp_path):
    b=book(tmp_path/"strict.sqlite",policy=replace(POLICY,max_lifetime_realized_loss_cents=1_000))
    trade(b,"BUY",8_000,"entry")
    trade(b,"SELL",8_000,"loss-exit",price=4_750_000,epoch=101)
    before=b.snapshot()
    assert -10_000<before.realized_net_pnl_cents<=-1_000
    with pytest.raises(CryptoPaperBlocked,match="independent"):
        trade(b,"BUY",1_000,"risk-veto",epoch=102)
    assert b.snapshot()==before


def test_cannot_remove_in_memory_policy_without_journal_integrity_failure(tmp_path):
    b=book(tmp_path/"strict.sqlite")
    b._atomic_review_policy=None
    with pytest.raises(CryptoPaperBlocked):
        b.snapshot()

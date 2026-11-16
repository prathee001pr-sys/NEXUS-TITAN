"""Fail-closed, real Stage97 spot account research review acceptance cases."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from nexus_titan.intelligence.market_state import MarketStateBuilder
from nexus_titan.intelligence.specialist_roles import SpecialistEvidence
from nexus_titan.operations.crypto_spot_independent_review import (
    CryptoSpotIndependentReviewBlocked, CryptoSpotReviewPolicy,
    review_synthetic_crypto_spot_risk,
)
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBook, CryptoPaperBlocked, CryptoPaperIntent, CryptoPaperLimits,
    seal_crypto_paper_permit,
)

KEY = b"LOCAL_TEST_ONLY_VETO_KEY".ljust(32, b"Q")


def case(tmp_path, *, side="BUY", epoch=100, qty=10_000, price=5_000_000,
         paper=True, fee_bps=10, market_age=2):
    state = MarketStateBuilder(max_age_seconds=30).build(
        exchange="CRYPTO_SYNTHETIC", symbol="BTC-USDT", interval="1m",
        event_time=datetime.fromtimestamp(epoch, timezone.utc),
        ingest_time=datetime.fromtimestamp(epoch + 1, timezone.utc),
        price_volume={"open":price/100, "high":price/100,"low":price/100,
                      "close":price/100, "volume":1},
        regime={"id":"SYNTHETIC"}, options_flow={"none":True},
        context={"economic_event":"test"},
        provenance={"source_id":"LOCAL_SYNTHETIC_TEST_ONLY"},
    )
    evidence=tuple(SpecialistEvidence(role,side,"synthetic role",f"qa:{role}","withdraw evidence")
                   for role in ("MARKET_STRUCTURE","TREND_REGIME"))
    book=CryptoPaperBook(path=tmp_path/"crypto.sqlite",account_id="veto-account",
                         limits=CryptoPaperLimits(200000,100000,150000,10000,
                                                  fee_bps=fee_bps,paper_enabled=paper),
                         verification_key=KEY)
    intent=CryptoPaperIntent(f"{side.lower()}{epoch}",side,qty,price,epoch)
    policy=CryptoSpotReviewPolicy(90000,140000,9000,20,100)
    return dict(state=state,evidence=evidence,intent=intent,
                book=book,now_epoch=epoch+market_age,policy=policy)


def paper_apply(kwargs):
    book,intent=kwargs["book"],kwargs["intent"]
    head=book.snapshot()
    permit=seal_crypto_paper_permit(KEY,account_id=book.account_id,
       revision=head.journal_revision,tip=head.journal_tip,
       intent=intent,expires_epoch=kwargs["now_epoch"]+10)
    return book.apply(intent,permit,now_epoch=kwargs["now_epoch"],human_approved=True)


def test_readonly_receipt_cannot_self_authorize_paper_order(tmp_path):
    args=case(tmp_path)
    before=args["book"].snapshot()
    result=review_synthetic_crypto_spot_risk(**args)
    assert result.status=="SYNTHETIC_INDEPENDENT_REVIEW_ONLY_NO_EXECUTION"
    assert result.conservative_notional_cents==50000
    assert result.reviewed_exposure_cents==50050
    assert len(result.policy_sha256)==64
    assert result.journal_tip==before.journal_tip
    assert result.live_trading_enabled is False
    assert result.paper_order_submitted is False
    assert result.signed_risk_permit_issued is False
    assert result.independent_production_risk_engine_verified is False
    assert args["book"].snapshot()==before
    with pytest.raises(CryptoPaperBlocked):
        args["book"].apply(args["intent"],None,now_epoch=args["now_epoch"],human_approved=True)
    assert args["book"].snapshot().journal_revision==0


@pytest.mark.parametrize("field,value",[
    ("max_order_cents",100001), ("max_total_exposure_cents",150001),
    ("max_lifetime_realized_loss_cents",10001),
    ("max_quote_age_seconds",31),
])
def test_cannot_relax_existing_stage97_policy(tmp_path,field,value):
    args=case(tmp_path)
    args["policy"]=replace(args["policy"],**{field:value})
    with pytest.raises(CryptoSpotIndependentReviewBlocked,match="cannot relax"):
        review_synthetic_crypto_spot_risk(**args)
    assert args["book"].snapshot().journal_revision==0


@pytest.mark.parametrize("field,value",[
    ("max_order_cents",True), ("max_order_cents",-1),
    ("max_total_exposure_cents",0),
    ("max_lifetime_realized_loss_cents",0),
    ("max_quote_age_seconds",True), ("max_quote_age_seconds",301),
    ("max_fee_bps",1001), ("max_fee_bps",False),
])
def test_invalid_risk_policy_is_rejected(field,value):
    args=dict(max_order_cents=90000,max_total_exposure_cents=140000,
              max_lifetime_realized_loss_cents=9000,max_quote_age_seconds=20,max_fee_bps=100)
    args[field]=value
    with pytest.raises(CryptoSpotIndependentReviewBlocked):CryptoSpotReviewPolicy(**args)


@pytest.mark.parametrize("feature",["notional","exposure","quote_age","fee","policy_type"])
def test_independent_review_vetoes_even_when_stage97_book_would_admit(tmp_path,feature):
    args=case(tmp_path,fee_bps=20 if feature=="fee" else 10)
    p=args["policy"]
    if feature=="notional":p=replace(p,max_order_cents=49000)
    elif feature=="exposure":p=replace(p,max_order_cents=50000,max_total_exposure_cents=50000)
    elif feature=="quote_age":p=replace(p,max_quote_age_seconds=1)
    elif feature=="fee":p=replace(p,max_fee_bps=10)
    elif feature=="policy_type":p=None
    args["policy"]=p
    with pytest.raises(CryptoSpotIndependentReviewBlocked):review_synthetic_crypto_spot_risk(**args)
    assert args["book"].snapshot().journal_revision==0


def test_risk_review_does_not_bypass_stage97_signed_permit(tmp_path):
    args=case(tmp_path)
    review_synthetic_crypto_spot_risk(**args)
    with pytest.raises(CryptoPaperBlocked):args["book"].apply(
        args["intent"],None,now_epoch=args["now_epoch"],human_approved=True)
    filled,_=paper_apply(args)
    assert filled.journal_revision==1
    # Old research receipt cannot be mistaken for an exact-head permit.
    args2=case(tmp_path,epoch=102)
    receipt=review_synthetic_crypto_spot_risk(**args2)
    assert receipt.journal_revision==1
    assert receipt.signed_risk_permit_issued is False


def test_protective_sell_allowed_for_research_after_kill_no_new_buy(tmp_path):
    args=case(tmp_path)
    paper_apply(args)
    args["book"].stop("hardstop")
    later=case(tmp_path,epoch=102)
    from nexus_titan.operations.crypto_spot_research_gate import CryptoSpotResearchBlocked
    with pytest.raises(CryptoSpotResearchBlocked):review_synthetic_crypto_spot_risk(**later)
    sell=case(tmp_path,side="SELL",epoch=103)
    receipt=review_synthetic_crypto_spot_risk(**sell)
    assert receipt.action=="SELL" and not receipt.signed_risk_permit_issued
    closed,_=paper_apply(sell)
    assert closed.position_microcoin==0 and closed.kill_active
    assert closed.cash_cents==closed.initial_cents+closed.realized_net_pnl_cents


def test_research_against_disabled_paper_account_is_denied(tmp_path):
    args=case(tmp_path,paper=False)
    from nexus_titan.operations.crypto_spot_research_gate import CryptoSpotResearchBlocked
    with pytest.raises(CryptoSpotResearchBlocked):review_synthetic_crypto_spot_risk(**args)


def test_policy_exposure_checked_at_actual_open_position(tmp_path):
    args=case(tmp_path)
    paper_apply(args)
    follow=case(tmp_path,epoch=102)
    follow["policy"]=replace(follow["policy"],max_total_exposure_cents=90000)
    with pytest.raises(CryptoSpotIndependentReviewBlocked,match="exposure"):
        review_synthetic_crypto_spot_risk(**follow)
    assert args["book"].snapshot().journal_revision==1


def test_non_authoritative_digest_changes_with_policy(tmp_path):
    a=case(tmp_path)
    one=review_synthetic_crypto_spot_risk(**a)
    a["policy"]=replace(a["policy"],max_order_cents=80000)
    two=review_synthetic_crypto_spot_risk(**a)
    assert one.policy_sha256!=two.policy_sha256
    assert not one.production_ready and not two.production_ready


def test_independent_lifetime_loss_veto_is_tighter_than_stage97(tmp_path):
    original=case(tmp_path)
    paper_apply(original)
    losing_exit=case(tmp_path,side="SELL",epoch=102,price=4_200_000)
    closed,_=paper_apply(losing_exit)
    assert -10_000 < closed.realized_net_pnl_cents < -8_000
    later=case(tmp_path,epoch=104)
    later["policy"]=replace(later["policy"],max_lifetime_realized_loss_cents=8_000)
    with pytest.raises(CryptoSpotIndependentReviewBlocked,match="loss veto"):
        review_synthetic_crypto_spot_risk(**later)
    assert later["book"].snapshot()==closed


def test_racing_ledger_revision_never_yields_green_receipt(tmp_path,monkeypatch):
    args=case(tmp_path)
    account=args["book"]
    original=account.snapshot
    seen=[0]

    def simulate_other_writer():
        seen[0]+=1
        if seen[0]==2:
            account.stop("synthetic-concurrent-stop")
        return original()

    monkeypatch.setattr(account,"snapshot",simulate_other_writer)
    with pytest.raises(CryptoSpotIndependentReviewBlocked,match="head advanced"):
        review_synthetic_crypto_spot_risk(**args)
    assert original().kill_active is True
    assert original().journal_revision==1

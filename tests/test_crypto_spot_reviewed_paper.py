"""Real Stage97 reviewed synthetic paper-route integration, NO live exchange."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from nexus_titan.intelligence.market_state import MarketStateBuilder
from nexus_titan.intelligence.specialist_roles import SpecialistEvidence
from nexus_titan.operations.crypto_spot_reviewed_paper import (
    CryptoReviewedPaperBlocked, submit_reviewed_synthetic_paper,
)
from nexus_titan.operations.crypto_spot_independent_review import (
    CryptoSpotIndependentReviewBlocked, CryptoSpotReviewPolicy,
)
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBlocked, CryptoPaperBook, CryptoPaperIntent, CryptoPaperLimits,
    seal_crypto_paper_permit,
)

# This signing key exists ONLY in synthetic tests. Gateway accepts no secret/key.
LOCAL_TEST_KEY = b"LOCAL_STUDY_DO_NOT_DEPLOY_2026".ljust(32, b"Q")


def fixture(tmp_path, *, side="BUY", epoch=100, qty=10_000, price=5_000_000,
            paper_enabled=True, source="LOCAL_SYNTHETIC_TEST_ONLY", age=2,
            policy=None):
    quote=price/100
    state=MarketStateBuilder(max_age_seconds=30).build(
        exchange="CRYPTO_SYNTHETIC", symbol="BTC-USDT", interval="1m",
        event_time=datetime.fromtimestamp(epoch, timezone.utc),
        ingest_time=datetime.fromtimestamp(epoch+1, timezone.utc),
        price_volume={"open":quote,"high":quote,"low":quote,"close":quote,"volume":1},
        regime={"synthetic":"flat"},options_flow={"status":"NOT_APPLICABLE"},
        context={"scenario":"local"},provenance={"source_id":source},
    )
    roles=tuple(SpecialistEvidence(r,side,"synthetic positive source",f"qa:{r}",
                                   "expire source") for r in ("MARKET_STRUCTURE","TREND_REGIME"))
    book=CryptoPaperBook(
        path=tmp_path/"crypto.sqlite",account_id="crypto-reviewed",
        limits=CryptoPaperLimits(200000,100000,150000,10000,paper_enabled=paper_enabled),
        verification_key=LOCAL_TEST_KEY,
        indian_book_path=tmp_path/"indian.sqlite",
    )
    intent=CryptoPaperIntent(f"{side.lower()}-{epoch}",side,qty,price,epoch)
    policy=policy or CryptoSpotReviewPolicy(90000,140000,9000,20,100)
    return dict(state=state,evidence=roles,book=book,intent=intent,
                policy=policy,now_epoch=epoch+age)


def make_test_permit(args, *, expires=None):
    book=args["book"]
    head=book.snapshot()
    return seal_crypto_paper_permit(
        LOCAL_TEST_KEY,account_id=book.account_id,revision=head.journal_revision,
        tip=head.journal_tip,intent=args["intent"],
        expires_epoch=expires if expires is not None else args["now_epoch"]+5,
    )


def approved(args, permit=None, human=True):
    return submit_reviewed_synthetic_paper(**args,permit=permit or make_test_permit(args),human_approved=human)


def test_happy_path_then_partial_close_full_close_restart(tmp_path):
    buy=fixture(tmp_path)
    receipt=approved(buy)
    assert receipt.paper_trade_recorded is True
    assert receipt.exchange_orders_transmitted==0
    assert receipt.test_permit_issued_by_gateway is False
    assert receipt.authenticated_human_identity_verified is False
    assert receipt.globally_mandatory_risk_gateway_verified is False
    assert receipt.live_trading_enabled is False and not receipt.production_ready
    assert buy["book"].snapshot().position_microcoin==10_000
    partial=fixture(tmp_path,side="SELL",epoch=102,qty=4_000,price=6_000_000)
    closed_part=approved(partial,human=False)
    assert closed_part.action=="SELL"
    assert partial["book"].snapshot().position_microcoin==6_000
    remainder=fixture(tmp_path,side="SELL",epoch=104,qty=6_000,price=6_000_000)
    final=approved(remainder,human=False)
    book=remainder["book"]
    s=book.snapshot()
    assert s.position_microcoin==0 and s.remaining_cost_basis_cents==0
    assert s.cash_cents==s.initial_cents+s.realized_net_pnl_cents
    assert final.realized_net_pnl_cents==s.realized_net_pnl_cents
    assert fixture(tmp_path,side="SELL",epoch=106)["book"].snapshot()==s


@pytest.mark.parametrize("bad",["none","fake_signature","expired","other_account",
                                "stale_head","wrong_intent","wrong_key"])
def test_invalid_test_permits_fail_closed(tmp_path,bad):
    args=fixture(tmp_path)
    permit=make_test_permit(args)
    if bad=="none": permit=None
    elif bad=="fake_signature": permit=replace(permit,signature_hex="0"*64)
    elif bad=="expired": permit=replace(permit,expires_epoch=100)
    elif bad=="other_account": permit=replace(permit,account_id="someone-else")
    elif bad=="stale_head": permit=replace(permit,expected_revision=1)
    elif bad=="wrong_intent":args["intent"]=replace(args["intent"],operation_id="different")
    elif bad=="wrong_key":
        permit=seal_crypto_paper_permit(b"X"*32,account_id=args["book"].account_id,
             revision=0,tip=args["book"].snapshot().journal_tip,intent=args["intent"],
             expires_epoch=110)
    with pytest.raises((CryptoReviewedPaperBlocked,CryptoPaperBlocked)):
        submit_reviewed_synthetic_paper(**args,permit=permit,human_approved=True)
    assert args["book"].snapshot().journal_revision==0


def test_buy_needs_explicit_test_only_local_approval(tmp_path):
    args=fixture(tmp_path)
    with pytest.raises(CryptoReviewedPaperBlocked,match="approval"):
        approved(args,human=False)
    assert args["book"].snapshot().journal_revision==0


@pytest.mark.parametrize("kind",["untrusted_source","expired_quote","wrong_role",
                                 "wrong_price","cap_violation","disabled_account","wrong_policy"])
def test_review_veto_happens_before_any_paper_event(tmp_path,kind):
    args=fixture(tmp_path,paper_enabled=(kind != "disabled_account"))
    if kind=="untrusted_source": args["state"]=replace(args["state"],provenance={"source_id":"PUBLIC_UNVERIFIED"})
    if kind=="expired_quote": args["now_epoch"]=200
    if kind=="wrong_role":args["evidence"]=(args["evidence"][0],)
    if kind=="wrong_price":args["intent"]=replace(args["intent"],price_cents_per_coin=4_000_000)
    if kind=="cap_violation":args["policy"]=replace(args["policy"],max_order_cents=49_000)
    if kind=="wrong_policy":args["policy"]=replace(args["policy"],max_order_cents=100_001)
    with pytest.raises((CryptoReviewedPaperBlocked,CryptoSpotIndependentReviewBlocked,ValueError)):
        approved(args)
    assert args["book"].snapshot().journal_revision==0


def test_journal_race_at_atomic_commit_denied(tmp_path,monkeypatch):
    args=fixture(tmp_path)
    book=args["book"]
    original=book.apply
    def concurrent_kill(intent,permit,**kwargs):
        book.stop("kill-race")
        return original(intent,permit,**kwargs)
    monkeypatch.setattr(book,"apply",concurrent_kill)
    with pytest.raises(CryptoPaperBlocked):approved(args)
    head=book.snapshot()
    assert head.journal_revision==1 and head.kill_active and head.position_microcoin==0


def test_protective_sell_after_kill_remains_available_with_signed_permit(tmp_path):
    buy=fixture(tmp_path)
    approved(buy)
    buy["book"].stop("emergency-stop")
    next_buy=fixture(tmp_path,epoch=102)
    with pytest.raises(ValueError):approved(next_buy)
    sell=fixture(tmp_path,side="SELL",epoch=104)
    receipt=approved(sell,human=False)
    assert receipt.action=="SELL" and not receipt.live_trading_enabled
    assert sell["book"].snapshot().position_microcoin==0


def test_no_replay_is_misrepresented_as_new_review(tmp_path):
    args=fixture(tmp_path)
    permit=make_test_permit(args)
    submit_reviewed_synthetic_paper(**args,permit=permit,human_approved=True)
    # Stage97 still owns idempotency; review route conservatively fails a new review.
    with pytest.raises(ValueError):
        submit_reviewed_synthetic_paper(**args,permit=permit,human_approved=True)
    assert args["book"].snapshot().journal_revision==1


def test_test_only_boolean_does_not_prove_authenticated_human(tmp_path):
    args=fixture(tmp_path)
    receipt=approved(args)
    assert receipt.authenticated_human_identity_verified is False
    assert receipt.globally_mandatory_risk_gateway_verified is False
    assert receipt.status.startswith("SYNTHETIC_")

@pytest.mark.parametrize("untrusted", [0, 1, "yes", None])
def test_invalid_or_non_boolean_human_approval_cannot_buy(tmp_path, untrusted):
    args=fixture(tmp_path)
    with pytest.raises(CryptoReviewedPaperBlocked):
        submit_reviewed_synthetic_paper(**args,permit=make_test_permit(args),
                                        human_approved=untrusted)
    assert args["book"].snapshot().journal_revision==0


def test_opt_in_limitation_stage97_direct_api_does_not_enforce_new_stricter_policy(tmp_path):
    """Document the unresolved all-entrypath enforcement gap, not a green signoff."""
    args=fixture(tmp_path)
    args["policy"]=replace(args["policy"],max_order_cents=49_000)
    with pytest.raises(CryptoSpotIndependentReviewBlocked):
        approved(args)
    # Existing Stage97 still validates its own *immutable* limits and signed
    # local test permit but does not know about the optional tighter review.
    state, duplicate=args["book"].apply(
        args["intent"],make_test_permit(args),
        now_epoch=args["now_epoch"],human_approved=True,autonomous=False,
    )
    assert not duplicate and state.journal_revision==1
    assert state.live_trading_enabled is False
    # Never claim a mandatory all-path independent Risk & Veto gate from this.

"""Actual synthetic BTC-USDT research -> consensus -> veto -> paper journal acceptance.

No broker/exchange calls. The generic lot-sizing model is ONLY a research signal:
it never signs CryptoPaperPermit or converts whole lots into microcoin quantity.
An explicit, test-local HMAC permit is separately provided to Stage97.
"""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from nexus_titan.intelligence.market_state import MarketStateBuilder
from nexus_titan.intelligence.specialist_roles import SpecialistEvidence, adapt_specialist_evidence
from nexus_titan.intelligence.pipeline import TradingIntelligencePipeline, RiskRequest, PipelineStatus
from nexus_titan.operations.crypto_research_preflight import (
    CryptoResearchPreflightBlocked, preflight_crypto_research,
)
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBook, CryptoPaperIntent, CryptoPaperLimits, CryptoPaperBlocked,
    seal_crypto_paper_permit,
)

TEST_KEY = b"STAGE97_RESEARCH_CHAIN_TEST_ONLY".ljust(32, b"Q")


def case(tmp_path, *, side="BUY", epoch=100, qty=10_000, price=5_000_000):
    dollar_price = price / 100
    state = MarketStateBuilder(max_age_seconds=30).build(
        exchange="CRYPTO_SYNTHETIC", symbol="BTC-USDT", interval="1m",
        event_time=datetime.fromtimestamp(epoch, timezone.utc),
        ingest_time=datetime.fromtimestamp(epoch + 1, timezone.utc),
        price_volume={"open": dollar_price, "high": dollar_price,
                      "low": dollar_price, "close": dollar_price, "volume": 1},
        regime={"label": "LOCAL_SYNTHETIC_ONLY"},
        options_flow={"status": "NOT_APPLICABLE"},
        context={"scenario": "deterministic_offline"},
        provenance={"source_id": "LOCAL_SYNTHETIC_TEST_ONLY"},
    )
    evidence = tuple(
        SpecialistEvidence(role, side, "Synthetic, independent test observation",
                           "synthetic:" + role + ":" + side,
                           "Invalidate on any source or regime mismatch")
        for role in ("MARKET_STRUCTURE", "TREND_REGIME")
    )
    book = CryptoPaperBook(
        path=tmp_path / "crypto-research-chain.sqlite",
        account_id="synthetic-crypto-chain",
        limits=CryptoPaperLimits(200_000, 100_000, 150_000, 10_000, paper_enabled=True),
        verification_key=TEST_KEY,
        indian_book_path=tmp_path / "distinct-indian-journal.sqlite",
    )
    intent = CryptoPaperIntent(
        f"chain-{side.lower()}-{epoch}", side, qty, price, epoch,
    )
    # Research-only generic whole-lot risk request; its size is deliberately
    # NOT used as a Stage97 microcoin execution quantity or approval.
    risk = RiskRequest(
        capital=1_000_000, entry_price=dollar_price,
        stop_price=dollar_price - 1_000 if side == "BUY" else dollar_price + 1_000,
        symbol="BTC-USDT", side=side, lot_size=1, tick_size=0.01,
    )
    return dict(
        pipeline=TradingIntelligencePipeline(), state=state,
        proposals=adapt_specialist_evidence(evidence),
        risk_request=risk, intent=intent, book=book, now_epoch=epoch + 2,
    )


def permit_for(args):
    account = args["book"].snapshot()
    return seal_crypto_paper_permit(
        TEST_KEY, account_id=account.account_id,
        revision=account.journal_revision, tip=account.journal_tip,
        intent=args["intent"], expires_epoch=args["now_epoch"] + 5,
    )


def research_only(args):
    before = args["book"].snapshot()
    receipt = preflight_crypto_research(**args)
    assert receipt.status == "RESEARCH_ONLY_PRECHECK_NO_EXECUTION"
    assert not any((receipt.risk_permit_issued, receipt.paper_order_submitted,
                    receipt.exchange_order_submitted, receipt.authorized_for_paper_execution,
                    receipt.live_trading_enabled, receipt.production_ready))
    assert args["book"].snapshot() == before
    return receipt


def test_actual_pipeline_research_then_independent_signed_buy_partial_sell_close_restart(tmp_path):
    buy = case(tmp_path)
    preflight = research_only(buy)
    assert preflight.action == "BUY" and preflight.journal_revision == 0
    with pytest.raises(CryptoPaperBlocked):
        buy["book"].apply(buy["intent"], None, now_epoch=buy["now_epoch"],
                          human_approved=True)
    assert buy["book"].snapshot().journal_revision == 0
    entry, duplicate = buy["book"].apply(
        buy["intent"], permit_for(buy), now_epoch=buy["now_epoch"],
        human_approved=True, autonomous=False,
    )
    assert not duplicate
    assert entry.position_microcoin == 10_000
    assert entry.total_fees_cents > 0

    partial = case(tmp_path, side="SELL", epoch=102, qty=4_000, price=6_000_000)
    research_only(partial)
    pstate, replay = partial["book"].apply(
        partial["intent"], permit_for(partial),
        now_epoch=partial["now_epoch"], human_approved=False, autonomous=False,
    )
    assert not replay and pstate.position_microcoin == 6_000

    rest = case(tmp_path, side="SELL", epoch=104, qty=6_000, price=6_000_000)
    research_only(rest)
    closed, replay = rest["book"].apply(
        rest["intent"], permit_for(rest),
        now_epoch=rest["now_epoch"], human_approved=False, autonomous=False,
    )
    assert not replay
    assert closed.position_microcoin == closed.remaining_cost_basis_cents == 0
    assert closed.cash_cents == closed.initial_cents + closed.realized_net_pnl_cents
    assert closed.realized_net_pnl_cents > 0
    assert case(tmp_path, side="SELL", epoch=106)["book"].snapshot() == closed


@pytest.mark.parametrize("fault", [
    "stale_state", "untrusted_source", "conflicting_evidence",
    "missing_risk", "wrong_risk_side", "over_limit", "future_quote",
    "unowned_sell", "disabled_account",
])
def test_actual_pipeline_preflight_veto_does_not_mutate_journal(tmp_path, fault):
    args = case(tmp_path)
    before = args["book"].snapshot()
    if fault == "stale_state":
        args["now_epoch"] = 200
    elif fault == "untrusted_source":
        args["state"] = replace(args["state"], provenance={"source_id": "PUBLIC_UNVERIFIED"})
    elif fault == "conflicting_evidence":
        proposals = list(args["proposals"])
        args["proposals"] = (
            proposals[0], replace(proposals[1], action="SELL")
        )
    elif fault == "missing_risk":
        args["risk_request"] = None
    elif fault == "wrong_risk_side":
        args["risk_request"] = replace(args["risk_request"], side="SELL")
    elif fault == "over_limit":
        args["intent"] = replace(args["intent"], quantity_microcoin=30_000)
    elif fault == "future_quote":
        args["now_epoch"] = 99
    elif fault == "unowned_sell":
        args = case(tmp_path, side="SELL")
    else:
        args["book"] = CryptoPaperBook(
            path=tmp_path / "disabled.sqlite", account_id="disabled-crypto",
            limits=CryptoPaperLimits(200_000, 100_000, 150_000, 10_000,
                                     paper_enabled=False),
            verification_key=TEST_KEY,
            indian_book_path=tmp_path / "distinct-indian-journal.sqlite",
        )
        before = args["book"].snapshot()
    with pytest.raises((CryptoResearchPreflightBlocked, ValueError)):
        preflight_crypto_research(**args)
    assert args["book"].snapshot() == before


def test_successful_research_never_grants_unapproved_or_forged_paper_write(tmp_path):
    args = case(tmp_path)
    research_only(args)
    good = permit_for(args)
    before = args["book"].snapshot()
    with pytest.raises(CryptoPaperBlocked):
        args["book"].apply(args["intent"], good, now_epoch=args["now_epoch"],
                           human_approved=False, autonomous=False)
    with pytest.raises(CryptoPaperBlocked):
        args["book"].apply(args["intent"],
                           replace(good, signature_hex="0" * 64),
                           now_epoch=args["now_epoch"],
                           human_approved=True, autonomous=False)
    assert args["book"].snapshot() == before


def test_research_pipeline_cannot_make_new_entry_after_emergency_kill(tmp_path):
    args = case(tmp_path)
    research_only(args)
    args["book"].stop("emergency-stop")
    before = args["book"].snapshot()
    assert before.kill_active
    with pytest.raises(CryptoResearchPreflightBlocked):
        preflight_crypto_research(**args)
    with pytest.raises(CryptoPaperBlocked):
        args["book"].apply(args["intent"], permit_for(args),
                           now_epoch=args["now_epoch"], human_approved=True,
                           autonomous=False)
    assert args["book"].snapshot() == before

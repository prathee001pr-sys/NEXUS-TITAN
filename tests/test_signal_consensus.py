from datetime import datetime, timezone
from nexus_titan.intelligence import MarketStateBuilder, ConsensusEngine, SignalProposal, Decision


def state():
    now = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)
    return MarketStateBuilder().build(exchange="NSE", symbol="NIFTY", interval="1m",
        event_time=now, ingest_time=now,
        price_volume={"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        regime={"label": "TRENDING"}, options_flow={"status": "NOT_APPLICABLE"},
        context={"events": []}, provenance={"source_id": "test-feed"})


def proposal(role, action):
    return SignalProposal(role, action, f"{role} reason", f"evidence:{role}", "close below support")


def test_agreement_only_proposes_candidate_not_order():
    result = ConsensusEngine().evaluate(state(), [proposal("T02", "BUY"), proposal("T05", "BUY")])
    assert result.decision is Decision.TRADE_CANDIDATE
    assert result.action == "BUY"
    assert result.confidence_label == "UNCALIBRATED"


def test_conflict_waits_for_confirmation():
    result = ConsensusEngine().evaluate(state(), [proposal("T02", "BUY"), proposal("T04", "SELL")])
    assert result.decision is Decision.WAIT_FOR_CONFIRMATION
    assert result.action is None


def test_hold_prevents_candidate():
    result = ConsensusEngine().evaluate(state(), [proposal("T02", "BUY"), proposal("T03", "HOLD")])
    assert result.decision is Decision.WAIT_FOR_CONFIRMATION


def test_no_proposals_means_no_trade():
    assert ConsensusEngine().evaluate(state(), []).decision is Decision.NO_TRADE


def test_incomplete_proposal_is_not_accepted():
    bad = SignalProposal("T02", "BUY", "", "", "")
    assert ConsensusEngine().evaluate(state(), [bad]).decision is Decision.WAIT_FOR_CONFIRMATION

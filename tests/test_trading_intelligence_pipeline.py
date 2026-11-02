from datetime import datetime, timezone

from nexus_titan.intelligence import MarketStateBuilder, SignalProposal
from nexus_titan.intelligence.pipeline import (
    PipelineStatus, RiskRequest, TradingIntelligencePipeline,
)


def market_state():
    now = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)
    return MarketStateBuilder().build(
        exchange="NSE", symbol="NIFTY", interval="1m", event_time=now, ingest_time=now,
        price_volume={"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        regime={"label": "TRENDING"}, options_flow={"status": "NOT_APPLICABLE"},
        context={"events": []}, provenance={"source_id": "test-feed"},
    )


def proposals():
    return [SignalProposal("T02", "BUY", "trend evidence", "evidence:trend", "close below support"),
            SignalProposal("T05", "BUY", "strategy evidence", "evidence:strategy", "close below support")]


def request(**overrides):
    values = dict(capital=50000, entry_price=101, stop_price=99, symbol="NIFTY",
                  side="BUY", lot_size=1, tick_size=0.05)
    values.update(overrides)
    return RiskRequest(**values)


def test_pipeline_requires_explicit_risk_check_before_candidate():
    result = TradingIntelligencePipeline().evaluate(market_state(), proposals())
    assert result.status is PipelineStatus.RISK_CHECK_REQUIRED
    assert result.order_submitted is False


def test_pipeline_passes_to_shadow_candidate_only_after_risk_approval():
    result = TradingIntelligencePipeline().evaluate(market_state(), proposals(), request())
    assert result.status is PipelineStatus.SHADOW_CANDIDATE
    assert result.risk_approved is True
    assert result.risk_quantity > 0
    assert result.order_submitted is False


def test_pipeline_rejects_risk_direction_mismatch():
    result = TradingIntelligencePipeline().evaluate(market_state(), proposals(), request(side="SELL"))
    assert result.status is PipelineStatus.RISK_REJECTED
    assert result.risk_quantity == 0


def test_pipeline_rejects_risk_veto():
    result = TradingIntelligencePipeline().evaluate(
        market_state(), proposals(), request(realized_daily_loss_pct=3.5))
    assert result.status is PipelineStatus.RISK_REJECTED
    assert result.risk_approved is False


def test_pipeline_blocks_invalid_market_state():
    now = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)
    invalid = MarketStateBuilder().build(exchange="NSE", symbol="NIFTY", interval="1m",
        event_time=now, ingest_time=now, price_volume={"close": 101})
    result = TradingIntelligencePipeline().evaluate(invalid, proposals(), request())
    assert result.status is PipelineStatus.DATA_INVALID
    assert result.order_submitted is False


def test_pipeline_rejects_malformed_risk_side_without_exception():
    result = TradingIntelligencePipeline().evaluate(
        market_state(), proposals(), request(side=None))
    assert result.status is PipelineStatus.RISK_REJECTED
    assert result.risk_quantity == 0

"""Compose existing as-of market analysis, options and signal/risk research.

Inputs/proposals remain synthetic/untrusted. EVOLVE is diagnostic only; no
research score can issue a permit, promote a strategy or change risk policy.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from nexus_titan.data.stage59_futures_history import Stage59FuturesHistory
from nexus_titan.data.stage71_fo_asof_alignment import Stage71FOLearningPreflight
from nexus_titan.derivatives.stage72_expiry_iv_research import Stage72OptionsResearchReport
from nexus_titan.evolve.stage73_fo_experience import FOEvolveReview
from nexus_titan.intelligence.consensus import SignalProposal
from nexus_titan.intelligence.market_state import MarketState, MarketStateBuilder
from nexus_titan.intelligence.pipeline import PipelineResult, RiskRequest, TradingIntelligencePipeline
from nexus_titan.research.market_intelligence import RegimeSnapshot, classify_regime, validate_ohlcv


@dataclass(frozen=True, slots=True)
class SyntheticFOAssessment:
    state: MarketState
    pipeline: PipelineResult
    regime: RegimeSnapshot
    completed_futures_bars: int
    source_stage71_sha256: str
    source_stage72_sha256: str
    stage73_review_sha256: str


def assess_synthetic_fo_research(
    *, futures: Stage59FuturesHistory, aligned: Stage71FOLearningPreflight,
    options: Stage72OptionsResearchReport, evolve: FOEvolveReview,
    proposals: tuple[SignalProposal, ...], risk_request: RiskRequest,
    now: datetime,
) -> SyntheticFOAssessment:
    if not (isinstance(futures, Stage59FuturesHistory)
            and isinstance(aligned, Stage71FOLearningPreflight)
            and isinstance(options, Stage72OptionsResearchReport)
            and isinstance(evolve, FOEvolveReview)):
        raise ValueError("Typed ingested F&O research inputs required")
    if (aligned.input_alignment_sha256 != options.source_alignment_sha256
            or futures.underlying != aligned.underlying or options.underlying != aligned.underlying
            or any(getattr(evolve, k) is not False for k in (
                'strategy_promotion_authorized','paper_order_authorized','live_trading_enabled','model_weights_updated'))
            or evolve.broker_orders_transmitted != 0):
        raise ValueError("Research source binding or EVOLVE no-authority boundary violated")
    matches = [o for o in aligned.observations if o.option_observed_at == options.observation_time
               and o.option_snapshot_sha256 == options.source_option_sha256
               and o.futures_csv_sha256 == futures.file_sha256]
    if len(matches) != 1:
        raise ValueError("Options observation is not bound to ingested futures")
    step = timedelta(minutes=int(futures.timeframe[:-1]))
    bars = tuple(b for b in futures.candles if b.timestamp + step <= options.observation_time)
    if not bars or bars[-1].timestamp != matches[0].futures_bar_opened_at:
        raise ValueError("Completed as-of futures candle unavailable")
    arrays = {name: [float(getattr(b, name)) for b in bars]
              for name in ('open','high','low','close','volume')}
    validate_ohlcv(arrays['high'],arrays['low'],arrays['open'],arrays['close'],arrays['volume'])
    regime = classify_regime(arrays['close'],arrays['high'],arrays['low'])
    last = {name: values[-1] for name,values in arrays.items()}
    state = MarketStateBuilder(max_age_seconds=30).build(
        exchange='NSE', symbol=options.symbol, interval=futures.timeframe,
        event_time=options.observation_time, ingest_time=now,
        price_volume=last, regime=asdict(regime),
        options_flow={'iv_mid': tuple(row.iv_mid for row in options.rows),
                      'research_sha256': options.research_output_sha256},
        context={'synthetic_only':True,'evolve_paired_count':evolve.paired_count,
                 'evolve_mode':'DIAGNOSTIC_NO_PROMOTION'},
        provenance={'source_id':futures.dataset_id,'csv_sha256':futures.file_sha256},
    )
    # Do not manufacture a signal when the actual analytics lack warm-up data.
    effective = () if 'UNKNOWN' in (regime.trend,regime.volatility) else proposals
    result = TradingIntelligencePipeline().evaluate(state,effective,risk_request)
    return SyntheticFOAssessment(state,result,regime,len(bars),aligned.input_alignment_sha256,
                                 options.research_output_sha256,evolve.review_sha256)

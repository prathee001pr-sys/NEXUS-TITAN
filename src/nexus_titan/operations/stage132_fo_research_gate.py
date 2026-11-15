"""Fail-closed Stage132 integration; never promotes snapshot to execution."""
from dataclasses import dataclass
from .stage129_contract_guard import review_contract,ContractReview
from .stage130_greeks_iv import estimate_option,OptionEstimate
from .stage131_cost_margin import estimate_cost_margin,CostEstimate

@dataclass(frozen=True)
class FOResearchReview:
    contract: ContractReview
    estimate: OptionEstimate | None
    costs: CostEstimate | None
    reasons: tuple[str,...]
    verdict: str = 'RESEARCH_ONLY_NO_GO'
    historical_backtest_approved: bool = False
    paper_trading_approved: bool = False
    live_trading_enabled: bool = False

def review_fo_research(*, underlying: str, expiry: str, strike: float, side: str, as_of: str, spot: float, years: float, volatility: float, rate: float, premium: float, quantity: int, capital: float, brokerage: float, other_fees: float, slippage_per_unit: float, margin_requirement: float) -> FOResearchReview:
    contract=review_contract(underlying,expiry,strike,side,as_of=as_of)
    if not contract.valid: return FOResearchReview(contract,None,None,contract.reasons)
    try:
        model=estimate_option(spot=spot,strike=strike,years=years,volatility=volatility,rate=rate,side=side)
        costs=estimate_cost_margin(premium=premium,quantity=quantity,capital=capital,brokerage=brokerage,other_fees=other_fees,slippage_per_unit=slippage_per_unit,margin_requirement=margin_requirement)
    except (ValueError,OverflowError,ZeroDivisionError) as exc:
        return FOResearchReview(contract,None,None,('INVALID_RESEARCH_INPUT',))
    reasons=('INSUFFICIENT_ESTIMATED_CAPITAL',) if not costs.sufficient_capital else ('UNVERIFIED_MARKET_DATA_AND_MARGIN',)
    return FOResearchReview(contract,model,costs,reasons)

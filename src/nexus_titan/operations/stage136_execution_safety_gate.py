"""Stage 136 never authorizes live, paper, or real broker execution."""
from dataclasses import dataclass
from .stage133_fill_simulator import simulate_limit,PaperFill
from .stage134_execution_costs import estimate_paper_costs,PaperCosts
from .stage135_fill_reconciliation import reconcile_paper,PaperReconciliation

@dataclass(frozen=True)
class ExecutionResearchGate:
    fill: PaperFill
    costs: PaperCosts | None
    reconciliation: PaperReconciliation
    verdict: str = 'RESEARCH_ONLY_NO_GO'
    live_trading_enabled: bool = False
    paper_execution_authorized: bool = False
    broker_order_authorized: bool = False

def evaluate_execution_research(*, side: str, quantity: int, limit_price: float, bid: float, ask: float, bid_size: int, ask_size: int, slippage: float, brokerage_flat: float, fee_rate: float) -> ExecutionResearchGate:
    fill=simulate_limit(side=side,quantity=quantity,limit_price=limit_price,bid=bid,ask=ask,bid_size=bid_size,ask_size=ask_size,slippage=slippage)
    events=(("synthetic-1",fill.filled,fill.average_price),) if fill.filled else ()
    reconciliation=reconcile_paper(order_quantity=quantity,events=events)
    costs=estimate_paper_costs(quantity=fill.filled,price=fill.average_price,brokerage_flat=brokerage_flat,fee_rate=fee_rate) if fill.filled else None
    return ExecutionResearchGate(fill,costs,reconciliation)

"""Stage95: connect existing validated research to the selected CE/PE journal.

No broker adapter, credential loading, authority creation or live switch exists.
The caller's independent test controller supplies every signed risk/close permit.
The permission flags are local instructions, not authenticated human identity.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from nexus_titan.cost.charges import IndianCostConfig, calculate_indian_trade_costs
from nexus_titan.operations.fo_risk_boundary import SyntheticFOOperation, SyntheticFORiskBoundary
from nexus_titan.operations.paper_controls import PaperAccess, PaperOperationBlocked
from nexus_titan.operations.synthetic_fo_execution import SyntheticFOExecutionGateway
from nexus_titan.operations.synthetic_option_positions import SyntheticCloseRequest
from nexus_titan.operations.synthetic_fo_research import assess_synthetic_fo_research
from nexus_titan.intelligence.consensus import SignalProposal
from nexus_titan.research.signal_engine import generate_signal


def assess_fo_strategy(*, boundary, futures, aligned, options, evolve,
                      confirmation, risk_request, now):
    """SMA on completed underlying bars plus an explicit second evidence lane.

    Rising underlying can propose a long CE; falling can propose a long PE.
    A caller-supplied confirmation is still untrusted research input. Neither
    this result nor a local permission flag can issue an execution permit.
    """
    contract = boundary.position_contract(options.symbol)
    step = timedelta(minutes=int(futures.timeframe[:-1]))
    closes = [float(bar.close) for bar in futures.candles
              if bar.timestamp + step <= options.observation_time]
    signal = generate_signal(closes)
    wanted = 'BUY' if contract['option_type']=='CE' else 'SELL'
    action = 'BUY' if signal.action==wanted else 'HOLD'
    strategy = SignalProposal('SMA_RULE',action,signal.reason,futures.file_sha256,
                              'Underlying SMA direction reverses or data/risk quality fails')
    if not isinstance(confirmation, SignalProposal) or confirmation.specialist_id=='SMA_RULE':
        raise PaperOperationBlocked("A distinct, explicit confirmation lane is required")
    return assess_synthetic_fo_research(
        futures=futures, aligned=aligned, options=options, evolve=evolve,
        proposals=(strategy,confirmation),risk_request=risk_request,now=now,
    )


@dataclass(frozen=True, slots=True)
class PaperExecutionAssumptions:
    slippage_ticks: int = 1
    max_spread_ticks: int = 10

    def __post_init__(self):
        if (type(self.slippage_ticks) is not int or not 0 <= self.slippage_ticks <= 100
                or type(self.max_spread_ticks) is not int
                or not 1 <= self.max_spread_ticks <= 100):
            raise PaperOperationBlocked("Bounded integer execution assumptions required")

    def price(self, side, bid, ask, tick):
        if (side not in ("BUY", "SELL")
                or any(type(x) is not int or not 0 < x <= 10**12 for x in (bid, ask, tick))
                or bid > ask or bid % tick or ask % tick
                or ask - bid > self.max_spread_ticks * tick):
            raise PaperOperationBlocked("Invalid, crossed, off-tick or excessive-spread quote")
        value = ask + self.slippage_ticks*tick if side == "BUY" else bid-self.slippage_ticks*tick
        if value <= 0:
            raise PaperOperationBlocked("Slippage leaves no positive execution price")
        return value


class FOClosedTradePipeline:
    def __init__(self, gateway: SyntheticFOExecutionGateway, *, boundary: SyntheticFORiskBoundary,
                 access: PaperAccess, costs: IndianCostConfig = IndianCostConfig(),
                 execution: PaperExecutionAssumptions = PaperExecutionAssumptions()):
        if (not isinstance(gateway, SyntheticFOExecutionGateway)
                or not isinstance(boundary, SyntheticFORiskBoundary)
                or gateway.boundary_sha256 != boundary.digest
                or not isinstance(access, PaperAccess)
                or not isinstance(costs, IndianCostConfig)
                or not isinstance(execution, PaperExecutionAssumptions)):
            raise PaperOperationBlocked("Explicit matching selected F&O account and paper policies required")
        self.gateway, self.boundary, self.access = gateway, boundary, access
        self.costs, self.execution = costs, execution

    def terms(self, *, symbol, side, quantity, bid_cents, ask_cents):
        contract = self.boundary.position_contract(symbol)  # CE/PE only; futures fail closed.
        if type(quantity) is not int or not 0 < quantity <= 10000:
            raise PaperOperationBlocked("Positive bounded whole-unit fill quantity required")
        price = self.execution.price(side, bid_cents, ask_cents, contract['tick_cents'])
        costs = calculate_indian_trade_costs(side, price/100, quantity, 'OPTIONS', self.costs)
        cents = int((Decimal(str(costs.total_charges))*100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        return price, cents, costs

    def open(self, operation, *, assessment, risk_permit, human_approved=False, autonomous=False):
        self.access.require(human_approved=human_approved, autonomous=autonomous)
        return self.gateway.apply_assessed_open(operation, assessment=assessment, risk_permit=risk_permit)

    def fill(self, operation, *, risk_permit, bid_cents, ask_cents, available_quantity,
             human_approved=False, autonomous=False):
        self.access.require(human_approved=human_approved, autonomous=autonomous)
        if not isinstance(operation, SyntheticFOOperation) or operation.kind != 'FILL':
            raise PaperOperationBlocked("Typed fill operation required")
        if (type(available_quantity) is not int or not 0 < available_quantity <= 10000
                or operation.quantity > available_quantity):
            raise PaperOperationBlocked("Synthetic fill exceeds declared available liquidity")
        matches = [o for o in self.gateway.snapshot().orders if o.order_id == operation.order_id]
        if len(matches) != 1:
            raise PaperOperationBlocked("An existing selected order is required")
        price, fee, _ = self.terms(symbol=matches[0].symbol, side='BUY', quantity=operation.quantity,
                                 bid_cents=bid_cents, ask_cents=ask_cents)
        if (operation.price_cents, operation.fee_cents) != (price, fee):
            raise PaperOperationBlocked("Fill must include configured spread, slippage and charges")
        return self.gateway.apply(operation, risk_permit=risk_permit)

    def close(self, request, *, authorization, bid_cents, ask_cents):
        # Signed reduce-only exits stay available after an emergency stop.
        if not isinstance(request, SyntheticCloseRequest):
            raise PaperOperationBlocked("Typed signed reduce-only close required")
        price, fee, _ = self.terms(symbol=request.symbol, side='SELL', quantity=request.quantity,
                                 bid_cents=bid_cents, ask_cents=ask_cents)
        if (request.price_cents, request.fee_cents) != (price, fee):
            raise PaperOperationBlocked("Close must include configured execution costs")
        return self.gateway.close_position(request, authorization=authorization)

    def cancel(self, operation):
        if not isinstance(operation, SyntheticFOOperation) or operation.kind != 'CANCEL':
            raise PaperOperationBlocked("Only cancellation reduces an unfilled reservation")
        return self.gateway.apply(operation)

    def dashboard(self):
        snapshot = self.gateway.snapshot()  # One durable revision for every number.
        if snapshot.cash_cents+snapshot.remaining_cost_basis_cents != (
                snapshot.initial_cents+snapshot.realized_net_pnl_cents):
            raise PaperOperationBlocked("Capital conservation failed")
        report = self.gateway._performance(snapshot)
        return {
            'schema_version': 1, 'market': 'INDIAN_FO', 'currency': 'INR',
            'source': 'SYNTHETIC_SQLITE_JOURNAL', 'account': asdict(snapshot),
            'performance': asdict(report), 'cost_schedule': asdict(self.costs),
            'execution_assumptions': asdict(self.execution),
            'paper_controls': asdict(self.access), 'live_trading_enabled': False,
            'real_market_shadow_validated': False, 'broker_orders_transmitted': 0,
        }

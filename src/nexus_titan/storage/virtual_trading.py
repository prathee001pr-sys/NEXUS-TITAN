"""Record approved research decisions in a local virtual trade ledger only."""
from pathlib import Path
from uuid import uuid4

from nexus_titan.storage.trade_ledger import TradeLedger
from nexus_titan.trading_engine import TradingDecision


def record_virtual_decision(
    decision: TradingDecision, symbol: str, entry_price: float, stop_price: float,
    ledger_path: str | Path = "data/virtual_trades.json",
) -> dict:
    if decision.signal != "BUY":
        return {"recorded": False, "trade_id": None,
                "reason": f"No virtual trade: signal is {decision.signal}."}
    if not decision.approved or decision.quantity < 1:
        return {"recorded": False, "trade_id": None,
                "reason": f"Risk check rejected trade: {decision.reason}"}
    trade_id=f"TITAN-{uuid4().hex[:12].upper()}"
    trade=TradeLedger(ledger_path).open_trade(
        trade_id,symbol,entry_price,decision.quantity,stop_price)
    return {"recorded": True,"trade_id":trade.trade_id,"symbol":trade.symbol,
            "entry_price":trade.entry_price,"quantity":trade.quantity,
            "stop_price":trade.stop_price,"status":trade.status,
            "reason":decision.reason}

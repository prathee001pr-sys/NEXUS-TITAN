"""Simple atomic JSON ledger for local virtual trade records."""
from __future__ import annotations
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class VirtualTrade:
    trade_id: str
    symbol: str
    entry_price: float
    quantity: int
    stop_price: float
    status: str = "OPEN"
    exit_price: float | None = None
    realized_pnl: float | None = None
    opened_at: str = ""
    closed_at: str | None = None


class TradeLedger:
    def __init__(self, path: str | Path = "data/virtual_trades.json"):
        self.path = Path(path)

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            value=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot read trade ledger: {exc}") from exc
        if not isinstance(value,list):
            raise ValueError("Trade ledger must contain a JSON list.")
        return value

    def _write(self, trades: list[dict]) -> None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix(self.path.suffix+".tmp")
        temporary.write_text(json.dumps(trades,indent=2),encoding="utf-8")
        temporary.replace(self.path)

    def list_trades(self) -> list[dict]:
        return self._read()

    def open_trade(self,trade_id: str,symbol: str,entry_price: float,quantity: int,stop_price: float) -> VirtualTrade:
        if not isinstance(trade_id,str) or not trade_id.strip() or not isinstance(symbol,str) or not symbol.strip():
            raise ValueError("Trade ID and symbol are required.")
        for label,value in (("entry_price",entry_price),("stop_price",stop_price)):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError(f"{label} must be finite.")
        if entry_price<=0 or stop_price<=0 or stop_price>=entry_price:
            raise ValueError("For long trades, stop must be positive and below entry.")
        if isinstance(quantity,bool) or not isinstance(quantity,int) or quantity<1:
            raise ValueError("Quantity must be a positive integer.")
        trades=self._read()
        if any(item.get("trade_id")==trade_id for item in trades):
            raise ValueError("Trade ID already exists.")
        trade=VirtualTrade(trade_id,symbol.strip().upper(),float(entry_price),quantity,float(stop_price),
                           opened_at=datetime.now(timezone.utc).isoformat())
        trades.append(asdict(trade)); self._write(trades)
        return trade

    def close_trade(self,trade_id: str,exit_price: float) -> dict:
        if isinstance(exit_price,bool) or not isinstance(exit_price,(int,float)) or not math.isfinite(exit_price) or exit_price<=0:
            raise ValueError("Exit price must be finite and positive.")
        trades=self._read()
        for item in trades:
            if item.get("trade_id")==trade_id:
                if item.get("status")!="OPEN": raise ValueError("Trade is not open.")
                item["exit_price"]=float(exit_price)
                item["realized_pnl"]=round((float(exit_price)-item["entry_price"])*item["quantity"],2)
                item["status"]="CLOSED"
                item["closed_at"]=datetime.now(timezone.utc).isoformat()
                self._write(trades); return item
        raise ValueError("Trade ID not found.")

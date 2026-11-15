"""ACID SQLite ledger for completed and open virtual trades."""
from __future__ import annotations
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class SQLiteTradeLedger:
    def __init__(self, db_path: str | Path = "data/virtual_trades.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, entry_price REAL NOT NULL,
                quantity INTEGER NOT NULL, stop_price REAL NOT NULL, status TEXT NOT NULL
                CHECK(status IN ('OPEN','CLOSED','CANCELLED')), exit_price REAL,
                realized_pnl REAL, fees REAL NOT NULL DEFAULT 0.0, opened_at TEXT NOT NULL,
                closed_at TEXT, notes TEXT)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10.0)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _positive(name, value):
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive.")

    def open_trade(self, trade_id: str, symbol: str, entry_price: float, quantity: int,
                   stop_price: float, fee: float=0.0, notes: str="") -> dict:
        if not trade_id or not isinstance(trade_id,str) or not symbol or not isinstance(symbol,str):
            raise ValueError("Trade ID and symbol are required.")
        self._positive("entry_price",entry_price); self._positive("stop_price",stop_price)
        if stop_price >= entry_price: raise ValueError("Stop must be below entry for a long trade.")
        if isinstance(quantity,bool) or not isinstance(quantity,int) or quantity < 1: raise ValueError("Quantity must be positive integer.")
        if isinstance(fee,bool) or not isinstance(fee,(int,float)) or not math.isfinite(fee) or fee < 0: raise ValueError("Fee must be finite and non-negative.")
        try:
            with self._connect() as db:
                db.execute("INSERT INTO trades(trade_id,symbol,entry_price,quantity,stop_price,status,fees,opened_at,notes) VALUES(?,?,?,?,?,'OPEN',?,?,?)",
                           (trade_id.strip(),symbol.strip().upper(),float(entry_price),quantity,float(stop_price),float(fee),datetime.now(timezone.utc).isoformat(),notes))
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Trade ID '{trade_id}' already exists.") from exc
        return self.get_trade(trade_id)

    def close_trade(self, trade_id: str, exit_price: float, exit_fee: float=0.0, notes: str|None=None) -> dict:
        self._positive("exit_price",exit_price)
        if isinstance(exit_fee,bool) or not isinstance(exit_fee,(int,float)) or not math.isfinite(exit_fee) or exit_fee < 0:
            raise ValueError("exit_fee must be finite and non-negative.")
        with self._connect() as db:
            row=db.execute("SELECT * FROM trades WHERE trade_id=?",(trade_id,)).fetchone()
            if not row: raise ValueError(f"Trade ID '{trade_id}' not found.")
            if row["status"]!="OPEN": raise ValueError(f"Trade is already {row['status']}.")
            fees=row["fees"]+float(exit_fee)
            pnl=round((float(exit_price)-row["entry_price"])*row["quantity"]-fees,2)
            db.execute("UPDATE trades SET status='CLOSED',exit_price=?,realized_pnl=?,fees=?,closed_at=?,notes=? WHERE trade_id=?",
                       (float(exit_price),pnl,fees,datetime.now(timezone.utc).isoformat(),notes if notes is not None else row["notes"],trade_id))
        return self.get_trade(trade_id)

    def get_trade(self, trade_id: str) -> dict|None:
        with self._connect() as db:
            row=db.execute("SELECT * FROM trades WHERE trade_id=?",(trade_id,)).fetchone()
            return dict(row) if row else None

    def list_trades(self,status: str|None=None,symbol: str|None=None,limit: int|None=None) -> list[dict]:
        query="SELECT * FROM trades WHERE 1=1"; params=[]
        if status: query+=" AND status=?"; params.append(status.upper())
        if symbol: query+=" AND symbol=?"; params.append(symbol.upper())
        query+=" ORDER BY opened_at DESC"
        if limit is not None:
            if isinstance(limit,bool) or not isinstance(limit,int) or limit < 1: raise ValueError("limit must be positive integer.")
            query+=" LIMIT ?"; params.append(limit)
        with self._connect() as db: return [dict(r) for r in db.execute(query,params).fetchall()]

    def get_performance_summary(self) -> dict:
        with self._connect() as db: rows=db.execute("SELECT realized_pnl,fees FROM trades WHERE status='CLOSED'").fetchall()
        if not rows: return {"total_closed_trades":0,"winning_trades":0,"losing_trades":0,"win_rate_percent":0.0,"total_net_pnl":0.0,"total_fees":0.0,"profit_factor":None,"expectancy":0.0}
        pnls=[r["realized_pnl"] for r in rows]; wins=sum(p>0 for p in pnls); losses=sum(p<0 for p in pnls)
        gp=sum(p for p in pnls if p>0); gl=-sum(p for p in pnls if p<0); total=sum(pnls)
        return {"total_closed_trades":len(rows),"winning_trades":wins,"losing_trades":losses,
                "win_rate_percent":round(wins/len(rows)*100,2),"total_net_pnl":round(total,2),
                "total_fees":round(sum(r["fees"] for r in rows),2),
                "profit_factor":round(gp/gl,4) if gl else None,"expectancy":round(total/len(rows),2)}

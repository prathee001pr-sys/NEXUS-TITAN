"""Small SQLite store for validated historical OHLCV candles."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle


@dataclass(frozen=True, slots=True)
class StoreResult:
    inserted: int
    duplicates: int


class SQLiteCandleStore:
    """Persist candles locally; duplicate symbol/timeframe/timestamp keys are ignored."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open TEXT NOT NULL,
                    high TEXT NOT NULL,
                    low TEXT NOT NULL,
                    close TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_candles_query "
                "ON candles (symbol, timeframe, timestamp)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def store(self, candles: tuple[OHLCVCandle, ...] | list[OHLCVCandle]) -> StoreResult:
        if not isinstance(candles, (tuple, list)):
            raise TypeError("candles must be a tuple or list")
        if any(not isinstance(item, OHLCVCandle) for item in candles):
            raise TypeError("all items must be OHLCVCandle objects")
        inserted = 0
        with self._connect() as connection:
            for candle in candles:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO candles
                    (symbol, timeframe, timestamp, open, high, low, close, volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candle.symbol, candle.timeframe, candle.timestamp.isoformat(),
                        str(candle.open), str(candle.high), str(candle.low),
                        str(candle.close), str(candle.volume), candle.source,
                    ),
                )
                inserted += cursor.rowcount
        return StoreResult(inserted=inserted, duplicates=len(candles) - inserted)

    def fetch(self, query: CandleQuery) -> tuple[OHLCVCandle, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, timeframe, timestamp, open, high, low, close, volume, source
                FROM candles
                WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp < ?
                ORDER BY timestamp ASC
                """,
                (
                    query.symbol, query.timeframe,
                    query.start.isoformat(), query.end.isoformat(),
                ),
            ).fetchall()
        return tuple(
            OHLCVCandle(
                symbol=row[0], timeframe=row[1],
                timestamp=datetime.fromisoformat(row[2]),
                open=Decimal(row[3]), high=Decimal(row[4]), low=Decimal(row[5]),
                close=Decimal(row[6]), volume=Decimal(row[7]), source=row[8],
            )
            for row in rows
        )

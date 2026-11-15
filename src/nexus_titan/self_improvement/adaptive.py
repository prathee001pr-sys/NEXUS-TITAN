"""Regime-aware strategy evidence registry and recommendation-only selector.

This module recommends candidates for research review; it never routes orders.
"""
from __future__ import annotations

import math
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class MarketRegime:
    name: str
    trend_percent: float
    volatility_percent: float
    lookback: int


@dataclass(frozen=True)
class StrategyRegimeEvidence:
    observation_id: str
    strategy_key: str
    regime: str
    observations: int
    net_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None
    source: str
    recorded_at: str


@dataclass(frozen=True)
class StrategyRecommendation:
    regime: str
    strategy_key: str | None
    score: float | None
    observations: int
    status: str
    explanation: str


class MarketRegimeDetector:
    """Transparent close-price detector; thresholds are explicit and configurable."""

    def __init__(self, lookback: int = 20, trend_threshold_pct: float = 2.0,
                 high_volatility_threshold_pct: float = 2.5) -> None:
        if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 5:
            raise ValueError("lookback must be an integer of at least 5.")
        thresholds = (trend_threshold_pct, high_volatility_threshold_pct)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in thresholds):
            raise ValueError("Regime thresholds must be finite positive numbers.")
        self.lookback = lookback
        self.trend_threshold_pct = trend_threshold_pct
        self.high_volatility_threshold_pct = high_volatility_threshold_pct

    def classify(self, candles: list[dict[str, float]]) -> MarketRegime:
        if len(candles) < self.lookback + 1:
            return MarketRegime("UNKNOWN", 0.0, 0.0, len(candles))
        closes = [float(c["close"]) for c in candles[-(self.lookback + 1):]]
        if any(not math.isfinite(v) or v <= 0 for v in closes):
            raise ValueError("Regime detection requires finite positive close prices.")
        trend = (closes[-1] / closes[0] - 1.0) * 100.0
        returns = [(closes[i] / closes[i - 1] - 1.0) * 100.0 for i in range(1, len(closes))]
        mean = sum(returns) / len(returns)
        variance = sum((v - mean) ** 2 for v in returns) / len(returns)
        volatility = math.sqrt(variance)
        if volatility >= self.high_volatility_threshold_pct:
            regime = "HIGH_VOLATILITY"
        elif trend >= self.trend_threshold_pct:
            regime = "TRENDING_UP"
        elif trend <= -self.trend_threshold_pct:
            regime = "TRENDING_DOWN"
        else:
            regime = "RANGING"
        return MarketRegime(regime, round(trend, 4), round(volatility, 4), self.lookback)


class StrategyEvidenceRegistry:
    def __init__(self, db_path: str | Path = "data/titan_learning.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS strategy_regime_evidence (
                observation_id TEXT PRIMARY KEY, strategy_key TEXT NOT NULL, regime TEXT NOT NULL,
                observations INTEGER NOT NULL, net_return_pct REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL, sharpe_ratio REAL, source TEXT NOT NULL,
                recorded_at TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_strategy_regime ON strategy_regime_evidence(strategy_key, regime)")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record(self, strategy_key: str, regime: str, observations: int, net_return_pct: float,
               max_drawdown_pct: float, sharpe_ratio: float | None, source: str) -> StrategyRegimeEvidence:
        if not strategy_key.strip() or not regime.strip() or not source.strip():
            raise ValueError("strategy_key, regime and source are required.")
        if isinstance(observations, bool) or not isinstance(observations, int) or observations < 1:
            raise ValueError("observations must be a positive integer.")
        values = [net_return_pct, max_drawdown_pct]
        if sharpe_ratio is not None:
            values.append(sharpe_ratio)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError("Performance values must be finite numbers.")
        if max_drawdown_pct < 0:
            raise ValueError("max_drawdown_pct cannot be negative.")
        item = StrategyRegimeEvidence(str(uuid.uuid4()), strategy_key.strip(), regime.strip().upper(),
            observations, float(net_return_pct), float(max_drawdown_pct),
            None if sharpe_ratio is None else float(sharpe_ratio), source.strip(), datetime.now(timezone.utc).isoformat())
        with self._connect() as db:
            db.execute("INSERT INTO strategy_regime_evidence VALUES(?,?,?,?,?,?,?,?,?)", tuple(asdict(item).values()))
        return item

    def recommend(self, regime: str, min_observations: int = 30,
                  max_drawdown_limit_pct: float = 10.0) -> StrategyRecommendation:
        if isinstance(min_observations, bool) or not isinstance(min_observations, int) or min_observations < 30:
            raise ValueError("min_observations must be an integer of at least 30.")
        if isinstance(max_drawdown_limit_pct, bool) or not isinstance(max_drawdown_limit_pct, (int, float)) or not math.isfinite(max_drawdown_limit_pct) or max_drawdown_limit_pct < 0:
            raise ValueError("max_drawdown_limit_pct must be a finite non-negative number.")
        with self._connect() as db:
            rows = db.execute("""SELECT strategy_key, SUM(observations),
                SUM(net_return_pct * observations) / SUM(observations),
                MAX(max_drawdown_pct),
                SUM(COALESCE(sharpe_ratio, 0) * observations) / SUM(observations)
                FROM strategy_regime_evidence WHERE regime=? GROUP BY strategy_key""",
                (regime.upper(),)).fetchall()
        eligible = []
        for key, count, avg_return, worst_dd, avg_sharpe in rows:
            if count >= min_observations and worst_dd <= max_drawdown_limit_pct:
                score = float(avg_return) + 0.25 * float(avg_sharpe) - 0.5 * float(worst_dd)
                eligible.append((score, key, count))
        if not eligible:
            return StrategyRecommendation(regime.upper(), None, None, 0, "NO_RECOMMENDATION",
                f"No strategy has at least {min_observations} regime-specific observations within the drawdown limit.")
        score, key, count = max(eligible, key=lambda row: (row[0], row[2], row[1]))
        return StrategyRecommendation(regime.upper(), key, round(score, 4), int(count), "RESEARCH_CANDIDATE",
            "Evidence-weighted research suggestion only; independent validation and human approval remain mandatory.")

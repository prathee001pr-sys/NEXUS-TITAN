"""Generate research signals from validated CSV market data."""
from pathlib import Path
from nexus_titan.data.market_data import load_market_data
from nexus_titan.research.signal_engine import Signal, generate_signal


def signal_from_csv(path: str | Path, fast_period: int = 5, slow_period: int = 10) -> tuple[Signal | None, tuple[str, ...]]:
    result = load_market_data(path)
    if not result.is_valid:
        return None, result.errors or ("Market data is invalid or empty.",)
    closes = [candle.close for candle in result.candles]
    signal = generate_signal(closes, fast_period=fast_period, slow_period=slow_period)
    return signal, ()

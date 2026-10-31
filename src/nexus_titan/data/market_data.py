"""CSV market-data loader for NEXUS TITAN."""
from dataclasses import dataclass
from datetime import datetime
import csv
import math
from pathlib import Path


@dataclass(frozen=True)
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketDataResult:
    candles: tuple[Candle, ...]
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return bool(self.candles) and not self.errors


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def load_market_data(path: str | Path) -> MarketDataResult:
    file_path = Path(path)
    candles: list[Candle] = []
    errors: list[str] = []
    seen_timestamps = set()
    previous_timestamp = None
    try:
        with file_path.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                return MarketDataResult((), ("CSV file is empty.",))
            headers = [name.strip() for name in reader.fieldnames]
            missing = [name for name in REQUIRED_COLUMNS if name not in headers]
            if missing:
                return MarketDataResult((), (f"Missing required columns: {', '.join(missing)}",))
            for row_number, row in enumerate(reader, start=2):
                try:
                    cleaned = {(key.strip() if key else key): value for key, value in row.items()}
                    timestamp = (cleaned.get("timestamp") or "").strip()
                    parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    if parsed_timestamp in seen_timestamps:
                        raise ValueError("duplicate candle timestamp")
                    if previous_timestamp is not None and parsed_timestamp <= previous_timestamp:
                        raise ValueError("candle timestamps must be in increasing order")
                    seen_timestamps.add(parsed_timestamp)
                    previous_timestamp = parsed_timestamp
                    values = {}
                    for name in ("open", "high", "low", "close", "volume"):
                        raw_value = cleaned.get(name)
                        if raw_value is None or not raw_value.strip():
                            raise ValueError(f"{name} is empty")
                        values[name] = float(raw_value)
                    if not all(math.isfinite(value) for value in values.values()):
                        raise ValueError("values must be finite numbers")
                    o, h, l, c, v = (values[k] for k in ("open", "high", "low", "close", "volume"))
                    if min(o, h, l, c) <= 0:
                        raise ValueError("prices must be positive")
                    if v < 0:
                        raise ValueError("volume cannot be negative")
                    if h < max(o, l, c):
                        raise ValueError("high is below an OHLC price")
                    if l > min(o, h, c):
                        raise ValueError("low is above an OHLC price")
                    candles.append(Candle(timestamp, o, h, l, c, v))
                except (ValueError, TypeError, AttributeError) as error:
                    errors.append(f"Row {row_number}: {error}")
    except (OSError, csv.Error) as error:
        return MarketDataResult((), (f"Could not read CSV: {error}",))
    if not candles and not errors:
        errors.append("CSV contains no market-data rows.")
    return MarketDataResult(tuple(candles), tuple(errors))

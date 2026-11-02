"""Immutable, quality-marked market-state contract (Blueprint v5.0)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from types import MappingProxyType
from typing import Mapping, Any


@dataclass(frozen=True, slots=True)
class StateQuality:
    valid: bool
    stale: bool
    missing_blocks: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketState:
    exchange: str
    symbol: str
    interval: str
    event_time: datetime
    ingest_time: datetime
    price_volume: Mapping[str, Any]
    regime: Mapping[str, Any]
    options_flow: Mapping[str, Any]
    context: Mapping[str, Any]
    provenance: Mapping[str, Any]
    quality: StateQuality


def _aware_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _freeze_block(block: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if block is None:
        return MappingProxyType({})
    if not isinstance(block, Mapping):
        raise TypeError("market-state blocks must be mappings")
    # A shallow immutable copy prevents caller mutation after construction.
    return MappingProxyType(dict(block))


class MarketStateBuilder:
    """Build a single state snapshot without imputing absent evidence."""

    REQUIRED_BLOCKS = ("price_volume", "regime", "options_flow", "context", "provenance")

    def __init__(self, *, max_age_seconds: int = 120) -> None:
        if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds < 1:
            raise ValueError("max_age_seconds must be a positive whole number")
        self.max_age_seconds = max_age_seconds

    def build(
        self, *, exchange: str, symbol: str, interval: str,
        event_time: datetime, ingest_time: datetime,
        price_volume: Mapping[str, Any] | None = None,
        regime: Mapping[str, Any] | None = None,
        options_flow: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> MarketState:
        for name, value in (("exchange", exchange), ("symbol", symbol), ("interval", interval)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        event = _aware_utc(event_time, "event_time")
        ingested = _aware_utc(ingest_time, "ingest_time")
        if event > ingested:
            raise ValueError("event_time cannot be after ingest_time")
        blocks = {
            "price_volume": _freeze_block(price_volume),
            "regime": _freeze_block(regime),
            "options_flow": _freeze_block(options_flow),
            "context": _freeze_block(context),
            "provenance": _freeze_block(provenance),
        }
        missing = tuple(name for name, block in blocks.items() if not block)
        age = (ingested - event).total_seconds()
        stale = age > self.max_age_seconds
        warnings: list[str] = []
        if missing:
            warnings.append("Missing evidence blocks are not imputed.")
        if stale:
            warnings.append(f"Snapshot age {age:.3f}s exceeds {self.max_age_seconds}s limit.")
        if not blocks["provenance"].get("source_id"):
            warnings.append("Provenance source_id is missing.")
        if not blocks["price_volume"]:
            pass
        else:
            for key in ("open", "high", "low", "close"):
                value = blocks["price_volume"].get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                    warnings.append(f"price_volume.{key} must be finite and positive.")
            volume = blocks["price_volume"].get("volume")
            if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not isfinite(volume) or volume < 0:
                warnings.append("price_volume.volume must be finite and non-negative.")
        valid = not missing and not stale and not warnings
        quality = StateQuality(valid, stale, missing, tuple(warnings))
        return MarketState(
            exchange.strip().upper(), symbol.strip().upper(), interval.strip(), event, ingested,
            blocks["price_volume"], blocks["regime"], blocks["options_flow"],
            blocks["context"], blocks["provenance"], quality,
        )

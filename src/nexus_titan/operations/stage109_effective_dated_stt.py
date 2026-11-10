"""Stage109: purely hypothetical F&O statutory STT component, versioned by date.

Official reference: NSE/FATAX/73524, 31-Mar-2026, effective 01-Apr-2026.
Only 2024-10-01 onwards is supported; this is NOT a full brokerage charges
calculator. Paise round *up* per trade as a conservative simulation assumption,
NOT a representation of an exchange or broker's final STT rounding/aggregation.
No market data, real fills, authorizations, API tokens, or external systems.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json


class Stage109Blocked(ValueError):
    pass


SOURCE = "https://nsearchives.nseindia.com/content/circulars/FATAX73524.pdf"
CUTOFF = date(2026, 4, 1)
START = date(2024, 10, 1)
_MAX = 10**12


@dataclass(frozen=True, slots=True)
class Stage109SyntheticTrade:
    trading_date: str
    instrument: str  # OPTION_PREMIUM, OPTION_EXERCISE, FUTURE
    side: str  # BUY/SELL for trade, EXERCISE for holder exercise
    quantity: int  # units; 0 allowed for a synthetic zero-fill
    turnover_paise: int  # premium / futures trade value, not margin or notional
    intrinsic_value_paise: int = 0  # total exercise intrinsic value, 0 otherwise
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"


@dataclass(frozen=True, slots=True)
class Stage109OtherCharges:
    """Unverified caller-provided scenario fees, never an official rate schedule."""
    brokerage_paise: int = 0
    exchange_paise: int = 0
    sebi_paise: int = 0
    stamp_paise: int = 0
    gst_paise: int = 0
    source: str = "HYPOTHETICAL_FEES_NOT_VERIFIED"


@dataclass(frozen=True, slots=True)
class Stage109CostPreview:
    trading_date: str
    instrument: str
    side: str
    quantity: int
    turnover_paise: int
    intrinsic_value_paise: int
    taxable_value_paise: int
    stt_rate_ppm: int
    modeled_stt_paise: int
    other_modeled_charges_paise: int
    modeled_total_charges_paise: int
    rate_source: str
    source_sha256: str
    actual_broker_charges_verified: bool = False
    exchange_rounding_verified: bool = False
    trade_authorized: bool = False
    live_trading_enabled: bool = False
    verdict: str = "DATED_STT_ESTIMATE_ONLY_NO_GO"


def _bounded(n: int) -> bool:
    return type(n) is int and 0 <= n <= _MAX


def review_stage109_cost(trade: Stage109SyntheticTrade,
                         other: Stage109OtherCharges = Stage109OtherCharges()) -> Stage109CostPreview:
    if type(trade) is not Stage109SyntheticTrade or type(other) is not Stage109OtherCharges:
        raise Stage109Blocked("Exact bounded synthetic inputs required")
    try:
        dt = date.fromisoformat(trade.trading_date)
    except (ValueError, TypeError, AttributeError) as exc:
        raise Stage109Blocked("Malformed trading date") from exc
    if (type(trade.trading_date) is not str or trade.trading_date != dt.isoformat()
        or not START <= dt <= date(2100, 1, 1)
        or trade.source != "LOCAL_SYNTHETIC_TEST_ONLY"
        or other.source != "HYPOTHETICAL_FEES_NOT_VERIFIED"
        or trade.instrument not in ("OPTION_PREMIUM", "OPTION_EXERCISE", "FUTURE")
        or not _bounded(trade.quantity) or trade.quantity > 100_000
        or not _bounded(trade.turnover_paise)
        or not _bounded(trade.intrinsic_value_paise)
        or any(not _bounded(x) or x > 100_000_000 for x in (
            other.brokerage_paise, other.exchange_paise, other.sebi_paise,
            other.stamp_paise, other.gst_paise))):
        raise Stage109Blocked("Malformed date, amount or unverified source")
    if trade.instrument == "OPTION_EXERCISE":
        if trade.side != "EXERCISE" or trade.turnover_paise != 0:
            raise Stage109Blocked("Exercise must use intrinsic value, not option premium")
        if (trade.quantity == 0) != (trade.intrinsic_value_paise == 0):
            raise Stage109Blocked("Exercise intrinsic and quantity inconsistent")
        base = trade.intrinsic_value_paise
    else:
        if trade.side not in ("BUY", "SELL") or trade.intrinsic_value_paise != 0:
            raise Stage109Blocked("Purchase/sale cannot use exercise intrinsic value")
        if (trade.quantity == 0) != (trade.turnover_paise == 0):
            raise Stage109Blocked("Trade turnover and quantity inconsistent")
        base = trade.turnover_paise if trade.side == "SELL" else 0
    if dt >= CUTOFF:
        rates = {"OPTION_PREMIUM": 1500, "OPTION_EXERCISE": 1500, "FUTURE": 500}
    else:
        rates = {"OPTION_PREMIUM": 1000, "OPTION_EXERCISE": 1250, "FUTURE": 200}
    rate = rates[trade.instrument] if base else 0
    stt = (base * rate + 999_999) // 1_000_000
    extra = sum((other.brokerage_paise, other.exchange_paise, other.sebi_paise,
                 other.stamp_paise, other.gst_paise))
    if trade.quantity == 0 and extra:
        raise Stage109Blocked("Zero fill cannot incur per-execution charges in this model")
    total = stt + extra
    if total > _MAX:
        raise Stage109Blocked("Modeled charges outside safe bound")
    payload = ["STAGE109_DATED_STT_V1", trade.trading_date, trade.instrument, trade.side,
               trade.quantity, trade.turnover_paise, trade.intrinsic_value_paise,
               rate, stt, other.brokerage_paise, other.exchange_paise,
               other.sebi_paise, other.stamp_paise, other.gst_paise]
    digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return Stage109CostPreview(trade.trading_date, trade.instrument, trade.side,
        trade.quantity, trade.turnover_paise, trade.intrinsic_value_paise,
        base, rate, stt, extra, total, SOURCE, digest)

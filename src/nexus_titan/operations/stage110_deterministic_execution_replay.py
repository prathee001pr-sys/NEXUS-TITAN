"""Stage110: deterministic *synthetic L1* replay inspired by Nautilus/LEAN.

Conservative book availability, event-time ordering, lot alignment, stale quote
blocking and cancellation. No broker adapter, no exchange order, no L2 claim.
A synthetic fill is NEVER an actual trade or evidence of executable liquidity.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from .stage105_execution_stress_review import Stage105ExecutionPreview


class Stage110Blocked(ValueError):
    pass


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_MAX = 10**12
_IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True, slots=True)
class Stage110ReplayIntent:
    request_id: str
    contract_id: str
    side: str
    quantity: int
    lot_size: int
    submitted_at_ms: int
    price_protection_paise: int  # max for buy; min for sell
    max_quote_age_ms: int = 30_000
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage110BookUpdate:
    event_id: str
    at_ms: int
    bid_paise: int
    ask_paise: int
    bid_quantity: int
    ask_quantity: int
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"


@dataclass(frozen=True, slots=True)
class Stage110OrderEvent:
    event_id: str
    at_ms: int
    action: str  # FILL or CANCEL
    quantity: int = 0
    price_paise: int = 0
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"


@dataclass(frozen=True, slots=True)
class Stage110ExecutionReplay:
    request_id: str
    contract_id: str
    side: str
    requested_quantity: int
    filled_quantity: int
    unfilled_quantity: int
    modeled_turnover_paise: int
    fill_count: int
    canceled: bool
    stage105_scenario_sha256: str
    replay_sha256: str
    evidence_tier: str = "SYNTHETIC_L1"
    real_order_book_verified: bool = False
    real_exchange_fill_verified: bool = False
    independent_risk_veto_verified: bool = False
    trade_authorized: bool = False
    live_trading_enabled: bool = False
    verdict: str = "SYNTHETIC_EVENT_REPLAY_ONLY_NO_GO"


def _n(v: object, low: int = 0, high: int = _MAX) -> bool:
    return type(v) is int and low <= v <= high


def _at_ms(raw: str) -> int:
    try:
        parsed = datetime.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise Stage110Blocked("Bad source clock") from exc
    if (parsed.utcoffset() != timedelta(hours=5, minutes=30)
        or parsed.isoformat() != raw or parsed.second != 0 or parsed.microsecond != 0):
        raise Stage110Blocked("Source time must be exact IST minute")
    return int(parsed.timestamp() * 1000)


def review_stage110_execution(
    preview: Stage105ExecutionPreview,
    intent: Stage110ReplayIntent,
    events: tuple[Stage110BookUpdate | Stage110OrderEvent, ...] |
            list[Stage110BookUpdate | Stage110OrderEvent],
) -> Stage110ExecutionReplay:
    if (type(preview) is not Stage105ExecutionPreview or type(intent) is not Stage110ReplayIntent
        or type(events) not in (list, tuple) or not 1 <= len(events) <= 100):
        raise Stage110Blocked("Bounded exact typed synthetic inputs required")
    if (type(intent.request_id) is not str or not _ID.fullmatch(intent.request_id)
        or type(intent.contract_id) is not str or not _ID.fullmatch(intent.contract_id)
        or preview.request_id != intent.request_id or preview.contract_id != intent.contract_id
        or intent.side not in ("BUY", "SELL") or intent.side != preview.side
        or intent.source != "LOCAL_SYNTHETIC_TEST_ONLY"
        or intent.live_trading_enabled is not False
        or not _n(intent.quantity, 1, 100_000) or intent.quantity != preview.requested_quantity
        or not _n(intent.lot_size, 1, 100_000) or intent.quantity % intent.lot_size
        or not _n(intent.submitted_at_ms, 1, 10**15)
        or not _n(intent.max_quote_age_ms, 1, 60_000)
        or not _n(intent.price_protection_paise, 1)
        or preview.currency != "INR" or preview.underlying not in ("NIFTY", "BANKNIFTY")
        or not _n(preview.filled_quantity, 0, intent.quantity)
        or preview.filled_quantity % intent.lot_size
        or preview.unfilled_quantity != intent.quantity - preview.filled_quantity
        or preview.statutory_charges_verified is not False
        or preview.execution_liquidity_verified is not False
        or preview.actual_fill_verified is not False
        or preview.trade_authorized is not False or preview.live_trading_enabled is not False
        or preview.verdict != "SIMULATED_PARTIAL_FILL_COSTS_ONLY_NO_GO"
        or type(preview.scenario_sha256) is not str
        or not re.fullmatch(r"[0-9a-f]{64}", preview.scenario_sha256)):
        raise Stage110Blocked("Stage105 lineage or no-live constraints failed")
    start = _at_ms(preview.source_first_asof_ist)
    end = _at_ms(preview.source_last_asof_ist) + 59_999
    if not start <= intent.submitted_at_ms <= end:
        raise Stage110Blocked("Submit time outside source session")
    ids: set[str] = set()
    clock = intent.submitted_at_ms
    latest_quote_ms: int | None = None
    bid = ask = bid_left = ask_left = 0
    filled = turnover = fills = 0
    canceled = False
    serial: list[list] = []
    for e in events:
        if type(e) not in (Stage110BookUpdate, Stage110OrderEvent):
            raise Stage110Blocked("Unknown event type")
        if (type(e.event_id) is not str or not _ID.fullmatch(e.event_id)
            or e.event_id in ids or not _n(e.at_ms, clock, end)
            or e.source != "LOCAL_SYNTHETIC_TEST_ONLY"):
            raise Stage110Blocked("Duplicate event, stale ordering, unsupported source")
        ids.add(e.event_id)
        clock = e.at_ms
        if type(e) is Stage110BookUpdate:
            if (not _n(e.bid_paise, 1) or not _n(e.ask_paise, e.bid_paise)
                or not _n(e.bid_quantity, 0, 1_000_000)
                or not _n(e.ask_quantity, 0, 1_000_000)):
                raise Stage110Blocked("Crossed, zero or unbounded synthetic L1 quote")
            latest_quote_ms = e.at_ms
            bid, ask, bid_left, ask_left = (
                e.bid_paise, e.ask_paise, e.bid_quantity, e.ask_quantity)
            serial.append(["BOOK", e.event_id, e.at_ms, bid, ask, bid_left, ask_left])
        elif e.action == "CANCEL":
            if canceled or e.quantity != 0 or e.price_paise != 0:
                raise Stage110Blocked("Invalid cancel")
            canceled = True
            serial.append(["CANCEL", e.event_id, e.at_ms])
        elif e.action == "FILL":
            if (canceled or latest_quote_ms is None
                or e.at_ms - latest_quote_ms > intent.max_quote_age_ms
                or not _n(e.quantity, 1, 100_000) or e.quantity % intent.lot_size
                or not _n(e.price_paise, 1)
                or filled + e.quantity > min(intent.quantity, preview.filled_quantity)):
                raise Stage110Blocked("Fill without permitted, fresh lot-aligned synthetic liquidity")
            if preview.hypothetical_price_paise is None or not _n(preview.hypothetical_price_paise, 1):
                raise Stage110Blocked("Reference scenario contains no positive synthetic price")
            if intent.side == "BUY":
                if (e.quantity > ask_left or not max(ask, preview.hypothetical_price_paise) <= e.price_paise <= intent.price_protection_paise):
                    raise Stage110Blocked("BUY fill violates price protection or displayed synthetic ask")
                ask_left -= e.quantity
            else:
                if (e.quantity > bid_left or not intent.price_protection_paise <= e.price_paise <= min(bid, preview.hypothetical_price_paise)):
                    raise Stage110Blocked("SELL fill violates price protection or displayed synthetic bid")
                bid_left -= e.quantity
            filled += e.quantity
            turnover += e.price_paise * e.quantity
            if turnover > _MAX:
                raise Stage110Blocked("Unbounded modeled turnover")
            fills += 1
            serial.append(["FILL", e.event_id, e.at_ms, e.quantity, e.price_paise])
        else:
            raise Stage110Blocked("Unsupported replay action")
    if latest_quote_ms is None:
        raise Stage110Blocked("At least one synthetic book update required")
    payload = ["STAGE110_SYNTHETIC_L1_REPLAY_V1", preview.scenario_sha256,
               intent.request_id, intent.contract_id, intent.side, intent.quantity,
               intent.lot_size, intent.submitted_at_ms, intent.price_protection_paise,
               intent.max_quote_age_ms, serial]
    digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return Stage110ExecutionReplay(intent.request_id, intent.contract_id, intent.side,
        intent.quantity, filled, intent.quantity-filled, turnover, fills,
        canceled, preview.scenario_sha256, digest)

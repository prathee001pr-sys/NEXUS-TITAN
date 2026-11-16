"""Research-only Crypto bridge; it never signs permits or submits orders.

This is a deliberately bounded *proposal* for issue #134. External callers
must still obtain an independently authenticated, exact-intent risk permit and
pass through the authoritative Stage97 CryptoPaperBook to execute paper trades.
The return value is never an execution authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


class CryptoResearchPreflightBlocked(ValueError):
    """Fail-closed refusal of an untrusted synthetic Crypto research candidate."""


@dataclass(frozen=True, slots=True)
class CryptoResearchPreflightReceipt:
    status: str
    market: str
    symbol: str
    action: str
    account_id: str
    journal_revision: int
    journal_tip: str
    observed_epoch: int
    synthetic_input_only: bool = True
    risk_permit_issued: bool = False
    paper_order_submitted: bool = False
    exchange_order_submitted: bool = False
    live_trading_enabled: bool = False
    authorized_for_paper_execution: bool = False
    production_ready: bool = False


def _integer(value: Any, *, minimum: int = 0, maximum: int = 10**15) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CryptoResearchPreflightBlocked("Invalid bounded integer")
    return value


def preflight_crypto_research(
    *,
    pipeline: Any,
    state: Any,
    proposals: Iterable[Any],
    risk_request: Any,
    intent: Any,
    book: Any,
    now_epoch: int,
) -> CryptoResearchPreflightReceipt:
    """Evaluate a synthetic candidate and read the crypto journal without mutation.

    Never infers a risk permit from consensus, risk-approved booleans or a
    locally reported green status. Does not call book.apply(), seal permits,
    enable an account, create/reuse account signing keys or place orders.
    The actual research pipeline and book remain separately authoritative.
    """
    now = _integer(now_epoch)
    if not hasattr(state, "quality") or type(state.quality.valid) is not bool or not state.quality.valid:
        raise CryptoResearchPreflightBlocked("Market state invalid")
    if getattr(state.quality, "stale", True) is not False:
        raise CryptoResearchPreflightBlocked("Stale market state")
    if getattr(state, "symbol", None) != "BTC-USDT" or getattr(state, "exchange", None) != "CRYPTO_SYNTHETIC":
        raise CryptoResearchPreflightBlocked("Unsupported synthetic crypto market")
    if not isinstance(getattr(state, "provenance", None), dict) and not hasattr(getattr(state, "provenance", None), "get"):
        raise CryptoResearchPreflightBlocked("Missing synthetic source context")
    if state.provenance.get("source_id") != "LOCAL_SYNTHETIC_TEST_ONLY":
        raise CryptoResearchPreflightBlocked("Unverified source cannot enter this synthetic contract")
    if getattr(intent, "source", None) != "LOCAL_SYNTHETIC_TEST_ONLY" or getattr(intent, "symbol", None) != "BTC-USDT":
        raise CryptoResearchPreflightBlocked("Intent does not match research source")
    action = getattr(intent, "side", None)
    if action not in ("BUY", "SELL"):
        raise CryptoResearchPreflightBlocked("Unsupported crypto action")
    observed = _integer(getattr(intent, "observed_epoch", None))
    if observed > now:
        raise CryptoResearchPreflightBlocked("Future quote")
    event_time = getattr(state, "event_time", None)
    ingest_time = getattr(state, "ingest_time", None)
    if (not isinstance(event_time, datetime) or event_time.tzinfo is None
            or event_time.utcoffset() is None or not isinstance(ingest_time, datetime)
            or ingest_time.tzinfo is None or ingest_time.utcoffset() is None):
        raise CryptoResearchPreflightBlocked("Timezone-aware event/ingest evidence required")
    event_ts, ingest_ts = event_time.timestamp(), ingest_time.timestamp()
    if event_ts < 0 or ingest_ts < event_ts or ingest_ts > now:
        raise CryptoResearchPreflightBlocked("Invalid chronological event/ingest context")
    if abs(event_ts - observed) > 1:
        raise CryptoResearchPreflightBlocked("Intent and market-state timestamps diverge")
    if getattr(risk_request, "symbol", None) != "BTC-USDT" or getattr(risk_request, "side", None) != action:
        raise CryptoResearchPreflightBlocked("Independent risk request does not match intent")
    limits = getattr(book, "limits", None)
    if limits is None or getattr(limits, "paper_enabled", None) is not True:
        raise CryptoResearchPreflightBlocked("Paper account disabled")
    max_age = _integer(getattr(limits, "max_quote_age_seconds", None), minimum=1, maximum=300)
    if now - observed > max_age:
        raise CryptoResearchPreflightBlocked("Stale synthetic quote")
    if getattr(limits, "mode", None) not in ("SAFE", "RISKY"):
        raise CryptoResearchPreflightBlocked("Invalid account mode")
    if type(getattr(limits, "autonomy_enabled", False)) is not bool:
        raise CryptoResearchPreflightBlocked("Invalid autonomy policy")
    quantity = _integer(getattr(intent, "quantity_microcoin", None), minimum=1)
    price = _integer(getattr(intent, "price_cents_per_coin", None), minimum=1)
    notional = (quantity * price + 999_999) // 1_000_000 if action == "BUY" else (quantity * price) // 1_000_000
    if notional < 100 or notional > getattr(limits, "max_order_cents", -1):
        raise CryptoResearchPreflightBlocked("Synthetic notional outside policy")
    if not callable(getattr(pipeline, "evaluate", None)):
        raise CryptoResearchPreflightBlocked("Research pipeline unavailable")
    # Materialize once; conflicting/untrusted proposal data must not be replayed.
    proposals = tuple(proposals)
    if not proposals or len(proposals) > 32:
        raise CryptoResearchPreflightBlocked("Missing or excessive proposals")
    result = pipeline.evaluate(state, proposals, risk_request)
    if (getattr(result, "status", None) != "SHADOW CANDIDATE"
            or getattr(result, "risk_approved", None) is not True
            or getattr(result, "order_submitted", None) is not False
            or getattr(getattr(result, "consensus", None), "action", None) != action):
        raise CryptoResearchPreflightBlocked("Consensus / risk failed closed")
    # Risk quantity uses instrument lots; NEVER convert it into microcoins.
    _integer(getattr(result, "risk_quantity", None), minimum=1)
    if not callable(getattr(book, "snapshot", None)):
        raise CryptoResearchPreflightBlocked("Crypto journal unavailable")
    account = book.snapshot()  # replay verified by Stage97; NO mutation.
    if (getattr(account, "market", None) != "CRYPTO_PAPER"
            or getattr(account, "currency", None) != "USDT"
            or getattr(account, "account_id", None) != getattr(book, "account_id", None)
            or getattr(account, "live_trading_enabled", None) is not False
            or getattr(account, "exchange_orders_transmitted", None) != 0
            or getattr(account, "real_market_evidence_verified", None) is not False):
        raise CryptoResearchPreflightBlocked("Crypto journal authority boundary mismatch")
    if getattr(account, "kill_active", None) is True and action == "BUY":
        raise CryptoResearchPreflightBlocked("One-way kill prevents new entry")
    revision = _integer(getattr(account, "journal_revision", None))
    tip = getattr(account, "journal_tip", None)
    if not isinstance(tip, str) or len(tip) != 64 or any(c not in "0123456789abcdef" for c in tip):
        raise CryptoResearchPreflightBlocked("Missing replay-checked account journal tip")
    cash = _integer(getattr(account, "cash_cents", None))
    basis = _integer(getattr(account, "remaining_cost_basis_cents", None))
    initial = _integer(getattr(account, "initial_cents", None))
    realized = getattr(account, "realized_net_pnl_cents", None)
    if type(realized) is not int or abs(realized) > 10**15:
        raise CryptoResearchPreflightBlocked("Malformed realized P&L")
    position = _integer(getattr(account, "position_microcoin", None))
    if cash + basis != initial + realized:
        raise CryptoResearchPreflightBlocked("Account conservation failure")
    if action == "SELL" and quantity > position:
        raise CryptoResearchPreflightBlocked("Sell exceeds synthetic position")
    return CryptoResearchPreflightReceipt(
        "RESEARCH_ONLY_PRECHECK_NO_EXECUTION", "CRYPTO_PAPER", "BTC-USDT", action,
        account.account_id, revision, tip, observed,
    )

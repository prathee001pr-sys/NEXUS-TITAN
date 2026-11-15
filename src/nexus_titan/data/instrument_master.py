"""Point-in-time Exchange Instrument Master, lot-size revisions, and contract rollover (Workstreams E & M)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
import math
from typing import Literal

from nexus_titan.data.sessions import MarketCalendar, TradingSession, nse_equity_derivatives_baseline
from nexus_titan.risk.portfolio_risk import InstrumentSpec

SegmentType = Literal["EQUITY", "FUTURES", "OPTIONS", "INDEX"]


@dataclass(frozen=True)
class PointInTimeContractSpec:
    """Versioned exchange contract metadata valid within [effective_from, effective_to] (Workstream E)."""

    symbol: str
    underlying: str
    exchange: str
    segment: SegmentType
    lot_size: int
    tick_size: float
    freeze_quantity: int
    effective_from: date
    effective_to: date
    expiry_date: date | None = None
    strike_step: float = 50.0
    max_lots_per_trade: int = 10
    source_reference: str | None = None
    source_verified: bool = False

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.underlying.strip() or not self.exchange.strip():
            raise ValueError("symbol, underlying, and exchange must be non-empty.")
        if (isinstance(self.lot_size, bool) or not isinstance(self.lot_size, int) or self.lot_size < 1
                or isinstance(self.freeze_quantity, bool) or not isinstance(self.freeze_quantity, int)
                or self.freeze_quantity < self.lot_size
                or isinstance(self.tick_size, bool) or not isinstance(self.tick_size, (int, float))
                or not math.isfinite(self.tick_size) or self.tick_size <= 0
                or isinstance(self.max_lots_per_trade, bool) or not isinstance(self.max_lots_per_trade, int)
                or self.max_lots_per_trade < 1):
            raise ValueError("Invalid lot_size, freeze_quantity, tick_size, or max_lots_per_trade.")
        if self.segment not in ("EQUITY", "FUTURES", "OPTIONS", "INDEX"):
            raise ValueError("Unsupported contract segment.")
        if self.effective_from > self.effective_to:
            raise ValueError("effective_from cannot be after effective_to.")
        if not isinstance(self.source_verified, bool):
            raise ValueError("source_verified must be boolean.")
        if self.source_verified and (not isinstance(self.source_reference, str) or not self.source_reference.strip()):
            raise ValueError("A verified contract spec requires a non-empty source_reference.")

    def to_instrument_spec(self) -> InstrumentSpec:
        return InstrumentSpec(
            symbol=self.symbol,
            lot_size=self.lot_size,
            tick_size=self.tick_size,
            max_lots_per_trade=self.max_lots_per_trade,
            freeze_quantity=self.freeze_quantity,
        )


# Static research references only. They are NOT verified against bundled official
# NSE circulars/contract-master snapshots. Production sizing must inject verified
# point-in-time records and call resolve_verified_lot_size().
DEFAULT_POINT_IN_TIME_SPECS: tuple[PointInTimeContractSpec, ...] = (
    PointInTimeContractSpec(
        symbol="NIFTY", underlying="NIFTY", exchange="NSE", segment="FUTURES",
        lot_size=50, tick_size=0.05, freeze_quantity=1800,
        effective_from=date(2021, 7, 1), effective_to=date(2024, 4, 25), strike_step=50.0,
    ),
    PointInTimeContractSpec(
        symbol="NIFTY", underlying="NIFTY", exchange="NSE", segment="FUTURES",
        lot_size=25, tick_size=0.05, freeze_quantity=1800,
        effective_from=date(2024, 4, 26), effective_to=date(2027, 12, 31), strike_step=50.0,
    ),
    PointInTimeContractSpec(
        symbol="BANKNIFTY", underlying="BANKNIFTY", exchange="NSE", segment="FUTURES",
        lot_size=25, tick_size=0.05, freeze_quantity=900,
        effective_from=date(2020, 1, 1), effective_to=date(2023, 6, 30), strike_step=100.0,
    ),
    PointInTimeContractSpec(
        symbol="BANKNIFTY", underlying="BANKNIFTY", exchange="NSE", segment="FUTURES",
        lot_size=15, tick_size=0.05, freeze_quantity=900,
        effective_from=date(2023, 7, 1), effective_to=date(2027, 12, 31), strike_step=100.0,
    ),
    PointInTimeContractSpec(
        symbol="FINNIFTY", underlying="FINNIFTY", exchange="NSE", segment="FUTURES",
        lot_size=40, tick_size=0.05, freeze_quantity=1800,
        effective_from=date(2021, 1, 1), effective_to=date(2024, 7, 31), strike_step=50.0,
    ),
    PointInTimeContractSpec(
        symbol="FINNIFTY", underlying="FINNIFTY", exchange="NSE", segment="FUTURES",
        lot_size=25, tick_size=0.05, freeze_quantity=1800,
        effective_from=date(2024, 8, 1), effective_to=date(2027, 12, 31), strike_step=50.0,
    ),
)


class PointInTimeInstrumentMaster:
    """Resolve contract specifications as of a specific historical or current date (Workstream E)."""

    def __init__(self, specs: tuple[PointInTimeContractSpec, ...] = DEFAULT_POINT_IN_TIME_SPECS) -> None:
        self._specs: list[PointInTimeContractSpec] = list(specs)

    def register(self, spec: PointInTimeContractSpec) -> None:
        for existing in self._specs:
            if (
                existing.symbol == spec.symbol
                and existing.segment == spec.segment
                and not (spec.effective_to < existing.effective_from or spec.effective_from > existing.effective_to)
            ):
                raise ValueError(
                    f"Overlapping point-in-time contract window for {spec.symbol} ({spec.segment}): "
                    f"{spec.effective_from}..{spec.effective_to}"
                )
        self._specs.append(spec)

    def resolve(
        self, symbol: str, as_of: date | str, segment: SegmentType | None = None
    ) -> PointInTimeContractSpec:
        target_date = date.fromisoformat(as_of[:10]) if isinstance(as_of, str) else as_of
        sym_clean = symbol.strip().upper()
        for spec in self._specs:
            if spec.symbol == sym_clean and (segment is None or spec.segment == segment):
                if spec.effective_from <= target_date <= spec.effective_to:
                    return spec
        raise KeyError(f"No point-in-time contract spec found for {sym_clean} on {target_date.isoformat()}.")

    def resolve_lot_size(self, symbol: str, as_of: date | str, segment: SegmentType | None = None) -> int:
        """Return a lot size from the research/reference catalogue.

        The bundled static catalogue is explicitly unverified reference data.
        It may support tests and research reports only. Production/virtual order
        sizing must use :meth:`resolve_verified_lot_size`. Unknown contracts
        raise instead of silently defaulting to one.
        """
        return self.resolve(symbol, as_of, segment=segment).lot_size

    def resolve_verified_lot_size(
        self, symbol: str, as_of: date | str, segment: SegmentType | None = None
    ) -> int:
        """Resolve a contract size only when its record carries source evidence.

        A non-empty reference is necessary but not sufficient: deployment
        operators must validate it against the official point-in-time exchange
        contract master and retain that source alongside the deployment.
        """
        spec = self.resolve(symbol, as_of, segment=segment)
        if not spec.source_verified or not spec.source_reference:
            raise PermissionError(
                f"Contract metadata for {spec.symbol} is unverified; official source evidence is required."
            )
        return spec.lot_size

    @staticmethod
    def should_roll_futures_contract(current_date: date | str, expiry_date: date | str, roll_days_before: int = 2) -> bool:
        """Return True when a near-month contract should roll to next-month prior to expiry."""
        curr = date.fromisoformat(current_date[:10]) if isinstance(current_date, str) else current_date
        exp = date.fromisoformat(expiry_date[:10]) if isinstance(expiry_date, str) else expiry_date
        if curr > exp:
            raise ValueError("current_date is past contract expiry_date.")
        return (exp - curr).days <= max(0, roll_days_before)


def build_nse_market_calendar(
    holidays: frozenset[date] | set[date] | None = None,
    muhurat_sessions: dict[date, tuple[TradingSession, ...]] | None = None,
) -> MarketCalendar:
    """Build an NSE regular session calendar (09:15 to 15:30 IST, Mon-Fri) with holidays and special sessions."""
    default_holidays = frozenset(holidays) if holidays is not None else frozenset({
        date(2026, 1, 26),  # Republic Day
        date(2026, 8, 15),  # Independence Day
        date(2026, 10, 2),  # Gandhi Jayanti
    })
    special = muhurat_sessions or {
        date(2026, 11, 8): (TradingSession(time(18, 0), time(19, 0)),),
    }
    return nse_equity_derivatives_baseline(holidays=default_holidays, special_sessions=special)

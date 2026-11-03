"""Stage43 — explicit fail-closed *paper-only* deployment entrypoint.

This module connects the existing Stage28, 37–42 components in ONE
supported *local* startup path. It does not disable or secure legacy Python
APIs elsewhere, authenticate a real operator, unify capital ledgers, inspect
market-source licences, or authorize a broker/live order.

A protected production system requires an independently enforced service,
credential isolation, signed identity evidence and external risk controls.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import math
import sqlite3

from nexus_titan.shadow.paper_intent_gateway import (
    PaperIntentDenied, PaperIntentGateway, PaperIntentResult,
)
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import TradingMode, VirtualAccount


class PaperDeploymentBlocked(PermissionError):
    """The local paper-only profile or requested admission is not safe."""


@dataclass(frozen=True, slots=True)
class PaperDeploymentConfig:
    account_id: str
    starting_capital: float
    virtual_state_dir: Path
    research_db_path: Path
    # Orders require a second explicit opt-in when opening every session.
    paper_orders_enabled: bool = False
    deployment_profile: str = "RESEARCH_PAPER_ONLY"


@dataclass(frozen=True, slots=True)
class PaperDeploymentStatus:
    account_id: str
    blockers: tuple[str, ...]
    research_profile: str
    read_only: bool
    paper_intents_enabled: bool
    strict_paper_mode: bool
    gateway_only_mode: bool
    virtual_reconciled: bool
    research_ledger_verified: bool
    live_orders_transmitted: int = 0
    live_trading_enabled: bool = False
    externally_authenticated_identity: bool = False
    cross_ledger_atomicity_verified: bool = False
    global_legacy_apis_disabled: bool = False
    approved_for_strategy_promotion: bool = False
    production_ready: bool = False


def _validate_config(config: PaperDeploymentConfig, callback: object) -> tuple[Path, Path]:
    if not isinstance(config, PaperDeploymentConfig):
        raise PaperDeploymentBlocked("Explicit PaperDeploymentConfig required")
    if config.deployment_profile != "RESEARCH_PAPER_ONLY":
        raise PaperDeploymentBlocked("Only RESEARCH_PAPER_ONLY profile is supported")
    if not isinstance(config.paper_orders_enabled, bool):
        raise PaperDeploymentBlocked("paper_orders_enabled must be explicit boolean")
    if (not isinstance(config.account_id, str) or
            not config.account_id.strip() or "/" in config.account_id or
            "\\" in config.account_id or config.account_id in {".", ".."}):
        raise PaperDeploymentBlocked("Safe, nonempty account_id required")
    if (isinstance(config.starting_capital, bool)
            or not isinstance(config.starting_capital, (int, float))
            or not math.isfinite(config.starting_capital)
            or config.starting_capital <= 0):
        raise PaperDeploymentBlocked("Explicit positive finite paper capital required")
    # SQLite options ledger is cent-based. No implicit rounding/deposit.
    if round(config.starting_capital * 100) != config.starting_capital * 100:
        raise PaperDeploymentBlocked("Paper capital must have exact cent precision")
    if not isinstance(config.virtual_state_dir, Path) or not isinstance(config.research_db_path, Path):
        raise PaperDeploymentBlocked("Explicit pathlib.Path state and research paths required")
    if not callable(callback):
        raise PaperDeploymentBlocked("Configured manual approval callback required")
    state_dir = config.virtual_state_dir
    research_path = config.research_db_path
    durable_path = state_dir / f"{config.account_id}_durable.db"
    if (not str(state_dir).strip() or not str(research_path).strip()
            or research_path.name in {"", ".", ".."}
            or state_dir == research_path
            or durable_path.resolve() == research_path.resolve()):
        raise PaperDeploymentBlocked("Distinct durable virtual and research SQLite paths required")
    if (state_dir.is_symlink() or research_path.is_symlink() or
            durable_path.is_symlink()):
        raise PaperDeploymentBlocked("Symbolic-linked account state paths are not supported")
    return durable_path, research_path


def _check_existing_virtual(db: Path, account_id: str, capital: float) -> None:
    """Read existing account policy BEFORE constructing a mutable account."""
    if not db.exists():
        return
    if not db.is_file():
        raise PaperDeploymentBlocked("Durable account path is not a file")
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as con:
            row = con.execute(
                "SELECT strict_paper_mode, gateway_only_mode, initial_capital "
                "FROM account_state WHERE account_id=?", (account_id,),
            ).fetchone()
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise PaperDeploymentBlocked("Existing account policy cannot be verified") from exc
    if row is None or row[0] != 1 or row[1] != 1:
        raise PaperDeploymentBlocked(
            "Existing account lacks verified strict+gateway-only policy; "
            "do not silently migrate a legacy account"
        )
    if not isinstance(row[2], (int, float)) or abs(row[2] - capital) > 0.000001:
        raise PaperDeploymentBlocked("Existing virtual account initial capital mismatch")


class PaperOnlyDeployment:
    """No broker path; convenience facade for guarded, opt-in paper intents.

    The account objects remain accessible to application developers, so this
    is NOT an independent OS/process security or global legacy-API firewall.
    """

    def __init__(
        self, config: PaperDeploymentConfig,
        virtual_account: VirtualAccount,
        research_ledger: DurableResearchShadowLedger,
    ) -> None:
        self.config = config
        self.virtual_account = virtual_account
        self.research_ledger = research_ledger
        self.gateway = PaperIntentGateway(virtual_account, research_ledger)

    def status(self) -> PaperDeploymentStatus:
        v, r = self.virtual_account, self.research_ledger
        blockers: list[str] = []
        reconciled = False
        audited = False
        try:
            v._assert_strict_paper_policy()
            if (not v.strict_paper_mode or not v.gateway_only_mode
                    or not v.durable_store or v.trading_mode is not TradingMode.MANUAL_APPROVAL
                    or v.require_pretrade_risk_check is not True
                    or not callable(v.approval_authorizer)):
                blockers.append("Strict manual gateway-only paper policy unavailable")
            reconciled = v.reconcile().is_reconciled
            if not reconciled:
                blockers.append("Virtual account internal reconciliation failed")
        except Exception:
            blockers.append("Virtual account state is stale, corrupted or untrusted")
        try:
            audited = r.guarded_paper_mode and r.verify_integrity()
            st = r.status()
            if (not audited or st.account_id != v.account_id
                    or abs(st.starting_capital - v.initial_capital) > 0.000001):
                blockers.append("Guarded research ledger policy or account identity mismatch")
            if st.open_order_count or st.reserved_cash or st.option_inventory:
                blockers.append("Independent research ledger has outstanding reservations/inventory")
            if st.live_orders_transmitted or st.approved_for_strategy_promotion:
                blockers.append("Research ledger claims forbidden authority")
        except Exception:
            blockers.append("Research ledger audit/status unavailable")
        if v.kill_switched:
            blockers.append("Emergency kill switch active")
        if v.account_id != self.config.account_id:
            blockers.append("Configured account ID changed")
        if not self.config.paper_orders_enabled:
            blockers.append("Paper order submissions disabled by session config")
        return PaperDeploymentStatus(
            account_id=v.account_id,
            blockers=tuple(blockers),
            research_profile=self.config.deployment_profile,
            read_only=bool(blockers),
            paper_intents_enabled=not blockers,
            strict_paper_mode=v.strict_paper_mode,
            gateway_only_mode=v.gateway_only_mode,
            virtual_reconciled=reconciled,
            research_ledger_verified=audited,
        )

    def _require_enabled(self) -> None:
        result = self.status()
        if not result.paper_intents_enabled:
            raise PaperDeploymentBlocked(
                "Deployment paper admission blocked: " + "; ".join(result.blockers)
            )

    def request_buy(
        self, *, symbol: str, quantity: int, entry_price: float,
        stop_price: float, lot_size: int = 1,
        instrument_type: str = "EQUITY_DELIVERY",
    ) -> PaperIntentResult:
        self._require_enabled()
        return self.gateway.request_buy(
            symbol=symbol, quantity=quantity, entry_price=entry_price,
            stop_price=stop_price, lot_size=lot_size,
            instrument_type=instrument_type, paper_trading_enabled=True,
        )

    def request_sell_to_close(self, *, symbol: str, quantity: int) -> PaperIntentResult:
        self._require_enabled()
        return self.gateway.request_sell_to_close(
            symbol=symbol, quantity=quantity, paper_trading_enabled=True,
        )


def open_paper_only_deployment(
    config: PaperDeploymentConfig, *,
    approval_authorizer: Callable[[str, str], bool] | None,
) -> PaperOnlyDeployment:
    """Open explicit strict/gateway-only paper session, never auto-migrate legacy.

    First-time initialization is for a fresh isolated account only. Existing
    account and research DB must BOTH exist and already have their strict
    guarded policies; otherwise fail closed without resetting account cash.
    """
    db_path, research_path = _validate_config(config, approval_authorizer)
    if db_path.exists() != research_path.exists():
        raise PaperDeploymentBlocked(
            "Incomplete virtual/research deployment pair; manual recovery required"
        )
    existing = db_path.exists()
    if existing:
        _check_existing_virtual(db_path, config.account_id, config.starting_capital)
    virtual = VirtualAccount(
        config.account_id, starting_capital=config.starting_capital,
        state_dir=config.virtual_state_dir, trading_mode=TradingMode.MANUAL_APPROVAL,
        require_pretrade_risk_check=True,
        approval_authorizer=approval_authorizer,
        strict_paper_mode=not existing,
    )
    research = DurableResearchShadowLedger(
        research_path, account_id=config.account_id,
        starting_capital=config.starting_capital,
        guarded_paper_mode=True,
    )
    if not existing:
        virtual.enable_gateway_only_mode(research)
    # Restart is permitted with open virtual orders, positions or emergency
    # lock. Session status decides whether *new* paper intents are allowed.
    result = PaperOnlyDeployment(config, virtual, research)
    state = result.status()
    # Persisted policy defects (as opposed to a conservative read-only
    # session or an emergency lock) are fatal at bootstrap.
    if not state.strict_paper_mode or not state.gateway_only_mode or not state.research_ledger_verified:
        raise PaperDeploymentBlocked("Research-only deployment policy failed bootstrap")
    return result

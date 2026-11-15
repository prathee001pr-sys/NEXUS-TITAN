"""Stage50: offline, read-only TITAN paper-safety dashboard data contract.

An opt-in model derived from the same Stage49 cooperative fence and its Stage48
signed-paper session. It does NOT place/approve/fill orders, run strategies,
fetch market prices, invoke models, or create a broker connection.

Only local synthetic research evidence is available. All exchange identity,
global risk, human auth, cross-book atomicity, and release flags remain false.
Theme tokens describe the approved black/silver aesthetic; the cybernetic
face image is NOT stored or replaced here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nexus_titan.operations.durable_paper_fence import Stage49DurablePaperFence
from nexus_titan.operations.signed_paper_approval import Stage48SignedPaperSession
from nexus_titan.virtual.order_manager import VirtualAccount


class Stage50DashboardBlocked(ValueError):
    """The paper-dashboard context is missing or mismatched."""


# Locked presentation contract, not a rendered image or new design approval.
_LOCKED_THEME = {
    "theme_id": "NEXUS_TITAN_BLACK_SILVER_LOCKED",
    "surface": "#080B0F",
    "panel": "#151A20",
    "silver": "#B9C2CD",
    "text": "#EDF0F4",
    "cyan_activity": "#54C5D5",
    "positive_market": "#32AF79",
    "negative_market": "#D65464",
    "cybernetic_face_asset": "EXTERNAL_APPROVED_REFERENCE_REQUIRED",
    "live_market_map": "UNAVAILABLE_NO_REAL_FEED",
}


def unattached_stage50_dashboard() -> dict[str, Any]:
    """Explicit nonfunctional no-data state for legacy dashboards."""
    return {
        "schema_version": 1,
        "component": "TITAN_PAPER_SAFETY",
        "status": "NOT_ATTACHED",
        "data_source": "NONE",
        "theme": dict(_LOCKED_THEME),
        "paper_order_actions_enabled": False,
        "approval_actions_enabled": False,
        "live_trading_enabled": False,
        "broker_connected": False,
        "production_ready": False,
    }


class Stage50ReadOnlyPaperDashboard:
    """Construct local, synthetic only status on demand; no write methods."""

    def __init__(self, fence: Stage49DurablePaperFence):
        if not isinstance(fence, Stage49DurablePaperFence):
            raise Stage50DashboardBlocked("Explicit Stage49 cooperative fence required")
        session = fence._session
        if not isinstance(session, Stage48SignedPaperSession):
            raise Stage50DashboardBlocked("Stage48 signed-paper source required")
        deployment = session._deployment
        if fence._deployment is not deployment or (
            deployment.virtual_account.account_id != deployment.config.account_id
            or fence._account_id != deployment.config.account_id
        ):
            raise Stage50DashboardBlocked("Dashboard account/deployment binding mismatch")
        self._fence = fence

    @property
    def account(self) -> VirtualAccount:
        """Reference is only for source-identity validation by the host."""
        return self._fence._deployment.virtual_account

    def snapshot(self) -> dict[str, Any]:
        """Fresh, serializable read-only local display snapshot.

        Never report a green trade/readiness signal based solely on local
        synthetic checks. Callers can persist or render this JSON but cannot
        treat the output as an approval, risk authorization or real feed.
        """
        account = self.account
        fence = self._fence
        deployment = fence._deployment
        blockers: list[str] = []
        fence_status = None
        session_status = None
        deployment_status = None
        cash_virtual = None
        cash_research = None
        try:
            fence_status = fence.inspect()
            blockers.extend(fence_status.blockers)
            cash_virtual = fence_status.virtual_cash_cents
            cash_research = fence_status.research_cash_cents
        except Exception:
            blockers.append("Stage49 coordinator audit unavailable")

        try:
            session_status = fence._session.status()
            if not session_status.signed_approval_adapter_installed:
                blockers.append("Signed paper approval callback was replaced")
        except Exception:
            blockers.append("Stage48 approval configuration unavailable")

        try:
            deployment_status = deployment.status()
            blockers.extend(deployment_status.blockers)
        except Exception:
            blockers.append("Stage43 strict paper deployment audit unavailable")

        # Snapshot accounts and risks without trusting another caller's
        # reconstructed cash/P&L, prices, token material or identity claims.
        try:
            orders = tuple(account.orders.values())
            state_counts: dict[str, int] = {}
            for order in orders:
                label = order.state.value
                state_counts[label] = state_counts.get(label, 0) + 1
            pending_count = state_counts.get("PENDING_APPROVAL", 0)
            approved_count = state_counts.get("ACCEPTED", 0)
            filled_fragments = sum(len(order.fills) for order in orders)
            inventory_count = len(account.positions)
            killed = account.kill_switched
            strict = account.strict_paper_mode is True
            gateway = account.gateway_only_mode is True
            risk_enabled = account.require_pretrade_risk_check is True
            policy = account.risk_engine.config
            configured_risk = {
                "max_risk_per_trade_pct": policy.max_risk_per_trade_pct,
                "max_portfolio_exposure_pct": policy.max_portfolio_exposure_pct,
                "daily_loss_limit_pct": policy.daily_loss_limit_pct,
                "max_drawdown_limit_pct": policy.max_drawdown_limit_pct,
                "consecutive_loss_limit": policy.consecutive_loss_limit,
                "max_concurrent_positions": policy.max_concurrent_positions,
            }
            if killed:
                blockers.append("Emergency kill switch is active")
            if not (strict and gateway and risk_enabled):
                blockers.append("Paper policy is not strict and risk guarded")
            if not isinstance(account.cash_balance, (float, int)) or isinstance(account.cash_balance, bool):
                blockers.append("Virtual paper account cash type invalid")
        except Exception:
            blockers.append("Virtual paper order/risk snapshot unavailable")
            state_counts = {}
            pending_count = approved_count = filled_fragments = inventory_count = None
            killed = None
            strict = gateway = risk_enabled = False
            configured_risk = None

        checked = datetime.now(timezone.utc).isoformat()
        # "BLOCKED" is presentation status, not a claim that all direct
        # Python trading APIs were disabled by this code.
        data_ok = (
            fence_status is not None
            and fence_status.coordinator_bound
            and deployment_status is not None
            and deployment_status.virtual_reconciled
            and deployment_status.research_ledger_verified
            and session_status is not None
            and session_status.signed_approval_adapter_installed
        )
        if not data_ok:
            blockers.append("At least one local state source is unverified")

        problems = tuple(dict.fromkeys(blockers))
        return {
            "schema_version": 1,
            "component": "TITAN_PAPER_SAFETY",
            "status": "LOCAL_REVIEW_REQUIRED" if problems else "LOCAL_SYNTHETIC_REVIEW_ONLY",
            "checked_at_utc": checked,
            "data_source": "LOCAL_SYNTHETIC_PAPER_SQLITE_ONLY",
            "theme": dict(_LOCKED_THEME),
            "account": {
                "account_id": deployment.config.account_id,
                "initial_paper_capital_cents": fence._starting_cents,
                "virtual_cash_cents": cash_virtual,
                "research_cash_cents": cash_research,
                # No double count: these represent separate books.
                "combined_cash_cents": None,
                "cross_ledger_atomicity": False,
                "two_book_cash_match_observed": (
                    cash_virtual is not None and cash_virtual == cash_research
                    and cash_virtual == fence._starting_cents
                ),
            },
            "paper_session": {
                "paper_orders_enabled_in_config": deployment.config.paper_orders_enabled,
                "strict_manual_account": strict,
                "gateway_only": gateway,
                "pretrade_risk_enabled": risk_enabled,
                "kill_switch_active": killed,
                "local_startup_reconciled": bool(
                    deployment_status and deployment_status.virtual_reconciled
                ),
                "research_integrity_checked": bool(
                    deployment_status and deployment_status.research_ledger_verified
                ),
            },
            "admission_fence": {
                "coordinator_bound": bool(fence_status and fence_status.coordinator_bound),
                "attempt_count": fence_status.attempt_count if fence_status is not None else None,
                "latest_attempt_state": (
                    fence_status.latest_attempt_state if fence_status is not None else None
                ),
                "first_synthetic_buy_preflight_passed": bool(
                    fence_status and fence_status.can_request_first_synthetic_buy
                ),
                "direct_legacy_entrypoints_blocked": False,
            },
            "paper_orders": {
                "total": len(orders) if "orders" in locals() else None,
                "counts_by_state": state_counts,
                "pending_manual_approval": pending_count,
                "approved_unfilled": approved_count,
                "fill_fragments": filled_fragments,
                "open_position_symbols": inventory_count,
                "latest_order_ids": [],  # avoid leaking order handles in UI
            },
            "signed_approval": {
                "configured_local_verifier": bool(
                    session_status and session_status.signed_approval_adapter_installed
                ),
                "external_identity_authenticated": False,
                "external_signer_verified": False,
                "replay_tokens_or_signature_secrets_exposed": False,
                "approval_actions_enabled": False,
            },
            "risk_veto": {
                "configured_limits": configured_risk,
                "new_proposal_risk_evaluated": False,
                "latest_veto_result": "NOT_EVALUATED_NO_TRUSTED_QUOTE",
                "independently_enforced_global_risk": False,
            },
            "market": {
                "india_fo_live_data": False,
                "crypto_live_data": False,
                "latest_price": None,
                "provider_identity_verified": False,
                "historical_fo_provenance_verified": False,
                "news_map_feed_verified": False,
            },
            "evolve": {
                "production_strategy_promotion_enabled": False,
                "autonomous_real_orders_enabled": False,
                "stage50_evolve_runtime_connected": False,
            },
            "safety": {
                "paper_order_actions_enabled": False,
                "approval_actions_enabled": False,
                "broker_connected": False,
                "live_trading_enabled": False,
                "combined_capital_authority_verified": False,
                "global_legacy_entrypoints_fenced": False,
                "independent_human_identity_verified": False,
                "production_ready": False,
            },
            "blockers": list(problems),
            "notes": [
                "DISPLAY ONLY. Green local checks are not live or strategy approval.",
                "Virtual and research books must never be summed as available capital.",
                "Operator must supply independently authenticated quotes and approvals later.",
            ],
        }

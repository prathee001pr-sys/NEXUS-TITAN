"""Conservative permission policy for NEXUS TITAN.

This module is an initial software guard, not a substitute for broker-side
controls, operating-system security, or independent human review.
"""
from enum import StrEnum


class Action(StrEnum):
    READ = "read"
    PAPER_TRADE = "paper_trade"
    LIVE_TRADE = "live_trade"
    CHANGE_RISK_CONTROLS = "change_risk_controls"
    CHANGE_PERMISSIONS = "change_permissions"


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_HUMAN_APPROVAL = "requires_human_approval"


_ALWAYS_REQUIRES_APPROVAL = {
    Action.LIVE_TRADE,
    Action.CHANGE_RISK_CONTROLS,
    Action.CHANGE_PERMISSIONS,
}


def decide(action: Action, *, paper_trading_enabled: bool = False) -> Decision:
    """Return the default policy decision for an action.

    Read-only access is allowed. Paper trading is opt-in. Live trading and
    changes to risk/permission controls always require a separate human
    approval workflow, which is intentionally not implemented in this phase.
    """
    if action in _ALWAYS_REQUIRES_APPROVAL:
        return Decision.REQUIRES_HUMAN_APPROVAL
    if action is Action.READ:
        return Decision.ALLOW
    if action is Action.PAPER_TRADE and paper_trading_enabled:
        return Decision.ALLOW
    return Decision.DENY

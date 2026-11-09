"""Explicit local paper permissions; these flags are not human authentication."""
from dataclasses import dataclass

from nexus_titan.core.permissions import Action, Decision, decide


class PaperOperationBlocked(PermissionError):
    """A paper instruction lacks an explicit local permission or safe input."""


@dataclass(frozen=True, slots=True)
class PaperAccess:
    enabled: bool = False
    mode: str = "SAFE"
    autonomous_on: bool = False
    autonomous_allowed: bool = False

    def __post_init__(self):
        if (any(type(v) is not bool for v in (
                self.enabled, self.autonomous_on, self.autonomous_allowed))
                or self.mode not in ("SAFE", "RISKY")):
            raise PaperOperationBlocked("Explicit boolean paper controls and SAFE/RISKY mode required")
        if self.autonomous_on and (self.mode != "RISKY" or not self.autonomous_allowed):
            raise PaperOperationBlocked("Autonomous paper mode is not permitted")

    def require(self, *, human_approved=False, autonomous=False):
        self.__post_init__()
        if type(human_approved) is not bool or type(autonomous) is not bool:
            raise PaperOperationBlocked("Permission claims must be literal booleans")
        if decide(Action.PAPER_TRADE, paper_trading_enabled=self.enabled) is not Decision.ALLOW:
            raise PaperOperationBlocked("Paper trading is disabled")
        if autonomous:
            if not (self.mode == "RISKY" and self.autonomous_on and self.autonomous_allowed):
                raise PaperOperationBlocked("Autonomous operation denied")
        elif not human_approved:
            raise PaperOperationBlocked("Explicit local human paper approval required")

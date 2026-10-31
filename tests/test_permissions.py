from nexus_titan.core.permissions import Action, Decision, decide


def test_read_is_allowed():
    assert decide(Action.READ) is Decision.ALLOW


def test_paper_trading_is_denied_by_default():
    assert decide(Action.PAPER_TRADE) is Decision.DENY


def test_paper_trading_requires_explicit_enablement():
    assert decide(Action.PAPER_TRADE, paper_trading_enabled=True) is Decision.ALLOW


def test_live_trading_always_requires_human_approval():
    assert decide(Action.LIVE_TRADE, paper_trading_enabled=True) is Decision.REQUIRES_HUMAN_APPROVAL


def test_risk_and_permission_changes_require_human_approval():
    assert decide(Action.CHANGE_RISK_CONTROLS) is Decision.REQUIRES_HUMAN_APPROVAL
    assert decide(Action.CHANGE_PERMISSIONS) is Decision.REQUIRES_HUMAN_APPROVAL

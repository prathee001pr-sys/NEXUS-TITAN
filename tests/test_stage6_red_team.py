from nexus_titan.research.adversarial_red_team import TradeProposal, challenge_trade


def test_red_team_flags_bad_stop_and_unfavourable_friction():
    report = challenge_trade(TradeProposal("BUY", 100, 105, 110, 8, 5, 10, 5, 10))
    assert report.veto_recommended
    assert not report.order_submitted
    assert any(f.scenario == "adverse_price_move" and not f.passed for f in report.findings)


def test_red_team_accepts_sane_proposal_as_non_execution_advice():
    report = challenge_trade(TradeProposal("BUY", 100, 95, 110, 1, 1, 10, 20, 10))
    assert not report.veto_recommended
    assert report.order_submitted is False

# Stage96: Selected Indian F&O accounting review (NO LIVE)

This additive candidate reads an existing Stage55 replay-checked synthetic F&O account. It checks cash/cost/realized-P&L conservation, per-position quantity and remaining basis, and exact-head synchronized synthetic MTM when supplied. A missing valid mark **must** leave open equity and unrealized P&L unavailable. Profit factor, expectancy and official drawdown remain unavailable because the approved completed-trade and valuation-history evidence was not supplied. It does not write trades, mint permissions or use a broker route.

The Stage95 `FOClosedTradePipeline` gateway is reused, never rewritten. `selected_fo_scorecard` requires that exact pipeline type. No trading success/real-market accuracy is claimed. Existing upstream older-stage audit limits and historical expiry/futures margin blockers remain.

# NEXUS TITAN Phase 06 — Stages 129–132 (offline)

Add-only research helpers. Stage129 validates contract identity and expiry against a caller-supplied as-of date. Stage130 provides European Black–Scholes estimates and a bounded implied-volatility inversion; Greeks are model estimates, **not** NSE market observations. Stage131 computes explicit, caller-supplied estimated brokerage, fees, slippage and margin, **not** broker/NSE verified margins. Stage132 integrates the helpers in a permanent `RESEARCH_ONLY_NO_GO` gate. No broker API, order execution, promotion, or historical data approval.

Requires a verified Phase05 baseline. Run `PYTHONPATH=src python -m pytest -q -o addopts='' tests/test_stage129_132_fo_research.py`, then full regression on Replit. Phase06 is not CI-verified until GitHub checks pass. Source inputs must be authentic and time-aligned for any future market-data analysis.

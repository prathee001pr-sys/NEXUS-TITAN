# Stage72 — F&O expiry-aware IV / Greeks research envelope (NO-LIVE)

2026-11-04. Stacked on Stage71 draft PR #63. New Stage72 analysis is **research only**.

## Implemented
- A *read-only* bounded research analyst over an explicitly time-aligned Stage71 synthetic option observation plus operator-declared NSE NIFTY/BANKNIFTY options contract and expiry cutoff.
- The existing **Stage16-18 chain integrity** checks run again. All quotes must pass; a single malformed quote fails the entire analysis.
- Bounded, unrounded Black–Scholes–Merton bisection derives bid/mid/ask implied-volatility range (1%-300% annualized) and checks price repricing. Stage6 Greeks are calculated at the mid-IV result; the mid volatility is a model estimate, NOT a calibrated forecast. The spread-derived IV range is **not a statistical confidence interval**, not a depth-backed fill quote, and not guaranteed executable.
- Rejects too-close expiry (default <=60m), wrong expiry date, stale/crossed/too-wide quotes, unaffiliated Stage71 snapshot, future/incomplete futures bar, forged authority claims, malformed rates, and unidentifiable IV outside the bounded bracket.
- Synthetic NIFTY/BANKNIFTY adversarial pytest checks, conservative smoke CLI and CI Python 3.11/3.12/3.13 coverage.

## Important limitations
- No authenticated exchange contract master, official settlement cutoff, market holidays, licensed vendor data, signed source identity, order book depth, realistic fees, F&O margin, expiry exercise/settlement, actual broker route or security assurance. The cutoff and interest/dividend assumptions are caller-provided and can be wrong. A stage71 typed report is not a cryptographically attested data pipeline.
- Model choice is simplified European-style BSM with continuous dividend yield. It is a **numerical research approximation**; its calculated volatility and Greeks may fail to reflect volatility smiles, forward prices, discrete dividends, microstructure, and actual Indian derivatives settlement. No profits, model accuracy, backtests, strategy promotion, paper or live trading allowed.
- The Stage6 legacy IV function uses rounded theoretical premium; Stage72 uses an independent unrounded bracketed solver to avoid converting an unidentifiable quote to a fake IV. This new solver is NOT installed as a mandatory global IV source; all old APIs are unchanged.
- Live release remains **NO-GO** until 60+ draft PR lineage is integrated and reviewed, independently verified real data supplied, risk gate/atomic capital enforced, security/CI and prospectively audited paper outcomes approved.

Next: Stage73 TITAN EVOLVE controlled experience memory, quantitative calibration and champion/challenger **research-only** experiments. No automatic risk parameter change.

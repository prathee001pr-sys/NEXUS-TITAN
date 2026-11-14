# NEXUS TITAN — Stage 221 Python Performance Baseline (candidate)

## Classification and boundaries

**Offline synthetic research/diagnostics only.** This is not a market-data benchmark,
latency SLA, broker-order throughput claim, production authorization, Rust rewrite
approval, benchmark of real NSE liquidity, or an automatic performance gate.

Starting point: **Stage 220** stacked feature commit
`1e5545105f077d93a47397b1c33686cbb057bde2`. Keep the Python-first
architecture and all independent Risk & Veto controls. No production trading
logic or deployed dashboard code is changed by Stage 221.

## Fixed reproducible microbenchmarks

The measurement harness constructs bounded, deterministic synthetic fixtures
and times only existing Python functions. It checks that every execution returns
the same output fingerprint; it refuses malformed or non-monotonic samples.
It uses `time.perf_counter_ns`, per-call median and nearest-rank p95 over bounded
batch samples. Case data and function sources have separate SHA-256 fingerprints.

Fixed targets:

1. **Stage 206** synthetic depth snapshot validation, 10 levels on each side.
2. **Stage 207** hypothetical BUY 750-unit depth walk / partial-fill modeling.
3. **Stage 191** accepted synthetic portfolio ledger of 1,000 closed trades.
4. **Stage 217** offline hash-chained progress journal, 300 events.

Run:

```bash
PYTHONPATH=src python scripts/run_stage221_performance_profile.py \
  --warmups 3 --iterations 5 --samples 9 \
  --json-out reports/stage221_my_host_profile.json
PYTHONPATH=src python scripts/run_stage221_cprofile_hotspots.py \
  --iterations 5 --top 8 --json-out reports/stage221_my_host_hotspots.json
```

For consistent comparisons, **run both Python and potential Rust prototypes on the
same machine, fixture hashes, risk checks, invocation method and sample settings**.
Cross-host absolute times cannot justify a Rust migration.

### Local container reference (14 Nov 2026)

These timings describe one uncalibrated, non-production container run only;
CPU contention causes variance and cProfile timings are invasive. Baseline
files are included for evidence, not as an acceptance gate.

| Fixed target | Median per call | p95 per call |
|---|---:|---:|
| Depth snapshot, 20 levels total | ~0.060 ms | ~0.172 ms |
| Hypothetical liquidity fill | ~0.090 ms | ~0.598 ms |
| 1,000-trade replay ledger | ~9.003 ms | ~14.783 ms |
| 300-event progress journal | ~3.577 ms | ~3.999 ms |

`cProfile` analysis of the ledger sample identified Python iteration,
`_safe_pnl`, and datetime normalization in Stage 191. The journal sample
spends time revalidating events and serializing hashes; the liquidity
model re-parses Decimal prices and independently replays depth validation.
These are investigation targets, **not proof that Rust is needed**.

## Recovery reliability — outstanding independent concern

The previous full local regression had **4,564 passed, 2 failed, 2 skipped**
with failures in `test_stage121_research_supervisor` and
`test_stage123_recovery_fault_lab`. These were sometimes green on isolation.
A Stage 221 opt-in isolated diagnostic on the current host reproduced variable
watchdog behavior: 2 of 3 synthetic `hang_once` runs required two timeouts
instead of one, despite eventually completing. No brokerage calls or live
trading occurred. The `subprocess.run(... timeout=1.2)` wall-clock watchdog
covers process creation/startup, child import/SQLite initialization, and
actual work; the source makes this a plausible contributor, **not a proven
root cause**. No production timeouts/retries/leases have been relaxed.

Optional **explicitly opt-in** triage command (separate synthetic temporary
SQLite ledgers, no external network, bounded 1–10 runs):

```bash
PYTHONPATH=src python scripts/run_stage221_recovery_variability.py \
  --explicit-opt-in --runs 3 --timeout-seconds 1.2
```

This probe deliberately returns nonzero on unexpected timeout counts. It
cannot bypass quarantine or mark Stage 220 reliability accepted.

## Validation, gates and next decisions

- Stage 221 new unit/CLI checks: **40 passed, 0 failed** (`-W error`).
- Stage 154–221 selected strict integration and historical F&O tests:
  **957 passed, 0 failed** (`-W error`).
- Full-suite and real-market evidence **not newly revalidated** for Stage 221.
- GitHub Python 3.11 / 3.12 / 3.13 CI and Secret Scan **pending** on new PR.
- Only measure/propose: no automated Rust integration, risk-limit edits, live
  broker permissions, strategy promotion, or merges into `main`.

For Stage 222, first agree on real throughput and latency requirements, gain
stable same-host baseline repetitions and isolate the watchdog variability.
Only if a hotspot actually violates a workload target should a narrowly scoped
Rust prototype be compared **with behavior parity and existing risk gates**.

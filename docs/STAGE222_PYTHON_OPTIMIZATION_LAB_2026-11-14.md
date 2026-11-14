# NEXUS TITAN — Stage 222 offline Python optimization experiment

## Identity / parent

Stacked on Stage 221 GitHub feature commit:
`b770784b1f5b28a3a778af310e15474948643786`.

Scope is *offline diagnostics only*. Stage 217 journal code, risk checks, permission controls, auth, broker execution, and main branch are unchanged. No trading or strategy promotion is authorized. No production deployment is approved. The repository visibility must not be modified.

## Why this workload?

Stage 221 synthetic profiler observed higher cost in a 300-event Stage 217 progress-journal audit than short synthetic depth/fill checks. Journal processing re-creates events and canonical JSON serializations per entry. Stage 222 asks whether a *restricted-format Python* serialization can be competitive, before considering a Rust prototype. This is not a high-frequency execution-path benchmark, and a journal need not be low latency.

## Candidate and equivalence scope

`stage222_journal_candidate.py` contains a separate experimental validator that preserves Stage 217's typed tuple length limits, event order/link checks, allowed states, stage range (1–220), SHA-256 shape validation, exact canonical digest and typed receipt fields. The generated digest is canonical JSON's sorted ASCII key layout, used **only after** all value types and ranges are validated. No arbitrary strings are interpolated without validation. The candidate is never imported by production services.

- Stage 217 original Python source blob matches the GitHub Stage 221 snapshot: `8c0138057fec27b21650cf45c944474445da456f`.
- 41 new Stage 222 focused tests passed with strict warnings (`-W error`) in local reconstructed codebase.
- 998 Stage 154–222 and historical F&O selected integration tests passed in strict warnings mode (0 failed).
- Positive, negative, tampering, malformed type, digest mismatch, broken link/order, boundary and deterministic pseudo-random cases compare complete candidate receipt against Stage 217 original receipt.
- **Equivalence is not a formal proof** for every possible hostile Python object, concurrency setting, or untrusted serialization. Independent review required before considering production changes.

## Bounded same-host A/B result (CPython 3.13.5, Linux, 14 Nov 2026)

9 alternating-order paired samples per workload; 5 operations per sample after warmup. Only execution is measured; fixture setup is excluded. Median values are rounded. These are local synthetic estimates (not latency SLA), and are **not** compared across hosts.

| Fixed synthetic workload | Original median | Candidate median | Observed ratio |
|---|---:|---:|---:|
| 30 progress events | 0.228 ms | 0.096 ms | 2.37x |
| 300 progress events | 3.336 ms | 1.754 ms | 1.90x |
| 1,000 progress events | 10.369 ms | 4.237 ms | 2.45x |

Report with sample distribution and fixture/output digests: `reports/STAGE222_LOCAL_PYTHON_AB_2026-11-14.json`.

Run a local comparison:

```bash
PYTHONPATH=src python scripts/run_stage222_comparison.py \
  --samples 9 --iterations 5 --json-out /tmp/titan_stage222_my_host.json
```

No CI job may use the speed ratio as a gating threshold. Repeat on representative workloads/hardware and measure memory/resource tradeoffs if the candidate is ever proposed for deployment.

## Required gates before any optimization promotion

1. Independent review confirms original Stage 217 contract is unchanged by this PR.
2. Broader/full regression, hostile-input parity, and recovered-process tests pass stably (Stage 121/123 intermittent full-run timeouts remain unresolved).
3. Demonstrate that operational workload actually needs latency/throughput optimization and that bottleneck is relevant to production goals.
4. Repeat A/B on target hardware with deterministic fixture hashes, valid 3.11–3.13 results, and resource measurements; never justify a migration from a single container microbenchmark.
5. Obtain an explicit owner decision before changing production Stage 217 code or starting Rust integration, with independent risk/veto validation and rollback.

**Verdict:** Experimental Python approach is promising for the synthetic Stage 217 journal, but no production replacement or Rust rewrite is approved. The previously identified recovery-timing flakiness is still outstanding.

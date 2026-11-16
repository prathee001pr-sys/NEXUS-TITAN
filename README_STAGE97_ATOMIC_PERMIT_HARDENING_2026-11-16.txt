NEXUS TITAN — STAGE97 ATOMIC PERMIT HARDENING (RESEARCH-ONLY)

Parent Draft PR #141: 1c757b636a7e0de68b82c8f668f5fe34727dbef5
New feature branch: feature/stage97-atomic-permit-hardening-2026-11-16

A P1 synthetic-paper permit bypass was reproduced: CryptoPaperBook._apply()
accepted an unpermitted trade when invoked directly. The included source patch
revalidates exact-intent TEST permit signature, local paper admission and journal
fence inside SQLite BEGIN IMMEDIATE. It keeps emergency KILL permit-free.

Local reconstructed Python 3.13.5 full regression: 4,967 passed, +5 subtests,
0 failures, 4 previously known Stage88/89 multithreaded os.fork warnings.
This is not yet new-head GitHub CI; the draft PR / branch must be independently
verified after authenticated noreply Git push.

IMPORTANT: not mandatory all-path stricter Risk & Veto, not authenticated human
identity, not live trading. The source audit returns NO-GO despite unit tests.

RUN once in Replit Shell via authenticated GH CLI using packaged script, after
verifying archive SHA-256. The script never merges main, changes visibility,
or enables live trading.

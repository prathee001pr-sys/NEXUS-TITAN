# NEXUS TITAN Phase03 — Guardian + Learn + Advisor

Yeh Stage117–120 ka **add-only tested offline candidate** hai, NOT GitHub-deployed feature.

- **TITAN GUARDIAN:** crash ke baad research jobs resume/inspect karne ke liye durable SQLite job ledger. External process supervisor abhi nahi.
- **TITAN LEARN:** authorized PDF pages, user-supplied video transcript/courses ke short excerpts with citations; no video/platform scraping.
- **TITAN ADVISOR:** proactive `Aap mujhe X dijiye, main Y karke Z improve karne mein madad kar sakta hoon` suggestions; feedback memory.
- **TITAN EVOLVE bridge:** learning evidence se only UNVERIFIED, human-governed strategy research proposal, no autonomous strategy deployment.

**Replit:** Agar latest Stage112–116 Phase02 code ho toh `NEXUS_TITAN_PHASE03_STAGES117_120_DELTA_2026-11-10.zip` ko **separate folder** mein extract karke source-hash preflight aur add-only installer chalayein. Full ZIP review/independent testing ke liye hai; current Replit project par overwrite na karein.

```bash
PYTHONPATH=src python scripts/run_titan_advisor_demo.py
python scripts/validate_phase03_install.py --focused
python scripts/validate_phase03_install.py --full
```

`pypdf` optional hai; PDF direct parsing ke liye isolated worker mein install karna hoga. User-provided transcripts ke liye extra package nahi chahiye.

Protected: No live orders, no broker routing, no modification to Risk & Veto, no automatic code execution, no merging main, no visibility change.

Safe manual/dry-run install (outside active project):

```bash
python /path/to/delta/scripts/install_phase03_add_only.py --source /path/to/delta --target ~/workspace/nexus-titan
# Dry-run verified ho, existing uncommitted changes review karo, phir explicitly:
python /path/to/delta/scripts/install_phase03_add_only.py --source /path/to/delta --target ~/workspace/nexus-titan --apply
```

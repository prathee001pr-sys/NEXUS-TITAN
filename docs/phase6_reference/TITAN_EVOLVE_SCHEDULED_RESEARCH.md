# TITAN EVOLVE — Scheduled Research Setup

TITAN EVOLVE's research scheduler is a **one-shot worker**. Configure Replit
Scheduled Deployments or an external cron service to invoke it on a cadence.
It does not silently run a permanent background loop.

## 1. Configure approved sources

Register an exact HTTPS URL. The hostname in `--allow-hosts` must exactly match
the source URL. Choose only public research/documentation sources you are allowed
to access and store.

```bash
PYTHONPATH=src python scripts/run_evolve_scheduler.py \
  --db data/titan_evolve_runtime.db \
  --allow-hosts docs.python.org \
  --add-source https://docs.python.org/3/library/asyncio.html \
  --topic approved-research --interval-hours 24
```

This is only a configuration example: a public page may change its content type,
require dynamic rendering, impose access restrictions or become unavailable.
Do not bypass authentication or access controls.

## 2. Run due research

Configure a Replit Scheduled Deployment or cron job to call:

```bash
PYTHONPATH=src python scripts/run_evolve_scheduler.py \
  --db data/titan_evolve_runtime.db \
  --allow-hosts docs.python.org \
  --run-due
```

Each invocation checks due sources, fetches only allow-listed URLs, stores
new/changed content in SQLite and exits.

## 3. Optional LLM research synthesis

Set these values in Replit Secrets, never in committed files:

- `TITAN_LLM_API_KEY`
- `TITAN_LLM_BASE_URL` (defaults to `https://api.openai.com/v1`)
- `TITAN_LLM_MODEL`
- `TITAN_LLM_TIMEOUT`

Provider access and billing depend on the separately configured provider account.

## 4. Inspect schedule and learning counters

```bash
PYTHONPATH=src python scripts/run_evolve_scheduler.py \
  --db data/titan_evolve_runtime.db --list
```

## 5. Safeguards

- Sources must be explicitly registered and hostname allow-listed.
- HTTPS and standard port 443 only; no authentication bypass.
- Identical content hashes are skipped.
- Changed content creates versioned learning evidence with provenance.
- Errors are persisted and retried after a bounded delay.
- The scheduler never enables strategies, modifies risk limits or places orders.
- Skill proposals remain inactive until evidence gates and human approval pass.

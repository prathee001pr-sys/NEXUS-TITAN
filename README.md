# NEXUS-TITAN-V2

NEXUS TITAN is a modular AI trading intelligence system.

## Current phase: Core foundation

This repository is being built incrementally. The initial foundation keeps
runtime dependencies minimal and introduces a conservative permission policy.

### Safety defaults

- Read-only actions are allowed.
- Paper trading is disabled unless explicitly enabled by configuration.
- Live trading and changes to risk or permission controls require a separate
  human-approval workflow. That workflow is not implemented yet.
- No broker integration or live execution is included in this foundation.

## Development

Requires Python 3.11 or newer.

```bash
python -m pip install -e ".[dev]"
pytest
```

## Current scope

This is a foundation scaffold, not a production trading system. Backtesting,
market data, broker adapters, and trading strategies will be added only after
the core interfaces and tests are established.

"""Validated, dependency-free application configuration."""
from dataclasses import dataclass
from collections.abc import Mapping


def _read_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    log_level: str = "INFO"
    paper_trading_enabled: bool = False
    virtual_capital_inr: int = 50_000

    def __post_init__(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test, or production")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level is not a supported logging level")
        if self.virtual_capital_inr <= 0:
            raise ValueError("virtual_capital_inr must be greater than zero")


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    """Load settings from a supplied environment mapping (or process env)."""
    if environ is None:
        import os
        environ = os.environ

    capital_raw = environ.get("TITAN_VIRTUAL_CAPITAL_INR", "50000")
    try:
        capital = int(capital_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("TITAN_VIRTUAL_CAPITAL_INR must be an integer") from exc

    return Settings(
        environment=environ.get("TITAN_ENVIRONMENT", "development").strip().lower(),
        log_level=environ.get("TITAN_LOG_LEVEL", "INFO").strip().upper(),
        paper_trading_enabled=_read_bool(
            environ.get("TITAN_PAPER_TRADING_ENABLED", "false"),
            "TITAN_PAPER_TRADING_ENABLED",
        ),
        virtual_capital_inr=capital,
    )

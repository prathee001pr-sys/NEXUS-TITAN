import pytest

from nexus_titan.core.config import Settings, load_settings


def test_defaults_are_safe():
    settings = load_settings({})
    assert settings.environment == "development"
    assert settings.paper_trading_enabled is False
    assert settings.virtual_capital_inr == 50_000


def test_environment_values_are_loaded_and_normalized():
    settings = load_settings({
        "TITAN_ENVIRONMENT": "TEST",
        "TITAN_LOG_LEVEL": "debug",
        "TITAN_PAPER_TRADING_ENABLED": "true",
        "TITAN_VIRTUAL_CAPITAL_INR": "75000",
    })
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.paper_trading_enabled is True
    assert settings.virtual_capital_inr == 75_000


@pytest.mark.parametrize("value", ["maybe", "2", ""])
def test_invalid_boolean_is_rejected(value):
    with pytest.raises(ValueError):
        load_settings({"TITAN_PAPER_TRADING_ENABLED": value})


def test_invalid_environment_is_rejected():
    with pytest.raises(ValueError):
        Settings(environment="staging")


def test_non_positive_virtual_capital_is_rejected():
    with pytest.raises(ValueError):
        Settings(virtual_capital_inr=0)


def test_invalid_capital_string_is_rejected():
    with pytest.raises(ValueError):
        load_settings({"TITAN_VIRTUAL_CAPITAL_INR": "fifty-thousand"})

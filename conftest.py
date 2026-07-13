"""Root conftest — sys.path setup + hermetic config isolation for all test runs."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

# Stop pydantic Settings from reading the developer's live .env during tests.
# pydantic-settings loads .env from CWD even when constructed with _env_file=None,
# so a local .env (e.g. an aggressive risk profile) would leak into Settings() and
# load_config() and make config/preflight tests depend on developer-local state.
from core.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None

_LEAKY_ENV_KEYS = (
    "MAX_POSITION_PCT", "KELLY_FRACTION", "MAX_ORDER_USD", "BANKROLL_USD",
    "CORE_DCA_PCT", "RESEARCH_PROBE_PCT", "EQUITY_RISK_PCT", "EQUITY_MAX_POSITIONS",
    "EQUITY_MAX_NAME_PCT", "EQUITY_MAX_SECTOR_PCT", "EQUITY_DAILY_LOSS_LIMIT_PCT",
    "EQUITY_DRAWDOWN_LIMIT_PCT", "EQUITY_MIN_RR", "EQUITY_TRAIL_R",
    "EQUITY_KELLY_MIN_TRADES", "EQUITY_HARD_TECH_GATE", "EQUITY_PYRAMID_ENABLED",
)


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch):
    """Re-assert config isolation before every test — some test resets env_file
    and OS env vars can leak between tests; tests must see code defaults unless
    they set values explicitly."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in _LEAKY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

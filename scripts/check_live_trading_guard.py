"""Self-check for the hard live-trading lock in equities.execution.alpaca.

Run: uv run python scripts/check_live_trading_guard.py

Asserts on _assert_live_trading_allowed directly — never places a real order.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import Settings
from equities.execution.alpaca import _assert_live_trading_allowed


def main() -> None:
    os.environ.pop("ALLOW_LIVE_TRADING", None)

    # Paper config passes with no opt-in env vars.
    paper = Settings(
        alpaca_paper=True,
        alpaca_base_url="https://paper-api.alpaca.markets",
        live_trading_enabled=False,
        _env_file=None,
    )
    _assert_live_trading_allowed(paper)

    # Live config without opt-ins raises.
    live = Settings(
        alpaca_paper=False,
        alpaca_base_url="https://api.alpaca.markets",
        live_trading_enabled=False,
        _env_file=None,
    )
    try:
        _assert_live_trading_allowed(live)
        raise AssertionError("expected RuntimeError for live config with no opt-ins")
    except RuntimeError:
        pass

    # Live config with only ALLOW_LIVE_TRADING=1 (live_trading_enabled still False) raises.
    os.environ["ALLOW_LIVE_TRADING"] = "1"
    try:
        _assert_live_trading_allowed(live)
        raise AssertionError("expected RuntimeError for live config with partial opt-in")
    except RuntimeError:
        pass

    # Live config with both opt-ins set does not raise.
    live_confirmed = Settings(
        alpaca_paper=False,
        alpaca_base_url="https://api.alpaca.markets",
        live_trading_enabled=True,
        _env_file=None,
    )
    _assert_live_trading_allowed(live_confirmed)

    os.environ.pop("ALLOW_LIVE_TRADING", None)
    print("ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()

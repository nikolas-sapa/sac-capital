"""Startup security preflight checks.

Run before the bot starts (paper or live). Fails loud on missing/placeholder
secrets and refuses to silently allow live trading without explicit
confirmation. This is a checker only — it contains no execution logic.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

from core.config import Settings, load_config

# Settings field name -> human-readable label used in failure messages.
REQUIRED_SECRET_FIELDS: dict[str, str] = {
    "alpaca_api_key_id": "ALPACA_API_KEY_ID",
    "alpaca_secret_key": "ALPACA_SECRET_KEY",
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
    # Note: anthropic_api_key is optional (used as fallback when LLM_PROVIDER=codex)
}

# Case-insensitive denylist of obvious placeholder values.
PLACEHOLDER_TOKENS = {
    "changeme",
    "change_me",
    "your_key_here",
    "your-key-here",
    "xxx",
    "todo",
    "placeholder",
    "replace_me",
    "replaceme",
    "test",
    "none",
    "null",
    "fixme",
}

LIVE_TRADING_CONFIRM_VAR = "LIVE_TRADING_CONFIRMED"


@dataclass
class PreflightResult:
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def add(self, message: str) -> None:
        self.failures.append(message)


def _looks_like_placeholder(value: str) -> bool:
    """Pragmatic placeholder check: empty or an exact denylisted placeholder token."""
    if not value:
        return True
    if value.strip().lower() in PLACEHOLDER_TOKENS:
        return True
    return False


def _required_llm_secret(settings: Settings) -> tuple[str, str] | None:
    provider = settings.llm_provider.strip().lower()
    if provider == "openai":
        return ("openai_api_key", "OPENAI_API_KEY")
    if provider == "anthropic":
        return ("anthropic_api_key", "ANTHROPIC_API_KEY")
    return None


def run_preflight(settings: Settings) -> PreflightResult:
    """Run all preflight checks against *settings* and return the result.

    Does not read .env directly — operates only on the passed Settings
    instance so callers (and tests) fully control inputs.
    """
    result = PreflightResult()

    for field_name, env_name in REQUIRED_SECRET_FIELDS.items():
        value = getattr(settings, field_name, "")
        if _looks_like_placeholder(value):
            result.add(f"{env_name} is missing or looks like a placeholder value")

    llm_secret = _required_llm_secret(settings)
    if llm_secret is not None:
        field_name, env_name = llm_secret
        value = getattr(settings, field_name, "")
        if _looks_like_placeholder(value):
            result.add(f"{env_name} is missing or looks like a placeholder value")

    if settings.live_trading_enabled:
        confirmed = os.environ.get(LIVE_TRADING_CONFIRM_VAR, "").strip().lower()
        if confirmed not in ("true", "1", "yes"):
            result.add(
                "live_trading_enabled is True but "
                f"{LIVE_TRADING_CONFIRM_VAR}=true was not set — refusing to start "
                "in live mode without explicit confirmation"
            )

    return result


def main() -> None:
    settings = load_config()
    result = run_preflight(settings)
    if not result.ok:
        print("PREFLIGHT FAILED:")
        for failure in result.failures:
            print(f"  - {failure}")
        sys.exit(1)
    print("PREFLIGHT OK: all checks passed")


if __name__ == "__main__":
    main()

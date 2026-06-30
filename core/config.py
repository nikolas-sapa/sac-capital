"""Typed application settings loaded from environment / .env file."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    anthropic_api_key: str = ""
    anthropic_fast_model: str = "claude-haiku-4-5-20251001"
    anthropic_strong_model: str = "claude-sonnet-4-6"
    openai_api_key: str = ""
    openai_fast_model: str = "gpt-5-mini"
    openai_strong_model: str = "gpt-5.5"
    codex_fast_model: str = "gpt-5.4-mini"
    codex_strong_model: str = "gpt-5.5"
    llm_provider: str = "codex"  # codex | openai | anthropic | claude
    bankroll_usd: float = 1000.0
    kelly_fraction: float = 0.5
    max_position_pct: float = 0.02
    research_probe_pct: float = 0.005
    core_dca_pct: float = 0.01
    max_order_usd: float = 25.0
    max_daily_order_count: int = 3
    allow_extended_hours: bool = False
    allow_test_orders: bool = False
    live_trading_enabled: bool = False
    execution_provider: str = "internal_paper"  # internal_paper | alpaca_paper

    # equities (Plan 07)
    equity_ledger_path: str = "data/equity.db"
    equity_risk_pct: float = 0.005
    equity_max_positions: int = 12
    equity_max_name_pct: float = 0.25
    equity_max_sector_pct: float = 0.35
    equity_daily_loss_limit_pct: float = 0.05
    equity_drawdown_limit_pct: float = 0.15
    equity_max_price_age_days: int = 7
    equity_provider_timeout_seconds: int = 10
    equity_provider_retries: int = 1
    equity_runner_max_runtime_seconds: int = 1800
    equity_runner_max_provider_failures: int = 20
    equity_runner_max_llm_failures: int = 5
    equity_runner_dry_run: bool = False
    finnhub_api_key: str = ""

    # Alpaca Trading API (paper by default)
    alpaca_api_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    alpaca_base_url: str = "https://paper-api.alpaca.markets"


def load_config(env_file: str | None = ".env") -> Settings:
    """Return a Settings instance, optionally reading from *env_file*."""
    return Settings(_env_file=env_file)

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
    bankroll_usd: float = 1000.0
    kelly_fraction: float = 0.5
    max_position_pct: float = 0.02


def load_config(env_file: str | None = ".env") -> Settings:
    """Return a Settings instance, optionally reading from *env_file*."""
    return Settings(_env_file=env_file)

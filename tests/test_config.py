"""Tests for core.config — typed settings loader."""
import pytest
from core.config import Settings, load_config


class TestDefaults:
    """Settings uses correct defaults when env vars are unset."""

    def test_bankroll_usd_default(self, monkeypatch):
        monkeypatch.delenv("BANKROLL_USD", raising=False)
        s = load_config(env_file=None)
        assert s.bankroll_usd == 1000.0

    def test_kelly_fraction_default(self, monkeypatch):
        monkeypatch.delenv("KELLY_FRACTION", raising=False)
        s = load_config(env_file=None)
        assert s.kelly_fraction == 0.5

    def test_max_position_pct_default(self, monkeypatch):
        monkeypatch.delenv("MAX_POSITION_PCT", raising=False)
        s = load_config(env_file=None)
        assert s.max_position_pct == 0.02

    def test_telegram_bot_token_default(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        s = load_config(env_file=None)
        assert s.telegram_bot_token == ""

    def test_telegram_chat_id_default(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        s = load_config(env_file=None)
        assert s.telegram_chat_id == ""

    def test_anthropic_api_key_default(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        s = load_config(env_file=None)
        assert s.anthropic_api_key == ""


class TestEnvOverrides:
    """Env vars override defaults."""

    def test_bankroll_usd_override(self, monkeypatch):
        monkeypatch.setenv("BANKROLL_USD", "5000.0")
        s = load_config(env_file=None)
        assert s.bankroll_usd == 5000.0

    def test_kelly_fraction_override(self, monkeypatch):
        monkeypatch.setenv("KELLY_FRACTION", "0.25")
        s = load_config(env_file=None)
        assert s.kelly_fraction == 0.25

    def test_max_position_pct_override(self, monkeypatch):
        monkeypatch.setenv("MAX_POSITION_PCT", "0.05")
        s = load_config(env_file=None)
        assert s.max_position_pct == 0.05

    def test_telegram_bot_token_override(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok_abc123")
        s = load_config(env_file=None)
        assert s.telegram_bot_token == "tok_abc123"

    def test_telegram_chat_id_override(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345678")
        s = load_config(env_file=None)
        assert s.telegram_chat_id == "12345678"

    def test_anthropic_api_key_override(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        s = load_config(env_file=None)
        assert s.anthropic_api_key == "sk-ant-test"


def test_equity_defaults_present():
    cfg = load_config(env_file=None)
    assert cfg.equity_ledger_path.endswith(".db")
    assert cfg.equity_risk_pct == 0.02


class TestReturnType:
    """load_config returns a Settings instance."""

    def test_returns_settings_instance(self):
        s = load_config(env_file=None)
        assert isinstance(s, Settings)

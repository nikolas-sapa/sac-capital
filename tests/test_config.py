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

    def test_risk_sizing_defaults(self, monkeypatch):
        monkeypatch.delenv("RESEARCH_PROBE_PCT", raising=False)
        monkeypatch.delenv("CORE_DCA_PCT", raising=False)
        monkeypatch.delenv("MAX_ORDER_USD", raising=False)
        monkeypatch.delenv("MAX_DAILY_ORDER_COUNT", raising=False)
        monkeypatch.delenv("ALLOW_EXTENDED_HOURS", raising=False)
        monkeypatch.delenv("ALLOW_TEST_ORDERS", raising=False)
        monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
        s = load_config(env_file=None)
        assert s.research_probe_pct == 0.005
        assert s.core_dca_pct == 0.01
        assert s.max_order_usd == 25.0
        assert s.max_daily_order_count == 3
        assert s.allow_extended_hours is False
        assert s.allow_test_orders is False
        assert s.live_trading_enabled is False

    def test_execution_provider_default(self, monkeypatch):
        monkeypatch.delenv("EXECUTION_PROVIDER", raising=False)
        s = load_config(env_file=None)
        assert s.execution_provider == "internal_paper"

    def test_telegram_bot_token_default(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        s = load_config(env_file=None)
        assert s.telegram_bot_token == ""

    def test_telegram_chat_id_default(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        s = load_config(env_file=None)
        assert s.telegram_chat_id == ""

    def test_telegram_alert_mode_default(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_ALERT_MODE", raising=False)
        s = load_config(env_file=None)
        assert s.telegram_alert_mode == "critical"

    def test_anthropic_api_key_default(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        s = load_config(env_file=None)
        assert s.anthropic_api_key == ""

    def test_anthropic_model_defaults(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_FAST_MODEL", raising=False)
        monkeypatch.delenv("ANTHROPIC_STRONG_MODEL", raising=False)
        s = load_config(env_file=None)
        assert s.anthropic_fast_model == "claude-haiku-4-5-20251001"
        assert s.anthropic_strong_model == "claude-sonnet-4-6"

    def test_openai_defaults(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_FAST_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_STRONG_MODEL", raising=False)
        monkeypatch.delenv("CODEX_FAST_MODEL", raising=False)
        monkeypatch.delenv("CODEX_STRONG_MODEL", raising=False)
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        s = load_config(env_file=None)
        assert s.openai_api_key == ""
        assert s.openai_fast_model == "gpt-5-mini"
        assert s.openai_strong_model == "gpt-5.5"
        assert s.codex_fast_model == "gpt-5.4-mini"
        assert s.codex_strong_model == "gpt-5.5"
        assert s.llm_provider == "codex"

    def test_alpaca_defaults(self, monkeypatch):
        monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        monkeypatch.delenv("ALPACA_PAPER", raising=False)
        monkeypatch.delenv("ALPACA_BASE_URL", raising=False)
        s = load_config(env_file=None)
        assert s.alpaca_api_key_id == ""
        assert s.alpaca_secret_key == ""
        assert s.alpaca_paper is True
        assert s.alpaca_base_url == "https://paper-api.alpaca.markets"


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

    def test_risk_sizing_overrides(self, monkeypatch):
        monkeypatch.setenv("RESEARCH_PROBE_PCT", "0.01")
        monkeypatch.setenv("CORE_DCA_PCT", "0.03")
        monkeypatch.setenv("MAX_ORDER_USD", "100")
        monkeypatch.setenv("MAX_DAILY_ORDER_COUNT", "8")
        monkeypatch.setenv("ALLOW_EXTENDED_HOURS", "true")
        monkeypatch.setenv("ALLOW_TEST_ORDERS", "true")
        monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
        s = load_config(env_file=None)
        assert s.research_probe_pct == 0.01
        assert s.core_dca_pct == 0.03
        assert s.max_order_usd == 100.0
        assert s.max_daily_order_count == 8
        assert s.allow_extended_hours is True
        assert s.allow_test_orders is True
        assert s.live_trading_enabled is True

    def test_execution_provider_override(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_PROVIDER", "alpaca_paper")
        s = load_config(env_file=None)
        assert s.execution_provider == "alpaca_paper"

    def test_telegram_bot_token_override(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok_abc123")
        s = load_config(env_file=None)
        assert s.telegram_bot_token == "tok_abc123"

    def test_telegram_chat_id_override(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345678")
        s = load_config(env_file=None)
        assert s.telegram_chat_id == "12345678"

    def test_telegram_alert_mode_override(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ALERT_MODE", "verbose")
        s = load_config(env_file=None)
        assert s.telegram_alert_mode == "verbose"

    def test_anthropic_api_key_override(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        s = load_config(env_file=None)
        assert s.anthropic_api_key == "sk-ant-test"

    def test_anthropic_model_overrides(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5-20251001")
        monkeypatch.setenv("ANTHROPIC_STRONG_MODEL", "claude-sonnet-4-6")
        s = load_config(env_file=None)
        assert s.anthropic_fast_model == "claude-haiku-4-5-20251001"
        assert s.anthropic_strong_model == "claude-sonnet-4-6"

    def test_openai_overrides(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        monkeypatch.setenv("OPENAI_FAST_MODEL", "gpt-5-nano")
        monkeypatch.setenv("OPENAI_STRONG_MODEL", "gpt-5.5")
        monkeypatch.setenv("CODEX_FAST_MODEL", "gpt-5.4-mini")
        monkeypatch.setenv("CODEX_STRONG_MODEL", "gpt-5.5")
        monkeypatch.setenv("LLM_PROVIDER", "codex")
        s = load_config(env_file=None)
        assert s.openai_api_key == "sk-openai-test"
        assert s.openai_fast_model == "gpt-5-nano"
        assert s.openai_strong_model == "gpt-5.5"
        assert s.codex_fast_model == "gpt-5.4-mini"
        assert s.codex_strong_model == "gpt-5.5"
        assert s.llm_provider == "codex"

    def test_alpaca_overrides(self, monkeypatch):
        monkeypatch.setenv("ALPACA_API_KEY_ID", "PKTEST")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-test")
        monkeypatch.setenv("ALPACA_PAPER", "false")
        monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
        s = load_config(env_file=None)
        assert s.alpaca_api_key_id == "PKTEST"
        assert s.alpaca_secret_key == "secret-test"
        assert s.alpaca_paper is False
        assert s.alpaca_base_url == "https://api.alpaca.markets"


def test_equity_defaults_present():
    cfg = load_config(env_file=None)
    assert cfg.equity_ledger_path.endswith(".db")
    assert cfg.equity_risk_pct == 0.02
    assert cfg.equity_max_positions == 4
    assert cfg.equity_max_name_pct == 0.25
    assert cfg.equity_max_sector_pct == 0.35
    assert cfg.equity_daily_loss_limit_pct == 0.05
    assert cfg.equity_drawdown_limit_pct == 0.15
    assert cfg.equity_max_price_age_days == 7
    assert cfg.equity_provider_timeout_seconds == 10
    assert cfg.equity_provider_retries == 1
    assert cfg.equity_runner_max_runtime_seconds == 1800
    assert cfg.equity_runner_max_provider_failures == 20
    assert cfg.equity_runner_max_llm_failures == 5
    assert cfg.equity_runner_dry_run is False


def test_equity_config_overrides(monkeypatch):
    monkeypatch.setenv("EQUITY_MAX_POSITIONS", "2")
    monkeypatch.setenv("EQUITY_DAILY_LOSS_LIMIT_PCT", "0.01")
    monkeypatch.setenv("EQUITY_RUNNER_MAX_RUNTIME_SECONDS", "30")
    monkeypatch.setenv("EQUITY_RUNNER_DRY_RUN", "true")

    cfg = load_config(env_file=None)

    assert cfg.equity_max_positions == 2
    assert cfg.equity_daily_loss_limit_pct == 0.01
    assert cfg.equity_runner_max_runtime_seconds == 30
    assert cfg.equity_runner_dry_run is True


class TestReturnType:
    """load_config returns a Settings instance."""

    def test_returns_settings_instance(self):
        s = load_config(env_file=None)
        assert isinstance(s, Settings)

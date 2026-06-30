"""Tests for scripts.preflight — startup security checks."""
from core.config import Settings
from scripts.preflight import LIVE_TRADING_CONFIRM_VAR, run_preflight


def _valid_settings(**overrides) -> Settings:
    defaults = dict(
        alpaca_api_key_id="PKLIVE1234567890",
        alpaca_secret_key="sk-real-looking-secret-value-123",
        telegram_bot_token="123456789:AAFakeRealisticTokenValue",
        telegram_chat_id="987654321",
        llm_provider="codex",
        live_trading_enabled=False,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


class TestAllValid:
    def test_all_keys_present_and_valid_passes(self):
        settings = _valid_settings()
        result = run_preflight(settings)
        assert result.ok is True
        assert result.failures == []


class TestMissingKey:
    def test_missing_key_fails_with_key_named(self):
        settings = _valid_settings(alpaca_api_key_id="")
        result = run_preflight(settings)
        assert result.ok is False
        assert any("ALPACA_API_KEY_ID" in f for f in result.failures)


class TestPlaceholderValue:
    def test_placeholder_value_fails_for_openai_provider(self):
        settings = _valid_settings(llm_provider="openai", openai_api_key="changeme")
        result = run_preflight(settings)
        assert result.ok is False
        assert any("OPENAI_API_KEY" in f for f in result.failures)

    def test_placeholder_value_case_insensitive(self):
        settings = _valid_settings(telegram_bot_token="ChangeMe")
        result = run_preflight(settings)
        assert result.ok is False
        assert any("TELEGRAM_BOT_TOKEN" in f for f in result.failures)

    def test_codex_provider_does_not_require_anthropic_key(self):
        settings = _valid_settings(anthropic_api_key="", llm_provider="codex")
        result = run_preflight(settings)
        assert result.ok is True
        assert result.failures == []

    def test_anthropic_provider_requires_anthropic_key(self):
        settings = _valid_settings(llm_provider="anthropic", anthropic_api_key="")
        result = run_preflight(settings)
        assert result.ok is False
        assert any("ANTHROPIC_API_KEY" in f for f in result.failures)


class TestLiveTradingGate:
    def test_live_trading_enabled_without_confirmation_fails(self, monkeypatch):
        monkeypatch.delenv(LIVE_TRADING_CONFIRM_VAR, raising=False)
        settings = _valid_settings(live_trading_enabled=True)
        result = run_preflight(settings)
        assert result.ok is False
        assert any("live_trading_enabled" in f for f in result.failures)

    def test_live_trading_enabled_with_confirmation_passes(self, monkeypatch):
        monkeypatch.setenv(LIVE_TRADING_CONFIRM_VAR, "true")
        settings = _valid_settings(live_trading_enabled=True)
        result = run_preflight(settings)
        assert result.ok is True
        assert result.failures == []

    def test_live_trading_disabled_passes_regardless_of_confirmation_var(
        self, monkeypatch
    ):
        monkeypatch.delenv(LIVE_TRADING_CONFIRM_VAR, raising=False)
        settings = _valid_settings(live_trading_enabled=False)
        result = run_preflight(settings)
        assert result.ok is True

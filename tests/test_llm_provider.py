from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.claude_client import ClaudeCodeClient, CodexCLIClient, LLMResponse, make_llm_client


def test_make_llm_client_respects_codex_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    client = make_llm_client()
    assert isinstance(client, ClaudeCodeClient)
    assert client._codex is not None  # type: ignore[attr-defined]


def test_make_llm_client_defaults_to_codex(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = make_llm_client()
    assert isinstance(client, ClaudeCodeClient)
    assert client._codex is not None  # type: ignore[attr-defined]


def test_make_llm_client_auto_prefers_openai_api_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    client = make_llm_client()

    assert client._openai is not None  # type: ignore[attr-defined]
    assert client._codex is None  # type: ignore[attr-defined]


def test_auto_provider_uses_anthropic_before_codex_when_configured(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    client = make_llm_client()

    assert client._anthropic is not None  # type: ignore[attr-defined]
    assert client._codex is None  # type: ignore[attr-defined]


def test_make_llm_client_uses_anthropic_for_legacy_api_key(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = make_llm_client(api_key="sk-ant-test")
    assert isinstance(client, ClaudeCodeClient)
    assert client._anthropic is not None  # type: ignore[attr-defined]
    assert client._codex is None  # type: ignore[attr-defined]


def test_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        ClaudeCodeClient()


def test_anthropic_provider_requires_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ClaudeCodeClient()


def test_codex_cli_writes_and_reads_last_message(monkeypatch):
    calls = {}

    def fake_run(args, input, capture_output, text, timeout, cwd, env=None, start_new_session=False):
        calls["args"] = args
        calls["input"] = input
        out_idx = args.index("--output-last-message") + 1
        Path(args[out_idx]).write_text('{"action":"reject"}')
        return SimpleNamespace(returncode=0, stderr="", stdout="ignored")

    monkeypatch.setattr("core.claude_client.subprocess.run", fake_run)
    resp = CodexCLIClient(timeout=1).complete("sys", "user", "haiku")

    assert resp.content == '{"action":"reject"}'
    assert "codex" in calls["args"]
    assert "gpt-5.4-mini" in calls["args"]
    assert "--ephemeral" in calls["args"]
    assert "--ignore-rules" in calls["args"]
    assert "Do not inspect files" in calls["input"]


def test_codex_client_falls_back_to_anthropic_on_quota_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    def fake_codex_complete(self, system, user, model):
        raise RuntimeError("codex exec failed (exit 1): quota exceeded")

    def fake_anthropic_complete(self, system, user, model):
        return LLMResponse(content="anthropic-fallback", input_tokens=1, output_tokens=1)

    monkeypatch.setattr("core.claude_client.CodexCLIClient.complete", fake_codex_complete)
    monkeypatch.setattr("core.claude_client.AnthropicResponsesClient.complete", fake_anthropic_complete)

    client = ClaudeCodeClient()
    resp = client.complete("sys", "user", "sonnet")

    assert resp.content == "anthropic-fallback"


def test_codex_client_falls_back_to_anthropic_on_token_expired(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    def fake_codex_complete(self, system, user, model):
        raise RuntimeError("codex exec failed (exit 1): HTTP 401 Unauthorized token_expired")

    def fake_anthropic_complete(self, system, user, model):
        return LLMResponse(content="anthropic-fallback", input_tokens=1, output_tokens=1)

    monkeypatch.setattr("core.claude_client.CodexCLIClient.complete", fake_codex_complete)
    monkeypatch.setattr("core.claude_client.AnthropicResponsesClient.complete", fake_anthropic_complete)

    client = ClaudeCodeClient()
    resp = client.complete("sys", "user", "sonnet")

    assert resp.content == "anthropic-fallback"


def test_explicit_anthropic_provider_uses_sdk(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    def fake_complete(self, system, user, model):
        return LLMResponse(content=f"{model}:{system}:{user}", input_tokens=3, output_tokens=4)

    monkeypatch.setattr("core.claude_client.AnthropicResponsesClient.complete", fake_complete)

    client = ClaudeCodeClient()
    resp = client.complete("sys", "user", "strong")

    assert resp.content == "strong:sys:user"

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


def test_auto_provider_ignores_anthropic_key_and_defaults_to_codex(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    client = make_llm_client()

    assert client._anthropic is None  # type: ignore[attr-defined]
    assert client._codex is not None  # type: ignore[attr-defined]


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


def test_codex_client_reraises_on_quota_error_when_no_claude_cli(monkeypatch):
    """Non-auth Codex failure with no `claude` binary for fallback → re-raise original."""
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def fake_codex_complete(self, system, user, model):
        raise RuntimeError("codex exec failed (exit 1): quota exceeded")

    monkeypatch.setattr("core.claude_client.CodexCLIClient.complete", fake_codex_complete)
    monkeypatch.setattr("core.claude_client.shutil.which", lambda name: None)

    client = ClaudeCodeClient()
    with pytest.raises(RuntimeError, match="quota exceeded"):
        client.complete("sys", "user", "sonnet")
    assert client._anthropic is None  # type: ignore[attr-defined]


def test_codex_fallback_on_token_expired_uses_claude_cli(monkeypatch):
    """Codex auth expiry → fall back to the `claude` CLI (subscription-billed, NOT metered API)."""
    monkeypatch.setenv("LLM_PROVIDER", "codex")

    def fake_codex_complete(self, system, user, model):
        raise RuntimeError("codex exec failed (exit 1): HTTP 401 Unauthorized token_expired")

    def fake_claude_cli(self, system, user, model):
        return LLMResponse(content="claude-cli-response", input_tokens=10, output_tokens=20)

    monkeypatch.setattr("core.claude_client.CodexCLIClient.complete", fake_codex_complete)
    monkeypatch.setattr("core.claude_client.shutil.which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr("core.claude_client.ClaudeCodeClient._complete_with_claude_cli", fake_claude_cli)

    client = ClaudeCodeClient()
    resp = client.complete("sys", "user", "sonnet")
    assert resp.content == "claude-cli-response"


def test_codex_fallback_never_uses_metered_anthropic_api(monkeypatch):
    """Guard: even with ANTHROPIC_API_KEY set, the fallback must NOT hit the metered SDK."""
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    def fake_codex_complete(self, system, user, model):
        raise RuntimeError("codex exec failed (exit 1): HTTP 401 Unauthorized token_expired")

    def boom(self, system, user, model):
        raise AssertionError("metered Anthropic API must not be used as fallback")

    monkeypatch.setattr("core.claude_client.CodexCLIClient.complete", fake_codex_complete)
    monkeypatch.setattr("core.claude_client.AnthropicResponsesClient.complete", boom)
    monkeypatch.setattr("core.claude_client.shutil.which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(
        "core.claude_client.ClaudeCodeClient._complete_with_claude_cli",
        lambda self, s, u, m: LLMResponse(content="claude-cli", input_tokens=1, output_tokens=1),
    )

    client = ClaudeCodeClient()
    resp = client.complete("sys", "user", "sonnet")
    assert resp.content == "claude-cli"


def test_codex_client_raises_clean_message_when_claude_cli_missing(monkeypatch):
    """Codex auth expiry with no `claude` binary for fallback → clean 'codex login' message."""
    monkeypatch.setenv("LLM_PROVIDER", "codex")

    def fake_codex_complete(self, system, user, model):
        raise RuntimeError("codex exec failed (exit 1): HTTP 401 Unauthorized refresh_token_reused")

    monkeypatch.setattr("core.claude_client.CodexCLIClient.complete", fake_codex_complete)
    monkeypatch.setattr("core.claude_client.shutil.which", lambda name: None)

    client = ClaudeCodeClient()
    with pytest.raises(RuntimeError, match="codex login"):
        client.complete("sys", "user", "sonnet")
    assert client._anthropic is None  # type: ignore[attr-defined]


def test_explicit_anthropic_provider_uses_sdk(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    def fake_complete(self, system, user, model):
        return LLMResponse(content=f"{model}:{system}:{user}", input_tokens=3, output_tokens=4)

    monkeypatch.setattr("core.claude_client.AnthropicResponsesClient.complete", fake_complete)

    client = ClaudeCodeClient()
    resp = client.complete("sys", "user", "strong")

    assert resp.content == "strong:sys:user"


def test_codex_fallback_on_exec_failure_uses_claude_cli(monkeypatch):
    """Non-auth Codex exec failure → fall back to the `claude` CLI (subscription)."""
    monkeypatch.setenv("LLM_PROVIDER", "codex")

    def fake_codex_complete(self, system, user, model):
        raise RuntimeError("codex exec failed (exit 1): internal error")

    def fake_claude_cli(self, system, user, model):
        return LLMResponse(content="fallback-response", input_tokens=5, output_tokens=15)

    monkeypatch.setattr("core.claude_client.CodexCLIClient.complete", fake_codex_complete)
    monkeypatch.setattr("core.claude_client.shutil.which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr("core.claude_client.ClaudeCodeClient._complete_with_claude_cli", fake_claude_cli)

    client = ClaudeCodeClient()
    resp = client.complete("sys", "user", "sonnet")
    assert resp.content == "fallback-response"


def test_claude_cli_provider_is_first_class(monkeypatch):
    """LLM_PROVIDER=claude_cli must route to the claude CLI without codex or keys."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    from core.claude_client import ClaudeCodeClient, LLMResponse

    client = ClaudeCodeClient()
    assert client._codex is None
    assert client._openai is None
    assert client._anthropic is None
    assert client._provider == "claude_cli"

    calls = {}

    def fake_cli(system, user, model):
        calls["model"] = model
        return LLMResponse(content="ok", input_tokens=1, output_tokens=1)

    client._complete_with_claude_cli = fake_cli
    resp = client.complete("sys", "usr", "fast")
    assert resp.content == "ok"
    assert calls["model"] == "fast"


def test_claude_cli_provider_invokes_claude_binary_via_subprocess(monkeypatch):
    """LLM_PROVIDER=claude_cli must shell out to `claude -p --model <mapped>` via
    subprocess, pass the prompt via `input`, and raise on nonzero returncode."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")

    calls = {}

    def fake_run(args, input, capture_output, text, timeout, start_new_session=False):
        calls["args"] = args
        calls["input"] = input
        return SimpleNamespace(returncode=1, stderr="boom", stdout="")

    monkeypatch.setattr("core.claude_client.subprocess.run", fake_run)
    client = ClaudeCodeClient()

    with pytest.raises(RuntimeError, match="boom"):
        client.complete("sys", "usr", "strong")

    assert calls["args"][:4] == ["claude", "-p", "--model", "claude-sonnet-4-6"]
    assert "sys" in calls["input"] and "usr" in calls["input"]

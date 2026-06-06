from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.claude_client import ClaudeCodeClient, CodexCLIClient, make_llm_client


def test_make_llm_client_respects_codex_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "codex")
    client = make_llm_client()
    assert isinstance(client, ClaudeCodeClient)
    assert client._codex is not None  # type: ignore[attr-defined]


def test_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        ClaudeCodeClient()


def test_codex_cli_writes_and_reads_last_message(monkeypatch):
    calls = {}

    def fake_run(args, input, capture_output, text, timeout, cwd):
        calls["args"] = args
        calls["input"] = input
        out_idx = args.index("--output-last-message") + 1
        Path(args[out_idx]).write_text('{"action":"reject"}')
        return SimpleNamespace(returncode=0, stderr="", stdout="ignored")

    monkeypatch.setattr("core.claude_client.subprocess.run", fake_run)
    resp = CodexCLIClient(timeout=1).complete("sys", "user", "haiku")

    assert resp.content == '{"action":"reject"}'
    assert "codex" in calls["args"]
    assert "--ephemeral" in calls["args"]
    assert "--ignore-rules" in calls["args"]
    assert "Do not inspect files" in calls["input"]

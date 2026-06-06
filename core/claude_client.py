"""LLM client adapters for the trading bot.

By default this module routes through OpenAI when OPENAI_API_KEY is set.
It falls back to the Claude Code CLI for backward compatibility.

Two adapters provided:
  ClaudeCodeClient  — complete(system, user, model) -> LLMResponse
                      used by EquityAnalyst and LLMProbabilityStrategy
  ClaudeCodeBackend — complete(prompt, *, model) -> str
                      satisfies the _Backend protocol in strategies/llm_probability/llm.py

The class names are kept stable to avoid rewriting all call sites during the
temporary provider swap.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int   # estimated (claude -p doesn't report usage)
    output_tokens: int

    def cost_usd(self, model: str = "sonnet") -> float:
        # The runners use separate conservative fixed-cost guards before calls.
        # Return 0 here so subscription/OpenAI provider differences do not block
        # legacy flows unexpectedly.
        return 0.0


class OpenAIResponsesClient:
    """Call OpenAI Responses API using the same complete() shape as the bot.

    Model aliases preserve existing Haiku/Sonnet call sites:
      - haiku  -> OPENAI_FAST_MODEL   or gpt-5-mini
      - sonnet -> OPENAI_STRONG_MODEL or gpt-5.2
    """

    _MODEL_MAP = {
        "claude-haiku-4-5-20251001": "fast",
        "claude-sonnet-4-6": "strong",
        "haiku": "fast",
        "sonnet": "strong",
    }

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 180,
        fast_model: str | None = None,
        strong_model: str | None = None,
    ) -> None:
        from openai import OpenAI

        self._fast_model = fast_model or os.getenv("OPENAI_FAST_MODEL", "gpt-5-mini")
        self._strong_model = strong_model or os.getenv("OPENAI_STRONG_MODEL", "gpt-5.2")
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), timeout=timeout)

    def _map_model(self, model: str) -> str:
        mapped = self._MODEL_MAP.get(model, model)
        if mapped == "fast":
            return self._fast_model
        if mapped == "strong":
            return self._strong_model
        return mapped

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        mapped = self._map_model(model)
        resp = self._client.responses.create(
            model=mapped,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_output_tokens=2048,
        )
        text = getattr(resp, "output_text", "") or ""
        usage = getattr(resp, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        if input_tokens == 0:
            input_tokens = (len(system) + len(user)) // 4
        if output_tokens == 0:
            output_tokens = len(text) // 4
        return LLMResponse(content=text.strip(), input_tokens=input_tokens, output_tokens=output_tokens)


class CodexCLIClient:
    """Call local Codex CLI non-interactively.

    This is intended for Mac-local runs where Codex is logged in with a ChatGPT
    subscription. It is slower than the OpenAI API and should not be used for
    high-frequency loops.
    """

    _MODEL_MAP = {
        "claude-haiku-4-5-20251001": "fast",
        "claude-sonnet-4-6": "strong",
        "haiku": "fast",
        "sonnet": "strong",
    }

    def __init__(
        self,
        timeout: int = 300,
        fast_model: str | None = None,
        strong_model: str | None = None,
    ) -> None:
        self._timeout = timeout
        self._fast_model = fast_model or os.getenv("CODEX_FAST_MODEL", "gpt-5.5")
        self._strong_model = strong_model or os.getenv("CODEX_STRONG_MODEL", "gpt-5.5")

    def _map_model(self, model: str) -> str:
        mapped = self._MODEL_MAP.get(model, model)
        if mapped == "fast":
            return self._fast_model
        if mapped == "strong":
            return self._strong_model
        return mapped

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        mapped = self._map_model(model)
        prompt = (
            "Return only the requested final answer. Do not inspect files, run tools, "
            "or include commentary outside the requested format.\n\n"
            f"System:\n{system}\n\nUser:\n{user}"
        )
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "codex-last-message.txt"
            result = subprocess.run(
                [
                    "codex",
                    "--ask-for-approval",
                    "never",
                    "exec",
                    "--model",
                    mapped,
                    "--sandbox",
                    "read-only",
                    "--skip-git-repo-check",
                    "--ephemeral",
                    "--ignore-rules",
                    "--cd",
                    tmp,
                    "--output-last-message",
                    str(out_path),
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=tmp,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                raise RuntimeError(f"codex exec failed (exit {result.returncode}): {stderr}")
            text = out_path.read_text().strip() if out_path.exists() else result.stdout.strip()
        return LLMResponse(
            content=text,
            input_tokens=len(prompt) // 4,
            output_tokens=len(text) // 4,
        )


class ClaudeCodeClient:
    """Backward-compatible client.

    Provider selection:
      - LLM_PROVIDER=codex  -> local Codex CLI / ChatGPT login
      - LLM_PROVIDER=openai -> OpenAI API (requires OPENAI_API_KEY)
      - LLM_PROVIDER=claude -> Claude CLI
      - blank              -> OpenAI API if OPENAI_API_KEY is set, else Claude CLI

    Args:
        timeout: Max seconds to wait for a response (default 60).
    """

    _MODEL_MAP = {
        "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6":         "claude-sonnet-4-6",
        "haiku":                     "claude-haiku-4-5-20251001",
        "sonnet":                    "claude-sonnet-4-6",
    }

    def __init__(self, timeout: int = 180, provider: str | None = None) -> None:
        self._timeout = timeout
        provider = (provider or os.getenv("LLM_PROVIDER", "")).lower()
        use_openai = provider == "openai" or (provider == "" and bool(os.getenv("OPENAI_API_KEY")))
        use_codex = provider == "codex"
        self._openai: OpenAIResponsesClient | None = None
        self._codex: CodexCLIClient | None = None
        if use_openai:
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
            self._openai = OpenAIResponsesClient(timeout=timeout)
        if use_codex:
            self._codex = CodexCLIClient(timeout=max(timeout, 300))

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        """Send a prompt and return the response."""
        if self._openai is not None:
            return self._openai.complete(system, user, model)
        if self._codex is not None:
            return self._codex.complete(system, user, model)

        mapped = self._MODEL_MAP.get(model, model)
        full_prompt = f"{system}\n\n---\n\n{user}"

        result = subprocess.run(
            [
                "claude", "-p", "--model", mapped,
                "--setting-sources=",   # don't load global settings → no MCP servers
                "--strict-mcp-config",  # only use explicitly configured MCP (none)
                "--permission-mode", "default",
                full_prompt,
            ],
            capture_output=True,
            text=True,
            timeout=self._timeout,
            stdin=subprocess.DEVNULL,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"claude -p failed (exit {result.returncode}): {stderr}")


        text = result.stdout.strip()
        # Rough token estimate (4 chars ≈ 1 token)
        est_in = len(full_prompt) // 4
        est_out = len(text) // 4
        return LLMResponse(content=text, input_tokens=est_in, output_tokens=est_out)


class ClaudeCodeBackend:
    """Adapter satisfying the _Backend protocol used by strategies/llm_probability/llm.py.

    complete(prompt, *, model) -> str
    complete_batch(prompts, *, model) -> list[str]
    """

    def __init__(self, timeout: int = 180) -> None:
        self._client = ClaudeCodeClient(timeout=timeout)

    def complete(self, prompt: str, *, model: str = "sonnet") -> str:
        resp = self._client.complete(system="", user=prompt, model=model)
        return resp.content

    def complete_batch(self, prompts: list[str], *, model: str = "sonnet") -> list[str]:
        return [self.complete(p, model=model) for p in prompts]


def make_llm_client(api_key: str = "") -> "ClaudeCodeClient":
    """Return an LLM client.

    Provider env vars take precedence. The Anthropic path is retained only for
    older code that explicitly passes an API key here.
    """
    provider = os.getenv("LLM_PROVIDER")
    if provider or os.getenv("OPENAI_API_KEY"):
        return ClaudeCodeClient(provider=provider)
    if api_key:
        from equities.analysis.analyst import AnthropicLLMClient
        return AnthropicLLMClient(api_key)  # type: ignore[return-value]
    return ClaudeCodeClient()

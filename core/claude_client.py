"""LLM client adapters for the trading bot.

By default this module routes through the local Codex CLI. OpenAI API,
Anthropic SDK, and Claude CLI routes remain available through LLM_PROVIDER
for compatibility.

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
    input_tokens: int   # estimated for local CLI providers
    output_tokens: int

    def cost_usd(self, model: str = "sonnet") -> float:
        # The runners use separate conservative fixed-cost guards before calls.
        # Return 0 here so subscription/OpenAI provider differences do not block
        # legacy flows unexpectedly.
        return 0.0


class OpenAIResponsesClient:
    """Call OpenAI Responses API using the same complete() shape as the bot.

    Model aliases preserve existing Haiku/Sonnet call sites:
      - fast   -> OPENAI_FAST_MODEL   or gpt-5-mini
      - haiku  -> OPENAI_FAST_MODEL   or gpt-5-mini
      - sonnet -> OPENAI_STRONG_MODEL or gpt-5.5
    """

    _MODEL_MAP = {
        "claude-haiku-4-5-20251001": "fast",
        "claude-sonnet-4-6": "strong",
        "fast": "fast",
        "strong": "strong",
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
        self._fast_model = fast_model or os.getenv("OPENAI_FAST_MODEL", "gpt-5-mini")
        self._strong_model = strong_model or os.getenv("OPENAI_STRONG_MODEL", "gpt-5.5")
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._timeout = timeout
        self._client = None

    def _map_model(self, model: str) -> str:
        mapped = self._MODEL_MAP.get(model, model)
        if mapped == "fast":
            return self._fast_model
        if mapped == "strong":
            return self._strong_model
        return mapped

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, timeout=self._timeout)
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


class AnthropicResponsesClient:
    """Call Anthropic's SDK using the same complete() shape as the bot.

    Model aliases preserve existing Haiku/Sonnet call sites:
      - fast   -> ANTHROPIC_FAST_MODEL   or claude-haiku-4-5-20251001
      - haiku  -> ANTHROPIC_FAST_MODEL   or claude-haiku-4-5-20251001
      - sonnet -> ANTHROPIC_STRONG_MODEL or claude-sonnet-4-6
    """

    _MODEL_MAP = {
        "claude-haiku-4-5-20251001": "fast",
        "claude-sonnet-4-6": "strong",
        "fast": "fast",
        "strong": "strong",
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
        self._fast_model = fast_model or os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5-20251001")
        self._strong_model = strong_model or os.getenv("ANTHROPIC_STRONG_MODEL", "claude-sonnet-4-6")
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._timeout = timeout
        self._client = None

    def _map_model(self, model: str) -> str:
        mapped = self._MODEL_MAP.get(model, model)
        if mapped == "fast":
            return self._fast_model
        if mapped == "strong":
            return self._strong_model
        return mapped

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self._api_key, timeout=self._timeout)
        mapped = self._map_model(model)
        resp = self._client.messages.create(
            model=mapped,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text if resp.content else ""
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
        "fast": "fast",
        "strong": "strong",
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
        self._fast_model = fast_model or os.getenv("CODEX_FAST_MODEL", "gpt-5.4-mini")
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
            _CODEX_SAFE_ENV_KEYS = {"PATH", "HOME", "TMPDIR", "TERM", "LANG", "LC_ALL", "USER", "LOGNAME"}
            safe_env = {k: v for k, v in os.environ.items() if k in _CODEX_SAFE_ENV_KEYS}
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
                env=safe_env,
                start_new_session=True,
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
      - LLM_PROVIDER=codex     -> local Codex CLI / ChatGPT login
      - LLM_PROVIDER=openai    -> OpenAI API (requires OPENAI_API_KEY)
      - LLM_PROVIDER=claude    -> Claude CLI
      - LLM_PROVIDER=anthropic -> Anthropic SDK
      - blank / auto           -> Codex CLI

    Args:
        timeout: Max seconds to wait for a response (default 60).
    """

    _MODEL_MAP = {
        "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6":         "claude-sonnet-4-6",
        "fast":                      "claude-haiku-4-5-20251001",
        "strong":                    "claude-sonnet-4-6",
        "haiku":                     "claude-haiku-4-5-20251001",
        "sonnet":                    "claude-sonnet-4-6",
    }

    def __init__(
        self,
        timeout: int = 180,
        provider: str | None = None,
        anthropic_api_key: str | None = None,
    ) -> None:
        self._timeout = timeout
        self._provider = (provider or os.getenv("LLM_PROVIDER", "")).lower()
        use_openai = self._provider == "openai" or (
            self._provider in {"", "auto"} and bool(os.getenv("OPENAI_API_KEY"))
        )
        use_anthropic = self._provider == "anthropic"
        use_codex = self._provider in {"", "codex", "auto"}
        self._openai: OpenAIResponsesClient | None = None
        self._anthropic: AnthropicResponsesClient | None = None
        self._codex: CodexCLIClient | None = None
        if use_openai:
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
            self._openai = OpenAIResponsesClient(timeout=timeout)
        if use_anthropic:
            if not (anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")):
                raise RuntimeError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
            self._anthropic = AnthropicResponsesClient(api_key=anthropic_api_key, timeout=timeout)
        if use_codex and not use_openai:
            self._codex = CodexCLIClient(timeout=max(timeout, 300))
    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        """Send a prompt and return the response."""
        if self._openai is not None:
            return self._openai.complete(system, user, model)
        if self._provider == "anthropic":
            if self._anthropic is None:
                raise RuntimeError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
            return self._anthropic.complete(system, user, model)
        if self._codex is not None:
            return self._codex.complete(system, user, model)
        return self._complete_with_claude_cli(system, user, model)

    def _complete_with_claude_cli(self, system: str, user: str, model: str) -> LLMResponse:
        mapped = self._MODEL_MAP.get(model, model)
        full_prompt = f"{system}\n\n---\n\n{user}"

        result = subprocess.run(
            [
                "claude", "-p", "--model", mapped,
                "--setting-sources=",   # don't load global settings → no MCP servers
                "--strict-mcp-config",  # only use explicitly configured MCP (none)
                "--permission-mode", "default",
            ],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=self._timeout,
            start_new_session=True,
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

    Provider env vars take precedence. Defaults to Codex CLI. Passing *api_key*
    preserves the older direct Anthropic behavior for legacy call sites.
    """
    provider = os.getenv("LLM_PROVIDER")
    if provider or os.getenv("OPENAI_API_KEY"):
        return ClaudeCodeClient(provider=provider)
    if api_key:
        return ClaudeCodeClient(provider="anthropic", anthropic_api_key=api_key)
    return ClaudeCodeClient()

"""Claude Code subscription client — routes LLM calls through `claude -p`.

Uses your Claude Code subscription instead of an API key.

Two adapters provided:
  ClaudeCodeClient  — complete(system, user, model) -> LLMResponse
                      used by EquityAnalyst and LLMProbabilityStrategy
  ClaudeCodeBackend — complete(prompt, *, model) -> str
                      satisfies the _Backend protocol in strategies/llm_probability/llm.py
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int   # estimated (claude -p doesn't report usage)
    output_tokens: int

    def cost_usd(self, model: str = "sonnet") -> float:
        # Subscription: billed to monthly plan, not per-token.
        # Return 0 so DailyBudget never blocks based on cost.
        return 0.0


class ClaudeCodeClient:
    """Call Claude via `claude -p` — uses your active Claude Code subscription.

    No API key required. The `model` parameter maps to Claude Code model IDs.

    Args:
        timeout: Max seconds to wait for a response (default 60).
    """

    _MODEL_MAP = {
        "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6":         "claude-sonnet-4-6",
        "haiku":                     "claude-haiku-4-5-20251001",
        "sonnet":                    "claude-sonnet-4-6",
    }

    def __init__(self, timeout: int = 60) -> None:
        self._timeout = timeout

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        """Send a prompt via `claude -p` and return the response."""
        mapped = self._MODEL_MAP.get(model, model)
        full_prompt = f"{system}\n\n---\n\n{user}"

        result = subprocess.run(
            ["claude", "-p", "--model", mapped, full_prompt],
            capture_output=True,
            text=True,
            timeout=self._timeout,
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

    def __init__(self, timeout: int = 60) -> None:
        self._client = ClaudeCodeClient(timeout=timeout)

    def complete(self, prompt: str, *, model: str = "sonnet") -> str:
        resp = self._client.complete(system="", user=prompt, model=model)
        return resp.content

    def complete_batch(self, prompts: list[str], *, model: str = "sonnet") -> list[str]:
        return [self.complete(p, model=model) for p in prompts]


def make_llm_client(api_key: str = "") -> "ClaudeCodeClient":
    """Return ClaudeCodeClient (subscription) when no API key, else AnthropicLLMClient."""
    if api_key:
        from equities.analysis.analyst import AnthropicLLMClient
        return AnthropicLLMClient(api_key)  # type: ignore[return-value]
    return ClaudeCodeClient()

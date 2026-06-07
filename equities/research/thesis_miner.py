"""ThesisMiner — LLM generates supply chain beneficiaries from structural theses."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from equities.analysis.analyst import LLMResponse


STRUCTURAL_THESES = [
    "AI inference compute scales 100x by 2027, requiring massive GPU, memory, power, and cooling infrastructure",
    "GLP-1 obesity drugs penetrate 15% of US adults by 2028, reshaping healthcare delivery and diagnostics",
    "US domestic semiconductor fabrication doubles by 2027 under CHIPS Act, benefiting equipment and materials",
    "AI-driven grid infrastructure spending reaches $500B over 5 years, requiring transformers, cables, power ICs",
    "Autonomous defense systems replace 20% of manned platforms by 2028, requiring AI chips, sensors, connectivity",
]

_SYSTEM = """You are a supply chain analyst identifying US-listed equities benefiting from a structural thesis.

Return:
- trunk: single most direct beneficiary (NYSE/NASDAQ ticker)
- level_1: 3-5 direct suppliers or close peers
- level_2: 3-5 suppliers to level_1 (one step deeper, less obvious)
- level_3: 3-5 suppliers to level_2 (deepest, most overlooked — prefer small/mid cap)

Rules: US tickers only. Each level less correlated to trunk than previous.

Return ONLY valid JSON. No markdown."""

_USER = """Thesis: {thesis}

Output:
{{
  "trunk": "TICKER",
  "level_1": ["T1","T2","T3"],
  "level_2": ["T4","T5","T6"],
  "level_3": ["T7","T8","T9"],
  "reasoning": "2-3 sentences"
}}"""


class LLMClient(Protocol):
    def complete(self, system: str, user: str, model: str) -> LLMResponse: ...


@dataclass
class ThesisResult:
    thesis: str
    trunk: str
    level_1: list[str] = field(default_factory=list)
    level_2: list[str] = field(default_factory=list)
    level_3: list[str] = field(default_factory=list)
    reasoning: str = ""

    def all_tickers(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for t in self.level_1 + self.level_2 + self.level_3:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result


class ThesisMiner:
    _SONNET = "strong"

    def __init__(self, llm: LLMClient | None = None) -> None:
        if llm is None:
            from core.claude_client import ClaudeCodeClient
            llm = ClaudeCodeClient()  # type: ignore[assignment]
        self._llm = llm

    def mine(self, thesis: str) -> ThesisResult:
        resp = self._llm.complete(_SYSTEM, _USER.format(thesis=thesis), self._SONNET)
        text = resp.content.strip()
        if text.startswith("```"):
            text = "\n".join(ln for ln in text.splitlines()[1:] if not ln.startswith("```"))
        data = json.loads(text)
        return ThesisResult(
            thesis=thesis,
            trunk=data.get("trunk", ""),
            level_1=data.get("level_1", []),
            level_2=data.get("level_2", []),
            level_3=data.get("level_3", []),
            reasoning=data.get("reasoning", ""),
        )

    def mine_all(self) -> list[ThesisResult]:
        results = []
        for thesis in STRUCTURAL_THESES:
            try:
                results.append(self.mine(thesis))
            except Exception:
                continue
        return results

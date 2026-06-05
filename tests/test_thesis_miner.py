"""Tests for ThesisMiner."""
from __future__ import annotations

import json

from equities.analysis.analyst import LLMResponse
from equities.research.thesis_miner import ThesisMiner


class _StubLLM:
    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({
                "trunk": "NVDA",
                "level_1": ["AVGO", "AMD", "TSM"],
                "level_2": ["MU", "ALAB", "MRVL"],
                "level_3": ["AMKR", "COHR", "ENTG"],
                "reasoning": "AI inference growth drives demand.",
            }),
            input_tokens=300,
            output_tokens=150,
        )


def test_thesis_miner_returns_result():
    miner = ThesisMiner(_StubLLM())
    result = miner.mine("AI inference scales 100x")
    assert result.trunk == "NVDA"
    assert "AMD" in result.level_1
    assert "MU" in result.level_2
    assert "COHR" in result.level_3


def test_thesis_miner_all_tickers_no_duplicates():
    miner = ThesisMiner(_StubLLM())
    result = miner.mine("AI inference scales 100x")
    all_t = result.all_tickers()
    assert len(all_t) == len(set(all_t))
    assert "AVGO" in all_t

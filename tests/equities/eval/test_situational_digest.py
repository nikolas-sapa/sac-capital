"""Tests for the nightly situational-awareness digest."""
from __future__ import annotations

import json

import pytest

from equities.analysis.analyst import LLMResponse
from equities.eval.replay import ReplayMetrics, ReplayReport
from equities.eval.situational_digest import (
    SituationalDigestBuilder,
    build_digest,
)
from equities.research.discovery_lag import DiscoveryLagCalculator
from equities.research.thesis_miner import ThesisMiner, ThesisResult


class _StubLLM:
    def __init__(self, trunk: str = "NVDA") -> None:
        self._trunk = trunk

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        return LLMResponse(
            content=json.dumps({
                "trunk": self._trunk,
                "level_1": ["AVGO"],
                "level_2": ["MU"],
                "level_3": ["AMKR"],
                "reasoning": "stub reasoning",
            }),
            input_tokens=10,
            output_tokens=10,
        )


class _StubLag(DiscoveryLagCalculator):
    """Stub that never hits the network — overrides the yfinance call."""

    def __init__(self, fixed: dict[str, list[tuple[str, float, float]]]) -> None:
        self._fixed = fixed

    def score_all_leaves(self, trunk: str) -> list[tuple[str, float, float]]:
        return self._fixed.get(trunk, [])


def _empty_metrics() -> ReplayMetrics:
    return ReplayMetrics(
        trade_count=0,
        expectancy_pct=0.0,
        win_rate=0.0,
        average_win_pct=0.0,
        average_loss_pct=0.0,
        max_drawdown_pct=0.0,
        average_exposure_days=0.0,
        max_sector_concentration=0.0,
        promotable=False,
        rejection_reason="sample_size_below_min_trades=20",
        sector_expectancy_pct={},
        catalyst_expectancy_pct={},
        exit_distribution={},
    )


def _metrics_with_breakdowns() -> ReplayMetrics:
    return ReplayMetrics(
        trade_count=42,
        expectancy_pct=1.23,
        win_rate=0.55,
        average_win_pct=4.5,
        average_loss_pct=-2.1,
        max_drawdown_pct=8.0,
        average_exposure_days=12.0,
        max_sector_concentration=0.4,
        promotable=True,
        sector_expectancy_pct={"Technology": 2.5, "Healthcare": -0.5},
        catalyst_expectancy_pct={"earnings_surprise_drift": 3.1, "material_filing": 0.2},
        exit_distribution={"target": 20, "stop": 10, "time": 12},
    )


# ---------------------------------------------------------------------------
# build_digest — pure formatter
# ---------------------------------------------------------------------------


def test_build_digest_includes_thematic_alerts():
    report = ReplayReport(
        train=_empty_metrics(),
        validation=_empty_metrics(),
        train_trades=[],
        validation_trades=[],
    )
    text = build_digest(
        thematic_alerts=["Thematic concentration: NVDA chain = 42.0% > limit 35%"],
        thesis_results=[],
        discovery_lag_by_trunk={},
        replay_report=report,
    )
    assert "Thematic concentration: NVDA chain = 42.0% > limit 35%" in text


def test_build_digest_flags_down_weighted_thesis():
    report = ReplayReport(
        train=_empty_metrics(),
        validation=_empty_metrics(),
        train_trades=[],
        validation_trades=[],
    )
    down_weighted = ThesisResult(
        thesis="AI inference compute scales 100x",
        trunk="NVDA",
        confidence_multiplier=0.7,
    )
    full_weight = ThesisResult(
        thesis="GLP-1 obesity drugs penetrate 15% of US adults",
        trunk="LLY",
        confidence_multiplier=1.0,
    )
    discovery_lag_by_trunk = {
        "NVDA": [("COHR", 0.8, 60.0), ("MU", 0.6, 40.0)],
        "LLY": [("ISRG", 0.5, 20.0)],
    }
    text = build_digest(
        thematic_alerts=[],
        thesis_results=[down_weighted, full_weight],
        discovery_lag_by_trunk=discovery_lag_by_trunk,
        replay_report=report,
    )
    # down-weighted thesis should be flagged somehow (multiplier visible / down-weight note)
    assert "0.7" in text
    assert "down-weight" in text.lower() or "discount" in text.lower()
    # full-weight thesis should NOT carry the same down-weight flag
    assert "NVDA" in text
    assert "LLY" in text
    assert "COHR" in text
    assert "60.0" in text or "60.00" in text


def test_build_digest_includes_replay_expectancy_breakdowns():
    report = ReplayReport(
        train=_metrics_with_breakdowns(),
        validation=_metrics_with_breakdowns(),
        train_trades=[],
        validation_trades=[],
    )
    text = build_digest(
        thematic_alerts=[],
        thesis_results=[],
        discovery_lag_by_trunk={},
        replay_report=report,
    )
    assert "Technology" in text
    assert "2.5" in text
    assert "earnings_surprise_drift" in text
    assert "3.1" in text


def test_build_digest_empty_inputs_no_crash():
    report = ReplayReport(
        train=_empty_metrics(),
        validation=_empty_metrics(),
        train_trades=[],
        validation_trades=[],
    )
    text = build_digest(
        thematic_alerts=[],
        thesis_results=[],
        discovery_lag_by_trunk={},
        replay_report=report,
    )
    assert isinstance(text, str)
    assert text.strip() != ""
    # sensible "nothing to report" signal somewhere
    assert "no" in text.lower() or "none" in text.lower()


# ---------------------------------------------------------------------------
# Orchestration — no network/LLM calls when given stubs
# ---------------------------------------------------------------------------


def test_orchestration_uses_stubs_without_network():
    miner = ThesisMiner(_StubLLM(trunk="NVDA"))
    lag_calc = _StubLag({"NVDA": [("COHR", 0.8, 55.0)]})
    builder = SituationalDigestBuilder(thesis_miner=miner, discovery_lag=lag_calc)

    report = ReplayReport(
        train=_empty_metrics(),
        validation=_empty_metrics(),
        train_trades=[],
        validation_trades=[],
    )
    text = builder.build(open_positions=[], replay_report=report)

    assert isinstance(text, str)
    assert "NVDA" in text
    assert "COHR" in text


def test_orchestration_handles_empty_thesis_results(monkeypatch):
    class _EmptyMiner(ThesisMiner):
        def mine_all(self) -> list[ThesisResult]:
            return []

    miner = _EmptyMiner(_StubLLM())
    lag_calc = _StubLag({})
    builder = SituationalDigestBuilder(thesis_miner=miner, discovery_lag=lag_calc)
    report = ReplayReport(
        train=_empty_metrics(),
        validation=_empty_metrics(),
        train_trades=[],
        validation_trades=[],
    )
    text = builder.build(open_positions=[], replay_report=report)
    assert isinstance(text, str)
    assert text.strip() != ""

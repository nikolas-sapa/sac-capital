import json
import sys
from datetime import date
from pathlib import Path

import pytest

import runner_research
from equities.research.backtest import BacktestReport
from equities.screen.supply_chain_lag_screen import SupplyChainLagCandidate
from runner_research import opportunity_score


def test_opportunity_score_rewards_fresh_lag_and_bottleneck():
    score = opportunity_score(
        lag_1y=-20.0,
        lag_3mo=30.0,
        lag_1mo=20.0,
        bottleneck=0.5,
    )

    assert score == 0.085


def test_opportunity_score_ignores_negative_lag():
    score = opportunity_score(
        lag_1y=-20.0,
        lag_3mo=-30.0,
        lag_1mo=-10.0,
        bottleneck=0.8,
    )

    assert score == 0.0


class FakeLag:
    def compute(self, trunk: str, ticker: str, period: str = "1y") -> float:
        return {"1y": 30.0, "3mo": 20.0, "1mo": 10.0}[period]

    def score_all_leaves(self, trunk: str):
        return [("AMAT", 0.6, 30.0)]


class FakeScreen:
    def __init__(self, prices, period: str = "1y") -> None:
        self.period = period

    def scan(self):
        return [_strategy_candidate()]

    def scan_history(self):
        return [_strategy_candidate()]


class FakeFeed:
    pass


def _strategy_candidate() -> SupplyChainLagCandidate:
    return SupplyChainLagCandidate(
        strategy="semi_bottleneck_catch_up",
        ticker="AMAT",
        trunk="AMD",
        entry_signal_at=date(2025, 1, 2),
        features={"opportunity_score": 0.2},
        entry_rule="test",
        exit_rule="test",
        risk_tags=[],
        thesis="test",
    )


def _report(trade_count: int = 1) -> BacktestReport:
    return BacktestReport(
        generated_at="2025-01-01T00:00:00+00:00",
        trade_count=trade_count,
        expectancy_pct=1.0,
        hit_rate=1.0,
        profit_factor=2.0,
        max_drawdown_pct=0.0,
        pnl_by_strategy={},
        pnl_by_trunk={},
        trades=[],
        actionable=trade_count > 0,
    )


def _patch_runner(monkeypatch, tmp_path: Path, report: BacktestReport) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["runner_research.py", "--static-only", "--strategy-backtest"])
    monkeypatch.setattr(runner_research, "DiscoveryLagCalculator", FakeLag)
    monkeypatch.setattr(runner_research, "SupplyChainLagScreen", FakeScreen)
    monkeypatch.setattr(runner_research, "run_backtest", lambda *args, **kwargs: report)
    import equities.data.prices

    monkeypatch.setattr(equities.data.prices, "YFinancePriceFeed", FakeFeed)


def test_strategy_backtest_writes_valid_json_and_jsonl(monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path, _report())

    runner_research.main()

    candidates = json.loads((tmp_path / "data/research_candidates.json").read_text())
    report = json.loads((tmp_path / "data/strategy_backtests.jsonl").read_text().strip())
    strategy = next(candidate for candidate in candidates if candidate.get("level") == "forward_paper_strategy")
    assert strategy["entry_signal_at"] == "2025-01-02"
    assert report["trade_count"] == 1


def test_candidate_write_failure_does_not_append_report(monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path, _report())
    appended = {"called": False}

    def fail_write(path, payload):
        raise RuntimeError("write failed")

    def record_append(path, report):
        appended["called"] = True

    monkeypatch.setattr(runner_research, "_write_json_atomic", fail_write)
    monkeypatch.setattr(runner_research, "append_backtest_report", record_append)

    with pytest.raises(RuntimeError, match="write failed"):
        runner_research.main()

    assert appended["called"] is False

import pytest
from datetime import datetime, timezone

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal
from orchestrator.performance import RollingStats, StrategyStats


def _market(cid: str = "m1") -> Market:
    return Market(
        condition_id=cid,
        question="Test?",
        outcomes=[
            Outcome("yes", "Yes", 0.4, 0.5),
            Outcome("no", "No", 0.4, 0.5),
        ],
        end_date=datetime.now(tz=timezone.utc),
        closed=False,
    )


def _fill(market: Market, stake: float = 10.0, fair_prob: float = 0.7) -> Fill:
    sig = Signal(
        market=market,
        token_id="yes",
        fair_prob=fair_prob,
        price=0.5,
        confidence=0.8,
        reason="test",
    )
    return Fill(
        signal=sig,
        stake=stake,
        shares=stake / 0.5,
        avg_price=0.5,
        mode="paper",
        timestamp=datetime.now(tz=timezone.utc),
    )


def test_no_resolved_returns_zero_stats(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    stats = StrategyStats(ledger).rolling("llm")
    assert stats.n_resolved == 0
    assert stats.win_rate == 0.0
    assert stats.roi == 0.0
    assert stats.expectancy == 0.0


def test_single_win(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    m = _market("m1")
    ledger.record(_fill(m, stake=10.0, fair_prob=0.8), strategy="llm")
    ledger.resolve("m1", "yes")
    stats = StrategyStats(ledger).rolling("llm")
    assert stats.n_resolved == 1
    assert stats.win_rate == pytest.approx(1.0)
    assert stats.roi > 0


def test_single_loss(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    m = _market("m1")
    ledger.record(_fill(m, stake=10.0, fair_prob=0.6), strategy="llm")
    ledger.resolve("m1", "no")  # "yes" token loses
    stats = StrategyStats(ledger).rolling("llm")
    assert stats.n_resolved == 1
    assert stats.win_rate == pytest.approx(0.0)
    assert stats.roi < 0
    assert stats.expectancy == pytest.approx(0.0)


def test_brier_is_zero_for_calibrated_forecast(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    m = _market("m1")
    ledger.record(_fill(m, fair_prob=1.0), strategy="x")
    ledger.resolve("m1", "yes")
    stats = StrategyStats(ledger).rolling("x")
    assert stats.brier_score == pytest.approx(0.0)


def test_window_limits_rows(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    for i in range(5):
        m = _market(f"m{i}")
        ledger.record(_fill(m), strategy="s")
        ledger.resolve(f"m{i}", "yes")
    stats = StrategyStats(ledger).rolling("s", window=2)
    assert stats.n_resolved == 2


def test_strategy_isolation(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    m = _market("m1")
    ledger.record(_fill(m, stake=5.0), strategy="a")
    ledger.resolve("m1", "yes")
    m2 = _market("m2")
    ledger.record(_fill(m2, stake=5.0), strategy="b")
    ledger.resolve("m2", "no")
    stats_a = StrategyStats(ledger).rolling("a")
    stats_b = StrategyStats(ledger).rolling("b")
    assert stats_a.win_rate == 1.0
    assert stats_b.win_rate == 0.0

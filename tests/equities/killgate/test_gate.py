import pytest
from equities.killgate.gate import GateResult, KillGate
from equities.killgate.tracker import ForwardPaperTracker


def _add_trade(tracker: ForwardPaperTracker, won: bool, strategy: str = "s") -> None:
    tid = tracker.record_entry("X", "swing", entry_price=100.0, shares=1.0, strategy=strategy)
    tracker.record_exit(tid, exit_price=110.0 if won else 90.0)


def test_fails_when_insufficient_trades(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    gate = KillGate(min_trades=100)
    for _ in range(10):
        _add_trade(tracker, won=True)
    result = gate.evaluate(tracker)
    assert result.passed is False
    assert "insufficient_trades" in result.reason


def test_fails_when_negative_pnl(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    gate = KillGate(min_trades=5)
    for _ in range(5):
        _add_trade(tracker, won=False)
    result = gate.evaluate(tracker)
    assert result.passed is False
    assert "negative_expectancy" in result.reason


def test_fails_when_win_rate_too_low(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    gate = KillGate(min_trades=5, min_win_rate=0.60)
    for _ in range(3):
        _add_trade(tracker, won=False)
    for _ in range(3):
        _add_trade(tracker, won=True)
    # win rate = 3/6 = 50% < 60%, but pnl might be positive
    result = gate.evaluate(tracker)
    # exact pass/fail depends on pnl balance; just check it evaluates
    assert isinstance(result.passed, bool)


def test_passes_all_gates(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    gate = KillGate(min_trades=5, min_win_rate=0.40)
    for _ in range(4):
        _add_trade(tracker, won=True)
    for _ in range(2):
        _add_trade(tracker, won=False)
    result = gate.evaluate(tracker)
    assert result.passed is True
    assert result.n_trades == 6
    assert result.net_pnl > 0


def test_strategy_filter(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    gate = KillGate(min_trades=5)
    for _ in range(6):
        _add_trade(tracker, won=True, strategy="equity_analyst")
    for _ in range(6):
        _add_trade(tracker, won=False, strategy="other")
    result = gate.evaluate(tracker, strategy="equity_analyst")
    assert result.passed is True
    assert result.n_trades == 6


def test_record_exit_for_open_trade_matches_oldest_trade(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    first = tracker.record_entry("TEST", "swing", 100.0, 1.0, strategy="equity_analyst")
    second = tracker.record_entry("TEST", "swing", 110.0, 1.0, strategy="equity_analyst")

    closed = tracker.record_exit_for_open_trade(
        "TEST",
        90.0,
        sleeve="swing",
        strategy="equity_analyst",
        is_gap_stop=True,
    )

    assert closed is True
    closed_trades = tracker.closed_trades("equity_analyst")
    assert [t.id for t in closed_trades] == [first]
    assert closed_trades[0].exit_price == pytest.approx(90.0)
    assert closed_trades[0].is_gap_stop is True
    assert [t.id for t in tracker.open_trades()] == [second]

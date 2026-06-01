from datetime import date, timedelta

import pytest

from equities.improve.promoter import AutoPromoter
from equities.improve.variants import ParameterVariant
from equities.killgate.gate import KillGate
from equities.killgate.tracker import ForwardPaperTracker


def _variant(name: str = "v1") -> ParameterVariant:
    return ParameterVariant(name=name, params={"threshold": 0.08})


def _add_winning_trades(tracker: ForwardPaperTracker, n: int, strategy: str = "s") -> None:
    for _ in range(n):
        tid = tracker.record_entry("X", "swing", 100.0, 1.0, strategy=strategy)
        tracker.record_exit(tid, 115.0)  # winning trade


def test_promote_passes_all_gates(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    _add_winning_trades(tracker, 10, "s")

    gate = KillGate(min_trades=5, min_win_rate=0.40)
    promoter = AutoPromoter(gate=gate, cooldown_days=0, min_live_paper_trades=0)

    promoted = promoter.try_promote(_variant(), tracker, live_paper_trade_count=5)
    assert promoted is True
    assert promoter.current_params() == {"threshold": 0.08}


def test_promote_blocked_by_kill_gate(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    # only 2 trades < min_trades=5
    _add_winning_trades(tracker, 2)
    gate = KillGate(min_trades=5)
    promoter = AutoPromoter(gate=gate, cooldown_days=0, min_live_paper_trades=0)
    assert promoter.try_promote(_variant(), tracker, live_paper_trade_count=5) is False


def test_promote_blocked_by_min_live_paper(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    _add_winning_trades(tracker, 10)
    gate = KillGate(min_trades=5)
    promoter = AutoPromoter(gate=gate, cooldown_days=0, min_live_paper_trades=20)
    # only 5 live paper trades < 20
    assert promoter.try_promote(_variant(), tracker, live_paper_trade_count=5) is False


def test_promote_blocked_by_cooldown(tmp_path, monkeypatch):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    _add_winning_trades(tracker, 10)
    gate = KillGate(min_trades=5)
    promoter = AutoPromoter(gate=gate, cooldown_days=14, min_live_paper_trades=0)

    # First promotion
    promoter.try_promote(_variant("v1"), tracker, live_paper_trade_count=0)

    # Second attempt immediately → blocked by cooldown
    result = promoter.try_promote(_variant("v2"), tracker, live_paper_trade_count=0)
    assert result is False


def test_rollback_reverts_to_previous(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    _add_winning_trades(tracker, 20)
    gate = KillGate(min_trades=5)
    promoter = AutoPromoter(gate=gate, cooldown_days=0, min_live_paper_trades=0)

    promoter.try_promote(_variant("v1"), tracker, live_paper_trade_count=0)
    promoter.try_promote(_variant("v2"), tracker, live_paper_trade_count=0)
    assert promoter.current_params() == {"threshold": 0.08}

    rolled_back = promoter.rollback()
    assert rolled_back is True
    assert promoter.promotion_history()[-1].variant.name == "v1"


def test_rollback_fails_with_one_promotion(tmp_path):
    tracker = ForwardPaperTracker(tmp_path / "fp.db")
    _add_winning_trades(tracker, 10)
    gate = KillGate(min_trades=5)
    promoter = AutoPromoter(gate=gate, cooldown_days=0, min_live_paper_trades=0)
    promoter.try_promote(_variant(), tracker, live_paper_trade_count=0)
    assert promoter.rollback() is False


def test_no_current_params_before_promotion():
    promoter = AutoPromoter()
    assert promoter.current_params() is None

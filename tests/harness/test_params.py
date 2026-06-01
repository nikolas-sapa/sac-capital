import pytest
from datetime import datetime, timezone

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal
from harness.params import ParamStore, RollbackGuard


def test_get_returns_none_when_unset(tmp_path):
    store = ParamStore(tmp_path / "p.db")
    assert store.get("llm", "min_edge") is None


def test_set_and_get(tmp_path):
    store = ParamStore(tmp_path / "p.db")
    store.set("llm", "min_edge", 0.08, reason="initial")
    assert store.get("llm", "min_edge") == pytest.approx(0.08)


def test_set_overwrites_active_value(tmp_path):
    store = ParamStore(tmp_path / "p.db")
    store.set("llm", "min_edge", 0.08)
    store.set("llm", "min_edge", 0.10)
    assert store.get("llm", "min_edge") == pytest.approx(0.10)


def test_history_shows_all_versions(tmp_path):
    store = ParamStore(tmp_path / "p.db")
    store.set("llm", "min_edge", 0.08)
    store.set("llm", "min_edge", 0.10)
    h = store.history("llm", "min_edge")
    assert len(h) == 2
    assert h[0]["active"] == 1  # newest is active
    assert h[1]["active"] == 0


def test_rollback_restores_previous(tmp_path):
    store = ParamStore(tmp_path / "p.db")
    store.set("llm", "min_edge", 0.08)
    store.set("llm", "min_edge", 0.10)
    result = store.rollback("llm", "min_edge")
    assert result is True
    assert store.get("llm", "min_edge") == pytest.approx(0.08)


def test_rollback_returns_false_when_no_history(tmp_path):
    store = ParamStore(tmp_path / "p.db")
    store.set("llm", "min_edge", 0.08)
    assert store.rollback("llm", "min_edge") is False


def test_stores_json_types(tmp_path):
    store = ParamStore(tmp_path / "p.db")
    store.set("s", "bins", [1, 2, 3])
    assert store.get("s", "bins") == [1, 2, 3]
    store.set("s", "cfg", {"a": True})
    assert store.get("s", "cfg") == {"a": True}


def _make_ledger(tmp_path: object) -> Ledger:
    return Ledger(tmp_path / "l.db")  # type: ignore[arg-type]


def _fill(ledger: Ledger, cid: str, won: bool, stake: float = 10.0) -> None:
    m = Market(
        condition_id=cid,
        question="Q?",
        outcomes=[
            Outcome("yes", "Yes", 0.4, 0.5),
            Outcome("no", "No", 0.4, 0.5),
        ],
        end_date=datetime.now(tz=timezone.utc),
        closed=False,
    )
    sig = Signal(market=m, token_id="yes", fair_prob=0.7, price=0.5, confidence=0.7, reason="t")
    fill = Fill(signal=sig, stake=stake, shares=stake/0.5, avg_price=0.5,
                mode="paper", timestamp=datetime.now(tz=timezone.utc))
    ledger.record(fill, strategy="llm")
    ledger.resolve(cid, "yes" if won else "no")


def test_rollback_guard_triggers_on_degradation(tmp_path):
    ledger = _make_ledger(tmp_path)
    store = ParamStore(tmp_path / "p.db")

    # Pre-change: 10 wins
    for i in range(5):
        _fill(ledger, f"pre{i}", won=True)

    store.set("llm", "min_edge", 0.08)
    store.set("llm", "min_edge", 0.10)  # simulated change

    # Post-change: 5 losses (badly degraded)
    for i in range(5):
        _fill(ledger, f"post{i}", won=False, stake=10.0)

    guard = RollbackGuard(store, ledger, threshold=0.1)
    rolled_back = guard.check_and_rollback("llm", "min_edge")
    assert rolled_back is True
    assert store.get("llm", "min_edge") == pytest.approx(0.08)

import pytest
from orchestrator.allocator import allocate
from orchestrator.performance import RollingStats


def _stats(name: str, expectancy: float = 0.0, n: int = 10) -> RollingStats:
    return RollingStats(
        strategy=name,
        n_resolved=n,
        win_rate=0.5,
        roi=expectancy * 2,  # approximate
        brier_score=0.2,
        expectancy=expectancy,
    )


def test_empty_stats_returns_empty():
    assert allocate(1000.0, {}) == {}


def test_floor_assigned_to_new_strategy():
    stats = {"llm": _stats("llm", n=0)}
    alloc = allocate(1000.0, stats, floor_pct=0.05)
    assert alloc["llm"] == pytest.approx(50.0)


def test_positive_expectancy_gets_more_than_floor():
    stats = {
        "good": _stats("good", expectancy=0.10),
        "new": _stats("new", n=0, expectancy=0.0),
    }
    alloc = allocate(1000.0, stats, floor_pct=0.05)
    assert alloc["good"] > alloc["new"]


def test_ceiling_enforced():
    stats = {"dominant": _stats("dominant", expectancy=0.9, n=100)}
    alloc = allocate(1000.0, stats, floor_pct=0.05, ceiling_pct=0.50)
    assert alloc["dominant"] <= 500.0


def test_budgets_sum_to_at_most_bankroll():
    stats = {
        "a": _stats("a", expectancy=0.1),
        "b": _stats("b", expectancy=0.05),
        "c": _stats("c", n=0),
    }
    alloc = allocate(1000.0, stats)
    assert sum(alloc.values()) <= 1000.0 + 1e-6


def test_negative_expectancy_gets_only_floor():
    stats = {"bad": _stats("bad", expectancy=0.0)}
    alloc = allocate(1000.0, stats, floor_pct=0.05)
    assert alloc["bad"] == pytest.approx(50.0)


def test_floor_scale_when_exceeds_bankroll():
    # 3 strategies × 40% floor = 120% > bankroll → scale down
    stats = {
        "a": _stats("a"),
        "b": _stats("b"),
        "c": _stats("c"),
    }
    alloc = allocate(1000.0, stats, floor_pct=0.40)
    total = sum(alloc.values())
    assert total == pytest.approx(1000.0, rel=1e-6)

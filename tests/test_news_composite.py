"""Tests for CompositeNewsProvider."""
from __future__ import annotations

from equities.data.news_composite import CompositeNewsProvider


class _StubProvider:
    def __init__(self, items: list[str]) -> None:
        self._items = items

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        return self._items[:limit]


def test_composite_merges_and_deduplicates():
    p1 = _StubProvider(["Apple beats estimates", "Apple raises guidance"])
    p2 = _StubProvider(["Apple beats estimates", "Apple new product launch"])
    comp = CompositeNewsProvider([p1, p2])
    result = comp.headlines("AAPL", limit=10)
    assert len(result) == 3
    assert "Apple beats estimates" in result
    assert "Apple new product launch" in result


def test_composite_respects_limit():
    p1 = _StubProvider([f"headline_{i}" for i in range(10)])
    p2 = _StubProvider([f"other_{i}" for i in range(10)])
    comp = CompositeNewsProvider([p1, p2])
    assert len(comp.headlines("AAPL", limit=5)) == 5


def test_composite_handles_empty_provider():
    p1 = _StubProvider([])
    p2 = _StubProvider(["Real news"])
    comp = CompositeNewsProvider([p1, p2])
    assert comp.headlines("AAPL", limit=10) == ["Real news"]

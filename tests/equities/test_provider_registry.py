from __future__ import annotations

from equities.data.news_composite import CompositeNewsProvider
from equities.data.registry import ProviderRegistry


class Provider:
    def __init__(self, name: str, items: list[str] | None = None, fail: bool = False) -> None:
        self.name = name
        self._items = items or []
        self._fail = fail

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        if self._fail:
            raise RuntimeError(f"{self.name} failed")
        return self._items[:limit]


def test_provider_registry_orders_by_priority_and_tracks_health():
    registry = ProviderRegistry()
    slow = Provider("slow")
    fast = Provider("fast")

    registry.register("news", slow, priority=20)
    registry.register("news", fast, priority=10)
    registry.record_success(fast)
    registry.record_failure(slow, RuntimeError("timeout"))

    assert registry.providers_for("news") == [fast, slow]
    health = {item.name: item for item in registry.health()}
    assert health["fast"].success_count == 1
    assert health["slow"].failure_count == 1
    assert health["slow"].last_error == "timeout"


def test_composite_news_records_failure_and_preserves_fallback_order():
    registry = ProviderRegistry()
    failing = Provider("failing", fail=True)
    fallback = Provider("fallback", items=["Real news"])
    failures = 0

    def record_failure() -> None:
        nonlocal failures
        failures += 1

    composite = CompositeNewsProvider(
        [failing, fallback],
        failure_callback=record_failure,
        registry=registry,
    )

    assert composite.headlines("AAPL", limit=5) == ["Real news"]
    assert failures == 1
    health = {item.name: item for item in registry.health()}
    assert health["failing"].failure_count == 1
    assert health["fallback"].success_count == 1

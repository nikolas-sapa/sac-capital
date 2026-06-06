from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from equities.data.health import ProviderHealth


@dataclass(frozen=True)
class _ProviderEntry:
    kind: str
    provider: Any
    priority: int
    name: str


class ProviderRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, list[_ProviderEntry]] = {}
        self._health: dict[int, ProviderHealth] = {}

    def register(self, kind: str, provider: Any, priority: int) -> None:
        entry = _ProviderEntry(
            kind=kind,
            provider=provider,
            priority=priority,
            name=_provider_name(provider),
        )
        self._entries.setdefault(kind, []).append(entry)
        self._entries[kind].sort(key=lambda item: item.priority)
        self._health.setdefault(
            id(provider),
            ProviderHealth(
                name=entry.name,
                kind=kind,
                success_count=0,
                failure_count=0,
                last_success_at=None,
                last_failure_at=None,
                last_error=None,
            ),
        )

    def providers_for(self, kind: str) -> list[Any]:
        return [entry.provider for entry in self._entries.get(kind, [])]

    def record_success(self, provider: Any) -> None:
        current = self._health.get(id(provider))
        if current is None:
            return
        self._health[id(provider)] = ProviderHealth(
            name=current.name,
            kind=current.kind,
            success_count=current.success_count + 1,
            failure_count=current.failure_count,
            last_success_at=_now(),
            last_failure_at=current.last_failure_at,
            last_error=current.last_error,
        )

    def record_failure(self, provider: Any, exc: Exception) -> None:
        current = self._health.get(id(provider))
        if current is None:
            return
        self._health[id(provider)] = ProviderHealth(
            name=current.name,
            kind=current.kind,
            success_count=current.success_count,
            failure_count=current.failure_count + 1,
            last_success_at=current.last_success_at,
            last_failure_at=_now(),
            last_error=str(exc),
        )

    def health(self) -> list[ProviderHealth]:
        return sorted(self._health.values(), key=lambda item: (item.kind, item.name))

    def failures(self) -> list[ProviderHealth]:
        return [item for item in self.health() if item.failure_count > 0]


def _provider_name(provider: Any) -> str:
    return getattr(provider, "name", "") or provider.__class__.__name__


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()

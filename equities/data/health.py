from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderHealth:
    name: str
    kind: str
    success_count: int
    failure_count: int
    last_success_at: str | None
    last_failure_at: str | None
    last_error: str | None

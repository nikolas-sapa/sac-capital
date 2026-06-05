"""Composite news provider — aggregates multiple providers and deduplicates."""
from __future__ import annotations

from typing import Protocol


class NewsProvider(Protocol):
    def headlines(self, ticker: str, limit: int = 15) -> list[str]: ...


class CompositeNewsProvider:
    """Aggregate headlines from multiple providers, deduplicating by exact match."""

    def __init__(self, providers: list[NewsProvider]) -> None:
        self._providers = providers

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for provider in self._providers:
            try:
                items = provider.headlines(ticker, limit=limit)
            except Exception:
                items = []
            for item in items:
                normalized = item.strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    merged.append(normalized)
                if len(merged) >= limit:
                    break
            if len(merged) >= limit:
                break
        return merged[:limit]

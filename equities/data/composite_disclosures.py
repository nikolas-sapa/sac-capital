"""Merge multiple politician-disclosure providers behind one .fetch() interface.

Lets the screener consume House + Senate (+ future) sources as a single feed.
Never raises: a failing or blocked source contributes zero trades and surfaces
its error, while healthy sources still return their trades.
"""
from __future__ import annotations

from datetime import datetime, timezone

from equities.data.politician_disclosures import DisclosureFetch


class CompositeDisclosureProvider:
    """Fan out to several providers and concatenate their trades."""

    def __init__(self, providers: list) -> None:
        self._providers = list(providers)

    def fetch(self) -> DisclosureFetch:
        trades = []
        sources: list[str] = []
        errors: list[str] = []
        for p in self._providers:
            try:
                result = p.fetch()
            except Exception as exc:  # belt-and-suspenders: providers shouldn't raise
                errors.append(f"{type(p).__name__}: {exc}")
                continue
            trades.extend(result.trades)
            if result.source and result.source != "none":
                sources.append(result.source)
            if result.error:
                errors.append(result.error)
        return DisclosureFetch(
            trades=trades,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            source="+".join(sources) if sources else "none",
            error="; ".join(errors) if errors else None,
        )

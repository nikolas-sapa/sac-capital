"""Politician STOCK Act disclosure screener — paper research funnel.

Scores recent congressional buy disclosures into CandidateEvents that flow
into the existing analyst stage. Discovery is intersected with the scanned
universe in slice 1 (real Instrument objects only).

# ponytail: 4-factor deterministic score (recency/cluster/repeat/size).
# committee/policy/sector-catalyst factors need joined data — Phase 2.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from core.assets.instrument import Instrument
from equities.screen.event_screen import CandidateEvent, EventType


class DisclosureProvider(Protocol):
    def fetch(self): ...  # returns DisclosureFetch


@dataclass(frozen=True)
class _TickerScore:
    urgency: float
    evidence: str


class PoliticianScreen:
    def __init__(self, provider: DisclosureProvider, *, lookback_days: int = 30,
                 min_amount: int = 15000) -> None:
        self._provider = provider
        self._lookback = lookback_days
        self._min_amount = min_amount

    def scan(self, universe: list[Instrument]) -> list[CandidateEvent]:
        by_ticker = {inst.ticker.upper(): inst for inst in universe}
        fetch = self._provider.fetch()
        today = date.today()

        grouped: dict[str, list] = defaultdict(list)
        for t in fetch.trades:
            if t.transaction_type != "buy":
                continue
            if t.ticker not in by_ticker:
                continue
            if t.date_filed is None or (today - t.date_filed).days > self._lookback:
                continue
            grouped[t.ticker].append(t)

        candidates: list[CandidateEvent] = []
        for ticker, trades in grouped.items():
            scored = self._score(trades, today)
            if scored is None:
                continue
            candidates.append(CandidateEvent(
                instrument=by_ticker[ticker],
                event_type=EventType.POLITICIAN_DISCLOSURE,
                evidence=scored.evidence,
                urgency=round(scored.urgency, 4),
                days_to_event=None,
            ))

        candidates.sort(key=lambda c: c.urgency, reverse=True)
        return candidates

    def _score(self, trades: list, today: date) -> _TickerScore | None:
        if not trades:
            return None
        if all(t.amount_max < self._min_amount for t in trades):
            return None

        freshest_lag = min((today - t.date_filed).days for t in trades)
        recency = max(0.0, 1.0 - freshest_lag / self._lookback)
        distinct = len({t.politician for t in trades})
        cluster = min(distinct / 3.0, 1.0)
        repeat = min(len(trades) / 3.0, 1.0)
        size = min(max(t.amount_max for t in trades) / 250_000.0, 1.0)

        urgency = 0.35 * recency + 0.30 * cluster + 0.20 * repeat + 0.15 * size
        names = ", ".join(sorted({t.politician for t in trades})[:3])
        evidence = (
            f"POL buy: {len(trades)} filing(s), {distinct} politician(s) "
            f"[{names}], freshest {freshest_lag}d ago, "
            f"≤${max(t.amount_max for t in trades):,}"
        )
        return _TickerScore(urgency=urgency, evidence=evidence)

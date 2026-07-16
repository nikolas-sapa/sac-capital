"""Tests for the two wiring gaps in runner_equities.py: the bottleneck/supply-chain-lag
screen conversion into CandidateEvent, and the core-universe dedup-union helper.
"""
from __future__ import annotations

from datetime import date

from core.assets.instrument import CapTier, Instrument
from equities.screen.event_screen import EventType
from equities.screen.supply_chain_lag_screen import (
    STRATEGY_SEMI_BOTTLENECK,
    SupplyChainLagCandidate,
)
from runner_equities import DEFAULT_SWING_UNIVERSE, _dedup_union, _lag_candidate_to_event


def _make_candidate(ticker: str = "MU", opportunity_score: float = 0.42) -> SupplyChainLagCandidate:
    return SupplyChainLagCandidate(
        strategy=STRATEGY_SEMI_BOTTLENECK,
        ticker=ticker,
        trunk="NVDA",
        entry_signal_at=date(2026, 1, 15),
        features={
            "lag_1y": 30.0,
            "lag_3mo": 12.0,
            "lag_1mo": -1.0,
            "bottleneck_score": 0.6,
            "opportunity_score": opportunity_score,
            "stop_loss": 90.0,
            "take_profit": 110.0,
            "max_holding_days": 21,
        },
        entry_rule="weekly close after lag signal",
        exit_rule="+18%, ATR stop, 21 trading days",
        risk_tags=["crowding"],
        thesis="MU is a bottleneck supplier lagging NVDA despite upstream strength.",
    )


def test_lag_candidate_to_event_has_supply_chain_lag_type_and_bounded_urgency():
    candidate = _make_candidate()
    event = _lag_candidate_to_event(candidate)

    assert event.event_type == EventType.SUPPLY_CHAIN_LAG
    assert 0.0 <= event.urgency <= 1.0
    assert event.urgency == round(candidate.opportunity_score, 4)
    assert "MU" in event.evidence
    assert "lag1y=30%" in event.evidence
    assert "bottleneck=0.60" in event.evidence


def test_lag_candidate_to_event_resolves_known_ticker_from_universe():
    candidate = _make_candidate(ticker="MU")
    event = _lag_candidate_to_event(candidate, DEFAULT_SWING_UNIVERSE)

    expected = next(i for i in DEFAULT_SWING_UNIVERSE if i.ticker == "MU")
    assert event.instrument == expected
    assert event.instrument.cap_tier == CapTier.LARGE


def test_lag_candidate_to_event_falls_back_to_synthetic_instrument_for_unknown_ticker():
    candidate = _make_candidate(ticker="ZZZZ")
    event = _lag_candidate_to_event(candidate, DEFAULT_SWING_UNIVERSE)

    assert event.instrument.ticker == "ZZZZ"
    assert event.instrument.cap_tier == CapTier.MID


def test_lag_candidate_to_event_urgency_is_clamped_to_one():
    candidate = _make_candidate(opportunity_score=1.5)
    event = _lag_candidate_to_event(candidate)

    assert event.urgency == 1.0


def test_dedup_union_removes_duplicates_and_preserves_order():
    a = Instrument("AAA", "Alpha", "NASDAQ", CapTier.LARGE)
    b = Instrument("BBB", "Beta", "NASDAQ", CapTier.MID)
    c = Instrument("AAA", "Alpha Duplicate", "NASDAQ", CapTier.LARGE)
    d = Instrument("CCC", "Gamma", "NASDAQ", CapTier.SMALL)

    result = _dedup_union([a, b], [c, d])

    assert [i.ticker for i in result] == ["AAA", "BBB", "CCC"]
    # first occurrence wins
    assert result[0] is a


def test_dedup_union_empty_lists():
    assert _dedup_union([], []) == []

"""Tests for NarrativeGapDetector."""
from __future__ import annotations

from equities.research.narrative_gap import NarrativeGapDetector


def test_ai_vocabulary_in_industrial_sector_flagged():
    detector = NarrativeGapDetector()
    headlines = [
        "Eaton lands $200M AI data center power deal",
        "Record backlog driven by hyperscaler demand",
        "AI infrastructure buildout fuels transformer orders",
    ]
    score = detector.detect("ETN", headlines, sector="Industrials", analyst_count=30)
    assert score > 0.5


def test_ai_vocab_in_tech_sector_not_flagged():
    detector = NarrativeGapDetector()
    headlines = ["NVIDIA announces new AI chip", "NVIDIA data center revenue triples"]
    score = detector.detect("NVDA", headlines, sector="Semiconductors", analyst_count=60)
    assert score < 0.3


def test_no_headlines_returns_zero():
    detector = NarrativeGapDetector()
    assert detector.detect("XYZ", [], "Energy", analyst_count=5) == 0.0


def test_low_coverage_amplifies_score():
    detector = NarrativeGapDetector()
    hl = ["AI-powered automation drives record orders"]
    low = detector.detect("KLIC", hl, "Semiconductors", analyst_count=3)
    high = detector.detect("KLIC", hl, "Semiconductors", analyst_count=50)
    assert low > high

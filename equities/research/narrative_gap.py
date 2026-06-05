"""Narrative gap detector — surface stocks where news suggests a new story
not yet reflected in analyst consensus."""
from __future__ import annotations

_NEW_ECONOMY_TERMS: set[str] = {
    "ai", "artificial intelligence", "data center", "automation",
    "robotics", "autonomous", "machine learning", "llm", "gpu",
    "backlog", "sold out", "record orders", "capacity constrained",
    "hyperscaler", "inference", "generative", "foundation model",
    "power demand", "grid upgrade", "nuclear", "energy transition",
}

_HIGH_TECH_SECTORS: set[str] = {
    "semiconductors", "technology", "software",
    "information technology", "communication services",
}


class NarrativeGapDetector:
    """Score 0.0-1.0. Above 0.5 = meaningful narrative gap."""

    def detect(
        self,
        ticker: str,  # noqa: ARG002
        headlines: list[str],
        sector: str,
        analyst_count: int,
    ) -> float:
        if not headlines:
            return 0.0

        all_text = " ".join(h.lower() for h in headlines)
        matched = sum(1 for t in _NEW_ECONOMY_TERMS if t in all_text)
        vocab_score = min(1.0, matched / 4.0)
        if vocab_score == 0.0:
            return 0.0

        is_high_tech = any(s in sector.lower() for s in _HIGH_TECH_SECTORS)
        sector_multiplier = 0.3 if is_high_tech else 1.0

        if analyst_count <= 3:
            coverage_amp = 1.5
        elif analyst_count <= 8:
            coverage_amp = 1.2
        elif analyst_count <= 20:
            coverage_amp = 1.0
        else:
            coverage_amp = 0.7

        return round(min(1.0, vocab_score * sector_multiplier * coverage_amp), 4)

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SentimentEvidence:
    source: str
    text: str
    polarity: str
    confidence: float


@dataclass(frozen=True)
class SentimentSnapshot:
    ticker: str
    bullish_count: int
    bearish_count: int
    neutral_count: int
    net_score: float
    confidence: float
    evidence: list[SentimentEvidence]
    summary: str


_BULLISH_TERMS = {
    "approval",
    "approved",
    "beat",
    "beats",
    "breakout",
    "contract",
    "growth",
    "guidance raise",
    "margin expansion",
    "partnership",
    "profitable",
    "raises",
    "record revenue",
    "upgrade",
    "upgraded",
}

_BEARISH_TERMS = {
    "bankruptcy",
    "cut guidance",
    "delay",
    "delayed",
    "dilution",
    "downgrade",
    "downgraded",
    "guidance cut",
    "lawsuit",
    "loss widens",
    "miss",
    "misses",
    "probe",
    "recall",
    "sec investigation",
}


def build_headline_sentiment_snapshot(
    ticker: str,
    headlines: list[str],
    source: str = "headlines",
    max_evidence: int = 10,
) -> SentimentSnapshot:
    seen: set[str] = set()
    evidence: list[SentimentEvidence] = []
    bullish = bearish = neutral = 0
    for headline in headlines:
        text = " ".join(str(headline).split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        polarity, confidence = classify_sentiment(text)
        if polarity == "bullish":
            bullish += 1
        elif polarity == "bearish":
            bearish += 1
        else:
            neutral += 1
        evidence.append(
            SentimentEvidence(
                source=source,
                text=text,
                polarity=polarity,
                confidence=confidence,
            )
        )

    scored = [item for item in evidence if item.polarity != "neutral"]
    total = bullish + bearish + neutral
    net_score = ((bullish - bearish) / total) if total else 0.0
    confidence = _snapshot_confidence(net_score, len(scored), total)
    summary = _summary(ticker, bullish, bearish, neutral, net_score)
    return SentimentSnapshot(
        ticker=ticker.upper(),
        bullish_count=bullish,
        bearish_count=bearish,
        neutral_count=neutral,
        net_score=round(net_score, 4),
        confidence=confidence,
        evidence=evidence[:max_evidence],
        summary=summary,
    )


def classify_sentiment(text: str) -> tuple[str, float]:
    lowered = text.lower()
    bullish_hits = sum(1 for term in _BULLISH_TERMS if term in lowered)
    bearish_hits = sum(1 for term in _BEARISH_TERMS if term in lowered)
    if bullish_hits > bearish_hits:
        return "bullish", min(0.95, 0.55 + bullish_hits * 0.12)
    if bearish_hits > bullish_hits:
        return "bearish", min(0.95, 0.55 + bearish_hits * 0.12)
    return "neutral", 0.4


def _snapshot_confidence(net_score: float, scored_count: int, total_count: int) -> float:
    if total_count == 0:
        return 0.0
    confidence = 0.3 + min(scored_count, 10) * 0.04 + abs(net_score) * 0.3
    return round(min(0.9, confidence), 4)


def _summary(ticker: str, bullish: int, bearish: int, neutral: int, net_score: float) -> str:
    if bullish + bearish + neutral == 0:
        return f"{ticker.upper()}: no sentiment evidence."
    if net_score > 0.2:
        direction = "bullish"
    elif net_score < -0.2:
        direction = "bearish"
    else:
        direction = "mixed"
    return (
        f"{ticker.upper()}: {direction} headline sentiment "
        f"({bullish} bullish, {bearish} bearish, {neutral} neutral)."
    )

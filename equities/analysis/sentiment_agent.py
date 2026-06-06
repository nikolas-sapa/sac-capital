from __future__ import annotations

from equities.data.sentiment import SentimentSnapshot


def format_sentiment_snapshot(snapshot: SentimentSnapshot) -> str:
    if not snapshot.evidence:
        return ""
    bullish = [item for item in snapshot.evidence if item.polarity == "bullish"]
    bearish = [item for item in snapshot.evidence if item.polarity == "bearish"]
    neutral = [item for item in snapshot.evidence if item.polarity == "neutral"]
    lines = [
        f"Net score: {snapshot.net_score:+.2f}",
        f"Confidence: {snapshot.confidence:.2f}",
        f"Summary: {snapshot.summary}",
    ]
    if bullish:
        lines.append("Bullish evidence:")
        lines.extend(f"- {_shorten(item.text, 150)}" for item in bullish[:3])
    if bearish:
        lines.append("Bearish evidence:")
        lines.extend(f"- {_shorten(item.text, 150)}" for item in bearish[:3])
    if not bullish and not bearish and neutral:
        lines.append("Neutral evidence:")
        lines.extend(f"- {_shorten(item.text, 150)}" for item in neutral[:3])
    return "\n".join(lines)


def _shorten(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."

from __future__ import annotations

from equities.analysis.sentiment_agent import format_sentiment_snapshot
from equities.data.sentiment import build_headline_sentiment_snapshot, classify_sentiment


def test_classify_sentiment_keyword_scoring():
    assert classify_sentiment("Company beats estimates and raises guidance")[0] == "bullish"
    assert classify_sentiment("Company misses estimates after guidance cut")[0] == "bearish"
    assert classify_sentiment("Company presents at investor conference")[0] == "neutral"


def test_headline_sentiment_dedupes_and_scores_snapshot():
    snapshot = build_headline_sentiment_snapshot(
        "ARWR",
        [
            "ARWR beats estimates and raises guidance",
            "ARWR beats estimates and raises guidance",
            "Analyst downgrade cites dilution risk",
            "Company presents at healthcare conference",
        ],
    )

    assert snapshot.bullish_count == 1
    assert snapshot.bearish_count == 1
    assert snapshot.neutral_count == 1
    assert snapshot.net_score == 0.0
    assert len(snapshot.evidence) == 3
    assert snapshot.confidence > 0


def test_empty_sentiment_snapshot_is_safe():
    snapshot = build_headline_sentiment_snapshot("ARWR", [])

    assert snapshot.bullish_count == 0
    assert snapshot.bearish_count == 0
    assert snapshot.neutral_count == 0
    assert snapshot.net_score == 0.0
    assert snapshot.confidence == 0.0
    assert snapshot.evidence == []
    assert format_sentiment_snapshot(snapshot) == ""


def test_format_sentiment_snapshot_is_compact_and_grounded():
    snapshot = build_headline_sentiment_snapshot(
        "ARWR",
        [
            "ARWR wins approval for new therapy",
            "Bearish analyst downgrade cites delayed launch",
        ],
    )
    block = format_sentiment_snapshot(snapshot)

    assert "Net score:" in block
    assert "Confidence:" in block
    assert "Bullish evidence:" in block
    assert "Bearish evidence:" in block
    assert "wins approval" in block
    assert "delayed launch" in block

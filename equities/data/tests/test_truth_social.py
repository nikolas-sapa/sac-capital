"""Offline coverage for the Truth Social parse -> strip -> filter path.

The WebSocket half needs a live key; these cover the deterministic logic that
decides what reaches the analyst LLM.
"""
from __future__ import annotations

import json

from equities.data.truth_social import (
    TruthSocialNewsProvider,
    mentions_ticker,
    strip_html,
)


def _post(post_id: str, content: str, username: str = "realDonaldTrump") -> dict:
    return {
        "id": post_id,
        "account": {"username": username},
        "created_at": "2026-07-19T12:00:00.000Z",
        "content": content,
    }


def test_strip_html_unwraps_mastodon_markup():
    html = '<p>Tariffs on <a href="x"><span>Apple</span></a> &amp; others!</p>'
    assert strip_html(html) == "Tariffs on Apple & others!"


def test_adjacent_blocks_keep_a_word_boundary():
    # Real feed data: <p>RT @realDonaldTrump</p><p>Republicans should...
    # used to collapse into "...realDonaldTrumpRepublicans".
    out = strip_html("<p>RT @realDonaldTrump</p><p>Republicans should act</p>")
    assert out == "RT @realDonaldTrump Republicans should act"


def test_media_only_posts_strip_to_empty():
    # 22 of 50 live posts were literally "<p></p>" — these must drop out,
    # not surface as blank headlines.
    assert strip_html("<p></p>") == ""


def test_strip_html_survives_garbage():
    assert strip_html("") == ""
    assert strip_html(None) == ""  # type: ignore[arg-type]


def test_cashtag_and_alias_match():
    assert mentions_ticker("buying $AAPL today", "AAPL")
    assert mentions_ticker("Apple is treating us unfairly", "AAPL")
    assert mentions_ticker("Tim Cook called me", "AAPL")


def test_ambiguous_tickers_do_not_match_loosely():
    # 'ON' and 'IT' are real tickers and common words — loose matches here
    # would fire on nearly every post.
    assert not mentions_ticker("IT is ON, believe me", "ON")
    assert not mentions_ticker("IT is ON, believe me", "IT")
    # ...but an explicit cash-tag is unambiguous.
    assert mentions_ticker("watching $ON closely", "ON")


def test_plain_symbol_needs_word_boundary():
    assert mentions_ticker("NVDA is doing great", "NVDA")
    assert not mentions_ticker("NVDAX is unrelated", "NVDA")
    assert not mentions_ticker("nvda lowercase prose", "NVDA")


def test_headlines_filters_by_ticker_and_author(tmp_path):
    cache = tmp_path / "posts.jsonl"
    cache.write_text(
        "\n".join(
            json.dumps(p)
            for p in [
                _post("1", "<p>Apple must build in America</p>"),
                _post("2", "<p>Totally unrelated post about golf</p>"),
                _post("3", "<p>Apple again</p>", username="someoneElse"),
            ]
        )
        + "\n"
    )
    provider = TruthSocialNewsProvider(api_key="test-key", cache_path=cache)
    provider._drain = lambda last_seen_id: []  # type: ignore[method-assign]

    out = provider.headlines("AAPL")

    assert len(out) == 1, out
    assert "Apple must build in America" in out[0]
    assert "@realDonaldTrump" in out[0]


def test_identical_reposts_collapse(tmp_path):
    cache = tmp_path / "posts.jsonl"
    dupe = "<p>Apple must build in America</p>"
    cache.write_text(
        "\n".join(json.dumps(_post(str(i), dupe)) for i in range(3)) + "\n"
    )
    provider = TruthSocialNewsProvider(api_key="test-key", cache_path=cache)
    provider._drain = lambda last_seen_id: []  # type: ignore[method-assign]

    assert len(provider.headlines("AAPL")) == 1


def test_no_key_is_a_noop(tmp_path):
    provider = TruthSocialNewsProvider(api_key="", cache_path=tmp_path / "none.jsonl")
    assert provider.headlines("AAPL") == []


def test_missing_cache_does_not_raise(tmp_path):
    provider = TruthSocialNewsProvider(api_key="test-key", cache_path=tmp_path / "absent.jsonl")
    provider._drain = lambda last_seen_id: []  # type: ignore[method-assign]
    assert provider.headlines("AAPL") == []

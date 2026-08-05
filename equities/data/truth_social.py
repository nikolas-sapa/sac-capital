"""Truth Social posts via VeritaWire → per-ticker headlines.

VeritaWire pushes Truth Social posts over a WebSocket (10s-delay tier). The
equity pipeline is a batch runner, so instead of a daemon we drain on demand:
connect, replay the backlog from the last seen post id, close. The newest
cached post id is the cursor, so consecutive runs pick up where the last left
off.

Fails closed to an empty list everywhere — a dead feed must never break a run.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

_WS_URL = "wss://veritawire.com/ws"
_CACHE_PATH = "data/truth_social_posts.jsonl"
_MAX_CACHED = 500
_IDLE_TIMEOUT = 5.0    # no message for this long => backlog drained
_DRAIN_BUDGET = 30.0   # hard wall-clock cap; heartbeats can defeat idle alone
_OPEN_TIMEOUT = 10.0
_DEFAULT_AUTHORS = ("realDonaldTrump",)

_logger = logging.getLogger(__name__)

# Trump names companies and people, not tickers. Anchor the alias map to what
# he actually says. ponytail: hand-maintained; swap for a name->ticker dataset
# if the alias list starts needing real upkeep.
_ALIASES: dict[str, tuple[str, ...]] = {
    "AAPL": ("apple", "tim cook"),
    "AMZN": ("amazon", "bezos"),
    "GOOGL": ("google", "alphabet", "sundar pichai"),
    "META": ("facebook", "meta", "zuckerberg"),
    "MSFT": ("microsoft",),
    "NVDA": ("nvidia", "jensen huang"),
    "TSLA": ("tesla", "elon musk", "musk"),
    "INTC": ("intel",),
    "BA": ("boeing",),
    "TSM": ("taiwan semiconductor", "tsmc"),
    "X": ("us steel", "u.s. steel"),
    "DJT": ("truth social", "trump media"),
}

# Real tickers that are also ordinary words — never bare-match these, they'd
# fire on half of all posts. Cash-tag or alias only.
_AMBIGUOUS = {
    "A", "ALL", "AN", "ANY", "ARE", "AS", "AT", "BE", "BIG", "BY", "CAN", "CAT",
    "DO", "FOR", "GO", "GOOD", "HAS", "HE", "IT", "ITS", "LOW", "NEW",
    "NOW", "ON", "ONE", "OR", "OUT", "PAY", "REAL", "SEE", "SO", "TRUE", "TWO",
    "UP", "US", "WE", "WELL", "WIN", "X", "YOU",
}


class _TextExtractor(HTMLParser):
    """Strip tags from Mastodon-style post HTML."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    # Tag boundaries are word boundaries: without this `<p>RT @x</p><p>Word`
    # collapses to "RT @xWord". Trailing whitespace is squeezed out below.
    def handle_starttag(self, tag: str, attrs: list) -> None:
        self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        self._parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self._parts.append(" ")

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._parts)).strip()


def strip_html(html: str) -> str:
    """Mastodon post HTML → plain text. Never raises."""
    try:
        parser = _TextExtractor()
        parser.feed(unescape(html or ""))
        parser.close()
        return parser.text()
    except Exception:
        return re.sub(r"<[^>]+>", " ", unescape(html or "")).strip()


def mentions_ticker(text: str, ticker: str, aliases: dict[str, tuple[str, ...]] | None = None) -> bool:
    """True if the post plausibly refers to `ticker`.

    Three ways to match, in descending confidence: an explicit $CASHTAG, a
    known company/person alias, or the bare uppercase symbol. The bare case is
    gated on a blocklist because tickers like ON/IT/ALL are common words and a
    loose match feeds garbage headlines to the analyst LLM.
    """
    if not text or not ticker:
        return False
    symbol = ticker.strip().upper()
    alias_map = _ALIASES if aliases is None else aliases

    if re.search(rf"\${re.escape(symbol)}\b", text, re.IGNORECASE):
        return True

    for alias in alias_map.get(symbol, ()):  # type: ignore[union-attr]
        if isinstance(alias, str) and re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE):
            return True

    if len(symbol) >= 3 and symbol not in _AMBIGUOUS:
        return bool(re.search(rf"\b{re.escape(symbol)}\b", text))
    return False


class TruthSocialNewsProvider:
    """Truth Social posts as ticker-scoped headlines. Never raises.

    The feed is drained once per process on the first `headlines()` call and
    every later call is served from that cache — N screened tickers must not
    mean N WebSocket connections.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        authors: tuple[str, ...] = _DEFAULT_AUTHORS,
        cache_path: str | Path = _CACHE_PATH,
        idle_timeout: float = _IDLE_TIMEOUT,
        drain_budget: float = _DRAIN_BUDGET,
    ) -> None:
        self._key = api_key or os.getenv("TRUTH_SOCIAL_API_KEY", "")
        self._authors = {a.lower() for a in authors}
        self._cache_path = Path(cache_path)
        self._idle_timeout = idle_timeout
        self._drain_budget = drain_budget
        self._posts: list[dict] | None = None

    # -- cache -------------------------------------------------------------

    def _read_cache(self) -> list[dict]:
        try:
            with self._cache_path.open() as fh:
                return [json.loads(line) for line in fh if line.strip()]
        except FileNotFoundError:
            return []
        except Exception as exc:
            _logger.warning(f"truth_social: unreadable cache {self._cache_path}: {exc}")
            return []

    def _write_cache(self, posts: list[dict]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_path.open("w") as fh:
                for post in posts[-_MAX_CACHED:]:
                    fh.write(json.dumps(post) + "\n")
        except Exception as exc:
            _logger.warning(f"truth_social: could not write cache: {exc}")

    # -- feed --------------------------------------------------------------

    def _drain(self, last_seen_id: str | None) -> list[dict]:
        """Replay the backlog since `last_seen_id`, then stop. Never raises."""
        if not self._key:
            return []
        try:
            from websockets.exceptions import ConnectionClosed
            from websockets.sync.client import connect
        except ImportError:
            return []

        # Cold start uses cursor 0, which the server treats as "send the
        # backlog" — without it a first run only sees posts landing inside its
        # own drain window, i.e. almost nothing.
        url = f"{_WS_URL}?last_seen_id={last_seen_id or '0'}"

        received: list[dict] = []
        deadline = time.monotonic() + self._drain_budget
        try:
            with connect(
                url,
                additional_headers={"Authorization": f"Bearer {self._key}"},
                open_timeout=_OPEN_TIMEOUT,
            ) as ws:
                while time.monotonic() < deadline:
                    try:
                        raw = ws.recv(timeout=self._idle_timeout)
                    except TimeoutError:
                        break          # quiet => backlog drained
                    except ConnectionClosed:
                        break
                    try:
                        payload = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue       # heartbeat / non-JSON frame
                    if isinstance(payload, dict) and payload.get("id"):
                        received.append(payload)
                else:
                    _logger.warning(
                        f"truth_social: hit {self._drain_budget}s drain budget; "
                        f"keeping {len(received)} posts"
                    )
        except Exception as exc:
            _logger.warning(f"truth_social: drain failed: {exc}")
        return received

    def _load(self) -> list[dict]:
        """Cache + fresh backlog, deduped by post id, oldest first."""
        cached = self._read_cache()
        fresh = self._drain(cached[-1].get("id") if cached else None)
        if not fresh:
            return cached

        merged: dict[str, dict] = {}
        for post in [*cached, *fresh]:
            post_id = str(post.get("id") or "")
            if post_id:
                merged[post_id] = post
        posts = list(merged.values())[-_MAX_CACHED:]
        self._write_cache(posts)
        return posts

    # -- provider ----------------------------------------------------------

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        if not self._key:
            return []
        if self._posts is None:
            self._posts = self._load()

        results: list[str] = []
        seen_text: set[str] = set()
        for post in reversed(self._posts):       # newest first
            account = post.get("account") or {}
            author = str(account.get("username") or "")
            if self._authors and author.lower() not in self._authors:
                continue
            text = strip_html(str(post.get("content") or ""))
            if not text or not mentions_ticker(text, ticker):
                continue
            # The feed redelivers identical reposts under distinct ids; the
            # analyst should not see the same post three times.
            key = text.casefold()
            if key in seen_text:
                continue
            seen_text.add(key)
            stamp = str(post.get("created_at") or "")[:10]
            prefix = f"Truth Social (@{author}"
            prefix += f", {stamp})" if stamp else ")"
            results.append(f"{prefix}: {text[:280]}")
            if len(results) >= limit:
                break
        return results

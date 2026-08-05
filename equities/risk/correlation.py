"""Real return-correlation gate (companion to the sector-string check in kernel.py).

Sector-label equality misses cross-sector concentration entirely — KLIC, ONTO,
LRCX, AMD, MU can carry four different GICS sub-industries yet move as one
semiconductor-capex bet. This computes actual pairwise Pearson correlation of
daily returns between a candidate and each open position, using the same
price feed the rest of the pipeline already uses (equities/data/prices.py —
no new dependency). Downloaded return series are disk-cached so a run doesn't
re-hit the provider once per candidate per open position; a stale/unavailable
provider degrades to "no correlation signal" (logged) rather than crashing
the run.
"""
from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_LOOKBACK_DAYS = 90
_DEFAULT_CACHE_TTL_SECONDS = 24 * 3600  # one trading day
_MIN_OVERLAP = 10  # minimum overlapping return points to trust a correlation


class CorrelationResult:
    """Pairwise correlations between one candidate and each open ticker it overlapped with."""

    def __init__(self, pairwise: dict[str, float], available: bool) -> None:
        self.pairwise = pairwise
        self.available = available  # False = candidate return series unavailable

    @property
    def max_pairwise(self) -> tuple[str, float] | None:
        """(ticker, corr) of the most correlated open position, or None if nothing to compare."""
        if not self.pairwise:
            return None
        peer = max(self.pairwise, key=self.pairwise.get)
        return peer, self.pairwise[peer]

    @property
    def portfolio_avg(self) -> float | None:
        """Mean correlation to the open book, or None if nothing to compare."""
        if not self.pairwise:
            return None
        return sum(self.pairwise.values()) / len(self.pairwise)


class CorrelationChecker:
    """Computes and caches pairwise return correlation vs. the open book.

    Args:
        price_feed:        Any object with .history(ticker, period, interval) -> PriceSeries
                            (e.g. equities.data.prices.YFinancePriceFeed — reused, not new).
        lookback_days:      Trading days of daily returns to correlate over (default 90).
        cache_dir:          Disk cache dir for downloaded return series.
        cache_ttl_seconds:  Cache freshness window (default 1 trading day).
    """

    def __init__(
        self,
        price_feed: Any,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
        cache_dir: str | Path = "data/correlation_cache",
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._price_feed = price_feed
        self._lookback_days = lookback_days
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_ttl_seconds = cache_ttl_seconds
        self._returns_memo: dict[str, list[float] | None] = {}  # per-run memo, avoids re-parsing cache file

    # ------------------------------------------------------------------
    # Return series (disk-cached)
    # ------------------------------------------------------------------

    def _cache_path(self, ticker: str) -> Path:
        return self._cache_dir / f"{ticker}.json"

    def _load_cached_returns(self, ticker: str) -> list[float] | None:
        path = self._cache_path(ticker)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - payload.get("fetched_at", 0) > self._cache_ttl_seconds:
            return None
        returns = payload.get("returns")
        if not isinstance(returns, list) or len(returns) < _MIN_OVERLAP:
            return None
        return [float(r) for r in returns]

    def _save_cached_returns(self, ticker: str, returns: list[float]) -> None:
        path = self._cache_path(ticker)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": time.time(), "returns": returns}))
        tmp.replace(path)

    def daily_returns(self, ticker: str) -> list[float] | None:
        """Daily % returns for ticker over the lookback window, or None if unavailable."""
        if ticker in self._returns_memo:
            return self._returns_memo[ticker]

        cached = self._load_cached_returns(ticker)
        if cached is not None:
            self._returns_memo[ticker] = cached
            return cached

        try:
            series = self._price_feed.history(ticker, period="6mo", interval="1d")
        except Exception as exc:
            logger.warning("correlation: price fetch failed for %s: %s", ticker, exc)
            self._returns_memo[ticker] = None
            return None

        closes = series.closes if series is not None else []
        if len(closes) < _MIN_OVERLAP + 1:
            logger.warning("correlation: insufficient history for %s (%d bars)", ticker, len(closes))
            self._returns_memo[ticker] = None
            return None

        closes = closes[-(self._lookback_days + 1):]
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] != 0
        ]
        if len(returns) < _MIN_OVERLAP:
            self._returns_memo[ticker] = None
            return None

        self._save_cached_returns(ticker, returns)
        self._returns_memo[ticker] = returns
        return returns

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, candidate: str, open_tickers: list[str]) -> CorrelationResult:
        """Pairwise correlation of candidate vs. each distinct open ticker.

        Peers whose return series can't be fetched are silently skipped (not
        treated as zero correlation) — a provider outage must not either
        block or wave through trades on bad data.
        """
        peers = sorted({t for t in open_tickers if t and t != candidate})
        candidate_returns = self.daily_returns(candidate)
        if candidate_returns is None:
            return CorrelationResult(pairwise={}, available=False)
        if not peers:
            return CorrelationResult(pairwise={}, available=True)

        pairwise: dict[str, float] = {}
        for peer in peers:
            peer_returns = self.daily_returns(peer)
            if peer_returns is None:
                continue
            corr = _pearson(candidate_returns, peer_returns)
            if corr is not None:
                pairwise[peer] = corr

        return CorrelationResult(pairwise=pairwise, available=True)


def _pearson(a: list[float], b: list[float]) -> float | None:
    """Pearson correlation over the overlapping trailing window of two return series."""
    n = min(len(a), len(b))
    if n < _MIN_OVERLAP:
        return None
    a, b = a[-n:], b[-n:]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    denom = math.sqrt(var_a * var_b)
    if denom == 0:
        return None
    return cov / denom

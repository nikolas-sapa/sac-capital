"""Tiingo news provider — free tier requires TIINGO_API_KEY env var."""
from __future__ import annotations

import logging
import os

_TIMEOUT = 8.0  # HTTP timeout for Tiingo API
_logger = logging.getLogger(__name__)


class TiingoNewsProvider:
    """Fetch news from Tiingo API. Falls back to empty list if key absent or request fails."""

    _BASE = "https://api.tiingo.com/tiingo/news"

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or os.getenv("TIINGO_API_KEY", "")

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        if not self._key:
            return []
        try:
            import httpx
            resp = httpx.get(
                self._BASE,
                params={"tickers": ticker, "limit": limit},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Token {self._key}",
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            results: list[str] = []
            for a in resp.json()[:limit]:
                title = a.get("title", "")
                desc = (a.get("description") or "")[:120].strip()
                if title:
                    results.append(f"{title} — {desc}" if desc else title)
            return results
        except httpx.TimeoutException:
            _logger.warning(f"Timeout fetching news from Tiingo for {ticker}; returning empty list")
            return []
        except Exception:
            return []

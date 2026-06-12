"""Crawl4AI-backed news provider — fetches full article text for richer LLM context."""
from __future__ import annotations

import asyncio

try:
    from crawl4ai import AsyncWebCrawler
    _CRAWL4AI_AVAILABLE = True
except ImportError:
    _CRAWL4AI_AVAILABLE = False

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]

from equities.data.yfinance_utils import call_quietly

_TIMEOUT = 8.0
_MAX_URLS = 3
_EXCERPT_LEN = 600
_BLOCKED_DOMAINS = ("finance.yahoo.com", "yahoo.com")


async def _fetch_articles(urls: list[str]) -> list[tuple[str, str]]:
    """Fetch full article markdown for each URL. Returns (url, text) pairs."""
    results: list[tuple[str, str]] = []
    async with AsyncWebCrawler(verbose=False) as crawler:
        for url in urls:
            try:
                result = await asyncio.wait_for(
                    crawler.arun(url=url),
                    timeout=_TIMEOUT,
                )
                if not getattr(result, "success", True):
                    continue
                text = (result.markdown or "").strip()
                if text:
                    results.append((url, text))
            except Exception:
                pass
    return results


class Crawl4AINewsProvider:
    """Fetches full article bodies via Crawl4AI for top yfinance news URLs."""

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        if not _CRAWL4AI_AVAILABLE or yf is None:
            return []
        try:
            news = call_quietly(lambda: yf.Ticker(ticker).news) or []
        except Exception:
            return []

        entries: list[tuple[str, str]] = []
        for item in news:
            content = item.get("content", {})
            title = content.get("title") or item.get("title", "")
            url = (
                content.get("canonicalUrl", {}).get("url")
                or content.get("clickThroughUrl", {}).get("url")
                or item.get("link", "")
            )
            if not title or not url:
                continue
            # skip Yahoo Finance URLs — they hit a GDPR consent wall
            if any(d in url for d in _BLOCKED_DOMAINS):
                continue
            entries.append((title, url))
            if len(entries) >= _MAX_URLS:
                break

        if not entries:
            return []

        urls = [u for _, u in entries]
        try:
            fetched = asyncio.run(_fetch_articles(urls))
        except Exception:
            return []

        url_to_text = dict(fetched)
        results: list[str] = []
        for title, url in entries:
            body = url_to_text.get(url, "")
            excerpt = body[:_EXCERPT_LEN].rstrip() if body else ""
            if excerpt:
                results.append(f"{title} — [full excerpt: {excerpt}]")
            else:
                results.append(title)
            if len(results) >= limit:
                break

        return results

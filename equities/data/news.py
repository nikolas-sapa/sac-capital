"""YFinance-backed news provider for the equity analyst pipeline."""
from __future__ import annotations

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None  # type: ignore[assignment]


class YFinanceNewsProvider:
    """Fetches recent news headlines + summaries for a ticker via yfinance."""

    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        if yf is None:
            return []
        try:
            news = yf.Ticker(ticker).news or []
            results: list[str] = []
            for n in news[:limit]:
                content = n.get("content", {})
                title = content.get("title") or n.get("title", "")
                summary = content.get("summary") or n.get("summary", "")
                if not title:
                    continue
                line = title
                if summary:
                    line += f" — {summary[:150].rstrip()}"
                results.append(line)
            return results
        except Exception:
            return []

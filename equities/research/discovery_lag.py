"""Discovery lag — measures how far a leaf supplier's stock lags the trunk."""
from __future__ import annotations


class DiscoveryLagCalculator:
    """Compute discovery_lag = trunk return pct - leaf return pct."""

    def compute(self, trunk: str, leaf: str, period: str = "1y") -> float:
        t = self._fetch_return(trunk, period=period)
        l = self._fetch_return(leaf, period=period)
        if t is None or l is None:
            return 0.0
        return round(t - l, 2)

    def _fetch_12m_return(self, ticker: str) -> float | None:
        return self._fetch_return(ticker, period="1y")

    def _fetch_return(self, ticker: str, period: str = "1y") -> float | None:
        try:
            import yfinance as yf
            hist = yf.Ticker(ticker).history(period=period)
            if hist.empty or len(hist) < 3:
                return None
            start = float(hist["Close"].iloc[0])
            end = float(hist["Close"].iloc[-1])
            return (end / start - 1) * 100 if start > 0 else None
        except Exception:
            return None

    def score_all_leaves(self, trunk: str, period: str = "1y") -> list[tuple[str, float, float]]:
        """Return [(leaf, bottleneck_score, discovery_lag_pct)] sorted by lag desc."""
        from equities.research.supply_chain import BottleneckScorer, get_leaves_for_trunk
        scorer = BottleneckScorer()
        return sorted(
            [(leaf, scorer.score(leaf, trunk), self.compute(trunk, leaf, period=period))
             for leaf in get_leaves_for_trunk(trunk)],
            key=lambda x: x[2],
            reverse=True,
        )

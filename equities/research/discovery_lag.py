"""Discovery lag — measures how far a leaf supplier's stock lags the trunk."""
from __future__ import annotations


class DiscoveryLagCalculator:
    """Compute discovery_lag = trunk return pct - leaf return pct."""

    def compute(self, trunk: str, leaf: str, period: str = "1y") -> float | None:
        t = self._fetch_return(trunk, period=period)
        l = self._fetch_return(leaf, period=period)
        if t is None or l is None:
            return None
        return round(t - l, 2)

    def _fetch_12m_return(self, ticker: str) -> float | None:
        return self._fetch_return(ticker, period="1y")

    def _fetch_return(self, ticker: str, period: str = "1y") -> float | None:
        try:
            import yfinance as yf
            # auto_adjust=True makes Close split and dividend adjusted. Raw
            # closes create impossible returns across splits and corrupt ranks.
            hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if hist.empty or len(hist) < 3:
                return None
            start = float(hist["Close"].iloc[0])
            end = float(hist["Close"].iloc[-1])
            if not (start > 0 and end > 0):
                return None
            return (end / start - 1) * 100
        except Exception:
            return None

    def score_all_leaves(self, trunk: str, period: str = "1y") -> list[tuple[str, float, float]]:
        """Return [(leaf, bottleneck_score, discovery_lag_pct)] sorted by lag desc."""
        from equities.research.supply_chain import BottleneckScorer, get_leaves_for_trunk
        scorer = BottleneckScorer()
        scored = []
        for leaf in get_leaves_for_trunk(trunk):
            lag = self.compute(trunk, leaf, period=period)
            if lag is not None:
                scored.append((leaf, scorer.score(leaf, trunk), lag))
        return sorted(
            scored,
            key=lambda x: x[2],
            reverse=True,
        )

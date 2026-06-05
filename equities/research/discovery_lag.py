"""Discovery lag — measures how far a leaf supplier's stock lags the trunk."""
from __future__ import annotations


class DiscoveryLagCalculator:
    """Compute discovery_lag = trunk_12m_return_pct - leaf_12m_return_pct."""

    def compute(self, trunk: str, leaf: str) -> float:
        t = self._fetch_12m_return(trunk)
        l = self._fetch_12m_return(leaf)
        if t is None or l is None:
            return 0.0
        return round(t - l, 2)

    def _fetch_12m_return(self, ticker: str) -> float | None:
        try:
            import yfinance as yf
            hist = yf.Ticker(ticker).history(period="1y")
            if hist.empty or len(hist) < 20:
                return None
            start = float(hist["Close"].iloc[0])
            end = float(hist["Close"].iloc[-1])
            return (end / start - 1) * 100 if start > 0 else None
        except Exception:
            return None

    def score_all_leaves(self, trunk: str) -> list[tuple[str, float, float]]:
        """Return [(leaf, bottleneck_score, discovery_lag_pct)] sorted by lag desc."""
        from equities.research.supply_chain import BottleneckScorer, get_leaves_for_trunk
        scorer = BottleneckScorer()
        return sorted(
            [(leaf, scorer.score(leaf, trunk), self.compute(trunk, leaf))
             for leaf in get_leaves_for_trunk(trunk)],
            key=lambda x: x[2],
            reverse=True,
        )

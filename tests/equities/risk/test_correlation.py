"""Self-check for the return-correlation gate (equities/risk/correlation.py).

Synthetic price series stand in for the real provider: a candidate that
tracks an open position tick-for-tick must be blocked; a candidate whose
returns are uncorrelated (independent random walk) must be allowed through.
"""
import math
import random

from core.assets.bar import Bar, PriceSeries
from core.assets.instrument import CapTier, Instrument
from equities.risk.correlation import CorrelationChecker
from equities.risk.kernel import RiskKernel
from equities.strategy import Recommendation, Sleeve


class _FakePriceFeed:
    """In-memory PriceFeed: ticker -> list of closes, no network."""

    def __init__(self, closes_by_ticker: dict[str, list[float]]) -> None:
        self._closes_by_ticker = closes_by_ticker

    def history(self, ticker: str, period: str = "6mo", interval: str = "1d") -> PriceSeries:
        closes = self._closes_by_ticker.get(ticker, [])
        bars = [
            Bar(day=__import__("datetime").date(2026, 1, 1), open=c, high=c, low=c, close=c, volume=0)
            for c in closes
        ]
        return PriceSeries(ticker=ticker, bars=bars)


def _walk(seed: int, n: int = 120, start: float = 100.0) -> list[float]:
    rng = random.Random(seed)
    closes = [start]
    for _ in range(n):
        closes.append(closes[-1] * (1 + rng.uniform(-0.02, 0.02)))
    return closes


def _swing_rec(ticker: str, entry: float = 100.0) -> Recommendation:
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=entry,
        stop_loss=entry * 0.95,
        take_profit=entry * 1.15,
        size_pct=0.02,
        confidence=0.72,
        catalyst="test",
        thesis="test thesis",
        horizon="2 weeks",
    )


def _open_pos(ticker: str) -> dict:
    return {"ticker": ticker, "sleeve": "swing", "shares": 10.0, "entry_price": 100.0, "status": "open"}


def main() -> None:
    base_walk = _walk(seed=1)

    # Candidate KLIC tracks the open position ONTO almost exactly (same series,
    # tiny noise) -> should be blocked by the pairwise correlation gate.
    correlated_closes = {
        "ONTO": base_walk,
        "KLIC": [c * (1 + 0.0001 * i) for i, c in enumerate(base_walk)],  # near-identical
    }
    checker = CorrelationChecker(_FakePriceFeed(correlated_closes), cache_dir="/tmp/sapa_corr_test_blocked")
    kernel = RiskKernel(
        capital=100_000.0,
        max_name_pct=1.0,
        max_pairwise_corr=0.7,
        max_portfolio_corr=0.5,
        correlation_checker=checker,
    )
    sized = kernel.approve(_swing_rec("KLIC"), [_open_pos("ONTO")])
    assert not sized.approved, "expected highly-correlated add to be blocked"
    assert sized.rejection_reason.startswith("correlation_pairwise_"), sized.rejection_reason
    print(f"OK: correlated add blocked ({sized.rejection_reason})")

    # Candidate is an independent random walk vs. the open position -> allowed.
    uncorrelated_closes = {
        "AAPL": base_walk,
        "XYZ": _walk(seed=99),
    }
    checker2 = CorrelationChecker(_FakePriceFeed(uncorrelated_closes), cache_dir="/tmp/sapa_corr_test_allowed")
    kernel2 = RiskKernel(
        capital=100_000.0,
        max_name_pct=1.0,
        max_pairwise_corr=0.7,
        max_portfolio_corr=0.5,
        correlation_checker=checker2,
    )
    sized2 = kernel2.approve(_swing_rec("XYZ"), [_open_pos("AAPL")])
    assert sized2.approved, f"expected uncorrelated add to be allowed, got: {sized2.rejection_reason}"
    print("OK: uncorrelated add allowed")

    # Missing/unavailable price data must degrade gracefully, not block.
    checker3 = CorrelationChecker(_FakePriceFeed({}), cache_dir="/tmp/sapa_corr_test_missing")
    kernel3 = RiskKernel(
        capital=100_000.0,
        max_name_pct=1.0,
        correlation_checker=checker3,
    )
    sized3 = kernel3.approve(_swing_rec("NEWCO"), [_open_pos("AAPL")])
    assert sized3.approved, f"expected missing-data case to degrade gracefully, got: {sized3.rejection_reason}"
    print("OK: missing price data degrades gracefully (no block)")


if __name__ == "__main__":
    main()

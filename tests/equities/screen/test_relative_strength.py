from __future__ import annotations

from datetime import date, timedelta

from core.assets.bar import Bar, PriceSeries
from core.assets.instrument import CapTier, Instrument
from equities.screen.relative_strength import RelativeStrengthScanner


class FakePriceFeed:
    def __init__(self, series: dict[str, PriceSeries]) -> None:
        self._series = series

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        return self._series[ticker]


def _instrument(ticker: str) -> Instrument:
    return Instrument(ticker, ticker, "NASDAQ", CapTier.MID)


def _series(ticker: str, closes: list[float], volumes: list[int] | None = None) -> PriceSeries:
    start = date(2025, 1, 1)
    volumes = volumes or [1_000 for _ in closes]
    bars = [
        Bar(
            day=start + timedelta(days=idx),
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=volumes[idx],
        )
        for idx, close in enumerate(closes)
    ]
    return PriceSeries(ticker=ticker, bars=bars)


def _strong_base_closes() -> list[float]:
    trend = [50.0 + idx * 0.25 for idx in range(180)]
    volatile = [95.0 + (3.0 if idx % 2 else -3.0) for idx in range(20)]
    base = [96.0 + idx * 0.15 for idx in range(20)]
    return trend + volatile + base


def test_relative_strength_scanner_ranks_trend_and_base_evidence():
    strong = _strong_base_closes()
    weak = [50.0 - idx * 0.02 for idx in range(220)]
    spy = [100.0 + idx * 0.03 for idx in range(220)]
    qqq = [100.0 + idx * 0.04 for idx in range(220)]
    volumes = [1_000 for _ in strong]
    volumes[-1] = 1_600
    feed = FakePriceFeed({
        "STR": _series("STR", strong, volumes),
        "WEAK": _series("WEAK", weak),
        "SPY": _series("SPY", spy),
        "QQQ": _series("QQQ", qqq),
    })

    result = RelativeStrengthScanner(feed).scan([_instrument("STR"), _instrument("WEAK")])

    strong_evidence = result["STR"]
    assert strong_evidence.rs_rank == 1
    assert strong_evidence.universe_size == 2
    assert strong_evidence.rs_score > 0
    assert strong_evidence.trend_ok is True
    assert strong_evidence.base_ok is True
    assert strong_evidence.breakout_volume is True
    assert strong_evidence.do_not_chase is False
    assert "RS rank 1/2" in strong_evidence.evidence
    assert "trend_20_50_200=pass" in strong_evidence.evidence
    assert "base=pass" in strong_evidence.evidence
    assert "breakout_volume=yes" in strong_evidence.evidence

    weak_evidence = result["WEAK"]
    assert weak_evidence.rs_rank == 2
    assert weak_evidence.trend_ok is False


def test_relative_strength_scanner_flags_do_not_chase():
    chased = [50.0 + idx * 0.1 for idx in range(214)] + [80.0, 84.0, 88.0, 92.0, 96.0, 100.0]
    spy = [100.0 + idx * 0.01 for idx in range(220)]
    feed = FakePriceFeed({
        "RUN": _series("RUN", chased),
        "SPY": _series("SPY", spy),
        "QQQ": _series("QQQ", spy),
    })

    result = RelativeStrengthScanner(feed).scan([_instrument("RUN")])

    assert result["RUN"].do_not_chase is True
    assert "do_not_chase=yes" in result["RUN"].evidence

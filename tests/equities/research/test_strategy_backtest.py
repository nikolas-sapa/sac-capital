from __future__ import annotations

from datetime import date, timedelta

from core.assets.bar import Bar, PriceSeries
from equities.research.backtest import run_backtest, simulate_candidate
from equities.screen.supply_chain_lag_screen import SupplyChainLagCandidate


class FakePriceFeed:
    def __init__(self, series: dict[str, PriceSeries]) -> None:
        self._series = series

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        return self._series.get(ticker, _series(ticker, [100.0] * 20))


def _series(ticker: str, closes: list[float]) -> PriceSeries:
    start = date(2025, 1, 1)
    bars = [
        Bar(
            day=start + timedelta(days=idx),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=10_000_000,
        )
        for idx, close in enumerate(closes)
    ]
    return PriceSeries(ticker=ticker, bars=bars)


def _bars(ticker: str, rows: list[tuple[float, float, float, float]]) -> PriceSeries:
    start = date(2025, 1, 1)
    return PriceSeries(
        ticker=ticker,
        bars=[
            Bar(
                day=start + timedelta(days=idx),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=10_000_000,
            )
            for idx, (open_, high, low, close) in enumerate(rows)
        ],
    )


def _candidate(**features) -> SupplyChainLagCandidate:
    return SupplyChainLagCandidate(
        strategy="semi_bottleneck_catch_up",
        ticker="AMAT",
        trunk="AMD",
        entry_signal_at=date(2025, 1, 2),
        features={
            "stop_loss": 92.0,
            "take_profit": 110.0,
            "max_holding_days": 3,
            **features,
        },
        entry_rule="test",
        exit_rule="test",
        risk_tags=[],
        thesis="test",
    )


def test_entry_uses_next_session_not_signal_day():
    series = _bars("AMAT", [
        (100.0, 100.0, 100.0, 100.0),
        (101.0, 101.0, 101.0, 101.0),
        (102.0, 104.0, 100.0, 103.0),
        (103.0, 111.0, 103.0, 110.0),
    ])

    trade = simulate_candidate(_candidate(), series, _series("AMD", [100.0] * 20))

    assert trade is not None
    assert trade.signal_day == "2025-01-02"
    assert trade.entry_day == "2025-01-03"
    assert trade.entry_price == 102.0


def test_stop_target_precedence_is_stop_first():
    series = _bars("AMAT", [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 112.0, 90.0, 105.0),
    ])

    trade = simulate_candidate(_candidate(), series, _series("AMD", [100.0] * 20))

    assert trade is not None
    assert trade.exit_reason == "stop_hit"
    assert trade.exit_price == 92.0


def test_costs_reduce_returns():
    series = _bars("AMAT", [
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 100.0, 100.0, 100.0),
        (100.0, 105.0, 99.0, 104.0),
    ])

    trade = simulate_candidate(_candidate(take_profit=105.0), series, _series("AMD", [100.0] * 20))

    assert trade is not None
    assert trade.gross_return_pct > trade.net_return_pct


def test_no_trades_when_data_insufficient():
    series = _series("AMAT", [100.0, 101.0])
    candidate = _candidate()
    feed = FakePriceFeed({
        "AMAT": series,
        "AMD": _series("AMD", [100.0, 101.0]),
        "SPY": _series("SPY", [100.0, 101.0]),
        "QQQ": _series("QQQ", [100.0, 101.0]),
        "SOXX": _series("SOXX", [100.0, 101.0]),
    })

    report = run_backtest([candidate], feed)

    assert report.trade_count == 0
    assert simulate_candidate(candidate, series, _series("AMD", [100.0, 101.0])) is None

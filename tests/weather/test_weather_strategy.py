from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from core.markets import Market, Outcome
from core.strategy import Signal
from strategies.weather.consensus import ConsensusResult
from strategies.weather.forecast import ModelForecasts
from strategies.weather.strategy import WeatherStrategy


def _temp_market(city: str = "New York", hours: float = 20.0, asks: list[float] | None = None) -> Market:
    if asks is None:
        asks = [0.28, 0.30, 0.28]
    bin_labels = ["68°", "70°", "72°"]
    outcomes = [
        Outcome(token_id=f"bin_{lbl}", label=lbl, best_bid=a - 0.05, best_ask=a)
        for lbl, a in zip(bin_labels, asks)
    ]
    return Market(
        condition_id="cond_wx",
        question=f"What will the high temperature be in {city}?",
        outcomes=outcomes,
        end_date=datetime.now(tz=timezone.utc) + timedelta(hours=hours),
        closed=False,
    )


def _good_forecasts() -> ModelForecasts:
    return ModelForecasts(icon_max=70.0, gfs_max=70.5, ecmwf_max=71.0, spread=1.0, agree=True)


def test_scan_emits_signal_for_valid_market():
    strat = WeatherStrategy()
    market = _temp_market("New York", hours=20)
    with patch("strategies.weather.strategy.fetch_forecast", return_value=_good_forecasts()):
        signals = strat.scan([market])
    assert len(signals) >= 1
    assert all(isinstance(s, Signal) for s in signals)


def test_scan_emits_nothing_outside_window():
    strat = WeatherStrategy()
    market = _temp_market("New York", hours=5)  # too soon
    with patch("strategies.weather.strategy.fetch_forecast", return_value=_good_forecasts()):
        signals = strat.scan([market])
    assert signals == []


def test_scan_emits_nothing_when_spread_too_wide():
    strat = WeatherStrategy()
    market = _temp_market("New York", hours=20)
    wide = ModelForecasts(icon_max=70.0, gfs_max=74.5, ecmwf_max=74.0, spread=4.5, agree=False)
    with patch("strategies.weather.strategy.fetch_forecast", return_value=wide):
        signals = strat.scan([market])
    assert signals == []


def test_scan_emits_nothing_when_price_filters_fail():
    strat = WeatherStrategy()
    market = _temp_market("New York", hours=20, asks=[0.34, 0.34, 0.34])  # sum=1.02 > 0.95
    with patch("strategies.weather.strategy.fetch_forecast", return_value=_good_forecasts()):
        signals = strat.scan([market])
    assert signals == []


def test_scan_skips_unknown_city():
    strat = WeatherStrategy()
    market = _temp_market("Atlantis", hours=20)
    with patch("strategies.weather.strategy.fetch_forecast", return_value=_good_forecasts()):
        signals = strat.scan([market])
    assert signals == []


def test_strategy_satisfies_protocol():
    from core.strategy import Strategy
    assert isinstance(WeatherStrategy(), Strategy)

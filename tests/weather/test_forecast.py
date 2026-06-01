import json
from pathlib import Path
from datetime import date

from strategies.weather.stations import STATIONS
from strategies.weather.forecast import build_url, parse_forecast, ModelForecasts


FIXTURE = json.loads((Path(__file__).parent / "fixtures/open_meteo.json").read_text())


def test_build_url_contains_bias_correction():
    url = build_url(STATIONS["New York"], date(2026, 6, 1))
    assert "bias_correction=true" in url


def test_build_url_contains_all_three_models():
    url = build_url(STATIONS["New York"], date(2026, 6, 1))
    assert "icon_seamless" in url
    assert "gfs_seamless" in url
    assert "ecmwf_ifs025" in url


def test_build_url_uses_station_coords():
    nyc = STATIONS["New York"]
    url = build_url(nyc, date(2026, 6, 1))
    assert str(nyc.lat) in url
    assert str(nyc.lon) in url


def test_build_url_fahrenheit_for_us():
    url = build_url(STATIONS["New York"], date(2026, 6, 1))
    assert "fahrenheit" in url


def test_build_url_celsius_for_international():
    url = build_url(STATIONS["Tokyo"], date(2026, 6, 1))
    assert "celsius" in url


def test_parse_forecast_returns_model_forecasts():
    mf = parse_forecast(FIXTURE)
    assert isinstance(mf, ModelForecasts)


def test_parse_forecast_has_three_model_daily_maxes():
    mf = parse_forecast(FIXTURE)
    assert mf.icon_max is not None
    assert mf.gfs_max is not None
    assert mf.ecmwf_max is not None


def test_parse_forecast_spread_computed():
    mf = parse_forecast(FIXTURE)
    assert mf.spread >= 0.0


def test_parse_forecast_agree_flag():
    mf = parse_forecast(FIXTURE)
    expected = mf.spread <= 3.0
    assert mf.agree == expected

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from strategies.weather.stations import StationInfo

_BASE = "https://api.open-meteo.com/v1/forecast"
_MODELS = "icon_seamless,gfs_seamless,ecmwf_ifs025"


@dataclass(frozen=True)
class ModelForecasts:
    icon_max: float
    gfs_max: float
    ecmwf_max: float
    spread: float   # max - min across the three models
    agree: bool     # spread <= 3.0 °F or °C


def build_url(station: StationInfo, target_date: date) -> str:
    temp_unit = "fahrenheit" if station.unit == "F" else "celsius"
    return (
        f"{_BASE}"
        f"?latitude={station.lat}&longitude={station.lon}"
        f"&hourly=temperature_2m"
        f"&models={_MODELS}"
        f"&bias_correction=true"
        f"&forecast_days=2"
        f"&temperature_unit={temp_unit}"
    )


def parse_forecast(data: dict[str, Any]) -> ModelForecasts:
    """Extract daily max for each model from the API response."""
    hourly = data["hourly"]
    icon_max  = max(v for v in hourly["temperature_2m_icon_seamless"]  if v is not None)
    gfs_max   = max(v for v in hourly["temperature_2m_gfs_seamless"]   if v is not None)
    ecmwf_max = max(v for v in hourly["temperature_2m_ecmwf_ifs025"]   if v is not None)
    spread = max(icon_max, gfs_max, ecmwf_max) - min(icon_max, gfs_max, ecmwf_max)
    return ModelForecasts(
        icon_max=icon_max,
        gfs_max=gfs_max,
        ecmwf_max=ecmwf_max,
        spread=round(spread, 2),
        agree=spread <= 3.0,
    )


def fetch_forecast(station: StationInfo, target_date: date) -> ModelForecasts:
    """Live fetch — not called in tests (use fixture + parse_forecast instead)."""
    url = build_url(station, target_date)
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    return parse_forecast(resp.json())

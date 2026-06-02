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
    icon_min: float
    gfs_min: float
    ecmwf_min: float
    spread: float   # max - min across max forecasts
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
    """Extract tomorrow's daily max and min for each model from the API response.

    forecast_days=2 returns 48 hourly values: [0..23] = today, [24..47] = tomorrow.
    We always slice tomorrow's hours (index 24 onward) because in_window() ensures
    the market resolves in 18-30h — i.e., it always resolves tomorrow.
    """
    hourly = data["hourly"]

    def _tomorrow(key: str) -> list[float]:
        vals = hourly[key]
        tomorrow = [v for v in vals[24:] if v is not None]
        # Fallback to all hours if tomorrow slice is empty (shouldn't happen)
        return tomorrow if tomorrow else [v for v in vals if v is not None]

    icon_vals  = _tomorrow("temperature_2m_icon_seamless")
    gfs_vals   = _tomorrow("temperature_2m_gfs_seamless")
    ecmwf_vals = _tomorrow("temperature_2m_ecmwf_ifs025")

    icon_max,  icon_min  = max(icon_vals),  min(icon_vals)
    gfs_max,   gfs_min   = max(gfs_vals),   min(gfs_vals)
    ecmwf_max, ecmwf_min = max(ecmwf_vals), min(ecmwf_vals)

    spread = max(icon_max, gfs_max, ecmwf_max) - min(icon_max, gfs_max, ecmwf_max)
    return ModelForecasts(
        icon_max=icon_max,   gfs_max=gfs_max,   ecmwf_max=ecmwf_max,
        icon_min=icon_min,   gfs_min=gfs_min,   ecmwf_min=ecmwf_min,
        spread=round(spread, 2),
        agree=spread <= 3.0,
    )


def fetch_forecast(station: StationInfo, target_date: date) -> ModelForecasts:
    """Live fetch — not called in tests (use fixture + parse_forecast instead)."""
    url = build_url(station, target_date)
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    return parse_forecast(resp.json())

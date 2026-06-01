from __future__ import annotations

import re
from datetime import date, datetime, timezone

from core.markets import Market
from core.strategy import Signal
from strategies.weather.bins import build_portfolio, find_bin
from strategies.weather.consensus import consensus
from strategies.weather.filters import passes_filters
from strategies.weather.forecast import fetch_forecast
from strategies.weather.stations import STATIONS
from strategies.weather.window import in_window

_CITY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in STATIONS) + r")\b",
    re.IGNORECASE,
)


def _detect_city(question: str) -> str | None:
    m = _CITY_PATTERN.search(question)
    if not m:
        return None
    # Normalise case to match STATIONS key
    raw = m.group(1)
    for key in STATIONS:
        if key.lower() == raw.lower():
            return key
    return None


class WeatherStrategy:
    """Scan Polymarket daily-temperature markets; emit Signals for the 3-bin portfolio."""

    name = "weather"

    def scan(self, markets: list[Market]) -> list[Signal]:
        signals: list[Signal] = []
        today = date.today()

        for market in markets:
            if market.closed:
                continue
            if not in_window(market.end_date):
                continue

            city = _detect_city(market.question)
            if city is None:
                continue

            station = STATIONS[city]
            try:
                mf = fetch_forecast(station, today)
            except Exception:
                continue

            cr = consensus(icon=mf.icon_max, gfs=mf.gfs_max, ecmwf=mf.ecmwf_max)
            if cr is None:
                continue

            portfolio = build_portfolio(cr, market)
            if len(portfolio) < 2:
                continue

            if not passes_filters(portfolio):
                continue

            # Confidence from model spread: tighter = higher
            confidence = max(0.3, min(0.9, 1.0 - cr.spread / 3.0))

            # Fair prob per bin: assume uniform across the 3-bin coverage window
            fair_prob_per_bin = 1.0 / 3.0

            for outcome in portfolio:
                signals.append(
                    Signal(
                        market=market,
                        token_id=outcome.token_id,
                        fair_prob=fair_prob_per_bin,
                        price=outcome.best_ask,
                        confidence=confidence,
                        reason=f"{city}: consensus={cr.center:.1f}° spread={cr.spread:.1f}° outlier={cr.outlier}",
                    )
                )

        return signals

"""Thematic concentration monitor — uses supply chain graph to detect theme over-concentration."""
from __future__ import annotations

from equities.research.supply_chain import get_trunks_for_leaf


class ThematicMonitor:
    def __init__(self, max_theme_pct: float = 0.35, capital: float = 10_000.0) -> None:
        self._max = max_theme_pct
        self._capital = capital

    def check(self, open_positions: list[dict]) -> list[str]:
        theme_exposure: dict[str, float] = {}
        for pos in open_positions:
            ticker = pos.get("ticker", "")
            value = pos.get("shares", 0) * pos.get("entry_price", 0.0)
            trunks = get_trunks_for_leaf(ticker)
            if not trunks:
                continue
            for trunk in trunks:
                theme_exposure[trunk] = theme_exposure.get(trunk, 0.0) + value

        alerts: list[str] = []
        for trunk, exposure in theme_exposure.items():
            pct = exposure / self._capital
            if pct > self._max:
                alerts.append(
                    f"Thematic concentration: {trunk} chain = {pct:.1%} > limit {self._max:.0%}"
                )
        return alerts

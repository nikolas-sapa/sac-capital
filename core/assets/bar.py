from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class PriceSeries:
    ticker: str
    bars: list[Bar]

    @property
    def closes(self) -> list[float]:
        return [b.close for b in self.bars]

    @property
    def latest(self) -> Bar | None:
        return self.bars[-1] if self.bars else None

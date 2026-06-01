from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CapTier(Enum):
    LARGE = "large"
    MID = "mid"
    SMALL = "small"


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    exchange: str
    cap_tier: CapTier

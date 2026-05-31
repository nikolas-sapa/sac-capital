from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from core.strategy import Signal


@dataclass(frozen=True)
class Fill:
    signal: Signal
    stake: float
    shares: float
    avg_price: float
    timestamp: datetime
    mode: str              # "paper" | "live"


@runtime_checkable
class Executor(Protocol):
    def place(self, signal: Signal, stake: float) -> Fill: ...

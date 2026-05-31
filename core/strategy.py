from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.markets import Market


@dataclass(frozen=True)
class Signal:
    market: Market
    token_id: str          # which outcome to buy
    fair_prob: float       # strategy's estimated true probability (0-1)
    price: float           # current ask we'd pay
    confidence: float      # 0-1, drives orchestrator weighting
    reason: str            # human-readable why


@runtime_checkable
class Strategy(Protocol):
    name: str

    def scan(self, markets: list[Market]) -> list[Signal]: ...

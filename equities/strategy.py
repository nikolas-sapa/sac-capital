from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from core.assets.instrument import Instrument


class Sleeve(Enum):
    CORE = "core"    # long-term DCA, no stops
    SWING = "swing"  # catalyst trade, hard stops


@dataclass(frozen=True)
class Recommendation:
    instrument: Instrument
    sleeve: Sleeve
    side: str                  # "buy" (short out of scope for v1)
    entry: float
    stop_loss: float | None    # None for CORE
    take_profit: float | None  # None for CORE
    size_pct: float            # fraction of capital to deploy
    confidence: float          # 0-1
    catalyst: str
    thesis: str
    horizon: str
    memo: dict[str, Any] | None = None
    # Full structured analysis from the LLM pipeline (analyst + challenger + auditor)
    analysis: dict[str, Any] | None = None
    # Sizing verdict from challenger debate
    size_verdict: str = "full"  # "full" | "half" | "skip"
    size_rationale: str = ""


@runtime_checkable
class ContinuousStrategy(Protocol):
    name: str

    def scan(self, universe: list[Instrument]) -> list[Recommendation]: ...

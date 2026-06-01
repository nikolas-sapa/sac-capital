"""Integration test for the orchestrated runner mode."""
import asyncio
from datetime import datetime, timezone, timedelta

import pytest

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal
from core.config import Settings
from runner import run_orchestrated


def _market(cid: str, question: str = "Q?") -> Market:
    return Market(
        condition_id=cid,
        question=question,
        outcomes=[
            Outcome("yes", "Yes", 0.4, 0.5),
            Outcome("no", "No", 0.4, 0.5),
        ],
        end_date=datetime.now(tz=timezone.utc) + timedelta(hours=4),
        closed=False,
    )


class AlwaysBuyStrategy:
    name = "always_buy"

    def __init__(self, token: str = "yes", fair_prob: float = 0.75):
        self._token = token
        self._fair_prob = fair_prob

    def scan(self, markets: list[Market]) -> list[Signal]:
        return [
            Signal(
                market=m,
                token_id=self._token,
                fair_prob=self._fair_prob,
                price=0.5,
                confidence=0.7,
                reason="stub",
            )
            for m in markets
        ]


class NoBuyStrategy:
    name = "no_buy"

    def scan(self, markets: list[Market]) -> list[Signal]:
        return []


class FakePaperExecutor:
    def __init__(self, ledger: Ledger):
        self._ledger = ledger

    def place(self, signal: Signal, stake: float, strategy: str = "") -> Fill:
        fill = Fill(
            signal=signal,
            stake=stake,
            shares=stake / signal.price,
            avg_price=signal.price,
            mode="paper",
            timestamp=datetime.now(tz=timezone.utc),
        )
        self._ledger.record(fill, strategy=strategy)
        return fill


def test_orchestrated_respects_max_position(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    executor = FakePaperExecutor(ledger)
    settings = Settings(
        bankroll_usd=1000.0,
        kelly_fraction=0.5,
        max_position_pct=0.02,  # max 20 per trade
    )
    markets = [_market(f"m{i}") for i in range(5)]
    strat = AlwaysBuyStrategy(fair_prob=0.75)

    fills = asyncio.run(
        run_orchestrated(markets, [strat], executor, settings, ledger)
    )

    for fill in fills:
        assert fill.stake <= 0.02 * 1000.0 + 1e-6


def test_orchestrated_conflict_deduplicated(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    executor = FakePaperExecutor(ledger)
    settings = Settings(bankroll_usd=1000.0, kelly_fraction=0.5, max_position_pct=0.02)

    m = _market("dup")
    # Two strategies both want to buy "yes" on the same market
    strat_a = AlwaysBuyStrategy(fair_prob=0.80)
    strat_a.name = "a"
    strat_b = AlwaysBuyStrategy(fair_prob=0.70)
    strat_b.name = "b"

    fills = asyncio.run(
        run_orchestrated([m], [strat_a, strat_b], executor, settings, ledger)
    )

    # Should only place once on this market (deduplication)
    assert len(fills) <= 1


def test_no_signals_produces_no_fills(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    executor = FakePaperExecutor(ledger)
    settings = Settings(bankroll_usd=1000.0)
    markets = [_market("m1")]

    fills = asyncio.run(
        run_orchestrated(markets, [NoBuyStrategy()], executor, settings, ledger)
    )
    assert fills == []

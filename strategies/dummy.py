"""DummyStrategy — always-on test strategy for development and integration testing.

Emits one buy signal on the first available market's first outcome.
Use only for smoke-testing the pipeline; never for live trading.
"""
from __future__ import annotations

from core.markets import Market
from core.strategy import Signal


class DummyStrategy:
    """Always-on strategy that emits a single buy signal for smoke-testing.

    Implements the Strategy protocol:
      - name (str): "dummy"
      - scan(markets) -> list[Signal]
    """

    name = "dummy"

    def scan(self, markets: list[Market]) -> list[Signal]:
        """Emit one Signal buying the first outcome of the first market.

        Uses the outcome's best_ask as price (fallback to 0.5 if best_ask <= 0).
        Sets fair_prob = 0.65, a deliberate edge over a ~0.5 price so kelly > 0.

        Returns [] if no markets are provided.
        """
        if not markets:
            return []

        market = markets[0]
        outcome = market.outcomes[0]

        price = outcome.best_ask if outcome.best_ask > 0 else 0.5

        return [
            Signal(
                market=market,
                token_id=outcome.token_id,
                fair_prob=0.65,
                price=price,
                confidence=1.0,
                reason="dummy: always-on test signal",
            )
        ]

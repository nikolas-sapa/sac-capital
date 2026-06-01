from __future__ import annotations

import re

from core.markets import Market
from core.strategy import Signal
from strategies.crypto_updown.arbitrage import find_arb

_UPDOWN_PATTERN = re.compile(r"\b(higher|lower|up|down)\b", re.IGNORECASE)
_CRYPTO_PATTERN = re.compile(r"\b(BTC|ETH|bitcoin|ethereum)\b", re.IGNORECASE)

_DEFAULT_FEE = 0.01  # 1% per leg (conservative; Polymarket fee is 0-2%)


def _is_updown_market(market: Market) -> bool:
    q = market.question
    return bool(_UPDOWN_PATTERN.search(q) and _CRYPTO_PATTERN.search(q))


def _find_up_down_outcomes(market: Market):
    up   = next((o for o in market.outcomes if o.label.lower() in ("up", "higher", "yes")), None)
    down = next((o for o in market.outcomes if o.label.lower() in ("down", "lower", "no")),  None)
    return up, down


class CryptoUpDownStrategy:
    """Crypto Up/Down strategy: complete-set arbitrage (always) +
    optional directional repricing (disabled until latency gate passes)."""

    name = "crypto_updown"

    def __init__(
        self,
        fee_per_leg: float = _DEFAULT_FEE,
        enable_repricing: bool = False,  # gated on Task 2 latency result
    ) -> None:
        self._fee = fee_per_leg
        self._repricing = enable_repricing

    def scan(self, markets: list[Market]) -> list[Signal]:
        signals: list[Signal] = []

        for market in markets:
            if market.closed:
                continue
            if not _is_updown_market(market):
                continue

            up, down = _find_up_down_outcomes(market)
            if up is None or down is None:
                continue

            # --- Complete-set arbitrage (always attempted) ---
            arb = find_arb(
                ask_up=up.best_ask,
                ask_down=down.best_ask,
                fee_per_leg=self._fee,
            )
            if arb is not None:
                profit = arb.expected_profit_per_unit
                for outcome, token_id in ((up, up.token_id), (down, down.token_id)):
                    signals.append(Signal(
                        market=market,
                        token_id=token_id,
                        fair_prob=0.5,  # arb: outcome doesn't matter
                        price=outcome.best_ask,
                        confidence=0.95,  # near-certain if arb math is correct
                        reason=f"arb: profit/unit={profit:.4f} fee={self._fee}",
                    ))

        return signals

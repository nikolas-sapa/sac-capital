"""07f — Variant tournament using walk-forward out-of-sample evaluation.

Splits forward-paper trades into a 60/40 train/validate split (sequential, no
shuffling). Each variant is evaluated only on the validate window — preventing
in-sample optimisation. The winner is the variant with the highest net PnL on
the out-of-sample window.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from equities.improve.variants import ParameterVariant


@dataclass(frozen=True)
class TournamentResult:
    winner: ParameterVariant
    winner_oos_pnl: float
    n_validated: int


def run_tournament(
    variants: Sequence[ParameterVariant],
    trades: Sequence[Any],
    score_fn: Callable[[Sequence[Any], dict[str, Any]], float],
) -> TournamentResult | None:
    """Evaluate variants on the out-of-sample half of `trades`.

    Args:
        variants:  List of ParameterVariants to evaluate.
        trades:    Sequential list of resolved ForwardPaperTrades.
        score_fn:  fn(trades_subset, params) → float (higher = better).

    Returns:
        TournamentResult with the winning variant, or None if < 4 trades.
    """
    if len(trades) < 4:
        return None

    split = int(len(trades) * 0.60)
    oos_trades = list(trades[split:])

    best_score: float | None = None
    best_variant: ParameterVariant | None = None

    for variant in variants:
        score = score_fn(oos_trades, variant.params)
        if best_score is None or score > best_score:
            best_score = score
            best_variant = variant

    if best_variant is None:
        return None

    return TournamentResult(
        winner=best_variant,
        winner_oos_pnl=best_score if best_score is not None else 0.0,
        n_validated=len(oos_trades),
    )

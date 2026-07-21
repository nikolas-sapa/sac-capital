"""07f — Variant tournament using walk-forward out-of-sample evaluation.

Splits forward-paper trades into a 60/40 train/validate split (sequential, no
shuffling). Each variant is evaluated only on the validate window — preventing
in-sample optimisation. The winner is the variant with the highest net PnL on
the out-of-sample window.

Also builds a per-trial "returns matrix" (rows = trades, columns = variants)
over the FULL trade history, for the promoter's overfitting check (see
equities/eval/overfitting.py). Assumes `score_fn` decomposes per-trade — i.e.
`score_fn([trade], params)` is a meaningful per-period return for that trial.
The matrix deliberately spans the full sample, not just the OOS slice:
combinatorially-symmetric cross-validation (CSCV) does its own internal
train/test splitting, so handing it the same 40% window would starve it of
data and make PBO estimates noisy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from equities.improve.variants import ParameterVariant


@dataclass(frozen=True)
class TournamentResult:
    winner: ParameterVariant
    winner_oos_pnl: float
    n_validated: int
    winner_index: int
    variant_names: list[str] = field(default_factory=list)
    # rows = trades (full history), columns = variants, in `variant_names` order.
    trial_returns_matrix: list[list[float]] = field(default_factory=list)


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
    best_index = -1

    for i, variant in enumerate(variants):
        score = score_fn(oos_trades, variant.params)
        if best_score is None or score > best_score:
            best_score = score
            best_variant = variant
            best_index = i

    if best_variant is None:
        return None

    # Full-history per-trial returns matrix for the overfitting check —
    # one column per variant, one row per trade in `trades` (not just OOS).
    trial_returns_matrix = [
        [score_fn([trade], variant.params) for variant in variants]
        for trade in trades
    ]

    return TournamentResult(
        winner=best_variant,
        winner_oos_pnl=best_score if best_score is not None else 0.0,
        n_validated=len(oos_trades),
        winner_index=best_index,
        variant_names=[v.name for v in variants],
        trial_returns_matrix=trial_returns_matrix,
    )

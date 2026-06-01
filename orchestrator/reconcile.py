from __future__ import annotations

from collections import defaultdict

from core.strategy import Signal


def reconcile(signals: list[Signal]) -> list[Signal]:
    """Deduplicate and resolve conflicting signals before execution.

    Rules:
    - Same (condition_id, token_id) from multiple strategies: keep the
      highest-confidence signal (don't double-bet the same outcome).
    - Same condition_id, different token_ids (opposing legs), unless all
      signals are arb: skip both to prevent opposing self-trades.
    - Arb sets: when ALL signals for a condition_id have reason starting with
      "arb:", keep the best-confidence signal per token (intentional both-legs buy).
    """
    by_market: dict[str, list[Signal]] = defaultdict(list)
    for sig in signals:
        by_market[sig.market.condition_id].append(sig)

    result: list[Signal] = []

    for _cond_id, sigs in by_market.items():
        token_ids = {s.token_id for s in sigs}

        if len(token_ids) == 1:
            # All same direction: keep highest-confidence signal
            result.append(max(sigs, key=lambda s: s.confidence))
        else:
            # Multiple tokens for same market
            all_arb = all(s.reason.startswith("arb:") for s in sigs)
            if all_arb:
                # Intentional complete-set arb: keep best-confidence per token
                by_token: dict[str, Signal] = {}
                for s in sigs:
                    if s.token_id not in by_token or s.confidence > by_token[s.token_id].confidence:
                        by_token[s.token_id] = s
                result.extend(by_token.values())
            else:
                # Opposing non-arb signals: skip all (no self-trade)
                pass

    return result

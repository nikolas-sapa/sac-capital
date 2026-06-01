from __future__ import annotations

from core.markets import Outcome

_MAX_SUM_ASK = 0.95    # above this → no math edge
_MIN_BIN_ASK = 0.01   # below this → already resolved
_MAX_BIN_ASK = 0.45   # above this → overpriced


def passes_filters(bins: list[Outcome]) -> bool:
    """Return True when the 3-bin portfolio has positive expected edge."""
    asks = [o.best_ask for o in bins]
    if any(a < _MIN_BIN_ASK for a in asks):
        return False
    if any(a > _MAX_BIN_ASK for a in asks):
        return False
    if sum(asks) > _MAX_SUM_ASK:
        return False
    return True

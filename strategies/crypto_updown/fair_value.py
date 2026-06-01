from __future__ import annotations

import math


def fair_up_prob(
    spot_now: float,
    strike: float,
    seconds_left: float,
    vol: float,
) -> float:
    """Normal approximation: probability that spot ends above strike at expiry.

    Uses a simplified lognormal model:
      log-return ~ N(0, sigma^2 * T)  where T = seconds_left / 86400 (days)
      P(Up) = P(spot_T > strike) = N(d) where d = log(spot/strike) / (sigma * sqrt(T))

    vol is daily log-return volatility. Clamps output to (1e-6, 1-1e-6).
    """
    if seconds_left <= 0:
        return 1.0 if spot_now > strike else 0.0

    T = max(seconds_left / 86400.0, 1e-9)
    sigma_t = vol * math.sqrt(T)

    if sigma_t < 1e-12:
        return 1.0 if spot_now > strike else 0.0

    d = math.log(spot_now / strike) / sigma_t
    p = _norm_cdf(d)
    return max(1e-6, min(1.0 - 1e-6, p))


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

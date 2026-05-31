"""Pure Bayesian functions for the probability module."""


def posterior(prior: float, likelihood_if_true: float, likelihood_if_false: float) -> float:
    """P(H|D) = prior*L_t / (prior*L_t + (1-prior)*L_f).

    Returns P(H|D) in [0,1].  If the denominator is zero, returns prior unchanged.
    """
    numerator = prior * likelihood_if_true
    denominator = numerator + (1.0 - prior) * likelihood_if_false
    if denominator == 0.0:
        return prior
    return numerator / denominator


def is_shock(
    prev_price: float,
    new_price: float,
    seconds: float,
    pct: float = 0.08,
    window: float = 60,
) -> bool:
    """True when an ABSOLUTE price move exceeds `pct` within `window` seconds.

    Prices are Polymarket probabilities in 0..1, so pct=0.08 means 8 pp.
    Shock condition: (seconds <= window) AND (abs(new_price - prev_price) > pct).
    Strictly greater than pct — equality is NOT a shock.
    """
    return seconds <= window and abs(new_price - prev_price) > pct

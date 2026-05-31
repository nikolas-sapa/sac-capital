"""
Fractional Kelly criterion sizing for binary prediction markets.

Given a market where YES pays 1/price (odds of b = (1-price)/price to 1),
the Kelly-optimal fraction of bankroll to wager is:

    f* = (b*p - q) / b

where:
    b     = (1 - price) / price  — net odds per unit risked
    p     = estimated probability of YES
    q     = 1 - p                — estimated probability of NO
    frac  = Kelly scaling factor (default 0.5 = half-Kelly)

Returns max(0, f* * frac), clamped at zero for negative-edge bets.
"""


def kelly_fraction(p: float, price: float, frac: float = 0.5) -> float:
    """Return the fractional Kelly bet size as a fraction of bankroll.

    Args:
        p:     Estimated probability that the outcome resolves YES (0 <= p <= 1).
        price: Current market price of the YES token (0 < price < 1).
        frac:  Kelly fraction multiplier, e.g. 0.5 for half-Kelly (default 0.5).

    Returns:
        Fraction of bankroll to bet, in [0, 1).  Returns 0.0 when there is no
        positive edge or when inputs are out of the valid range.

    Kelly math:
        b = (1 - price) / price   # net odds: win b units per 1 unit risked
        q = 1 - p                 # complementary probability
        f* = (b * p - q) / b      # full-Kelly fraction
        return max(0.0, f* * frac)
    """
    if not (0 < price < 1) or not (0 <= p <= 1):
        return 0.0
    b = (1 - price) / price
    q = 1 - p
    f = (b * p - q) / b
    return max(0.0, f * frac)

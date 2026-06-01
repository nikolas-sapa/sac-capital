import pytest
from datetime import datetime, timezone, timedelta
from core.markets import Market, Outcome
from strategies.weather.bins import find_bin, build_portfolio


def _market_with_bins(bin_midpoints: list[float]) -> Market:
    """Build a synthetic temperature market with labeled bins."""
    outcomes = []
    for mid in bin_midpoints:
        outcomes.append(Outcome(
            token_id=f"bin_{mid}",
            label=f"{mid}°",
            best_bid=0.25,
            best_ask=0.30,
        ))
    return Market(
        condition_id="cond_weather",
        question="What will the high temp be in New York today?",
        outcomes=outcomes,
        end_date=datetime.now(tz=timezone.utc) + timedelta(hours=20),
        closed=False,
    )


def test_find_bin_exact_match():
    market = _market_with_bins([68.0, 70.0, 72.0, 74.0])
    bin_id = find_bin(market, temp=70.0)
    assert bin_id == "bin_70.0"


def test_find_bin_rounds_to_nearest():
    market = _market_with_bins([68.0, 70.0, 72.0, 74.0])
    bin_id = find_bin(market, temp=71.2)
    assert bin_id == "bin_72.0"


def test_find_bin_gap_falls_back_to_nearest():
    # Temp 73 falls in a gap between 72 and 74 — falls back to nearest midpoint
    market = _market_with_bins([68.0, 70.0, 72.0, 74.0])
    bin_id = find_bin(market, temp=73.0)
    assert bin_id in ("bin_72.0", "bin_74.0")


def test_build_portfolio_returns_three_bins():
    from strategies.weather.consensus import ConsensusResult
    market = _market_with_bins([66.0, 68.0, 70.0, 72.0, 74.0])
    cr = ConsensusResult(center=70.0, spread=1.5, outlier=None, outlier_above=False)
    portfolio = build_portfolio(cr, market)
    assert len(portfolio) == 3


def test_build_portfolio_upward_skew_when_outlier_above():
    from strategies.weather.consensus import ConsensusResult
    market = _market_with_bins([66.0, 68.0, 70.0, 72.0, 74.0])
    cr = ConsensusResult(center=70.0, spread=2.0, outlier="ecmwf", outlier_above=True)
    portfolio = build_portfolio(cr, market)
    # Center bin + 1 below + 2 above OR center + 1 below + 1 above — must include center
    token_ids = [b.token_id for b in portfolio]
    assert "bin_70.0" in token_ids
    # Should be skewed upward (72 included, not 66)
    assert "bin_72.0" in token_ids


def test_build_portfolio_symmetric_when_no_outlier():
    from strategies.weather.consensus import ConsensusResult
    market = _market_with_bins([66.0, 68.0, 70.0, 72.0, 74.0])
    cr = ConsensusResult(center=70.0, spread=0.5, outlier=None, outlier_above=False)
    portfolio = build_portfolio(cr, market)
    token_ids = [b.token_id for b in portfolio]
    assert "bin_70.0" in token_ids
    assert "bin_68.0" in token_ids
    assert "bin_72.0" in token_ids

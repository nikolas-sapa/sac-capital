from datetime import datetime, timedelta, timezone

import pytest

from core.markets import Market, Outcome
from strategies.llm_probability.filters import is_candidate, candidate_markets, liquidity_score


def _market(
    *,
    yes_bid: float = 0.45,
    yes_ask: float = 0.55,
    no_bid: float = 0.40,
    no_ask: float = 0.50,
    hours_to_close: float = 72,
    closed: bool = False,
    volume_proxy: float = 500.0,  # not on Market directly; used via liquidity_score
) -> Market:
    end = datetime.now(tz=timezone.utc) + timedelta(hours=hours_to_close)
    return Market(
        condition_id="cond_test",
        question="Will X happen?",
        outcomes=[
            Outcome(token_id="yes", label="Yes", best_bid=yes_bid, best_ask=yes_ask),
            Outcome(token_id="no",  label="No",  best_bid=no_bid,  best_ask=no_ask),
        ],
        end_date=end,
        closed=closed,
    )


# --- is_candidate ---

def test_healthy_market_is_candidate():
    assert is_candidate(_market()) is True


def test_already_closed_is_rejected():
    assert is_candidate(_market(closed=True)) is False


def test_too_close_to_resolution_is_rejected():
    assert is_candidate(_market(hours_to_close=2)) is False


def test_no_book_on_yes_is_rejected():
    # ask=0 means no offer; bid=0+ask=0 → no tradeable book
    assert is_candidate(_market(yes_ask=0.0)) is False


def test_dead_zone_yes_ask_rejected():
    # ask very near 0 or 1 → market already resolved in crowd's eyes
    assert is_candidate(_market(yes_ask=0.03)) is False
    assert is_candidate(_market(yes_ask=0.97)) is False


def test_low_volume_market_still_candidate():
    # low volume is the EDGE — must NOT be rejected on volume alone
    assert is_candidate(_market(yes_bid=0.30, yes_ask=0.40)) is True


# --- liquidity_score ---

def test_tighter_spread_scores_higher():
    tight = _market(yes_bid=0.48, yes_ask=0.52)
    wide  = _market(yes_bid=0.20, yes_ask=0.80)
    assert liquidity_score(tight) > liquidity_score(wide)


def test_liquidity_score_bounded():
    score = liquidity_score(_market())
    assert 0.0 <= score <= 1.0


# --- candidate_markets ---

def test_candidate_markets_filters_list():
    markets = [
        _market(),                        # good
        _market(closed=True),             # rejected
        _market(hours_to_close=1),        # rejected
        _market(yes_ask=0.98),            # dead zone
    ]
    result = candidate_markets(markets)
    assert len(result) == 1


def test_candidate_markets_sorted_by_liquidity():
    m_tight = _market(yes_bid=0.48, yes_ask=0.52)
    m_wide  = _market(yes_bid=0.25, yes_ask=0.75)
    result = candidate_markets([m_wide, m_tight])
    # tighter spread (better liquidity for entry) comes first
    assert result[0].outcomes[0].best_ask == pytest.approx(0.52)

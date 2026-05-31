"""Tests for core/ledger.py — TDD step 1 (written before implementation)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market(condition_id: str = "cond-abc") -> Market:
    return Market(
        condition_id=condition_id,
        question="Will X happen?",
        outcomes=[
            Outcome(token_id="tok-yes", label="Yes", best_bid=0.55, best_ask=0.56),
            Outcome(token_id="tok-no", label="No", best_bid=0.43, best_ask=0.44),
        ],
        end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
        closed=False,
    )


def _signal(market: Market, token_id: str = "tok-yes") -> Signal:
    return Signal(
        market=market,
        token_id=token_id,
        fair_prob=0.65,
        price=0.56,
        confidence=0.8,
        reason="test reason",
    )


def _fill(
    market: Market,
    token_id: str = "tok-yes",
    stake: float = 10.0,
    shares: float = 17.86,
    avg_price: float = 0.56,
) -> Fill:
    return Fill(
        signal=_signal(market, token_id),
        stake=stake,
        shares=shares,
        avg_price=avg_price,
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        mode="paper",
    )


# ---------------------------------------------------------------------------
# record + persistence
# ---------------------------------------------------------------------------

def test_record_appends_row(tmp_path):
    """record() stores a fill that is retrievable via open_positions()."""
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market = _market()
    fill = _fill(market)

    ledger.record(fill)

    positions = ledger.open_positions()
    assert len(positions) == 1
    pos = positions[0]
    assert pos["condition_id"] == market.condition_id
    assert pos["token_id"] == fill.signal.token_id
    assert pos["stake"] == pytest.approx(fill.stake)
    assert pos["shares"] == pytest.approx(fill.shares)


def test_record_creates_csv_mirror(tmp_path):
    """record() also writes a CSV file alongside the db."""
    db_path = tmp_path / "ledger.db"
    csv_path = tmp_path / "ledger.csv"
    ledger = Ledger(db_path)
    market = _market()
    fill = _fill(market)

    ledger.record(fill)

    assert csv_path.exists()
    content = csv_path.read_text()
    assert market.condition_id in content


def test_persistence_across_instances(tmp_path):
    """A new Ledger opened on the same path sees previously recorded rows."""
    db_path = tmp_path / "ledger.db"

    ledger1 = Ledger(db_path)
    market = _market()
    ledger1.record(_fill(market))

    # Open a brand-new instance on the same path
    ledger2 = Ledger(db_path)
    positions = ledger2.open_positions()
    assert len(positions) == 1
    assert positions[0]["condition_id"] == market.condition_id


# ---------------------------------------------------------------------------
# open_positions
# ---------------------------------------------------------------------------

def test_open_positions_returns_unresolved_only(tmp_path):
    """open_positions() excludes rows that have been resolved.

    resolve() settles ALL unresolved rows for the given condition_id —
    winners and losers alike — so after resolution none remain open for
    that condition.
    """
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market = _market()
    market2 = _market("cond-xyz")

    ledger.record(_fill(market, token_id="tok-yes"))
    ledger.record(_fill(market, token_id="tok-no"))
    ledger.record(_fill(market2, token_id="tok-yes"))  # different condition

    # All three unresolved
    assert len(ledger.open_positions()) == 3

    ledger.resolve(market.condition_id, "tok-yes")

    # Both rows for market are now resolved; only market2's row remains open
    open_pos = ledger.open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["condition_id"] == "cond-xyz"


# ---------------------------------------------------------------------------
# resolve + pnl
# ---------------------------------------------------------------------------

def test_resolve_winning_position_pnl(tmp_path):
    """Winning position: pnl = shares - stake."""
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market = _market()
    stake = 10.0
    shares = 17.86

    ledger.record(_fill(market, token_id="tok-yes", stake=stake, shares=shares))
    resolved = ledger.resolve(market.condition_id, "tok-yes")

    assert resolved == 1
    assert ledger.pnl() == pytest.approx(shares - stake)


def test_resolve_losing_position_pnl(tmp_path):
    """Losing position: pnl = -stake."""
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market = _market()
    stake = 10.0
    shares = 17.86

    ledger.record(_fill(market, token_id="tok-yes", stake=stake, shares=shares))
    ledger.resolve(market.condition_id, "tok-no")  # tok-no wins → tok-yes loses

    assert ledger.pnl() == pytest.approx(-stake)


def test_resolve_multiple_positions_same_condition(tmp_path):
    """resolve() handles multiple rows for the same condition_id."""
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market = _market()

    stake_yes = 10.0
    shares_yes = 17.86
    stake_no = 5.0
    shares_no = 11.36

    ledger.record(_fill(market, token_id="tok-yes", stake=stake_yes, shares=shares_yes))
    ledger.record(_fill(market, token_id="tok-no", stake=stake_no, shares=shares_no))

    resolved = ledger.resolve(market.condition_id, "tok-yes")

    assert resolved == 2
    # tok-yes wins: shares_yes - stake_yes; tok-no loses: -stake_no
    expected_pnl = (shares_yes - stake_yes) + (-stake_no)
    assert ledger.pnl() == pytest.approx(expected_pnl)


def test_resolve_returns_count_of_rows_resolved(tmp_path):
    """resolve() returns the number of rows it updated."""
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market = _market()

    ledger.record(_fill(market, token_id="tok-yes"))
    ledger.record(_fill(market, token_id="tok-yes"))  # second fill same token

    count = ledger.resolve(market.condition_id, "tok-yes")
    assert count == 2


def test_resolve_does_not_affect_other_conditions(tmp_path):
    """Resolving one condition does not change rows for a different condition."""
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market_a = _market("cond-A")
    market_b = _market("cond-B")

    ledger.record(_fill(market_a, token_id="tok-yes"))
    ledger.record(_fill(market_b, token_id="tok-yes"))

    ledger.resolve("cond-A", "tok-yes")

    open_pos = ledger.open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["condition_id"] == "cond-B"


def test_pnl_zero_when_nothing_resolved(tmp_path):
    """pnl() returns 0.0 when no rows are resolved."""
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market = _market()
    ledger.record(_fill(market))

    assert ledger.pnl() == 0.0


def test_pnl_accumulates_across_markets(tmp_path):
    """pnl() sums realized pnl across all resolved rows."""
    db_path = tmp_path / "ledger.db"
    ledger = Ledger(db_path)
    market_a = _market("cond-A")
    market_b = _market("cond-B")

    # Market A: win 7.86
    ledger.record(_fill(market_a, token_id="tok-yes", stake=10.0, shares=17.86))
    ledger.resolve("cond-A", "tok-yes")

    # Market B: lose 5.0
    ledger.record(_fill(market_b, token_id="tok-yes", stake=5.0, shares=11.36))
    ledger.resolve("cond-B", "tok-no")

    expected = (17.86 - 10.0) + (-5.0)
    assert ledger.pnl() == pytest.approx(expected)

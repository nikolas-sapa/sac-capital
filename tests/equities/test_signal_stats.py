"""Tests for signal_stats — regime-conditional signal win-rate tracking."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from equities.ledger_equity import EquityLedger
from equities.signal_stats import signal_stats_line, update_signal_stats
from equities.strategy import Recommendation, Sleeve
from core.assets.instrument import Instrument, CapTier


@pytest.fixture
def temp_ledger():
    """Create a temporary ledger for testing."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ledger.db"
        ledger = EquityLedger(str(db_path))
        yield ledger
        ledger.close()


def _make_rec(ticker: str, entry: float = 100.0) -> Recommendation:
    """Helper to create a test recommendation."""
    return Recommendation(
        instrument=Instrument(
            ticker=ticker,
            name=f"{ticker} Corp",
            exchange="NASDAQ",
            cap_tier=CapTier.LARGE,
        ),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=entry,
        stop_loss=entry * 0.95,
        take_profit=entry * 1.10,
        size_pct=0.02,
        confidence=0.7,
        catalyst="test catalyst",
        thesis="test thesis",
        horizon="1-2 weeks",
        analysis={"signal_class": "earnings_approaching"},
    )


class TestUpdateSignalStats:
    """Tests for update_signal_stats(ledger, regime, window_days)."""

    def test_empty_ledger_creates_table(self, temp_ledger):
        """update_signal_stats should create signal_stats table even if no positions."""
        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)
        # Verify table exists by querying it
        cursor = temp_ledger._con.execute(
            "SELECT COUNT(*) FROM signal_stats"
        )
        assert cursor.fetchone()[0] == 0

    def test_single_winning_position(self, temp_ledger):
        """Single closed winning position should yield win_rate=1.0."""
        rec = _make_rec("AAPL", entry=100.0)
        now = datetime.now(tz=timezone.utc)

        # Open position
        pos_id = temp_ledger.open_position(
            rec, shares=100, fill_price=100.0, opened_at=now,
            mode="paper", strategy="test", signal_class="earnings_approaching"
        )

        # Close as winner
        temp_ledger.close_position(
            pos_id, exit_price=110.0, exit_reason="tp_hit",
            closed_at=now + timedelta(days=5)
        )

        # Update stats
        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        # Verify
        row = temp_ledger._con.execute(
            "SELECT win_rate, trades FROM signal_stats WHERE signal_class=? AND regime=?",
            ("earnings_approaching", "high_vol")
        ).fetchone()
        assert row is not None
        assert row[0] == 1.0  # win_rate
        assert row[1] == 1    # trades

    def test_mixed_win_loss_positions(self, temp_ledger):
        """Multiple closed positions with mixed outcomes."""
        now = datetime.now(tz=timezone.utc)

        # Two winners
        for i in range(2):
            rec = _make_rec("AAPL", entry=100.0)
            pos_id = temp_ledger.open_position(
                rec, shares=100, fill_price=100.0, opened_at=now + timedelta(days=i),
                mode="paper", strategy="test", signal_class="earnings_approaching"
            )
            temp_ledger.close_position(
                pos_id, exit_price=110.0, exit_reason="tp_hit",
                closed_at=now + timedelta(days=i+5)
            )

        # One loser
        rec = _make_rec("GOOGL", entry=150.0)
        pos_id = temp_ledger.open_position(
            rec, shares=50, fill_price=150.0, opened_at=now + timedelta(days=2),
            mode="paper", strategy="test", signal_class="earnings_approaching"
        )
        temp_ledger.close_position(
            pos_id, exit_price=140.0, exit_reason="sl_hit",
            closed_at=now + timedelta(days=7)
        )

        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        row = temp_ledger._con.execute(
            "SELECT win_rate, trades FROM signal_stats WHERE signal_class=? AND regime=?",
            ("earnings_approaching", "high_vol")
        ).fetchone()
        assert row is not None
        assert row[0] == pytest.approx(2.0 / 3.0)  # win_rate
        assert row[1] == 3  # trades

    def test_multiple_signal_classes(self, temp_ledger):
        """Different signal classes tracked separately."""
        now = datetime.now(tz=timezone.utc)

        # Earnings winner
        rec1 = _make_rec("AAPL", entry=100.0)
        rec1.analysis["signal_class"] = "earnings_approaching"
        pos_id = temp_ledger.open_position(
            rec1, shares=100, fill_price=100.0, opened_at=now,
            mode="paper", strategy="test", signal_class="earnings_approaching"
        )
        temp_ledger.close_position(
            pos_id, exit_price=110.0, exit_reason="tp_hit",
            closed_at=now + timedelta(days=5)
        )

        # Filing winner
        rec2 = _make_rec("MSFT", entry=100.0)
        rec2.analysis["signal_class"] = "material_filing"
        pos_id = temp_ledger.open_position(
            rec2, shares=100, fill_price=100.0, opened_at=now,
            mode="paper", strategy="test", signal_class="material_filing"
        )
        temp_ledger.close_position(
            pos_id, exit_price=105.0, exit_reason="tp_hit",
            closed_at=now + timedelta(days=3)
        )

        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        # Both should exist
        rows = temp_ledger._con.execute(
            "SELECT signal_class, win_rate FROM signal_stats WHERE regime=?",
            ("high_vol",)
        ).fetchall()
        classes = {r[0]: r[1] for r in rows}
        assert "earnings_approaching" in classes
        assert "material_filing" in classes
        assert classes["earnings_approaching"] == 1.0
        assert classes["material_filing"] == 1.0

    def test_window_filtering(self, temp_ledger):
        """Positions closed outside window are excluded."""
        now = datetime.now(tz=timezone.utc)

        # Inside window (5 days ago)
        rec = _make_rec("AAPL", entry=100.0)
        pos_id = temp_ledger.open_position(
            rec, shares=100, fill_price=100.0, opened_at=now - timedelta(days=5),
            mode="paper", strategy="test", signal_class="earnings_approaching"
        )
        temp_ledger.close_position(
            pos_id, exit_price=110.0, exit_reason="tp_hit",
            closed_at=now - timedelta(days=1)
        )

        # Outside 30-day window (40 days ago)
        rec = _make_rec("GOOGL", entry=100.0)
        pos_id = temp_ledger.open_position(
            rec, shares=100, fill_price=100.0, opened_at=now - timedelta(days=40),
            mode="paper", strategy="test", signal_class="earnings_approaching"
        )
        temp_ledger.close_position(
            pos_id, exit_price=95.0, exit_reason="sl_hit",
            closed_at=now - timedelta(days=35)
        )

        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        row = temp_ledger._con.execute(
            "SELECT trades FROM signal_stats WHERE signal_class=? AND regime=?",
            ("earnings_approaching", "high_vol")
        ).fetchone()
        assert row is not None
        assert row[0] == 1  # Only the inside-window position counted

    def test_excludes_void_and_rejected(self, temp_ledger):
        """Void and rejected positions should not affect stats."""
        now = datetime.now(tz=timezone.utc)

        # Winner
        rec = _make_rec("AAPL", entry=100.0)
        pos_id = temp_ledger.open_position(
            rec, shares=100, fill_price=100.0, opened_at=now,
            mode="paper", strategy="test", signal_class="earnings_approaching"
        )
        temp_ledger.close_position(
            pos_id, exit_price=110.0, exit_reason="tp_hit",
            closed_at=now + timedelta(days=5)
        )

        # Void position (should be ignored)
        rec = _make_rec("GOOGL", entry=100.0)
        pos_id = temp_ledger.open_position(
            rec, shares=100, fill_price=100.0, opened_at=now,
            mode="paper", strategy="test", signal_class="earnings_approaching",
            status="void"
        )

        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        row = temp_ledger._con.execute(
            "SELECT trades FROM signal_stats WHERE signal_class=? AND regime=?",
            ("earnings_approaching", "high_vol")
        ).fetchone()
        assert row is not None
        assert row[0] == 1  # Only winner counted

    def test_multiple_regimes(self, temp_ledger):
        """Same data with different regime labels."""
        now = datetime.now(tz=timezone.utc)

        # Create a winning position
        rec = _make_rec("AAPL", entry=100.0)
        pos_id = temp_ledger.open_position(
            rec, shares=100, fill_price=100.0, opened_at=now,
            mode="paper", strategy="test", signal_class="earnings_approaching"
        )
        temp_ledger.close_position(
            pos_id, exit_price=110.0, exit_reason="tp_hit",
            closed_at=now + timedelta(days=5)
        )

        # Update with high_vol regime
        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        # Now update again with low_vol regime (overwrites)
        update_signal_stats(temp_ledger, regime="low_vol", window_days=30)

        # low_vol should have the data
        row = temp_ledger._con.execute(
            "SELECT trades FROM signal_stats WHERE signal_class=? AND regime=?",
            ("earnings_approaching", "low_vol")
        ).fetchone()
        assert row is not None
        assert row[0] == 1


class TestSignalStatsLine:
    """Tests for signal_stats_line(ledger, signal_class, regime)."""

    def test_insufficient_trades_returns_none(self, temp_ledger):
        """min_trades=10 by default; fewer trades return None."""
        now = datetime.now(tz=timezone.utc)

        # Create 5 trades
        for i in range(5):
            rec = _make_rec("AAPL", entry=100.0 + i)
            pos_id = temp_ledger.open_position(
                rec, shares=100, fill_price=100.0 + i, opened_at=now + timedelta(days=i),
                mode="paper", strategy="test", signal_class="earnings_approaching"
            )
            temp_ledger.close_position(
                pos_id, exit_price=110.0 + i, exit_reason="tp_hit",
                closed_at=now + timedelta(days=i+1)
            )

        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        line = signal_stats_line(temp_ledger, "earnings_approaching", "high_vol", min_trades=10)
        assert line is None

    def test_sufficient_trades_returns_formatted_line(self, temp_ledger):
        """With >= min_trades, return formatted line."""
        now = datetime.now(tz=timezone.utc)

        # Create 15 trades: 10 winners, 5 losers
        for i in range(10):
            rec = _make_rec("AAPL", entry=100.0)
            pos_id = temp_ledger.open_position(
                rec, shares=100, fill_price=100.0, opened_at=now + timedelta(days=i),
                mode="paper", strategy="test", signal_class="earnings_approaching"
            )
            temp_ledger.close_position(
                pos_id, exit_price=110.0, exit_reason="tp_hit",
                closed_at=now + timedelta(days=i+1)
            )

        for i in range(5):
            rec = _make_rec("GOOGL", entry=100.0)
            pos_id = temp_ledger.open_position(
                rec, shares=100, fill_price=100.0, opened_at=now + timedelta(days=i+10),
                mode="paper", strategy="test", signal_class="earnings_approaching"
            )
            temp_ledger.close_position(
                pos_id, exit_price=95.0, exit_reason="sl_hit",
                closed_at=now + timedelta(days=i+11)
            )

        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        line = signal_stats_line(temp_ledger, "earnings_approaching", "high_vol", min_trades=10)
        assert line is not None
        assert "earnings_approaching" in line
        assert "high_vol" in line
        assert "67%" in line  # 10/15 = 66.7%
        assert "15 trades" in line

    def test_line_format(self, temp_ledger):
        """Verify the exact format of the output line."""
        now = datetime.now(tz=timezone.utc)

        # Create 10 winning trades
        for i in range(10):
            rec = _make_rec("AAPL", entry=100.0)
            pos_id = temp_ledger.open_position(
                rec, shares=100, fill_price=100.0, opened_at=now + timedelta(days=i),
                mode="paper", strategy="test", signal_class="material_filing"
            )
            temp_ledger.close_position(
                pos_id, exit_price=110.0, exit_reason="tp_hit",
                closed_at=now + timedelta(days=i+1)
            )

        update_signal_stats(temp_ledger, regime="low_vol", window_days=30)

        line = signal_stats_line(temp_ledger, "material_filing", "low_vol", min_trades=10)
        assert line is not None
        # Expected format: "Historical 30d win rate for material_filing in low_vol: 100% over 10 trades — weight conviction accordingly."
        assert line.startswith("Historical")
        assert "material_filing" in line
        assert "low_vol" in line
        assert "100%" in line
        assert "10 trades" in line
        assert "weight conviction accordingly" in line

    def test_zero_trades_for_class_returns_none(self, temp_ledger):
        """No trades for a signal_class should return None."""
        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        line = signal_stats_line(temp_ledger, "nonexistent_class", "high_vol", min_trades=0)
        assert line is None

    def test_default_min_trades_is_10(self, temp_ledger):
        """Default min_trades should be 10."""
        now = datetime.now(tz=timezone.utc)

        # Create 9 trades (below default min_trades)
        for i in range(9):
            rec = _make_rec("AAPL", entry=100.0)
            pos_id = temp_ledger.open_position(
                rec, shares=100, fill_price=100.0, opened_at=now + timedelta(days=i),
                mode="paper", strategy="test", signal_class="earnings_approaching"
            )
            temp_ledger.close_position(
                pos_id, exit_price=110.0, exit_reason="tp_hit",
                closed_at=now + timedelta(days=i+1)
            )

        update_signal_stats(temp_ledger, regime="high_vol", window_days=30)

        # Should return None with default min_trades=10
        line = signal_stats_line(temp_ledger, "earnings_approaching", "high_vol")
        assert line is None

        # Should return line with min_trades=9
        line = signal_stats_line(temp_ledger, "earnings_approaching", "high_vol", min_trades=9)
        assert line is not None


class TestSignalClassColumn:
    """Tests for signal_class column in positions table."""

    def test_signal_class_stored_in_position(self, temp_ledger):
        """signal_class parameter should be stored in positions."""
        rec = _make_rec("AAPL", entry=100.0)
        now = datetime.now(tz=timezone.utc)

        pos_id = temp_ledger.open_position(
            rec, shares=100, fill_price=100.0, opened_at=now,
            mode="paper", strategy="test", signal_class="earnings_approaching"
        )

        row = temp_ledger._con.execute(
            "SELECT signal_class FROM positions WHERE id=?", (pos_id,)
        ).fetchone()
        assert row is not None
        assert row[0] == "earnings_approaching"

    def test_signal_class_default_empty_string(self, temp_ledger):
        """signal_class should default to empty string."""
        rec = _make_rec("AAPL", entry=100.0)
        now = datetime.now(tz=timezone.utc)

        # Call open_position without signal_class
        pos_id = temp_ledger.open_position(
            rec, shares=100, fill_price=100.0, opened_at=now,
            mode="paper", strategy="test"
        )

        row = temp_ledger._con.execute(
            "SELECT signal_class FROM positions WHERE id=?", (pos_id,)
        ).fetchone()
        assert row is not None
        assert row[0] == ""

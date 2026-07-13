"""Tests for EquityPaperTracker."""
import pytest

from core.assets.instrument import CapTier, Instrument
from equities.ledger_equity import EquityLedger
from equities.paper import EquityPaperTracker
from equities.strategy import Recommendation, Sleeve


def _rec(ticker: str = "ARWR", entry: float = 74.0, stop: float = 68.0, tp: float = 88.0) -> Recommendation:
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=entry,
        stop_loss=stop,
        take_profit=tp,
        size_pct=0.02,
        confidence=0.72,
        catalyst="test",
        thesis="test",
        horizon="2 weeks",
    )


class FakePrices:
    def __init__(self, prices: dict[str, float] | None = None):
        self._prices = dict(prices or {})

    def latest_close(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def set(self, ticker: str, price: float) -> None:
        self._prices[ticker] = price


def test_mark_uses_fallback_price_when_live_price_missing(tmp_path):
    ledger = EquityLedger(tmp_path / "e.db")
    tracker = EquityPaperTracker(
        ledger,
        FakePrices({}),
        price_fallback=lambda ticker: 79.0 if ticker == "ARWR" else None,
    )
    tracker.open_position(_rec("ARWR", entry=74.0, stop=68.0, tp=120.0), shares=2.0, fill_price=74.0)
    tracker.mark_and_check_exits()
    pos = ledger.open_positions()[0]
    assert pos["mark_price"] == pytest.approx(79.0)
    assert pos["unrealized_pnl"] == pytest.approx((79.0 - 74.0) * 2.0)


def test_open_position_recorded(tmp_path):
    ledger = EquityLedger(tmp_path / "e.db")
    tracker = EquityPaperTracker(ledger, FakePrices({"ARWR": 74.0}))
    fill = tracker.open_position(_rec(), shares=2.5, fill_price=74.0, strategy="test")
    assert fill.shares == pytest.approx(2.5)
    assert len(ledger.open_positions()) == 1


def test_stop_hit_fires_exit(tmp_path):
    ledger = EquityLedger(tmp_path / "e.db")
    tracker = EquityPaperTracker(ledger, FakePrices({"ARWR": 65.0}))
    tracker.open_position(_rec("ARWR", entry=74.0, stop=68.0), shares=1.0, fill_price=74.0)
    exits = tracker.mark_and_check_exits()
    assert len(exits) == 1
    assert exits[0].reason == "stop_hit"
    assert len(ledger.open_positions()) == 0


def test_target_touch_activates_trail_not_exit(tmp_path):
    """A take_profit touch is now the trail activator, not an exit (exit engine v2)."""
    ledger = EquityLedger(tmp_path / "e.db")
    tracker = EquityPaperTracker(ledger, FakePrices({"ARWR": 90.0}))
    tracker.open_position(_rec("ARWR", tp=88.0), shares=1.0, fill_price=74.0)
    exits = tracker.mark_and_check_exits()
    assert exits == []
    assert len(ledger.open_positions()) == 1


def test_no_exit_within_bands(tmp_path):
    ledger = EquityLedger(tmp_path / "e.db")
    tracker = EquityPaperTracker(ledger, FakePrices({"ARWR": 76.0}))
    tracker.open_position(_rec("ARWR", stop=68.0, tp=88.0), shares=1.0, fill_price=74.0)
    exits = tracker.mark_and_check_exits()
    assert exits == []
    assert len(ledger.open_positions()) == 1


def test_mark_updates_unrealized_pnl(tmp_path):
    ledger = EquityLedger(tmp_path / "e.db")
    tracker = EquityPaperTracker(ledger, FakePrices({"ARWR": 80.0}))
    tracker.open_position(_rec("ARWR", stop=68.0, tp=120.0), shares=2.0, fill_price=74.0)
    tracker.mark_and_check_exits()
    pos = ledger.open_positions()[0]
    assert pos["mark_price"] == pytest.approx(80.0)
    assert pos["unrealized_pnl"] == pytest.approx((80.0 - 74.0) * 2.0)


def test_winner_trails_instead_of_capping(tmp_path):
    """Price rides through take_profit; tracker holds, then exits on the trail."""
    ledger = EquityLedger(tmp_path / "e.db")
    prices = FakePrices()
    tracker = EquityPaperTracker(ledger, prices, trail_r=1.5)
    rec = _rec("TEST", entry=100.0, stop=90.0, tp=120.0)
    tracker.open_position(rec, shares=10.0, fill_price=100.0)

    prices.set("TEST", 125.0)          # through target: NO exit (trail activates)
    assert tracker.mark_and_check_exits() == []

    prices.set("TEST", 130.0)          # new high water 130
    assert tracker.mark_and_check_exits() == []

    prices.set("TEST", 114.0)          # 130 - 1.5*10 = 115 trail -> exit
    fired = tracker.mark_and_check_exits()
    assert len(fired) == 1 and fired[0].reason == "trailing_stop_hit"

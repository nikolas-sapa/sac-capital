from datetime import datetime

from core.assets.instrument import Instrument, CapTier
from equities.strategy import Recommendation, Sleeve
from equities.ledger_equity import EquityLedger


def _rec() -> Recommendation:
    inst = Instrument(ticker="ACME", name="Acme", exchange="NASDAQ", cap_tier=CapTier.SMALL)
    return Recommendation(
        instrument=inst, sleeve=Sleeve.SWING, side="buy",
        entry=10.0, stop_loss=9.0, take_profit=13.0,
        size_pct=0.03, confidence=0.6, catalyst="beat", thesis="t", horizon="2-10d",
    )


def test_open_position_appears_in_open_positions(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=5.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2, 14, 30), mode="paper", strategy="swing_v1")
    open_pos = led.open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["ticker"] == "ACME"
    assert open_pos[0]["shares"] == 5.0
    assert open_pos[0]["status"] == "open"
    assert open_pos[0]["strategy"] == "swing_v1"
    led.close()


def test_mark_updates_unrealized(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=5.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2), mode="paper")
    led.mark("ACME", price=12.0)
    pos = led.open_positions()[0]
    assert pos["mark_price"] == 12.0
    assert pos["unrealized_pnl"] == 10.0   # (12-10)*5
    led.close()


def test_close_sets_realized_and_removes_from_open(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    pid = led.open_position(_rec(), shares=5.0, fill_price=10.0,
                            opened_at=datetime(2026, 1, 2), mode="paper")
    led.close_position(pid, exit_price=13.0, exit_reason="target",
                       closed_at=datetime(2026, 1, 5))
    assert led.open_positions() == []
    assert led.realized_pnl() == 15.0      # (13-10)*5
    led.close()


def test_csv_mirror_written(tmp_path):
    led = EquityLedger(tmp_path / "eq.db")
    led.open_position(_rec(), shares=5.0, fill_price=10.0,
                      opened_at=datetime(2026, 1, 2), mode="paper", strategy="swing_v1")
    csv_path = (tmp_path / "eq.csv")
    assert csv_path.exists()
    assert "ACME" in csv_path.read_text()
    led.close()

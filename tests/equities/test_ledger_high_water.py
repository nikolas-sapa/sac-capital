import json
from datetime import datetime, timezone

from equities.ledger_equity import EquityLedger
from equities.strategy import Recommendation, Sleeve
from core.assets.instrument import Instrument, CapTier


def _rec(**kw):
    defaults = dict(
        instrument=Instrument("TEST", "Test Co", "NYSE", CapTier.LARGE),
        sleeve=Sleeve.SWING, side="buy", entry=100.0, stop_loss=95.0,
        take_profit=115.0, size_pct=0.02, confidence=0.7,
        catalyst="c", thesis="t", horizon="2-3 weeks",
    )
    defaults.update(kw)
    return Recommendation(**defaults)


def test_mark_ratchets_high_water(tmp_path):
    ledger = EquityLedger(tmp_path / "eq.db")
    pid = ledger.open_position(_rec(), 10.0, 100.0, datetime.now(tz=timezone.utc), mode="paper")
    ledger.mark("TEST", 108.0)
    ledger.mark("TEST", 103.0)   # pullback must NOT lower high water
    pos = {p["id"]: p for p in ledger.open_positions()}[pid]
    assert pos["high_water_price"] == 108.0
    assert pos["mark_price"] == 103.0


def test_horizon_persisted_in_analysis_json(tmp_path):
    ledger = EquityLedger(tmp_path / "eq.db")
    pid = ledger.open_position(_rec(horizon="1-2 weeks"), 10.0, 100.0,
                               datetime.now(tz=timezone.utc), mode="paper")
    pos = {p["id"]: p for p in ledger.open_positions()}[pid]
    assert json.loads(pos["analysis_json"])["horizon"] == "1-2 weeks"


def test_update_analysis_field(tmp_path):
    ledger = EquityLedger(tmp_path / "eq.db")
    pid = ledger.open_position(_rec(), 10.0, 100.0, datetime.now(tz=timezone.utc), mode="paper")
    ledger.update_analysis_field(pid, "tranche", 2)
    pos = {p["id"]: p for p in ledger.open_positions()}[pid]
    assert json.loads(pos["analysis_json"])["tranche"] == 2

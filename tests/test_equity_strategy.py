from core.assets.instrument import Instrument, CapTier
from equities.strategy import Recommendation, Sleeve, ContinuousStrategy


def _inst() -> Instrument:
    return Instrument(ticker="ACME", name="Acme", exchange="NASDAQ", cap_tier=CapTier.SMALL)


def test_swing_rec_carries_stops():
    rec = Recommendation(
        instrument=_inst(), sleeve=Sleeve.SWING, side="buy",
        entry=10.0, stop_loss=9.0, take_profit=13.0,
        size_pct=0.03, confidence=0.6, catalyst="earnings beat",
        thesis="under-covered, gapped on beat", horizon="2-10d",
    )
    assert rec.sleeve is Sleeve.SWING
    assert rec.stop_loss == 9.0


def test_core_sleeve_omits_stops():
    rec = Recommendation(
        instrument=_inst(), sleeve=Sleeve.CORE, side="buy",
        entry=200.0, stop_loss=None, take_profit=None,
        size_pct=0.0, confidence=0.5, catalyst="quality screen",
        thesis="accumulate", horizon="months",
    )
    assert rec.stop_loss is None


def test_strategy_protocol_is_runtime_checkable():
    class Dummy:
        name = "dummy"
        def scan(self, universe):
            return []
    assert isinstance(Dummy(), ContinuousStrategy)

from core.assets.instrument import Instrument, CapTier


def test_instrument_holds_identity_and_cap_tier():
    inst = Instrument(ticker="ACME", name="Acme Corp", exchange="NASDAQ", cap_tier=CapTier.SMALL)
    assert inst.ticker == "ACME"
    assert inst.cap_tier is CapTier.SMALL


def test_instrument_is_frozen():
    import dataclasses
    inst = Instrument(ticker="ACME", name="Acme Corp", exchange="NASDAQ", cap_tier=CapTier.LARGE)
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        inst.ticker = "OTHER"  # type: ignore[misc]

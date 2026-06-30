from datetime import date, timedelta

from core.assets.instrument import CapTier, Instrument
from equities.data.politician_disclosures import DisclosureFetch, PoliticianTrade
from equities.screen.event_screen import EventType
from equities.screen.politician_screen import PoliticianScreen


class _StubProvider:
    def __init__(self, trades):
        self._trades = trades

    def fetch(self):
        return DisclosureFetch(trades=self._trades, fetched_at="t", source="house", error=None)


def test_politician_screen_emits_candidate_for_universe_ticker():
    today = date.today()
    trade = PoliticianTrade(
        ticker="MSFT", politician="Rep X", chamber="house", transaction_type="buy",
        owner="self", amount_min=50001, amount_max=100000,
        transaction_date=today - timedelta(days=10), date_filed=today - timedelta(days=3),
        filing_lag_days=7, source="house", source_url="http://x",
    )
    universe = [Instrument(ticker="MSFT", name="Microsoft", exchange="NASDAQ", cap_tier=CapTier.LARGE)]
    out = PoliticianScreen(_StubProvider([trade])).scan(universe)
    assert len(out) == 1
    assert out[0].instrument.ticker == "MSFT"
    assert out[0].event_type == EventType.POLITICIAN_DISCLOSURE
    assert 0.0 < out[0].urgency <= 1.0

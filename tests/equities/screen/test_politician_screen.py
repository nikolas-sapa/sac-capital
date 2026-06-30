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


def _trade(ticker, who, days_ago_filed, amount_max=100000, ttype="buy"):
    today = date.today()
    return PoliticianTrade(
        ticker=ticker, politician=who, chamber="house", transaction_type=ttype,
        owner="self", amount_min=1, amount_max=amount_max,
        transaction_date=today - timedelta(days=days_ago_filed + 5),
        date_filed=today - timedelta(days=days_ago_filed),
        filing_lag_days=5, source="house", source_url="http://x",
    )


_AAPL = Instrument(ticker="AAPL", name="Apple", exchange="NASDAQ", cap_tier=CapTier.LARGE)
_TSLA = Instrument(ticker="TSLA", name="Tesla", exchange="NASDAQ", cap_tier=CapTier.LARGE)


def test_cluster_buy_scores_higher_than_single():
    cluster = _StubProvider([_trade("AAPL", "A", 2), _trade("AAPL", "B", 3), _trade("AAPL", "C", 4)])
    single = _StubProvider([_trade("TSLA", "A", 2)])
    c_aapl = PoliticianScreen(cluster).scan([_AAPL])
    c_tsla = PoliticianScreen(single).scan([_TSLA])
    assert c_aapl and c_aapl[0].event_type == EventType.POLITICIAN_DISCLOSURE
    assert c_aapl[0].urgency > c_tsla[0].urgency


def test_sells_and_off_universe_excluded():
    prov = _StubProvider([_trade("AAPL", "A", 2, ttype="sell"), _trade("NVDA", "B", 2)])
    out = PoliticianScreen(prov).scan([_AAPL])  # NVDA not in universe, AAPL only a sell
    assert out == []


def test_stale_filing_rejected():
    prov = _StubProvider([_trade("AAPL", "A", days_ago_filed=99)])
    assert PoliticianScreen(prov, lookback_days=30).scan([_AAPL]) == []

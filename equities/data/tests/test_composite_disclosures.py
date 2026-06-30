from equities.data.composite_disclosures import CompositeDisclosureProvider
from equities.data.politician_disclosures import DisclosureFetch, PoliticianTrade


def _trade(ticker):
    return PoliticianTrade(
        ticker=ticker, politician="X", chamber="house", transaction_type="buy",
        owner="self", amount_min=1, amount_max=2, transaction_date=None,
        date_filed=None, filing_lag_days=None, source="s", source_url="u",
    )


class _Stub:
    def __init__(self, trades, source, error=None):
        self._f = DisclosureFetch(trades=trades, fetched_at="t", source=source, error=error)

    def fetch(self):
        return self._f


class _Raises:
    def fetch(self):
        raise RuntimeError("boom")


def test_merges_trades_and_sources():
    c = CompositeDisclosureProvider([
        _Stub([_trade("AAA")], "house"),
        _Stub([_trade("BBB"), _trade("CCC")], "senate"),
    ])
    r = c.fetch()
    assert [t.ticker for t in r.trades] == ["AAA", "BBB", "CCC"]
    assert r.source == "house+senate"
    assert r.error is None


def test_aggregates_errors_and_survives_a_raising_provider():
    c = CompositeDisclosureProvider([
        _Stub([_trade("AAA")], "house", error="senate gate 403"),
        _Raises(),
    ])
    r = c.fetch()
    assert [t.ticker for t in r.trades] == ["AAA"]      # healthy source still delivered
    assert "senate gate 403" in r.error
    assert "boom" in r.error                            # raising provider captured, not propagated

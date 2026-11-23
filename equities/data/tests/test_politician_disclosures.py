from datetime import date

from equities.data.politician_disclosures import (
    PoliticianTrade,
    _build_trade,
    parse_amount_range,
)


def test_parse_amount_range_standard_bracket():
    assert parse_amount_range("$50,001 - $100,000") == (50001, 100000)
    assert parse_amount_range("$1,001 - $15,000") == (1001, 15000)
    assert parse_amount_range("garbage") == (0, 0)


def test_build_trade_buy():
    t = _build_trade(
        ticker="NVDA",
        politician="Nancy Pelosi",
        chamber="house",
        raw_type="purchase",
        owner="spouse",
        amount="$50,001 - $100,000",
        txn_date="2026-06-10",
        filed_date="2026-06-29",
        url="https://disclosures-clerk.house.gov/x",
    )
    assert isinstance(t, PoliticianTrade)
    assert t.ticker == "NVDA"
    assert t.transaction_type == "buy"
    assert t.amount_min == 50001 and t.amount_max == 100000
    assert t.transaction_date == date(2026, 6, 10)
    assert t.date_filed == date(2026, 6, 29)
    assert t.filing_lag_days == 19
    assert t.chamber == "house"


def test_build_trade_missing_ticker_returns_none():
    assert _build_trade(
        ticker="--", politician="x", chamber="house", raw_type="purchase",
        owner="self", amount="", txn_date=None, filed_date=None, url=None,
    ) is None


def test_build_trade_malformed_fields_no_crash():
    """Non-string amount / unparseable date fields must not crash."""
    t = _build_trade(
        ticker="AAPL", politician="Rep A", chamber="senate",
        raw_type="purchase", owner="self",
        amount=12345, txn_date=20260601, filed_date="2026-06-20",
        url="http://x",
    )
    assert t.ticker == "AAPL"
    assert t.amount_min == 12345
    assert t.transaction_date is None

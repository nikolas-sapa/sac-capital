from datetime import date

import equities.data.politician_disclosures as mod
from equities.data.politician_disclosures import (
    PoliticianDisclosureProvider,
    PoliticianTrade,
    _normalize_house_record,
    parse_amount_range,
)


def test_parse_amount_range_standard_bracket():
    assert parse_amount_range("$50,001 - $100,000") == (50001, 100000)
    assert parse_amount_range("$1,001 - $15,000") == (1001, 15000)
    assert parse_amount_range("garbage") == (0, 0)


def test_normalize_house_record_buy():
    raw = {
        "ticker": "NVDA",
        "representative": "Nancy Pelosi",
        "type": "purchase",
        "owner": "spouse",
        "amount": "$50,001 - $100,000",
        "transaction_date": "2026-06-10",
        "disclosure_date": "2026-06-29",
        "ptr_link": "https://disclosures-clerk.house.gov/x",
    }
    t = _normalize_house_record(raw)
    assert isinstance(t, PoliticianTrade)
    assert t.ticker == "NVDA"
    assert t.transaction_type == "buy"
    assert t.amount_min == 50001 and t.amount_max == 100000
    assert t.transaction_date == date(2026, 6, 10)
    assert t.date_filed == date(2026, 6, 29)
    assert t.filing_lag_days == 19
    assert t.chamber == "house"


def test_normalize_house_record_missing_ticker_returns_none():
    assert _normalize_house_record({"ticker": "--", "type": "purchase"}) is None


def test_fetch_partial_failure_never_raises(monkeypatch):
    def fake_fetch_json(url, *, timeout):
        if "house" in url:
            return [{
                "ticker": "AAPL", "representative": "Rep A", "type": "purchase",
                "owner": "self", "amount": "$1,001 - $15,000",
                "transaction_date": "2026-06-01", "disclosure_date": "2026-06-20",
                "ptr_link": "http://x",
            }]
        raise ValueError("senate feed down")

    monkeypatch.setattr(mod, "_fetch_json", fake_fetch_json)
    result = PoliticianDisclosureProvider(house_url="http://house", senate_url="http://senate").fetch()
    assert len(result.trades) == 1
    assert result.trades[0].ticker == "AAPL"
    assert result.source == "house"
    assert result.error is not None and "senate" in result.error


def test_malformed_feed_never_raises(monkeypatch):
    """Non-list payloads and non-dict / non-string-field rows must not crash fetch()."""
    def fake_fetch_json(url, *, timeout):
        if "house" in url:
            return {"error": "AccessDenied"}          # dict, not list
        return [
            "garbage",                                  # non-dict row -> skipped
            {"ticker": "AAPL", "representative": "Rep A", "type": "purchase",
             "owner": "self", "amount": 12345,          # non-string amount
             "transaction_date": 20260601,              # non-string date
             "disclosure_date": "2026-06-20", "ptr_link": "http://x"},
        ]
    monkeypatch.setattr(mod, "_fetch_json", fake_fetch_json)
    result = PoliticianDisclosureProvider(house_url="http://house", senate_url="http://senate").fetch()
    assert result.error is not None and "house" in result.error  # dict payload surfaced as error
    assert len(result.trades) == 1                                # senate good row survived
    assert result.trades[0].ticker == "AAPL"
    assert result.trades[0].amount_min == 12345                   # str-coerced amount parsed
    assert result.trades[0].transaction_date is None              # numeric date -> None, no crash
